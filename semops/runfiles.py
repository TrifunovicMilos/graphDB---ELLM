"""Official run files (format semops-run/1): one JSON file per execution of one query.

The format and its validation live in the course checker `semops_check.py`, which must stay
OUTSIDE this repository. Point the environment variable SEMOPS_CHECKER_PATH to it:
    export SEMOPS_CHECKER_PATH=/absolute/path/to/semops_check.py
We use two of its documented library functions:
    calls_from_log(log_path, run_id)  -> the calls of the run, read from the gateway log
    write_run_file(repo_root, doc)    -> validates the document and writes
                                         runs/<domain>/<set>/<query>/<run_id>.json
(The gateway wrapper `runs build` is not used: the checker file we have does not implement it.)
"""
import importlib
import json
import os
import sys
from datetime import datetime, timezone

import pyoxigraph as ox

from . import config

XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"


def load_checker():
    """Imports semops_check.py from SEMOPS_CHECKER_PATH."""
    path = os.environ.get("SEMOPS_CHECKER_PATH")
    if not path or not os.path.isfile(path):
        raise RuntimeError("set SEMOPS_CHECKER_PATH to the absolute path of semops_check.py "
                           "(outside this repository)")
    folder = os.path.dirname(os.path.abspath(path))
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return importlib.import_module(os.path.splitext(os.path.basename(path))[0])


def utc(timestamp):
    """Unix seconds -> '2026-12-15T10:00:00Z'."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- the answer, in SPARQL 1.1 Query Results JSON ----

def _uri(code):
    return {"type": "uri", "value": config.WD + code}

def _literal(text, datatype=None):
    term = {"type": "literal", "value": str(text)}
    if datatype:
        term["datatype"] = datatype
    return term

def _result_set(variables, rows):
    return {"head": {"vars": variables}, "results": {"bindings": rows}}

def answer_filter(accepted):
    """Q1-Q3: the accepted games. accepted = iterable of codes."""
    return _result_set(["entity"], [{"entity": _uri(e)} for e in sorted(accepted)])

def answer_classify(labels_by_game):
    """Q4: {game: label text}. An empty label stays unbound."""
    rows = []
    for e in sorted(labels_by_game):
        row = {"entity": _uri(e)}
        if labels_by_game[e]:
            row["label"] = _literal(labels_by_game[e])
        rows.append(row)
    return _result_set(["entity", "label"], rows)

def answer_extract(resolved_by_game):
    """Q5: {game: entity code or None}. Unresolved answers stay unbound."""
    rows = []
    for e in sorted(resolved_by_game):
        row = {"entity": _uri(e)}
        if resolved_by_game[e]:
            row["value"] = _uri(resolved_by_game[e])
        rows.append(row)
    return _result_set(["entity", "value"], rows)

def answer_join(pairs):
    """Q6: the accepted (game, series) pairs."""
    return _result_set(["left", "right"], [{"left": _uri(l), "right": _uri(r)} for l, r in sorted(pairs)])

def answer_count(counts):
    """Q8: {decade: count}."""
    rows = [{"group": _literal(d), "count": _literal(c, XSD_INTEGER)} for d, c in sorted(counts.items())]
    return _result_set(["group", "count"], rows)


# ---- the run file ----

def sample_of(codes):
    """The `sample` object of a run on the first N inputs only (None for a full run)."""
    return {"method": "first-n-sorted-iri", "inputs": list(codes)} if codes else None


def load_prices(path):
    """Our own price list (JSON): {"id", "currency", "models": {model: {input_per_million, output_per_million}}}.
    Every model used in a run must be there, even with price 0, or the checker rejects the run."""
    if not os.path.isfile(path):
        raise RuntimeError("price list not found: %s (see prices.json in the repository)" % path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_run(repo_root, *, query_id, data_set, run_id, plan_id, model, answer, n_input,
              sample, started, finished, wallclock, prices_path, plan_params=None,
              reference_run_id=None, source_run_id=None, labels=None, model_proxy=None):
    """Builds the run document, validates it with the checker and writes it. Returns the path.

    `started`/`finished` are Unix seconds, `wallclock` is seconds, `n_input` is the size of the
    input set (for a join: left x right). With `source_run_id` the run reuses the decisions of
    another run (Q8) and has no calls of its own.
    """
    checker = load_checker()
    calls = [] if source_run_id else checker.calls_from_log(config.GATEWAY_LOG, run_id)
    doc = {
        "format": "semops-run/1",
        "run": {
            "group_id": config.GROUP_ID, "domain": config.DOMAIN, "data_set": data_set,
            "query_set": "common", "query_id": query_id, "run_id": run_id, "plan_id": plan_id,
            "plan_params": plan_params or {}, "reference_run_id": reference_run_id,
            "source_run_id": source_run_id, "engine": "oxigraph-" + ox.__version__,
            "model_oracle": model, "model_proxy": model_proxy,
            "language_expression": config.LANGEX[query_id], "labels": labels,
            "n_input_bindings": n_input, "sample": sample, "pool_mode": None, "shipped": False,
            "started_at": utc(started), "finished_at": utc(finished), "wallclock_s": round(wallclock, 3),
        },
        "answer": answer,
        "candidates": None,
        "oracle_check": None,
        "calls": calls,
        "price_list": load_prices(prices_path),
    }
    return checker.write_run_file(repo_root, doc)
