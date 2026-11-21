"""Evaluation against the official solutions (data/games/<set>/gt/*.csv).

Every function prints a short report. Called by pipelines.py right after a query has run,
only when the gt file exists.
"""
import csv, os
from collections import Counter

from .config import LABELS as Q4_LABELS, NAME_TO_QID


def normalize(text):
    """To compare labels: strip spaces and final dot, lowercase."""
    return text.strip().rstrip(".").lower()


# ---- filters (Q1-Q3) ----
# compares the model answers with the official solution
# run.py calls it only if you passed --gt <file>
# candidates  {qid: name} of all evaluated games
# predicted   {qid: name} of those for which the model said True
# if the true platformers are A, B, C and the model says A, B, D:
# correct = A, B | false positive = D | false negative = C
# precision = correct / found = 2/3,  recall = correct / true positives = 2/3
def evaluate(gt_file, candidates, predicted):
    with open(gt_file, encoding="utf-8") as f:
        # DictReader: each CSV row becomes a dictionary keyed by the header names
        # gt = {"Q170003": {"qid": "Q170003", "direct": "1", "path": "1"}, ...}
        gt = {row["qid"]: row for row in csv.DictReader(f)}
    for column in ("direct", "path"):          # the same comparison, twice
        correct, fp, fn = [], [], []
        for code in candidates:
            if code not in gt:
                print("WARNING: not in", gt_file, ":", code)
                continue
            truth = gt[code][column] == "1"
            says_yes = code in predicted
            if says_yes and truth:
                correct.append(code)
            elif says_yes and not truth:
                fp.append(code)
            elif truth:
                fn.append(code)
        found = len(correct) + len(fp)
        positives = len(correct) + len(fn)
        prec = len(correct) / found if found else 0.0
        rec = len(correct) / positives if positives else 0.0
        print(f"\ncomparison with '{column}': true positives {positives} | found {found} | correct {len(correct)}")
        print("  precision: %.2f   recall: %.2f" % (prec, rec))
        for c in fp:
            print("  false positive:", candidates[c])
        for c in fn:
            print("  false negative:", candidates[c])


# ---- classification (Q4) ----
# hit rate, accuracy and macro-F1 against gt/q4.csv
def evaluate_q4(gt_file, answers, game_names):
    # gt csv has columns qid,labels,label_names,k; `labels` may hold several codes separated by "|"
    truth = {}
    with open(gt_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["qid"] in answers:                 # only the games we evaluated
                truth[row["qid"]] = {x.rsplit("/", 1)[-1] for x in row["labels"].split("|")}
    # model label -> code (None if out of list or empty)
    pred = {e: NAME_TO_QID.get(normalize(answers[e])) for e in truth}
    n = len(truth)
    hit = sum(1 for e in truth if pred[e] in truth[e])
    single = {e: next(iter(ls)) for e, ls in truth.items() if len(ls) == 1}
    acc = sum(1 for e, l in single.items() if pred[e] == l)
    f1s = []
    print("\nQ4: label | true (single) | tp | fp | fn | F1")
    for l in sorted(set(single.values()) | {p for e, p in pred.items() if e in single and p}):
        tp = sum(1 for e, g in single.items() if g == l and pred[e] == l)
        fp = sum(1 for e, g in single.items() if g != l and pred[e] == l)
        fn = sum(1 for e, g in single.items() if g == l and pred[e] != l)
        f1 = 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
        f1s.append(f1)
        print(f"  {Q4_LABELS[l]} | {tp + fn} | {tp} | {fp} | {fn} | {f1:.2f}")
    out_of_list = sum(1 for e in truth if answers[e] and pred[e] is None)
    empty = sum(1 for e in truth if not answers[e])
    print(f"\n  games evaluated: {n} (with a single true label: {len(single)})")
    print("  hit rate: %.2f" % (hit / n if n else 0.0))
    print("  accuracy: %.2f" % (acc / len(single) if single else 0.0))
    print("  macro-F1: %.2f" % (sum(f1s) / len(f1s) if f1s else 0.0))
    print(f"  answers out of list: {out_of_list} | empty/broken answers: {empty}")



# ---- extraction (Q5): matching a string to an entity, then accuracy ----
def normalize_name(text):
    return " ".join(text.lower().split()).rstrip(".")

# reads labels.csv and aliases.csv and builds two dictionaries:
#   index = {normalized name: set of codes}   names = {code: label}
def load_index(folder):
    index, names = {}, {}
    for file, column in (("labels.csv", "label"), ("aliases.csv", "alias")):
        with open(os.path.join(folder, file), encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                index.setdefault(normalize_name(row[column]), set()).add(row["qid"])
                if column == "label":
                    names[row["qid"]] = row[column]
    return index, names

# tries to turn the model string into an entity code
# resolve("Nintendo", index) -> ("Q8093", "ok")
# status: "ok", "empty", "not found" or "ambiguous" (several entities with that name)
def resolve(string, index):
    if not string.strip():
        return None, "empty"
    candidates = index.get(normalize_name(string), set())
    if len(candidates) == 1:
        return next(iter(candidates)), "ok"
    return None, ("not found" if not candidates else "ambiguous")


# EVALUATION
def evaluate_q5(gt_file, answers, index, names):
    truth = {}
    with open(gt_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["qid"] in answers:
                truth[row["qid"]] = {x.rsplit("/", 1)[-1] for x in row["values"].split("|")}
    correct, reasons = 0, Counter()
    wrong, unresolved = [], []
    for e, vs in truth.items():
        s = answers[e]
        q, reason = resolve(s, index)
        reasons[reason] += 1
        if q is None:
            unresolved.append((e, s, reason))
        elif q in vs:
            correct += 1
        else:
            wrong.append((e, s, q))
    n = len(truth)
    print(f"\nQ5: games evaluated: {n} (without solution, not counted: {len(answers) - n})")
    print("  accuracy: %.2f" % (correct / n if n else 0.0))
    print("  unresolved: %.2f   (empty %d, not found %d, ambiguous %d)" %
          (len(unresolved) / n if n else 0.0, reasons["empty"], reasons["not found"], reasons["ambiguous"]))
    print("\n  examples of WRONG answers (game | model -> matched entity | truth):")
    for e, s, q in wrong[:8]:
        true_names = ", ".join(names.get(v, v) for v in truth[e])
        print(f"    {names.get(e, e)} | {s!r} -> {names.get(q, q)} | {true_names}")
    print("\n  examples of UNRESOLVED (game | model | reason | truth):")
    for e, s, reason in unresolved[:8]:
        true_names = ", ".join(names.get(v, v) for v in truth[e])
        print(f"    {names.get(e, e)} | {s!r} | {reason} | {true_names}")


# ---- join (Q6) ----
# reads gt/q6.csv (columns left,right) and returns the set of true pairs
def read_pairs(gt_file):
    with open(gt_file, encoding="utf-8") as f:
        return {(r["left"], r["right"]) for r in csv.DictReader(f)}

# precision, recall and F1 of the pairs accepted by the model, against gt/q6.csv
# only the true pairs among the candidates are counted (the others could not appear)
def evaluate_pairs(gt_file, candidates, predicted):
    true = {c for c in read_pairs(gt_file) if c in candidates}
    accepted = set(predicted)
    correct = accepted & true
    prec = len(correct) / len(accepted) if accepted else 0.0
    rec = len(correct) / len(true) if true else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    print(f"\nQ6: pairs evaluated {len(candidates)} | true pairs among them {len(true)} | "
          f"accepted by the model {len(accepted)} | correct {len(correct)}")
    print("  precision: %.2f   recall: %.2f   F1: %.2f" % (prec, rec, f1))
    print("\n  examples of FALSE POSITIVES (game ~ series):")
    for c in sorted(accepted - true)[:8]:
        print("    ", candidates[c][0], "~", candidates[c][1])
    print("\n  examples of FALSE NEGATIVES (game ~ series):")
    for c in sorted(true - accepted)[:8]:
        print("    ", candidates[c][0], "~", candidates[c][1])


# ---- count per decade (Q8) ----
# compares the per-decade counts with the solution (gt/q8.csv)
# run.py calls it right after count_per_decade
# metric: mean relative error over the decades where the true positives are > 0
# example: true 33, predicted 40 -> error |40 - 33| / 33 = 0.21
# decades with 0 true positives are not in the mean: we only print what the model predicted
def evaluate_q8(gt_file, counts):
    with open(gt_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    errors = []
    print("\nQ8: decade | true | predicted | relative error")
    for row in rows:
        decade = int(row["decade"])
        true = int(row["positives"])
        pred = counts.get(decade, 0)
        if true > 0:
            error = abs(pred - true) / true
            errors.append(error)
            print(f"  {decade}s | {true} | {pred} | {error:.2f}")
        else:
            print(f"  {decade}s | 0 | {pred} | (not in the mean)")
    if errors:
        print("  mean relative error: %.2f" % (sum(errors) / len(errors)))

