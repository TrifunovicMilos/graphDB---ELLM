"""Report on the tau variants: length, token statistics, leakage scan and samples to read by hand.

Usage (from the project folder; no model needed):
    python tau_experiments/tau_report.py               # dev set, all variants of variants.TAU_SPECS
    python tau_experiments/tau_report.py --set eval

Writes tau_experiments/tau_texts/report_<set>.md and texts_<set>_tau<variant>.txt (the same 20 Q1
positives in every variant, to read by hand).

Token counts use tiktoken's cl100k_base, as in the course data card (152 mean / 256 p90 for the
release tau of the dev games). Install it once with `pip install tiktoken`. Without it, the script
falls back to characters / 4 and says so.

Leakage scan. The hidden statements (genre P136, series P179, follows/followed by, franchise, has
parts) must never reach the model through a field WE add. For every entity it looks for the labels
of its hidden values in each part of tau:
  label, lead     legitimate evidence (the slides allow the lead to state the answer); counted only
  description     the field to check: any hit there is a LEAK
The same scan on the RAW description of graph.nt is printed as a control, to show what the
screening removes.
"""
import argparse
import csv
import os
import random
import re
import statistics
from collections import Counter, defaultdict

from common import HERE, ROOT
from semops import prompts
import variants

HIDDEN_FOR_TAU = {"P136": "genre", "P179": "series", "P155": "follows", "P156": "followed by",
                  "P8345": "franchise", "P527": "has part"}


def token_counter():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda text: len(enc.encode(text))), "cl100k_base"
    except Exception as e:                      # not installed, or no network to fetch the table
        print("WARNING: tiktoken cl100k_base unavailable (%s); using characters/4" % type(e).__name__)
        return (lambda text: round(len(text) / 4)), "approx. characters/4"


_UNCUT = {v: variants.make_tau_builder(dict(spec, max_chars=10 ** 9)) for v, spec in variants.TAU_SPECS.items()}


def full_length(variant, label, description, lead):
    """Length of the tau text before any cut (to count how many texts the budget shortens)."""
    return len(_UNCUT[variant](label, description, lead))


def p90(values):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(0.9 * len(values))) - 1)]


def contains(text, phrase):
    """Case-insensitive whole-word match of phrase in text."""
    return re.search(r"(?<!\w)" + re.escape(phrase.lower()) + r"(?!\w)", text.lower()) is not None


def load(data_dir):
    with open(os.path.join(data_dir, "entities.csv"), encoding="utf-8", newline="") as f:
        entities = list(csv.DictReader(f))
    hidden = defaultdict(list)
    with open(os.path.join(data_dir, "hidden_statements.csv"), encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["property"] in HIDDEN_FOR_TAU and row["value_label"]:
                hidden[row["qid"]].append((row["property"], row["value_label"]))
    positives = []
    gt = os.path.join(data_dir, "gt", "q1.csv")
    if os.path.isfile(gt):
        with open(gt, encoding="utf-8") as f:
            positives = [r["qid"] for r in csv.DictReader(f) if r["path"] == "1"]
    return entities, hidden, positives


def scan(entities, hidden, field):
    """Entities whose `field` names one of their hidden values -> {property: count}, examples."""
    hits, examples = Counter(), []
    for e in entities:
        text = e[field] if field != "label_lead" else e["label"] + " " + e["lead"]
        found = [(p, v) for p, v in hidden.get(e["qid"], []) if text and contains(text, v)]
        for p in {p for p, _ in found}:
            hits[p] += 1
        if found and len(examples) < 5:
            examples.append((e["label"], text[:90], found[0][1]))
    return hits, examples


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_name", choices=["dev", "eval"], default="dev")
    ap.add_argument("--data-root", default=os.path.join(ROOT, "data", "games"))
    ap.add_argument("--out", default=os.path.join(HERE, "tau_texts"))
    a = ap.parse_args()
    data_dir = os.path.join(a.data_root, a.set_name)
    entities, hidden, positives = load(data_dir)
    count, tokenizer = token_counter()
    os.makedirs(a.out, exist_ok=True)
    lines = ["# tau variants, %s set" % a.set_name, "",
             "Tokens: %s. Entities: %d (%s)." % (tokenizer, len(entities),
             ", ".join("%d %s" % (n, c) for c, n in Counter(e["class"] for e in entities).items())), "",
             "| tau | class | chars mean | tokens mean | tokens p90 | tokens max | text shortened |",
             "|---|---|---|---|---|---|---|"]

    by_qid = e_by = {e["qid"]: e for e in entities}
    for v in variants.TAU_TESTED:
        texts = {e["qid"]: prompts.tau(v, e["label"], e["description_screened"], e["lead"]) for e in entities}
        for cls in sorted({e["class"] for e in entities}):
            q = [e["qid"] for e in entities if e["class"] == cls]
            toks = [count(texts[x]) for x in q]
            chars = [len(texts[x]) for x in q]
            limit = variants.TAU_SPECS[v]["max_chars"]
            full = {x: full_length(v, e_by[x]["label"], e_by[x]["description_screened"], e_by[x]["lead"]) for x in q}
            cut = sum(1 for x in q if full[x] > limit)
            lines.append("| %s | %s | %.0f | %.1f | %d | %d | %.0f%% |" % (
                v, cls, statistics.mean(chars), statistics.mean(toks), p90(toks), max(toks), 100 * cut / len(q)))
        # samples to read by hand: 20 Q1 positives, same 20 for every variant
        rng = random.Random(42)
        sample = rng.sample(positives, min(20, len(positives))) if positives else []
        with open(os.path.join(a.out, "texts_%s_tau%s.txt" % (a.set_name, v)), "w", encoding="utf-8") as f:
            f.write("tau %s, %s set: 20 Q1 positives (seed 42). Check by hand that no field we ADD names\n"
                    "the hidden genre. Naming it in the label or the lead is legitimate evidence.\n\n" % (v, a.set_name))
            for x in sample:
                genres = ", ".join(val for p, val in hidden.get(x, []) if p == "P136")
                f.write("=" * 100 + "\n%s  (hidden genre: %s)\n\n%s\n\n" % (x, genres, texts[x]))

    lines += ["", "## Leakage scan", "",
              "Entities whose field names one of their own hidden values (genre, series, follows, followed by, "
              "franchise, has part).", "",
              "| field | used in tau | entities with a hit | by property |", "|---|---|---|---|"]
    for field, used, note in (("description_screened", "B, C, C-900, C-600", "the field we add"),
                              ("label_lead", "all", "legitimate evidence"),
                              ("description", "none", "control: the RAW description of graph.nt")):
        hits, examples = scan(entities, hidden, field)
        total = sum(1 for e in entities if any(contains(e[field] if field != "label_lead"
                    else e["label"] + " " + e["lead"], val) for _, val in hidden.get(e["qid"], [])))
        lines.append("| %s (%s) | %s | %d | %s |" % (field, note, used, total,
                     ", ".join("%s %d" % (HIDDEN_FOR_TAU[p], n) for p, n in hits.most_common()) or "-"))
        if field == "description_screened" and examples:
            lines += ["", "Examples (a hit is a leak only if a query asks about that value: see the next table):"] + ["- %s: %r names %r" % ex for ex in examples] + [""]

    # query-relevant check: does the screened description state the ANSWER of a common query in other
    # words (the course screening only catches the exact label)? Q1 platformer, Q2 visual novel, Q4 labels.
    lines += ["", "## Query answers stated in the screened description", "",
              "The course screening blanks a description that names the exact hidden label. This checks "
              "for the answer of Q1, Q2 and Q4 in other words.", "",
              "| query | inputs whose description_screened states the true answer | examples |", "|---|---|---|"]
    def gt_rows(name):
        path = os.path.join(data_dir, "gt", name + ".csv")
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    q4_words = {"action game": ["action game"], "adventure video game": ["adventure game", "adventure video game"],
                "role-playing video game": ["role-playing", "rpg"], "action-adventure game": ["action-adventure"],
                "puzzle video game": ["puzzle"], "racing video game": ["racing"],
                "first-person shooter": ["first-person shooter", "fps"], "shoot 'em up": ["shoot 'em up", "shmup"]}
    checks = (("Q1", [r["qid"] for r in gt_rows("q1") if r["path"] == "1"], lambda q: ["platform", "metroidvania"]),
              ("Q2", [r["qid"] for r in gt_rows("q2") if r["path"] == "1"], lambda q: ["visual novel"]),
              ("Q4", [r["qid"] for r in gt_rows("q4")],
               lambda q, names={r["qid"]: r["label_names"] for r in gt_rows("q4")}:
               [w for n in names[q].split("|") for w in q4_words.get(n.strip(), [])]))
    for name, inputs, words in checks:
        hit = [q for q in inputs if q in by_qid and any(contains(by_qid[q]["description_screened"], w) for w in words(q))]
        lines.append("| %s | %d of %d | %s |" % (name, len(hit), len(inputs),
                     "; ".join("%s: %s" % (by_qid[q]["label"], by_qid[q]["description_screened"]) for q in hit[:3]) or "-"))

    report = os.path.join(a.out, "report_%s.md" % a.set_name)
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwritten:", report, "and", len(variants.TAU_TESTED), "text files in", a.out)


if __name__ == "__main__":
    main()
