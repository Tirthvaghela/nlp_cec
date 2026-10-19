"""Post-hoc uncertainty of the archived v4.0 fresh-set result (final quality audit).

Reads ONLY the archived reports (results/evaluation_embedding_v4_fresh_v4.json and
results/v4_fresh_comparison_with_v3.json). It does not load v4_fresh_test.json, does not run the engine
and does not look at individual answers - it adds confidence intervals to numbers that already exist.

Usage (from backend/):  python -m evaluation.uncertainty_v4_fresh
"""

from __future__ import annotations

import json

from evaluation.common import RESULTS_DIR, write_json
from evaluation.stats import bootstrap_ci


def main():
    rep = json.loads((RESULTS_DIR / "evaluation_embedding_v4_fresh_v4.json").read_text(encoding="utf-8"))
    cmp_ = json.loads((RESULTS_DIR / "v4_fresh_comparison_with_v3.json").read_text(encoding="utf-8"))["systems"]
    rows = rep["per_answer"]
    args = ([r["pred"] for r in rows], [r["gold"] for r in rows], [r["max"] for r in rows], [r["question"] for r in rows])
    n = len(rows)
    out = {
        "note": "Post-hoc analysis of archived v4.0 fresh-set results (audit). No engine run, no new data. "
                "Per-answer predictions of the v3 configuration and the keyword baseline were not archived, so a "
                "paired confidence interval for v4 - v3 cannot be computed without re-running the spent set; the "
                "difference is reported as total absolute error instead.",
        "engine_version": rep["engine_version"],
        "v4_cluster_bootstrap": bootstrap_ci(*args, by_cluster=True),
        "v4_answer_bootstrap": bootstrap_ci(*args, by_cluster=False),
        "total_absolute_error_marks": {
            "v4.0 engine": round(cmp_["v4 engine (frozen)"]["mae"] * n, 2),
            "v3 configuration": round(cmp_["v3 configuration"]["mae"] * n, 2),
            "keyword baseline": round(rep["baselines"]["keyword_overlap"]["mae"] * n, 2),
            "TF-IDF fallback": round(cmp_["v4 TF-IDF fallback"]["mae"] * n, 2),
        },
        "n_answers": n,
    }
    write_json("v4_fresh_uncertainty_posthoc.json", out)
    c, a = out["v4_cluster_bootstrap"], out["v4_answer_bootstrap"]
    print(f"v4.0 fresh MAE {c['mae']['estimate']:.3f}  95% CI by question {c['mae']['ci'][0]:.3f}-{c['mae']['ci'][1]:.3f} "
          f"({c['clusters']} questions); by answer {a['mae']['ci'][0]:.3f}-{a['mae']['ci'][1]:.3f}")
    print(f"within +-1 {c['within_1']['estimate']:.1%}  CI {c['within_1']['ci'][0]:.1%}-{c['within_1']['ci'][1]:.1%}")
    print("total absolute error (marks, 64 answers):", out["total_absolute_error_marks"])


if __name__ == "__main__":
    main()
