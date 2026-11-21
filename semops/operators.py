"""The semantic operators, as functions that Oxigraph calls from inside a SPARQL query.

How it fits together:
  .rq query    FILTER( ex:sem_filter(?label, ?lead, "the game is a platformer") )
  Oxigraph     calls our Python function once per row (this is `custom_functions`)
  operators    builds tau, asks a *backend*, returns the answer to Oxigraph
  backend      decides: GatewayBackend (real model), FakeBackend or AlwaysTrueBackend (fake.py)

A backend has four methods: filter, classify, map, join. They return the decision, or
None when the answer was broken (parse failure): a broken answer is NOT a "no".
"""
import pyoxigraph as ox

from . import config, prompts

XSD_BOOL = ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean")


class Stats:
    """Counters of one run. `calls` = how many times Oxigraph called our function."""
    def __init__(self):
        self.calls = 0
        self.out_of_list = 0     # Q4 answers outside the 8 labels
        self.broken = 0          # answers the backend could not parse


class GatewayBackend:
    """Real model, through the gateway. `gateway` is a semops.gateway.Gateway."""

    def __init__(self, gateway):
        self.gw = gateway

    def filter(self, text, criterion):
        v = self.gw.ask(prompts.INSTR_FILTER, prompts.filter_text(criterion, text),
                        "boolean_answer", prompts.BOOL_SCHEMA)
        return None if v is None else v["answer"]

    def classify(self, text, criterion, labels):
        v = self.gw.ask(prompts.INSTR_CLASSIFY, prompts.classify_text(criterion, text, labels),
                        "genre_label", prompts.classify_schema(labels))
        return None if v is None else v["label"]

    def map(self, text, criterion):
        v = self.gw.ask(prompts.INSTR_MAP, prompts.map_text(criterion, text),
                        "extracted_value", prompts.MAP_SCHEMA)
        return None if v is None else v["value"]

    def join(self, text_left, text_right, criterion):
        v = self.gw.ask(prompts.INSTR_JOIN, prompts.join_text(criterion, text_left, text_right),
                        "boolean_answer", prompts.BOOL_SCHEMA)
        return None if v is None else v["answer"]


def _bool(value):
    """Python bool -> the SPARQL boolean that FILTER understands."""
    return ox.Literal("true" if value else "false", datatype=XSD_BOOL)


def make_functions(backend, stats, quiet=False):
    """Dictionary {function IRI: Python function} for `store.query(..., custom_functions=...)`.

    Called by engine.run_* with the backend chosen by run.py. `stats` is updated at every call.
    """
    labels = list(config.LABELS.values())

    def log(label, answer):
        if not quiet:
            print(f"  [call {stats.calls}] {label}: {answer!r}")

    def sem_filter(label, lead, criterion):
        stats.calls += 1
        ok = backend.filter(prompts.tau(label.value, lead.value), criterion.value)
        if ok is None:                     # broken answer: counted apart, treated as "no"
            stats.broken += 1
            ok = False
        log(label.value, ok)
        return _bool(ok)

    def sem_classify(label, lead, criterion):
        stats.calls += 1
        answer = backend.classify(prompts.tau(label.value, lead.value), criterion.value, labels)
        if answer is None:
            stats.broken += 1
            answer = ""
        elif answer.strip().rstrip(".").lower() not in config.NAME_TO_QID and answer != "":
            stats.out_of_list += 1
        log(label.value, answer)
        return ox.Literal(answer)

    def sem_map(label, lead, criterion):
        stats.calls += 1
        answer = backend.map(prompts.tau(label.value, lead.value), criterion.value)
        if answer is None:
            stats.broken += 1
            answer = ""
        log(label.value, answer)
        return ox.Literal(answer)

    def sem_join(llabel, llead, rlabel, rlead, criterion):
        stats.calls += 1
        ok = backend.join(prompts.tau(llabel.value, llead.value),
                          prompts.tau(rlabel.value, rlead.value), criterion.value)
        if ok is None:
            stats.broken += 1
            ok = False
        if ok and not quiet:
            print(f"  [call {stats.calls}] YES: {llabel.value}  ~  {rlabel.value}")
        elif stats.calls % 100 == 0 and not quiet:
            print(f"  ... {stats.calls} calls")
        return _bool(ok)

    return {ox.NamedNode(config.EX + "sem_filter"): sem_filter,
            ox.NamedNode(config.EX + "sem_classify"): sem_classify,
            ox.NamedNode(config.EX + "sem_map"): sem_map,
            ox.NamedNode(config.EX + "sem_join"): sem_join}
