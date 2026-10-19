"""Real-student study tooling: protocol order is enforced. Uses a tiny SYNTHETIC study built in a temp
directory - no real student data exists in this repository."""

import csv
import json
from datetime import date, timedelta

import pytest

from evaluation import real_study as rs
from tests.conftest import QUESTION

ANSWERS = [  # synthetic, written for this test
    ("a1", "Tokenization splits text into tokens such as words. It is the first step and later steps use the tokens."),
    ("a2", "Tokenization breaks a sentence into words."),
    ("a3", "It is about grammar rules."),
]
MARKS_A = {"a1": "MMX", "a2": "PXX", "a3": "XXX"}
MARKS_B = {"a1": "MMX", "a2": "MXX", "a3": "XXX"}  # one disagreement: a2/c1
CRITERIA = {  # test values only - real values are chosen and approved by the project team
    "min_answers": 3, "min_questions": 1, "min_answers_per_question": 3, "min_teacher_concept_kappa": 0.0,
    "min_teacher_within_1": 0.5, "max_normalised_mae_ci_upper": 1.0, "min_within_1_ci_lower": 0.0,
    "max_mae_ratio_to_teacher_mae": 100, "max_severe_error_share": 1.0, "max_severe_error_share_per_question_type": 1.0,
    "keyword_baseline_rule": "report_only", "v3_rule": "report_only", "require_flagged_mae_above_unflagged": False,
}


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def fill(obj):
    """Replace every template placeholder with a test value."""
    if isinstance(obj, dict):
        return {k: fill(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v) for v in obj]
    return "test value" if isinstance(obj, str) and obj.startswith("<") else obj


def adjudicate(study, rows=(("a2", "c1", "P", "C", "Mentions words only, not subwords/characters"),)):
    write_csv(study / "adjudication.csv", ["answer_id", "concept_id", "final_level", "adjudicator_id", "reason"], rows)


@pytest.fixture
def study(tmp_path):
    rs.cmd_init(tmp_path)
    manifest = fill(json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")))
    manifest.update(consent_obtained_for_all_answers=True, retention_until=(date.today() + timedelta(days=30)).isoformat())
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    crit = json.loads((tmp_path / "acceptance_criteria.json").read_text(encoding="utf-8"))
    crit.update(approved_by="test", approved_on=date.today().isoformat(), approval_evidence="test fixture, not a real approval",
                criteria=CRITERIA,
                attestations={k: True for k in rs.REQUIRED_ATTESTATIONS})
    (tmp_path / "acceptance_criteria.json").write_text(json.dumps(crit), encoding="utf-8")
    q = {"id": "S1", "question_type": "explanation", **{k: QUESTION[k] for k in ("text", "max_marks", "reference_answer")},
         "rubric": [dict(c, id=f"c{n + 1}") for n, c in enumerate(QUESTION["rubric"])]}
    (tmp_path / "questions.json").write_text(json.dumps({"questions": [q]}), encoding="utf-8")
    write_csv(tmp_path / "answers.csv", ["answer_id", "question_id", "answer_text"], [(a, "S1", t) for a, t in ANSWERS])
    for name, marks in (("A", MARKS_A), ("B", MARKS_B)):
        write_csv(tmp_path / f"marks_{name}.csv", ["answer_id", "concept_id", "level", "comment"],
                  [(a, f"c{i + 1}", lv, "") for a, lvs in marks.items() for i, lv in enumerate(lvs)])
    (tmp_path / "names.txt").write_text("Priya\nArjun\n", encoding="utf-8")
    return tmp_path


def pii_ok(study):
    assert not rs.cmd_check_pii(study, study / "names.txt")


def test_templates_contain_no_data(tmp_path):
    rs.cmd_init(tmp_path)
    for f in ("answers.csv", "marks_A.csv", "marks_B.csv", "adjudication.csv"):
        assert len((tmp_path / f).read_text(encoding="utf-8").strip().splitlines()) == 1  # header only
    with pytest.raises(SystemExit, match="incomplete"):
        rs.load_manifest(tmp_path)  # placeholders are rejected
    crit = json.loads((tmp_path / "acceptance_criteria.json").read_text(encoding="utf-8"))
    assert all(v is None for v in crit["criteria"].values())  # no threshold is pre-filled
    with pytest.raises(SystemExit, match="not set"):
        rs.load_criteria(tmp_path)


def test_study_directory_must_be_outside_the_repository():
    with pytest.raises(SystemExit, match="inside the repository"):
        rs.check_location(rs.REPO_ROOT / "backend" / "my_study")
    rs.check_location(rs.IGNORED_DATA_DIR / "s1")  # tolerated: git-ignored


def test_pii_detection():
    assert rs.find_pii("Contact me at student@example.edu", [])
    assert rs.find_pii("My roll number is 21BCE1234", [])
    assert rs.find_pii("Call 9876543210 if needed", [])
    assert rs.find_pii("As Priya explained in class", ["Priya"])
    assert not rs.find_pii("TF-IDF = TF x IDF and log(N/df) is 2.5 for 10 documents", [])


def test_consent_retention_and_blind_marking_are_enforced(study):
    m = json.loads((study / "manifest.json").read_text(encoding="utf-8"))
    for change, msg in ((dict(consent_obtained_for_all_answers=False), "consent"), (dict(retention_until="2000-01-01"), "retention"),
                        (dict(manual_pii_review="<who>"), "incomplete"), (dict(adjudication="<who>"), "placeholders"),
                        (dict(markers=[dict(m["markers"][0]), dict(m["markers"][1], blind_to_model_scores=False)]), "blind")):
        (study / "manifest.json").write_text(json.dumps(dict(m, **change)), encoding="utf-8")
        with pytest.raises(SystemExit, match=msg):
            rs.cmd_agreement(study)


def test_two_declared_independent_markers_required(study):
    (study / "marks_B.csv").rename(study / "marks_Z.csv")  # undeclared marker
    with pytest.raises(SystemExit, match="do not match the markers declared"):
        rs.cmd_agreement(study)
    (study / "marks_Z.csv").unlink()
    with pytest.raises(SystemExit, match="do not match"):
        rs.cmd_agreement(study)


def test_duplicate_or_conflicting_marks_rejected(study):
    with (study / "marks_A.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(["a1", "c1", "X", "second opinion"])
    with pytest.raises(SystemExit, match="more than once"):
        rs.cmd_agreement(study)


def test_placeholder_questions_rejected(study):
    (study / "questions.json").write_text((rs.TEMPLATES / "questions.template.json").read_text(encoding="utf-8"),
                                          encoding="utf-8")
    with pytest.raises(SystemExit, match="placeholders"):
        rs.cmd_agreement(study)


def test_pii_check_must_pass_with_names_on_the_exact_answers(study):
    adjudicate(study)
    with pytest.raises(SystemExit, match="de-identification"):
        rs.cmd_freeze(study)  # never run
    rs.cmd_check_pii(study, None)  # without a name list it cannot pass
    with pytest.raises(SystemExit, match="de-identification"):
        rs.cmd_freeze(study)
    pii_ok(study)
    with (study / "answers.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(["a4", "S1", "Arjun says tokens are words."])
    with pytest.raises(SystemExit, match="de-identification"):
        rs.cmd_freeze(study)  # answers changed after the check
    assert rs.cmd_check_pii(study, study / "names.txt")  # and the new answer is caught by the name list


def test_criteria_must_be_approved_before_freeze(study):
    pii_ok(study)
    adjudicate(study)
    crit = json.loads((study / "acceptance_criteria.json").read_text(encoding="utf-8"))
    for change, msg in ((dict(criteria=dict(CRITERIA, max_severe_error_share=None)), "not set"),
                        (dict(approved_on="<YYYY-MM-DD>"), "placeholder"),
                        (dict(criteria=dict(CRITERIA, v3_rule="whatever")), "must be one of"),
                        (dict(attestations={}), "attestation")):
        (study / "acceptance_criteria.json").write_text(json.dumps(dict(crit, **change)), encoding="utf-8")
        with pytest.raises(SystemExit, match=msg):
            rs.cmd_freeze(study)


def test_agreement_and_adjudication_before_freeze(study):
    pii_ok(study)
    report = rs.cmd_agreement(study)
    assert report["concept_disagreements"] == 1 and report["n_answers"] == 3
    assert report["question_total_mae_between_markers"] == pytest.approx(1 / 3)  # a2: 1.0 vs 2.0 marks
    work = list(csv.DictReader((study / "adjudication_worklist.csv").open(encoding="utf-8")))
    assert [(w["answer_id"], w["concept_id"]) for w in work] == [("a2", "c1")]
    with pytest.raises(SystemExit, match="not adjudicated"):
        rs.cmd_freeze(study)
    adjudicate(study)
    path = rs.cmd_freeze(study)
    data = rs.load_study_set(study)
    a2 = next(a for q in data["questions"] for a in q["answers"] if a["id"] == "a2")
    assert a2["labels"]["c1"] == "P" and a2["human_score"] == 1.0 and a2["marker_scores"] == {"A": 1.0, "B": 2.0}
    assert data["synthetic"] is False and data["teacher_agreement"]["concept_disagreements"] == 1
    assert data["frozen_engine"] == rs.frozen_engine() and data["acceptance_criteria_sha256"]
    with pytest.raises(SystemExit, match="already frozen"):
        rs.cmd_freeze(study)
    path.write_text(path.read_text(encoding="utf-8").replace("Tokenization", "Tokenisation"), encoding="utf-8")
    with pytest.raises(SystemExit, match="changed after it was frozen"):
        rs.load_study_set(study)


def test_kappa_undefined_without_variation_is_reported_as_none(study):
    for name in ("A", "B"):
        write_csv(study / f"marks_{name}.csv", ["answer_id", "concept_id", "level", "comment"],
                  [(a, f"c{i + 1}", "X", "") for a, _ in ANSWERS for i in range(3)])
    assert rs.cmd_agreement(study)["concept_linear_weighted_kappa"] is None


def test_freeze_refuses_pii_and_dev_overlap(study):
    adjudicate(study, [("a2", "c1", "P", "C", "x")])
    rows = [(a, "S1", t) for a, t in ANSWERS]
    write_csv(study / "answers.csv", ["answer_id", "question_id", "answer_text"], rows[:2] + [("a3", "S1", "mail me: x@y.org")])
    assert rs.cmd_check_pii(study, study / "names.txt")
    with pytest.raises(SystemExit, match="de-identification"):
        rs.cmd_freeze(study)
    from evaluation.common import iter_answers, load_dataset

    dev_text = next(a["text"] for _, a in iter_answers(load_dataset(), "dev") if a["text"].strip())
    write_csv(study / "answers.csv", ["answer_id", "question_id", "answer_text"], rows[:2] + [("a3", "S1", dev_text)])
    pii_ok(study)
    with pytest.raises(SystemExit, match="development dataset"):
        rs.cmd_freeze(study)


@pytest.fixture
def frozen(study):
    pii_ok(study)
    adjudicate(study, [("a2", "c1", "P", "C", "x")])
    rs.cmd_freeze(study)
    return study


def test_score_once_with_confidence_intervals_and_criteria(frozen, backend):
    with pytest.raises(SystemExit, match="never been scored"):
        rs.cmd_score(frozen, historical_rerun=True, backend=backend, n_boot=200)
    out = rs.cmd_score(frozen, backend=backend, n_boot=200)
    assert set(out["systems"]) == {"engine (current)", "v4.0 profile", "v3 profile", "keyword baseline (dev-fitted)"}
    assert {k for k in out["paired_differences"]} == {
        "engine (current) - v4.0 profile", "engine (current) - v3 profile", "engine (current) - keyword baseline (dev-fitted)"}
    assert all(m["n"] == 3 for m in out["systems"].values())  # every system scored the same locked answers
    m = out["systems"]["engine (current)"]
    assert m["mae"]["ci"][0] <= m["mae"]["estimate"] <= m["mae"]["ci"][1]
    assert "unreliable" in m["ci_warning"]  # one question: no honest interval
    assert out["subgroups"]["question_type"]["explanation"]["reported"] is False  # n=3 < 20
    assert out["acceptance"]["overall"] == "INCONCLUSIVE"  # CI-based criteria cannot be evaluated with 1 question
    assert out["acceptance"]["criteria"]["max_normalised_mae_ci_upper"]["status"] == "NOT_EVALUABLE"
    report = (frozen / "results" / "score_report.json").read_text(encoding="utf-8")
    assert all(t not in report for _, t in ANSWERS)  # reports never contain answer text
    assert json.loads((frozen / "SCORED.json").read_text(encoding="utf-8"))["set_sha256"] == out["set_sha256"]
    with pytest.raises(SystemExit, match="already scored"):
        rs.cmd_score(frozen, backend=backend, n_boot=200)
    (frozen / "results" / "score_report.json").unlink()  # deleting the report alone does not re-open the set
    with pytest.raises(SystemExit, match="already scored"):
        rs.cmd_score(frozen, backend=backend, n_boot=200)
    rs.cmd_score(frozen, historical_rerun=True, backend=backend, n_boot=200)
    assert (frozen / "results" / "score_report_rerun.md").read_text(encoding="utf-8").count("HISTORICAL RERUN") == 1


def test_score_refuses_changed_criteria_engine_or_backend(frozen, backend, monkeypatch):
    from app.nlp.similarity import TfidfBackend

    crit = frozen / "acceptance_criteria.json"
    original = crit.read_text(encoding="utf-8")
    crit.write_text(original.replace('"max_severe_error_share": 1.0', '"max_severe_error_share": 0.9'), encoding="utf-8")
    with pytest.raises(SystemExit, match="changed after freezing"):
        rs.cmd_score(frozen, backend=backend, n_boot=200)
    crit.write_text(original, encoding="utf-8")
    monkeypatch.setattr(rs, "frozen_engine", lambda: {"engine_version": "9.9.9"})
    with pytest.raises(SystemExit, match="differs from the engine"):
        rs.cmd_score(frozen, backend=backend, n_boot=200)
    monkeypatch.undo()
    with pytest.raises(SystemExit, match="TF-IDF fallback is not the frozen system"):
        rs.cmd_score(frozen, backend=TfidfBackend(), n_boot=200)
    assert not (frozen / "SCORED.json").exists()  # refusals leave the set unscored


def test_supervisor_verify_and_status(frozen, backend, capsys):
    import hashlib

    status = rs.study_status(frozen)
    assert status["B5 set scored once (SCORED.json)"].startswith("no")
    for k in ("B1 acceptance criteria", "B2 ethics approval and consent (manifest.json)", "B3 independent marking"):
        assert status[k]["fields completed"] == "yes"
        assert status[k]["approval independently verified"].startswith("not independently verified")
    assert status["B1 acceptance criteria"]["approval documented"] == "yes"
    assert "not independently verified" in status["B5 hashes held by the supervisor"]
    rs.cmd_score(frozen, backend=backend, n_boot=200)
    set_file, report = frozen / "study_set.json", frozen / "results" / "score_report.json"
    # the hash a supervisor computes from the raw file equals the printed / recorded one (LF on every platform)
    raw_report_hash = hashlib.sha256(report.read_bytes()).hexdigest()
    assert raw_report_hash == json.loads((frozen / "SCORED.json").read_text(encoding="utf-8"))["score_report_sha256"]
    set_hash = hashlib.sha256(set_file.read_bytes()).hexdigest()
    assert set_hash == (frozen / "study_set.sha256").read_text(encoding="utf-8").split()[0]
    assert rs.cmd_verify(frozen, set_hash, raw_report_hash) is True
    out = capsys.readouterr().out
    assert "VERIFIED" in out and "does not prove consent" in out
    assert rs.cmd_verify(frozen, None, None) is False  # without the supervisor's values it is not a verification
    assert rs.cmd_verify(frozen, "0" * 64, raw_report_hash) is False
    report.write_text(report.read_text(encoding="utf-8").replace('"historical_rerun": false', '"historical_rerun": true'),
                      encoding="utf-8", newline="\n")
    assert rs.cmd_verify(frozen, set_hash, raw_report_hash) is False  # tampered report
    assert "MISMATCH" in capsys.readouterr().out


def test_status_reports_pending_items_without_approving(tmp_path):
    rs.cmd_init(tmp_path)
    status = rs.study_status(tmp_path)
    flat = [vv for v in status.values() for vv in (v.values() if isinstance(v, dict) else [v])]
    assert all(v.startswith(("no", "not independently verified")) for v in flat)  # nothing reads as done or approved


def test_criteria_evaluation_rules():
    diff = {"mae_difference": -0.1, "ci": [-0.2, 0.05]}
    assert rs._comparison("point_estimate_not_worse", diff)[0] == "PASS"
    assert rs._comparison("ci_upper_below_zero", diff)[0] == "FAIL"
    assert rs._comparison("report_only", diff)[0] == "REPORTED"
