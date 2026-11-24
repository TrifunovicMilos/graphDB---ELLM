"""O1 calibration on the development set: the cost/agreement curve of the cascade and its operating points.

Usage, from the project folder, with the gateway running (Ollama only if a proxy answer is not cached):
    python o1_cascade/calibrate.py --reference g00-dev-q1-ref
    python o1_cascade/calibrate.py --reference g00-dev-q1-ref --targets 0.90 0.95 0.99
    python o1_cascade/calibrate.py --reference g00-dev-q1-ref --rescore      # recompute the proxy scores
    python o1_cascade/calibrate.py --reference g00-dev-q1-ref --curve-rows 60  # list more points of the curve

How it works (semops/cascade.py has the decision rule):
  1. Proxy scores: the proxy (local/qwen2.5:3b) answers every input with the frozen prompt, through the
     gateway, and its log-probabilities give a score per input. On dev these answers are already in the
     gateway cache, so this costs nothing. Saved to o1_cascade/scores_<set>_<query>.csv and reused.
  2. Oracle answers: read from the reference run file runs/games/<set>/<query>/<reference>.json
     (the oracle on every input). No model call.
  3. For every pair of thresholds the cascade's answer per input is known without any call: below
     theta_low the proxy says no, above theta_high it says yes, in between the oracle's reference answer
     is used. So the whole curve "share of inputs sent to the oracle" vs "agreement with the reference"
     is computed exactly, and for each target the cheapest thresholds are chosen.

Agreement is measured as the checker does for a filter: precision, recall and F1 of the cascade's
answer set against the reference's answer set (f1_ref). The share of decisions that match is shown too.
Calibrate on dev only; on eval the chosen thresholds run once (python run.py ... --plan o1-...).

Outputs in o1_cascade/: calibration_<set>_<query>.md (operating points + curve, for the report),
frontier_<set>_<query>.csv (every best point), frontier_<set>_<query>.png (if matplotlib is installed).
"""
import argparse
import csv
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from semops import cascade, config, prompts  # noqa: E402
from semops.gateway import Gateway  # noqa: E402

PROXY = "local/qwen2.5:3b"


def main_set(data_dir):
    with open(os.path.join(data_dir, "sets.csv"), encoding="utf-8") as f:
        return sorted(r["qid"] for r in csv.DictReader(f) if r["set_id"] == "main")


def compute_scores(a, codes, path):
    """The proxy on every input through the gateway (cache hits on dev); writes the scores CSV."""
    with open(os.path.join(a.data_dir, "entities.csv"), encoding="utf-8", newline="") as f:
        entities = {r["qid"]: r for r in csv.DictReader(f)}
    instructions = prompts.INSTRUCTIONS["filter"][prompts.INSTR_DEFAULT["filter"]]
    criterion = config.LANGEX[a.query]
    run_id = "%s-%s-%s-o1-calibration-%s" % (config.GROUP_ID, a.set_name, a.query.lower(), time.strftime("%m%d%H%M%S"))
    gw = Gateway(a.proxy_model, run_id, namespace="%s-tau%s" % (config.CACHE_NAMESPACE, config.DEFAULT_TAU))
    rows, start = [], time.time()
    for i, q in enumerate(codes, 1):
        e = entities[q]
        text = prompts.filter_text(criterion, prompts.tau(config.DEFAULT_TAU, e["label"], e["description_screened"], e["lead"]))
        answer, response = gw.ask_response(instructions, text, "boolean_answer", prompts.BOOL_SCHEMA)
        score, exact = cascade.proxy_score(response)
        rows.append({"qid": q, "label": e["label"], "proxy_answer": "" if answer is None else answer["answer"],
                     "score": "" if score is None else round(score, 6), "exact": exact})
        if i % 100 == 0:
            print("  proxy scores: %d / %d (%.0f s)" % (i, len(codes), time.time() - start), flush=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "label", "proxy_answer", "score", "exact"])
        w.writeheader()
        w.writerows(rows)
    print("proxy scores written:", path, "| gateway run id:", run_id, "| %.0f s" % (time.time() - start))


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def frontier(scores, oracle):
    """All best cascades: for every number of oracle calls, the thresholds with the best f1_ref.

    scores: {qid: score}; oracle: {qid: bool}. Returns a list of dicts sorted by oracle calls.
    """
    values = sorted(set(scores.values()))
    U, N = len(values), len(scores)
    yes = {v: 0 for v in values}
    tot = {v: 0 for v in values}
    for q, s in scores.items():
        tot[s] += 1
        yes[s] += oracle[q]
    Y, T = [0], [0]                                     # prefix sums over the sorted score groups
    for v in values:
        Y.append(Y[-1] + yes[v])
        T.append(T[-1] + tot[v])
    ytot = Y[-1]

    def theta(k):                                       # a cut between group k-1 and group k
        if k <= 0:
            return values[0] - 1.0
        if k >= U:
            return values[-1] + 1.0
        return (values[k - 1] + values[k]) / 2

    best = {}
    for i in range(U + 1):                              # groups below i: the proxy says no
        for j in range(i, U + 1):                       # groups from j on: the proxy says yes
            yes_below = Y[i]
            no_above = (N - T[j]) - (ytot - Y[j])
            calls = T[j] - T[i]
            tp, fp, fn = ytot - yes_below, no_above, yes_below
            f1 = 1.0 if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)
            if calls not in best or f1 > best[calls]["f1_ref"]:
                best[calls] = {"oracle_calls": calls, "oracle_share": calls / N, "f1_ref": f1,
                               "precision_ref": tp / (tp + fp) if tp + fp else 1.0,
                               "recall_ref": tp / (tp + fn) if tp + fn else 1.0,
                               "agreement": 1 - (yes_below + no_above) / N, "disagreements": yes_below + no_above,
                               "theta_low": theta(i), "theta_high": theta(j)}
    points, top = [], -1.0                              # keep only points that improve on every cheaper one
    for calls in sorted(best):
        if best[calls]["f1_ref"] > top + 1e-12:
            points.append(best[calls])
            top = best[calls]["f1_ref"]
    return points


def cascade_answers(scores, oracle, lo, hi):
    out = {}
    for q, s in scores.items():
        d = cascade.decide(s, lo, hi)
        out[q] = oracle[q] if d is None else d
    return out


def prf(pred, gold):
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 1.0
    r = tp / len(gold) if gold else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", required=True, help="run id of the reference run (plan ref, the oracle on every input)")
    ap.add_argument("--query", choices=["Q1", "Q2"], default="Q1")
    ap.add_argument("--set", dest="set_name", choices=["dev"], default="dev", help="calibrate on dev only")
    ap.add_argument("--proxy-model", default=PROXY)
    ap.add_argument("--targets", type=float, nargs="+", default=[0.90, 0.95, 0.99], help="target f1_ref values")
    ap.add_argument("--rescore", action="store_true", help="recompute the proxy scores even if the CSV exists")
    ap.add_argument("--curve-rows", type=int, default=25, help="about how many points of the curve to list in the report")
    a = ap.parse_args()
    a.data_dir = os.path.join(ROOT, "data", "games", a.set_name)
    tag = "%s_%s" % (a.set_name, a.query.lower())

    ref_path = os.path.join(ROOT, "runs", config.DOMAIN, a.set_name, a.query, a.reference + ".json")
    with open(ref_path, encoding="utf-8") as f:
        ref = json.load(f)
    if ref["run"]["plan_id"] != "ref":
        raise SystemExit("%s is not a run of the plan ref" % a.reference)
    codes = main_set(a.data_dir)
    if ref["run"]["n_input_bindings"] != len(codes) or ref["run"]["sample"] is not None:
        raise SystemExit("the reference run must cover the whole input set (%d inputs)" % len(codes))
    accepted = {b["entity"]["value"].rsplit("/", 1)[-1] for b in ref["answer"]["results"]["bindings"]}
    oracle = {q: q in accepted for q in codes}
    prices = ref["price_list"]["models"]
    first = {}
    for c in ref["calls"]:
        first.setdefault(c["key"], c)
    ref_cost = sum((c["tokens_in"] * prices[c["model"]]["input_per_million"] +
                    c["tokens_out"] * prices[c["model"]]["output_per_million"]) / 1e6 for c in first.values())

    scores_path = os.path.join(HERE, "scores_%s.csv" % tag)
    if a.rescore or not os.path.isfile(scores_path):
        compute_scores(a, codes, scores_path)
    with open(scores_path, encoding="utf-8") as f:
        srows = list(csv.DictReader(f))
    missing = [r["qid"] for r in srows if r["score"] == ""]
    if missing:
        raise SystemExit("%d inputs have no proxy score (parse failures); first: %s" % (len(missing), missing[:5]))
    scores = {r["qid"]: float(r["score"]) for r in srows}
    if set(scores) != set(codes):
        raise SystemExit("the scores file does not match the input set; run with --rescore")
    with open(os.path.join(a.data_dir, "gt", a.query.lower() + ".csv"), encoding="utf-8") as f:
        gold = {r["qid"] for r in csv.DictReader(f) if r["path"] == "1"}

    points = frontier(scores, oracle)
    N = len(codes)
    proxy_alone = {q: scores[q] > 0 for q in codes}            # the proxy's own answer (score sign)
    chosen = []
    for t in a.targets:
        p = dict(next((x for x in points if x["f1_ref"] >= t), points[-1]))
        p["theta_low"], p["theta_high"] = round(p["theta_low"], 6), round(p["theta_high"], 6)   # as printed below
        ans = cascade_answers(scores, oracle, p["theta_low"], p["theta_high"])
        assert sum(ans[q] != oracle[q] for q in codes) == p["disagreements"], "threshold placement mismatch"
        _, _, f1_gt = prf({q for q in codes if ans[q]}, gold)
        lo, hi = wilson(N - p["disagreements"], N)
        chosen.append(dict(p, target=t, f1_gt=f1_gt, agreement_low=lo, agreement_high=hi,
                           est_cost=ref_cost * p["oracle_calls"] / N))

    proxy_f1_ref = prf({q for q in codes if proxy_alone[q]}, accepted)[2]
    proxy_f1_gt = prf({q for q in codes if proxy_alone[q]}, gold)[2]
    oracle_f1_gt = prf(accepted, gold)[2]

    with open(os.path.join(HERE, "frontier_%s.csv" % tag), "w", encoding="utf-8", newline="") as f:
        fields = ["oracle_calls", "oracle_share", "f1_ref", "precision_ref", "recall_ref", "agreement", "disagreements",
                  "theta_low", "theta_high"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in points:
            w.writerow({k: (round(p[k], 6) if isinstance(p[k], float) else p[k]) for k in fields})

    exact = sum(r["exact"] == "True" for r in srows)
    lines = ["# O1 calibration, %s, %s" % (a.query, a.set_name), "",
             "Proxy `%s` (scores: %s; exact for %d of %d inputs, a bound for the rest). Oracle `%s`, reference run `%s` "
             "(%d inputs, %d accepted, cost $%.4f)." % (a.proxy_model, cascade.SCORE_METHOD, exact, N,
                                                        ref["run"]["model_oracle"], a.reference, N, len(accepted), ref_cost), "",
             "## Operating points", "",
             "| target f1_ref | theta_low | theta_high | oracle calls | f1_ref (P / R) | decisions = reference (95% CI) | F1 vs answer key | est. oracle cost |",
             "|---|---|---|---|---|---|---|---|"]
    for p in chosen:
        lines.append("| %.2f | %.6f | %.6f | %d (%.1f%%) | %.3f (%.3f / %.3f) | %.3f (%.3f-%.3f) | %.3f | $%.4f |" % (
            p["target"], p["theta_low"], p["theta_high"], p["oracle_calls"], 100 * p["oracle_share"], p["f1_ref"],
            p["precision_ref"], p["recall_ref"], p["agreement"], p["agreement_low"], p["agreement_high"], p["f1_gt"], p["est_cost"]))
    lines += ["", "Ends of the curve: the proxy alone (0 oracle calls) has f1_ref %.3f and F1 %.3f against the answer key; "
              "the oracle alone (the reference, %d calls) has f1_ref 1 and F1 %.3f." % (proxy_f1_ref, proxy_f1_gt, N, oracle_f1_gt), "",
              "## The curve (best f1_ref for each number of oracle calls)", "",
              "| oracle calls | share | f1_ref | decisions = reference | theta_low | theta_high |", "|---|---|---|---|---|---|"]
    step = max(1, len(points) // a.curve_rows)
    for p in points[::step] + ([points[-1]] if (len(points) - 1) % step else []):
        lines.append("| %d | %.1f%% | %.3f | %.3f | %.4f | %.4f |" % (p["oracle_calls"], 100 * p["oracle_share"], p["f1_ref"],
                     p["agreement"], p["theta_low"], p["theta_high"]))
    lines += ["", "## Run the operating points (official run files)", "", "```bash"]
    for p in chosen:
        name = "o1-%02d" % round(100 * p["target"])
        lines.append("python run.py %s --set %s --plan %s --model %s --proxy-model %s --theta-low %.6f --theta-high %.6f "
                     "--target %.2f --reference-run %s --run-id %s-%s-%s-%s --write-run --yes" % (
                         a.query, a.set_name, name, ref["run"]["model_oracle"], a.proxy_model, p["theta_low"], p["theta_high"],
                         p["target"], a.reference, config.GROUP_ID, a.set_name, a.query.lower(), name))
    lines += ["```", "", "Thresholds are learned here, on dev, and must not be changed for eval."]
    md = os.path.join(HERE, "calibration_%s.md" % tag)
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines) + "\n\nwritten: " + md)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib not installed: no plot; `pip install matplotlib` for frontier_%s.png)" % tag)
        return
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot([100 * p["oracle_share"] for p in points], [p["f1_ref"] for p in points], color="#185FA5", lw=1.6,
            label="best cascade for each number of oracle calls")
    ax.scatter([0], [proxy_f1_ref], color="#888780", zorder=3, label="proxy alone")
    for p in chosen:
        ax.scatter([100 * p["oracle_share"]], [p["f1_ref"]], color="#D85A30", zorder=4)
        ax.annotate("%.2f" % p["target"], (100 * p["oracle_share"], p["f1_ref"]), textcoords="offset points",
                    xytext=(5, -10), fontsize=7)
    ax.set_xlabel("inputs sent to the oracle (%)")
    ax.set_ylabel("F1 against the reference (f1_ref)")
    ax.set_title("O1 cascade, %s %s: cost vs agreement" % (a.query, a.set_name))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    png = os.path.join(HERE, "frontier_%s.png" % tag)
    fig.savefig(png, dpi=150)
    print("plot written:", png)


if __name__ == "__main__":
    main()
