"""Evaluate the scoring engine against human reference marks.

Usage (from backend/):
    python -m evaluation.evaluate                     # DEV split (default) - safe during development
    python -m evaluation.evaluate --split seen-test   # Q9-Q12: held out for v2, PREVIOUSLY SEEN (not independent for v3)
    python -m evaluation.evaluate --v4-fresh --historical-rerun  # v4 fresh set (SPENT after the v4.0 run; history only)
    python -m evaluation.evaluate --final --historical-rerun     # v3 final set (SPENT after the v3 run; history only)
    python -m evaluation.evaluate --profile v4.0      # reproduce an earlier engine configuration (v3 | v4.0)
    python -m evaluation.evaluate --backend tfidf     # fallback backend
    python -m evaluation.evaluate --show-errors       # also print every answer with |error| >= 1

Development runs never load or print the final set. ``--final`` verifies that
final_test.json still matches the SHA-256 recorded before v3 development began.

Reports for the chosen split:
  * score agreement: MAE, RMSE, normalised MAE, exact / within-0.5 / within-1, Pearson, Spearman
  * concept-level agreement: accuracy, linear-weighted kappa, confusion matrix
  * MAE per question and per answer type; largest disagreements
  * whether "needs review" flags point at the less reliable scores
  * two baselines, each linearly fitted on DEV (never on the evaluated split, unless it is dev):
      - keyword overlap: share of reference-answer key terms found in the answer
      - holistic cosine: sentence-embedding cosine of the whole answer vs the reference
Note: on the dev split the engine's thresholds were fitted on the same questions (in-sample);
the leave-one-question-out estimates are produced by ``python -m evaluation.experiments``.
Results go to results/evaluation_<backend>_<split>_v<engine version>.json and .md (``_v4`` for 4.0, ``_v4.1`` for
4.1, unsuffixed for v3). Archived reports are never overwritten (common.HISTORICAL_RESULTS): a reproduction is
written to ``*_rerun.*``. Both held-out sets are spent, so they only run with --historical-rerun and the report
is labelled as a historical rerun, never as an independent test.
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict

import numpy as np

from evaluation.common import (
    LEVEL_OF, V3_PROFILE, V40_PROFILE, iter_answers, load_dataset, load_final_set, load_v4_fresh_set, result_path,
    write_json,
)

from app.nlp import preprocessing as pp
from app.nlp.config import ENGINE_VERSION, EvaluationConfig
from app.nlp.metrics import concept_metrics, score_metrics
from app.nlp.rubric import QuestionSpec, round_to_step
from app.nlp.scorer import evaluate_answer
from app.nlp.similarity import EmbeddingBackend, TfidfBackend

SPLIT_NOTES = {
    "dev": "DEV split (Q1-Q8). The engine's thresholds were fitted on these questions, so these numbers are in-sample; "
           "see results/v3_dev_experiments.json for leave-one-question-out estimates.",
    "seen-test": "Q9-Q12. Held out for engine v2, but their per-answer errors were inspected afterwards, so they are "
                 "NOT an independent test of engine v3.",
    "v4_fresh": "v4 FRESH held-out set (R1-R8, v4_fresh_test.json): 8 new questions x 8 fixed answer types, written and "
                "labelled before any v4 change, integrity-checked by SHA-256, evaluated once after v4 was frozen. Synthetic; "
                "written and marked by the engine developer.",
    "final": "v3 FINAL held-out set (Q13-Q18, final_test.json), written and labelled before v3 development, "
             "integrity-checked by SHA-256, evaluated once after the configuration was frozen.",
}


PROFILES = {"current": {}, "v4.0": V40_PROFILE, "v3": V3_PROFILE}


def profile_overrides(profile: str, backend_name: str) -> dict:
    """Historical profiles pin feature switches; on the TF-IDF backend only the switches (not the
    embedding weights) apply, as the TF-IDF backend has its own defaults."""
    p = PROFILES[profile]
    if backend_name != "embedding":
        p = {k: v for k, v in p.items() if k not in ("debias_weight", "keyword_weight", "use_sentence_pairs")}
    return p


def report_tag(profile: str) -> str:
    if profile == "v3":
        return ""
    if profile == "v4.0":
        return "_v4"
    major, minor = ENGINE_VERSION.split(".")[:2]
    return f"_v{major}" if minor == "0" else f"_v{major}.{minor}"


def run_engine(pairs, backend, profile: str = "current"):
    rows = []
    cfg = EvaluationConfig.for_backend(backend.name, **profile_overrides(profile, backend.name))
    for q, a in pairs:
        res = evaluate_answer(QuestionSpec.from_dict(q), a["text"], cfg, backend)
        rows.append({
            "id": a["id"], "question": q["id"], "type": a["type"], "max": q["max_marks"], "text": a["text"],
            "gold": a["human_score"], "pred": res.suggested_score, "confidence": res.confidence,
            "needs_review": res.needs_review, "flags": [f.code for f in res.flags],
            "holistic": res.holistic_similarity or 0.0,
            "concepts": [{"id": c.id, "pred": c.level, "gold": LEVEL_OF[a["labels"][c.id]], "score": c.combined_score,
                          "issue": c.issue} for c in res.concepts],
            "_q": q,
        })
    return rows, cfg


def keyword_overlap(q, text):
    ref = set(pp.key_terms(q["reference_answer"]))
    ans = {pp.stem(w) for w in pp.content_words(text)}
    return len(ref & ans) / len(ref) if ref else 0.0


def fit_linear(dev_rows, feature):
    """Fit score_ratio = a * feature + b on DEV rows; return a predictor for any row."""
    x = np.array([feature(r) for r in dev_rows])
    y = np.array([r["gold"] / r["max"] for r in dev_rows])
    a, b = np.polyfit(x, y, 1)
    return lambda r: float(max(0.0, min(r["max"], round_to_step((a * feature(r) + b) * r["max"], 0.5))))


def summarise(rows):
    out = {"scores": score_metrics([r["pred"] for r in rows], [r["gold"] for r in rows], [r["max"] for r in rows])}
    out["concepts"] = concept_metrics([c["pred"] for r in rows for c in r["concepts"]],
                                      [c["gold"] for r in rows for c in r["concepts"]])
    by_q, by_t = defaultdict(list), defaultdict(list)
    for r in rows:
        by_q[r["question"]].append(abs(r["pred"] - r["gold"]))
        by_t[r["type"]].append(abs(r["pred"] - r["gold"]))
    out["per_question_mae"] = {k: float(np.mean(v)) for k, v in sorted(by_q.items(), key=lambda kv: int(kv[0][1:]))}
    out["per_type_mae"] = {k: {"mae": float(np.mean(v)), "n": len(v)} for k, v in sorted(by_t.items())}
    flagged = [abs(r["pred"] - r["gold"]) for r in rows if r["needs_review"]]
    clear = [abs(r["pred"] - r["gold"]) for r in rows if not r["needs_review"]]
    out["review_flags"] = {
        "flagged_n": len(flagged), "flagged_mae": float(np.mean(flagged)) if flagged else None,
        "not_flagged_n": len(clear), "not_flagged_mae": float(np.mean(clear)) if clear else None,
    }
    issues = defaultdict(lambda: {"fired": 0, "on_human_missing": 0})
    for r in rows:
        for c in r["concepts"]:
            if c["issue"]:
                issues[c["issue"]]["fired"] += 1
                issues[c["issue"]]["on_human_missing"] += c["gold"] == "missing"
    out["correctness_safeguards"] = dict(issues)
    errs = np.array([r["pred"] - r["gold"] for r in rows])
    out["error_distribution"] = {
        "over_credit_gt_0_5": int((errs > 0.5).sum()), "under_credit_lt_-0_5": int((errs < -0.5).sum()),
        "abs_error_ge_2": int((np.abs(errs) >= 2).sum()),
    }
    return out


def fmt(x, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    return f"{x:.1%}" if pct else f"{x:.3f}"


def markdown_report(p) -> str:
    L = [f"# Evaluation report - split `{p['split']}`, backend `{p['backend']}`", "",
         f"{p['note']}", "",
         f"Engine {p['engine_version']} - model `{p['model_name']}` - config `{p['config_fingerprint']}` - "
         f"{p['n_answers']} synthetic answers, {p['n_questions']} questions, max marks per question "
         f"{p['max_marks_range'][0]:g}-{p['max_marks_range'][1]:g}.", "",
         "## Question-score agreement", "",
         "| System | MAE | RMSE | Norm. MAE | Exact | Within 0.5 | Within 1 | Pearson | Spearman |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, b in (("AnswerWise engine", p["engine"]["scores"]),
                    ("Baseline: keyword overlap (fitted on dev)", p["baselines"]["keyword_overlap"]),
                    ("Baseline: holistic cosine (fitted on dev)", p["baselines"]["holistic_cosine"])):
        L.append(f"| {name} | {fmt(b['mae'])} | {fmt(b['rmse'])} | {fmt(b['normalised_mae'], True)} | "
                 f"{fmt(b['exact_agreement'], True)} | {fmt(b['within_0_5'], True)} | {fmt(b['within_1_0'], True)} | "
                 f"{fmt(b['pearson'])} | {fmt(b['spearman'])} |")
    c = p["engine"]["concepts"]
    ed = p["engine"]["error_distribution"]
    L += ["", f"Error distribution: {ed['over_credit_gt_0_5']} answers over-credited by more than 0.5, "
          f"{ed['under_credit_lt_-0_5']} under-credited by more than 0.5, {ed['abs_error_ge_2']} with |error| >= 2. "
          f"Mean signed error {fmt(p['engine']['scores']['mean_signed_error'])}.", "",
          "## Concept-level agreement", "",
          f"{c['n']} concept decisions - accuracy {fmt(c['accuracy'], True)}, credit vs no-credit accuracy "
          f"{fmt(c['credit_vs_no_credit_accuracy'], True)}, linear-weighted kappa {fmt(c['linear_weighted_kappa'])}.", "",
          "| human \\ engine | matched | partial | missing |", "|---|---|---|---|"]
    for g, row in c["confusion_matrix_gold_rows_pred_cols"].items():
        L.append(f"| {g} | {row['matched']} | {row['partial']} | {row['missing']} |")
    L += ["", "## MAE by answer type", "", "| Answer type | n | MAE |", "|---|---|---|"]
    for t, v in p["engine"]["per_type_mae"].items():
        L.append(f"| {t} | {v['n']} | {fmt(v['mae'])} |")
    L += ["", "## MAE by question", "", "| Question | MAE |", "|---|---|"]
    for qid, v in p["engine"]["per_question_mae"].items():
        L.append(f"| {qid} | {fmt(v)} |")
    rf = p["engine"]["review_flags"]
    L += ["", "## Review flags", "",
          f"* Flagged for careful review: {rf['flagged_n']} answers, MAE {fmt(rf['flagged_mae'])}",
          f"* Not flagged: {rf['not_flagged_n']} answers, MAE {fmt(rf['not_flagged_mae'])}", "",
          "## Correctness safeguards (v3)", ""]
    sg = p["engine"]["correctness_safeguards"]
    if sg:
        L += ["| Safeguard | Fired | ...on concepts the human marked missing |", "|---|---|---|"]
        for k, v in sg.items():
            L.append(f"| {k} | {v['fired']} | {v['on_human_missing']} |")
    else:
        L.append("No safeguard fired on this split.")
    L += ["", "## Largest disagreements (|error| >= 1)", "", "| Answer | Type | Human | Engine | Flags |", "|---|---|---|---|---|"]
    for r in p["largest_errors"]:
        L.append(f"| {r['id']} | {r['type']} | {r['gold']:g} | {r['pred']:g} | {', '.join(r['flags']) or '-'} |")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["embedding", "tfidf"], default="embedding")
    ap.add_argument("--split", choices=["dev", "seen-test"], default="dev")
    ap.add_argument("--final", action="store_true", help="v3 final set (spent; requires --historical-rerun for v4+)")
    ap.add_argument("--historical-rerun", action="store_true", help="allow re-running a spent held-out set (history only)")
    ap.add_argument("--v4-fresh", action="store_true", help="v4 fresh set (spent after the v4.0 run; needs --historical-rerun)")
    ap.add_argument("--profile", choices=list(PROFILES), default="current",
                    help="engine configuration: current, or an earlier one pinned for reproduction")
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()
    split = "v4_fresh" if args.v4_fresh else "final" if args.final else args.split
    if split == "final" and int(ENGINE_VERSION.split(".")[0]) >= 4 and not args.historical_rerun:
        raise SystemExit("The v3 final set was already used for the v3 evaluation and is not an independent test for "
                         f"engine {ENGINE_VERSION}. Add --historical-rerun to re-run it for history only.")
    if split == "v4_fresh" and not args.historical_rerun:
        raise SystemExit("The v4 fresh set was used for the v4.0 evaluation and inspected afterwards; it is no longer an "
                         "independent test. Add --historical-rerun to re-run it for history only.")

    t0 = time.time()
    data = load_dataset()
    backend = EmbeddingBackend() if args.backend == "embedding" else TfidfBackend()
    dev_rows, cfg = run_engine(list(iter_answers(data, "dev")), backend, args.profile)
    if split == "dev":
        rows = dev_rows
    elif split == "seen-test":
        rows, _ = run_engine(list(iter_answers(data, "test")), backend, args.profile)
    elif split == "final":
        rows, _ = run_engine(list(iter_answers(load_final_set(), "final")), backend, args.profile)
    else:  # v4_fresh
        rows, _ = run_engine(list(iter_answers(load_v4_fresh_set(), "v4_fresh")), backend, args.profile)

    kw = fit_linear(dev_rows, lambda r: keyword_overlap(r["_q"], r["text"]))
    hol = fit_linear(dev_rows, lambda r: r["holistic"])

    def base(fn):
        return score_metrics([fn(r) for r in rows], [r["gold"] for r in rows], [r["max"] for r in rows])

    errors = sorted(rows, key=lambda r: -abs(r["pred"] - r["gold"]))
    payload = {
        "split": split, "backend": backend.name, "model_name": backend.model_name, "profile": args.profile,
        "historical_rerun": bool(args.historical_rerun),
        "note": ("HISTORICAL RERUN of a spent held-out set - not an independent test. " if args.historical_rerun else "")
                + SPLIT_NOTES[split]
                + (f" Configuration profile '{args.profile}' (engine code {ENGINE_VERSION} with later features switched off)."
                   if args.profile != "current" else ""),
        "engine_version": ENGINE_VERSION, "config": cfg.to_dict(), "config_fingerprint": cfg.fingerprint(),
        "n_answers": len(rows), "n_questions": len({r["question"] for r in rows}),
        "max_marks_range": [min(r["max"] for r in rows), max(r["max"] for r in rows)],
        "engine": summarise(rows),
        "baselines": {"keyword_overlap": base(kw), "holistic_cosine": base(hol)},
        "largest_errors": [{k: r[k] for k in ("id", "type", "gold", "pred", "flags")} for r in errors
                           if abs(r["pred"] - r["gold"]) >= 1],
        "per_answer": [{k: v for k, v in r.items() if k not in ("_q", "text")} for r in rows],
        "seconds": round(time.time() - t0, 1),
    }
    stem = f"evaluation_{backend.name}_{split}{report_tag(args.profile)}"
    write_json(f"{stem}.json", payload)
    result_path(f"{stem}.md").write_text(markdown_report(payload), encoding="utf-8")

    s, c = payload["engine"]["scores"], payload["engine"]["concepts"]
    kb, hb = payload["baselines"]["keyword_overlap"], payload["baselines"]["holistic_cosine"]
    print(f"[{split}] n={len(rows)} engine MAE={s['mae']:.3f} RMSE={s['rmse']:.3f} exact={s['exact_agreement']:.1%} "
          f"within1={s['within_1_0']:.1%} | concept acc={c['accuracy']:.1%} kappa={c['linear_weighted_kappa']:.3f} | "
          f"baselines MAE: keyword={kb['mae']:.3f} (within1 {kb['within_1_0']:.1%}) holistic={hb['mae']:.3f}")
    rf = payload["engine"]["review_flags"]
    print(f"review flags: flagged n={rf['flagged_n']} MAE={fmt(rf['flagged_mae'])} | "
          f"not flagged n={rf['not_flagged_n']} MAE={fmt(rf['not_flagged_mae'])}")
    print("safeguards:", payload["engine"]["correctness_safeguards"])
    if args.show_errors:
        for r in errors:
            if abs(r["pred"] - r["gold"]) >= 1:
                print(f"  {r['id']:7} {r['type']:24} human={r['gold']:<4g} engine={r['pred']:<4g} {r['flags']}")
    print(f"saved {stem}.json/.md in {payload['seconds']}s")


if __name__ == "__main__":
    main()
