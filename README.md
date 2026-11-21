# Semantic operators on graphs: *games* domain (Oxigraph)

Team project for the course *Graph Databases* 2026/2027. Group: **LLME**.
Domain: video games with series. Engine: **Oxigraph** (`pyoxigraph`). Every model call goes through the course **LLM gateway**.

## Overview

SPARQL queries run on a video-game graph and, inside the query, a language model decides on each row. Four operators:

| Operator | What it does | Queries |
|---|---|---|
| `sem_filter` | yes/no on a row | Q1, Q2, Q3 |
| `sem_classify` | one label out of 8 | Q4 |
| `sem_map` | extracts free text, matched to an entity | Q5 |
| `sem_join` | yes/no on a (game, series) pair | Q6 (Q7 optional) |

Q8 counts, per decade, the games accepted by Q1, with no new model calls.
Everything is measured: quality against the official solutions, cost in model calls and tokens (from the gateway log).

## Status

| Query | Status |
|---|---|
| Q1, Q2 filters | done |
| Q3 restriction + filter | done, 3 plans (`q3_naive`, `q3_struttura_prima`, `q3_semantica_prima`) |
| Q4 classification | done (the 8 labels are an enum of the answer schema) |
| Q5 extraction | done, simple matching |
| Q6 join 50 x 100 | done, nested loop (5,000 pairs) |
| Q7 large join (optional) | missing (blocking with embeddings) |
| Q8 count per decade | done, reuses a Q1 run |
| Run files (`semops-run/1`) | written by `run.py --write-run` |

## Still to do

- Reference runs (`plan ref`) on dev and eval for Q1-Q6, with a cloud model (gateway route + credits).
- Optimisations: cascade (proxy + oracle), blocking for joins, block prompts; frontier of at least three operating points.
- Better τ and prompts; error analysis. Q5 matching beyond identical names.
- The 6 own queries (M2) with answer key under `keys/`, leakage check; design note and report.

## Repository layout

```
.
├── README.md
├── prices.json          our price list (every model used must be listed, even at price 0)
├── run.py               the program to launch
├── semops/
│   ├── config.py        group id, gateway address, criteria, label set
│   ├── prompts.py       τ, instructions, JSON schemas, prompt builders
│   ├── gateway.py       HTTP client of the LLM gateway
│   ├── fake.py          free fake models, for testing without any model
│   ├── operators.py     sem_filter / classify / map / join as Oxigraph functions
│   ├── engine.py        graph loading, running the .rq files, join sampling
│   ├── metrics.py       evaluation against gt/*.csv
│   ├── runfiles.py      official run files
│   └── pipelines.py     one function per query type
├── query/               q1 q2 q4 q5 q6 and the three q3 plans (.rq)
├── runs/                official run files (committed)
├── keys/                answer keys of our own queries (committed)
└── data/games/          NOT committed: course data package (dev/, eval/)
```

## Setup

1. `pip install pyoxigraph`
2. Data: copy the course package to `data/games/` (never commit it; `hidden.nt` least of all).
3. **Gateway** (separate folder, e.g. `~/llm-gateway`): follow its README and manual. On a Mac with an Intel processor `bash setup.sh` fails on `onnxruntime`; install without the embedding libraries:
   ```bash
   uv sync --locked --python 3.12 --no-install-package fastembed --no-install-package onnxruntime
   ```
   then run the remaining steps of `setup.sh` by hand (`chmod +x bin/* tools/semops_cli.py`, copy `gateway.toml.example` to `gateway.toml` and `models.toml.example` to `models.toml`, copy the credential templates). Embeddings then come from `local/nomic-embed-text` (Ollama) or Google. Start it with `start server`; check with `curl http://127.0.0.1:8000/health`.
4. Local model: `ollama pull qwen2.5:3b` (Ollama must be running).
5. Run files: set `SEMOPS_CHECKER_PATH` to `semops_check.py` (outside this repository), and set `SEMOPS_GROUP_ID` (or edit `semops/config.py`). `SEMOPS_GATEWAY_LOG` must point to the gateway's `data/calls.jsonl` if the gateway is not in `~/llm-gateway`.

## Usage

```bash
python run.py <Q1|Q2|Q3|Q4|Q5|Q6|Q8> [--llm fake|gateway] [--model NAME] [--set dev|eval]
              [--n N] [--m M] [--plan ID] [--run-id ID] [--reference-run ID]
              [--source-run ID] [--query-file FILE] [--write-run] [--yes]
```

| Option | Meaning |
|---|---|
| `--llm` | `fake` (default, free) or `gateway` (real model) |
| `--model` | public model name of the gateway (default `local/qwen2.5:3b`) |
| `--n` | only the first N inputs (0 = all) |
| `--m` | Q6 tests only: M series on the right; makes the test easier than the real one |
| `--plan` | plan id in the run file (`ref` = reference plan) |
| `--source-run` | Q8: run id of the Q1 run whose decisions are reused |
| `--write-run` | write `runs/games/<set>/<query>/<run_id>.json` (needs `--llm gateway`, no `--m`) |
| `--yes` | skip the confirmation on big runs |

Examples:

```bash
python run.py Q1 --llm fake
python run.py Q1 --llm gateway --n 20
python run.py Q6 --llm gateway --n 6 --m 10
python run.py Q1 --llm gateway --plan ref --write-run --run-id g07-dev-q1-ref
python run.py Q8 --source-run g07-dev-q1-ref --write-run --run-id g07-dev-q8-ref
python run.py Q3 --query-file query/q3_struttura_prima.rq --llm gateway --plan structure-first
```

The evaluation against `gt/` is printed automatically when the file exists. Add `| tail -30` to see only the summary.

## How it works

```
run.py
 ├─ loads the graph (graph.nt) into Oxigraph
 ├─ runs the query once with an "always true" backend (free): the candidates
 └─ runs the query for real: Oxigraph calls our sem_* function per row
        tau(row) -> text -> instructions + "Criterion: ℓ" + text + JSON schema
        -> POST /v1/responses on the gateway (cache, validation, retries, log)
    then evaluates, and with --write-run builds the run file:
        answer (SPARQL JSON) + calls read from the gateway log + price list -> semops_check.write_run_file
```

Notes:
- `parse_ok: false` from the gateway means the model failed the schema; it is counted as a broken answer, not as a "no".
- Cache hits and tokens are only in the gateway log. The cache is the gateway's (namespace `llme-v1`, see `config.py`); `run_id` is not part of the cache key.
- The run id should be unique per execution (the default adds a timestamp): the log is read by run id.
- Each query reads its fixed criterion from the `.rq` file; the instructions around it, τ and the model are ours.

## Open points

- Group id (`g..`) to be set in `config.py`.
- Which model is the oracle for the official runs, and prices of the cloud models in `prices.json`.
- P178 (developer) in τ: allowed by the property catalogue but it is the Q5 solution; not used for now.
- τ text: `ex:lead` as in `graph.nt`; comparison with `description_screened` still to do.
- Q6 with the small local model accepts unrelated series (precision 0.21 on an easy sample): to improve with prompt, cascade or blocking.
- How cache hits count in the official costs: the checker records `cache_hit` for each call.

## Git rules

- Never commit `data/`, `hidden.nt`, credentials (`*.local.env`).
- Commit `runs/` and `keys/`: they are the submission.
- One branch per task; one change of prompt, τ or model per commit, with the effect on the metrics in the message.
