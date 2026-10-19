# Evaluation report - split `dev`, backend `tfidf`

DEV split (Q1-Q8). The engine's thresholds were fitted on these questions, so these numbers are in-sample; see results/v3_dev_experiments.json for leave-one-question-out estimates.

Engine 3.0.0 - model `tfidf-char-ngrams` - config `61caf044528acbcf` - 74 synthetic answers, 8 questions, max marks per question 3-5.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.730 | 1.127 | 16.9% | 41.9% | 59.5% | 79.7% | 0.750 | 0.679 |
| Baseline: keyword overlap (fitted on dev) | 0.757 | 1.081 | 17.5% | 33.8% | 58.1% | 75.7% | 0.762 | 0.699 |
| Baseline: holistic cosine (fitted on dev) | 1.115 | 1.420 | 25.7% | 14.9% | 40.5% | 63.5% | 0.529 | 0.520 |

Error distribution: 18 answers over-credited by more than 0.5, 12 under-credited by more than 0.5, 11 with |error| >= 2. Mean signed error 0.189.

## Concept-level agreement

294 concept decisions - accuracy 69.4%, credit vs no-credit accuracy 77.2%, linear-weighted kappa 0.566.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 71 | 16 | 12 |
| partial | 7 | 1 | 7 |
| missing | 18 | 30 | 132 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 4 | 1.000 |
| empty | 2 | 0.000 |
| incorrect | 7 | 0.714 |
| incorrect_swapped | 1 | 2.500 |
| irrelevant_long | 7 | 0.143 |
| keyword_list | 1 | 2.500 |
| negated | 4 | 1.125 |
| paraphrase | 8 | 1.188 |
| partial | 10 | 1.000 |
| repeated | 2 | 0.000 |
| short_correct_definition | 8 | 0.250 |
| single_concept | 7 | 0.214 |
| spelling | 8 | 0.312 |
| swapped | 1 | 1.500 |
| vague_short | 1 | 1.000 |
| wrong_with_keywords | 3 | 2.167 |

## MAE by question

| Question | MAE |
|---|---|
| Q1 | 0.409 |
| Q2 | 1.389 |
| Q3 | 0.778 |
| Q4 | 0.778 |
| Q5 | 0.667 |
| Q6 | 0.667 |
| Q7 | 0.389 |
| Q8 | 0.833 |

## Review flags

* Flagged for careful review: 74 answers, MAE 0.730
* Not flagged: 0 answers, MAE -

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| negated | 6 | 5 |
| misattributed | 5 | 5 |
| reversed_comparison | 2 | 2 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q2-d2 | wrong_with_keywords | 0 | 3.5 | fallback_backend, borderline_concepts |
| Q2-a2 | partial | 1 | 4 | fallback_backend |
| Q4-a4 | incorrect | 0 | 3 | fallback_backend, borderline_concepts |
| Q2-a7 | keyword_list | 0 | 2.5 | fallback_backend, keyword_list |
| Q3-a3 | incorrect_swapped | 0 | 2.5 | fallback_backend, possible_swap, borderline_concepts |
| Q4-d2 | wrong_with_keywords | 0 | 2 | fallback_backend, borderline_concepts |
| Q5-a3 | partial | 2 | 0 | fallback_backend, possible_contradiction, borderline_concepts |
| Q6-a1 | paraphrase | 4 | 2 | fallback_backend, borderline_concepts, spelling_normalised |
| Q7-a1 | paraphrase | 3 | 1 | fallback_backend, borderline_concepts |
| Q8-a1 | paraphrase | 4 | 2 | fallback_backend, borderline_concepts |
| Q8-a4 | abbreviations | 4 | 2 | fallback_backend, borderline_concepts |
| Q3-d2 | negated | 0 | 1.5 | fallback_backend, very_short_answer, possible_swap, possible_contradiction |
| Q5-d2 | swapped | 0 | 1.5 | fallback_backend, possible_swap, borderline_concepts |
| Q6-d2 | negated | 0 | 1.5 | fallback_backend, possible_contradiction, borderline_concepts |
| Q8-a7 | spelling | 3 | 1.5 | fallback_backend, borderline_concepts, spelling_normalised |
| Q1-a2 | partial | 2 | 1 | fallback_backend, borderline_concepts |
| Q1-a5 | irrelevant_long | 0 | 1 | fallback_backend, borderline_concepts, spelling_normalised |
| Q1-d3 | vague_short | 0 | 1 | fallback_backend, very_short_answer |
| Q2-a5 | incorrect | 0 | 1 | fallback_backend, borderline_concepts |
| Q2-d1 | short_correct_definition | 1 | 2 | fallback_backend, very_short_answer |
| Q3-a1 | paraphrase | 4 | 3 | fallback_backend, borderline_concepts |
| Q3-a2 | partial | 1 | 2 | fallback_backend, borderline_concepts |
| Q4-a1 | paraphrase | 5 | 4 | fallback_backend, borderline_concepts |
| Q4-a2 | abbreviations | 2.5 | 1.5 | fallback_backend, borderline_concepts |
| Q5-a1 | paraphrase | 5 | 4 | fallback_backend, borderline_concepts, spelling_normalised |
| Q5-a2 | partial | 1 | 2 | fallback_backend, borderline_concepts |
| Q6-d1 | short_correct_definition | 2 | 3 | fallback_backend, borderline_concepts |
| Q7-d2 | negated | 0 | 1 | fallback_backend |
| Q8-a2 | partial | 1 | 0 | fallback_backend, borderline_concepts |
| Q8-d2 | wrong_with_keywords | 0 | 1 | fallback_backend, possible_contradiction, borderline_concepts |
