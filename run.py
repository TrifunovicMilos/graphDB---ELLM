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
import time

from semops import config, engine, fake, operators, pipelines, runfiles
from semops.gateway import Gateway, GatewayError

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("query_id", choices=sorted(config.QUERY_KIND), help="Q1..Q6 or Q8")
p.add_argument("--query-file", help="override the default .rq file (e.g. query/q3_struttura_prima.rq)")
p.add_argument("--set", dest="set_name", choices=["dev", "eval"], default="dev")
p.add_argument("--data-root", default="data/games", help="folder holding dev/ and eval/")
p.add_argument("--llm", choices=["fake", "gateway"], default="fake")
p.add_argument("--model", default=config.DEFAULT_MODEL, help="public model name in the gateway's models.toml")
p.add_argument("--n", type=int, default=0, help="only the first N inputs (0 = all)")
p.add_argument("--m", type=int, default=0, help="Q6 tests only: M series on the right (0 = all)")
p.add_argument("--plan", default="ref", help="plan id for the run file (ref = reference plan)")
p.add_argument("--run-id", help="run id (default: <group>-<set>-<query>-<plan>-<timestamp>)")
p.add_argument("--reference-run", help="run id of the ref run this run is compared with")
p.add_argument("--source-run", help="Q8: run id of the Q1 run whose decisions are reused")
p.add_argument("--write-run", action="store_true", help="write the official run file under runs/")
p.add_argument("--prices", default="prices.json", help="our price list (JSON), used for run files")
p.add_argument("--yes", action="store_true", help="do not ask for confirmation on big runs")
a = p.parse_args()

a.repo_root = os.getcwd()
a.data_dir = os.path.join(a.data_root, a.set_name)
a.query_file = a.query_file or config.QUERY_FILES.get(a.query_id)
kind = config.QUERY_KIND[a.query_id]
stamp = time.strftime("%m%d%H%M%S")
a.run_id = a.run_id or f"{config.GROUP_ID}-{a.set_name}-{a.query_id.lower()}-{a.plan}-{stamp}"

if a.write_run and a.llm != "gateway" and kind != "count":
    raise SystemExit("--write-run needs --llm gateway (the calls come from the gateway log)")
if a.write_run and a.m:
    raise SystemExit("--write-run cannot be used with --m (a restricted right side is not a valid sample)")
if a.llm == "gateway" and kind != "count" and kind != "join" and (a.n == 0 or a.n > 100) and not a.yes:
    if input("Many model calls. Continue? (y/n) ") != "y":
        raise SystemExit("cancelled")

store = engine.load_graph(os.path.join(a.data_dir, "graph.nt"))
print("triples loaded:", len(store))

stats = operators.Stats()
gateway = None
if a.llm == "fake":
    backend = fake.FakeBackend()
else:
    gateway = Gateway(a.model, a.run_id)
    backend = operators.GatewayBackend(gateway)
    print("run id:", a.run_id, "| model:", a.model)

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
except GatewayError as e:
    raise SystemExit("ERROR: %s" % e)

print(f"\nfunction calls: {stats.calls} | broken answers: {stats.broken} | out of list: {stats.out_of_list}")
if gateway:
    print(f"gateway requests: {gateway.requests} | parse failures: {gateway.parse_failures} "
          f"| time waiting for the model: {gateway.seconds:.0f}s")

if a.write_run:
    path = runfiles.write_run(
        a.repo_root, query_id=a.query_id, data_set=a.set_name, run_id=a.run_id, plan_id=a.plan,
        model=a.model, answer=out.answer, n_input=out.n_input, sample=out.sample,
        started=out.started, finished=out.finished, wallclock=out.finished - out.started,
        prices_path=a.prices, reference_run_id=a.reference_run, source_run_id=a.source_run, labels=out.labels)
    print("run file written:", path)
