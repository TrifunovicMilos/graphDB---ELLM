"""What the model sees: tau, instructions, answer schemas and prompt builders.

A request to the gateway has two text parts:
  instructions  fixed text per operator (INSTR_*)
  input         "Criterion: <fixed criterion>" + the item(s) as text (tau)
and a JSON schema that the answer must follow.
The texts are frozen (PROMPT_VERSION); see tau_experiments/ for how they were chosen.
"""

# Frozen prompt version: tau A + instructions F0 (filter), C0 (classify), M0 (map), J5 (join).
# Chosen on the development set with the 3B model; the experiments, their results and the reasons are
# in tau_experiments/README.md. Changing any of these texts changes every cached request and
# invalidates the cascade calibration: do it only with a new version.
PROMPT_VERSION = "v1"

from .config import TAU_MAX_CHARS


# ---- tau: the text of an entity ----
# Built ONCE per entity when the graph is loaded (engine.load_graph) and stored as the literal ex:tau;
# the .rq files pass ?tau to the operators. A builder gets (label, description, lead) from entities.csv;
# the description is description_screened, never the raw one of graph.nt (it can name the hidden genre).

def tau_label_lead(label, description, lead):
    """Variant A (frozen): label. lead, cut at TAU_MAX_CHARS characters. The description is not used.

    tau_label_lead("Doom", "1993 video game", "Doom is a 1993 first-person shooter.")
      -> "Doom. Doom is a 1993 first-person shooter."
    """
    return (label + ". " + lead)[:TAU_MAX_CHARS]


# variant id -> builder. tau_experiments/variants.py registers the variants that were tested.
TAU_BUILDERS = {"A": tau_label_lead}


def tau(variant, label, description, lead):
    """The text of one entity for a tau variant (config.DEFAULT_TAU = the frozen one)."""
    return TAU_BUILDERS[variant](label, description, lead)


def tau_name(text):
    """The entity name at the start of a tau text (for printing, and for the fake join)."""
    if text.startswith("Name: "):                  # the "fields" variants of the experiments
        return text[6:].split("\n", 1)[0].strip()
    return text.split(". ")[0].strip()


# ---- instructions: the text around "Criterion: <l>" (l is fixed by the course and goes in verbatim) ----
# One general text per operator: no domain words and no examples from the data, because the pool runs
# the same prompts on films and on other groups' queries.
INSTR_FILTER = ("You are a classifier. Decide whether the item satisfies the criterion. "
                "Answer only with JSON: {\"answer\": true} or {\"answer\": false}.")
INSTR_CLASSIFY = ("You are a classifier. Choose the single label that best answers the criterion "
                  "for the item. Answer only with JSON: {\"label\": \"<one of the labels>\"}.")
INSTR_MAP = ("You extract information from a text. Answer the criterion for the item with a short "
             "value, using the name exactly as written in the text. If the text does not say, "
             "use an empty string. Answer only with JSON: {\"value\": \"<string>\"}.")
INSTR_JOIN = 'Decide whether the left and right items satisfy the criterion. True only if it holds for this pair as stated or clearly implied; shared creators, publishers, genres or themes are not enough. If neither text mentions the other item, answer false. Most pairs are false.'

# id -> text per operator. The ids are those of the experiments (F0 = the original filter text,
# J5 = the fifth join variant); tau_experiments/variants.py registers the other tested texts.
INSTRUCTIONS = {
    "filter": {"F0": INSTR_FILTER},
    "classify": {"C0": INSTR_CLASSIFY},
    "map": {"M0": INSTR_MAP},
    "join": {"J5": INSTR_JOIN},
}
INSTR_DEFAULT = {"filter": "F0", "classify": "C0", "map": "M0", "join": "J5"}


def instruction_ids():
    """{"F0": "filter", "J5": "join", ...} for every registered instruction."""
    return {i: op for op, variants in INSTRUCTIONS.items() for i in variants}


# JSON schemas of the answers (the gateway validates every answer against them)
BOOL_SCHEMA = {"type": "object", "properties": {"answer": {"type": "boolean"}},
               "required": ["answer"], "additionalProperties": False}
MAP_SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}},
              "required": ["value"], "additionalProperties": False}

def classify_schema(labels):
    """The label must be one of `labels` (an enum): the model cannot invent others."""
    return {"type": "object",
            "properties": {"label": {"type": "string", "enum": list(labels)}},
            "required": ["label"], "additionalProperties": False}


def filter_text(criterion, tau_text):
    return "Criterion: " + criterion + "\n\nItem: " + tau_text

def classify_text(criterion, tau_text, labels):
    return "Criterion: " + criterion + "\n\nLabels: " + ", ".join(labels) + "\n\nItem: " + tau_text

def map_text(criterion, tau_text):
    return "Criterion: " + criterion + "\n\nItem: " + tau_text

def join_text(criterion, tau_left, tau_right):
    return "Criterion: " + criterion + "\n\nLeft: " + tau_left + "\n\nRight: " + tau_right
