"""Tooling for a consent-based evaluation on REAL student answers (docs/REAL_STUDENT_EVALUATION_PROTOCOL.md).

No real data ships with this repository. A study lives in its own directory OUTSIDE the repository
(only ``backend/evaluation/study_data/``, which is git-ignored, is tolerated inside it). The steps enforce
the protocol's order; each one refuses to run when an earlier one is incomplete.

    python -m evaluation.real_study init       --study DIR                       # copy study_templates/ into DIR
    python -m evaluation.real_study check-pii  --study DIR --names names.txt     # de-identification check (recorded)
    python -m evaluation.real_study agreement  --study DIR                       # teacher agreement + adjudication worklist
    python -m evaluation.real_study freeze     --study DIR                       # reference marks + engine + criteria lock (once)
    python -m evaluation.real_study score      --study DIR                       # model vs reference (once)
    python -m evaluation.real_study verify     --study DIR --set-hash H [--report-hash H]  # supervisor integrity check
    python -m evaluation.real_study status     --study DIR                       # what is still pending (B1-B3, B5)

Study directory:
    manifest.json               approval, consent, purpose, retention, markers (blind-marking declarations)
    acceptance_criteria.json    pre-registered pass/fail thresholds, approved by the project team / faculty
    questions.json              questions + rubrics (+ question_type)
    answers.csv                 answer_id, question_id, answer_text - pseudonymous ids only
    marks_<marker>.csv          answer_id, concept_id, level (M | P | X) - one file per manifest marker, marked independently
    adjudication.csv            answer_id, concept_id, final_level, adjudicator_id, reason - for every disagreement
Outputs (inside the study directory, never in the repository):
    pii_check.json, agreement.json, adjudication_worklist.csv, study_set.json + study_set.sha256,
    SCORED.json, results/score_report.{json,md}
Reports contain ids, marks and metrics only - never answer text.

What local files cannot enforce: someone with write access can delete SCORED.json and results/ and score
again. The protocol therefore requires sending the freeze hash and the score-report hash to the faculty
supervisor when they are produced (an external record).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from evaluation.common import DATASET, V3_PROFILE, V40_PROFILE, iter_answers, load_dataset
from evaluation.stats import bootstrap_ci, paired_difference_ci

TEMPLATES = Path(__file__).resolve().parent / "study_templates"
REPO_ROOT = Path(__file__).resolve().parents[2]
IGNORED_DATA_DIR = Path(__file__).resolve().parent / "study_data"
LEVELS = {"M": 1.0, "P": 0.5, "X": 0.0}
REQUIRED_MANIFEST = ("study_id", "institution", "ethics_approval_reference", "consent_procedure", "purpose",
                     "data_controller", "retention_until", "deletion_procedure", "manual_pii_review")
MIN_SUBGROUP_N = 20
MIN_CLUSTERS_FOR_CI = 5
COMPARISON_RULES = ("ci_upper_below_zero", "point_estimate_not_worse", "report_only")
# criterion -> (kind, allowed range / values). Values are chosen and approved by the project team, never defaulted.
CRITERIA_SPEC = {
    "min_answers": ("int", (1, None)),
    "min_questions": ("int", (1, None)),
    "min_answers_per_question": ("int", (1, None)),
    "min_teacher_concept_kappa": ("num", (-1, 1)),
    "min_teacher_within_1": ("num", (0, 1)),
    "max_normalised_mae_ci_upper": ("num", (0, 1)),
    "min_within_1_ci_lower": ("num", (0, 1)),
    "max_mae_ratio_to_teacher_mae": ("num", (0, None)),
    "max_severe_error_share": ("num", (0, 1)),
    "max_severe_error_share_per_question_type": ("num", (0, 1)),
    "keyword_baseline_rule": ("rule", COMPARISON_RULES),
    "v3_rule": ("rule", COMPARISON_RULES),
    "require_flagged_mae_above_unflagged": ("bool", None),
}
REQUIRED_ATTESTATIONS = ("pilot_deployment_requires_review_before_publish", "students_informed_marks_are_teacher_decided")

_PII = {
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone number": re.compile(r"(?<!\w)(?:\+?\d[\s-]?){10,13}(?!\w)"),
    "URL": re.compile(r"https?://\S+|www\.\S+", re.I),
    "ID-like number (6+ digits)": re.compile(r"(?<![\d.])\d{6,}(?![\d.])"),
    "roll/registration number": re.compile(r"\b\d{2}[A-Z]{2,5}\d{3,6}\b"),
    "self-identification": re.compile(r"\b(?:my name is|i am called|roll no|roll number|student id|enrol(?:l)?ment no)\b", re.I),
}


class StudyError(SystemExit):
    pass


# --- loading and validation -------------------------------------------------------------------

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise StudyError(f"missing file: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _sha256_file(path: Path) -> str:
    """SHA-256 of the file's exact bytes - the same value `sha256sum` / `Get-FileHash` print. No line-ending
    normalisation: a file re-saved with different line endings is a different file (security audit F8)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _placeholders(obj, path="") -> list[str]:
    """Template values ("<...>") left in a JSON document (keys starting with "_" are comments)."""
    if isinstance(obj, str):
        return [path] if obj.strip().startswith("<") else []
    if isinstance(obj, dict):
        return [p for k, v in obj.items() if not str(k).startswith("_") for p in _placeholders(v, f"{path}.{k}".strip("."))]
    if isinstance(obj, list):
        return [p for i, v in enumerate(obj) for p in _placeholders(v, f"{path}[{i}]")]
    return []


def check_location(study: Path) -> None:
    s = study.resolve()
    inside_repo = s == REPO_ROOT or REPO_ROOT in s.parents
    in_ignored = s == IGNORED_DATA_DIR or IGNORED_DATA_DIR in s.parents
    if inside_repo and not in_ignored:
        raise StudyError(f"the study directory {s} is inside the repository. Keep real student data outside it "
                         f"(or, at most, under the git-ignored {IGNORED_DATA_DIR}).")


def load_manifest(study: Path) -> dict:
    check_location(study)
    path = study / "manifest.json"
    if not path.exists():
        raise StudyError("missing manifest.json (copy it from the templates with `init`)")
    m = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_MANIFEST if not str(m.get(k, "")).strip() or str(m.get(k)).strip().startswith("<")]
    if missing:
        raise StudyError(f"manifest.json is incomplete: {', '.join(missing)}")
    if (ph := _placeholders(m)):
        raise StudyError(f"manifest.json still contains template placeholders: {', '.join(ph[:5])}")
    if m.get("consent_obtained_for_all_answers") is not True:
        raise StudyError("manifest.json: consent_obtained_for_all_answers must be true. Answers without informed consent "
                         "must be removed before any further step.")
    try:
        retention = date.fromisoformat(m["retention_until"])
    except ValueError:
        raise StudyError("manifest.json: retention_until must be a date (YYYY-MM-DD)") from None
    if retention < date.today():
        raise StudyError(f"retention period ended on {m['retention_until']}: delete the study data as the manifest requires.")
    markers = m.get("markers") or []
    ids = [str(x.get("id", "")).strip() for x in markers]
    if len(markers) < 2 or len(set(ids)) != len(ids) or not all(ids):
        raise StudyError("manifest.json: list at least two markers with distinct ids")
    unblind = [i for i, x in zip(ids, markers)
               if x.get("blind_to_model_scores") is not True or x.get("blind_to_other_marker") is not True]
    if unblind:
        raise StudyError(f"manifest.json: markers {unblind} are not declared blind to model scores and to the other "
                         "marker; their marks cannot serve as an independent reference.")
    return m


APPROVAL_FIELDS = ("approved_by", "approved_on", "approval_evidence")


def _read_criteria(study: Path) -> dict:
    path = study / "acceptance_criteria.json"
    if not path.exists():
        raise StudyError("missing acceptance_criteria.json: the pass/fail criteria must be written and approved before freezing")
    return json.loads(path.read_text(encoding="utf-8"))


def criteria_field_problems(c: dict) -> list[str]:
    """The 13 values and the attestations are filled in and valid. Says nothing about approval."""
    problems = []
    vals = c.get("criteria") or {}
    for name, (kind, rng) in CRITERIA_SPEC.items():
        v = vals.get(name)
        if v is None:
            problems.append(f"{name} is not set")
        elif kind == "bool" and not isinstance(v, bool):
            problems.append(f"{name} must be true or false")
        elif kind == "rule" and v not in rng:
            problems.append(f"{name} must be one of {rng}")
        elif kind in ("int", "num"):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or (kind == "int" and int(v) != v):
                problems.append(f"{name} must be a number")
            elif (rng[0] is not None and v < rng[0]) or (rng[1] is not None and v > rng[1]):
                problems.append(f"{name}={v} is outside {rng}")
    att = c.get("attestations") or {}
    problems += [f"attestation {a} must be true" for a in REQUIRED_ATTESTATIONS if att.get(a) is not True]
    return problems


def approval_documentation_problems(c: dict) -> list[str]:
    """An approval is DOCUMENTED: who approved, when, and a reference to the approval evidence (signed minutes,
    e-mail, document id). Software cannot check that the evidence is genuine - that is independent verification."""
    problems = [f"{k} is missing or a placeholder" for k in APPROVAL_FIELDS
                if not str(c.get(k) or "").strip() or str(c.get(k)).strip().startswith("<")]
    if "approved_on is missing or a placeholder" not in problems:
        try:
            date.fromisoformat(c["approved_on"])
        except (KeyError, ValueError):
            problems.append("approved_on must be a date (YYYY-MM-DD)")
    return problems


def load_criteria(study: Path) -> dict:
    """Required by freeze: all criteria fields AND documented approval evidence."""
    c = _read_criteria(study)
    problems = criteria_field_problems(c) + approval_documentation_problems(c)
    if problems:
        raise StudyError("acceptance_criteria.json is not complete with documented approval: " + "; ".join(problems))
    return c


def load_questions(study: Path) -> dict[str, dict]:
    data = json.loads((study / "questions.json").read_text(encoding="utf-8"))
    if (ph := _placeholders(data)):
        raise StudyError(f"questions.json still contains template placeholders: {ph[:5]}")
    out = {}
    for q in data["questions"]:
        if q["id"] in out:
            raise StudyError(f"duplicate question id {q['id']}")
        ids = [c["id"] for c in q["rubric"]]
        if len(set(ids)) != len(ids):
            raise StudyError(f"question {q['id']}: duplicate rubric concept ids")
        total_marks = sum(c["marks"] for c in q["rubric"])
        if abs(total_marks - q["max_marks"]) > 1e-9:
            raise StudyError(f"question {q['id']}: rubric marks {total_marks:g} != max_marks {q['max_marks']:g}")
        out[q["id"]] = q
    return out


def load_answers(study: Path, questions: dict) -> list[dict]:
    rows = _read_csv(study / "answers.csv")
    seen = set()
    for r in rows:
        if r["answer_id"] in seen:
            raise StudyError(f"duplicate answer_id {r['answer_id']}")
        if r["question_id"] not in questions:
            raise StudyError(f"answer {r['answer_id']}: unknown question_id {r['question_id']}")
        seen.add(r["answer_id"])
    return rows


def load_marks(study: Path, questions: dict, answers: list[dict], manifest: dict) -> dict[str, dict[tuple[str, str], str]]:
    """{marker_id: {(answer_id, concept_id): level}}: exactly one file per manifest marker, each covering every
    concept of every answer exactly once."""
    declared = sorted(str(x["id"]) for x in manifest["markers"])
    files = {f.stem[len("marks_"):]: f for f in sorted(study.glob("marks_*.csv"))}
    if sorted(files) != declared:
        raise StudyError(f"marks files {sorted(files)} do not match the markers declared in manifest.json {declared}")
    expected = {(a["answer_id"], c["id"]) for a in answers for c in questions[a["question_id"]]["rubric"]}
    out = {}
    for marker, f in files.items():
        marks = {}
        for r in _read_csv(f):
            lvl = r["level"].upper()
            if lvl not in LEVELS:
                raise StudyError(f"{f.name}: level must be M, P or X (got {r['level']!r})")
            key = (r["answer_id"], r["concept_id"])
            if key in marks:
                raise StudyError(f"{f.name}: {key[0]}/{key[1]} is marked more than once")
            marks[key] = lvl
        if set(marks) != expected:
            gap = sorted(expected - set(marks))[:5]
            extra = sorted(set(marks) - expected)[:5]
            raise StudyError(f"{f.name}: marks do not cover exactly every (answer, concept); missing {gap} extra {extra}")
        out[marker] = marks
    return out


def total(q: dict, levels: dict[str, str]) -> float:
    return sum(c["marks"] * LEVELS[levels[c["id"]]] for c in q["rubric"])


def frozen_engine() -> dict:
    """Identity of the scoring engine that the study is frozen against."""
    from app.nlp import EvaluationConfig
    from app.nlp.config import DEFAULT_MODEL, ENGINE_VERSION

    # The repository is not guaranteed to be under version control, so the engine's source code itself is hashed:
    # an edit to the NLP package that does not bump the version or change the config is still detected.
    nlp_dir = REPO_ROOT / "backend" / "app" / "nlp"
    h = hashlib.sha256()
    for f in sorted(nlp_dir.glob("*.py")):
        h.update(f.name.encode() + b"\0" + f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return {"engine_version": ENGINE_VERSION, "model": DEFAULT_MODEL, "backend": "embedding",
            "config_fingerprint": EvaluationConfig.for_backend("embedding").fingerprint(),
            "nlp_source_sha256": h.hexdigest()}


# --- steps ---------------------------------------------------------------------------------

def cmd_init(study: Path) -> None:
    check_location(study)
    study.mkdir(parents=True, exist_ok=True)
    for f in TEMPLATES.iterdir():
        target = study / f.name.replace(".template", "")
        if target.exists():
            print(f"kept existing {target.name}")
            continue
        shutil.copy(f, target)
        print(f"created {target.name}")


def find_pii(text: str, names: list[str]) -> list[str]:
    hits = [label for label, rx in _PII.items() if rx.search(text)]
    low = text.lower()
    hits += [f"listed name '{n}'" for n in names if re.search(rf"\b{re.escape(n.lower())}\b", low)]
    return hits


def cmd_check_pii(study: Path, names_file: Path | None) -> list[tuple[str, list[str]]]:
    load_manifest(study)
    names = [n.strip() for n in names_file.read_text(encoding="utf-8").splitlines() if n.strip()] if names_file else []
    answers = _read_csv(study / "answers.csv")
    found = [(a["answer_id"], h) for a in answers if (h := find_pii(a["answer_text"], names))]
    for aid, h in found:
        print(f"  {aid}: {', '.join(h)}")
    passed = not found and bool(names)
    (study / "pii_check.json").write_text(json.dumps({
        "answers_sha256": _sha256_file(study / "answers.csv"), "names_listed": len(names), "findings": len(found),
        "passed": passed, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2), encoding="utf-8")
    print(f"{len(found)} of {len(answers)} answers contain possible identifying information"
          + (" - remove or redact it, then run check-pii again." if found else "."))
    if not names:
        print("NOT PASSED: --names with the class's names is required; regexes cannot recognise names on their own.")
    elif passed:
        print("passed and recorded in pii_check.json (valid only for this exact answers.csv).")
    return found


def agreement_report(questions: dict, answers: list[dict], marks: dict) -> tuple[dict, list[dict]]:
    from sklearn.metrics import cohen_kappa_score

    markers = sorted(marks)
    a, b = markers[0], markers[1]
    keys = sorted(marks[a])
    la = [marks[a][k] for k in keys]
    lb = [marks[b][k] for k in keys]
    order = {"X": 0, "P": 1, "M": 2}
    totals = {m: [] for m in (a, b)}
    for ans in answers:
        q = questions[ans["question_id"]]
        for m in (a, b):
            totals[m].append(total(q, {c["id"]: marks[m][(ans["answer_id"], c["id"])] for c in q["rubric"]}))
    ta, tb = np.array(totals[a]), np.array(totals[b])
    diff = np.abs(ta - tb)
    if len(set(la) | set(lb)) > 1:
        kappa = float(cohen_kappa_score([order[x] for x in la], [order[y] for y in lb], weights="linear"))
    else:
        kappa = float("nan")
    report = {
        "markers": markers, "compared": [a, b], "n_answers": len(answers), "n_concept_decisions": len(keys),
        "concept_exact_agreement": float(np.mean([x == y for x, y in zip(la, lb)])),
        # kappa is undefined when both teachers used a single level throughout (no variation to agree on)
        "concept_linear_weighted_kappa": None if math.isnan(kappa) else kappa,
        "question_total_mae_between_markers": float(diff.mean()),
        "question_total_exact": float(np.mean(diff < 1e-9)),
        "question_total_within_1": float(np.mean(diff <= 1 + 1e-9)),
        "question_total_pearson": float(np.corrcoef(ta, tb)[0, 1]) if ta.std() and tb.std() else None,
        "concept_disagreements": int(sum(x != y for x, y in zip(la, lb))),
    }
    worklist = [{"answer_id": k[0], "concept_id": k[1], f"level_{a}": marks[a][k], f"level_{b}": marks[b][k]}
                for k in keys if marks[a][k] != marks[b][k]]
    if len(markers) > 2:  # every other marker is also compared with the first; any disagreement goes to adjudication
        for m in markers[2:]:
            for k in keys:
                if marks[m][k] != marks[a][k] and not any((w["answer_id"], w["concept_id"]) == k for w in worklist):
                    worklist.append({"answer_id": k[0], "concept_id": k[1], f"level_{a}": marks[a][k], f"level_{m}": marks[m][k]})
    return report, worklist


def _fmt(x, pattern="{:.3f}"):
    return "undefined" if x is None else pattern.format(x)


def cmd_agreement(study: Path) -> dict:
    manifest = load_manifest(study)
    questions = load_questions(study)
    answers = load_answers(study, questions)
    report, worklist = agreement_report(questions, answers, load_marks(study, questions, answers, manifest))
    (study / "agreement.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (study / "adjudication_worklist.csv").open("w", encoding="utf-8", newline="") as f:
        fields = sorted({k for w in worklist for k in w}, key=lambda k: (k not in ("answer_id", "concept_id"), k))
        w = csv.DictWriter(f, fieldnames=fields or ["answer_id", "concept_id"])
        w.writeheader()
        w.writerows(worklist)
    print(f"teacher agreement: concept exact {report['concept_exact_agreement']:.1%}, weighted kappa "
          f"{_fmt(report['concept_linear_weighted_kappa'])}; question totals MAE "
          f"{report['question_total_mae_between_markers']:.3f}, within +-1 {report['question_total_within_1']:.1%}. "
          f"{len(worklist)} concept decision(s) need adjudication (adjudication_worklist.csv).")
    return report


def _normalise(t: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


def cmd_freeze(study: Path) -> Path:
    manifest = load_manifest(study)
    out, out_hash = study / "study_set.json", study / "study_set.sha256"
    if out.exists() or out_hash.exists():
        raise StudyError("study_set.json is already frozen; a frozen set is never rebuilt. Start a new study for new data.")
    criteria = load_criteria(study)
    questions = load_questions(study)
    answers = load_answers(study, questions)
    pii = json.loads((study / "pii_check.json").read_text(encoding="utf-8")) if (study / "pii_check.json").exists() else {}
    if not pii.get("passed") or pii.get("answers_sha256") != _sha256_file(study / "answers.csv"):
        raise StudyError("no passing de-identification check for the current answers.csv: run `check-pii --names ...` "
                         "after the last edit of answers.csv")
    marks = load_marks(study, questions, answers, manifest)
    report, worklist = agreement_report(questions, answers, marks)
    adjudicated = {}
    if worklist:
        for r in _read_csv(study / "adjudication.csv"):
            if r["final_level"].upper() not in LEVELS or not r.get("adjudicator_id") or not r.get("reason"):
                raise StudyError(f"adjudication.csv: {r['answer_id']}/{r['concept_id']} needs final_level (M/P/X), "
                                 "adjudicator_id and reason")
            adjudicated[(r["answer_id"], r["concept_id"])] = r["final_level"].upper()
        open_items = [(w["answer_id"], w["concept_id"]) for w in worklist if (w["answer_id"], w["concept_id"]) not in adjudicated]
        if open_items:
            raise StudyError(f"{len(open_items)} disagreement(s) are not adjudicated yet, e.g. {open_items[:5]}")
    # Development data must never contain study answers (and vice versa).
    dev_texts = {_normalise(a["text"]) for _, a in iter_answers(load_dataset(DATASET), "all")} - {""}
    if (leak := [a["answer_id"] for a in answers if _normalise(a["answer_text"]) in dev_texts]):
        raise StudyError(f"answers {leak[:10]} also appear in the development dataset; remove them from one of the two")
    first = sorted(marks)[0]
    by_q = defaultdict(list)
    for a in answers:
        q = questions[a["question_id"]]
        labels = {}
        for c in q["rubric"]:
            k = (a["answer_id"], c["id"])
            levels = {marks[m][k] for m in marks}
            labels[c["id"]] = marks[first][k] if len(levels) == 1 else adjudicated[k]
        by_q[q["id"]].append({
            "id": a["answer_id"], "type": q.get("question_type", "unspecified"), "text": a["answer_text"],
            "labels": labels, "human_score": total(q, labels),
            "marker_scores": {m: total(q, {c["id"]: marks[m][(a["answer_id"], c["id"])] for c in q["rubric"]}) for m in marks},
        })
    payload = {
        "name": f"real-student study {manifest['study_id']}", "synthetic": False, "label_scheme": LEVELS,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "teacher_agreement": report,
        "frozen_engine": frozen_engine(),
        "acceptance_criteria_sha256": _sha256_file(study / "acceptance_criteria.json"),
        "acceptance_criteria": criteria,
        "questions": [{**{k: v for k, v in q.items() if k != "answers"}, "split": "real_study", "answers": by_q[qid]}
                      for qid, q in questions.items() if by_q[qid]],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    out_hash.write_text(f"{digest}  study_set.json\n", encoding="utf-8", newline="\n")
    print(f"frozen {sum(len(v) for v in by_q.values())} answers against engine {payload['frozen_engine']['engine_version']} "
          f"(config {payload['frozen_engine']['config_fingerprint']}); sha256 {digest}.\n"
          "Send this hash to the faculty supervisor now, before scoring (external record).")
    return out


def load_study_set(study: Path) -> dict:
    raw = (study / "study_set.json").read_bytes()
    expected = (study / "study_set.sha256").read_text(encoding="utf-8").split()[0]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise StudyError("study_set.json changed after it was frozen; its results would not be valid.")
    return json.loads(raw.decode("utf-8"))


def _keyword_baseline():
    """Keyword-overlap baseline fitted on the DEV split only (never on study data)."""
    from evaluation.evaluate import keyword_overlap

    dev = list(iter_answers(load_dataset(DATASET), "dev"))
    x = np.array([keyword_overlap(q, a["text"]) for q, a in dev])
    y = np.array([a["human_score"] / q["max_marks"] for q, a in dev])
    slope, icpt = np.polyfit(x, y, 1)
    return lambda q, text: float(np.clip(np.floor((slope * keyword_overlap(q, text) + icpt) * q["max_marks"] / 0.5 + 0.5) * 0.5,
                                         0, q["max_marks"]))


def _metrics(pred, gold, maxm, clusters, n_boot):
    ci = bootstrap_ci(pred, gold, maxm, clusters, n_boot=n_boot)
    if ci["clusters"] < MIN_CLUSTERS_FOR_CI:
        ci["ci_warning"] = (f"only {ci['clusters']} question(s): the question-level bootstrap interval is unreliable "
                            f"(zero width with one question); at least {MIN_CLUSTERS_FOR_CI} questions are needed")
    e = np.asarray(pred) - np.asarray(gold)
    return {**ci, "mean_signed_error": float(e.mean()), "severe_errors_ge_2": int((np.abs(e) >= 2 - 1e-9).sum()),
            "severe_error_share": float(np.mean(np.abs(e) >= 2 - 1e-9)), "exact": float(np.mean(np.abs(e) < 1e-9))}


def _comparison(rule: str, diff: dict) -> tuple[str, str]:
    d, (lo, hi) = diff["mae_difference"], diff["ci"]
    if rule == "report_only":
        return "REPORTED", f"difference {d:+.3f} [{lo:+.3f}, {hi:+.3f}] (no pass/fail rule)"
    ok = hi < 0 if rule == "ci_upper_below_zero" else d <= 0
    return ("PASS" if ok else "FAIL"), f"difference {d:+.3f} [{lo:+.3f}, {hi:+.3f}], rule {rule}"


def evaluate_criteria(c: dict, r: dict, qtypes: list[str], qids: list[str]) -> dict:
    """PASS / FAIL / NOT_EVALUABLE per pre-registered criterion, and the overall outcome."""
    eng, ta = r["systems"]["engine (current)"], r["teacher_agreement"]
    res = {}

    def put(name, status, detail):
        res[name] = {"status": status, "detail": detail}

    per_q = min(qids.count(q) for q in set(qids))
    put("min_answers", "PASS" if r["n_answers"] >= c["min_answers"] else "FAIL", f"{r['n_answers']} vs >= {c['min_answers']}")
    put("min_questions", "PASS" if r["n_questions"] >= c["min_questions"] else "FAIL", f"{r['n_questions']} vs >= {c['min_questions']}")
    put("min_answers_per_question", "PASS" if per_q >= c["min_answers_per_question"] else "FAIL",
        f"smallest question has {per_q} vs >= {c['min_answers_per_question']}")
    k = ta["concept_linear_weighted_kappa"]
    put("min_teacher_concept_kappa", "NOT_EVALUABLE" if k is None else ("PASS" if k >= c["min_teacher_concept_kappa"] else "FAIL"),
        f"{_fmt(k)} vs >= {c['min_teacher_concept_kappa']}")
    put("min_teacher_within_1", "PASS" if ta["question_total_within_1"] >= c["min_teacher_within_1"] else "FAIL",
        f"{ta['question_total_within_1']:.3f} vs >= {c['min_teacher_within_1']}")
    ci_ok = "ci_warning" not in eng
    hi = eng["normalised_mae"]["ci"][1]
    put("max_normalised_mae_ci_upper", "NOT_EVALUABLE" if not ci_ok else ("PASS" if hi <= c["max_normalised_mae_ci_upper"] else "FAIL"),
        f"upper CI {hi:.3f} vs <= {c['max_normalised_mae_ci_upper']}" + ("" if ci_ok else f" ({eng['ci_warning']})"))
    lo = eng["within_1"]["ci"][0]
    put("min_within_1_ci_lower", "NOT_EVALUABLE" if not ci_ok else ("PASS" if lo >= c["min_within_1_ci_lower"] else "FAIL"),
        f"lower CI {lo:.3f} vs >= {c['min_within_1_ci_lower']}" + ("" if ci_ok else f" ({eng['ci_warning']})"))
    tm = ta["question_total_mae_between_markers"]
    ratio = eng["mae"]["estimate"] / tm if tm > 0 else None
    put("max_mae_ratio_to_teacher_mae", "NOT_EVALUABLE" if ratio is None else ("PASS" if ratio <= c["max_mae_ratio_to_teacher_mae"] else "FAIL"),
        f"model MAE / teacher-teacher MAE = {_fmt(ratio)} vs <= {c['max_mae_ratio_to_teacher_mae']}")
    put("max_severe_error_share", "PASS" if eng["severe_error_share"] <= c["max_severe_error_share"] else "FAIL",
        f"{eng['severe_error_share']:.3f} vs <= {c['max_severe_error_share']}")
    big = {t: v for t, v in r["subgroups"]["question_type"].items() if v["reported"]}
    if not big:
        put("max_severe_error_share_per_question_type", "NOT_EVALUABLE", f"no question type has n >= {MIN_SUBGROUP_N}")
    else:
        worst = max(big, key=lambda t: big[t]["severe_error_share"])
        s = big[worst]["severe_error_share"]
        put("max_severe_error_share_per_question_type", "PASS" if s <= c["max_severe_error_share_per_question_type"] else "FAIL",
            f"worst type '{worst}' {s:.3f} vs <= {c['max_severe_error_share_per_question_type']}"
            f" ({len(r['subgroups']['question_type']) - len(big)} type(s) below n={MIN_SUBGROUP_N} not checked)")
    for name, other in (("keyword_baseline_rule", "keyword baseline (dev-fitted)"), ("v3_rule", "v3 profile")):
        diff = r["paired_differences"][f"engine (current) - {other}"]
        status, detail = _comparison(c[name], diff)
        if status != "REPORTED" and not ci_ok and c[name] == "ci_upper_below_zero":
            status, detail = "NOT_EVALUABLE", detail + f" ({eng['ci_warning']})"
        put(name, status, detail)
    rf = r["review_flags"]
    if c["require_flagged_mae_above_unflagged"]:
        if rf["flagged_mae"] is None or rf["not_flagged_mae"] is None:
            put("require_flagged_mae_above_unflagged", "NOT_EVALUABLE", "all or no answers were flagged")
        else:
            put("require_flagged_mae_above_unflagged", "PASS" if rf["flagged_mae"] > rf["not_flagged_mae"] else "FAIL",
                f"flagged {rf['flagged_mae']:.3f} vs unflagged {rf['not_flagged_mae']:.3f}")
    statuses = [v["status"] for v in res.values()]
    sample_ok = all(res[k]["status"] == "PASS" for k in ("min_answers", "min_questions", "min_answers_per_question"))
    if "FAIL" in statuses and sample_ok:
        overall = "NOT MET"
    elif not sample_ok or "NOT_EVALUABLE" in statuses:
        overall = "INCONCLUSIVE"
    else:
        overall = "MET"
    return {"overall": overall, "criteria": res,
            "meaning": "MET = the pre-registered conditions for continuing a teacher-reviewed pilot are satisfied on this "
                       "sample. It is not a certification of grading accuracy and never permits unreviewed grading."}


def cmd_score(study: Path, historical_rerun: bool = False, backend=None, n_boot: int = 10000) -> dict:
    from app.nlp import EvaluationConfig, QuestionSpec, evaluate_answer
    from app.nlp.similarity import EmbeddingBackend

    load_manifest(study)
    data = load_study_set(study)
    results = study / "results"
    report_path, marker = results / "score_report.json", study / "SCORED.json"
    already = report_path.exists() or marker.exists()
    if already and not historical_rerun:
        raise StudyError("this study set was already scored; it is no longer an independent test. Use --historical-rerun "
                         "to reproduce it (written to score_report_rerun.*).")
    if historical_rerun and not already:
        raise StudyError("--historical-rerun was given but this set has never been scored; run `score` without it.")
    if _sha256_file(study / "acceptance_criteria.json") != data["acceptance_criteria_sha256"]:
        raise StudyError("acceptance_criteria.json changed after freezing; criteria cannot be changed once the set is frozen.")
    frozen = data["frozen_engine"]
    if frozen_engine() != frozen:
        raise StudyError(f"the installed engine {frozen_engine()} differs from the engine the study was frozen against "
                         f"{frozen}; check out the frozen version before scoring.")
    backend = backend or EmbeddingBackend()
    if backend.name != "embedding" or backend.model_name != frozen["model"]:
        raise StudyError(f"scoring needs the frozen embedding model {frozen['model']} (got {backend.name} / "
                         f"{backend.model_name}); the TF-IDF fallback is not the frozen system.")
    systems = {"engine (current)": {}, "v4.0 profile": V40_PROFILE, "v3 profile": V3_PROFILE}
    pairs = [(q, a) for q in data["questions"] for a in q["answers"]]
    gold = [a["human_score"] for _, a in pairs]
    maxm = [q["max_marks"] for q, _ in pairs]
    qids = [q["id"] for q, _ in pairs]
    qtypes = [q.get("question_type", "unspecified") for q, _ in pairs]
    preds, flagged = {}, []
    for name, profile in systems.items():
        cfg = EvaluationConfig.for_backend(backend.name, **profile)
        res = [evaluate_answer(QuestionSpec.from_dict(q), a["text"], cfg, backend) for q, a in pairs]
        preds[name] = [r.suggested_score for r in res]
        if name == "engine (current)":
            flagged = [r.needs_review for r in res]
    kw = _keyword_baseline()
    preds["keyword baseline (dev-fitted)"] = [kw(q, a["text"]) for q, a in pairs]
    out = {
        "study": data["name"], "set_sha256": (study / "study_set.sha256").read_text(encoding="utf-8").split()[0],
        "historical_rerun": historical_rerun, "frozen_engine": frozen,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_answers": len(pairs), "n_questions": len(set(qids)), "max_marks": sorted(set(maxm)),
        "question_types": {t: qtypes.count(t) for t in sorted(set(qtypes))},
        "teacher_agreement": data["teacher_agreement"],
        "systems": {k: _metrics(v, gold, maxm, qids, n_boot) for k, v in preds.items()},
        "paired_differences": {
            f"engine (current) - {other}": paired_difference_ci(preds["engine (current)"], preds[other], gold, qids, n_boot=n_boot)
            for other in preds if other != "engine (current)"
        },
        "review_flags": {
            "flagged_n": int(sum(flagged)), "not_flagged_n": int(len(flagged) - sum(flagged)),
            "flagged_mae": float(np.mean([abs(p - g) for p, g, f in zip(preds["engine (current)"], gold, flagged) if f]))
            if any(flagged) else None,
            "not_flagged_mae": float(np.mean([abs(p - g) for p, g, f in zip(preds["engine (current)"], gold, flagged) if not f]))
            if not all(flagged) else None,
        },
        "subgroups": {},
        "per_answer": [{"id": a["id"], "question": q["id"], "gold": a["human_score"],
                        **{k: v[i] for k, v in preds.items()}, "needs_review": flagged[i]} for i, (q, a) in enumerate(pairs)],
    }
    for key, groups in (("question_type", qtypes), ("question", qids)):
        sub = {}
        for g in sorted(set(groups)):
            idx = [i for i, x in enumerate(groups) if x == g]
            if len(idx) < MIN_SUBGROUP_N:
                sub[g] = {"n": len(idx), "reported": False, "reason": f"n < {MIN_SUBGROUP_N}"}
                continue
            e = np.array([preds["engine (current)"][i] - gold[i] for i in idx])
            sub[g] = {"n": len(idx), "reported": True, "severe_error_share": float(np.mean(np.abs(e) >= 2 - 1e-9)), **{
                f"{k} mae": float(np.mean([abs(v[i] - gold[i]) for i in idx])) for k, v in preds.items()}}
        out["subgroups"][key] = sub
    out["acceptance"] = evaluate_criteria(data["acceptance_criteria"]["criteria"], out, qtypes, qids)
    results.mkdir(exist_ok=True)
    stem = "score_report_rerun" if historical_rerun else "score_report"
    text = json.dumps(out, indent=2)
    # LF line endings on every platform, so the printed hash equals `sha256sum` of the file the supervisor receives.
    (results / f"{stem}.json").write_text(text, encoding="utf-8", newline="\n")
    (results / f"{stem}.md").write_text(markdown(out), encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not historical_rerun:
        marker.write_text(json.dumps({"scored_at": out["scored_at"], "score_report_sha256": digest,
                                      "set_sha256": out["set_sha256"]}, indent=2), encoding="utf-8", newline="\n")
    print(f"wrote results/{stem}.json and .md (sha256 {digest}); pre-registered criteria: {out['acceptance']['overall']}."
          + ("" if historical_rerun else " Send this report hash to the faculty supervisor now (external record)."))
    return out


def cmd_verify(study: Path, set_hash: str | None, report_hash: str | None) -> bool:
    """Compare the exact bytes of the lock and the report with the hashes the supervisor kept (security audit F7/F8).

    VERIFIED only if: the supervisor's lock hash is given and equals study_set.json; and, whenever a score report or
    SCORED.json exists, the supervisor's report hash is given and equals score_report.json. A matching lock hash alone
    never verifies a report. A match proves file integrity only - NOT consent, blind marking, independent review or
    that the set was scored once."""
    checks: list[tuple[str, bool | None, str]] = []  # (name, ok / None = not verified, detail)
    set_file, set_rec = study / "study_set.json", study / "study_set.sha256"
    report, scored = study / "results" / "score_report.json", study / "SCORED.json"
    if not set_file.exists():
        checks.append(("study_set.json present", False, "missing"))
    else:
        actual = _sha256_file(set_file)
        if set_rec.exists():
            checks.append(("study_set.json matches its own .sha256 file", actual == set_rec.read_text(encoding="utf-8").split()[0], ""))
        if set_hash:
            checks.append(("study_set.json matches the supervisor's lock hash", actual == set_hash.strip().lower(), ""))
        else:
            checks.append(("study_set.json compared with the supervisor's lock hash", None, "pass --set-hash"))
    if report.exists() or scored.exists():
        if not report.exists():
            checks.append(("score_report.json present", False, "SCORED.json exists but the report is missing"))
        else:
            actual = _sha256_file(report)
            if scored.exists():
                rec = json.loads(scored.read_text(encoding="utf-8")).get("score_report_sha256")
                checks.append(("score_report.json matches SCORED.json", actual == rec, ""))
            else:
                checks.append(("SCORED.json present", False, "missing"))
            if report_hash:
                checks.append(("score_report.json matches the supervisor's report hash", actual == report_hash.strip().lower(), ""))
            else:
                checks.append(("score_report.json compared with the supervisor's report hash", None,
                               "a report exists, so --report-hash is required"))
    elif report_hash:
        checks.append(("score_report.json present", False, "the supervisor holds a report hash but no report exists"))
    for name, ok, detail in checks:
        label = "PASS" if ok else ("NOT VERIFIED" if ok is None else "FAIL")
        print(f"[{label:12}] {name}" + (f" ({detail})" if detail else ""))
    failed = any(ok is False for _, ok, _ in checks)
    unverified = any(ok is None for _, ok, _ in checks)
    verdict = "MISMATCH" if failed else ("NOT VERIFIED" if unverified or not checks else "VERIFIED")
    print("File-integrity check only - it does not prove consent, blind marking, independent review or a single scoring run.")
    print(verdict)
    return verdict == "VERIFIED"


NOT_INDEPENDENTLY_VERIFIED = "not independently verified (software cannot verify human approvals; the supervisor must)"


def study_status(study: Path) -> dict:
    """What is pending in a study directory, per blocker. Facts only; approves nothing (security audit F9).

    Each approval-type blocker is reported on three separate levels: fields completed, approval documented,
    approval independently verified. The last level is never set by software."""
    def problems_of(fn):
        try:
            fn()
            return []
        except SystemExit as exc:
            return [str(exc)]
        except (OSError, ValueError, KeyError) as exc:
            return [f"{type(exc).__name__}: {exc}"]

    def level(problems: list[str]) -> str:
        return "yes" if not problems else "no - " + "; ".join(problems)[:300]

    out: dict[str, dict | str] = {}
    try:
        c = _read_criteria(study)
        fields, approval = criteria_field_problems(c), approval_documentation_problems(c)
    except (SystemExit, OSError, ValueError) as exc:
        fields = approval = [str(exc)]
    out["B1 acceptance criteria"] = {"fields completed": level(fields), "approval documented": level(approval),
                                     "approval independently verified": NOT_INDEPENDENTLY_VERIFIED}
    manifest_problems = problems_of(lambda: load_manifest(study))
    out["B2 ethics approval and consent (manifest.json)"] = {
        "fields completed": level(manifest_problems),
        "approval documented": "reference recorded" if not manifest_problems else "no",
        "approval independently verified": NOT_INDEPENDENTLY_VERIFIED}
    pii = study / "pii_check.json"
    pii_state = "no - run check-pii --names"
    if pii.exists():
        p = json.loads(pii.read_text(encoding="utf-8"))
        current = (study / "answers.csv").exists() and p.get("answers_sha256") == _sha256_file(study / "answers.csv")
        pii_state = "yes" if p.get("passed") and current else "no - last check did not pass or answers changed since"
    out["B2 de-identification check passed on current answers"] = pii_state
    marks_problems = problems_of(
        lambda: load_marks(study, load_questions(study), load_answers(study, load_questions(study)), load_manifest(study)))
    out["B3 independent marking"] = {
        "fields completed": level(marks_problems),
        "approval documented": "markers declared blind in the manifest" if not marks_problems else "no",
        "approval independently verified": "not independently verified (blind marking is declared, not checkable)"}
    out["B3/B5 set frozen (study_set.json + hash)"] = "yes" if (study / "study_set.sha256").exists() else "no - freeze"
    out["B5 set scored once (SCORED.json)"] = "yes" if (study / "SCORED.json").exists() else "no - score"
    out["B5 hashes held by the supervisor"] = "not independently verified (confirm with the supervisor, then run verify)"
    return out


def markdown(r: dict) -> str:
    ta = r["teacher_agreement"]
    fe = r["frozen_engine"]
    L = [f"# {r['study']} - model vs teacher reference marks", "",
         ("**HISTORICAL RERUN - not an independent test.**\n" if r["historical_rerun"] else ""),
         f"{r['n_answers']} real student answers, {r['n_questions']} questions, max marks {r['max_marks']}; question types "
         f"{r['question_types']}. Set SHA-256 `{r['set_sha256'][:16]}...`. Frozen engine {fe['engine_version']}, backend "
         f"`{fe['backend']}`, model `{fe['model']}`, config `{fe['config_fingerprint']}`. Scored {r['scored_at']}.", "",
         "## Teacher agreement (reference ceiling)", "",
         f"Concept exact agreement {ta['concept_exact_agreement']:.1%}, linear-weighted kappa "
         f"{_fmt(ta['concept_linear_weighted_kappa'])}; question totals: MAE between teachers "
         f"{ta['question_total_mae_between_markers']:.3f}, within +-1 {ta['question_total_within_1']:.1%}. "
         f"{ta['concept_disagreements']} concept disagreements were adjudicated.", "",
         "## Systems (95% CIs: bootstrap over questions)", "",
         "| System | MAE | Norm. MAE | Within +-1 | Severe (>=2) | Exact | Signed |", "|---|---|---|---|---|---|---|"]
    for k, m in r["systems"].items():
        L.append(f"| {k} | {m['mae']['estimate']:.3f} [{m['mae']['ci'][0]:.3f}, {m['mae']['ci'][1]:.3f}] | "
                 f"{m['normalised_mae']['estimate']:.1%} | {m['within_1']['estimate']:.1%} "
                 f"[{m['within_1']['ci'][0]:.1%}, {m['within_1']['ci'][1]:.1%}] | {m['severe_errors_ge_2']} | "
                 f"{m['exact']:.1%} | {m['mean_signed_error']:+.2f} |")
    if (warn := r["systems"]["engine (current)"].get("ci_warning")):
        L += ["", f"**Warning:** {warn}."]
    L += ["", "## Paired differences in MAE (negative = current engine has lower error)", "",
          "| Comparison | Difference | 95% CI | CI excludes 0 |", "|---|---|---|---|"]
    for k, d in r["paired_differences"].items():
        L.append(f"| {k} | {d['mae_difference']:+.3f} | [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}] | {d['ci_excludes_zero']} |")
    rf = r["review_flags"]
    L += ["", "## Review flags (current engine)", "",
          f"Flagged {rf['flagged_n']} (MAE {_fmt(rf['flagged_mae'])}), not flagged {rf['not_flagged_n']} "
          f"(MAE {_fmt(rf['not_flagged_mae'])}).", "", "## Subgroups", "", f"Reported only when n >= {MIN_SUBGROUP_N}.", ""]
    for key, sub in r["subgroups"].items():
        for g, v in sub.items():
            L.append(f"* {key} `{g}` (n={v['n']}): " + (", ".join(f"{k} {x:.3f}" for k, x in v.items()
                                                                if k not in ("n", "reported")) if v["reported"] else v["reason"]))
    acc = r["acceptance"]
    L += ["", f"## Pre-registered acceptance criteria: **{acc['overall']}**", "", acc["meaning"], "",
          "| Criterion | Status | Detail |", "|---|---|---|"]
    for k, v in acc["criteria"].items():
        L.append(f"| {k} | {v['status']} | {v['detail']} |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["init", "check-pii", "agreement", "freeze", "score", "verify", "status"])
    ap.add_argument("--study", type=Path, required=True)
    ap.add_argument("--names", type=Path, help="check-pii: text file with one name per line (required to pass)")
    ap.add_argument("--historical-rerun", action="store_true")
    ap.add_argument("--set-hash", help="verify: the study_set.json hash the supervisor kept")
    ap.add_argument("--report-hash", help="verify: the score_report.json hash the supervisor kept")
    args = ap.parse_args(argv)
    if args.step == "init":
        cmd_init(args.study)
    elif args.step == "check-pii":
        found = cmd_check_pii(args.study, args.names)
        sys.exit(1 if found or not args.names else 0)
    elif args.step == "agreement":
        cmd_agreement(args.study)
    elif args.step == "freeze":
        cmd_freeze(args.study)
    elif args.step == "verify":
        sys.exit(0 if cmd_verify(args.study, args.set_hash, args.report_hash) else 1)
    elif args.step == "status":
        for k, v in study_status(args.study).items():
            if isinstance(v, dict):
                print(k)
                for kk, vv in v.items():
                    print(f"    {kk}: {vv}")
            else:
                print(f"{k}: {v}")
    else:
        cmd_score(args.study, args.historical_rerun)


if __name__ == "__main__":
    main()
