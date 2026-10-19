"""v4 development experiments - DEV split only, leave-one-question-out (same protocol as experiments.py).

Usage (from backend/):  python -m evaluation.experiments_v4

Candidates (each with a stated hypothesis; small set, no weight grids):
  E0  v3 engine as released (old keyword-list detector)
  E1  v3 + keyword-list predicate cues   -> bug fix: dense correct sentences are no longer treated as lists
  E2  E1 + adaptive debias               -> concepts that are mostly "topic" keep their meaning (short definitions)
  E3  E1 + antonym-flip check            -> wrong statements that swap a word for its antonym lose credit
  E4  E1 + adaptive debias + antonym check
  E5  E3 + echo guard                    -> sentences that only name/restate the topic earn nothing
  E6  E1 + echo guard                    -> isolates the echo guard
The final held-out sets (v3 final_test.json, v4_fresh_test.json) are never loaded here.
"""

from __future__ import annotations

import time

from evaluation.calibrate import collect
from evaluation.common import iter_answers, load_dataset, write_json
from evaluation.experiments import V2, keyword_baseline_loqo, loqo, summary

from app.nlp.similarity import EmbeddingBackend

V3 = dict(V2, correctness_checks=True, token_recall_weight=0.0)
CANDIDATES = {
    "E0 v3 (released)": dict(V3, keyword_list_predicate_cues=False, adaptive_debias=False, antonym_check=False),
    "E1 v3 + detector fix": dict(V3, keyword_list_predicate_cues=True, adaptive_debias=False, antonym_check=False),
    "E2 E1 + adaptive debias": dict(V3, keyword_list_predicate_cues=True, adaptive_debias=True, antonym_check=False),
    "E3 E1 + antonym check": dict(V3, keyword_list_predicate_cues=True, adaptive_debias=False, antonym_check=True),
    "E4 E1 + adaptive + antonym": dict(V3, keyword_list_predicate_cues=True, adaptive_debias=True, antonym_check=True),
    # added after E0-E4 were run: vague answers were the worst category (dev MAE 2.25)
    "E5 E3 + echo guard": dict(V3, keyword_list_predicate_cues=True, adaptive_debias=False, antonym_check=True,
                               echo_guard=True),
    "E6 E1 + echo guard": dict(V3, keyword_list_predicate_cues=True, adaptive_debias=False, antonym_check=False,
                               echo_guard=True),
}
FOCUS = ["short_correct_definition", "dense_correct", "vague_short", "wrong_with_keywords", "swapped",
         "incorrect_swapped", "negated", "keyword_list", "paraphrase", "partial", "irrelevant_long"]


def main():
    t0 = time.time()
    dev = list(iter_answers(load_dataset(), "dev"))
    types = [a["type"] for _, a in dev]
    backend = EmbeddingBackend()
    results, d0 = [], None
    for name, params in CANDIDATES.items():
        d = collect(backend, dev, **params)
        d0 = d0 or d
        pred, lv = loqo(d)
        s = summary(name, pred, d, types, lv)
        s["params"] = params
        s["per_answer"] = {a["id"]: float(p) for (_, a), p in zip(dev, pred)}
        results.append(s)
    base = summary("keyword-overlap baseline", keyword_baseline_loqo(dev, d0), d0, types)
    results.append(base)

    print(f"DEV n={len(dev)} synthetic answers, {len(set(d0['qid']))} questions, max 3-5 marks - LOQO")
    print(f"{'candidate':30}{'MAE':>7}{'RMSE':>7}{'+-1':>7}{'exact':>7}{'severe':>8}{'signed':>8}{'concept':>9}")
    for r in results:
        print(f"{r['candidate']:30}{r['mae']:7.3f}{r['rmse']:7.3f}{r['within_1']:7.1%}{r['exact']:7.1%}"
              f"{r['severe_errors_ge_2']:8d}{r['mean_signed_error']:8.2f}{r.get('concept_accuracy', float('nan')):9.1%}")
    print("\nMAE by answer type")
    print(f"{'type':28}" + "".join(f"{r['candidate'][:9]:>11}" for r in results))
    for t in FOCUS:
        if t in types:
            print(f"{t + f' ({types.count(t)})':28}" + "".join(f"{r['mae_by_type'].get(t, float('nan')):11.2f}" for r in results))
    # severe-regression check: answers whose error grows by >= 1 mark versus E0
    e0 = results[0]["per_answer"]
    gold = {a["id"]: a["human_score"] for _, a in dev}
    for r in results[1:-1]:
        worse = [k for k in gold if abs(r["per_answer"][k] - gold[k]) - abs(e0[k] - gold[k]) >= 1]
        better = [k for k in gold if abs(e0[k] - gold[k]) - abs(r["per_answer"][k] - gold[k]) >= 1]
        print(f"{r['candidate']:30} vs E0: {len(better)} answers better by >=1 mark, {len(worse)} worse by >=1 mark {worse}")
        r["vs_E0"] = {"better_ge_1": better, "worse_ge_1": worse}
    write_json("v4_dev_experiments.json", {"split": "dev", "n": len(dev), "protocol": "LOQO, thresholds re-fitted per fold",
                                           "results": results, "seconds": round(time.time() - t0, 1)})
    print(f"\nsaved results/v4_dev_experiments.json ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
