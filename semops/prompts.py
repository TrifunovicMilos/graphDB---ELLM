"""What the model sees: tau, instructions, answer schemas and prompt builders.

A request to the gateway has two text parts:
  instructions  fixed text per operator (INSTR_*)
  input         "Criterion: <fixed criterion>" + the item(s) as text (tau)
and a JSON schema that the answer must follow.
To change what the model sees, change tau(); to change how it is asked, change INSTR_*.
"""

# tau turns an entity (name + lead text) into the text the model sees.
# tau("Doom", "Doom is a 1993 first-person shooter.") -> "Doom. Doom is a 1993 first-person shooter."
# Cut at 1200 characters. Called by every operator, once per row (or per side of a pair).
def tau(label, lead):
    return (label + ". " + lead)[:1200]


INSTR_FILTER = ("You are a classifier. Decide whether the item satisfies the criterion. "
                "Answer only with JSON: {\"answer\": true} or {\"answer\": false}.")
INSTR_CLASSIFY = ("You are a classifier. Choose the single label that best answers the criterion "
                  "for the item. Answer only with JSON: {\"label\": \"<one of the labels>\"}.")
INSTR_MAP = ("You extract information from a text. Answer the criterion for the item with a short "
             "value, using the name exactly as written in the text. If the text does not say, "
             "use an empty string. Answer only with JSON: {\"value\": \"<string>\"}.")
INSTR_JOIN = ("You are a classifier. Decide whether the left item and the right item satisfy the "
              "criterion. Answer only with JSON: {\"answer\": true} or {\"answer\": false}.")

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
