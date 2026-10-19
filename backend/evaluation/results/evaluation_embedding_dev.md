# Evaluation report - split `dev`, backend `embedding`

DEV split (Q1-Q8). The engine's thresholds were fitted on these questions, so these numbers are in-sample; see results/v3_dev_experiments.json for leave-one-question-out estimates.

Engine 3.0.0 - model `sentence-transformers/all-MiniLM-L6-v2` - config `c5f68ec927d78a4d` - 74 synthetic answers, 8 questions, max marks per question 3-5.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.547 | 1.041 | 12.4% | 60.8% | 70.3% | 82.4% | 0.792 | 0.748 |
| Baseline: keyword overlap (fitted on dev) | 0.757 | 1.081 | 17.5% | 33.8% | 58.1% | 75.7% | 0.762 | 0.699 |
| Baseline: holistic cosine (fitted on dev) | 1.203 | 1.500 | 27.8% | 18.9% | 39.2% | 51.4% | 0.437 | 0.412 |

Error distribution: 13 answers over-credited by more than 0.5, 9 under-credited by more than 0.5, 8 with |error| >= 2. Mean signed error 0.101.

## Concept-level agreement

294 concept decisions - accuracy 81.6%, credit vs no-credit accuracy 87.4%, linear-weighted kappa 0.717.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 79 | 8 | 12 |
| partial | 9 | 2 | 4 |
| missing | 11 | 10 | 159 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 4 | 0.500 |
| empty | 2 | 0.000 |
| incorrect | 7 | 0.571 |
| incorrect_swapped | 1 | 0.000 |
| irrelevant_long | 7 | 0.000 |
| keyword_list | 1 | 1.500 |
| negated | 4 | 0.625 |
| paraphrase | 8 | 0.750 |
| partial | 10 | 0.800 |
| repeated | 2 | 0.250 |
| short_correct_definition | 8 | 0.312 |
| single_concept | 7 | 0.143 |
| spelling | 8 | 0.562 |
| swapped | 1 | 0.500 |
| vague_short | 1 | 0.000 |
| wrong_with_keywords | 3 | 2.500 |

## MAE by question

| Question | MAE |
|---|---|
| Q1 | 0.273 |
| Q2 | 1.389 |
| Q3 | 0.167 |
| Q4 | 0.611 |
| Q5 | 0.556 |
| Q6 | 0.833 |
| Q7 | 0.222 |
| Q8 | 0.389 |

## Review flags

* Flagged for careful review: 46 answers, MAE 0.696
* Not flagged: 28 answers, MAE 0.304

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| negated | 3 | 3 |
| misattributed | 6 | 5 |
| reversed_comparison | 2 | 2 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q2-d2 | wrong_with_keywords | 0 | 4.5 | borderline_concepts |
| Q2-a2 | partial | 1 | 4 | - |
| Q6-a5 | spelling | 4 | 1 | borderline_concepts, divergent_signals, spelling_normalised |
| Q1-a6 | incorrect | 0 | 2 | borderline_concepts |
| Q4-a1 | paraphrase | 5 | 3 | borderline_concepts |
| Q4-d2 | wrong_with_keywords | 0 | 2 | borderline_concepts |
| Q5-a3 | partial | 2 | 0 | - |
| Q6-a1 | paraphrase | 4 | 2 | borderline_concepts, spelling_normalised |
| Q2-a3 | partial | 1.5 | 3 | borderline_concepts |
| Q2-a7 | keyword_list | 0 | 1.5 | keyword_list, borderline_concepts |
| Q3-d2 | negated | 0 | 1.5 | very_short_answer, possible_swap, possible_contradiction, borderline_concepts |
| Q4-a2 | abbreviations | 2.5 | 1 | borderline_concepts |
| Q6-d1 | short_correct_definition | 2 | 0.5 | borderline_concepts, divergent_signals |
| Q1-a1 | paraphrase | 4 | 3 | spelling_normalised |
| Q2-a5 | incorrect | 0 | 1 | borderline_concepts, divergent_signals |
| Q2-d1 | short_correct_definition | 1 | 2 | very_short_answer, borderline_concepts |
| Q5-a2 | partial | 1 | 2 | - |
| Q6-a3 | single_concept | 1 | 0 | divergent_signals |
| Q7-d2 | negated | 0 | 1 | - |
| Q8-a5 | incorrect | 0 | 1 | borderline_concepts |
| Q8-a7 | spelling | 3 | 2 | borderline_concepts, spelling_normalised |
| Q8-d2 | wrong_with_keywords | 0 | 1 | possible_contradiction, borderline_concepts |
