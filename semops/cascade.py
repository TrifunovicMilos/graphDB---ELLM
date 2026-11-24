"""O1, the model cascade: a cheap proxy answers when it is sure, the oracle when it is not.

Score. The proxy's log-odds that the answer is true, read from the token log-probabilities in the
gateway response (provider_response, OpenAI-compatible format as Ollama serves it; the local route
requests the top 5). At the token that carries the boolean, the probabilities of every spelling of
"true" (" true", "True", ...) and of "false" in the top list are summed:
    score = ln P(true) - ln P(false)        > 0: the proxy leans to yes, < 0: to no
When one side is not in the top list, its probability is at most the smallest listed one; that
value is used, so the score is then a bound (|score| is at least that large), not an exact value.

Decision for one binding:
    score <= theta_low   -> false (the proxy decides)
    score >= theta_high  -> true  (the proxy decides)
    otherwise            -> the oracle decides, with exactly the request of the reference plan,
                            so on a set with a reference run every oracle call is a cache hit
A proxy answer without a score (parse failure) also goes to the oracle.
The thresholds are learned on the development set (o1_cascade/calibrate.py), never on eval.
"""
import math

from . import prompts

SCORE_METHOD = "log-odds of true vs false from the proxy's top-5 token log-probabilities"


def _logsumexp(values):
    top = max(values)
    return top + math.log(sum(math.exp(v - top) for v in values))


def proxy_score(response):
    """(score, exact) from a gateway response of the proxy, or (None, False) when there is none."""
    try:
        tokens = response["provider_response"]["choices"][0]["logprobs"]["content"]
    except (KeyError, IndexError, TypeError):
        return None, False
    for token in tokens or []:
        if token["token"].strip().lower() not in ("true", "false"):
            continue
        alternatives = token.get("top_logprobs") or [{"token": token["token"], "logprob": token["logprob"]}]
        lp = {"true": [], "false": []}
        for alt in alternatives:
            word = alt["token"].strip().lower()
            if word in lp:
                lp[word].append(alt["logprob"])
        floor = min(alt["logprob"] for alt in alternatives)
        exact = bool(lp["true"]) and bool(lp["false"])
        lt = _logsumexp(lp["true"]) if lp["true"] else floor
        lf = _logsumexp(lp["false"]) if lp["false"] else floor
        return lt - lf, exact
    return None, False


def decide(score, theta_low, theta_high):
    """True / False when the proxy decides, None when the oracle must."""
    if score is None:
        return None
    if score <= theta_low:
        return False
    if score >= theta_high:
        return True
    return None


class CascadeBackend:
    """Backend for the filter operator (see operators.py): proxy first, oracle when unsure.

    `proxy` and `oracle` are semops.gateway.Gateway instances with the same run id and cache
    namespace; `instructions` is the filter instruction text (the frozen one, prompts.INSTR_FILTER).
    """

    def __init__(self, proxy, oracle, theta_low, theta_high, instructions):
        if theta_low > theta_high:
            raise ValueError("theta_low must not be above theta_high")
        self.proxy, self.oracle = proxy, oracle
        self.theta_low, self.theta_high, self.instructions = theta_low, theta_high, instructions
        self.by_proxy = self.by_oracle = self.unscored = 0

    def filter(self, text, criterion):
        prompt = prompts.filter_text(criterion, text)
        _, response = self.proxy.ask_response(self.instructions, prompt, "boolean_answer", prompts.BOOL_SCHEMA)
        score, _ = proxy_score(response)
        decision = decide(score, self.theta_low, self.theta_high)
        if decision is not None:
            self.by_proxy += 1
            return decision
        self.unscored += score is None
        self.by_oracle += 1
        v = self.oracle.ask(self.instructions, prompt, "boolean_answer", prompts.BOOL_SCHEMA)
        return None if v is None else v["answer"]

    def _not_a_filter(self, *args):
        raise NotImplementedError("the O1 cascade is implemented for the filter operator (Q1, Q2, Q3) only")

    classify = map = join = _not_a_filter
