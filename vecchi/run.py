# The program you launch. Examples:
#   python run.py query/q1.rq --n 60 --llm real --gt data/games/dev/gt/q1.csv
#   python run.py query/q4.rq --type classify --n 30 --gt data/games/dev/gt/q4.csv
#   python run.py query/q5.rq --type extract --n 30 --gt data/games/dev/gt/q5.csv
#   python run.py query/q6.rq --type join --gt data/games/dev/gt/q6.csv
import argparse, os
import semops       # filters, classification, cache, counters, evaluations (Q1-Q4, Q8)
import extraction   # Q5
import joining      # Q6

# argparse reads the words written after "python run.py" and puts them in `a`
p = argparse.ArgumentParser()
p.add_argument("query", help="query file, e.g. query/q1.rq")                      # required
p.add_argument("--type", choices=["filter", "classify", "extract", "join"], default="filter",
               help="filter = Q1-Q3, classify = Q4, extract = Q5, join = Q6")
p.add_argument("--n", type=int, default=0, help="how many games (0 = all)")
p.add_argument("--m", type=int, default=0, help="only for --type join: how many series on the right (0 = all)")
p.add_argument("--llm", choices=["fake", "real"], default="fake")
p.add_argument("--data", default="data/games/dev", help="data folder")
p.add_argument("--gt", default=None, help="solution file, e.g. data/games/dev/gt/q1.csv")
p.add_argument("--q8", default=None, help="gt/q8.csv file: also computes the count per decade (Q8)")
a = p.parse_args()

# safety brake: with the real model, many rows take hours
if a.llm == "real" and a.type != "join" and (a.n == 0 or a.n > 100):
    if input("Many calls (about 15 s each without cache). Continue? (y/n) ") != "y":
        raise SystemExit("cancelled")

# load the graph
store = semops.load_graph(os.path.join(a.data, "graph.nt"))
print("triples loaded:", len(store))

if a.type == "filter":
    # candidates = the games that reach the FILTER (with the "always true" function: zero cost)
    candidates = semops.run_query(store, a.query, a.n, semops.always_true_functions())
    print("candidate games:", len(candidates))

    # the real query; `llm` is a FUNCTION (no parentheses: we do not call it now)
    llm = semops.fake_llm if a.llm == "fake" else semops.real_llm
    semops.reset_stats()
    predicted = semops.run_query(store, a.query, a.n, semops.make_functions(llm))
    print("\ngames accepted by the model:", len(predicted))

    # comparison with the official solution
    if a.gt:
        semops.evaluate(a.gt, candidates, predicted)

    # Q8 = count per decade of the Q1 decisions (no new calls)
    if a.q8:
        if a.n:
            print("WARNING: Q8 only makes sense on ALL games (--n 0); with --n the comparison is partial.")
        semops.evaluate_q8(a.q8, semops.count_per_decade(store, predicted))

elif a.type == "classify":
    # classification (Q4): each game gets one label
    candidates = semops.run_classify(store, a.query, a.n, semops.empty_classify_functions())
    print("games to classify:", len(candidates))

    llm = semops.fake_llm_label if a.llm == "fake" else semops.real_llm_label
    semops.reset_stats()
    answers = semops.run_classify(store, a.query, a.n, semops.make_classify_functions(llm))

    if a.gt:
        semops.evaluate_q4(a.gt, answers, candidates)

elif a.type == "extract":
    # extraction (Q5): each game gets a free text, then we match it to an entity
    candidates = extraction.run_values(store, a.query, a.n, extraction.empty_map_functions())
    print("games to process:", len(candidates))

    llm = extraction.fake_llm_value if a.llm == "fake" else extraction.real_llm_value
    semops.reset_stats()
    answers = extraction.run_values(store, a.query, a.n, extraction.make_map_functions(llm))

    if a.gt:
        index, names = extraction.load_index(a.data)     # labels.csv + aliases.csv
        extraction.evaluate_q5(a.gt, answers, index, names)

else:
    # join (Q6): each (game, series) pair gets a yes/no
    true_pairs = joining.read_pairs(a.gt) if a.gt else None
    left_list, right_list = joining.pick_sample(store, a.n, a.m, true_pairs)
    candidates = joining.run_pairs(store, a.query, joining.always_true_join_functions(), left_list, right_list)
    print("pairs to evaluate:", len(candidates))

    # safety brake: one real-model call per pair
    if a.llm == "real" and len(candidates) > 100:
        if input("%d pairs = %d calls (about 15 s each without cache). Continue? (y/n) " % (len(candidates), len(candidates))) != "y":
            raise SystemExit("cancelled")

    llm = joining.fake_llm_pair if a.llm == "fake" else joining.real_llm_pair
    semops.reset_stats()
    predicted = joining.run_pairs(store, a.query, joining.make_join_functions(llm), left_list, right_list)
    print("\npairs accepted by the model:", len(predicted))

    if a.gt:
        joining.evaluate_pairs(a.gt, candidates, predicted)

s = semops.stats
print(f"\nreal calls: {s['calls']}, from cache: {s['cache']}, LLM time: {s['seconds']:.0f}s")
print(f"invalid answers: {s['invalid']}, out of list: {s['out_of_list']}")
