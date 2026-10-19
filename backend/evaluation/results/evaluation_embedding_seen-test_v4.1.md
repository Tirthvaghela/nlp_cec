# Evaluation report - split `seen-test`, backend `embedding`

Q9-Q12. Held out for engine v2, but their per-answer errors were inspected afterwards, so they are NOT an independent test of engine v3.

Engine 4.1.0 - model `sentence-transformers/all-MiniLM-L6-v2` - config `0c55a0ed63bf58c0` - 28 synthetic answers, 4 questions, max marks per question 3-4.

## Question-score agreement

| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|
| AnswerWise engine | 0.786 | 1.102 | 20.5% | 39.3% | 42.9% | 78.6% | 0.787 | 0.769 |
| Baseline: keyword overlap (fitted on dev) | 0.607 | 0.982 | 16.4% | 42.9% | 71.4% | 85.7% | 0.792 | 0.735 |
| Baseline: holistic cosine (fitted on dev) | 1.071 | 1.369 | 28.3% | 21.4% | 46.4% | 57.1% | 0.550 | 0.537 |

Error distribution: 3 answers over-credited by more than 0.5, 13 under-credited by more than 0.5, 3 with |error| >= 2. Mean signed error -0.500.

## Concept-level agreement

105 concept decisions - accuracy 75.2%, credit vs no-credit accuracy 79.0%, linear-weighted kappa 0.544.

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 23 | 4 | 16 |
| partial | 0 | 0 | 0 |
| missing | 2 | 4 | 56 |

## MAE by answer type

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 2 | 1.750 |
| empty | 1 | 0.000 |
| incorrect | 4 | 0.250 |
| irrelevant_long | 4 | 0.000 |
| keyword_list | 1 | 0.500 |
| paraphrase | 4 | 1.875 |
| partial | 4 | 0.875 |
| repeated | 1 | 1.000 |
| single_concept | 4 | 0.750 |
| spelling | 3 | 0.667 |

## MAE by question

| Question | MAE |
|---|---|
| Q9 | 0.643 |
| Q10 | 1.286 |
| Q11 | 0.429 |
| Q12 | 0.786 |

## Review flags

* Flagged for careful review: 13 answers, MAE 1.308
* Not flagged: 15 answers, MAE 0.333

## Correctness safeguards (v3)

| Safeguard | Fired | ...on concepts the human marked missing |
|---|---|---|
| misattributed | 1 | 0 |
| negated | 1 | 1 |

## Largest disagreements (|error| >= 1)

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q10-a1 | paraphrase | 4 | 1 | borderline_concepts, divergent_signals |
| Q9-a1 | paraphrase | 4 | 2 | borderline_concepts |
| Q12-a4 | abbreviations | 4 | 2 | borderline_concepts |
| Q10-a2 | partial | 1 | 2.5 | borderline_concepts |
| Q10-a4 | abbreviations | 4 | 2.5 | borderline_concepts |
| Q12-a1 | paraphrase | 4 | 2.5 | borderline_concepts |
| Q9-a3 | single_concept | 1 | 0 | borderline_concepts |
| Q9-a4 | spelling | 4 | 3 | spelling_normalised |
| Q10-a3 | single_concept | 1 | 0 | very_short_answer, possible_swap |
| Q10-a5 | incorrect | 0 | 1 | possible_contradiction, borderline_concepts, divergent_signals, spelling_normalised |
| Q10-a7 | spelling | 3 | 2 | spelling_normalised |
| Q11-a1 | paraphrase | 3 | 2 | spelling_normalised |
| Q11-a2 | partial | 1 | 2 | very_short_answer, borderline_concepts |
| Q11-a3 | single_concept | 1 | 0 | very_short_answer |
| Q12-a2 | partial | 1 | 0 | - |
| Q12-a6 | repeated | 2 | 1 | repeated_content, borderline_concepts |
