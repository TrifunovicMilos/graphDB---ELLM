# Q5: sem_map (extract a value from the text) and matching to an entity
# imports semops to reuse tau, the cache, the counters, etc.
# sem_map: for each game the model answers with free text,
# not with a choice among options (sem_classify) nor with yes/no (sem_filter);
# that text is then matched to a graph entity using labels.csv (names)
# and aliases.csv (other names), and we measure how many matches are correct

import csv, os, re
from collections import Counter
import pyoxigraph as ox
import semops

EX = semops.EX

# PROMPT

INSTRUCTIONS_MAP = ("You extract information from a text. Answer the criterion for the item with a short "
                    "value, using the name exactly as written in the text. If the text does not say, "
                    "use an empty string. Answer only with JSON: {\"value\": \"<string>\"}.")

def build_prompt_map(criterion, tau_text):
    return INSTRUCTIONS_MAP + "\n\nCriterion: " + criterion + "\n\nItem: " + tau_text


# FAKE MODEL AND REAL MODEL

# fake LLM for extraction: looks for "developed by X" in the text and returns X
# (its mistakes are regex artifacts, not model errors)
def fake_llm_value(prompt):
    semops.stats["calls"] += 1
    text = prompt.split("Item:")[1]
    m = re.search(r"(?:developed|created|made) by ([A-Z0-9][\w&.'\-]*(?: [A-Z0-9][\w&.'\-]*)*)", text)
    return m.group(1).rstrip(".") if m else ""

# real model for extraction: returns the string in the "value" field (or None if broken)
def real_llm_value(prompt):
    return semops._cached_answer(prompt, "value", str)


# sem_map
# called by Oxigraph for every row when it finds in the .rq
# BIND( ex:sem_map(?label, ?lead, "the company that developed the game") AS ?value )
def make_map_functions(llm):
    def sem_map(label, lead, criterion):
        answer = llm(build_prompt_map(criterion.value, semops.tau(label.value, lead.value)))
        if answer is None:
            answer = ""
        print(f"  [calls {semops.stats['calls']}, cache {semops.stats['cache']}] {label.value}: {answer!r}")
        return ox.Literal(answer)
    return {ox.NamedNode(EX + "sem_map"): sem_map}

# sem_map that returns an empty string and costs nothing (to see the candidates)
def empty_map_functions():
    def sem_map(label, lead, criterion):
        return ox.Literal("")
    return {ox.NamedNode(EX + "sem_map"): sem_map}

# runs q5.rq and returns {game_code: model_string}
def run_values(store, query_file, n, functions):
    q = semops._read_query(query_file, n)
    results = {}
    for r in store.query(q, custom_functions=functions):
        value = r["value"]
        results[semops.qid(r["e"])] = value.value if value is not None else ""
    return results


# MATCHING: from string to entity (labels.csv + aliases.csv)

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
