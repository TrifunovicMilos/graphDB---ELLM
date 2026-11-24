"""The program you launch. One command = one execution of one query.

Examples (from the project folder):
  python run.py Q1 --llm fake --n 60                       free, no gateway
  python run.py Q1 --llm gateway --n 20                    real model through the gateway
  python run.py Q6 --llm gateway --n 6 --m 10              small join test
  python run.py Q1 --llm gateway --plan ref --write-run    full reference run + official run file
  python run.py Q8 --source-run <run_id of the Q1 run> --write-run

Query ids: Q1 Q2 Q3 Q4 Q5 Q6 Q8. The type of operator follows from the id.
Before using the gateway: `start server` in the gateway folder (see README).
"""
import argparse
import os
import runpy
import tempfile
import time

from semops import cascade, config, engine, fake, operators, pipelines, prompts, runfiles
from semops.gateway import Gateway, GatewayError
from semops.operators import ModelCallError

# The experiments in tau_experiments/ register the tau and instruction variants they tested this way;
# without the variable only the frozen ones (prompts.PROMPT_VERSION) exist.
if os.environ.get("SEMOPS_VARIANTS"):
    runpy.run_path(os.environ["SEMOPS_VARIANTS"])
INSTR_IDS = prompts.instruction_ids()

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("query_id", choices=sorted(config.QUERY_KIND), help="Q1..Q6 or Q8")
p.add_argument("--query-file", help="override the default .rq file (e.g. query/q3_struttura_prima.rq)")
p.add_argument("--set", dest="set_name", choices=["dev", "eval"], default="dev")
p.add_argument("--data-root", default="data/games", help="folder holding dev/ and eval/")
p.add_argument("--llm", choices=["fake", "gateway"], default="fake")
p.add_argument("--model", default=config.DEFAULT_MODEL, help="public model name in the gateway's models.toml")
p.add_argument("--tau", choices=sorted(prompts.TAU_BUILDERS), default=config.DEFAULT_TAU,
               help="text of an entity (default %(default)s, the frozen one)")
p.add_argument("--instr", choices=sorted(INSTR_IDS),
               help="instructions for the operator of this query (default: the frozen ones, prompts.INSTR_DEFAULT)")
p.add_argument("--inputs", help="file with one game code (Q...) per line: run only on these (tests, no --write-run)")
p.add_argument("--n", type=int, default=0, help="only the first N inputs (0 = all)")
p.add_argument("--m", type=int, default=0, help="Q6 tests only: M series on the right (0 = all)")
p.add_argument("--plan", default="ref", help="plan id for the run file (ref = reference plan; o1... = the O1 cascade)")
p.add_argument("--proxy-model", default="local/qwen2.5:3b", help="O1: the cheap model that answers first (--model is the oracle)")
p.add_argument("--theta-low", type=float, help="O1: proxy score <= this -> no (from o1_cascade/calibrate.py)")
p.add_argument("--theta-high", type=float, help="O1: proxy score >= this -> yes; in between the oracle decides")
p.add_argument("--target", type=float, help="O1: the target f1_ref these thresholds were calibrated for (recorded only)")
p.add_argument("--run-id", help="run id (default: <group>-<set>-<query>-<plan>-<timestamp>)")
p.add_argument("--reference-run", help="run id of the ref run this run is compared with")
p.add_argument("--source-run", help="Q8: run id of the Q1 run whose decisions are reused")
p.add_argument("--write-run", action="store_true", help="write the official run file under runs/")
p.add_argument("--gt", help="solution file (default: data/games/<set>/gt/<query>.csv, found automatically)")
p.add_argument("--prices", default="prices.json", help="our price list (JSON), used for run files")
p.add_argument("--yes", action="store_true", help="do not ask for confirmation on big runs")
a = p.parse_args()

a.repo_root = os.getcwd()
a.data_dir = os.path.join(a.data_root, a.set_name)
a.query_file = a.query_file or config.QUERY_FILES.get(a.query_id)
kind = config.QUERY_KIND[a.query_id]
operator = {"extract": "map"}.get(kind, kind)
if a.instr and INSTR_IDS[a.instr] != operator:
    raise SystemExit("--instr %s is for %s, but %s is a %s query" % (a.instr, INSTR_IDS[a.instr], a.query_id, operator))
a.instr = a.instr or prompts.INSTR_DEFAULT.get(operator, "")
frozen = a.tau == config.DEFAULT_TAU and a.instr == prompts.INSTR_DEFAULT.get(operator, "")
a.cascade = a.plan.startswith("o1")
if a.cascade and (kind != "filter" or a.llm != "gateway" or a.theta_low is None or a.theta_high is None):
    raise SystemExit("--plan o1... needs a filter query (Q1-Q3), --llm gateway, --theta-low and --theta-high")
stamp = time.strftime("%m%d%H%M%S")
a.run_id = a.run_id or f"{config.GROUP_ID}-{a.set_name}-{a.query_id.lower()}-{a.plan}-tau{a.tau}{'-' + a.instr if a.instr else ''}-{stamp}"

if a.write_run and a.llm != "gateway" and kind != "count":
    raise SystemExit("--write-run needs --llm gateway (the calls come from the gateway log)")
if a.inputs:
    # restrict the query to the listed games: a temporary copy of the .rq with VALUES ?e { ... }
    if a.write_run:
        raise SystemExit("--inputs is for tests: it cannot be used with --write-run")
    with open(a.inputs, encoding="utf-8") as f:
        codes = [x.strip() for x in f if x.strip() and not x.startswith("#")]
    with open(a.query_file, encoding="utf-8") as f:
        text = f.read()
    marker = "{ SELECT ?e WHERE {"
    if kind == "join":
        a.left_inputs = codes                       # the join takes these games on the left side
    elif marker not in text:
        raise SystemExit("--inputs needs a query with '%s' (Q1, Q2, Q4, Q5) or the join" % marker)
    else:
        values = " VALUES ?e { " + " ".join("<%s%s>" % (config.WD, c) for c in codes) + " }"
        tmp = tempfile.NamedTemporaryFile("w", suffix=".rq", delete=False, encoding="utf-8")
        tmp.write(text.replace(marker, marker + values, 1))
        tmp.close()
        a.query_file = tmp.name
if a.write_run and a.m:
    raise SystemExit("--write-run cannot be used with --m (a restricted right side is not a valid sample)")
if a.llm == "gateway" and kind != "count" and kind != "join" and (a.n == 0 or a.n > 100) and not a.yes:
    if input("Many model calls. Continue? (y/n) ") != "y":
        raise SystemExit("cancelled")

store = engine.load_graph(os.path.join(a.data_dir, "graph.nt"), a.tau)
print("triples loaded:", len(store), "| tau:", a.tau)

stats = operators.Stats()
gateway = None
if a.llm == "fake":
    backend = fake.FakeBackend()
else:
    gateway = Gateway(a.model, a.run_id, namespace=f"{config.CACHE_NAMESPACE}-tau{a.tau}")
    if a.cascade:      # same run id and cache namespace for both, so the oracle's requests are the reference's
        proxy = Gateway(a.proxy_model, a.run_id, namespace=f"{config.CACHE_NAMESPACE}-tau{a.tau}")
        backend = cascade.CascadeBackend(proxy, gateway, a.theta_low, a.theta_high,
                                         prompts.INSTRUCTIONS[operator][a.instr])
        print("O1 cascade | proxy:", a.proxy_model, "| oracle:", a.model, "| theta_low", a.theta_low, "| theta_high", a.theta_high)
    else:
        backend = operators.GatewayBackend(gateway, {operator: prompts.INSTRUCTIONS[operator][a.instr]}
                                           if a.instr else None)
    print("run id:", a.run_id, "| model:", a.model, "| instructions:", a.instr)

try:
    if kind == "filter":
        out = pipelines.run_filter(a, store, backend, stats)
    elif kind == "classify":
        out = pipelines.run_classify(a, store, backend, stats)
    elif kind == "extract":
        out = pipelines.run_extract(a, store, backend, stats)
    elif kind == "join":
        out = pipelines.run_join(a, store, backend, stats)
    else:
        if not a.source_run:
            raise SystemExit("Q8 needs --source-run <run id of the Q1 run>")
        out = pipelines.run_count(a, store)
except (GatewayError, ModelCallError) as e:
    raise SystemExit("ERROR: %s" % e)

print(f"\nfunction calls: {stats.calls} | broken answers: {stats.broken} | out of list: {stats.out_of_list}")
if a.cascade:
    print(f"O1: decided by the proxy {backend.by_proxy} | by the oracle {backend.by_oracle} "
          f"(of which proxy answers without a score: {backend.unscored})")
if gateway:
    print(f"gateway requests: {gateway.requests} | parse failures: {gateway.parse_failures} "
          f"| time waiting for the model: {gateway.seconds:.0f}s")

if a.write_run:
    path = runfiles.write_run(
        a.repo_root, query_id=a.query_id, data_set=a.set_name, run_id=a.run_id, plan_id=a.plan,
        model=a.model, answer=out.answer, n_input=out.n_input, sample=out.sample,
        started=out.started, finished=out.finished, wallclock=out.finished - out.started,
        prices_path=a.prices, reference_run_id=a.reference_run, source_run_id=a.source_run, labels=out.labels,
        model_proxy=a.proxy_model if a.cascade else None,
        plan_params=dict({"prompt_version": prompts.PROMPT_VERSION if frozen else "experimental",
                          "tau": a.tau, "instructions": a.instr},
                         **({"proxy_score": cascade.SCORE_METHOD, "theta_low": a.theta_low, "theta_high": a.theta_high,
                             "target_f1_ref": a.target} if a.cascade else {})))
    print("run file written:", path)
