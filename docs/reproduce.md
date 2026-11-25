# Reproduce the LLME runs

Run the project commands from the repository root. The official course `games` package and evaluation checker are distributed through Moodle. The [course LLM gateway](https://github.com/GDB-2026-2027/llm-gateway) is a separate checkout.

## 1. Verify the checked-in evidence offline

Prerequisites are Python, PyOxigraph, the course data and the checker. The committed reference records Oxigraph 0.5.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install 'pyoxigraph==0.5.13'

export SEMOPS_CHECKER_PATH=/absolute/path/to/semops_check.py
export GAMES_DATA="$PWD/data/games"

python run.py Q1 --set dev --llm fake --n 10
python "$SEMOPS_CHECKER_PATH" runs/games/dev/Q1/g00-dev-q1-ref.json \
  --data "games=$GAMES_DATA" --results /tmp/llme-dev-reference.csv
```

Place `dev/` and `eval/` under `data/games/`. For an alternate data location, set `GAMES_DATA` to its absolute path and add `--data-root "$GAMES_DATA"` to runner commands. The calibration script itself expects `data/games/`. The fake run verifies SPARQL and the operator wiring. The checker reads the existing run file and answer key without issuing model requests. The expected reference row has 1,000 calls and F1 0.859.

To reproduce the Q1 development frontier using the committed scores and reference, run the following with `data/games/` populated. It regenerates the calibration Markdown and CSV, and writes the plot if Matplotlib is installed. Use a disposable checkout if you want to keep the committed copies as-is.

```bash
python o1_cascade/calibrate.py --reference g00-dev-q1-ref \
  --targets 0.86 0.87 0.88 0.89 0.90 0.91 0.92 0.93 0.94 0.95 0.96 0.97 0.98 0.99 \
  --curve-rows 60
```

With matching score and reference files, this step needs neither the gateway nor credentials. `--rescore` uses the proxy through the gateway. The current generator’s printed operating-point commands need the additional flag `--llm gateway`. Use the example in section 3 when executing a run.

## 2. Configure the gateway for live runs

Follow the gateway’s [setup instructions](https://github.com/GDB-2026-2027/llm-gateway#configuration-and-startup). Enable Ollama with `qwen2.5:3b` for the proxy. Its `local/qwen2.5:3b` gateway route must expose top-5 token log-probabilities for O1. Check that `gemini-3.5-flash-lite` is configured in the gateway’s local `models.toml`. If it is absent from the template, add this route and use the Google Cloud project and location approved for your team.

```toml
[models."gemini-3.5-flash-lite"]
backend = "google_genai"
task = "responses"
upstream_model = "gemini-3.5-flash-lite"
json_schema_mode = "native"
```

Set `[google].project_id` in `gateway.toml`, enable Vertex AI on that project and authenticate with Application Default Credentials. The generic gateway health check confirms the local server is up. A one-game probe verifies the specific model route and permission to call it. Use the approved project and confirm billing before the probe. Keep credentials, local configuration and SQLite caches out of Git. See the [gateway configuration reference](https://github.com/GDB-2026-2027/llm-gateway/blob/main/docs/CONFIGURATION.md).

```bash
export SEMOPS_GATEWAY_LOG=/absolute/path/to/gateway/data/calls.jsonl
export SEMOPS_GROUP_ID=gNN  # Replace with the course-assigned group ID.

curl -fsS http://127.0.0.1:8000/health
python run.py Q1 --set dev --llm gateway --model gemini-3.5-flash-lite --n 1
```

The project’s [price list](../prices.json) records the rates used in the run files. Keep the gateway’s own price-list entry aligned when comparing log estimates. Use the same prompt version, model route IDs and cache namespace when replaying a reference. A reference request can be reused only when the matching entry is available in the gateway cache.

## 3. Record and check a reference and a cascade run

The example uses the proposed 0.96 **Q1** operating point. Replace `gNN` in `SEMOPS_GROUP_ID` first. The reference requests one oracle decision per input, so check the actual gateway cache and budget before proceeding. Omit `--n` for the full set.

```bash
REF_RUN="${SEMOPS_GROUP_ID}-dev-q1-ref"

python run.py Q1 --set dev --llm gateway --model gemini-3.5-flash-lite \
  --plan ref --run-id "$REF_RUN" --write-run

python run.py Q1 --set dev --llm gateway --model gemini-3.5-flash-lite \
  --plan o1-96 --proxy-model local/qwen2.5:3b \
  --theta-low -18.720532 --theta-high 10.692574 --target 0.96 \
  --reference-run "$REF_RUN" --run-id "${SEMOPS_GROUP_ID}-dev-q1-o1-96" --write-run

python "$SEMOPS_CHECKER_PATH" . --data "games=$GAMES_DATA" --results results.csv
```

Use the same split’s reference run ID for each comparison. For eval, first record the eval reference and apply the thresholds chosen on dev. Keep the thresholds specific to the query and prompt version that produced them. The checked-in frontier shows Q1 development calibration only. See the [cascade experiments](../o1_cascade/README.md) for the other candidate thresholds.

Q8 takes `--source-run` for the matching Q1 run on the same split. On the current cascade branch, Q3 needs `--query-file query/q3_struttura_prima.rq` for its reference attempt until the separate Q3 fix is integrated. Verify the run metadata and the checker’s reported input count before using that result. For Q6, use `--n` and `--m` for debugging only, and account for 5,000 pairs in the full nested-loop plan.

## 4. Evidence to record for submission

- Capture the prompt version, model names, threshold values, cache namespace, installed versions, price-list ID and run IDs.
- Keep each run JSON, the checker’s results table and the source log records needed for reproduction. Report oracle routing share, new upstream calls, tokens, wall time, cost, agreement with the reference and F1 against the official key.
- Resolve the real group ID before packaging. The committed `g00` reference is development evidence. Re-export under the assigned ID with verified cache coverage before treating it as a submission run.
- Verify clean-clone reproduction on another machine. Final reference runs beyond Q1 dev, eval runs, the chosen operating points, the own-query keys and the assigned pool results are still to be collected.
