"""Shared parts of the tau and instruction experiments: paths, the fixed sample, one run, results.csv.

Every run goes through the project's own run.py (as a separate process, with the tested variants
registered through SEMOPS_VARIANTS), so an experiment run is exactly a normal run with other texts.
"""
import csv
import json
import os
import random
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from semops import config  # noqa: E402
import variants  # noqa: E402,F401  registers the tested variants in semops

DATA_DIR = os.path.join(ROOT, "data", "games", "dev")
SAMPLES = os.path.join(HERE, "samples")
RESULTS = os.path.join(HERE, "results.csv")          # every run of both experiments, one row each
VARIANTS_FILE = os.path.join(HERE, "variants.py")

FIELDS = ["experiment", "workload", "tau", "instructions", "query", "metric", "score", "precision", "recall",
          "accepted_pairs", "calls", "parse_failures", "input_tokens", "input_tokens_per_call", "cache_hits",
          "seconds", "model", "run_id", "finished"]
METRIC = {"Q1": "F1 (path)", "Q2": "F1 (path)", "Q4": "macro-F1", "Q6": "F1"}


def codes_in(path):
    with open(path, encoding="utf-8") as f:
        return [x.strip() for x in f if x.strip() and not x.startswith("#")]


def _write_codes(path, header, codes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# %s (%d)\n" % (header, len(codes)) + "\n".join(codes) + "\n")


def sample_files():
    """The fixed dev sample, written once (seed 42) and then reused, so every run sees the same games.

    Q1 400 random main-set games; Q2 all 30 positives + 270 random negatives; Q4 200 random Q4 inputs.
    (Q6 needs no file: the first 5 left games x all 100 series, run.py --n 5.)
    """
    paths = {q: os.path.join(SAMPLES, "sample_dev_%s.txt" % q) for q in ("q1", "q2", "q4")}
    if all(os.path.isfile(x) for x in paths.values()):
        return paths
    with open(os.path.join(DATA_DIR, "sets.csv"), encoding="utf-8") as f:
        main = sorted(r["qid"] for r in csv.DictReader(f) if r["set_id"] == "main")

    def gt(name):
        with open(os.path.join(DATA_DIR, "gt", name + ".csv"), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    q2_pos = sorted(r["qid"] for r in gt("q2") if r["path"] == "1")
    rng = random.Random(42)
    sample = {"q1": sorted(rng.sample(main, 400)),
              "q2": sorted(q2_pos + rng.sample([x for x in main if x not in set(q2_pos)], 270)),
              "q4": sorted(rng.sample(sorted(r["qid"] for r in gt("q4")), 200))}
    for q, codes in sample.items():
        _write_codes(paths[q], "tau experiment sample, dev set, seed 42", codes)
    return paths


def holdout_files():
    """Dev games the sample does not use: Q1 the other 600 main-set games; Q6 left games 6-10."""
    used = set(codes_in(sample_files()["q1"]))
    with open(os.path.join(DATA_DIR, "sets.csv"), encoding="utf-8") as f:
        sets = list(csv.DictReader(f))
    main = sorted(r["qid"] for r in sets if r["set_id"] == "main")
    left = sorted(r["qid"] for r in sets if r["set_id"] == "q6_left")
    paths = {"q1": os.path.join(SAMPLES, "holdout_dev_q1.txt"), "q6": os.path.join(SAMPLES, "holdout_dev_q6_left.txt")}
    if not os.path.isfile(paths["q1"]):
        _write_codes(paths["q1"], "holdout, dev set: main-set games outside the sample", [x for x in main if x not in used])
    if not os.path.isfile(paths["q6"]):
        _write_codes(paths["q6"], "holdout, dev set: Q6 left games 6-10", left[5:10])
    return paths


def parse_output(query, out):
    """(score, precision, recall, accepted pairs) from the output of run.py."""
    if query in ("Q1", "Q2"):
        m = re.search(r"precision: ([\d.]+)\s+recall: ([\d.]+)", out.split("comparison with 'path'")[-1])
        if not m:
            return None, None, None, None
        p, r = float(m.group(1)), float(m.group(2))
        return (2 * p * r / (p + r) if p + r else 0.0), p, r, None
    if query == "Q4":
        m = re.search(r"macro-F1: ([\d.]+)", out)
        return (float(m.group(1)) if m else None), None, None, None
    if query == "Q6":
        m = re.search(r"precision: ([\d.]+)\s+recall: ([\d.]+)\s+F1: ([\d.]+)", out)
        acc = re.search(r"accepted by the model (\d+)", out)
        if not m:
            return None, None, None, None
        return float(m.group(3)), float(m.group(1)), float(m.group(2)), (int(acc.group(1)) if acc else None)
    return None, None, None, None


def gateway_usage(run_id):
    """(distinct requests, their input tokens, cache hits) of one run, from the gateway log."""
    if not os.path.isfile(config.GATEWAY_LOG):
        return None, None, None
    first, hits = {}, 0
    with open(config.GATEWAY_LOG, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("run_id") == run_id:
                hits += bool(rec.get("cache_hit"))
                first.setdefault(rec.get("key"), rec.get("tokens_in") or 0)
    return len(first), sum(first.values()), hits


def run_one(results, experiment, workload, tau, instr, query, args, llm="gateway", model=config.DEFAULT_MODEL):
    """One execution of run.py; its output goes to logs/<run_id>.log and one row to `results`."""
    logs = os.path.join(os.path.dirname(results), "logs")
    base = f"{config.GROUP_ID}-dev-{query.lower()}-{experiment}-{workload}-tau{tau}-{instr}-{time.strftime('%m%d%H%M%S')}"
    run_id, k = base, 1
    while os.path.exists(os.path.join(logs, run_id + ".log")):   # never reuse a run id (the log is read by it)
        k += 1
        run_id = "%s-%d" % (base, k)
    cmd = [sys.executable, os.path.join(ROOT, "run.py"), query, "--tau", tau, "--instr", instr, "--llm", llm,
           "--model", model, "--run-id", run_id, "--yes"] + args
    print(">>> %-11s %-7s tau %-5s %-3s %s %s" % (experiment, workload, tau, instr, query, " ".join(args)), flush=True)
    env = dict(os.environ, SEMOPS_VARIANTS=VARIANTS_FILE)
    start = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    seconds = time.time() - start
    out = proc.stdout + proc.stderr
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, run_id + ".log"), "w", encoding="utf-8") as f:
        f.write(" ".join(cmd) + "\n\n" + out)
    if proc.returncode != 0:
        print("    FAILED (exit %d):\n%s" % (proc.returncode, "\n".join(out.splitlines()[-8:])))
        return None
    score, p, r, accepted = parse_output(query, out)
    m = re.search(r"function calls: (\d+) \| broken answers: (\d+)", out)
    n_req, tok, hits = gateway_usage(run_id) if llm == "gateway" else (None, None, None)
    row = {"experiment": experiment, "workload": workload, "tau": tau, "instructions": instr, "query": query,
           "metric": METRIC.get(query, ""), "score": score, "precision": p, "recall": r, "accepted_pairs": accepted,
           "calls": int(m.group(1)) if m else None, "parse_failures": int(m.group(2)) if m else None,
           "input_tokens": tok, "input_tokens_per_call": round(tok / n_req, 1) if n_req else None,
           "cache_hits": hits, "seconds": round(seconds), "model": model if llm == "gateway" else "fake",
           "run_id": run_id, "finished": time.strftime("%Y-%m-%d %H:%M")}
    new = not os.path.isfile(results)
    with open(results, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print("    %s %s | calls %s | parse failures %s | input tokens/call %s | %d s" % (
        row["metric"], fmt(score), row["calls"], row["parse_failures"], row["input_tokens_per_call"], seconds))
    return row


def read_results(results, experiment):
    if not os.path.isfile(results):
        return []
    with open(results, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["experiment"] == experiment]


def latest(rows, *keys):
    """The last row for each combination of `keys` (a re-run replaces the earlier one)."""
    out = {}
    for r in rows:
        out[tuple(r[k] for k in keys)] = r
    return out


def fmt(x, digits=3):
    return "-" if x in (None, "") else "%.*f" % (digits, float(x))


def write_summary(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines) + "\nwritten: " + path)
