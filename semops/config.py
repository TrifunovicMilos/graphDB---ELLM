"""Fixed settings of the project. Change them here, nowhere else.

Environment variables override the defaults, so each teammate can keep a different
setup (for example another gateway log path) without editing the code.
"""
import os

# group id of the course, "g" + two digits (e.g. "g07"). TODO: replace with the real one.
GROUP_ID = os.environ.get("SEMOPS_GROUP_ID", "g00")
DOMAIN = "games"

# the local LLM gateway (see the gateway README). Start it with `start server`.
GATEWAY_URL = os.environ.get("SEMOPS_GATEWAY_URL", "http://127.0.0.1:8000")
# the gateway writes one JSON line per call here; run files are built from it
GATEWAY_LOG = os.environ.get("SEMOPS_GATEWAY_LOG", os.path.expanduser("~/llm-gateway/data/calls.jsonl"))
DEFAULT_MODEL = "local/qwen2.5:3b"      # public model name from the gateway's models.toml
CACHE_NAMESPACE = os.environ.get("SEMOPS_CACHE_NAMESPACE", "llme-v1")

EX = "http://example.org/semop/"        # prefix of our predicates (ex:)
WD = "http://www.wikidata.org/entity/"  # prefix of Wikidata entities

# kind of operator of each common query, and the file with its default query
QUERY_KIND = {"Q1": "filter", "Q2": "filter", "Q3": "filter", "Q4": "classify",
              "Q5": "extract", "Q6": "join", "Q8": "count"}
QUERY_FILES = {"Q1": "query/q1.rq", "Q2": "query/q2.rq", "Q3": "query/q3_naive.rq",
               "Q4": "query/q4.rq", "Q5": "query/q5.rq", "Q6": "query/q6.rq"}
# set of the data package that holds the inputs of each query (ex:inSet ex:set-<name>)
INPUT_SET = {"Q1": "main", "Q2": "main", "Q3": "main", "Q4": "q4_input", "Q5": "main", "Q8": "main"}

# the fixed criterion of each query (language expression). Q3 and Q8 use the one of Q1.
LANGEX = {"Q1": "the game is a platformer", "Q2": "the game is a visual novel",
          "Q3": "the game is a platformer", "Q4": "the genre that describes the game best",
          "Q5": "the company that developed the game", "Q6": "the game is part of the series",
          "Q8": "the game is a platformer"}

# the 8 labels of Q4: code -> English name
LABELS = {
    "Q270948":  "action game",
    "Q23916":   "adventure video game",
    "Q744038":  "role-playing video game",
    "Q343568":  "action-adventure game",
    "Q54767":   "puzzle video game",
    "Q860750":  "racing video game",
    "Q185029":  "first-person shooter",
    "Q1044478": "shoot 'em up",
}
NAME_TO_QID = {name.lower(): qid for qid, name in LABELS.items()}
