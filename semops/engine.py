"""Loading the graph and running the .rq queries.

Every entity carries its text as ex:tau (built in load_graph); the queries pass ?tau to the
semantic functions.

Placeholders inside the .rq files (replaced here before the query runs):
  LIMIT __N__                 first N inputs (removed when N = 0)
  __VALUES_L__ __VALUES_R__   restrict the two sides of the join (Q6)
"""
import csv
import os

import pyoxigraph as ox

from . import config, prompts


def load_graph(path, tau_variant=config.DEFAULT_TAU):
    """Reads an .nt file into an in-memory Oxigraph store and adds one ex:tau literal per entity.

    tau is built from entities.csv next to the .nt file (label, description_screened, lead), never
    from the raw schema:description of graph.nt, which can name the hidden genre.
    """
    store = ox.Store()
    store.bulk_load(path=path, format=ox.RdfFormat.N_TRIPLES)
    tau_pred = ox.NamedNode(config.EX + "tau")
    quads = []
    with open(os.path.join(os.path.dirname(path), "entities.csv"), encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            text = prompts.tau(tau_variant, row["label"], row["description_screened"], row["lead"])
            quads.append(ox.Quad(ox.NamedNode(config.WD + row["qid"]), tau_pred, ox.Literal(text)))
    store.bulk_extend(quads)
    return store

def qid(node):
    """Full address -> short code: <http://www.wikidata.org/entity/Q42> -> 'Q42'."""
    return node.value.rsplit("/", 1)[-1]

def set_members(store, set_name):
    """Sorted codes of the entities of a set (ex:inSet ex:set-<set_name>)."""
    q = f"PREFIX ex: <{config.EX}> SELECT ?x WHERE {{ ?x ex:inSet ex:set-{set_name} }}"
    return sorted(qid(r["x"]) for r in store.query(q))

def read_query(query_file, n):
    with open(query_file, encoding="utf-8") as f:
        q = f.read()
    return q.replace("LIMIT __N__", ("LIMIT " + str(n)) if n else "")


def run_filter(store, query_file, n, functions):
    """{game code: name} of the rows the query returns (Q1-Q3)."""
    q = read_query(query_file, n)
    return {qid(r["e"]): r["label"].value for r in store.query(q, custom_functions=functions)}

def run_values(store, query_file, n, functions, variable):
    """{game code: text} for queries that BIND a value: variable 'genre' (Q4) or 'value' (Q5)."""
    q = read_query(query_file, n)
    out = {}
    for r in store.query(q, custom_functions=functions):
        v = r[variable]
        out[qid(r["e"])] = v.value if v is not None else ""
    return out


def pick_sample(store, n, m, true_pairs):
    """Join tests: which games (left) and series (right) to use. DEBUG AID ONLY.

    n = first n games by code (0 = all); m = m series (0 = all): the true series of the chosen
    games first (when `true_pairs` is known), then the others. Easier than the real task.
    Returns (left_list, right_list), None = no restriction.
    """
    all_left, all_right = set_members(store, "q6_left"), set_members(store, "q6_right")
    left = all_left[:n] if n else None
    right = None
    if m:
        chosen = set(left if left else all_left)
        right = sorted({r for (l, r) in (true_pairs or set()) if l in chosen})[:m]
        for r in all_right:
            if len(right) >= m:
                break
            if r not in right:
                right.append(r)
    return left, right

def _values_clause(variable, codes):
    if not codes:
        return ""
    return "VALUES ?" + variable + " { " + " ".join("wd:" + c for c in codes) + " }"

def run_pairs(store, query_file, functions, left, right):
    """{(game, series): (game name, series name)} of the pairs the join returns (Q6)."""
    with open(query_file, encoding="utf-8") as f:
        q = f.read()
    q = q.replace("__VALUES_L__", _values_clause("l", left)).replace("__VALUES_R__", _values_clause("r", right))
    return {(qid(r["l"]), qid(r["r"])): (r["llabel"].value, r["rlabel"].value)
            for r in store.query(q, custom_functions=functions)}


def decade_counts(store, accepted):
    """Q8: games accepted by Q1, counted per decade of ex:firstYear. {1990: 55, ...}"""
    counts = {}
    q = (f"PREFIX ex: <{config.EX}> "
         "SELECT ?e ?y WHERE { ?e ex:inSet ex:set-main ; ex:firstYear ?y }")
    for r in store.query(q):
        if qid(r["e"]) in accepted:
            decade = (int(r["y"].value) // 10) * 10
            counts[decade] = counts.get(decade, 0) + 1
    return counts
