# Q6: sem_join ("which (game, series) pairs satisfy the criterion?")
# imports semops (tau, cache, counters).
# there are two sets: games on the left (50) and series on the right (100);
# for every (game, series) pair the model answers yes/no to "the game is part of the series"
import csv
import pyoxigraph as ox
import semops

EX = semops.EX

# PROMPT
INSTRUCTIONS_PAIR = ("You are a classifier. Decide whether the left item and the right item satisfy the "
                     "criterion. Answer only with JSON: {\"answer\": true} or {\"answer\": false}.")

def build_prompt_pair(criterion, tau_left, tau_right):
    return (INSTRUCTIONS_PAIR + "\n\nCriterion: " + criterion +
            "\n\nLeft: " + tau_left + "\n\nRight: " + tau_right)


# FAKE MODEL AND REAL MODEL

# fake LLM for pairs: true if the series name appears in the game text
def fake_llm_pair(prompt):
    semops.stats["calls"] += 1
    right = prompt.split("Right:")[1]
    left = prompt.split("Left:")[1].split("Right:")[0]
    series_name = right.split(". ")[0].strip().lower()
    return len(series_name) > 2 and series_name in left.lower()

# real model
def real_llm_pair(prompt):
    answer = semops._cached_answer(prompt, "answer", bool)
    return False if answer is None else answer


# sem_join
def make_join_functions(llm):
    # called by Oxigraph for every PAIR of rows, when it finds in the .rq
    #   FILTER( ex:sem_join(?llabel, ?llead, ?rlabel, ?rlead, "the criterion") )
    def sem_join(llabel, llead, rlabel, rlead, criterion):
        prompt = build_prompt_pair(criterion.value,
                                   semops.tau(llabel.value, llead.value),
                                   semops.tau(rlabel.value, rlead.value))
        ok = llm(prompt)
        s = semops.stats
        if ok:
            print(f"  [calls {s['calls']}, cache {s['cache']}] YES: {llabel.value}  ~  {rlabel.value}")
        elif (s["calls"] + s["cache"]) % 100 == 0:
            print(f"  ... {s['calls']} calls, {s['cache']} from cache")
        return semops._bool(ok)
    return {ox.NamedNode(EX + "sem_join"): sem_join}

# sem_join that always says true and costs nothing (to list all the pairs)
def always_true_join_functions():
    def sem_join(llabel, llead, rlabel, rlead, criterion):
        return semops._bool(True)
    return {ox.NamedNode(EX + "sem_join"): sem_join}


# CHOOSE THE PAIRS AND RUN THE QUERY

# reads gt/q6.csv (columns left,right) and returns the set of true pairs
def read_pairs(gt_file):
    with open(gt_file, encoding="utf-8") as f:
        return {(r["left"], r["right"]) for r in csv.DictReader(f)}

# codes of the entities in a set, sorted (e.g. set_name = 'q6_left')
def _set_members(store, set_name):
    q = f"PREFIX ex: <{EX}> SELECT ?x WHERE {{ ?x ex:inSet ex:set-{set_name} }}"
    return sorted(semops.qid(r["x"]) for r in store.query(q))

# chooses which games and which series to use for a reduced test (debug aid only)
# n = how many games (0 = all), m = how many series (0 = all)
# the series are: first the true ones of the chosen games (if --gt), then the others, up to m.
# WARNING: this makes the test easier than the real one; real runs use n = m = 0.
def pick_sample(store, n, m, true_pairs):
    all_left = _set_members(store, "q6_left")
    all_right = _set_members(store, "q6_right")
    left_list = all_left[:n] if n else None
    right_list = None
    if m:
        chosen_left = set(left_list if left_list else all_left)
        true_series = sorted({r for (l, r) in (true_pairs or set()) if l in chosen_left})
        right_list = true_series[:m]
        for r in all_right:
            if len(right_list) >= m:
                break
            if r not in right_list:
                right_list.append(r)
    return left_list, right_list

# builds 'VALUES ?l { wd:Q1 wd:Q2 }' (empty string if there is no restriction)
def _values_clause(variable, codes):
    if not codes:
        return ""
    return "VALUES ?" + variable + " { " + " ".join("wd:" + c for c in codes) + " }"

# runs q6.rq and returns {(game, series): (game_name, series_name)}
# the lines __VALUES_L__ and __VALUES_R__ of the .rq are replaced with the chosen lists
def run_pairs(store, query_file, functions, left_list, right_list):
    with open(query_file, encoding="utf-8") as f:
        q = f.read()
    q = q.replace("__VALUES_L__", _values_clause("l", left_list))
    q = q.replace("__VALUES_R__", _values_clause("r", right_list))
    return {(semops.qid(r["l"]), semops.qid(r["r"])): (r["llabel"].value, r["rlabel"].value)
            for r in store.query(q, custom_functions=functions)}


# EVALUATION

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
