# Evaluation report - split `v4_fresh`, backend `embedding`

v4 FRESH held-out set (R1-R8, v4_fresh_test.json): 8 new questions x 8 fixed answer types, written and labelled before any v4 change, integrity-checked by SHA-256, evaluated once after v4 was frozen. Synthetic; written and marked by the engine developer.

Engine 4.0.0 - model `sentence-transformers/all-MiniLM-L6-v2` - config `1ac0c0c62643e69f` - 64 synthetic answers, 8 questions, max marks per question 3-4.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.547 | 0.931 | 14.8% | 45.3% | 73.4% | 87.5% | 0.806 | 0.783 |
| Baseline: keyword overlap (fitted on dev) | 0.961 | 1.382 | 25.2% | 26.6% | 50.0% | 75.0% | 0.598 | 0.574 |
| Baseline: holistic cosine (fitted on dev) | 1.305 | 1.472 | 34.4% | 6.2% | 25.0% | 43.8% | 0.364 | 0.392 |

Error distribution: 6 answers over-credited by more than 0.5, 11 under-credited by more than 0.5, 4 with |error| >= 2. Mean signed error -0.109.

## Concept-level agreement

240 concept decisions - accuracy 77.5%, credit vs no-credit accuracy 84.2%, linear-weighted kappa 0.652.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 56 | 7 | 16 |
| partial | 9 | 5 | 6 |
| missing | 6 | 10 | 125 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 2 | 0.500 |
| dense_correct | 8 | 1.000 |
| irrelevant_long | 2 | 0.000 |
| keyword_list | 2 | 0.250 |
| negated | 5 | 0.300 |
| paraphrase | 8 | 1.125 |
| partial | 8 | 0.562 |
| short_correct_definition | 8 | 0.125 |
| spelling | 2 | 1.000 |
| swapped | 3 | 0.667 |
| vague_short | 8 | 0.000 |
| wrong_with_keywords | 8 | 0.688 |

## MAE by question

| Question | MAE |
|---|---|
| R1 | 0.562 |
| R2 | 0.500 |
| R3 | 0.250 |
| R4 | 0.500 |
| R5 | 1.062 |
| R6 | 0.312 |
| R7 | 0.625 |
| R8 | 0.562 |

## Review flags

* Flagged for careful review: 49 answers, MAE 0.612
* Not flagged: 15 answers, MAE 0.333

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| echo | 3 | 1 |
| negated | 6 | 6 |
| misattributed | 6 | 6 |
| antonym | 1 | 1 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| R5-a3 | dense_correct | 4 | 0 | borderline_concepts |
| R5-a1 | paraphrase | 4 | 1 | divergent_signals |
| R1-a7 | swapped | 0 | 2 | spelling_normalised |
| R8-a1 | paraphrase | 3 | 1 | borderline_concepts |
| R2-a8 | spelling | 4 | 2.5 | borderline_concepts, spelling_normalised |
| R3-a4 | partial | 1.5 | 3 | borderline_concepts |
| R7-a1 | paraphrase | 4 | 2.5 | borderline_concepts |
| R8-a6 | wrong_with_keywords | 0 | 1.5 | possible_contradiction, borderline_concepts |
| R1-a6 | wrong_with_keywords | 0 | 1 | borderline_concepts, divergent_signals |
| R2-a4 | partial | 1 | 0 | divergent_signals |
| R4-a1 | paraphrase | 3 | 2 | borderline_concepts |
| R4-a6 | wrong_with_keywords | 0 | 1 | borderline_concepts |
| R5-a4 | partial | 1 | 0 | - |
| R6-a1 | paraphrase | 4 | 3 | borderline_concepts |
| R7-a3 | dense_correct | 3.5 | 2.5 | borderline_concepts |
| R7-a6 | wrong_with_keywords | 0 | 1 | borderline_concepts, divergent_signals |
| R7-a8 | abbreviations | 4 | 3 | - |
