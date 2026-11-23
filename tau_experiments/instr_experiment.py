"""Experiment 2: which instructions? tau fixed (A), same dev sample, 3B model, temperature 0.

Usage, from the project folder, with Ollama and the gateway running:
    python tau_experiments/instr_experiment.py                         # all filter and join variants
    python tau_experiments/instr_experiment.py --filters F3 --joins J4  # only some
    python tau_experiments/instr_experiment.py --holdout F0 J5          # confirm a filter and a join choice
    python tau_experiments/instr_experiment.py --summary                # only rebuild summary_instructions.md
    python tau_experiments/instr_experiment.py --llm fake --results /tmp/test.csv   # test without a model

The variants are in variants.py (one general text per operator; F0 and J0 are the original texts).
Workload = the tau experiment sample: Q1 400 games, Q2 30 positives + 270 negatives (filters), Q6 the
first 5 games x 100 series (joins). Q4 and Q5 keep C0 / M0.
--holdout runs the original and the chosen variant on dev games the sample did not use: Q1 the other
600 main-set games, Q6 games 6-10 x 100 series. (Q2 has no holdout: all 30 dev visual novels are in
the sample.) The summary also pools sample and holdout: Q1 over all 1,000 games, Q6 over 10 games.
"""
import argparse
import os
import re

from common import RESULTS, fmt, holdout_files, latest, read_results, run_one, sample_files, write_summary
import variants


def jobs(a):
    if a.holdout:
        h = holdout_files()
        f_new, j_new = a.holdout
        return [("holdout", i, "Q1", ["--inputs", h["q1"]]) for i in dict.fromkeys(["F0", f_new])] + \
               [("holdout", i, "Q6", ["--inputs", h["q6"]]) for i in dict.fromkeys(["J0", j_new])]
    s = sample_files()
    out = []
    for i in a.filters:
        out += [("sample", i, "Q1", ["--inputs", s["q1"]]), ("sample", i, "Q2", ["--inputs", s["q2"]])]
    for i in a.joins:
        out.append(("sample", i, "Q6", ["--n", "5"]))
    return out


def _counts(logs, run_id, query):
    """(positives, found, correct) from a run's log: Q1 against the 'path' key, Q6 pairs."""
    with open(os.path.join(logs, run_id + ".log"), encoding="utf-8") as f:
        t = f.read()
    if query == "Q6":
        m = re.search(r"true pairs among them (\d+) \| accepted by the model (\d+) \| correct (\d+)", t)
    else:
        m = re.search(r"true positives (\d+) \| found (\d+) \| correct (\d+)", t.split("comparison with 'path'")[-1])
    return tuple(int(x) for x in m.groups()) if m else None


def summary(results):
    rows = read_results(results, "instructions")
    got = latest(rows, "workload", "instructions", "query")
    logs = os.path.join(os.path.dirname(results), "logs")
    lines = ["# Experiment 2: instructions, tau A (3B model, temperature 0)", ""]

    def cell(r, q):
        if not r:
            return "-"
        c = "%s (P %s R %s)" % (fmt(r["score"]), fmt(r["precision"], 2), fmt(r["recall"], 2)) if r["precision"] else fmt(r["score"])
        return c + (", %s accepted" % r["accepted_pairs"] if q == "Q6" and r["accepted_pairs"] else "")

    for workload, title in (("sample", "Sample: Q1 400 games, Q2 30 + 270, Q6 games 1-5 x 100 series"),
                            ("holdout", "Holdout: Q1 the other 600 games, Q6 games 6-10 x 100 series")):
        fs = [i for i in variants.FILTER_TESTED if (workload, i, "Q1") in got]
        js = [i for i in variants.JOIN_TESTED if (workload, i, "Q6") in got]
        if not fs and not js:
            continue
        lines += ["## " + title, ""]
        if fs:
            lines += ["| filter | Q1 F1 | Q2 F1 | mean | input tokens / call | parse failures |", "|---|---|---|---|---|---|"]
            for i in fs:
                r1, r2 = got.get((workload, i, "Q1")), got.get((workload, i, "Q2"))
                sc = [float(r["score"]) for r in (r1, r2) if r]
                tk = [float(r["input_tokens_per_call"]) for r in (r1, r2) if r and r["input_tokens_per_call"]]
                pf = sum(int(r["parse_failures"] or 0) for r in (r1, r2) if r)
                lines.append("| %s | %s | %s | %s | %s | %d |" % (i, cell(r1, "Q1"), cell(r2, "Q2"),
                             fmt(sum(sc) / len(sc)), fmt(sum(tk) / len(tk), 0) if tk else "-", pf))
            lines.append("")
        if js:
            lines += ["| join | Q6 F1 | input tokens / call | parse failures |", "|---|---|---|---|"]
            for i in js:
                r = got[(workload, i, "Q6")]
                lines.append("| %s | %s | %s | %s |" % (i, cell(r, "Q6"), fmt(r["input_tokens_per_call"], 0)
                             if r["input_tokens_per_call"] else "-", r["parse_failures"]))
            lines.append("")
    # pooled: variants run on both the sample and the holdout
    pooled = []
    for q, ids, what in (("Q1", variants.FILTER_TESTED, "Q1 over all 1,000 dev games"),
                         ("Q6", variants.JOIN_TESTED, "Q6 over 10 games x 100 series (10 true pairs)")):
        for i in ids:
            parts = [got.get((w, i, q)) for w in ("sample", "holdout")]
            if all(parts):
                c = [_counts(logs, r["run_id"], q) for r in parts]
                if all(c):
                    pos, found, correct = (sum(x[k] for x in c) for k in range(3))
                    p, rc = correct / found if found else 0.0, correct / pos if pos else 0.0
                    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
                    pooled.append("| %s | %s | %d of %d found correct | %s | %s | %s |" % (
                        what, i, correct, found, fmt(p, 2), fmt(rc, 2), fmt(f1)))
    if pooled:
        lines += ["## Sample and holdout pooled", "", "| query | instructions | answers | precision | recall | F1 |",
                  "|---|---|---|---|---|---|"] + pooled + [""]
    lines += ["Rule fixed in advance, per operator: the best mean F1 wins unless its input tokens per call are more "
              "than 25% above the original; differences under about 0.02-0.03 are ties and a tie keeps the original; "
              "the winner must hold on the holdout.",
              "Texts: variants.py (and semops/prompts.py for the frozen ones). Every run: results.csv "
              "(experiment = instructions). Full outputs: logs/."]
    write_summary(os.path.join(os.path.dirname(results), "summary_instructions.md"), lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--filters", nargs="+", choices=variants.FILTER_TESTED, default=variants.FILTER_TESTED)
    ap.add_argument("--joins", nargs="+", choices=variants.JOIN_TESTED, default=variants.JOIN_TESTED)
    ap.add_argument("--holdout", nargs=2, metavar=("FILTER", "JOIN"), help="e.g. --holdout F0 J5")
    ap.add_argument("--summary", action="store_true", help="only rebuild summary_instructions.md")
    ap.add_argument("--llm", choices=["gateway", "fake"], default="gateway")
    ap.add_argument("--results", default=RESULTS, help="results file (default tau_experiments/results.csv)")
    a = ap.parse_args()
    if a.holdout and (a.holdout[0] not in variants.FILTER_TESTED or a.holdout[1] not in variants.JOIN_TESTED):
        ap.error("--holdout takes a filter id then a join id, e.g. --holdout F0 J5")
    if not a.summary:
        for workload, instr, query, args in jobs(a):
            run_one(a.results, "instructions", workload, "A", instr, query, args, llm=a.llm)
    summary(a.results)


if __name__ == "__main__":
    main()
