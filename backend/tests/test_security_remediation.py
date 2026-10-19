"""Security remediation sprint (post-audit F1-F4, F7-F11). No test here runs the scoring engine: evaluations are
inserted as documents where needed. Databases are disposable (the conftest test database or answerwise_sec_<pid>_*);
the development database is never touched."""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

import pytest
from bson import ObjectId

from app import deployment
from app.config import get_settings, invite_code_problem, pilot_config_problems
from app.db import now
from app.ratelimit import (
    INVITE_GLOBAL_LIMIT, INVITE_GLOBAL_WINDOW, INVITE_IP_LIMIT, LOGIN_IP_LIMIT, LOGIN_MAX_FAILURES, LOGIN_WINDOW,
    REGISTER_IP_LIMIT, RateLimiter, limiter,
)
from evaluation import real_study as rs
from scripts import pilot_fallback_report, pilot_init_db, seed
from scripts import pilot_preflight as pf
from tests.conftest import PASSWORD, QUESTION
from tests.test_pilot_readiness import (  # noqa: F401 (fixtures)
    SAFE, _health, _health_for, pilot_env, scratch_db, supervisor_hash,
)

STRONG = "Xq7-Lm2Vp9_Rt4Kz8Wy"
ROOT = Path(__file__).resolve().parents[2]


def reg(client, role, email=None, **extra):
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"name": f"Sec {role}", "email": email, "password": PASSWORD, "role": role,
                                                **extra})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"} if r.status_code == 201 else None
    return r, headers, email


# ============================== F1: rate limiting and invite codes =================================

def test_rate_limiter_window_and_cooldown():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    for _ in range(3):
        assert rl.hit("k", 3, 60) is None
    wait = rl.hit("k", 3, 60)
    assert wait is not None and 1 <= wait <= 60
    t[0] = 61
    assert rl.hit("k", 3, 60) is None  # cooldown over: not a permanent lock


def test_repeated_wrong_passwords_lock_the_account_with_429(client, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    _, _, email = reg(client, "student")
    for i in range(LOGIN_MAX_FAILURES):
        assert client.post("/api/auth/login", json={"email": email, "password": f"Wrong-guess-{i}"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"  # even the CORRECT password is refused now
    assert 1 <= int(r.headers["Retry-After"]) <= LOGIN_WINDOW
    # the account key is the normalised e-mail: case/whitespace variants do not reset the counter
    assert client.post("/api/auth/login", json={"email": f"  {email.upper()} ", "password": PASSWORD}).status_code == 429
    # unknown e-mails are throttled the same way (no account enumeration through 429 vs 401)
    for i in range(LOGIN_MAX_FAILURES):
        client.post("/api/auth/login", json={"email": "nobody@example.com", "password": f"Wrong-{i}"})
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong-x1"}).status_code == 429
    # cooldown: after the window the correct password works again
    later = limiter._clock() + LOGIN_WINDOW + 1
    monkeypatch.setattr(limiter, "_clock", lambda: later)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert "Wrong-guess" not in caplog.text and PASSWORD not in caplog.text


def test_successful_login_resets_the_account_counter(client):
    _, _, email = reg(client, "student")
    for _ in range(LOGIN_MAX_FAILURES - 1):
        client.post("/api/auth/login", json={"email": email, "password": "Wrong-1234"})
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    for _ in range(LOGIN_MAX_FAILURES - 1):
        assert client.post("/api/auth/login", json={"email": email, "password": "Wrong-1234"}).status_code == 401


def test_malformed_login_requests_count_towards_the_ip_limit(client):
    for i in range(LOGIN_IP_LIMIT):
        bad = [b"not json", b"{}", b'{"email": "x"}'][i % 3]
        r = client.post("/api/auth/login", content=bad, headers={"Content-Type": "application/json"})
        assert r.status_code == 422
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "Whatever-1"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_registration_ip_limit(client):
    for _ in range(REGISTER_IP_LIMIT):
        client.post("/api/auth/register", content=b"{}", headers={"Content-Type": "application/json"})
    r, _, _ = reg(client, "student")
    assert r.status_code == 429


def test_teacher_invite_guessing_is_throttled_per_ip_and_globally(client, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(get_settings(), "teacher_invite_code", STRONG)
    for i in range(INVITE_IP_LIMIT):
        assert reg(client, "teacher", invite_code=f"guess-{i}")[0].status_code == 403
    r, _, _ = reg(client, "teacher", invite_code=STRONG)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0  # correct code refused while throttled
    assert reg(client, "student")[0].status_code == 201  # students are not affected
    # distributed guessing: the global counter (all IPs) also stops it
    limiter.reset()
    for _ in range(INVITE_GLOBAL_LIMIT):
        limiter.record("invite-fail:global", INVITE_GLOBAL_WINDOW)
    assert reg(client, "teacher", invite_code=STRONG)[0].status_code == 429
    limiter.reset()
    assert reg(client, "teacher", invite_code=STRONG)[0].status_code == 201
    assert STRONG not in caplog.text and "guess-0" not in caplog.text


@pytest.mark.parametrize("code,ok", [
    ("x", False), ("pilot-code", False), ("   ", False), ("<random code>", False), ("aaaaaaaaaaaaaaaaaaaa", False),
    ("teacherInvite2027xyz", False), ("Xq7 Lm2Vp9_Rt4Kz8Wy", False), (STRONG, True),
])
def test_pilot_mode_requires_a_strong_invite_code(code, ok, pilot_env):
    from app.config import Settings

    pilot_env.setenv("TEACHER_INVITE_CODE", code)
    assert (invite_code_problem(code) is None) is ok
    problems = pilot_config_problems(Settings())
    assert (not any("TEACHER_INVITE_CODE" in p for p in problems)) is ok
    assert all(code.strip() not in p for p in problems if code.strip())  # the code itself is never echoed


# ============================== F2: pilot enrollment ================================================

@pytest.fixture
def pilot_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "pilot_mode", True)


def _assessment(client, teacher):
    a = client.post("/api/assessments", json={"title": "Pilot", "subject": "NLP", "instructions": "x"}, headers=teacher).json()
    q = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION}, headers=teacher).json()
    assert client.post(f"/api/assessments/{a['id']}/publish", headers=teacher).status_code == 200
    return a, q


def test_unenrolled_students_cannot_register_view_or_submit_in_pilot_mode(client, monkeypatch):
    _, t, _ = reg(client, "teacher")
    _, early, _ = reg(client, "student")  # account created before pilot mode: never enrolled
    a, q = _assessment(client, t)
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    r, _, stranger = reg(client, "student")
    assert r.status_code == 403 and r.json()["code"] == "enrollment_required"
    body = {"assessment_id": a["id"], "answers": [{"question_id": q["id"], "text": "Tokens."}]}
    assert client.get("/api/assessments", headers=early).json() == []
    assert client.get(f"/api/assessments/{a['id']}", headers=early).status_code == 404
    assert client.put("/api/submissions/draft", json=body, headers=early).status_code == 404
    assert client.post("/api/submissions/submit", json=body, headers=early).status_code == 404
    # enrollment is teacher-only
    assert client.post("/api/enrollments", json={"emails": [stranger]}, headers=early).status_code == 403
    assert client.get("/api/enrollments", headers=early).status_code == 403


def test_enrolled_student_has_access_until_revoked(client, db, monkeypatch):
    _, t, _ = reg(client, "teacher")
    a, q = _assessment(client, t)
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    email = f"pupil-{uuid.uuid4().hex[:6]}@example.com"
    assert client.post("/api/enrollments", json={"emails": [email.upper()]}, headers=t).status_code == 201
    r, s, _ = reg(client, "student", email=email)
    assert r.status_code == 201
    assert [x["id"] for x in client.get("/api/assessments", headers=s).json()] == [a["id"]]
    body = {"assessment_id": a["id"], "answers": [{"question_id": q["id"], "text": "Tokens."}]}
    assert client.put("/api/submissions/draft", json=body, headers=s).status_code == 200
    listing = client.get("/api/enrollments", headers=t).json()
    assert listing == [{"email": email, "active": True, "registered": True}]
    assert client.delete(f"/api/enrollments/{email}", headers=t).status_code == 200
    # the existing token immediately loses access (the user is re-read on every request)
    assert client.get("/api/assessments", headers=s).json() == []
    assert client.post("/api/submissions/submit", json=body, headers=s).status_code == 404
    assert client.post("/api/enrollments", json={"emails": [email]}, headers=t).status_code == 201  # re-enroll
    assert client.post("/api/submissions/submit", json=body, headers=s).status_code == 200
    assert db.enrollments.find_one({"email": email})["enrolled_by"] is not None


def test_development_mode_is_unchanged(client):
    assert get_settings().pilot_mode is False
    _, t, _ = reg(client, "teacher")
    a, _ = _assessment(client, t)
    r, s, _ = reg(client, "student")
    assert r.status_code == 201 and [x["id"] for x in client.get("/api/assessments", headers=s).json()] == [a["id"]]


# ============================== F3: seed safety =====================================================

@pytest.fixture
def mongo():
    from pymongo import MongoClient

    c = MongoClient(get_settings().mongodb_uri, serverSelectionTimeoutMS=3000)  # sprint 5 setup: MONGODB_URI
    try:
        c.admin.command("ping")
    except Exception:  # noqa: BLE001
        pytest.skip("MongoDB not available")
    names = []

    def make(tag):
        name = f"answerwise_sec_{os.getpid()}_{tag}"
        assert name != "answerwise"
        names.append(name)
        return c[name]

    yield make
    for n in names:
        c.drop_database(n)


def _dev():
    from app.config import Settings

    return Settings(environment="development", pilot_mode=False)


def test_seed_refuses_a_pilot_marked_database_even_from_a_development_shell(mongo, monkeypatch):
    db = mongo("pilot")
    deployment.write_marker(db, deployment.PILOT)
    for reset in (False, True):
        with pytest.raises(SystemExit, match="PILOT database"):
            seed.check_seed_target(db, _dev(), reset)
    # the full entry point too: nothing is written to the pilot database
    monkeypatch.setattr(seed, "get_settings", _dev)
    monkeypatch.setattr(seed, "get_db", lambda: db)
    monkeypatch.setattr("sys.argv", ["seed", "--reset"])
    before = sorted(db.list_collection_names())
    with pytest.raises(SystemExit, match="PILOT database"):
        seed.main()
    assert sorted(db.list_collection_names()) == before and db.users.count_documents({}) == 0


def test_seed_fails_closed_on_ambiguous_or_uninspectable_targets(mongo):
    db = mongo("ambiguous")
    db.users.insert_one({"email": "real.person@school.example", "role": "student"})
    with pytest.raises(SystemExit, match="already contains data"):
        seed.check_seed_target(db, _dev(), reset=False)
    with pytest.raises(SystemExit, match="non-demo account"):
        seed.check_seed_target(db, _dev(), reset=True)
    other = mongo("unknown")
    other[deployment.MARKER_COLLECTION].insert_one({"_id": deployment.MARKER_ID, "kind": "staging"})
    with pytest.raises(SystemExit, match="unknown deployment marker"):
        seed.check_seed_target(other, _dev(), reset=True)

    class Unreachable:
        name = "x"

        def __getitem__(self, _):
            raise ConnectionError("unreachable")

        def list_collection_names(self):
            raise ConnectionError("unreachable")

    with pytest.raises(SystemExit, match="could not be inspected"):
        seed.check_seed_target(Unreachable(), _dev(), reset=False)


def test_seed_still_allowed_for_local_development(mongo):
    seed.check_seed_target(mongo("empty"), _dev(), reset=False)  # empty database
    dev = mongo("dev")
    deployment.write_marker(dev, deployment.DEVELOPMENT)
    dev.users.insert_one({"email": "x@school.example"})
    seed.check_seed_target(dev, _dev(), reset=True)  # marked development
    legacy = mongo("legacy")
    legacy.users.insert_many([{"email": "teacher@answerwise.dev"}, {"email": "aarav@answerwise.dev"}])
    seed.check_seed_target(legacy, _dev(), reset=True)  # pre-marker demo-only database


def test_pilot_init_db_only_marks_an_empty_database(mongo):
    from app.config import Settings

    pilot = Settings(pilot_mode=True)
    with pytest.raises(SystemExit, match="PILOT_MODE is not on"):
        pilot_init_db.init(mongo("a"), _dev())
    busy = mongo("busy")
    busy.users.insert_one({"email": "someone@school.example"})
    with pytest.raises(SystemExit, match="not empty"):
        pilot_init_db.init(busy, pilot)
    fresh = mongo("fresh")
    marker = pilot_init_db.init(fresh, pilot)
    assert deployment.read_marker(fresh)["kind"] == "pilot" and marker["instance_id"]
    with pytest.raises(SystemExit, match="Already initialised"):
        pilot_init_db.init(fresh, pilot)


def test_pilot_server_refuses_to_start_on_an_unmarked_database(db, monkeypatch):
    from app import main

    monkeypatch.setattr(get_settings(), "pilot_mode", True)

    async def start():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="not marked as a pilot database"):
        asyncio.run(start())
    deployment.write_marker(db, deployment.PILOT)
    monkeypatch.setenv("ANSWERWISE_LAUNCHER", "1")  # V1: pilot servers must be started by scripts/run_server.py
    asyncio.run(start())  # a marked database starts


# ============================== F4: preflight bound to the running server ===========================

def test_preflight_rejects_a_server_using_another_database(scratch_db, monkeypatch):  # noqa: F811
    _health(monkeypatch, _health_for(scratch_db, database_fingerprint="0123456789abcdef"))
    ok, results = pf.run("https://pilot")
    assert not ok
    row = next(r for r in results if r[0] == "Server and preflight use the same pilot database")
    assert row[1] == "FAIL" and "!=" in row[2]
    _health(monkeypatch, _health_for(scratch_db))
    assert pf.run("https://pilot", supervisor_hash())[0] is True


def test_preflight_fails_closed_without_server_identity_or_marker(scratch_db, monkeypatch):  # noqa: F811
    payload = _health_for(scratch_db)
    payload.pop("deployment")
    _health(monkeypatch, payload)
    assert pf.run("https://pilot")[0] is False
    _health(monkeypatch, _health_for(scratch_db, database_fingerprint=None))
    assert pf.run("https://pilot")[0] is False
    scratch_db[deployment.MARKER_COLLECTION].delete_many({})  # unmarked database
    ok, results = pf.run()
    assert not ok and any(n == "Database carries the pilot marker" and s == "FAIL" for n, s, _ in results)


def test_health_summary_exposes_no_secrets(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "teacher_invite_code", STRONG)
    h = client.get("/api/health").json()
    text = json.dumps(h)
    s = get_settings()
    assert STRONG not in text and s.jwt_secret not in text and s.mongodb_uri not in text and s.mongodb_db not in text
    assert h["deployment"]["teacher_invite_code_strong"] is True


# ============================== F7/F8: truthful verification ========================================

def _study(tmp_path, report=True):
    s = tmp_path / "study"
    (s / "results").mkdir(parents=True)
    set_bytes = b'{\n  "synthetic": true\n}\n'
    (s / "study_set.json").write_bytes(set_bytes)
    set_hash = hashlib.sha256(set_bytes).hexdigest()
    (s / "study_set.sha256").write_text(f"{set_hash}  study_set.json\n", encoding="utf-8")
    rep_hash = None
    if report:
        rep = b'{\n  "report": 1\n}'
        (s / "results" / "score_report.json").write_bytes(rep)
        rep_hash = hashlib.sha256(rep).hexdigest()
        (s / "SCORED.json").write_text(json.dumps({"score_report_sha256": rep_hash}), encoding="utf-8")
    return s, set_hash, rep_hash


def test_verify_requires_the_report_hash_whenever_a_report_exists(tmp_path, capsys):
    s, set_hash, rep_hash = _study(tmp_path)
    assert rs.cmd_verify(s, set_hash, rep_hash) is True
    assert rs.cmd_verify(s, set_hash, None) is False  # a lock hash alone never verifies a report
    assert capsys.readouterr().out.strip().endswith("NOT VERIFIED")
    assert rs.cmd_verify(s, None, rep_hash) is False
    assert rs.cmd_verify(s, "0" * 64, rep_hash) is False


def test_verify_rejects_replaced_or_missing_reports(tmp_path, capsys):
    s, set_hash, rep_hash = _study(tmp_path)
    new = b'{\n  "report": 2\n}'
    (s / "results" / "score_report.json").write_bytes(new)
    (s / "SCORED.json").write_text(json.dumps({"score_report_sha256": hashlib.sha256(new).hexdigest()}), encoding="utf-8")
    assert rs.cmd_verify(s, set_hash, rep_hash) is False  # consistent with SCORED.json, but not with the supervisor
    assert "MISMATCH" in capsys.readouterr().out
    (s / "results" / "score_report.json").unlink()
    assert rs.cmd_verify(s, set_hash, rep_hash) is False  # SCORED.json without a report
    s2, set2, _ = _study(tmp_path / "b", report=False)
    assert rs.cmd_verify(s2, set2, None) is True  # nothing scored yet: the lock alone is the whole claim
    assert rs.cmd_verify(s2, set2, "ab" * 32) is False  # supervisor holds a report hash but there is no report


def test_verify_hashes_exact_bytes_line_endings_included(tmp_path, capsys):
    s, set_hash, rep_hash = _study(tmp_path)
    report = s / "results" / "score_report.json"
    report.write_bytes(report.read_bytes().replace(b"\n", b"\r\n"))
    assert hashlib.sha256(report.read_bytes()).hexdigest() != rep_hash
    assert rs.cmd_verify(s, set_hash, rep_hash) is False  # CRLF re-save = different bytes = mismatch
    assert rs._sha256_file(report) == hashlib.sha256(report.read_bytes()).hexdigest()  # same as sha256sum
    lock = s / "study_set.json"
    lock.write_bytes(lock.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(SystemExit, match="changed after it was frozen"):
        rs.load_study_set(s)


# ============================== F9: approval is not implied =========================================

def _criteria(**over):
    c = json.loads((rs.TEMPLATES / "acceptance_criteria.template.json").read_text(encoding="utf-8"))
    c["criteria"] = {"min_answers": 3, "min_questions": 1, "min_answers_per_question": 3, "min_teacher_concept_kappa": 0.0,
                     "min_teacher_within_1": 0.5, "max_normalised_mae_ci_upper": 1.0, "min_within_1_ci_lower": 0.0,
                     "max_mae_ratio_to_teacher_mae": 100, "max_severe_error_share": 1.0,
                     "max_severe_error_share_per_question_type": 1.0, "keyword_baseline_rule": "report_only",
                     "v3_rule": "report_only", "require_flagged_mae_above_unflagged": False}
    c["attestations"] = {k: True for k in rs.REQUIRED_ATTESTATIONS}
    c.update(over)
    return c


def test_completed_criteria_are_not_labelled_approved(tmp_path):
    rs.cmd_init(tmp_path)
    (tmp_path / "acceptance_criteria.json").write_text(json.dumps(_criteria()), encoding="utf-8")
    b1 = rs.study_status(tmp_path)["B1 acceptance criteria"]
    assert b1["fields completed"] == "yes"
    assert b1["approval documented"].startswith("no") and "approval_evidence" in b1["approval documented"]
    assert b1["approval independently verified"].startswith("not independently verified")
    with pytest.raises(SystemExit, match="documented approval"):
        rs.load_criteria(tmp_path)  # freeze requirement
    (tmp_path / "acceptance_criteria.json").write_text(json.dumps(_criteria(
        approved_by="test only", approved_on="2026-10-17", approval_evidence="test fixture")), encoding="utf-8")
    b1 = rs.study_status(tmp_path)["B1 acceptance criteria"]
    assert b1["approval documented"] == "yes"
    assert b1["approval independently verified"].startswith("not independently verified")  # never set by software
    rs.load_criteria(tmp_path)


# ============================== F10: frozen-engine manifest =========================================

def _manifest_copy(tmp_path, monkeypatch, mutate=None, raw=None):
    m = json.loads(pf.FROZEN.read_text(encoding="utf-8"))
    if mutate:
        mutate(m)
    p = tmp_path / "manifest.json"
    p.write_bytes(raw if raw is not None else json.dumps(m).encode())
    monkeypatch.setattr(pf, "FROZEN", p)
    r = []
    pf.check_engine(r)
    return r


def test_repository_manifest_covers_every_scoring_file_and_matches():
    m = json.loads(pf.FROZEN.read_text(encoding="utf-8"))
    nlp = {f"app/nlp/{p.name}" for p in (ROOT / "backend" / "app" / "nlp").glob("*.py")}
    assert nlp | {"app/services/evaluation_service.py"} <= set(m["files"])
    r = []
    pf.check_engine(r)
    # V2 (sprint 2): this used to be "NOT VERIFIED" and counted as a pass - that WAS the vulnerability. Now it fails.
    assert r[0][1] == "PASS" and r[1][1] == "FAIL" and "missing" in r[1][2]  # no supervisor hash given


@pytest.mark.parametrize("case,expected", [
    ("missing", "manifest missing"), ("malformed", "malformed"), ("no_files", "incomplete"),
    ("unlisted", "not listed in manifest"), ("changed", "changed"), ("stale_identity", "differs"),
])
def test_bad_manifests_fail_clearly(tmp_path, monkeypatch, case, expected):
    if case == "missing":
        monkeypatch.setattr(pf, "FROZEN", tmp_path / "nope.json")
        r = []
        pf.check_engine(r)
    elif case == "malformed":
        r = _manifest_copy(tmp_path, monkeypatch, raw=b"{not json")
    else:
        mut = {"no_files": lambda m: m.pop("files"),
               "unlisted": lambda m: m["files"].pop("app/nlp/scorer.py"),
               "changed": lambda m: m["files"].update({"app/nlp/scorer.py": "0" * 64}),
               "stale_identity": lambda m: m.update(nlp_source_sha256="0" * 64)}[case]
        r = _manifest_copy(tmp_path, monkeypatch, mutate=mut)
    assert r[0][1] == "FAIL" and expected in r[0][2]


def test_supervisor_manifest_hash_is_compared(monkeypatch):
    digest = hashlib.sha256(pf.FROZEN.read_bytes()).hexdigest()
    r = []
    pf.check_engine(r, digest)
    assert r[1][1] == "PASS"
    r = []
    pf.check_engine(r, "f" * 64)
    assert r[1][1] == "FAIL"


# ============================== F11/F12: fallback handling ==========================================

def _fake_evaluations(db, sub_id, backend):
    sub = db.submissions.find_one({"_id": ObjectId(sub_id)})
    ids = []
    for q in db.questions.find({"assessment_id": sub["assessment_id"]}):
        ids.append(db.evaluations.insert_one({
            "submission_id": sub["_id"], "question_id": q["_id"], "assessment_id": sub["assessment_id"],
            "student_id": sub["student_id"], "version": 1, "rubric_version": q.get("rubric_version", 1),
            "rubric_fingerprint": "x", "config_fingerprint": "x", "engine_version": "test-insert", "backend": backend,
            "model_name": "none", "ai_score": 1.0, "max_marks": q["max_marks"], "teacher_score": None,
            "adjustment_reason": "", "teacher_feedback": "", "status": "ai_suggested", "published": False,
            "evaluated_at": now(), "reviewed_at": None, "published_at": None,
            "result": {"suggested_score": 1.0, "max_marks": q["max_marks"], "concepts": [], "holistic_similarity": None,
                       "relevance_ratio": None, "word_count": 1, "confidence": "low", "corrections": [],
                       "feedback": {"summary": "", "strengths": [], "partial": [], "missing": [], "suggestions": [],
                                    "text": ""}, "needs_review": True, "flags": [], "metadata": {}}}).inserted_id)
    db.submissions.update_one({"_id": sub["_id"]}, {"$set": {"status": "evaluated"}})
    return ids


def test_fallback_scored_results_need_a_teacher_mark_with_reason_in_pilot_mode(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "require_review_before_publish", True)
    _, t, _ = reg(client, "teacher")
    a, q = _assessment(client, t)
    _, s, _ = reg(client, "student")
    sub = client.post("/api/submissions/submit", json={"assessment_id": a["id"], "answers": [
        {"question_id": q["id"], "text": "Tokens."}]}, headers=s).json()
    (ev,) = _fake_evaluations(db, sub["id"], backend="tfidf")
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    # sprint 3 (V10): accepting the AI score must be explicit - an empty body is no longer a review
    assert client.patch(f"/api/evaluations/{ev}", json={"accept_ai_score": True}, headers=t).json()["status"] == "reviewed"
    r = client.post(f"/api/results/submission/{sub['id']}/publish", headers=t)
    assert r.status_code == 409 and r.json()["code"] == "fallback_requires_teacher_mark"
    rows = pilot_fallback_report.report(db)
    assert len(rows) == 1 and not rows[0]["teacher_marked_with_reason"]
    client.patch(f"/api/evaluations/{ev}", json={"teacher_score": 1.0, "adjustment_reason": "Fallback scored: marked by teacher"},
                 headers=t)
    assert pilot_fallback_report.report(db)[0]["teacher_marked_with_reason"] is True
    assert client.post(f"/api/results/submission/{sub['id']}/publish", headers=t).status_code == 200


def test_fallback_limitations_are_explicit_in_output_and_runbook(scratch_db):  # noqa: F811
    ok, results = pf.run()
    note = next(d for n, s, d in results if s == "NOTE")
    assert "does not guarantee" in note and "after every server restart" in note
    runbook = (ROOT / "docs" / "PILOT_RUNBOOK.md").read_text(encoding="utf-8")
    for phrase in ("pilot_fallback_report", 'backend: "tfidf"', "after every server restart", "with a reason",
                   "does not guarantee"):
        assert phrase in runbook, phrase
    readiness = (ROOT / "docs" / "PILOT_READINESS.md").read_text(encoding="utf-8")
    assert "fallback" in readiness and "does not guarantee" in readiness
