# Evaluation report - backend `embedding`

Model: `sentence-transformers/all-MiniLM-L6-v2` - engine 2.0.0 - config `610a2d9ef7acf98d` - dataset: 85 synthetic answers (57 dev / 28 test)

## Question-score agreement

| Split | System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|---|
| dev | AnswerWise engine | 0.544 | 1.030 | 12.4% | 61.4% | 71.9% | 82.5% | 0.818 | 0.796 |
| dev | Baseline: keyword overlap | 0.789 | 1.112 | 18.3% | 28.1% | 56.1% | 77.2% | 0.778 | 0.775 |
| dev | Baseline: holistic cosine | 1.289 | 1.555 | 30.0% | 15.8% | 29.8% | 47.4% | 0.479 | 0.477 |
| test | AnswerWise engine | 0.768 | 1.106 | 20.1% | 42.9% | 46.4% | 75.0% | 0.771 | 0.768 |
| test | Baseline: keyword overlap | 0.607 | 1.000 | 16.2% | 46.4% | 71.4% | 82.1% | 0.774 | 0.708 |
| test | Baseline: holistic cosine | 1.071 | 1.336 | 28.4% | 21.4% | 42.9% | 53.6% | 0.551 | 0.521 |
| all | AnswerWise engine | 0.618 | 1.056 | 15.0% | 55.3% | 63.5% | 80.0% | 0.795 | 0.785 |
| all | Baseline: keyword overlap | 0.729 | 1.076 | 17.6% | 34.1% | 61.2% | 78.8% | 0.778 | 0.762 |
| all | Baseline: holistic cosine | 1.218 | 1.486 | 29.5% | 17.6% | 34.1% | 49.4% | 0.496 | 0.493 |

## Concept-level agreement (matched / partial / missing)

| Split | Concepts | Accuracy | Credit vs no-credit accuracy | Linear weighted kappa |
|---|---|---|---|---|
| dev | 227 | 81.1% | 88.1% | 0.722 |
| test | 105 | 75.2% | 79.0% | 0.557 |
| all | 332 | 79.2% | 85.2% | 0.672 |

Test-split confusion matrix (rows = human label, columns = engine):

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 24 | 4 | 15 |
| partial | 0 | 0 | 0 |
| missing | 2 | 5 | 55 |

## MAE by answer type (all splits)

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 6 | 0.917 |
| empty | 3 | 0.000 |
| incorrect | 11 | 0.500 |
| incorrect_swapped | 1 | 3.500 |
| irrelevant_long | 11 | 0.000 |
| keyword_list | 2 | 1.000 |
| paraphrase | 12 | 1.125 |
| partial | 14 | 0.821 |
| repeated | 3 | 0.500 |
| single_concept | 11 | 0.273 |
| spelling | 11 | 0.591 |

## MAE by question

| Question | Split | MAE |
|---|---|---|
| Q1 | dev | 0.375 |
| Q10 | test | 1.214 |
| Q11 | test | 0.429 |
| Q12 | test | 0.786 |
| Q2 | dev | 1.000 |
| Q3 | dev | 0.500 |
| Q4 | dev | 0.500 |
| Q5 | dev | 0.643 |
| Q6 | dev | 0.857 |
| Q7 | dev | 0.143 |
| Q8 | dev | 0.357 |
| Q9 | test | 0.643 |

## Do review flags point at less reliable scores?

* Flagged for careful review: 46 answers, MAE 0.870
* Not flagged: 39 answers, MAE 0.321

## Largest disagreements

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q3-a3 | incorrect_swapped | 0 | 3.5 | borderline_concepts |
| Q2-a2 | partial | 1 | 4 | - |
| Q6-a5 | spelling | 4 | 1 | borderline_concepts, divergent_signals, spelling_normalised |
| Q10-a1 | paraphrase | 4 | 1 | borderline_concepts, divergent_signals |
| Q1-a6 | incorrect | 0 | 2 | borderline_concepts |
| Q4-a1 | paraphrase | 5 | 3 | borderline_concepts |
| Q5-a3 | partial | 2 | 0 | - |
| Q6-a1 | paraphrase | 4 | 2 | borderline_concepts, spelling_normalised |
| Q9-a1 | paraphrase | 4 | 2 | borderline_concepts |
| Q12-a4 | abbreviations | 4 | 2 | borderline_concepts |
| Q2-a3 | partial | 1.5 | 3 | borderline_concepts |
| Q2-a7 | keyword_list | 0 | 1.5 | keyword_list, borderline_concepts |
| Q4-a2 | abbreviations | 2.5 | 1 | borderline_concepts |
| Q10-a2 | partial | 1 | 2.5 | borderline_concepts |
| Q10-a4 | abbreviations | 4 | 2.5 | borderline_concepts |
| Q10-a5 | incorrect | 0 | 1.5 | borderline_concepts, spelling_normalised |
| Q12-a1 | paraphrase | 4 | 2.5 | borderline_concepts |
| Q1-a1 | paraphrase | 4 | 3 | spelling_normalised |
| Q2-a5 | incorrect | 0 | 1 | borderline_concepts, divergent_signals |
| Q5-a2 | partial | 1 | 2 | - |
| Q6-a3 | single_concept | 1 | 0 | divergent_signals |
| Q8-a5 | incorrect | 0 | 1 | borderline_concepts |
| Q8-a7 | spelling | 3 | 2 | borderline_concepts, spelling_normalised |
| Q9-a3 | single_concept | 1 | 0 | borderline_concepts |
| Q9-a4 | spelling | 4 | 3 | spelling_normalised |
| Q10-a7 | spelling | 3 | 2 | spelling_normalised |
| Q11-a1 | paraphrase | 3 | 2 | spelling_normalised |
| Q11-a2 | partial | 1 | 2 | very_short_answer, borderline_concepts |
| Q11-a3 | single_concept | 1 | 0 | very_short_answer |
| Q12-a2 | partial | 1 | 0 | - |
| Q12-a6 | repeated | 2 | 1 | repeated_content, borderline_concepts |
