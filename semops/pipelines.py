"""One function per query type. Each runs a query end to end and returns an Outcome.

Common flow (filter, classify, extract, join):
  1. load the graph
  2. list the candidates with the free AlwaysTrueBackend (which rows reach the model)
  3. run the real query with the chosen backend (fake or gateway)
  4. evaluate against gt/<query>.csv if it exists
  5. return the answer in SPARQL JSON form + numbers needed for the run file
Called by run.py, which then (optionally) writes the run file.
"""
import json
import os
import time

from . import config, engine, fake, metrics, operators, runfiles


class Outcome:
    """Result of one query run, with what run.py needs to write a run file."""
    def __init__(self, answer, n_input, sample, started, finished, labels=None, accepted=None):
        self.answer, self.n_input, self.sample = answer, n_input, sample
        self.started, self.finished, self.labels = started, finished, labels
        self.accepted = accepted          # set of accepted game codes (filters), for Q8


def _gt(opts, name):
    """The solution file: --gt if given, else data/games/<set>/gt/<name>.csv when it exists."""
    if getattr(opts, "gt", None):
        return opts.gt
    path = os.path.join(opts.data_dir, "gt", name + ".csv")
    return path if os.path.isfile(path) else None

def _timed(function):
    start = time.time()
    result = function()
    return result, start, time.time()

def _sample_codes(store, set_name, n):
    """The first n codes of a set, sorted like ORDER BY ?e in the queries."""
    return engine.set_members(store, set_name)[:n] if n else None


def run_filter(opts, store, backend, stats):
    """Q1-Q3: sem_filter on the games of the main set."""
    functions_real = operators.make_functions(backend, stats)
    candidates = engine.run_filter(store, opts.query_file, opts.n, operators.make_functions(
        fake.AlwaysTrueBackend(), operators.Stats(), quiet=True))
    print("candidate games:", len(candidates))
    accepted_map, t0, t1 = _timed(lambda: engine.run_filter(store, opts.query_file, opts.n, functions_real))
    operators.raise_if_failed(stats)
    operators.raise_if_failed(stats)
    print("\ngames accepted by the model:", len(accepted_map))
    gt = _gt(opts, opts.query_id.lower())
    if gt:
        metrics.evaluate(gt, candidates, accepted_map)
    members = engine.set_members(store, config.INPUT_SET[opts.query_id])
    sample = _sample_codes(store, config.INPUT_SET[opts.query_id], opts.n)
    return Outcome(runfiles.answer_filter(accepted_map), opts.n or len(members),
                   runfiles.sample_of(sample), t0, t1, accepted=set(accepted_map))


def run_classify(opts, store, backend, stats):
    """Q4: sem_classify, one label of the 8 for each game."""
    candidates = engine.run_values(store, opts.query_file, opts.n, operators.make_functions(
        fake.AlwaysTrueBackend(), operators.Stats(), quiet=True), "genre")
    print("games to classify:", len(candidates))
    answers, t0, t1 = _timed(lambda: engine.run_values(
        store, opts.query_file, opts.n, operators.make_functions(backend, stats), "genre"))
    operators.raise_if_failed(stats)
    operators.raise_if_failed(stats)
    gt = _gt(opts, "q4")
    if gt:
        metrics.evaluate_q4(gt, answers, candidates)
    members = engine.set_members(store, "q4_input")
    return Outcome(runfiles.answer_classify(answers), opts.n or len(members),
                   runfiles.sample_of(_sample_codes(store, "q4_input", opts.n)), t0, t1,
                   labels=list(config.LABELS.values()))


def run_extract(opts, store, backend, stats):
    """Q5: sem_map extracts a company name; we match it to an entity (labels.csv + aliases.csv)."""
    candidates = engine.run_values(store, opts.query_file, opts.n, operators.make_functions(
        fake.AlwaysTrueBackend(), operators.Stats(), quiet=True), "value")
    print("games to process:", len(candidates))
    answers, t0, t1 = _timed(lambda: engine.run_values(
        store, opts.query_file, opts.n, operators.make_functions(backend, stats), "value"))
    operators.raise_if_failed(stats)
    operators.raise_if_failed(stats)
    index, names = metrics.load_index(opts.data_dir)
    gt = _gt(opts, "q5")
    if gt:
        metrics.evaluate_q5(gt, answers, index, names)
    resolved = {e: metrics.resolve(text, index)[0] for e, text in answers.items()}
    members = engine.set_members(store, "main")
    return Outcome(runfiles.answer_extract(resolved), opts.n or len(members),
                   runfiles.sample_of(_sample_codes(store, "main", opts.n)), t0, t1)


def run_join(opts, store, backend, stats):
    """Q6: sem_join on every (game, series) pair (nested loop: one call per pair)."""
    gt = _gt(opts, "q6")
    true_pairs = metrics.read_pairs(gt) if gt else None
    left, right = engine.pick_sample(store, opts.n, opts.m, true_pairs)
    candidates = engine.run_pairs(store, opts.query_file, operators.make_functions(
        fake.AlwaysTrueBackend(), operators.Stats(), quiet=True), left, right)
    print("pairs to evaluate:", len(candidates))
    if opts.llm == "gateway" and len(candidates) > 100 and not opts.yes:
        if input("%d pairs = %d model calls. Continue? (y/n) " % (len(candidates), len(candidates))) != "y":
            raise SystemExit("cancelled")
    accepted, t0, t1 = _timed(lambda: engine.run_pairs(
        store, opts.query_file, operators.make_functions(backend, stats), left, right))
    operators.raise_if_failed(stats)
    operators.raise_if_failed(stats)
    print("\npairs accepted by the model:", len(accepted))
    if gt:
        metrics.evaluate_pairs(gt, candidates, accepted)
    all_left = engine.set_members(store, "q6_left")
    n_right = len(engine.set_members(store, "q6_right"))
    n_left = opts.n or len(all_left)
    return Outcome(runfiles.answer_join(accepted), n_left * n_right,
                   runfiles.sample_of(left), t0, t1)


def run_count(opts, store):
    """Q8: count per decade, reusing the decisions of an earlier Q1 run (no model calls).

    `opts.source_run` is the run_id of that Q1 run: its run file is read from runs/.
    """
    path = os.path.join(opts.repo_root, "runs", config.DOMAIN, opts.set_name, "Q1", opts.source_run + ".json")
    with open(path, encoding="utf-8") as f:
        source = json.load(f)
    accepted = {b["entity"]["value"].rsplit("/", 1)[-1] for b in source["answer"]["results"]["bindings"]}
    started = time.time()
    counts = engine.decade_counts(store, accepted)
    finished = time.time()
    gt = _gt(opts, "q8")
    if gt:
        metrics.evaluate_q8(gt, counts)
    n = len(engine.set_members(store, "main"))
    return Outcome(runfiles.answer_count(counts), n, None, started, finished)
