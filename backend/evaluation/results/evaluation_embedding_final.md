# Evaluation report - split `final`, backend `embedding`

v3 FINAL held-out set (Q13-Q18, final_test.json), written and labelled before v3 development, integrity-checked by SHA-256, evaluated once after the configuration was frozen.

Engine 3.0.0 - model `sentence-transformers/all-MiniLM-L6-v2` - config `c5f68ec927d78a4d` - 48 synthetic answers, 6 questions, max marks per question 3-4.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.594 | 0.938 | 16.1% | 50.0% | 60.4% | 85.4% | 0.790 | 0.747 |
| Baseline: keyword overlap (fitted on dev) | 0.917 | 1.299 | 24.7% | 35.4% | 52.1% | 66.7% | 0.592 | 0.510 |
| Baseline: holistic cosine (fitted on dev) | 1.188 | 1.392 | 32.7% | 10.4% | 35.4% | 45.8% | 0.412 | 0.417 |

Error distribution: 11 answers over-credited by more than 0.5, 8 under-credited by more than 0.5, 5 with |error| >= 2. Mean signed error 0.073.

## Concept-level agreement

176 concept decisions - accuracy 77.8%, credit vs no-credit accuracy 81.2%, linear-weighted kappa 0.629.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 47 | 3 | 11 |
| partial | 3 | 1 | 2 |
| missing | 11 | 9 | 89 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 3 | 1.167 |
| empty | 1 | 0.000 |
| irrelevant_long | 5 | 0.000 |
| keyword_list | 2 | 0.500 |
| negated | 5 | 0.800 |
| paraphrase | 6 | 0.917 |
| partial | 2 | 0.750 |
| repeated | 1 | 0.000 |
| short_correct_definition | 6 | 0.250 |
| single_concept | 1 | 0.000 |
| spelling | 4 | 0.375 |
| swapped | 3 | 1.833 |
| vague_short | 4 | 0.000 |
| wrong_with_keywords | 5 | 0.900 |

## MAE by question

| Question | MAE |
|---|---|
| Q13 | 0.562 |
| Q14 | 0.562 |
| Q15 | 0.625 |
| Q16 | 0.750 |
| Q17 | 0.312 |
| Q18 | 0.750 |

## Review flags

* Flagged for careful review: 30 answers, MAE 0.817
* Not flagged: 18 answers, MAE 0.222

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| negated | 4 | 4 |
| misattributed | 5 | 4 |
| reversed_comparison | 1 | 1 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q16-a6 | abbreviations | 4 | 1.5 | borderline_concepts |
| Q18-a3 | swapped | 0 | 2.5 | possible_swap, borderline_concepts |
| Q13-a4 | wrong_with_keywords | 0 | 2 | - |
| Q14-a1 | paraphrase | 3 | 1 | borderline_concepts |
| Q15-a3 | swapped | 0 | 2 | possible_swap |
| Q13-a5 | negated | 0 | 1.5 | possible_contradiction |
| Q14-a4 | wrong_with_keywords | 0 | 1.5 | borderline_concepts |
| Q13-a7 | keyword_list | 0 | 1 | keyword_list, borderline_concepts, divergent_signals |
| Q14-a6 | abbreviations | 3 | 2 | - |
| Q15-a1 | paraphrase | 4 | 3 | borderline_concepts |
| Q15-a2 | short_correct_definition | 1.5 | 0.5 | keyword_list, borderline_concepts, divergent_signals |
| Q15-a5 | spelling | 4 | 3 | spelling_normalised |
| Q16-a1 | paraphrase | 4 | 3 | possible_swap |
| Q16-a4 | negated | 0 | 1 | possible_swap, borderline_concepts |
| Q16-a7 | wrong_with_keywords | 0 | 1 | borderline_concepts, divergent_signals |
| Q17-a3 | swapped | 2 | 3 | borderline_concepts |
| Q18-a1 | paraphrase | 4 | 3 | borderline_concepts |
| Q18-a4 | negated | 0 | 1 | possible_contradiction, borderline_concepts |
| Q18-a6 | partial | 1 | 2 | very_short_answer |
