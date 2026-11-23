"""Every tau and instruction variant that was tested, registered into semops so the experiments can be re-run.

semops itself holds only the frozen choice (prompts.PROMPT_VERSION: tau A; instructions F0, C0, M0, J5).
This file adds the other variants under their experiment ids:
  - run.py executes it when the environment variable SEMOPS_VARIANTS points to it (the experiment
    scripts set it for every run they start);
  - the experiment scripts import it.
The texts are exactly those that were run. Do not edit them: the results in results.csv and the
gateway cache belong to these exact texts. A new idea gets a new id.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from semops import prompts  # noqa: E402


# ---- tau ----
# description  add description_screened (never the raw description of graph.nt)
# max_chars    length budget in characters
# style        "plain"  = label. description. lead, cut at max_chars (the course release tau is B)
#              "fields" = Name: / Description: / Article:, whitespace collapsed, cut at a sentence end
TAU_SPECS = {
    "A":     {"description": False, "max_chars": 1200, "style": "plain"},    # frozen (prompts.tau_label_lead)
    "B":     {"description": True,  "max_chars": 1200, "style": "plain"},
    "C":     {"description": True,  "max_chars": 1200, "style": "fields"},
    "C-900": {"description": True,  "max_chars": 900,  "style": "fields"},
    "C-600": {"description": True,  "max_chars": 600,  "style": "fields"},
}
TAU_TESTED = list(TAU_SPECS)


def _join(*parts):
    """'Doom', '1993 video game', 'Doom is ...' -> 'Doom. 1993 video game. Doom is ...' (empty parts skipped)."""
    parts = [p.strip() for p in parts if p and p.strip()]
    head = [p.rstrip(".") + "." for p in parts[:-1]]
    return " ".join(head + parts[-1:])


def _cut_at_sentence(text, limit):
    """At most `limit` characters, ending at the last sentence end (or word end) that fits."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end > limit // 2:
        return cut[:end + 1]
    space = cut.rfind(" ")
    return cut[:space] if space > 0 else cut


def make_tau_builder(spec):
    """A builder (label, description, lead) -> text for one spec of TAU_SPECS."""
    def build(label, description, lead):
        description = description.strip() if spec["description"] and description else ""
        limit = spec["max_chars"]
        if spec["style"] == "plain":
            if not description:
                return (label + ". " + lead)[:limit]
            return _join(label, description, lead)[:limit]
        head = "Name: " + label + "\n"
        if description:
            head += "Description: " + description + "\n"
        head += "Article: "
        return head + _cut_at_sentence(" ".join(lead.split()), limit - len(head))
    return build


for _variant, _spec in TAU_SPECS.items():
    if _variant not in prompts.TAU_BUILDERS:          # A is already there: the frozen one
        prompts.TAU_BUILDERS[_variant] = make_tau_builder(_spec)


# ---- instructions (the text around "Criterion: <l>") ----
FILTER_TESTED = ["F0", "F1", "F2", "F3", "F4", "F5"]
JOIN_TESTED = ["J0", "J1", "J2", "J3", "J4", "J5"]
INSTRUCTION_NOTES = {
    "F0": "the original filter text (frozen)",
    "F1": "decide from the text and what the model knows about the item",
    "F2": "a more specific form of the category counts; judge the main nature, not a passing mention",
    "F3": "original + also satisfied when the text uses another name for it or combines it with other properties",
    "F4": "F3 shortened, without the JSON sentence",
    "F5": "only 'Decide whether the item satisfies the criterion.'",
    "J0": "the original join text",
    "J1": "strict: true only if the criterion holds for this pair; shared creator/publisher/genre/theme is not enough; most pairs are false",
    "J2": "J1 + two invented, domain-neutral examples",
    "J3": "J1 shortened, without the JSON sentence",
    "J4": "J1 + 'if neither text mentions the other item, answer false'",
    "J5": "J4 shortened (frozen)"
}

prompts.INSTRUCTIONS["filter"].update({
    'F1': 'You are a classifier. Decide whether the item satisfies the criterion, using the text and what you know about the item. Answer only with JSON: {"answer": true} or {"answer": false}.',
    'F2': 'You are a classifier. Decide whether the item satisfies the criterion. The criterion is satisfied if the item belongs to the named category or to a more specific form of it. Judge the item\'s main nature, not a passing mention. Answer only with JSON: {"answer": true} or {"answer": false}.',
    'F3': 'You are a classifier. Decide whether the item satisfies the criterion. It is also satisfied when the text uses another name for it or combines it with other properties. Answer only with JSON: {"answer": true} or {"answer": false}.',
    'F4': 'Decide whether the item satisfies the criterion. It is also satisfied when the text uses another name for it or combines it with other properties.',
    'F5': 'Decide whether the item satisfies the criterion.',
})
prompts.INSTRUCTIONS["join"].update({
    'J0': 'You are a classifier. Decide whether the left item and the right item satisfy the criterion. Answer only with JSON: {"answer": true} or {"answer": false}.',
    'J1': 'You are a classifier. Decide whether the left item and the right item satisfy the criterion. Answer true only if the criterion holds for this specific pair, as stated or clearly implied by the texts. Sharing a creator, publisher, genre, theme or naming pattern is not enough. Most pairs do not satisfy the criterion. Answer only with JSON: {"answer": true} or {"answer": false}.',
    'J2': 'You are a classifier. Decide whether the left item and the right item satisfy the criterion. Answer true only if the criterion holds for this specific pair, as stated or clearly implied by the texts. Sharing a creator, publisher, genre, theme or naming pattern is not enough. Most pairs do not satisfy the criterion. Two invented examples. Criterion: the book is part of the trilogy. Left: The Silent Harbor. The second novel of the Northlight trilogy by A. Rowe. Right: Northlight. A trilogy of novels by A. Rowe. Answer: true. Left: Winter Roads. A novel by A. Rowe, written after the Northlight trilogy. Right: Northlight. A trilogy of novels by A. Rowe. Answer: false. Answer only with JSON: {"answer": true} or {"answer": false}.',
    'J3': 'Decide whether the left and right items satisfy the criterion. True only if it holds for this pair as stated or clearly implied; shared creators, publishers, genres or themes are not enough. Most pairs are false.',
    'J4': 'You are a classifier. Decide whether the left item and the right item satisfy the criterion. Answer true only if the criterion holds for this specific pair, as stated or clearly implied by the texts. Sharing a creator, publisher, genre, theme or naming pattern is not enough. Most pairs do not satisfy the criterion. If neither text mentions the other item, answer false. Answer only with JSON: {"answer": true} or {"answer": false}.',
})
