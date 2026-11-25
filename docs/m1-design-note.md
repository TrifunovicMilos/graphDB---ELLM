# M1 design note

**LLME · Graph Databases 2026/27 · Video games and series · Oxigraph**

This design note records the system implemented in the project branch and the proposed O1 configuration. The evidence below is from development runs. The operating points are for team review before evaluation.

## Problem and operator definitions

The project evaluates semantic operators over an RDF graph of video games and series. SPARQL selects and combines graph bindings. The semantic operator evaluates a fixed natural-language criterion on a text representation of each binding.

- **Semantic filter.** Keep games whose text satisfies the criterion, for example “the game is a platformer” in Q1.
- **Semantic classification.** Assign one label from a closed vocabulary, for example one of the eight game genres in Q4. Record failures separately.
- **Semantic join.** Keep game–series pairs whose two texts satisfy the membership criterion in Q6.
- **Semantic mapping.** Extract a free-text developer name in Q5 and resolve it through the provided label and alias index.

Q2 filters for visual novels. Q3 adds a structural restriction to the Q1 criterion by selecting games developed by a company based in Japan. Q8 counts the accepted Q1 results by first-release decade and reuses those decisions without model calls. The common Q7 large join is the optional bonus query.

## Data, representation and system

Both course splits load with Oxigraph. The source RDF has **52,313 triples and 1,000 main-set games in dev** and **147,987 triples and 4,000 main-set games in eval**. The loader uses the public `graph.nt` files. Hidden statements are reserved for the answer keys.

Prompt version **v1** freezes τ variant **A** as the entity label plus its English Wikipedia lead, truncated to 1,200 characters. The loader materializes this text as `ex:tau`. The prompt supplies the query’s fixed criterion, the text and the operator’s JSON response schema. The frozen instructions are **F0** for filtering, **C0** for classification, **M0** for mapping and **J5** for joining. The [development experiments](../tau_experiments/README.md) record the variants considered.

Oxigraph invokes a Python extension function for each semantic operation. The function submits a structured request to the course gateway, which validates the model response and records usage, costs and cache status. For the end-to-end evidence, [Q1 dev reference](../runs/games/dev/Q1/g00-dev-q1-ref.json) processed all 1,000 games through Oxigraph, the gateway and Gemini 3.5 Flash-Lite. It accepted 212 games with zero parse failures. The course checker accepted the file and reported **F1 0.859** against the expanded answer key, **231,029 input tokens**, **5,000 output tokens** and **USD 0.0818**. The file uses the provisional group ID `g00`.

## Optimization and budget

**O1 is the proposed optimization for the filter queries.** A local Qwen 2.5 3B proxy scores each binding using boolean token log-probabilities. Scores at or below the lower threshold reject the binding, and scores at or above the upper threshold accept it. For scores in the middle or missing scores, the cascade backend calls the Flash-Lite oracle through the gateway. Calibrate the thresholds on dev against the oracle’s decisions. Freeze the selected thresholds before eval.

| Target F1 vs. reference | Routed to oracle on dev | F1 vs. reference | F1 vs. answer key | Estimated oracle cost |
| --- | ---: | ---: | ---: | ---: |
| 0.90 | 57 / 1,000 | 0.900 | 0.820 | USD 0.0047 |
| 0.96 | 168 / 1,000 | 0.961 | 0.849 | USD 0.0137 |
| 0.99 | 629 / 1,000 | 0.990 | 0.858 | USD 0.0515 |

The table comes from [Q1 development calibration](../o1_cascade/calibration_dev_q1.md). It estimates oracle spend from the development reference and routing volume. The 0.96 point is the proposed default because it preserves most of the reference agreement while routing 16.8% of inputs to the oracle. Reserve cloud calls for reference and evaluation runs. Size the join and pool runs against the course budget with observed tokens per call, and count cache hits separately from new model calls. The group’s cloud allowance and final operating points still need confirmation.

For the [reproduction steps](reproduce.md), start with the cached calibration evidence and checker. The evaluation runs and final cost–quality frontier remain open.
