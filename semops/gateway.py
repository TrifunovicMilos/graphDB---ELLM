"""Client of the course LLM gateway (a local HTTP server, see the gateway README).

Why a gateway: it routes by public model name, validates the JSON answer, retries,
caches, and writes one log line per call. The official costs and the run files come from
that log. So every model call of the project must go through here.

Contract (docs/API.md of the gateway):
  POST /v1/responses   body: model, instructions, input, text.format (json_schema), metadata
                       answer: output[0].content[0].text = a JSON *string*, plus parse_ok
  parse_ok false = the model failed the schema: the value is a fallback, NOT a real decision.
  cache hits, tokens and cost are NOT in the body: only in the gateway log.
"""
import json
import time
import urllib.error
import urllib.request

from . import config


class GatewayError(RuntimeError):
    """The gateway answered with an error we cannot recover from (or is unreachable)."""


class Gateway:
    """One instance per run. `run_id` identifies the run in the gateway log."""

    def __init__(self, model, run_id, namespace=config.CACHE_NAMESPACE, url=config.GATEWAY_URL):
        self.model, self.run_id, self.namespace, self.url = model, run_id, namespace, url.rstrip("/")
        self.requests = 0          # HTTP requests sent (cache hits included)
        self.parse_failures = 0    # answers with parse_ok false
        self.seconds = 0.0         # time spent waiting for the gateway

    def _post(self, path, body):
        """POST a JSON body, retry a few times on 429/502 (rate limit, upstream hiccup)."""
        data = json.dumps(body).encode()
        for attempt in range(4):
            request = urllib.request.Request(self.url + path, data=data,
                                             headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=300) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:300]
                if e.code in (429, 502) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise GatewayError("gateway HTTP %d on %s: %s" % (e.code, path, detail))
            except urllib.error.URLError as e:
                raise GatewayError("gateway unreachable at %s (is `start server` running?): %s" % (self.url, e))

    def ask(self, instructions, text, schema_name, schema):
        """One structured request. Returns the parsed answer (a dict) or None if parse_ok is false.

        Example: ask(INSTR_FILTER, "Criterion: ...", "boolean_answer", BOOL_SCHEMA) -> {"answer": True}
        """
        return self.ask_response(instructions, text, schema_name, schema)[0]

    def ask_response(self, instructions, text, schema_name, schema):
        """Like ask(), but returns (parsed answer or None, the full gateway response).

        The full response holds the provider's raw answer (provider_response), e.g. the token
        log-probabilities that the cascade (semops/cascade.py) turns into a confidence score.
        The request is exactly the one ask() sends, so both share the gateway cache.
        """
        body = {"model": self.model, "temperature": 0, "instructions": instructions,
                "input": [{"role": "user", "content": text}],
                "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True,
                                    "schema": schema}},
                "metadata": {"run_id": self.run_id, "cache_namespace": self.namespace}}
        start = time.time()
        response = self._post("/v1/responses", body)
        self.seconds += time.time() - start
        self.requests += 1
        if response.get("parse_ok") is not True:
            self.parse_failures += 1
            print("   !! parse failure (parse_ok false):", response.get("error_type"))
            return None, response
        try:
            return json.loads(response["output"][0]["content"][0]["text"]), response
        except (KeyError, IndexError, ValueError):
            self.parse_failures += 1
            return None, response

    def embed(self, texts, model):
        """Embeddings of a list of texts, in input order (for blocking in joins)."""
        body = {"model": model, "input": list(texts),
                "metadata": {"run_id": self.run_id, "cache_namespace": self.namespace}}
        response = self._post("/v1/embeddings", body)
        self.requests += 1
        return [item["embedding"] for item in sorted(response["data"], key=lambda d: d["index"])]
