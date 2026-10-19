"""Post-freeze comparison on the v4 FRESH set: v3 configuration vs frozen v4 vs TF-IDF fallback.

Run only after v4 was frozen and officially evaluated with `evaluate --v4-fresh`; it cannot influence v4.
Usage (from backend/):  python -m evaluation.compare_v4_fresh
"""

import numpy as np

from evaluation.common import PRE_V4_FEATURES_OFF, V41_FEATURES_OFF, iter_answers, load_v4_fresh_set, write_json

from app.nlp import EvaluationConfig, QuestionSpec, evaluate_answer
from app.nlp.metrics import score_metrics
from app.nlp.similarity import EmbeddingBackend, TfidfBackend

# Pinned: later engine defaults (e.g. the v4.1 audit fixes) must not change what "v3" and "v4" mean here.
V3 = dict(correctness_checks=True, **PRE_V4_FEATURES_OFF)
V40 = V41_FEATURES_OFF


def run(pairs, backend, **cfg):
    config = EvaluationConfig.for_backend(backend.name, **cfg)
    pred = [evaluate_answer(QuestionSpec.from_dict(q), a["text"], config, backend).suggested_score for q, a in pairs]
    gold = [a["human_score"] for _, a in pairs]
    return score_metrics(pred, gold, [q["max_marks"] for q, _ in pairs]), pred


def main():
    pairs = list(iter_answers(load_v4_fresh_set(), "v4_fresh"))
    emb = EmbeddingBackend()
    out, preds = {}, {}
    out["v3 configuration"], preds["v3"] = run(pairs, emb, **V3)
    out["v4 engine (frozen)"], preds["v4"] = run(pairs, emb, **V40)
    out["v4 TF-IDF fallback"], _ = run(pairs, TfidfBackend(), **V40)
    types = [a["type"] for _, a in pairs]
    gold = np.array([a["human_score"] for _, a in pairs])
    by_type = {}
    for t in sorted(set(types)):
        idx = [i for i, x in enumerate(types) if x == t]
        by_type[t] = {"n": len(idx), **{f"{k}_mae": float(np.mean(np.abs(np.array(v)[idx] - gold[idx]))) for k, v in preds.items()}}
    for k, v in out.items():
        print(f"{k:22} MAE {v['mae']:.3f}  RMSE {v['rmse']:.3f}  within1 {v['within_1_0']:.1%}  exact {v['exact_agreement']:.1%}")
    for t, v in by_type.items():
        print(f"   {t:26} n={v['n']}  v3 {v['v3_mae']:.2f}  v4 {v['v4_mae']:.2f}")
    write_json("v4_fresh_comparison_with_v3.json", {"note": "post-freeze comparison on the v4 fresh set",
                                                    "systems": out, "mae_by_type": by_type})


if __name__ == "__main__":
    main()
