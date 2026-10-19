# Evaluation report - backend `tfidf`

Model: `tfidf-char-ngrams` - engine 2.0.0 - config `1535dfb5b4351ef5` - dataset: 85 synthetic answers (57 dev / 28 test)

## Question-score agreement

| Split | System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|---|
| dev | AnswerWise engine | 0.675 | 1.078 | 15.8% | 43.9% | 63.2% | 84.2% | 0.795 | 0.778 |
| dev | Baseline: keyword overlap | 0.789 | 1.112 | 18.3% | 28.1% | 56.1% | 77.2% | 0.778 | 0.775 |
| dev | Baseline: holistic cosine | 0.982 | 1.294 | 22.8% | 21.1% | 45.6% | 68.4% | 0.682 | 0.681 |
| test | AnswerWise engine | 0.536 | 0.926 | 14.1% | 53.6% | 71.4% | 82.1% | 0.851 | 0.853 |
| test | Baseline: keyword overlap | 0.607 | 1.000 | 16.2% | 46.4% | 71.4% | 82.1% | 0.774 | 0.708 |
| test | Baseline: holistic cosine | 0.821 | 1.077 | 21.6% | 25.0% | 53.6% | 75.0% | 0.782 | 0.718 |
| all | AnswerWise engine | 0.629 | 1.030 | 15.3% | 47.1% | 65.9% | 83.5% | 0.801 | 0.798 |
| all | Baseline: keyword overlap | 0.729 | 1.076 | 17.6% | 34.1% | 61.2% | 78.8% | 0.778 | 0.762 |
| all | Baseline: holistic cosine | 0.929 | 1.227 | 22.4% | 22.4% | 48.2% | 70.6% | 0.698 | 0.697 |

## Concept-level agreement (matched / partial / missing)

| Split | Concepts | Accuracy | Credit vs no-credit accuracy | Linear weighted kappa |
|---|---|---|---|---|
| dev | 227 | 68.7% | 79.3% | 0.580 |
| test | 105 | 81.0% | 86.7% | 0.695 |
| all | 332 | 72.6% | 81.6% | 0.616 |

Test-split confusion matrix (rows = human label, columns = engine):

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 28 | 6 | 9 |
| partial | 0 | 0 | 0 |
| missing | 1 | 4 | 57 |

## MAE by answer type (all splits)

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 6 | 1.083 |
| empty | 3 | 0.000 |
| incorrect | 11 | 0.545 |
| incorrect_swapped | 1 | 3.000 |
| irrelevant_long | 11 | 0.136 |
| keyword_list | 2 | 1.750 |
| paraphrase | 12 | 1.375 |
| partial | 14 | 0.679 |
| repeated | 3 | 0.167 |
| single_concept | 11 | 0.227 |
| spelling | 11 | 0.364 |

## MAE by question

| Question | Split | MAE |
|---|---|---|
| Q1 | dev | 0.375 |
| Q10 | test | 0.571 |
| Q11 | test | 0.357 |
| Q12 | test | 0.429 |
| Q2 | dev | 1.143 |
| Q3 | dev | 0.929 |
| Q4 | dev | 0.714 |
| Q5 | dev | 0.500 |
| Q6 | dev | 0.500 |
| Q7 | dev | 0.357 |
| Q8 | dev | 0.929 |
| Q9 | test | 0.786 |

## Do review flags point at less reliable scores?

* Flagged for careful review: 85 answers, MAE 0.629
* Not flagged: 0 answers, MAE -

## Largest disagreements

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q2-a2 | partial | 1 | 4 | fallback_backend |
| Q3-a3 | incorrect_swapped | 0 | 3 | fallback_backend, borderline_concepts |
| Q4-a4 | incorrect | 0 | 3 | fallback_backend, borderline_concepts |
| Q9-a1 | paraphrase | 4 | 1 | fallback_backend, borderline_concepts |
| Q2-a7 | keyword_list | 0 | 2.5 | fallback_backend, keyword_list |
| Q6-a1 | paraphrase | 4 | 2 | fallback_backend, borderline_concepts, spelling_normalised |
| Q7-a1 | paraphrase | 3 | 1 | fallback_backend, borderline_concepts |
| Q8-a1 | paraphrase | 4 | 2 | fallback_backend, borderline_concepts |
| Q8-a4 | abbreviations | 4 | 2 | fallback_backend, borderline_concepts |
| Q11-a1 | paraphrase | 3 | 1 | fallback_backend, borderline_concepts, spelling_normalised |
| Q8-a7 | spelling | 3 | 1.5 | fallback_backend, borderline_concepts, spelling_normalised |
| Q9-a4 | spelling | 4 | 2.5 | fallback_backend, borderline_concepts, spelling_normalised |
| Q10-a1 | paraphrase | 4 | 2.5 | fallback_backend, borderline_concepts |
| Q12-a4 | abbreviations | 4 | 2.5 | fallback_backend, borderline_concepts |
| Q1-a2 | partial | 2 | 1 | fallback_backend, borderline_concepts |
| Q1-a5 | irrelevant_long | 0 | 1 | fallback_backend, borderline_concepts, spelling_normalised |
| Q2-a5 | incorrect | 0 | 1 | fallback_backend, borderline_concepts |
| Q3-a1 | paraphrase | 4 | 3 | fallback_backend, borderline_concepts |
| Q3-a2 | partial | 1 | 2 | fallback_backend, borderline_concepts |
| Q3-a4 | single_concept | 1 | 2 | fallback_backend, borderline_concepts |
| Q4-a1 | paraphrase | 5 | 4 | fallback_backend, borderline_concepts |
| Q4-a2 | abbreviations | 2.5 | 1.5 | fallback_backend, borderline_concepts |
| Q5-a1 | paraphrase | 5 | 4 | fallback_backend, borderline_concepts, spelling_normalised |
| Q5-a2 | partial | 1 | 2 | fallback_backend, borderline_concepts |
| Q5-a3 | partial | 2 | 1 | fallback_backend, borderline_concepts |
| Q8-a2 | partial | 1 | 0 | fallback_backend, borderline_concepts |
| Q9-a7 | keyword_list | 0 | 1 | fallback_backend, keyword_list, borderline_concepts |
| Q10-a4 | abbreviations | 4 | 3 | fallback_backend, borderline_concepts |
| Q10-a5 | incorrect | 0 | 1 | fallback_backend, borderline_concepts, spelling_normalised |
