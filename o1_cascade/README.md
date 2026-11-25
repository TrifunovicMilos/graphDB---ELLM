# O1: the model cascade

A cheap **proxy** answers every input; when it is unsure, the strong **oracle** decides. This is optimization O1 of the course, applied to the filter queries (Q1, Q2, Q3).

| Role | Model | Cost |
|---|---|---|
| Proxy | `local/qwen2.5:3b` (Ollama, through the gateway) | free |
| Oracle | `gemini-3.5-flash-lite` (Vertex AI, through the gateway) | about $0.00008 per call |

The oracle was chosen on 50 dev games (25 platformers): F1 0.96 for Flash-Lite against 0.76 for the 3B model, with no thinking tokens (5 output tokens per answer). Gemini 3.5 Flash would cost about 25 times more per call because of its default thinking.

## Decision pending: which operating points to report and ship

Not decided yet (calibration on dev, 24 Nov; see `calibration_dev_q1.md` for all 14 targets from 0.86 to 0.99).

| Candidate | Thresholds (θ_low / θ_high) | Oracle calls | f1_ref | F1 vs answer key |
|---|---|---|---|---|
| 0.90 | −12.370856 / 3.002084 | 5.7% | 0.900 | 0.820 |
| 0.95 | −18.569462 / 6.121365 | 14.7% | 0.951 | 0.840 |
| 0.96 | −18.720532 / 10.692574 | 16.8% | 0.961 | 0.849 |
| 0.99 | −21.045546 / 14.318511 | 62.9% | 0.990 | 0.858 |

- The course asks for at least three operating points and the one we would ship.
- The knee of the curve is at about 0.96: up to there each +0.01 of f1_ref costs 8–22 oracle calls, beyond it 100–250.
- Proposed: report 0.90 / 0.96 / 0.99 and ship 0.96. The alternative is to ship 0.95 (21 fewer calls; the difference is within the confidence interval).
- Confirm the three operating points and the default before packaging the dev runs. Keep the same Q1 thresholds for eval.

## Results on dev (Q1, 24 Nov)

**The reference.** Gemini 3.5 Flash-Lite on all 1,000 dev games (`runs/games/dev/Q1/g00-dev-q1-ref.json`):
- precision 0.835, recall 0.885, **F1 0.859** against the answer key (direct key: 0.815);
- 1,000 calls, 231,029 input and 5,000 output tokens, **$0.082**, 39 minutes;
- 0 parse failures.

The 3B model alone on the same games: F1 0.765 (precision 0.83, recall 0.71). The oracle's lead comes almost entirely from recall: it knows platformers whose text never says so.

**The curve** (`frontier_dev_q1.png`, every point in `frontier_dev_q1.csv`). F1 against the reference rises steeply at first, then flattens:

| Step | Extra oracle calls per +0.01 f1_ref |
|---|---|
| up to 0.96 (16.8% of the games) | 8–22 |
| 0.96 → 0.97 → 0.98 → 0.99 | 110, 100, 251 |

**Why the knee.** It depends on how often the oracle overrules the proxy's "no" at each confidence level:

| Proxy "no" score | Games | Oracle says "yes" |
|---|---|---|
| −5 to 0 (unsure) | 17 | 53% |
| −10 to −5 | 20 | 45% |
| −15 to −10 | 31 | 19% |
| −20 to −15 | 146 | 12% |
| below −20 (extremely sure) | 615 | 2% |

- The cascade first sends the unsure games, where the oracle overrules about half: big gains for few calls.
- The last 13 disagreements hide among 615 extremely sure "no" answers. Catching them means asking about nearly all of those games: the flat, expensive tail.
- The proxy's "yes" is rarely wrong (13 of 171), so θ_high stays low while θ_low is far below zero.

The steps in the curve come from how densely the games sit in each band, not from ties: 902 of the 1,000 scores are distinct.

## How it decides (`semops/cascade.py`)

The proxy's **score** is the log-odds that the answer is true, read from its top-5 token log-probabilities: `score = ln P(true) − ln P(false)`. When one side is not in the top 5, its probability is bounded by the smallest listed one, so the score is then a bound. On dev, 482 of 1,000 scores are exact.

| Proxy score | Answer |
|---|---|
| ≤ θ_low | no (the proxy decides) |
| ≥ θ_high | yes (the proxy decides) |
| in between, or no score | the oracle decides, with **exactly the reference request**, so on a set with a reference run it is a cache hit |

## Workflow

1. **Reference run:** the oracle on every input (plan `ref`). These are the labels and fill the cache.
   ```bash
   python run.py Q1 --llm gateway --model gemini-3.5-flash-lite --plan ref --run-id g00-dev-q1-ref --write-run --yes
   ```
2. **Calibration on dev:** the script reads the committed proxy scores and oracle reference file, computes the cost/agreement curve, and picks the cheapest thresholds for each target. This path runs offline.
   The committed files were made with 14 targets and a fine curve:
   ```bash
   python o1_cascade/calibrate.py --reference g00-dev-q1-ref --targets 0.86 0.87 0.88 0.89 0.90 0.91 0.92 0.93 0.94 0.95 0.96 0.97 0.98 0.99 --curve-rows 60
   ```
   Options:
   - `--targets`: the f1_ref values to find thresholds for (default 0.90 0.95 0.99)
   - `--curve-rows`: about how many curve points to list in the report (default 25)
   - `--rescore`: recompute the proxy scores through the gateway instead of reusing `scores_dev_q1.csv`

   It writes (re-running replaces these files):
   - `calibration_dev_q1.md`: the operating points, the curve, and the ready commands for step 3
   - `frontier_dev_q1.csv`: every best point
   - `frontier_dev_q1.png`: the plot (needs `pip install matplotlib`)
   - `scores_dev_q1.csv`: the proxy score of every game
3. **Operating points:** one official run file per point. The current calibration generator prints commands without `--llm gateway`, so add the flag as below. Replace the example group and run IDs before using the commands for submission.
   ```bash
   python run.py Q1 --set dev --llm gateway --plan o1-<target> --model gemini-3.5-flash-lite --proxy-model local/qwen2.5:3b \
       --theta-low <θ_low> --theta-high <θ_high> --target <target> --reference-run g00-dev-q1-ref \
       --run-id g00-dev-q1-o1-<target> --write-run --yes
   ```
   The run file records `model_proxy`, the thresholds, the score method and the target in `plan_params`, and `reference_run_id`. The checker then reports `oracle_fraction` and the agreement with the reference (`precision_ref`, `recall_ref`, `f1_ref`).
4. **Evaluation set, once:**
   - the reference run on eval (mandatory anyway),
   - then the same three operating points **with the thresholds learned on dev**, without recalibrating.

**Agreement** is measured as the course checker does for a filter: F1 of the cascade's answer set against the reference's answer set (`f1_ref`). The share of identical decisions, with a 95% interval, is reported too.

## Checked before use

On dev, with the real cached answers of both models:
- `run.py --plan o1-…` made exactly the decisions the calibration predicted at all three targets: the same number of oracle calls (57, 147, 629) and the same `f1_ref`.
- The course checker accepted an O1 run file and reported `oracle_fraction` 0.147 and `f1_ref` 0.951 for the 0.95 point.
