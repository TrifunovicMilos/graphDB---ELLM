# Experiment 1: tau, dev sample (3B model, temperature 0)

| tau | Q1 F1 | Q2 F1 | Q4 macro-F1 | Q6 F1 (pairs accepted, 5 true) | mean of 4 | input tokens / call | parse failures |
|---|---|---|---|---|---|---|---|
| A | 0.797 | 0.829 | 0.770 | 0.100 (95) | 0.624 | 256 | 0 |
| B | 0.809 | 0.780 | 0.760 | 0.070 (136) | 0.605 | 265 | 0 |
| C | 0.800 | 0.794 | 0.780 | 0.040 (245) | 0.603 | 267 | 0 |
| C-900 | 0.800 | 0.780 | 0.780 | 0.040 (270) | 0.600 | 249 | 0 |
| C-600 | 0.787 | 0.785 | 0.800 | 0.050 (198) | 0.606 | 211 | 0 |

Rule fixed in advance: the best mean wins, unless its input tokens per call are more than 25% above the cheapest variant; differences under about 0.02-0.03 are ties.
Variants: variants.TAU_SPECS. Every run: results.csv (experiment = tau). Full outputs: logs/.
