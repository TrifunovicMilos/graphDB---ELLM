# Project library, imported by run.py.
# From run.py the functions are called as semops.function_name(...)

# INDEX: data, tau and prompts, fake model, real model + cache,
#        sem_filter (Q1-Q3), sem_classify (Q4), run and evaluate, Q8
import csv, hashlib, json, os, time, urllib.request
import pyoxigraph as ox

# constants (used in this file)
URL        = "http://localhost:11434/v1/chat/completions"             # address of Ollama on the local machine
MODEL      = "qwen2.5:3b"                                             # model to use (also part of the cache key)
CACHE_FILE = "cache_llm.json"                                         # cache of the model answers
EX         = "http://example.org/semop/"                              # prefix of our predicates (ex:)
XSD_BOOL   = ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean") # boolean type for SPARQL

# the 8 Q4 genre labels: code -> English name
Q4_LABELS = {
    "Q270948":  "action game",
    "Q23916":   "adventure video game",
    "Q744038":  "role-playing video game",
    "Q343568":  "action-adventure game",
    "Q54767":   "puzzle video game",
    "Q860750":  "racing video game",
    "Q185029":  "first-person shooter",
    "Q1044478": "shoot 'em up",
}
# name (lowercase) -> code, to find which label the model answer corresponds to
NAME_TO_QID = {name.lower(): qid for qid, name in Q4_LABELS.items()}

# shared counters
stats = {"calls": 0, "cache": 0, "seconds": 0.0, "out_of_list": 0, "invalid": 0}

# called by run.py right before the real query
def reset_stats():
    stats.update(calls=0, cache=0, seconds=0.0, out_of_list=0, invalid=0)


# DATA

# reads an .nt file and loads it into an in-memory Oxigraph database
def load_graph(path):
    store = ox.Store()
    store.bulk_load(path=path, format=ox.RdfFormat.N_TRIPLES)
    return store


# TAU AND PROMPTS

INSTRUCTIONS = ("You are a classifier. Decide whether the item satisfies the criterion. "
                "Answer only with JSON: {\"answer\": true} or {\"answer\": false}.")

INSTRUCTIONS_CLASSIFY = ("You are a classifier. Choose the single label that best answers the criterion "
                         "for the item. Answer only with JSON: {\"label\": \"<one of the labels>\"}.")

# turns an entity (here: name + lead text) into a text (the model only sees text)
# tau("Doom", "Doom is a 1993 first-person shooter.") ->  "Doom. Doom is a 1993 first-person shooter."
# the [:1200] cuts the text to the first 1200 characters
def tau(label, lead):
    return (label + ". " + lead)[:1200]

# glues instructions + criterion + tau into the full message for the model
# called by sem_filter for every row
# prompt structure: instructions, 'Criterion: ...', tau
def build_prompt(criterion, tau_text):
    return INSTRUCTIONS + "\n\nCriterion: " + criterion + "\n\nItem: " + tau_text

# prompt for CLASSIFICATION: same as above plus the list of allowed labels
def build_prompt_classify(criterion, tau_text, names):
    return (INSTRUCTIONS_CLASSIFY + "\n\nCriterion: " + criterion +
            "\n\nLabels: " + ", ".join(names) + "\n\nItem: " + tau_text)


# FAKE MODEL (free)

# says True if a word chosen from the criterion appears in the text after 'Item:'
# used with run.py --llm fake
def fake_llm(prompt):
    stats["calls"] += 1
    criterion = prompt.split("Criterion:")[1].split("Item:")[0].lower()
    text = prompt.split("Item:")[1].lower()
    word = "visual novel" if "visual novel" in criterion else "platform"
    return word in text

# fake LLM for classification: picks a label from keywords in the text
# used with run.py --type classify --llm fake
# looks at the text after 'Item:'; the ORDER of the rules matters (first match wins)
# if nothing matches it answers "action game"
def fake_llm_label(prompt):
    stats["calls"] += 1
    text = prompt.split("Item:")[1].lower()
    rules = [("first-person shooter", "first-person shooter"),
             ("shoot 'em up", "shoot 'em up"), ("shmup", "shoot 'em up"),
             ("role-playing", "role-playing video game"),
             ("puzzle", "puzzle video game"), ("racing", "racing video game"),
             ("action-adventure", "action-adventure game"),
             ("adventure", "adventure video game"), ("action", "action game")]
    for word, label in rules:
        if word in text:
            return label
    return "action game"


# REAL MODEL (Ollama) AND CACHE

# the cache is read ONCE, when the module is imported
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

# sends a prompt to Ollama and returns the value of the field `field` (checked to be of type `kind`),
# or None if the answer is broken
# only called by _cached_answer, and only when the answer is NOT already in the cache
def call_model(prompt, field, kind):
    stats["calls"] += 1
    # request body, temperature 0 (same question -> same answer)
    body = {"model": MODEL, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}}
    # json.dumps = dictionary -> JSON string;  .encode() = string -> bytes
    request = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(request, timeout=300) as r:     # send and wait (max 300 s)
        response = json.loads(r.read())                         # bytes -> dictionary
    stats["seconds"] += time.time() - start
    # response has the form {"choices": [{"message": {"content": '{"answer": true}'}}], ...}
    text = response["choices"][0]["message"]["content"]         # string '{"answer": true}'
    try:
        value = json.loads(text)[field]                         # -> True
        if isinstance(value, kind):                             # a real True/False, not the string "false"
            return value
    except Exception:
        pass
    print("   !! invalid answer:", text)
    stats["invalid"] += 1
    return None             # None = "broken answer": NOT saved in the cache

# first looks in the cache; if the answer is not there, asks the model and saves it
def _cached_answer(prompt, field, kind):
    key = hashlib.sha256((MODEL + "\n" + prompt).encode()).hexdigest()
    if key in cache:
        stats["cache"] += 1
        return cache[key]
    answer = call_model(prompt, field, kind)
    if answer is None:
        return None
    cache[key] = answer
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    return answer

# called by sem_filter for every row, with --llm real
def real_llm(prompt):
    answer = _cached_answer(prompt, "answer", bool)
    return False if answer is None else answer

# called by sem_classify for every row, with --type classify --llm real
def real_llm_label(prompt):
    return _cached_answer(prompt, "label", str)


# sem_filter (Q1-Q3)

# turns Python true/false into the SPARQL boolean value, the only one FILTER understands
# _bool(True) -> "true"^^xsd:boolean
def _bool(value):
    return ox.Literal("true" if value else "false", datatype=XSD_BOOL)

# builds the dictionary for Oxigraph; `llm` is the function that decides (fake_llm or real_llm)
def make_functions(llm):
    def sem_filter(label, lead, criterion):
        ok = llm(build_prompt(criterion.value, tau(label.value, lead.value)))
        print(f"  [calls {stats['calls']}, cache {stats['cache']}] {label.value}: {ok}")
        return _bool(ok)     # hand the answer to FILTER

    # the dictionary tells Oxigraph: "when you see ex:sem_filter, call this function"
    return {ox.NamedNode(EX + "sem_filter"): sem_filter}

# sem_filter that always says true and costs nothing
# run.py uses it in the first pass to find which games reach the FILTER (the candidates) without calling any model
def always_true_functions():
    def sem_filter(label, lead, criterion):
        return _bool(True)
    return {ox.NamedNode(EX + "sem_filter"): sem_filter}


# sem_classify (Q4)

# to compare labels: strip spaces and final dot, lowercase
def normalize(text):
    return text.strip().rstrip(".").lower()

def make_classify_functions(llm):
    names = list(Q4_LABELS.values())
    def sem_classify(label, lead, criterion):
        prompt = build_prompt_classify(criterion.value, tau(label.value, lead.value), names)
        answer = llm(prompt)
        if answer is None:                           # broken answer (already counted in `invalid`)
            answer = ""
        elif normalize(answer) not in NAME_TO_QID:
            stats["out_of_list"] += 1
        print(f"  [calls {stats['calls']}, cache {stats['cache']}] {label.value}: {answer!r}")
        return ox.Literal(answer)
    return {ox.NamedNode(EX + "sem_classify"): sem_classify}

# sem_classify that returns an empty string and costs nothing (to see the candidates)
def empty_classify_functions():
    def sem_classify(label, lead, criterion):
        return ox.Literal("")
    return {ox.NamedNode(EX + "sem_classify"): sem_classify}


# RUN A QUERY AND EVALUATE

# from full address to short code
# called by the run_* functions for every result row
# qid(NamedNode("http://www.wikidata.org/entity/Q101243107")) -> "Q101243107"
# node.value = the address text;
# rsplit("/", 1) cuts it at the last "/" in two pieces; [-1] takes the last piece
def qid(node):
    return node.value.rsplit("/", 1)[-1]

# reads the .rq and replaces "LIMIT __N__" with "LIMIT 60" (if n=60) or removes it (n=0)
def _read_query(query_file, n):
    with open(query_file, encoding="utf-8") as f:
        q = f.read()
    return q.replace("LIMIT __N__", ("LIMIT " + str(n)) if n else "")

# runs a query and returns {game_code: name}
# run.py calls it first with always_true_functions (candidates), then with make_functions(llm)
# 1. reads the query text from the file
# 2. replaces "LIMIT __N__" with "LIMIT 60" (if n=60) or removes it (n=0)
# 3. store.query(...) runs the query
# 4. each row (binding) has ?e and ?label: row["e"] -> address, row["label"] -> name
def run_query(store, query_file, n, functions):
    q = _read_query(query_file, n)
    return {qid(r["e"]): r["label"].value
            for r in store.query(q, custom_functions=functions)}

# same for Q4: returns {game_code: label_answered_by_the_model}
def run_classify(store, query_file, n, functions):
    q = _read_query(query_file, n)
    results = {}
    for r in store.query(q, custom_functions=functions):
        genre = r["genre"]
        results[qid(r["e"])] = genre.value if genre is not None else ""
    return results

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


# Q8: COUNT PER DECADE (no new model calls)

# counts, per decade, the games the model accepted in Q1
# run.py calls it if you chose --q8 <file>, using the Q1 predictions
# Q8 makes no new calls, it reuses the decisions already taken
# a normal query takes the year (ex:firstYear) of every game in the main set;
# for the accepted ones it computes the decade
# example: year 1993 -> 1993 // 10 = 199 (integer division) -> 199 * 10 = 1990
# result, for instance: {1980: 31, 1990: 55, 2000: 48}
def count_per_decade(store, predicted):
    counts = {}
    q = ("PREFIX ex: <http://example.org/semop/> "
         "SELECT ?e ?y WHERE { ?e ex:inSet ex:set-main ; ex:firstYear ?y }")
    for r in store.query(q):
        if qid(r["e"]) in predicted:
            decade = (int(r["y"].value) // 10) * 10
            counts[decade] = counts.get(decade, 0) + 1
    return counts

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
