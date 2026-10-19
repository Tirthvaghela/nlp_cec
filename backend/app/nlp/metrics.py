"""Agreement metrics between engine scores and human reference marks."""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
from scipy import stats
from sklearn.metrics import cohen_kappa_score

LEVELS = ["matched", "partial", "missing"]


def mae(pred: list[float], gold: list[float]) -> float:
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(gold)))) if gold else math.nan


def rmse(pred: list[float], gold: list[float]) -> float:
    return float(np.sqrt(np.mean((np.asarray(pred) - np.asarray(gold)) ** 2))) if gold else math.nan


def agreement_within(pred: list[float], gold: list[float], tol: float) -> float:
    if not gold:
        return math.nan
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(gold)) <= tol + 1e-9))


def normalised_mae(pred: list[float], gold: list[float], max_marks: list[float]) -> float:
    """MAE expressed as a fraction of each question's maximum marks."""
    if not gold:
        return math.nan
    p, g, m = (np.asarray(x, dtype=float) for x in (pred, gold, max_marks))
    return float(np.mean(np.abs(p - g) / m))


def correlation(pred: list[float], gold: list[float]) -> dict[str, float]:
    if len(gold) < 3 or np.std(pred) == 0 or np.std(gold) == 0:
        return {"pearson": math.nan, "spearman": math.nan}
    return {
        "pearson": float(stats.pearsonr(pred, gold)[0]),
        "spearman": float(stats.spearmanr(pred, gold)[0]),
    }


def score_metrics(pred: list[float], gold: list[float], max_marks: list[float]) -> dict:
    out = {
        "n": len(gold),
        "mae": mae(pred, gold),
        "rmse": rmse(pred, gold),
        "normalised_mae": normalised_mae(pred, gold, max_marks),
        "exact_agreement": agreement_within(pred, gold, 0.0),
        "within_0_5": agreement_within(pred, gold, 0.5),
        "within_1_0": agreement_within(pred, gold, 1.0),
        "mean_signed_error": float(np.mean(np.asarray(pred) - np.asarray(gold))) if gold else math.nan,
    }
    out.update(correlation(pred, gold))
    return out


def concept_metrics(pred_levels: list[str], gold_levels: list[str]) -> dict:
    """Accuracy, per-level precision/recall and Cohen's kappa for concept decisions."""
    n = len(gold_levels)
    if n == 0:
        return {"n": 0}
    confusion = {g: {p: 0 for p in LEVELS} for g in LEVELS}
    for p, g in zip(pred_levels, gold_levels):
        confusion[g][p] += 1
    acc = sum(confusion[l][l] for l in LEVELS) / n
    per_level = {}
    pred_counts = Counter(pred_levels)
    for lvl in LEVELS:
        tp = confusion[lvl][lvl]
        support = sum(confusion[lvl].values())
        precision = tp / pred_counts[lvl] if pred_counts[lvl] else math.nan
        recall = tp / support if support else math.nan
        per_level[lvl] = {"precision": precision, "recall": recall, "support": support}
    # "Credit given or not" view: matched/partial vs missing.
    binary_acc = float(np.mean([(p != "missing") == (g != "missing") for p, g in zip(pred_levels, gold_levels)]))
    order = {l: i for i, l in enumerate(LEVELS)}
    kappa = cohen_kappa_score([order[g] for g in gold_levels], [order[p] for p in pred_levels], weights="linear")
    return {
        "n": n,
        "accuracy": acc,
        "credit_vs_no_credit_accuracy": binary_acc,
        "linear_weighted_kappa": float(kappa),
        "per_level": per_level,
        "confusion_matrix_gold_rows_pred_cols": confusion,
    }
