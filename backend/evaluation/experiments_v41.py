"""v4.1 audit experiments - DEV split only, leave-one-question-out (same protocol as experiments_v4.py).

Usage (from backend/):  python -m evaluation.experiments_v41

Two candidate fixes for documented expected failures (tests marked xfail in v4.0):
  F0  v4.0 as released
  F1  F0 + attribute-swap check   -> "common -> high, distinctive -> low" inside one contrasting concept
  F2  F0 + expanded-topic echo    -> spelling out an abbreviation from the question is not an explanation
  F3  F0 + both
  F4  F3 + antonym contrast exemption -> the antonym check skips concepts that contrast two things (added after
      the audit found a 4.0 false positive: "frequent words ... whereas RARE distinctive words" flagged as a
      contradiction of "COMMON words ..."); compared against F3
Each candidate is also checked for *firings*: every concept on which the new check changes the outcome
is listed with its human label, so false positives on correct answers are visible, not just the MAE.

Both final held-out sets (v3 final_test.json, v4_fresh_test.json) are already spent and are never loaded
here. Because no unused held-out set exists, these candidates can only be validated on DEV data; a DEV
improvement is not evidence of a general accuracy gain.
"""

from __future__ import annotations

import time

from evaluation.calibrate import collect
from evaluation.common import LEVEL_OF, V41_FEATURES_OFF, iter_answers, load_dataset, write_json
from evaluation.experiments import keyword_baseline_loqo, loqo, summary

from app.nlp import EvaluationConfig, QuestionSpec, evaluate_answer
from app.nlp.similarity import EmbeddingBackend

V40 = V41_FEATURES_OFF  # every other setting = v4.0 defaults
CANDIDATES = {
    "F0 v4.0 (released)": V40,
    "F1 + attribute-swap check": dict(V40, attribute_swap_check=True),
    "F2 + expanded-topic echo": dict(V40, echo_expanded_topic=True),
    "F3 + both": dict(V40, attribute_swap_check=True, echo_expanded_topic=True),
    "F4 F3 + contrast exemption": dict(V40, attribute_swap_check=True, echo_expanded_topic=True,
                                       antonym_contrast_exemption=True),
}
COMPARE_WITH = {"F4 F3 + contrast exemption": "F3 + both"}  # default: F0


def firings(backend, dev, base: dict, params: dict) -> list[dict]:
    """Concepts whose level or issue differs from the released engine, with the human label."""
    out = []
    for q, a in dev:
        spec = QuestionSpec.from_dict(q)
        r0 = evaluate_answer(spec, a["text"], EvaluationConfig.for_backend(backend.name, **base), backend)
        r1 = evaluate_answer(spec, a["text"], EvaluationConfig.for_backend(backend.name, **params), backend)
        for c0, c1 in zip(r0.concepts, r1.concepts):
            if (c0.level, c0.issue) != (c1.level, c1.issue):
                out.append({"answer": a["id"], "type": a["type"], "concept": c1.id, "human": LEVEL_OF[a["labels"][c1.id]],
                            "before": c0.level, "after": c1.level, "issue": c1.issue})
    return out


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
        if params is not V40:
            s["firings_vs"] = COMPARE_WITH.get(name, "F0 v4.0 (released)")
            s["firings"] = firings(backend, dev, CANDIDATES[s["firings_vs"]], params)
        results.append(s)
    results.append(summary("keyword-overlap baseline", keyword_baseline_loqo(dev, d0), d0, types))

    print(f"DEV n={len(dev)} synthetic answers, {len(set(d0['qid']))} questions - LOQO")
    print(f"{'candidate':30}{'MAE':>7}{'RMSE':>7}{'+-1':>7}{'exact':>7}{'severe':>8}{'signed':>8}")
    for r in results:
        print(f"{r['candidate']:30}{r['mae']:7.3f}{r['rmse']:7.3f}{r['within_1']:7.1%}{r['exact']:7.1%}"
              f"{r['severe_errors_ge_2']:8d}{r['mean_signed_error']:8.2f}")
    for r in results[1:-1]:
        print(f"\n{r['candidate']}: {len(r['firings'])} concept outcome change(s) vs {r['firings_vs']}")
        for f in r["firings"]:
            print(f"   {f['answer']:8} {f['type']:26} {f['concept']:4} human={f['human']:8} {f['before']:>8} -> {f['after']:8} {f['issue']}")
    write_json("v41_dev_experiments.json", {"split": "dev", "n": len(dev), "protocol": "LOQO, thresholds re-fitted per fold",
                                            "results": results, "seconds": round(time.time() - t0, 1)})
    print(f"\nsaved results/v41_dev_experiments.json ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
