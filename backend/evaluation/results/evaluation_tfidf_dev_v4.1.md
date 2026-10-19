# Evaluation report - split `dev`, backend `tfidf`

DEV split (Q1-Q8). The engine's thresholds were fitted on these questions, so these numbers are in-sample; see results/v3_dev_experiments.json for leave-one-question-out estimates.

Engine 4.1.0 - model `tfidf-char-ngrams` - config `2626d5180964efdc` - 85 synthetic answers, 8 questions, max marks per question 3-5.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.647 | 1.006 | 15.1% | 44.7% | 62.4% | 81.2% | 0.802 | 0.744 |
| Baseline: keyword overlap (fitted on dev) | 0.812 | 1.111 | 18.9% | 27.1% | 52.9% | 76.5% | 0.749 | 0.711 |
| Baseline: holistic cosine (fitted on dev) | 1.171 | 1.450 | 27.0% | 11.8% | 37.6% | 58.8% | 0.505 | 0.490 |

Error distribution: 17 answers over-credited by more than 0.5, 15 under-credited by more than 0.5, 9 with |error| >= 2. Mean signed error 0.094.

## Concept-level agreement

338 concept decisions - accuracy 71.6%, credit vs no-credit accuracy 79.9%, linear-weighted kappa 0.605.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 88 | 18 | 15 |
| partial | 10 | 2 | 8 |
| missing | 16 | 29 | 152 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 4 | 1.000 |
| dense_correct | 7 | 0.500 |
| empty | 2 | 0.000 |
| incorrect | 7 | 0.714 |
| incorrect_swapped | 1 | 1.500 |
| irrelevant_long | 7 | 0.143 |
| keyword_list | 1 | 2.500 |
| negated | 4 | 1.125 |
| paraphrase | 8 | 1.188 |
| partial | 10 | 1.000 |
| repeated | 2 | 0.000 |
| short_correct_definition | 10 | 0.300 |
| single_concept | 7 | 0.071 |
| spelling | 8 | 0.312 |
| swapped | 1 | 1.500 |
| vague_short | 2 | 0.000 |
| wrong_with_keywords | 4 | 1.500 |

## MAE by question

| Question | MAE |
|---|---|
| Q1 | 0.333 |
| Q2 | 1.045 |
| Q3 | 0.550 |
| Q4 | 0.700 |
| Q5 | 0.650 |
| Q6 | 0.727 |
| Q7 | 0.450 |
| Q8 | 0.727 |

## Review flags

* Flagged for careful review: 85 answers, MAE 0.647
* Not flagged: 0 answers, MAE -

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| negated | 6 | 5 |
| echo | 13 | 9 |
| antonym | 2 | 2 |
| misattributed | 5 | 5 |
| reversed_comparison | 2 | 2 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q2-a2 | partial | 1 | 4 | fallback_backend |
| Q4-a4 | incorrect | 0 | 3 | fallback_backend, borderline_concepts |
| Q2-a7 | keyword_list | 0 | 2.5 | fallback_backend, keyword_list |
| Q2-d2 | wrong_with_keywords | 0 | 2.5 | fallback_backend, possible_contradiction, borderline_concepts |
| Q5-a3 | partial | 2 | 0 | fallback_backend, possible_contradiction, borderline_concepts |
| Q6-a1 | paraphrase | 4 | 2 | fallback_backend, borderline_concepts, spelling_normalised |
| Q7-a1 | paraphrase | 3 | 1 | fallback_backend, borderline_concepts |
| Q8-a1 | paraphrase | 4 | 2 | fallback_backend, borderline_concepts |
| Q8-a4 | abbreviations | 4 | 2 | fallback_backend, borderline_concepts |
| Q3-a3 | incorrect_swapped | 0 | 1.5 | fallback_backend, possible_swap, restates_question, borderline_concepts |
| Q3-d2 | negated | 0 | 1.5 | fallback_backend, very_short_answer, possible_swap, possible_contradiction |
| Q4-d2 | wrong_with_keywords | 0 | 1.5 | fallback_backend, possible_contradiction, borderline_concepts |
| Q5-d2 | swapped | 0 | 1.5 | fallback_backend, possible_swap, borderline_concepts |
| Q6-d2 | negated | 0 | 1.5 | fallback_backend, possible_contradiction, borderline_concepts |
| Q6-v2 | wrong_with_keywords | 0 | 1.5 | fallback_backend, borderline_concepts |
| Q8-a7 | spelling | 3 | 1.5 | fallback_backend, borderline_concepts, spelling_normalised |
| Q1-a2 | partial | 2 | 1 | fallback_backend, borderline_concepts |
| Q1-a5 | irrelevant_long | 0 | 1 | fallback_backend, borderline_concepts, spelling_normalised |
| Q2-a5 | incorrect | 0 | 1 | fallback_backend, borderline_concepts |
| Q2-d1 | short_correct_definition | 1 | 2 | fallback_backend, very_short_answer |
| Q3-a1 | paraphrase | 4 | 3 | fallback_backend, borderline_concepts |
| Q3-a2 | partial | 1 | 2 | fallback_backend, borderline_concepts |
| Q4-a1 | paraphrase | 5 | 4 | fallback_backend, borderline_concepts |
| Q4-a2 | abbreviations | 2.5 | 1.5 | fallback_backend, borderline_concepts |
| Q5-a1 | paraphrase | 5 | 4 | fallback_backend, borderline_concepts, spelling_normalised |
| Q5-a2 | partial | 1 | 2 | fallback_backend, borderline_concepts |
| Q6-d1 | short_correct_definition | 2 | 3 | fallback_backend, borderline_concepts |
| Q6-v1 | short_correct_definition | 2 | 1 | fallback_backend, very_short_answer, borderline_concepts |
| Q7-d2 | negated | 0 | 1 | fallback_backend |
| Q7-v1 | dense_correct | 3 | 2 | fallback_backend |
| Q8-a2 | partial | 1 | 0 | fallback_backend, borderline_concepts |
| Q8-v1 | dense_correct | 3 | 2 | fallback_backend |
