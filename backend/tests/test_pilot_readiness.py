"""Classroom pilot safeguards: PILOT_MODE fail-safe, seed guard, read-only pre-flight. No scoring involved.

The pre-flight database checks run against a throw-away database (answerwise_preflight_test_<pid>), never the
development database."""

import io
import json
import os

import pytest

from app import config
from scripts import pilot_preflight as pf

SAFE = {
    "ENVIRONMENT": "production", "PILOT_MODE": "true", "REQUIRE_REVIEW_BEFORE_PUBLISH": "true",
    # test-only values (not a real deployment's secret or origin); sprint 3 requires a random-looking secret and https
    "JWT_SECRET": "R7q2Vx9LmT4pW8zK1sN6bY3hJ5dF0gC2aE7uQ9iO4wZ", "TEACHER_INVITE_CODE": "Xq7-Lm2Vp9_Rt4Kz8Wy", "MONGODB_DB": f"answerwise_preflight_test_{os.getpid()}",
    "SIMILARITY_BACKEND": "embedding", "CORS_ORIGINS": "https://pilot.example", "PRELOAD_MODEL": "true",
}


@pytest.fixture
def pilot_env(monkeypatch):
    for k, v in SAFE.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def test_safe_pilot_configuration_has_no_problems(pilot_env):
    assert config.pilot_config_problems(config.Settings()) == []
    assert config.get_settings.__wrapped__().pilot_mode is True  # starts


@pytest.mark.parametrize("key,value,expected", [
    ("REQUIRE_REVIEW_BEFORE_PUBLISH", "false", "REQUIRE_REVIEW_BEFORE_PUBLISH"),
    ("ENVIRONMENT", "development", "ENVIRONMENT"),
    ("JWT_SECRET", "change-me-to-a-long-random-string", "JWT_SECRET"),
    ("JWT_SECRET", "short", "JWT_SECRET"),
    ("TEACHER_INVITE_CODE", "", "TEACHER_INVITE_CODE"),
    ("TEACHER_INVITE_CODE", "x", "too weak"),
    ("TEACHER_INVITE_CODE", "pilot-code", "too weak"),
    ("PRELOAD_MODEL", "false", "PRELOAD_MODEL"),
    ("MONGODB_DB", "answerwise", "dedicated pilot database"),
    ("SIMILARITY_BACKEND", "tfidf", "SIMILARITY_BACKEND"),
    ("CORS_ORIGINS", "*", "CORS_ORIGINS"),
])
def test_pilot_mode_refuses_to_start_on_unsafe_configuration(pilot_env, key, value, expected):
    pilot_env.setenv(key, value)
    with pytest.raises(RuntimeError, match=expected):
        config.get_settings.__wrapped__()


def test_pilot_mode_off_keeps_development_behaviour(monkeypatch):
    monkeypatch.setenv("PILOT_MODE", "false")
    monkeypatch.setenv("REQUIRE_REVIEW_BEFORE_PUBLISH", "false")
    assert config.get_settings.__wrapped__().pilot_mode is False  # no exception: existing workflow unchanged


@pytest.mark.parametrize("env", [{"ENVIRONMENT": "production"}, {"PILOT_MODE": "true"}])
def test_seed_refuses_production_and_pilot_databases(monkeypatch, env):
    from scripts import seed

    monkeypatch.setattr(seed, "get_settings", lambda: config.Settings(**{k.lower(): v for k, v in env.items()}))
    monkeypatch.setattr(seed, "get_db", lambda: pytest.fail("seed must not touch the database"))
    monkeypatch.setattr("sys.argv", ["seed"])
    with pytest.raises(SystemExit, match="Refusing to seed"):
        seed.main()


@pytest.fixture
def scratch_db(pilot_env):
    from pymongo import MongoClient

    # Sprint 5 setup: the server the preflight uses (MONGODB_URI), not a hard-coded localhost:27017.
    client = MongoClient(config.Settings().mongodb_uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except Exception:  # noqa: BLE001
        pytest.skip("MongoDB not available")
    name = SAFE["MONGODB_DB"]
    assert name != config.DEVELOPMENT_DB
    from app import deployment

    db = client[name]
    deployment.write_marker(db, deployment.PILOT)  # a fresh pilot database, as initialised by scripts.pilot_init_db
    yield db
    client.drop_database(name)


def supervisor_hash() -> str:
    """What the supervisor computes and keeps outside the project: SHA-256 of the manifest's exact bytes."""
    import hashlib

    return hashlib.sha256(pf.FROZEN.read_bytes()).hexdigest()


def _health_for(db, **deployment_overrides):
    from app import deployment

    d = {"environment": "production", "pilot_mode": True, "require_review_before_publish": True, "preload_model": True,
         "teacher_invite_code_configured": True, "teacher_invite_code_strong": True, "database_marker": "pilot",
         "database_marker_valid": True, "client_address_mode": "direct", "trusted_proxy_count": 0, "transport": "tls-direct",
         "database_fingerprint": deployment.fingerprint(db, deployment.read_marker(db))}
    # Sprint 5 (A4) setup: a current server also reports the model cache it resolves (here: the preflight's own).
    from app import model_cache

    d["model_cache"] = {"cache_id": model_cache.cache_id(), "conflicts": False,
                        "revision": json.loads(pf.FROZEN.read_text(encoding="utf-8"))["model_artifacts"]["revision"]}
    d.update(deployment_overrides)
    return {"status": "ok", "engine_version": "4.1.0", "similarity_backend": "embedding",
            "model": "sentence-transformers/all-MiniLM-L6-v2", "fallback_reason": None,
            "require_review_before_publish": d["require_review_before_publish"], "pilot_mode": d["pilot_mode"],
            "deployment": d}


def test_preflight_passes_on_a_fresh_pilot_database(scratch_db):
    ok, results = pf.run(manifest_sha256=supervisor_hash())
    assert ok, results
    status = {name: s for name, s, _ in results}
    assert status["No demo accounts or seeded demo data in the pilot database"] == "PASS"
    assert any("frozen pilot engine" in n and s == "PASS" for n, s, _ in results)


def test_preflight_fails_on_demo_accounts_without_printing_them(scratch_db, capsys):
    scratch_db.users.insert_one({"email": "teacher@answerwise.dev", "role": "teacher"})
    scratch_db.submissions.insert_one({"source": "seed"})
    with pytest.raises(SystemExit) as exc:
        pf.main([])
    out = capsys.readouterr().out
    assert exc.value.code == 1 and "PREFLIGHT FAILED" in out
    assert "demo accounts: 1, seeded documents: 1" in out and "teacher@answerwise.dev" not in out
    assert SAFE["JWT_SECRET"] not in out


def test_preflight_fails_on_unsafe_configuration(scratch_db, monkeypatch):
    monkeypatch.setenv("REQUIRE_REVIEW_BEFORE_PUBLISH", "false")
    ok, results = pf.run()
    assert not ok and any(s == "FAIL" and "REQUIRE_REVIEW_BEFORE_PUBLISH" in d for _, s, d in results)


def test_preflight_fails_when_the_engine_differs(scratch_db, monkeypatch):
    import evaluation.real_study as rs

    edited = dict(rs.frozen_engine(), nlp_source_sha256="0" * 64)  # as if a scoring file had been edited
    monkeypatch.setattr(rs, "frozen_engine", lambda: edited)
    ok, results = pf.run()
    assert not ok and any("frozen pilot engine" in n and s == "FAIL" for n, s, _ in results)


def _health(monkeypatch, payload):
    monkeypatch.setattr(pf.urllib.request, "urlopen",
                        lambda *a, **k: io.BytesIO(json.dumps(payload).encode()) if payload is not None else (_ for _ in ()).throw(OSError("refused")))


@pytest.mark.parametrize("change,expected_ok", [
    ({}, True),
    ({"deployment": {"require_review_before_publish": False}}, False),
    ({"similarity_backend": "tfidf", "fallback_reason": "Embedding model unavailable"}, False),
    ({"similarity_backend": "loading"}, False),  # unconfirmed -> fail closed
    (None, False),  # server unreachable -> fail closed
])
def test_preflight_checks_the_running_server_and_fails_closed(scratch_db, monkeypatch, change, expected_ok):
    payload = None
    if change is not None:
        payload = _health_for(scratch_db, **change.pop("deployment", {}))
        payload.update(change)
    _health(monkeypatch, payload)
    ok, _ = pf.run("https://localhost:8000", supervisor_hash())  # sprint 5 (A2): https required in the pilot
    assert ok is expected_ok


def test_health_reports_pilot_flags(client):
    h = client.get("/api/health").json()
    assert h["pilot_mode"] is False and h["require_review_before_publish"] is False
    assert h["deployment"]["pilot_mode"] is False and h["deployment"]["database_marker"] is None
