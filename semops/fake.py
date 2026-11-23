"""Free fake "models": simple rules, no gateway, no cost. Used to test the structure.

Same interface as the real backend (see operators.py): they receive the text(s) of tau
and the criterion, and answer directly. Their mistakes are rule artifacts, not model errors.
"""
import re

from . import prompts

class FakeBackend:
    def filter(self, text, criterion):
        word = "visual novel" if "visual novel" in criterion.lower() else "platform"
        return word in text.lower()

    def classify(self, text, criterion, labels):
        rules = [("first-person shooter", "first-person shooter"),
                 ("shoot 'em up", "shoot 'em up"), ("shmup", "shoot 'em up"),
                 ("role-playing", "role-playing video game"),
                 ("puzzle", "puzzle video game"), ("racing", "racing video game"),
                 ("action-adventure", "action-adventure game"),
                 ("adventure", "adventure video game"), ("action", "action game")]
        low = text.lower()
        for word, label in rules:      # ORDER matters: the first match wins
            if word in low:
                return label
        return "action game"

    def map(self, text, criterion):
        m = re.search(r"(?:developed|created|made) by ([A-Z0-9][\w&.'\-]*(?: [A-Z0-9][\w&.'\-]*)*)", text)
        return m.group(1).rstrip(".") if m else ""

    def join(self, text_left, text_right, criterion):
        series = prompts.tau_name(text_right).lower()        # tau starts with the series name
        return len(series) > 2 and series in text_left.lower()


class AlwaysTrueBackend:
    """Costs nothing: used to list which rows/pairs reach the semantic function (the candidates)."""
    def filter(self, text, criterion):
        return True
    def classify(self, text, criterion, labels):
        return ""
    def map(self, text, criterion):
        return ""
    def join(self, text_left, text_right, criterion):
        return True
