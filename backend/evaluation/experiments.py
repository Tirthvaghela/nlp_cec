"""Compare candidate scoring approaches on the DEV split only (v3 development).

Usage (from backend/):
    python -m evaluation.experiments

Every candidate is evaluated with leave-one-question-out cross-validation (LOQO):
for each dev question the thresholds are re-fitted on the other dev questions
(same smoothed-MAE rule as calibrate.py) and applied to the held-out question.
The keyword-overlap baseline is evaluated with the same protocol (its linear fit
is re-done per fold). The held-out / final data are never loaded here.

Candidates (each with a stated hypothesis):
  C0  v2 engine (sentence cosine, topic-debiased, + keyword evidence)
  C1  + token-level concept recall          -> fixes under-credited short definitions
  C2  + correctness safeguards              -> stops crediting swapped / reversed / negated statements
  C3  C1 + C2
Small grids only: debias weight in {0.5, 0.9}, token-recall weight in {0.3, 0.5}.
"""

from __future__ import annotations

import time
from collections import defaultdict

import numpy as np

from evaluation.calibrate import collect, pick, sweep
from evaluation.common import V2_PROFILE, iter_answers, load_dataset, write_json
from evaluation.evaluate import keyword_overlap  # noqa: E402

from app.nlp.rubric import round_to_step
from app.nlp.similarity import EmbeddingBackend

V2 = V2_PROFILE  # pinned: the v2/v3 defaults (checks off, no v4 features), so later default changes cannot leak in
MATCH = np.round(np.arange(0.20, 0.90 + 1e-9, 0.01), 2)
PARTIAL = np.round(np.arange(0.10, 0.85 + 1e-9, 0.01), 2)


def loqo(d):
    totals, level = sweep(d, MATCH, PARTIAL)
    pred = np.zeros(len(d["gold"]))
    lv = np.zeros(len(d["gold_level"]), dtype=int)
    owner = d["member"].argmax(axis=1)
    for q in sorted(set(d["qid"])):
        train = d["qid"] != q
        i, j, *_ = pick(totals, level, d, train, MATCH, PARTIAL)
        pred[~train] = totals[i, j, ~train]
        held_c = ~train[owner]
        lv[held_c] = level[i, j, held_c]
    return pred, lv


def summary(name, pred, d, types, levels=None):
    err = pred - d["gold"]
    ae = np.abs(err)
    out = {
        "candidate": name, "n": int(len(ae)), "mae": float(ae.mean()), "rmse": float(np.sqrt((err ** 2).mean())),
        "within_1": float((ae <= 1 + 1e-9).mean()), "exact": float((ae < 1e-9).mean()),
        "severe_errors_ge_2": int((ae >= 2 - 1e-9).sum()), "mean_signed_error": float(err.mean()),
        "over_credit_answers": int((err > 0.5).sum()), "under_credit_answers": int((err < -0.5).sum()),
    }
    if levels is not None:
        out["concept_accuracy"] = float((levels == d["gold_level"]).mean())
    by = defaultdict(list)
    for t, e in zip(types, ae):
        by[t].append(e)
    out["mae_by_type"] = {t: round(float(np.mean(v)), 3) for t, v in sorted(by.items())}
    return out


def keyword_baseline_loqo(dev, d):
    feats = np.array([keyword_overlap(q, a["text"]) for q, a in dev])
    ratio = d["gold"] / d["max"]
    pred = np.zeros(len(feats))
    for q in sorted(set(d["qid"])):
        tr = d["qid"] != q
        a, b = np.polyfit(feats[tr], ratio[tr], 1)
        raw = (a * feats[~tr] + b) * d["max"][~tr]
        pred[~tr] = np.clip(np.floor(raw / 0.5 + 0.5) * 0.5, 0, d["max"][~tr])
    return pred


def main():
    t0 = time.time()
    data = load_dataset()
    dev = list(iter_answers(data, "dev"))
    types = [a["type"] for _, a in dev]
    backend = EmbeddingBackend()

    grid = {
        "C0 v2": [dict(V2)],
        "C1 +token recall": [dict(V2, debias_weight=db, token_recall_weight=b) for db in (0.5, 0.9) for b in (0.3, 0.5)],
        "C2 +correctness checks": [dict(V2, correctness_checks=True)],
        "C3 recall+checks": [dict(V2, debias_weight=db, token_recall_weight=b, correctness_checks=True)
                             for db in (0.5, 0.9) for b in (0.3, 0.5)],
    }
    results, details = [], {}
    d0 = None
    for name, configs in grid.items():
        best = None
        for params in configs:
            d = collect(backend, dev, **params)
            d0 = d0 or d
            pred, lv = loqo(d)
            s = summary(name, pred, d, types, lv)
            s["params"] = params
            print(f"  {name:24} {params} -> LOQO MAE {s['mae']:.3f} within1 {s['within_1']:.1%} severe {s['severe_errors_ge_2']}")
            if best is None or (s["mae"], s["severe_errors_ge_2"]) < (best["mae"], best["severe_errors_ge_2"]):
                best = s
                details[name] = {"pred": pred.tolist()}
        results.append(best)

    base = summary("keyword-overlap baseline", keyword_baseline_loqo(dev, d0), d0, types)
    results.append(base)

    print(f"\nDEV (n={len(dev)} synthetic answers, {len(set(d0['qid']))} questions) - leave-one-question-out")
    print(f"{'candidate':26}{'MAE':>7}{'RMSE':>7}{'+-1':>7}{'exact':>7}{'severe':>8}{'signed':>8}{'concept acc':>12}")
    for r in results:
        print(f"{r['candidate']:26}{r['mae']:7.3f}{r['rmse']:7.3f}{r['within_1']:7.1%}{r['exact']:7.1%}"
              f"{r['severe_errors_ge_2']:8d}{r['mean_signed_error']:8.2f}{r.get('concept_accuracy', float('nan')):12.1%}")
    all_types = sorted({t for r in results for t in r["mae_by_type"]})
    print("\nMAE by answer type")
    print(f"{'type':26}" + "".join(f"{r['candidate'][:10]:>12}" for r in results))
    for t in all_types:
        n = types.count(t)
        print(f"{t + f' ({n})':26}" + "".join(f"{r['mae_by_type'].get(t, float('nan')):12.2f}" for r in results))
    write_json("v3_dev_experiments.json", {"split": "dev", "n": len(dev), "protocol": "LOQO, thresholds re-fitted per fold",
                                           "results": results, "seconds": round(time.time() - t0, 1)})
    print(f"\nsaved results/v3_dev_experiments.json ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
