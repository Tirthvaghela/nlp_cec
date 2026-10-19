# Evaluation report - backend `embedding`

Model: `sentence-transformers/all-MiniLM-L6-v2` - engine 1.0.0 - config `0bd1f02a04ecdb57` - dataset: 57 synthetic answers (29 dev / 28 test)

## Question-score agreement

| Split | System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|---|
| dev | AnswerWise engine | 0.466 | 0.725 | 10.2% | 51.7% | 65.5% | 93.1% | 0.920 | 0.880 |
| dev | Baseline: keyword overlap | 0.897 | 1.246 | 19.7% | 27.6% | 55.2% | 65.5% | 0.713 | 0.694 |
| dev | Baseline: holistic cosine | 1.207 | 1.474 | 26.4% | 24.1% | 31.0% | 44.8% | 0.563 | 0.566 |
| test | AnswerWise engine | 0.839 | 1.326 | 20.7% | 46.4% | 53.6% | 71.4% | 0.785 | 0.743 |
| test | Baseline: keyword overlap | 0.750 | 1.052 | 18.6% | 32.1% | 60.7% | 75.0% | 0.873 | 0.888 |
| test | Baseline: holistic cosine | 1.179 | 1.529 | 28.9% | 25.0% | 42.9% | 50.0% | 0.566 | 0.600 |
| all | AnswerWise engine | 0.649 | 1.064 | 15.3% | 49.1% | 59.6% | 82.5% | 0.838 | 0.799 |
| all | Baseline: keyword overlap | 0.825 | 1.155 | 19.2% | 29.8% | 57.9% | 70.2% | 0.768 | 0.770 |
| all | Baseline: holistic cosine | 1.193 | 1.501 | 27.6% | 24.6% | 36.8% | 47.4% | 0.542 | 0.546 |

## Concept-level agreement (matched / partial / missing)

| Split | Concepts | Accuracy | Credit vs no-credit accuracy | Linear weighted kappa |
|---|---|---|---|---|
| dev | 115 | 83.5% | 88.7% | 0.787 |
| test | 112 | 72.3% | 79.5% | 0.513 |
| all | 227 | 78.0% | 84.1% | 0.651 |

Test-split confusion matrix (rows = human label, columns = engine):

| human \ engine | matched | partial | missing |
|---|---|---|---|
| matched | 21 | 5 | 19 |
| partial | 3 | 2 | 3 |
| missing | 1 | 0 | 58 |

## MAE by answer type (all splits)

| Answer type | n | MAE |
|---|---|---|
| abbreviations | 4 | 1.125 |
| empty | 2 | 0.000 |
| incorrect | 7 | 0.286 |
| incorrect_swapped | 1 | 1.000 |
| irrelevant_long | 7 | 0.000 |
| keyword_list | 1 | 1.000 |
| paraphrase | 8 | 1.688 |
| partial | 10 | 0.700 |
| repeated | 2 | 0.000 |
| single_concept | 7 | 0.214 |
| spelling | 8 | 0.812 |

## MAE by question

| Question | Split | MAE |
|---|---|---|
| Q1 | dev | 0.375 |
| Q2 | dev | 0.500 |
| Q3 | dev | 0.286 |
| Q4 | dev | 0.714 |
| Q5 | test | 0.857 |
| Q6 | test | 1.286 |
| Q7 | test | 0.357 |
| Q8 | test | 0.857 |

## Do review flags point at less reliable scores?

* Flagged for careful review: 35 answers, MAE 0.871
* Not flagged: 22 answers, MAE 0.295

## Largest disagreements

| Answer | Type | Human | Engine | Flags |
|---|---|---|---|---|
| Q6-a1 | paraphrase | 4 | 0 | borderline_concepts, divergent_signals, spelling_normalised |
| Q6-a5 | spelling | 4 | 1 | borderline_concepts, divergent_signals, spelling_normalised |
| Q4-a1 | paraphrase | 5 | 3 | borderline_concepts |
| Q5-a3 | partial | 2 | 0 | - |
| Q8-a1 | paraphrase | 4 | 2 | borderline_concepts |
| Q8-a7 | spelling | 3 | 1 | borderline_concepts, spelling_normalised |
| Q4-a2 | abbreviations | 2.5 | 1 | - |
| Q5-a1 | paraphrase | 5 | 3.5 | borderline_concepts, spelling_normalised |
| Q5-a4 | abbreviations | 5 | 3.5 | borderline_concepts |
| Q7-a1 | paraphrase | 3 | 1.5 | borderline_concepts |
| Q1-a1 | paraphrase | 4 | 3 | spelling_normalised |
| Q1-a2 | partial | 2 | 1 | borderline_concepts, divergent_signals |
| Q1-a6 | incorrect | 0 | 1 | borderline_concepts, divergent_signals |
| Q2-a3 | partial | 1.5 | 2.5 | borderline_concepts |
| Q2-a7 | keyword_list | 0 | 1 | keyword_list, borderline_concepts, divergent_signals |
| Q3-a1 | paraphrase | 4 | 3 | - |
| Q3-a3 | incorrect_swapped | 0 | 1 | borderline_concepts, divergent_signals |
| Q4-a3 | partial | 1 | 0 | borderline_concepts, divergent_signals |
| Q6-a2 | partial | 1 | 0 | borderline_concepts |
| Q6-a3 | single_concept | 1 | 0 | divergent_signals |
| Q7-a6 | spelling | 3 | 2 | borderline_concepts, spelling_normalised |
| Q8-a4 | abbreviations | 4 | 3 | borderline_concepts |
| Q8-a5 | incorrect | 0 | 1 | - |
