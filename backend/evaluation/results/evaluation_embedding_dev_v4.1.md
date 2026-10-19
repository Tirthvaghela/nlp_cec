# Evaluation report - split `dev`, backend `embedding`

DEV split (Q1-Q8). The engine's thresholds were fitted on these questions, so these numbers are in-sample; see results/v3_dev_experiments.json for leave-one-question-out estimates.

Engine 4.1.0 - model `sentence-transformers/all-MiniLM-L6-v2` - config `0c55a0ed63bf58c0` - 85 synthetic answers, 8 questions, max marks per question 3-5.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.535 | 0.975 | 12.5% | 57.6% | 69.4% | 82.4% | 0.817 | 0.774 |
| Baseline: keyword overlap (fitted on dev) | 0.812 | 1.111 | 18.9% | 27.1% | 52.9% | 76.5% | 0.749 | 0.711 |
| Baseline: holistic cosine (fitted on dev) | 1.235 | 1.530 | 28.7% | 21.2% | 36.5% | 47.1% | 0.406 | 0.362 |

Error distribution: 12 answers over-credited by more than 0.5, 14 under-credited by more than 0.5, 7 with |error| >= 2. Mean signed error -0.018.

## Concept-level agreement

338 concept decisions - accuracy 80.8%, credit vs no-credit accuracy 86.7%, linear-weighted kappa 0.713.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 94 | 9 | 18 |
| partial | 11 | 3 | 6 |
| missing | 8 | 13 | 176 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 4 | 0.500 |
| dense_correct | 7 | 0.786 |
| empty | 2 | 0.000 |
| incorrect | 7 | 0.571 |
| incorrect_swapped | 1 | 0.000 |
| irrelevant_long | 7 | 0.000 |
| keyword_list | 1 | 1.500 |
| negated | 4 | 0.625 |
| paraphrase | 8 | 0.750 |
| partial | 10 | 0.500 |
| repeated | 2 | 0.250 |
| short_correct_definition | 10 | 0.500 |
| single_concept | 7 | 0.143 |
| spelling | 8 | 0.562 |
| swapped | 1 | 0.500 |
| vague_short | 2 | 0.000 |
| wrong_with_keywords | 4 | 1.875 |

## MAE by question

| Question | MAE |
|---|---|
| Q1 | 0.333 |
| Q2 | 0.864 |
| Q3 | 0.150 |
| Q4 | 0.650 |
| Q5 | 0.550 |
| Q6 | 0.909 |
| Q7 | 0.350 |
| Q8 | 0.455 |

## Review flags

* Flagged for careful review: 55 answers, MAE 0.691
* Not flagged: 30 answers, MAE 0.250

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| negated | 4 | 4 |
| echo | 11 | 8 |
| misattributed | 5 | 4 |
| reversed_comparison | 2 | 2 |
| antonym | 1 | 1 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q2-d2 | wrong_with_keywords | 0 | 4.5 | borderline_concepts |
| Q6-a5 | spelling | 4 | 1 | borderline_concepts, divergent_signals, spelling_normalised |
| Q1-a6 | incorrect | 0 | 2 | borderline_concepts |
| Q4-a1 | paraphrase | 5 | 3 | borderline_concepts |
| Q5-a3 | partial | 2 | 0 | - |
| Q6-a1 | paraphrase | 4 | 2 | borderline_concepts, spelling_normalised |
| Q6-v1 | short_correct_definition | 2 | 0 | very_short_answer, divergent_signals |
| Q2-a3 | partial | 1.5 | 3 | borderline_concepts |
| Q2-a7 | keyword_list | 0 | 1.5 | keyword_list, borderline_concepts |
| Q3-d2 | negated | 0 | 1.5 | very_short_answer, possible_swap, possible_contradiction, borderline_concepts |
| Q4-a2 | abbreviations | 2.5 | 1 | borderline_concepts |
| Q4-d2 | wrong_with_keywords | 0 | 1.5 | possible_contradiction, borderline_concepts |
| Q4-v1 | dense_correct | 3 | 1.5 | borderline_concepts |
| Q6-d1 | short_correct_definition | 2 | 0.5 | borderline_concepts, divergent_signals |
| Q7-v1 | dense_correct | 3 | 1.5 | borderline_concepts |
| Q1-a1 | paraphrase | 4 | 3 | spelling_normalised |
| Q1-v1 | dense_correct | 4 | 3 | - |
| Q2-a5 | incorrect | 0 | 1 | borderline_concepts, divergent_signals |
| Q2-d1 | short_correct_definition | 1 | 2 | very_short_answer, borderline_concepts |
| Q5-a2 | partial | 1 | 2 | - |
| Q6-a3 | single_concept | 1 | 0 | divergent_signals |
| Q7-d2 | negated | 0 | 1 | - |
| Q8-a5 | incorrect | 0 | 1 | borderline_concepts |
| Q8-a7 | spelling | 3 | 2 | borderline_concepts, spelling_normalised |
| Q8-d2 | wrong_with_keywords | 0 | 1 | restates_question, possible_contradiction, borderline_concepts |
| Q8-v1 | dense_correct | 3 | 2 | - |
