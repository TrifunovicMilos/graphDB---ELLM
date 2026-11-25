# Semantic operators on graphs: *games* domain (Oxigraph)

Team project for the course *Graph Databases* 2026/2027. Group: **LLME**.
Domain: video games with series. Engine: **Oxigraph** (`pyoxigraph`). Every model call goes through the course **LLM gateway**.

[M1 design note](docs/m1-design-note.md) · [Reproduction guide](docs/reproduce.md) · [O1 calibration](o1_cascade/README.md)

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
| Q3 restriction + filter | Structure-first and semantic-first plan files. Pass `--query-file` while the separate Q3 fix is pending. |
| Q4 classification | done (the 8 labels are an enum of the answer schema) |
| Q5 extraction | done, simple matching |
| Q6 join 50 x 100 | done, nested loop (5,000 pairs) |
| Q7 large join (optional) | missing (blocking with embeddings) |
| Q8 count per decade | done, reuses a Q1 run |
| Run files (`semops-run/1`) | written by `run.py --write-run` |

## Still to do

- The Q1 dev Flash-Lite reference is checked in under provisional group ID `g00`. Record the remaining Q1–Q6 reference runs on dev and eval.
- Confirm three O1 operating points and the default, record the runs, and evaluate the dev thresholds on eval. Blocking for joins and block prompts remain separate options.
- Error analysis; Q5 matching beyond identical names. (τ and prompts: done, v1 frozen, see `tau_experiments/`.)
- Six own queries (M2), with answer keys and leakage checks, and the final report.

## τ and prompts: version v1 (frozen)

What the model sees was chosen with two experiments on the development set (3B model, temperature 0); the method, all results and the reasons are in [`tau_experiments/README.md`](tau_experiments/README.md).

| Part | Frozen choice |
|---|---|
| τ (text of an entity) | **A**: label + Wikipedia lead, cut at 1,200 characters (`prompts.tau_label_lead`) |
| Filter instructions (Q1, Q2, Q3) | **F0**: the original text |
| Join instructions (Q6, Q7) | **J5**: strict; "if neither text mentions the other item, answer false" |
| Classify / map (Q4 / Q5) | **C0 / M0**: the original texts |

τ is built once per entity when the graph is loaded and stored as `ex:tau`; the queries pass `?tau` to the operators. The criterion ℓ always goes in verbatim (`Criterion: <ℓ>`). Every run file records `prompt_version` (`v1`, or `experimental` when `--tau` / `--instr` select something else). Changing any of these texts means a new version, new reference runs and a new cascade calibration.

## Repository layout

```
.
├── README.md
├── prices.json          our price list (every model used must be listed, even at price 0)
├── run.py               the program to launch
├── semops/
│   ├── config.py        group id, gateway address, criteria, label set
│   ├── prompts.py       frozen τ and instructions (v1), JSON schemas, prompt builders
│   ├── gateway.py       HTTP client of the LLM gateway
│   ├── fake.py          free fake models, for testing without any model
│   ├── operators.py     sem_filter / classify / map / join as Oxigraph functions
│   ├── engine.py        graph loading, running the .rq files, join sampling
│   ├── metrics.py       evaluation against gt/*.csv
│   ├── runfiles.py      official run files
│   ├── cascade.py       O1: proxy score from log-probabilities, thresholds, cascade backend
│   └── pipelines.py     one function per query type
├── query/               q1 q2 q4 q5 q6 and the q3 plans (.rq)
├── tau_experiments/     how τ and the instructions were chosen: scripts, results.csv, logs, README
├── o1_cascade/          O1 cascade: calibration script, curve and operating points, README
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
              [--tau ID] [--instr ID] [--inputs FILE]
              [--proxy-model NAME] [--theta-low X] [--theta-high Y] [--target T]
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
| `--tau`, `--instr` | another τ / instructions than the frozen ones (only those registered by `tau_experiments/variants.py`; experiments only) |
| `--inputs` | file with one game code per line: run only on these games (tests and experiments; not with `--write-run`) |
| `--plan o1...` | the O1 cascade (filter queries): `--model` is the oracle, `--proxy-model` the cheap model, `--theta-low` / `--theta-high` the thresholds from `o1_cascade/calibrate.py`; see `o1_cascade/README.md` |

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
        ex:tau of the row (built at load time) -> instructions + "Criterion: ℓ" + τ + JSON schema
        -> POST /v1/responses on the gateway (cache, validation, retries, log)
    then evaluates, and with --write-run builds the run file:
        answer (SPARQL JSON) + calls read from the gateway log + price list -> semops_check.write_run_file
```

Notes:
- `parse_ok: false` from the gateway means the model failed the schema; it is counted as a broken answer, not as a "no".
- Cache hits and tokens are only in the gateway log. The cache is the gateway's (namespace `llme-v1-tau<τ>`, see `config.py` and `run.py`); `run_id` is not part of the cache key.
- The run id should be unique per execution (the default adds a timestamp): the log is read by run id.
- Each query reads its fixed criterion from the `.rq` file; the instructions around it, τ and the model are ours.

## Open points

- **TODO: O1 operating points.** Decide which operating points to report and which to ship (proposed 0.90 / 0.96 / 0.99, ship 0.96; see `o1_cascade/README.md`), then run them on dev and, with the same thresholds, on eval.
- **TODO: real group id.** `semops/config.py` still uses the placeholder `GROUP_ID = "g00"` (the course assigns a `gNN` id; ask on Moodle or the professor). Until it is set, every run file and run id says `g00`. Once known: set `GROUP_ID` (or `SEMOPS_GROUP_ID`), then **re-run every `--write-run` made with `g00`** (reference runs, O1 operating points) with the real id. The model answers come from the gateway cache, so this costs nothing; delete the old `g00` files under `runs/` afterwards. Not needed for tests, experiments or calibration on dev.
- Confirm the official oracle and the approved cloud budget. The existing Q1 dev reference uses `gemini-3.5-flash-lite`, with its rates recorded in `prices.json`.
- P178 (developer) in τ: allowed by the property catalogue but it is the Q5 solution; not used for now.
- `query/q3_naive.rq` is the default Q3 file in `config.py` but does not exist: `python run.py Q3` fails unless `--query-file` is given.
- Q6: with the J5 instructions the 3B model reaches F1 0.74 on 10 dev games (it was 0.14); the wrong pairs left share a publisher with the game. Next: blocking (O2) or the cascade's oracle.
- How cache hits count in the official costs: the checker records `cache_hit` for each call.
