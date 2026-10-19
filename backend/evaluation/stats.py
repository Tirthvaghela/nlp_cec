"""Uncertainty estimates for score-agreement metrics (no engine, numpy only).

Answers to the same question are not independent (one rubric, one reference answer, often one
writer), so the default bootstrap resamples *questions* (cluster bootstrap) and keeps every answer of
a drawn question. With few questions the interval is wide - that width is the honest result.
"""

from __future__ import annotations

import numpy as np

METRICS = {
    "mae": lambda e, m: float(np.mean(np.abs(e))),
    "normalised_mae": lambda e, m: float(np.mean(np.abs(e) / m)),
    "within_1": lambda e, m: float(np.mean(np.abs(e) <= 1 + 1e-9)),
    "severe_ge_2": lambda e, m: float(np.mean(np.abs(e) >= 2 - 1e-9)),
}


def _draws(clusters: np.ndarray, n_boot: int, seed: int, by_cluster: bool):
    rng = np.random.default_rng(seed)
    if not by_cluster:
        n = len(clusters)
        for _ in range(n_boot):
            yield rng.integers(0, n, n)
        return
    ids = np.unique(clusters)
    members = {c: np.flatnonzero(clusters == c) for c in ids}
    for _ in range(n_boot):
        yield np.concatenate([members[c] for c in rng.choice(ids, len(ids))])


def bootstrap_ci(pred, gold, max_marks, clusters, n_boot: int = 10000, seed: int = 0, by_cluster: bool = True,
                 level: float = 0.95) -> dict:
    """Point estimate and percentile CI for each metric in METRICS."""
    p, g, m = (np.asarray(x, dtype=float) for x in (pred, gold, max_marks))
    c = np.asarray(clusters)
    e = p - g
    lo, hi = (1 - level) / 2 * 100, (1 + level) / 2 * 100
    boots = {k: [] for k in METRICS}
    for idx in _draws(c, n_boot, seed, by_cluster):
        for k, f in METRICS.items():
            boots[k].append(f(e[idx], m[idx]))
    return {k: {"estimate": METRICS[k](e, m), "ci": [float(np.percentile(v, lo)), float(np.percentile(v, hi))]}
            for k, v in boots.items()} | {"n": int(len(e)), "clusters": int(len(np.unique(c))),
                                          "resampling": "question clusters" if by_cluster else "answers",
                                          "n_boot": n_boot, "level": level}


def paired_difference_ci(pred_a, pred_b, gold, clusters, n_boot: int = 10000, seed: int = 0, by_cluster: bool = True,
                         level: float = 0.95) -> dict:
    """CI for MAE(a) - MAE(b) on the same answers (negative = a has the lower error)."""
    a, b, g = (np.asarray(x, dtype=float) for x in (pred_a, pred_b, gold))
    d = np.abs(a - g) - np.abs(b - g)
    c = np.asarray(clusters)
    vals = [float(np.mean(d[idx])) for idx in _draws(c, n_boot, seed, by_cluster)]
    lo, hi = (1 - level) / 2 * 100, (1 + level) / 2 * 100
    ci = [float(np.percentile(vals, lo)), float(np.percentile(vals, hi))]
    return {"mae_difference": float(np.mean(d)), "ci": ci, "ci_excludes_zero": bool(ci[1] < 0 or ci[0] > 0),
            "total_abs_error_a": float(np.abs(a - g).sum()), "total_abs_error_b": float(np.abs(b - g).sum()),
            "n": int(len(d)), "resampling": "question clusters" if by_cluster else "answers"}
