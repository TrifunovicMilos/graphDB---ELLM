# How τ and the instructions were chosen

Two experiments on the **development set** decided what the model sees in every request: the text of an entity (**τ**) and the **instructions** around the fixed criterion. This folder holds the scripts, every run, and the results. The choice is frozen in `semops/prompts.py` as **prompt version v1**.

## Result: what is frozen (v1)

| Part | Choice | Why |
|---|---|---|
| τ | **A**: label + Wikipedia lead, cut at 1,200 characters | Best mean of five variants. The others tie on Q1, Q2 and Q4, and are worse on Q6. A uses no description, so the 9 Q4 games whose screened description still names their genre cannot leak. |
| Filter instructions (Q1, Q2, Q3) | **F0**: the original text | Five alternatives: none is better. F1 ties with F0 on all 1,000 dev games (142 correct platformers each). F3 recovers mixed-genre platformers in Q1 but halves Q2's precision. |
| Join instructions (Q6, Q7) | **J5**: strict, and "if neither text mentions the other item, answer false" | Q6 F1 from 0.14 to 0.74 over 10 dev games, recall stays 1.0, confirmed on games the choice had not seen. |
| Classify / map (Q4 / Q5) | **C0 / M0**: the original texts | Not tested. |

Effect on Q6, the query that needed it most: wrong "yes" answers fall from **121 to 7** over 10 games × 100 series, at about 5% more input tokens per call than the original join text.

## Method

**Fixed conditions.** Model `local/qwen2.5:3b` through the course gateway, temperature 0, development set only. Only one thing changed at a time:
- experiment 1 varied τ, with the instructions of that time (F0, C0, J0);
- experiment 2 varied the instructions, with τ fixed to A.

**Fixed sample** (`samples/`, seed 42). Every variant saw exactly the same games:

| Query | Sample | Metric |
|---|---|---|
| Q1 platformer | 400 random main-set games (88 platformers) | F1 against the expanded key (`path`) |
| Q2 visual novel | all 30 visual novels + 270 random others | F1 against the expanded key |
| Q4 genre | 200 random Q4 inputs | macro-F1 |
| Q6 game ↔ series | first 5 games × all 100 series (5 true pairs) | F1, and the pairs accepted |

Q2 keeps all its positives, so its precision is higher than on the full set. The sample numbers are for *comparing* variants, not the official Q2 result.

**Holdout** (`samples/holdout_*`). Dev games the sample did not use: the other 600 main-set games for Q1, and games 6–10 × 100 series for Q6. A winner had to hold there. Q2 has no holdout: all 30 dev visual novels are in the sample.

**Decision rule, fixed before the first run.** The best mean score wins, unless its input tokens per call are more than 25% above the cheapest variant. Differences under about 0.02–0.03 are ties, and a tie keeps the simpler or original option. For Q6, the number of accepted pairs is reported next to F1, because with 5 true pairs F1 alone hides how many wrong "yes" answers the model gives.

**Course rules respected.**
- ℓ is fixed and goes into every request verbatim as `Criterion: <ℓ>`. τ, the instructions, the plan and the model are ours ("Common Query Reference").
- Each operator has one general instruction: no game terms, and no examples taken from the data. The pool will run the same prompts on films and on other groups' queries. The two examples in J2 are invented and about books.
- Only the hidden properties are kept out of τ, and only `description_screened` is used, never the raw description in `graph.nt`.
- Tuning was done on dev only, and the prompts are frozen before the reference runs and the cascade calibration ("a prompt change invalidates the calibration").

## Experiment 1: τ

Variants (`variants.py`, `TAU_SPECS`):

| | Fields | Budget | Cut |
|---|---|---|---|
| A | label + lead | 1,200 chars | hard |
| B | label + screened description + lead (the course's release τ) | 1,200 | hard |
| C | `Name:` / `Description:` / `Article:`, whitespace collapsed | 1,200 | at a sentence end |
| C-900 | as C | 900 | at a sentence end |
| C-600 | as C | 600 | at a sentence end |

**Text statistics** (`tau_texts/report_dev.md`, `cl100k_base`, dev games). Mean / p90 tokens of τ:
- A: 146 / 252
- B: 151 / 255, which matches the course data card's 152 / 256 for the same τ
- C: 153 / 242
- C-900: 137 / 190
- C-600: 110 / 137

The budget shortens 15% of game texts in A and 51% in C-600.

**Results on the sample** (from `summary_tau.md`; input tokens are per call, instructions included, averaged over the four queries):

| τ | Q1 F1 | Q2 F1 | Q4 macro-F1 | Q6 F1 (pairs accepted) | **Mean** | Input tokens / call |
|---|---|---|---|---|---|---|
| **A** | 0.797 | **0.829** | 0.770 | **0.100 (95)** | **0.624** | 256 |
| B | **0.809** | 0.780 | 0.760 | 0.070 (136) | 0.605 | 265 |
| C | 0.800 | 0.794 | 0.780 | 0.040 (245) | 0.603 | 267 |
| C-900 | 0.800 | 0.780 | 0.780 | 0.040 (270) | 0.600 | 249 |
| C-600 | 0.787 | 0.785 | **0.800** | 0.050 (198) | 0.606 | **211** |

All runs had 0 parse failures.

**What it showed:**
- **Q1, Q2 and Q4 are a tie.** All five variants fall within 0.016 of each other on the mean of the three.
- **The description adds nothing, and makes the 3B model less stable.** For 74% of games it is just "YYYY video game". Even so, adding it flipped four Q2 answers to wrong "yes" (Anna's Quest, Beholder, I Am Setsuna, Touch My Katamari). The model reacts to the wording, not to information.
- **The labelled-fields format roughly doubles the wrong "yes" on the join:** 245–270 accepted pairs for the C variants against 95 for A. That is the one large, non-random difference.
- **A wins by the rule.** It has the best mean, its cost is 21% above C-600 (under the 25% limit), and it is the simplest variant. C-600 would save 16–21% of tokens, but at the price of twice the Q6 errors.

**Leakage** (`tau_texts/report_dev.md`):
- The screened description never states the answer of Q1 or Q2.
- For Q4 it does, in other words, for **9 of 444** games (e.g. "Japanese role-playing game"). This is a gap in the course's own screening, which only catches the exact label. A does not use the description, so it is not affected.
- The 20 Q1 positives of each variant are in `tau_texts/texts_dev_tau*.txt` for the manual check the slides require.

## Experiment 2: instructions (τ = A)

All variants are in `variants.py` (`INSTRUCTION_NOTES` describes each one):

| | Operator | Idea |
|---|---|---|
| F0 | filter | the original text |
| F1 | filter | decide from the text and what the model knows about the item |
| F2 | filter | a more specific form of the category counts; judge the main nature |
| F3 | filter | F0 + "also satisfied when the text uses another name for it or combines it with other properties" |
| F4 | filter | F3 shortened, without the JSON sentence |
| F5 | filter | only "Decide whether the item satisfies the criterion." |
| J0 | join | the original text |
| J1 | join | strict: true only if the criterion holds for this pair; shared creator, publisher, genre or theme is not enough; most pairs are false |
| J2 | join | J1 + two invented examples |
| J3 | join | J1 shortened |
| J4 | join | J1 + "if neither text mentions the other item, answer false" |
| J5 | join | J4 shortened |

There were two rounds:
- **Round 1:** F1, F2, J1, J2.
- **Round 2:** F3–F5 and J3–J5, built on the errors of round 1.

The short variants leave out "Answer only with JSON…", because the gateway already enforces the answer schema; they still had 0 parse failures.

**Filter results, sample:**

| | Q1 F1 (P / R) | Q2 F1 (P / R) | Mean | Tokens / call |
|---|---|---|---|---|
| **F0** | 0.797 (0.85 / 0.75) | 0.829 (0.96 / 0.73) | **0.813** | 203 |
| F1 | 0.787 (0.84 / 0.74) | 0.844 (1.00 / 0.73) | 0.815 | 214 |
| F2 | 0.771 (0.83 / 0.72) | 0.814 (0.92 / 0.73) | 0.793 | 236 |
| F3 | **0.805** (0.80 / **0.81**) | 0.711 (0.66 / 0.77) | 0.758 | 222 |
| F4 | 0.761 (0.88 / 0.67) | 0.806 (0.95 / 0.70) | 0.783 | 202 |
| F5 | 0.771 (0.83 / 0.72) | 0.791 (0.91 / 0.70) | 0.781 | 183 |

On the holdout (600 games), F0 scored 0.743 and F1 0.754. Pooled over all 1,000 dev games, **both find exactly 142 of the 200 platformers** (F1 F1 0.768, F0 0.765), so it is a tie and F0 stays.

**Join results** (Q6; pairs accepted out of 500, 5 true):

| | Sample (games 1–5) | Holdout (games 6–10) | Pooled, 10 true pairs | Tokens / call (sample) |
|---|---|---|---|---|
| J0 | 0.100, 95 accepted | 0.240, 36 accepted | P 0.08, R 1.00, **F1 0.142** | 374 |
| J1 | 0.350, 18 accepted | 0.670, 10 accepted | P 0.32, R 0.90, F1 0.474 | 419 |
| J2 | 0.000, 1 accepted | – | – | 507 |
| J3 | 0.190, 49 accepted | – | – | 383 |
| J4 | 0.560, 13 accepted | – | – | 430 |
| **J5** | **0.670, 10 accepted** | **0.830, 7 accepted** | **P 0.59, R 1.00, F1 0.741** | 394 |

**What it showed:**
- **Filter instructions barely matter for the 3B model.** Most of its misses are information that is not in the text: of the 58 platformers F0 missed across dev, only about 20 say "platform" anywhere. Those 20 mostly describe a mixed genre ("third-person shooter platform game", "puzzle-platform"). F3 recovers exactly those, but on Q2 the same sentence makes the model call adventure games visual novels, so a general instruction cannot have it.
- **Short versions of the filter text lose about 0.03.** The model reacts to the wording around the content (the "You are a classifier" opening, the JSON sentence), not only to the content itself.
- **The join was a yes-bias, and an instruction fixes most of it.**
  - J1 cut the wrong "yes" answers by about 80%.
  - The mention rule of J4 and J5 cut them further, and also recovered the one true pair J1 lost (Snake's Revenge ~ Metal Gear).
  - J5 costs about 6% fewer tokens than J1.
  - J2's examples overcorrected: the model then rejected almost every pair.
- **What the 3B model still gets wrong with J5:** pairs whose series shares a publisher with the game (Modern Combat 2 / 3 ~ Brothers in Arms, both Gameloft). These are exactly the hard distractors the course put on the right side. Blocking (O2) or the cascade's oracle is the next step, not more instructions.

## Limits of this evidence

- Everything was decided with the 3B model. The oracle may react differently, so a check of the frozen prompts on about 100 games with the oracle is advisable.
- Q2 had no holdout, and Q6 rests on 10 true pairs.
- No deliberate repeat run was made. Temperature 0 is nearly deterministic, but the noise level (about 0.02–0.03) is an estimate.
- The sample and holdout were used for two rounds of choices, so the margins of the winners are probably slightly optimistic. Further tuning on these games is not advisable.

## Folder contents

```
tau_experiments/
├── README.md               this file
├── results.csv             every run of both experiments, one row each (66 runs)
├── summary_tau.md          table of experiment 1 (written by tau_experiment.py)
├── summary_instructions.md tables of experiment 2, with the holdout and the pooled results
├── variants.py             every tested τ and instruction variant (exact texts)
├── common.py               shared code: paths, sample, one run, results.csv
├── tau_experiment.py       experiment 1
├── instr_experiment.py     experiment 2
├── tau_report.py           τ lengths, tokens, leakage scan, texts to read by hand
├── samples/                the fixed sample and the holdout (lists of game codes)
├── tau_texts/              report_dev.md + the 20 Q1 positives in each τ variant
└── logs/                   the full output of every run (<run_id>.log)
```

**`results.csv` columns:**
- `experiment` (tau | instructions), `workload` (pilot | sample | holdout)
- `tau`, `instructions`, `query`
- `metric`, `score`, `precision`, `recall`, `accepted_pairs` (Q6)
- `calls` (operator calls), `parse_failures`
- `input_tokens` and `input_tokens_per_call` (distinct requests, from the gateway log), `cache_hits`
- `seconds`, `model`, `run_id`, `finished`

The 20 pilot rows were a first small check of the chain; they take no part in any decision.

**Two record-keeping notes:**
- The J0 and J1 sample runs started in the same second and got the same run id (`…-1123133757`). J1's output overwrote the log, and the token count of that run id mixes both.
  - The J1 row has its own numbers (its 500 requests are the ones not cached).
  - The J0 row is marked `…-J0`. J0 answered all 500 pairs from the cache of the τ run A, so its log is that run's output, with a note at the top.
  - Since then, run ids include the workload and the instruction id, and a run id is never reused, so this cannot happen again.
- The holdout command `--holdout F0 J5` re-ran F0 (twice) and J0 entirely from the cache, so the holdout has extra F0 and J0 rows with only cache hits. The summaries use the latest row of each.

## How to run

**Requirements:** the course data in `data/games/`, the project's virtual environment, and for real runs Ollama (`qwen2.5:3b`) and the gateway (`bin/start server` in `~/llm-gateway`). `tau_report.py` needs no model; install `pip install tiktoken` for exact token counts.

From the project folder:

```bash
# texts: lengths, tokens, leakage scan, 20 positives per variant to read  (seconds, no model)
python tau_experiments/tau_report.py

# experiment 1: all tau variants on the sample (about 1,400 calls per variant)
python tau_experiments/tau_experiment.py --pilot          # a few minutes: check the chain first
python tau_experiments/tau_experiment.py                  # or --taus A C-600 for some variants

# experiment 2: instruction variants on the sample, then a filter + join choice on the holdout
python tau_experiments/instr_experiment.py                # or --filters F0 F3 --joins J1 J5
python tau_experiments/instr_experiment.py --holdout F0 J5

# only rebuild the summary tables from results.csv
python tau_experiments/tau_experiment.py --summary
python tau_experiments/instr_experiment.py --summary

# test the scripts without any model (writes to a separate results file)
python tau_experiments/tau_experiment.py --pilot --llm fake --results /tmp/test_results.csv
```

Every run is a normal `run.py` run. The scripts register the tested variants through the `SEMOPS_VARIANTS` variable and pass `--tau`, `--instr` and `--inputs`. Each τ variant has its own gateway cache namespace, and the texts in `variants.py` are exactly those that were run, so **re-running anything already done is answered from the cache and costs nothing**. A new idea gets a new id in `variants.py`; existing texts must not be edited.

**To use the frozen version, nothing is needed:** `python run.py …` without `--tau` / `--instr` uses τ A and F0 / C0 / M0 / J5, and records `prompt_version: v1` in the run file.
