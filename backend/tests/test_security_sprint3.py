"""Sprint 3: residual-risk closure (F5/V9 sessions, F6 secrets/CORS, V6 enrollment audit, V7 frozen model/runtime
and overrides, V10 review/publication identity, V11 directory, V12 TLS). No test runs the scoring engine:
evaluations are inserted as documents; model files are hashed from disk, never loaded. Databases are disposable."""

import json
import os
import secrets
import uuid
from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from bson import ObjectId

from app import deployment
from app.config import cors_problems, get_settings, secret_problems
from app.db import now
from scripts import pilot_preflight as pf
from scripts import run_server
from tests.conftest import PASSWORD, QUESTION
from tests.test_pilot_readiness import (  # noqa: F401 (fixtures)
    SAFE, _health, _health_for, pilot_env, scratch_db, supervisor_hash,
)


def reg(client, role, email=None):
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"name": f"S3 {role}", "email": email, "password": PASSWORD, "role": role})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email, r.json()["user"]["id"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ============================== A. F5/V9: session revocation ========================================

def test_password_change_revokes_every_earlier_session(client):
    h1, email, _ = reg(client, "student")
    h2 = bearer(client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"])
    assert client.get("/api/auth/me", headers=h2).status_code == 200
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "NewPassw0rd"},
                    headers=h1)
    assert r.status_code == 200 and r.json()["access_token"]
    for old in (h1, h2):  # the device that changed it AND another device (e.g. a stolen token)
        r_old = client.get("/api/auth/me", headers=old)
        assert r_old.status_code == 401 and r_old.json()["code"] == "session_revoked"
        assert client.get("/api/assessments", headers=old).status_code == 401  # any protected route
    assert client.get("/api/auth/me", headers=bearer(r.json()["access_token"])).status_code == 200


def test_sign_out_everywhere(client):
    h, email, _ = reg(client, "teacher")
    other = bearer(client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"])
    r = client.post("/api/auth/logout-all", headers=h)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=other).status_code == 401
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.get("/api/auth/me", headers=bearer(r.json()["access_token"])).status_code == 200


def test_tokens_issued_before_session_versions_stay_valid_until_a_revocation(client, db):
    h, _, uid = reg(client, "student")
    s = get_settings()
    t = now()
    legacy = jwt.encode({"sub": uid, "iat": t, "exp": t + timedelta(hours=1), "type": "access"}, s.jwt_secret, "HS256")
    assert client.get("/api/auth/me", headers=bearer(legacy)).status_code == 200  # no "sv" = version 0
    client.post("/api/auth/logout-all", headers=h)
    assert client.get("/api/auth/me", headers=bearer(legacy)).status_code == 401
    for bad_sv in (True, "0", 1.0):  # forged / malformed versions are rejected
        tok = jwt.encode({"sub": uid, "sv": bad_sv, "iat": t, "exp": t + timedelta(hours=1), "type": "access"},
                         s.jwt_secret, "HS256")
        assert client.get("/api/auth/me", headers=bearer(tok)).status_code == 401


# ============================== B. F6: secrets and CORS =============================================

@pytest.mark.parametrize("secret,ok", [
    ("", False), ("change-me-to-a-long-random-string", False), ("Zq9" * 5, False), ("ab" * 20, False),
    ("abcdefgh" * 6, False), ("Password-0123456789-abcdefghijklmnop", False),
])
def test_weak_secrets_are_rejected(secret, ok):
    assert (not secret_problems(secret)) is ok
    assert all(secret not in p for p in secret_problems(secret) if secret)  # never echoed


def test_random_secrets_are_accepted():
    for _ in range(20):
        assert secret_problems(secrets.token_urlsafe(48)) == []


@pytest.mark.parametrize("origins,https,ok", [
    ([], False, False), (["*"], False, False), (["null"], False, False), (["https://pilot.example/app"], False, False),
    (["https://pilot.example?x=1"], False, False), (["https://*.example"], False, False),
    (["http://pilot.example"], True, False), (["https://pilot.example"], True, True),
    (["https://pilot.example:8443", "https://staff.pilot.example"], True, True), (["http://localhost:5173"], False, True),
])
def test_cors_allowlist_rules(origins, https, ok):
    assert (not cors_problems(origins, https)) is ok


def test_production_refuses_weak_secret_or_bad_cors(monkeypatch):
    from app import config

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PILOT_MODE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://school.example")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.get_settings.__wrapped__()
    good = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET", good)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS") as exc:
        config.get_settings.__wrapped__()
    assert good not in str(exc.value)
    monkeypatch.setenv("CORS_ORIGINS", "https://school.example")
    assert config.get_settings.__wrapped__().environment == "production"


def test_pilot_requires_https_origins(pilot_env):  # noqa: F811
    from app.config import Settings, pilot_config_problems

    pilot_env.setenv("CORS_ORIGINS", "http://pilot.example")
    assert any("https" in p for p in pilot_config_problems(Settings()))


# ============================== C. V6: enrollment audit; withdrawal policy undecided =================

def test_enrollment_changes_are_appended_to_an_event_log(client, db):
    t, _, tid = reg(client, "teacher")
    email = f"p-{uuid.uuid4().hex[:6]}@example.com"
    client.post("/api/enrollments", json={"emails": [email]}, headers=t)
    client.delete(f"/api/enrollments/{email}", headers=t)
    t2, _, t2id = reg(client, "teacher")
    client.post("/api/enrollments", json={"emails": [email]}, headers=t2)  # re-enroll overwrites current state...
    events = list(db.enrollment_events.find({"email": email}).sort("at", 1))
    assert [(e["action"], str(e["by"])) for e in events] == [("enrolled", tid), ("revoked", tid), ("enrolled", t2id)]
    assert str(db.enrollments.find_one({"email": email})["enrolled_by"]) == t2id  # ...but the history is kept


def _fake_evaluation(db, sub_id, backend="embedding"):
    sub = db.submissions.find_one({"_id": ObjectId(sub_id)})
    q = db.questions.find_one({"assessment_id": sub["assessment_id"]})
    return db.evaluations.insert_one({
        "submission_id": sub["_id"], "question_id": q["_id"], "assessment_id": sub["assessment_id"],
        "student_id": sub["student_id"], "version": 1, "rubric_version": q.get("rubric_version", 1),
        "rubric_fingerprint": "x", "config_fingerprint": "x", "engine_version": "test-insert", "backend": backend,
        "model_name": "none", "ai_score": 1.0, "max_marks": q["max_marks"], "teacher_score": None,
        "adjustment_reason": "", "teacher_feedback": "", "status": "ai_suggested", "published": False,
        "evaluated_at": now(), "reviewed_at": None, "published_at": None,
        "result": {"suggested_score": 1.0, "max_marks": q["max_marks"], "concepts": [], "holistic_similarity": None,
                   "relevance_ratio": None, "word_count": 1, "confidence": "low", "corrections": [],
                   "feedback": {"summary": "", "strengths": [], "partial": [], "missing": [], "suggestions": [], "text": ""},
                   "needs_review": True, "flags": [], "metadata": {}}}).inserted_id


def _submitted(client, db):
    t, _, tid = reg(client, "teacher")
    a = client.post("/api/assessments", json={"title": "Sprint three audit", "subject": "NLP", "instructions": "x"}, headers=t).json()
    q = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION}, headers=t).json()
    client.post(f"/api/assessments/{a['id']}/publish", headers=t)
    s, semail, _ = reg(client, "student")
    sub = client.post("/api/submissions/submit", json={"assessment_id": a["id"], "answers": [
        {"question_id": q["id"], "text": "Tokens."}]}, headers=s).json()
    ev = _fake_evaluation(db, sub["id"])
    db.submissions.update_one({"_id": ObjectId(sub["id"])}, {"$set": {"status": "evaluated"}})  # as evaluation would
    return t, tid, s, semail, a, sub, ev


def test_withdrawal_policy_is_undecided_current_behaviour_documented(client, db, monkeypatch):
    """CHARACTERISATION, not an endorsement: today a revoked (withdrawn) participant's EXISTING submission can still be
    reviewed and published. Whether withdrawal should block this is a faculty decision (PILOT_READINESS.md, decision
    register). If faculty decide to block it, this test must be replaced by one asserting the new rule."""
    t, _, s, semail, _, sub, ev = _submitted(client, db)
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    db.enrollments.insert_one({"email": semail, "revoked_at": now()})
    db.users.update_one({"email": semail}, {"$set": {"pilot_enrolled": False}})
    assert client.patch(f"/api/evaluations/{ev}", json={"accept_ai_score": True}, headers=t).status_code == 200
    assert client.post(f"/api/results/submission/{sub['id']}/publish", headers=t).status_code == 200


# ============================== D. V7: frozen model, runtime, overrides =============================

def _manifest_variant(tmp_path, monkeypatch, mutate):
    m = json.loads(pf.FROZEN.read_text(encoding="utf-8"))
    mutate(m)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    monkeypatch.setattr(pf, "FROZEN", p)
    r = []
    pf.check_engine(r, __import__("hashlib").sha256(p.read_bytes()).hexdigest())
    return {n: (s, d) for n, s, d in r}


MODEL_ROW = "Model weights, tokenizer and config on disk equal the frozen snapshot (exact bytes)"
RUNTIME_ROW = "Python and scoring-library versions equal the frozen runtime"


def test_manifest_covers_model_files_and_runtime():
    m = json.loads(pf.FROZEN.read_text(encoding="utf-8"))
    assert m["model_artifacts"]["revision"] and "model.safetensors" in m["model_artifacts"]["files"]
    assert {"python", "torch", "transformers", "sentence-transformers", "tokenizers"} <= set(m["runtime"])
    rev, snap = pf.model_snapshot(m["model"])
    if not snap:
        pytest.skip("model not cached on this machine")
    rows = {n: s for n, s, _ in (lambda r: (pf.check_engine(r, supervisor_hash()), r)[1])([])}
    assert rows[MODEL_ROW] == "PASS" and rows[RUNTIME_ROW] == "PASS"


@pytest.mark.parametrize("mutate,row,expected", [
    (lambda m: m["model_artifacts"]["files"].update({"model.safetensors": "0" * 64}), MODEL_ROW, "differs"),
    (lambda m: m["model_artifacts"]["files"].update({"extra.bin": "0" * 64}), MODEL_ROW, "differs"),
    (lambda m: m["model_artifacts"].update(revision="0" * 40), MODEL_ROW, "revision"),
    (lambda m: m["model_artifacts"].update(files={}), MODEL_ROW, "no model_artifacts"),
    (lambda m: m["runtime"].update(torch="0.0.1"), RUNTIME_ROW, "torch"),
    (lambda m: m["runtime"].update(python="2.7.18"), RUNTIME_ROW, "python"),
])
def test_changed_model_or_runtime_fails_closed(tmp_path, monkeypatch, mutate, row, expected):
    if not pf.model_snapshot(json.loads(pf.FROZEN.read_text(encoding="utf-8"))["model"])[1]:
        pytest.skip("model not cached on this machine")
    rows = _manifest_variant(tmp_path, monkeypatch, mutate)
    assert rows[row][0] == "FAIL" and expected in rows[row][1]


def test_missing_model_cache_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-cache"))
    r = []
    pf.check_engine(r, supervisor_hash())
    row = next(x for x in r if x[0] == MODEL_ROW)
    assert row[1] == "FAIL" and "not found" in row[2]


def test_manifest_without_model_or_runtime_sections_is_incomplete(tmp_path, monkeypatch):
    for key in ("model_artifacts", "runtime"):
        rows = _manifest_variant(tmp_path, monkeypatch, lambda m, k=key: m.pop(k))
        assert any(s == "FAIL" and "incomplete" in d for s, d in rows.values())


def test_question_overrides_fail_the_preflight(scratch_db):  # noqa: F811
    name = "No per-question scoring overrides of any kind (they are outside the frozen identity)"  # renamed in sprint 5
    scratch_db.questions.insert_one({"text": "q", "settings": {"match_threshold": None, "partial_threshold": None}})
    rows = {n: s for n, s, _ in pf.run(manifest_sha256=supervisor_hash())[1]}
    assert rows[name] == "PASS"
    scratch_db.questions.insert_one({"text": "q2", "settings": {"match_threshold": 0.7}})
    ok, results = pf.run(manifest_sha256=supervisor_hash())
    assert not ok and {n: s for n, s, _ in results}[name] == "FAIL"


def test_launcher_pins_the_model_cache_offline_in_pilot_mode(tmp_path, monkeypatch):
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "ANSWERWISE_LAUNCHER", "ANSWERWISE_CLIENT_ADDRESS_MODE",
              "ANSWERWISE_TRANSPORT"):
        monkeypatch.delenv(k, raising=False)
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.write_text("dummy")
    key.write_text("dummy")
    s = _pilot_settings()
    run_server.build_config(s, "0.0.0.0", 8443, str(cert), str(key))
    assert os.environ["HF_HUB_OFFLINE"] == "1" and os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["ANSWERWISE_TRANSPORT"] == "tls-direct"


# ============================== E. V10: review and publication identity =============================

def test_empty_review_is_not_a_review(client, db):
    t, _, _, _, _, _, ev = _submitted(client, db)
    r = client.patch(f"/api/evaluations/{ev}", json={}, headers=t)
    assert r.status_code == 422 and r.json()["code"] == "review_decision_required"
    assert db.evaluations.find_one({"_id": ev})["status"] == "ai_suggested" and "review_log" not in db.evaluations.find_one({"_id": ev})
    r = client.patch(f"/api/evaluations/{ev}", json={"accept_ai_score": True, "teacher_score": 1.5}, headers=t)
    assert r.status_code == 422 and r.json()["code"] == "review_conflict"
    assert client.patch(f"/api/evaluations/{ev}", json={"mark_reviewed": False}, headers=t).status_code == 200  # not a review


@pytest.mark.parametrize("body,decision", [
    ({"accept_ai_score": True}, "accepted_ai_score"),
    ({"teacher_score": None}, "accepted_ai_score"),  # what the review panel sends for "Accept AI score"
    ({"teacher_score": 1.0, "adjustment_reason": "Agree"}, "teacher_mark"),  # equal to the AI score, entered by the teacher
])
def test_review_decisions_are_explicit_and_logged(client, db, body, decision):
    t, tid, _, _, _, _, ev = _submitted(client, db)
    r = client.patch(f"/api/evaluations/{ev}", json=body, headers=t)
    assert r.status_code == 200 and r.json()["status"] == "reviewed"
    entry = db.evaluations.find_one({"_id": ev})["review_log"][-1]
    assert entry["decision"] == decision and str(entry["reviewed_by"]) == tid and entry["at"]


def test_publication_records_who_and_when(client, db):
    t, tid, _, _, a, sub, ev = _submitted(client, db)
    client.patch(f"/api/evaluations/{ev}", json={"accept_ai_score": True}, headers=t)
    assert client.post(f"/api/results/submission/{sub['id']}/publish", headers=t).status_code == 200
    s = db.submissions.find_one({"_id": ObjectId(sub["id"])})
    assert str(s["published_by"]) == tid and s["publication_log"][-1]["action"] == "published" and s["publication_log"][-1]["at"]
    assert str(db.evaluations.find_one({"_id": ev})["published_by"]) == tid
    assert client.post(f"/api/results/submission/{sub['id']}/unpublish", headers=t).status_code == 200
    s = db.submissions.find_one({"_id": ObjectId(sub["id"])})
    assert [e["action"] for e in s["publication_log"]] == ["published", "unpublished"]
    assert s["published_by"] is None and str(s["unpublished_by"]) == tid
    r = client.post(f"/api/results/assessment/{a['id']}/publish", json={}, headers=t).json()  # bulk path
    assert r["published_submissions"] == 1
    assert [e["action"] for e in db.submissions.find_one({"_id": ObjectId(sub["id"])})["publication_log"]][-1] == "published"


def test_historical_publication_records_are_not_backfilled(client, db):
    t, _, _, _, _, sub, _ = _submitted(client, db)
    db.submissions.update_one({"_id": ObjectId(sub["id"])}, {"$set": {"status": "published"}})  # legacy-style record
    s = db.submissions.find_one({"_id": ObjectId(sub["id"])})
    assert "published_by" not in s and "publication_log" not in s  # unknown stays unknown


# ============================== F. V11: student directory ============================================

def test_pilot_directory_lists_only_enrolled_participants(client, db, monkeypatch):
    t, _, _ = reg(client, "teacher")
    _, outsider, _ = reg(client, "student")
    _, insider, _ = reg(client, "student")
    db.users.update_one({"email": insider}, {"$set": {"pilot_enrolled": True}})
    everyone = {s["email"] for s in client.get("/api/users/students", headers=t).json()}
    assert {outsider, insider} <= everyone  # development: unchanged
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    listed = {s["email"] for s in client.get("/api/users/students", headers=t).json()}
    assert insider in listed and outsider not in listed


# ============================== G. V12: TLS and topology =============================================

def _pilot_settings(**over):
    from app.config import Settings

    s = Settings(**over)
    s.pilot_mode = True
    return s


def test_pilot_launcher_refuses_plain_http_beyond_loopback(tmp_path, monkeypatch):
    monkeypatch.delenv("ANSWERWISE_TRANSPORT", raising=False)
    with pytest.raises(SystemExit, match="TLS is required"):
        run_server.transport_mode(_pilot_settings(), "0.0.0.0", None, None)
    with pytest.raises(SystemExit, match="BOTH"):
        run_server.transport_mode(_pilot_settings(), "0.0.0.0", str(tmp_path / "missing.pem"), None)
    with pytest.raises(SystemExit, match="TRUSTED_PROXIES"):
        run_server.transport_mode(_pilot_settings(tls_terminated_by_proxy=True), "0.0.0.0", None, None)
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.write_text("dummy")
    key.write_text("dummy")
    assert run_server.transport_mode(_pilot_settings(), "0.0.0.0", str(cert), str(key)) == "tls-direct"
    assert run_server.transport_mode(_pilot_settings(tls_terminated_by_proxy=True, trusted_proxies="10.0.0.5"),
                                     "0.0.0.0", None, None) == "tls-proxy"
    assert run_server.transport_mode(_pilot_settings(), "127.0.0.1", None, None) == "loopback-plain"
    from app.config import Settings

    assert run_server.transport_mode(Settings(), "0.0.0.0", None, None) == "plain"  # development: warning only


@pytest.mark.parametrize("transport,ok", [("tls-direct", True), ("tls-proxy", True), ("loopback-plain", False),
                                          ("plain", False), ("unknown", False), (None, False)])
def test_preflight_requires_the_server_to_report_tls(scratch_db, monkeypatch, transport, ok):  # noqa: F811
    _health(monkeypatch, _health_for(scratch_db, transport=transport))
    assert pf.run("https://pilot", supervisor_hash())[0] is ok


def test_proxy_tls_declaration_needs_a_proxy(pilot_env):  # noqa: F811
    from app.config import Settings, pilot_config_problems

    pilot_env.setenv("TLS_TERMINATED_BY_PROXY", "true")
    assert any("TLS_TERMINATED_BY_PROXY" in p for p in pilot_config_problems(Settings()))


def test_health_reports_transport_without_secrets(client, monkeypatch):
    monkeypatch.setenv("ANSWERWISE_TRANSPORT", "tls-direct")
    h = client.get("/api/health").json()
    assert h["deployment"]["transport"] == "tls-direct"
    assert get_settings().jwt_secret not in json.dumps(h)
