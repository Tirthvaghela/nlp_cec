"""Post-freeze comparison: score the archived v2 configuration on the v3 FINAL set.

Run only after v3 was frozen and evaluated (it cannot influence v3's design).
Usage (from backend/):  python -m evaluation.compare_final_v2
"""

import numpy as np

from evaluation.common import PRE_V4_FEATURES_OFF, V2_PROFILE, V3_PROFILE, iter_answers, load_final_set, write_json

from app.nlp import EvaluationConfig, QuestionSpec, evaluate_answer
from app.nlp.metrics import score_metrics
from app.nlp.similarity import EmbeddingBackend, TfidfBackend


def run(pairs, backend, **cfg):
    config = EvaluationConfig.for_backend(backend.name, **cfg)
    pred = [evaluate_answer(QuestionSpec.from_dict(q), a["text"], config, backend).suggested_score for q, a in pairs]
    gold = [a["human_score"] for _, a in pairs]
    return score_metrics(pred, gold, [q["max_marks"] for q, _ in pairs]), pred


def main():
    pairs = list(iter_answers(load_final_set(), "final"))
    emb = EmbeddingBackend()
    out = {}
    # Pinned profiles: later engine defaults must not change what "v2" and "v3" mean here.
    out["v2 engine (checks off)"], p2 = run(pairs, emb, **V2_PROFILE)
    out["v3 engine (frozen)"], p3 = run(pairs, emb, **V3_PROFILE)
    out["v3 TF-IDF fallback"], _ = run(pairs, TfidfBackend(), correctness_checks=True, **PRE_V4_FEATURES_OFF)
    types = [a["type"] for _, a in pairs]
    gold = np.array([a["human_score"] for _, a in pairs])
    by_type = {}
    for t in sorted(set(types)):
        idx = [i for i, x in enumerate(types) if x == t]
        by_type[t] = {"n": len(idx), "v2_mae": float(np.mean(np.abs(np.array(p2)[idx] - gold[idx]))),
                      "v3_mae": float(np.mean(np.abs(np.array(p3)[idx] - gold[idx])))}
    for k, v in out.items():
        print(f"{k:24} MAE {v['mae']:.3f}  RMSE {v['rmse']:.3f}  within1 {v['within_1_0']:.1%}  exact {v['exact_agreement']:.1%}")
    for t, v in by_type.items():
        print(f"   {t:26} n={v['n']}  v2 {v['v2_mae']:.2f}  v3 {v['v3_mae']:.2f}")
    write_json("v3_final_comparison_with_v2.json", {"note": "post-freeze comparison on the v3 final set", "systems": out,
                                                    "mae_by_type": by_type})


if __name__ == "__main__":
    main()
