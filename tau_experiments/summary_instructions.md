# Experiment 2: instructions, tau A (3B model, temperature 0)

## Sample: Q1 400 games, Q2 30 + 270, Q6 games 1-5 x 100 series

| filter | Q1 F1 | Q2 F1 | mean | input tokens / call | parse failures |
|---|---|---|---|---|---|
| F0 | 0.797 (P 0.85 R 0.75) | 0.829 (P 0.96 R 0.73) | 0.813 | 203 | 0 |
| F1 | 0.787 (P 0.84 R 0.74) | 0.844 (P 1.00 R 0.73) | 0.815 | 214 | 0 |
| F2 | 0.771 (P 0.83 R 0.72) | 0.814 (P 0.92 R 0.73) | 0.793 | 236 | 0 |
| F3 | 0.805 (P 0.80 R 0.81) | 0.711 (P 0.66 R 0.77) | 0.758 | 222 | 0 |
| F4 | 0.761 (P 0.88 R 0.67) | 0.806 (P 0.95 R 0.70) | 0.783 | 202 | 0 |
| F5 | 0.771 (P 0.83 R 0.72) | 0.791 (P 0.91 R 0.70) | 0.781 | 183 | 0 |

| join | Q6 F1 | input tokens / call | parse failures |
|---|---|---|---|
| J0 | 0.100 (P 0.05 R 1.00), 95 accepted | 374 | 0 |
| J1 | 0.350 (P 0.22 R 0.80), 18 accepted | 419 | 0 |
| J2 | 0.000 (P 0.00 R 0.00), 1 accepted | 507 | 0 |
| J3 | 0.190 (P 0.10 R 1.00), 49 accepted | 383 | 0 |
| J4 | 0.560 (P 0.38 R 1.00), 13 accepted | 430 | 0 |
| J5 | 0.670 (P 0.50 R 1.00), 10 accepted | 394 | 0 |

## Holdout: Q1 the other 600 games, Q6 games 6-10 x 100 series

| filter | Q1 F1 | Q2 F1 | mean | input tokens / call | parse failures |
|---|---|---|---|---|---|
| F0 | 0.743 (P 0.82 R 0.68) | - | 0.743 | 199 | 0 |
| F1 | 0.754 (P 0.83 R 0.69) | - | 0.754 | 210 | 0 |

| join | Q6 F1 | input tokens / call | parse failures |
|---|---|---|---|
| J0 | 0.240 (P 0.14 R 1.00), 36 accepted | 429 | 0 |
| J1 | 0.670 (P 0.50 R 1.00), 10 accepted | 474 | 0 |
| J5 | 0.830 (P 0.71 R 1.00), 7 accepted | 449 | 0 |

## Sample and holdout pooled

| query | instructions | answers | precision | recall | F1 |
|---|---|---|---|---|---|
| Q1 over all 1,000 dev games | F0 | 142 of 171 found correct | 0.83 | 0.71 | 0.765 |
| Q1 over all 1,000 dev games | F1 | 142 of 170 found correct | 0.84 | 0.71 | 0.768 |
| Q6 over 10 games x 100 series (10 true pairs) | J0 | 10 of 131 found correct | 0.08 | 1.00 | 0.142 |
| Q6 over 10 games x 100 series (10 true pairs) | J1 | 9 of 28 found correct | 0.32 | 0.90 | 0.474 |
| Q6 over 10 games x 100 series (10 true pairs) | J5 | 10 of 17 found correct | 0.59 | 1.00 | 0.741 |

Rule fixed in advance, per operator: the best mean F1 wins unless its input tokens per call are more than 25% above the original; differences under about 0.02-0.03 are ties and a tie keeps the original; the winner must hold on the holdout.
Texts: variants.py (and semops/prompts.py for the frozen ones). Every run: results.csv (experiment = instructions). Full outputs: logs/.
