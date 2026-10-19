"""Sprint 9: no application process may use the protected main database "answerwise" (incident of 2026-10-17,
docs/SPRINT9_INCIDENT_CONTAINMENT.md).

Pure unit tests. Nothing here starts the app, imports app.main, opens a socket or talks to MongoDB:
* settings are built with the local backend/.env DISABLED (or replaced by a temporary file), so the developer's real
  configuration and secrets are never read;
* every MongoClient the code under test could create is replaced by a stub that fails the test if it is called.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import config

BACKEND = Path(__file__).resolve().parent.parent
SAFE_SECRET = "R7q2Vx9LmT4pW8zK1sN6bY3hJ5dF0gC2aE7uQ9iO4wZ"  # test-only value


@pytest.fixture
def env(monkeypatch):
    """Isolated environment: no .env file, no inherited settings that matter here."""
    monkeypatch.setitem(config.Settings.model_config, "env_file", None)
    for k in ("MONGODB_DB", "ENVIRONMENT", "PILOT_MODE", "JWT_SECRET", "CORS_ORIGINS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PILOT_MODE", "false")
    return monkeypatch


def _no_mongo(*_a, **_k):
    raise AssertionError("a MongoClient was created: the protected-database guard must stop before any connection")


@pytest.mark.parametrize("name", ["answerwise", "Answerwise", "ANSWERWISE", " answerwise ", "answerwise\t"])
def test_protected_name_is_refused_in_any_spelling(name):
    assert "protected database 'answerwise'" in config.protected_database_problem(name)


@pytest.mark.parametrize("name", ["answerwise_dev", "answerwise_test_1234", "answerwise_pilot_2027s1", "answerwise2",
                                  "my_answerwise"])
def test_other_names_are_allowed(name):
    assert config.protected_database_problem(name) is None


def test_empty_name_is_refused():
    assert config.protected_database_problem("  ") == "MONGODB_DB is empty"


def test_default_database_is_the_local_development_database(env):
    s = config.get_settings.__wrapped__()
    assert s.mongodb_db == config.LOCAL_DEVELOPMENT_DB == "answerwise_dev"


@pytest.mark.parametrize("environment", ["development", "production"])
def test_selecting_the_protected_database_refuses_to_start_in_every_mode(env, environment):
    env.setenv("ENVIRONMENT", environment)
    env.setenv("JWT_SECRET", SAFE_SECRET)
    env.setenv("CORS_ORIGINS", "https://school.example")
    env.setenv("MONGODB_DB", "answerwise")
    with pytest.raises(RuntimeError, match="Refusing to start: MONGODB_DB selects the protected database"):
        config.get_settings.__wrapped__()
    env.setenv("MONGODB_DB", "answerwise_dev")
    assert config.get_settings.__wrapped__().mongodb_db == "answerwise_dev"  # same mode, other database: starts


def test_guard_reads_the_selected_name_from_the_env_file_too(env, tmp_path):
    """The incident's configuration: MONGODB_DB=answerwise in backend/.env (here a temporary copy, no secrets)."""
    f = tmp_path / ".env"
    f.write_text("ENVIRONMENT=development\nMONGODB_DB=answerwise\n", encoding="utf-8")
    env.setitem(config.Settings.model_config, "env_file", f)
    with pytest.raises(RuntimeError, match="protected database"):
        config.get_settings.__wrapped__()
    env.setenv("MONGODB_DB", "answerwise_dev")  # an explicit environment override wins over the file
    assert config.get_settings.__wrapped__().mongodb_db == "answerwise_dev"


def test_environment_label_does_not_bypass_the_guard(env):
    env.setenv("MONGODB_DB", "answerwise")
    for label in ("development", "Development"):
        env.setenv("ENVIRONMENT", label)
        with pytest.raises(RuntimeError, match="protected database"):
            config.get_settings.__wrapped__()


def test_pilot_mode_still_refuses_development_and_protected_databases(env):
    for name in ("answerwise", "answerwise_dev"):
        s = config.Settings(pilot_mode=True, mongodb_db=name)
        assert any("dedicated pilot database" in p for p in config.pilot_config_problems(s))


def test_get_db_never_connects_to_the_protected_database(env, monkeypatch):
    from app import db as db_module

    env.setenv("MONGODB_DB", "answerwise")
    monkeypatch.setattr(db_module, "MongoClient", _no_mongo)
    monkeypatch.setattr(db_module, "_db", None)
    # get_settings() unwrapped for this module only: the process-wide cached Settings (shared with app.main in a full
    # test run) is left untouched.
    monkeypatch.setattr(db_module, "get_settings", config.get_settings.__wrapped__)
    with pytest.raises(RuntimeError, match="protected database"):
        db_module.get_db()


def test_preflight_does_not_open_the_protected_database(env, monkeypatch):
    import pymongo

    from scripts import pilot_preflight as pf

    env.setenv("MONGODB_DB", "Answerwise")
    monkeypatch.setattr(pymongo, "MongoClient", _no_mongo)
    results = []
    assert pf.check_database(results) is None
    assert results[0][0] == "Pilot database reachable" and results[0][1] == "FAIL"
    assert "not inspected" in results[0][2]


@pytest.mark.parametrize("name", ["answerwise", "answerwise_dev"])
def test_pilot_init_refuses_development_and_protected_databases(name):
    from types import SimpleNamespace

    from scripts import pilot_init_db

    fake_db = SimpleNamespace(name=name, list_collection_names=_no_mongo)
    with pytest.raises(SystemExit, match="development database"):
        pilot_init_db.init(fake_db, SimpleNamespace(pilot_mode=True))


def test_app_main_resolves_settings_at_import_before_the_app_exists():
    """Static check (app.main is NOT imported): the module-level `settings = get_settings()` runs before the FastAPI
    app, its lifespan (ensure_indexes) or any router exists, so uvicorn stops at import time on the protected
    database, before anything can connect."""
    tree = ast.parse((BACKEND / "app" / "main.py").read_text(encoding="utf-8"))
    order = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
            func = node.value.func.id if isinstance(node.value.func, ast.Name) else None
            order.append((target, func))
    assert ("settings", "get_settings") in order and ("app", "FastAPI") in order
    assert order.index(("settings", "get_settings")) < order.index(("app", "FastAPI"))


def test_env_template_uses_the_development_database():
    lines = (BACKEND / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "MONGODB_DB=answerwise_dev" in lines and "MONGODB_DB=answerwise" not in lines


# ---- sprint 10: every command-line entry point stops before connecting --------------------------------------------

def test_seed_refuses_before_connecting(env, monkeypatch):
    from scripts import seed

    env.setenv("MONGODB_DB", "answerwise")
    monkeypatch.setattr(seed, "get_settings", config.get_settings.__wrapped__)
    monkeypatch.setattr(seed, "get_db", _no_mongo)
    monkeypatch.setattr("sys.argv", ["seed", "--reset"])  # the most destructive form: it must not get anywhere
    with pytest.raises(RuntimeError, match="protected database"):
        seed.main()


def test_pilot_launcher_refuses_before_serving(env, monkeypatch):
    import uvicorn

    from scripts import run_server

    env.setenv("MONGODB_DB", "answerwise")
    monkeypatch.setattr(config, "get_settings", config.get_settings.__wrapped__)  # run_server imports it at call time
    monkeypatch.setattr(uvicorn, "Server", _no_mongo)
    monkeypatch.setattr(run_server, "build_config", _no_mongo)
    with pytest.raises(RuntimeError, match="protected database"):
        run_server.main(["--host", "127.0.0.1", "--port", "8000"])


def test_fallback_report_refuses_before_connecting(env, monkeypatch):
    from app import db as db_module
    from scripts import pilot_fallback_report

    env.setenv("MONGODB_DB", "ANSWERWISE")
    monkeypatch.setattr(db_module, "MongoClient", _no_mongo)
    monkeypatch.setattr(db_module, "_db", None)
    monkeypatch.setattr(db_module, "get_settings", config.get_settings.__wrapped__)
    with pytest.raises(RuntimeError, match="protected database"):
        pilot_fallback_report.main()
