import math

import pytest

from app.nlp.metrics import agreement_within, concept_metrics, mae, rmse, score_metrics


def test_score_metrics_basic():
    pred, gold = [1, 2, 3.5, 0], [1, 3, 3, 0]
    assert mae(pred, gold) == pytest.approx(0.375)
    assert rmse(pred, gold) == pytest.approx(math.sqrt((0 + 1 + 0.25 + 0) / 4))
    assert agreement_within(pred, gold, 0) == 0.5
    assert agreement_within(pred, gold, 0.5) == 0.75
    m = score_metrics(pred, gold, [4, 4, 4, 4])
    assert m["n"] == 4 and m["normalised_mae"] == pytest.approx(0.375 / 4)
    assert -1 <= m["pearson"] <= 1


def test_concept_metrics_confusion_and_kappa():
    gold = ["matched", "partial", "missing", "missing"]
    pred = ["matched", "missing", "missing", "partial"]
    m = concept_metrics(pred, gold)
    assert m["accuracy"] == 0.5
    assert m["confusion_matrix_gold_rows_pred_cols"]["partial"]["missing"] == 1
    assert m["credit_vs_no_credit_accuracy"] == 0.5
    perfect = concept_metrics(gold, gold)
    assert perfect["accuracy"] == 1 and perfect["linear_weighted_kappa"] == pytest.approx(1.0)
