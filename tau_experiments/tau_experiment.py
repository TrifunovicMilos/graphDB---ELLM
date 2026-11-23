"""Experiment 1: which tau (text of an entity)? Same fixed dev sample for every variant, 3B model, temperature 0.

Usage, from the project folder, with Ollama and the gateway running:
    python tau_experiments/tau_experiment.py                  # all variants of variants.TAU_SPECS
    python tau_experiments/tau_experiment.py --taus A C-600   # only some
    python tau_experiments/tau_experiment.py --pilot          # tiny workload, to check the chain first
    python tau_experiments/tau_experiment.py --summary        # only rebuild summary_tau.md
    python tau_experiments/tau_experiment.py --llm fake --results /tmp/test.csv   # test without a model

Workload (identical for every variant; about 1,400 calls each):
    Q1 platformer      400 random main-set games          F1 against the expanded key ("path")
    Q2 visual novel    all 30 positives + 270 negatives   F1 against the expanded key
    Q4 genre           200 random Q4 inputs               macro-F1
    Q6 game ~ series   first 5 games x all 100 series     F1, and the number of pairs accepted
The instructions are the ORIGINAL ones of that time (F0, C0, J0), so the runs can be repeated as they were.
Pilot: Q1 and Q2 on the first 50 games, Q4 on 30, Q6 on 1 game x 100 series.

Each tau variant has its own gateway cache namespace, so re-running a variant costs nothing.
"""
import argparse
import os

from common import RESULTS, fmt, latest, read_results, run_one, sample_files, write_summary
import variants

INSTR = {"Q1": "F0", "Q2": "F0", "Q4": "C0", "Q6": "J0"}      # the instructions of the tau experiment
QUERIES = ["Q1", "Q2", "Q4", "Q6"]


def workload(pilot):
    if pilot:
        return "pilot", [("Q1", ["--n", "50"]), ("Q2", ["--n", "50"]), ("Q4", ["--n", "30"]), ("Q6", ["--n", "1"])]
    s = sample_files()
    return "sample", [("Q1", ["--inputs", s["q1"]]), ("Q2", ["--inputs", s["q2"]]),
                      ("Q4", ["--inputs", s["q4"]]), ("Q6", ["--n", "5"])]


def summary(results):
    rows = [r for r in read_results(results, "tau") if r["workload"] == "sample"]
    got = latest(rows, "tau", "query")
    taus = [t for t in variants.TAU_TESTED if any(k[0] == t for k in got)]
    lines = ["# Experiment 1: tau, dev sample (3B model, temperature 0)", "",
             "| tau | Q1 F1 | Q2 F1 | Q4 macro-F1 | Q6 F1 (pairs accepted, 5 true) | mean of 4 | input tokens / call | parse failures |",
             "|---|---|---|---|---|---|---|---|"]
    for t in taus:
        cells, scores, toks, broken = [], [], [], 0
        for q in QUERIES:
            r = got.get((t, q))
            if not r:
                cells.append("-")
                continue
            c = fmt(r["score"])
            if q == "Q6" and r["accepted_pairs"]:
                c += " (%s)" % r["accepted_pairs"]
            cells.append(c)
            scores.append(float(r["score"]))
            if r["input_tokens_per_call"]:
                toks.append(float(r["input_tokens_per_call"]))
            broken += int(r["parse_failures"] or 0)
        mean = fmt(sum(scores) / len(scores)) + ("" if len(scores) == len(QUERIES) else " (incomplete)") if scores else "-"
        lines.append("| %s | %s | %s | %s | %s |" % (t, " | ".join(cells), mean,
                     fmt(sum(toks) / len(toks), 0) if toks else "-", broken))
    lines += ["", "Rule fixed in advance: the best mean wins, unless its input tokens per call are more than 25% "
              "above the cheapest variant; differences under about 0.02-0.03 are ties.",
              "Variants: variants.TAU_SPECS. Every run: results.csv (experiment = tau). Full outputs: logs/."]
    write_summary(os.path.join(os.path.dirname(results), "summary_tau.md"), lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--taus", nargs="+", choices=variants.TAU_TESTED, default=variants.TAU_TESTED)
    ap.add_argument("--pilot", action="store_true", help="tiny workload, to check the chain first")
    ap.add_argument("--summary", action="store_true", help="only rebuild summary_tau.md")
    ap.add_argument("--llm", choices=["gateway", "fake"], default="gateway")
    ap.add_argument("--results", default=RESULTS, help="results file (default tau_experiments/results.csv)")
    a = ap.parse_args()
    if not a.summary:
        name, jobs = workload(a.pilot)
        for tau in a.taus:
            for query, args in jobs:
                run_one(a.results, "tau", name, tau, INSTR[query], query, args, llm=a.llm)
    summary(a.results)


if __name__ == "__main__":
    main()
