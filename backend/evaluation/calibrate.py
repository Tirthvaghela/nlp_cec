"""Choose engine weights and thresholds using the DEV split only.

Usage (from backend/):
    python -m evaluation.calibrate                 # embedding backend
    python -m evaluation.calibrate --backend tfidf # fallback backend

Method
------
1. For every combination of the *structural* parameters (topic-debias weight,
   keyword weight, sentence-pair windows) the engine is run once on every DEV
   answer and each concept's combined score is stored. Concept scores and
   evidence assignment do not depend on the thresholds, so the thresholds can
   then be swept cheaply and *exactly* (same credit, rounding and clamping as the
   engine, including the keyword-list downgrade).
   (v3 adds the dense+sparse hybrid weight to this grid.)
2. Thresholds for a set of questions are chosen by the lowest *smoothed* MAE
   (MAE averaged over the +/-0.02 neighbourhood of a (match, partial) grid point),
   which prefers a stable region over one lucky grid point.
3. Leave-one-question-out cross-validation (LOQO): for each DEV question, the
   thresholds are chosen on the other questions and applied to the held-out one.
   The LOQO MAE estimates how well thresholds transfer to a *new* question - the
   situation a teacher is in. The structural combination with the lowest LOQO
   MAE is selected, and its final thresholds are fitted on all DEV questions.

The chosen values are saved to results/calibration_<backend>.json and copied by
hand into app/nlp/config.py.
"""

from __future__ import annotations

import argparse
import itertools
import time

import numpy as np

from evaluation.common import LEVEL_OF, iter_answers, load_dataset, write_json

from app.nlp.config import EvaluationConfig
from app.nlp.rubric import QuestionSpec
from app.nlp.scorer import evaluate_answer
from app.nlp.similarity import EmbeddingBackend, TfidfBackend

LEVEL_INDEX = {"matched": 0, "partial": 1, "missing": 2}


def collect(backend, answers, **params):
    """Run the engine once; return flat per-concept arrays for exact threshold sweeps."""
    scores, marks, is_list, gold_level, owner = [], [], [], [], []
    gold, maxm, qid = [], [], []
    for n, (q, a) in enumerate(answers):
        cfg = EvaluationConfig.for_backend(backend.name, **params)
        res = evaluate_answer(QuestionSpec.from_dict(q), a["text"], cfg, backend)
        for c in res.concepts:
            scores.append(c.combined_score)
            marks.append(c.marks)
            # evidence downgraded one level by the engine (keyword list, or v3 added-negation check)
            is_list.append(c.keyword_list_evidence or c.issue in ("negated", "antonym"))
            gold_level.append(LEVEL_INDEX[LEVEL_OF[a["labels"][c.id]]])
            owner.append(n)
        gold.append(a["human_score"])
        maxm.append(q["max_marks"])
        qid.append(q["id"])
    member = np.zeros((len(scores), len(gold)))
    member[np.arange(len(scores)), owner] = 1.0
    return {
        "scores": np.array(scores), "marks": np.array(marks), "is_list": np.array(is_list),
        "gold_level": np.array(gold_level), "member": member, "gold": np.array(gold),
        "max": np.array(maxm), "qid": np.array(qid),
    }


def _round(x, step=0.5):
    return np.floor(x / step + 0.5 + 1e-9) * step


def sweep(d, match_grid, partial_grid):
    """Predicted question scores and concept levels for every (match, partial) pair.

    Returns pred[M, P, answers] and level[M, P, concepts]; invalid pairs are NaN.
    """
    s = d["scores"][None, None, :]
    m = match_grid[:, None, None]
    p = partial_grid[None, :, None]
    level = np.where(s >= m, 0, np.where(s >= p, 1, 2))
    # keyword-list evidence is downgraded by one level (matched->partial, partial->missing)
    level = np.where(d["is_list"][None, None, :] & (level < 2), level + 1, level)
    credit = np.choose(level, [1.0, 0.5, 0.0])
    awarded = np.minimum(d["marks"], _round(d["marks"] * credit))
    totals = np.clip(_round(awarded @ d["member"]), 0, d["max"])
    valid = (partial_grid[None, :] <= match_grid[:, None] - 0.05 + 1e-9)
    totals = np.where(valid[:, :, None], totals, np.nan)
    return totals, level


def smooth(mae, radius=2):
    out = np.full_like(mae, np.nan)
    for i, j in zip(*np.where(~np.isnan(mae))):
        out[i, j] = np.nanmean(mae[max(0, i - radius) : i + radius + 1, max(0, j - radius) : j + radius + 1])
    return out


def pick(totals, level, d, answer_mask, match_grid, partial_grid):
    concept_mask = answer_mask[d["member"].argmax(axis=1)]
    err = np.abs(totals[:, :, answer_mask] - d["gold"][answer_mask])
    mae = err.mean(axis=2)
    acc = (level[:, :, concept_mask] == d["gold_level"][concept_mask]).mean(axis=2)
    sm = smooth(mae)
    key = np.where(np.isnan(sm), np.inf, sm) - 1e-6 * acc
    i, j = np.unravel_index(np.argmin(key), key.shape)
    return i, j, float(mae[i, j]), float(sm[i, j]), float(acc[i, j])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["embedding", "tfidf"], default="embedding")
    args = ap.parse_args()

    data = load_dataset()
    dev = list(iter_answers(data, "dev"))
    backend = EmbeddingBackend() if args.backend == "embedding" else TfidfBackend()
    lo, hi = (0.20, 0.90) if args.backend == "embedding" else (0.05, 0.75)
    match_grid = np.round(np.arange(lo, hi + 1e-9, 0.01), 2)
    partial_grid = np.round(np.arange(lo - 0.10, hi - 0.05 + 1e-9, 0.01), 2)

    if args.backend == "embedding":
        debias_grid = [0.0, 0.5, 0.75, 0.9, 1.0]
        hybrid_grid = [0.0, 0.25, 0.4, 0.55]
    else:
        debias_grid, hybrid_grid = [0.0], [0.0]
    kw_grid = [0.0, 0.15, 0.3, 0.45]
    pairs_grid = [True, False]

    t0 = time.time()
    candidates = []
    for debias, hybrid, kw, pairs in itertools.product(debias_grid, hybrid_grid, kw_grid, pairs_grid):
        d = collect(backend, dev, debias_weight=debias, hybrid_weight=hybrid, keyword_weight=kw, use_sentence_pairs=pairs)
        totals, level = sweep(d, match_grid, partial_grid)
        questions = sorted(set(d["qid"]))
        cv_err, folds = [], {}
        for q in questions:
            train = d["qid"] != q
            i, j, *_ = pick(totals, level, d, train, match_grid, partial_grid)
            held = ~train
            e = np.abs(totals[i, j, held] - d["gold"][held])
            cv_err.extend(e.tolist())
            folds[q] = {"match": float(match_grid[i]), "partial": float(partial_grid[j]), "mae": float(e.mean())}
        all_mask = np.ones(len(d["gold"]), dtype=bool)
        i, j, mae, sm, acc = pick(totals, level, d, all_mask, match_grid, partial_grid)
        cand = {
            "debias_weight": debias, "hybrid_weight": hybrid, "keyword_weight": kw, "use_sentence_pairs": pairs,
            "loqo_cv_mae": float(np.mean(cv_err)),
            "match_threshold": float(match_grid[i]), "partial_threshold": float(partial_grid[j]),
            "dev_fit_mae": mae, "dev_fit_smoothed_mae": sm, "dev_fit_concept_accuracy": acc,
            "folds": folds,
        }
        candidates.append(cand)
        print(f"debias={debias:<4} hybrid={hybrid:<4} kw={kw:<4} pairs={pairs!s:<5} LOQO-MAE={cand['loqo_cv_mae']:.3f} | "
              f"all-dev fit: match={cand['match_threshold']:.2f} partial={cand['partial_threshold']:.2f} "
              f"MAE={mae:.3f} acc={acc:.3f}")

    candidates.sort(key=lambda c: (round(c["loqo_cv_mae"], 6), c["dev_fit_smoothed_mae"]))
    best = candidates[0]
    payload = {
        "backend": args.backend, "model_name": backend.model_name, "split": "dev",
        "n_answers": len(dev), "n_questions": len({q['id'] for q, _ in dev}),
        "selection": "structural params by leave-one-question-out CV MAE; thresholds by smoothed MAE on all dev questions",
        "best": best,
        "top10": candidates[:10],
        "all_candidates": candidates,
        "seconds": round(time.time() - t0, 1),
    }
    path = write_json(f"calibration_{args.backend}.json", payload)
    print("\nTOP 5 by LOQO MAE:")
    for c in candidates[:5]:
        print(f"  debias={c['debias_weight']} hybrid={c['hybrid_weight']} kw={c['keyword_weight']} pairs={c['use_sentence_pairs']} "
              f"LOQO={c['loqo_cv_mae']:.3f} match={c['match_threshold']} partial={c['partial_threshold']}")
    print("BEST:", {k: v for k, v in best.items() if k != "folds"})
    print("per-fold:", best["folds"])
    print("saved", path)


if __name__ == "__main__":
    main()
