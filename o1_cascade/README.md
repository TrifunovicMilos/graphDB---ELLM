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
- **Decide before running the official dev operating points**, and then keep the same thresholds for eval.

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
2. **Calibration on dev:** no paid calls. The proxy's answers come from the cache and the oracle's from the reference run file. The script computes the whole cost/agreement curve and picks the cheapest thresholds for each target.
   ```bash
   python o1_cascade/calibrate.py --reference g00-dev-q1-ref
   ```
   It writes:
   - `calibration_dev_q1.md`: the operating points, the curve, and the ready commands for step 3
   - `frontier_dev_q1.csv`: every best point
   - `frontier_dev_q1.png`: the plot (needs `pip install matplotlib`)
   - `scores_dev_q1.csv`: the proxy score of every game
3. **Operating points:** one official run file each, with the commands printed by step 2:
   ```bash
   python run.py Q1 --plan o1-95 --model gemini-3.5-flash-lite --proxy-model local/qwen2.5:3b \
       --theta-low <θ_low> --theta-high <θ_high> --target 0.95 --reference-run g00-dev-q1-ref \
       --run-id g00-dev-q1-o1-95 --write-run --yes
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
