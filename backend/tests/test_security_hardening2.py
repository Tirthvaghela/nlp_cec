"""Security hardening sprint 2 (independent audit V1-V5, V8 and the test gaps it listed).

No test runs the scoring engine. Databases are disposable (the conftest test database or answerwise_sec2_<pid>_*);
the development database is never touched. Where the request path matters, tests go through the real ASGI app -
and for proxy headers through uvicorn's own Config.load() middleware stack - rather than calling helpers."""

import asyncio
import hashlib
import io
import json
import os
import time
import uuid

import httpx
import pytest

from app import deployment
from app.config import get_settings
from app.ratelimit import (
    INVITE_IP_LIMIT, LOGIN_IP_LIMIT, LOGIN_MAX_FAILURES, PWCHANGE_MAX_FAILURES, PWCHANGE_WINDOW, RateLimiter, limiter,
)
from scripts import pilot_preflight as pf
from scripts import run_server, seed
from tests.conftest import PASSWORD
from tests.test_pilot_readiness import (  # noqa: F401 (fixtures)
    SAFE, _health, _health_for, pilot_env, scratch_db, supervisor_hash,
)

STRONG = "Xq7-Lm2Vp9_Rt4Kz8Wy"
LAUNCH_VARS = ("ANSWERWISE_LAUNCHER", "ANSWERWISE_CLIENT_ADDRESS_MODE")


@pytest.fixture
def launcher_env():
    """build_config() sets process environment variables: restore them so other tests are unaffected."""
    saved = {k: os.environ.get(k) for k in LAUNCH_VARS}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _settings(**over):
    from app.config import Settings

    return Settings(**over)


async def _logins(asgi_app, peer: str, n: int, spoof: bool):
    """n login attempts (distinct unknown e-mails, so only the per-IP cap can trigger), optionally each with a
    different forged X-Forwarded-For."""
    transport = httpx.ASGITransport(app=asgi_app, client=(peer, 40000))
    codes = []
    async with httpx.AsyncClient(transport=transport, base_url="http://pilot") as c:
        for i in range(n):
            headers = {"X-Forwarded-For": f"198.51.100.{i % 250}"} if spoof else {}
            r = await c.post("/api/auth/login", json={"email": f"u{i}-{uuid.uuid4().hex[:6]}@example.com",
                                                      "password": "Wrong-123"}, headers=headers)
            codes.append(r.status_code)
    return codes


@pytest.fixture
def fast_bcrypt(monkeypatch):
    from app.routers import auth

    monkeypatch.setattr(auth, "verify_password", lambda pw, h: False)  # speed only; the limiter path is unchanged


# ============================== 1. V1: forwarded-header spoofing ====================================

def test_plain_uvicorn_defaults_let_a_local_peer_spoof_its_address(db, fast_bcrypt, launcher_env):
    """Control: why the launcher exists. uvicorn's defaults trust X-Forwarded-For from 127.0.0.1."""
    import uvicorn

    cfg = uvicorn.Config("app.main:app", log_config=None)  # what `uvicorn app.main:app` does
    cfg.load()
    codes = asyncio.run(_logins(cfg.loaded_app, "127.0.0.1", LOGIN_IP_LIMIT + 10, spoof=True))
    assert 429 not in codes  # every forged address gets its own bucket: the per-IP cap is bypassed


def test_pilot_launcher_ignores_forged_forwarded_headers(db, fast_bcrypt, launcher_env):
    cfg = run_server.build_config(_settings(trusted_proxies=""), "0.0.0.0", 8000)
    assert cfg.proxy_headers is False and os.environ["ANSWERWISE_CLIENT_ADDRESS_MODE"] == "direct"
    cfg.load()
    codes = asyncio.run(_logins(cfg.loaded_app, "127.0.0.1", LOGIN_IP_LIMIT + 1, spoof=True))
    assert codes[:LOGIN_IP_LIMIT] == [401] * LOGIN_IP_LIMIT and codes[-1] == 429  # keyed on the real peer


def test_only_explicitly_trusted_proxies_are_believed(db, fast_bcrypt, launcher_env):
    cfg = run_server.build_config(_settings(trusted_proxies="10.0.0.5"), "0.0.0.0", 8000)
    assert cfg.proxy_headers is True and cfg.forwarded_allow_ips == ["10.0.0.5"]  # never the implicit 127.0.0.1
    cfg.load()
    # an untrusted peer forging the header is still keyed on its own address
    codes = asyncio.run(_logins(cfg.loaded_app, "203.0.113.9", LOGIN_IP_LIMIT + 1, spoof=True))
    assert codes[-1] == 429
    limiter.reset()
    # a local process is NOT trusted either (the old default)
    assert asyncio.run(_logins(cfg.loaded_app, "127.0.0.1", LOGIN_IP_LIMIT + 1, spoof=True))[-1] == 429
    limiter.reset()
    # the configured proxy is believed: requests are attributed to the client it reports
    asyncio.run(_logins(cfg.loaded_app, "10.0.0.5", 3, spoof=True))
    with limiter._lock:
        keys = [k for k in limiter._events if k.startswith("ip:/api/auth/login:")]
    assert keys and all("198.51.100." in k for k in keys)


@pytest.mark.parametrize("proxies,pilot,ok", [
    ("*", False, False), ("not-an-ip", False, False), ("127.0.0.1", True, False), ("::1", True, False),
    ("0.0.0.0/0", True, False), ("127.0.0.1", False, True), ("10.0.0.5,10.0.1.0/24", True, True),
])
def test_launcher_refuses_unsafe_trusted_proxies(proxies, pilot, ok, launcher_env):
    s = _settings(trusted_proxies=proxies, pilot_mode=False, tls_terminated_by_proxy=True)  # sprint 3: TLS declared
    s.pilot_mode = pilot  # trusted_proxy_problems reads the flag only
    if ok:
        run_server.build_config(s, "0.0.0.0", 8000)
    else:
        with pytest.raises(SystemExit, match="TRUSTED_PROXIES"):
            run_server.build_config(s, "0.0.0.0", 8000)


def test_pilot_server_refuses_to_start_without_the_launcher(db, monkeypatch, launcher_env):
    from app import main

    os.environ.pop("ANSWERWISE_LAUNCHER", None)
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    deployment.write_marker(db, deployment.PILOT)

    async def start():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="pilot launcher"):
        asyncio.run(start())


# ============================== 2/3/10. V2: mandatory supervisor manifest hash ======================

def _engine_rows(manifest_sha256):
    r = []
    pf.check_engine(r, manifest_sha256)
    return r


@pytest.mark.parametrize("supplied,expected", [
    (None, "missing"), ("", "missing"), ("xyz", "malformed"), ("a" * 63, "malformed"), ("g" * 64, "malformed"),
    ("0" * 64, "differ"),
])
def test_missing_malformed_or_wrong_manifest_hash_fails(supplied, expected):
    row = _engine_rows(supplied)[1]
    assert row[1] == "FAIL" and expected in row[2]


def test_correct_manifest_hash_passes_and_is_case_insensitive():
    assert _engine_rows(supervisor_hash())[1][1] == "PASS"
    assert _engine_rows("  " + supervisor_hash().upper() + "\n")[1][1] == "PASS"


def test_manifest_hash_covers_exact_bytes(tmp_path, monkeypatch):
    original = pf.FROZEN.read_bytes()
    copy = tmp_path / "manifest.json"
    copy.write_bytes(original.replace(b"\n", b"\r\n"))  # same JSON, different bytes
    monkeypatch.setattr(pf, "FROZEN", copy)
    stale = hashlib.sha256(original).hexdigest()
    rows = _engine_rows(stale)
    assert rows[0][1] == "PASS" and rows[1][1] == "FAIL"  # content valid, but not the bytes the supervisor hashed
    assert _engine_rows(hashlib.sha256(copy.read_bytes()).hexdigest())[1][1] == "PASS"


def test_preflight_fails_without_the_supervisor_hash(scratch_db):  # noqa: F811
    ok, results = pf.run()
    assert not ok
    assert any(n.startswith("Manifest equals") and s == "FAIL" and "missing" in d for n, s, d in results)
    ok, _ = pf.run(manifest_sha256=supervisor_hash())
    assert ok


def test_not_verified_never_counts_as_pass(scratch_db, monkeypatch):  # noqa: F811
    real = pf.check_engine

    def soft(results, manifest_sha256=None):
        real(results, manifest_sha256)
        results.append(("Something unconfirmed", "NOT VERIFIED", ""))

    monkeypatch.setattr(pf, "check_engine", soft)
    assert pf.run(manifest_sha256=supervisor_hash())[0] is False


# ============================== 4. V3: atomic rate limiting under concurrency =======================

async def _parallel(app, n, make_request):
    transport = httpx.ASGITransport(app=app, client=("192.0.2.10", 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://pilot") as c:
        return await asyncio.gather(*(make_request(c, i) for i in range(n)))


def test_parallel_wrong_passwords_cannot_exceed_the_account_limit(client, monkeypatch):
    from app.main import app
    from app.routers import auth

    email = f"victim-{uuid.uuid4().hex[:6]}@example.com"
    assert client.post("/api/auth/register", json={"name": "Victim", "email": email, "password": PASSWORD,
                                                   "role": "student"}).status_code == 201
    entered = []

    def slow_wrong(pw, h):  # every admitted attempt overlaps with all others (bcrypt-like delay)
        entered.append(1)
        time.sleep(0.3)
        return False

    monkeypatch.setattr(auth, "verify_password", slow_wrong)
    responses = asyncio.run(_parallel(app, 20, lambda c, i: c.post(
        "/api/auth/login", json={"email": email, "password": f"Guess-{i}"})))
    codes = sorted(r.status_code for r in responses)
    assert codes.count(401) == LOGIN_MAX_FAILURES and codes.count(429) == 20 - LOGIN_MAX_FAILURES
    assert len(entered) == LOGIN_MAX_FAILURES  # never more password checks than the limit


def test_parallel_invite_guesses_cannot_exceed_the_ip_limit(client, monkeypatch):
    from app.main import app
    from app.routers import auth

    monkeypatch.setattr(get_settings(), "teacher_invite_code", STRONG)
    real = auth.hmac.compare_digest
    compared = []

    def slow_compare(a, b):
        compared.append(1)
        time.sleep(0.3)
        return real(a, b)

    monkeypatch.setattr(auth.hmac, "compare_digest", slow_compare)
    responses = asyncio.run(_parallel(app, 20, lambda c, i: c.post("/api/auth/register", json={
        "name": "Guesser", "email": f"g{i}-{uuid.uuid4().hex[:6]}@example.com", "password": PASSWORD,
        "role": "teacher", "invite_code": f"guess-{i}"})))
    codes = [r.status_code for r in responses]
    assert codes.count(403) == INVITE_IP_LIMIT and codes.count(429) == 20 - INVITE_IP_LIMIT
    assert len(compared) == INVITE_IP_LIMIT


def test_reserve_all_is_all_or_nothing():
    rl = RateLimiter(clock=lambda: 0.0)
    assert rl.reserve("b", 1, 60)[0] is not None  # b is full
    taken, wait = rl.reserve_all([("a", 5, 60), ("b", 1, 60)])
    assert taken is None and wait
    assert rl.retry_after("a", 1, 60) is None  # the reservation on "a" was rolled back
    token, _ = rl.reserve("c", 1, 60)
    rl.release("c", token)
    assert rl.reserve("c", 1, 60)[0] is not None  # a released (successful) attempt does not count


# ============================== 5. V4: expiry, cleanup, bounded storage =============================

def test_expired_one_off_keys_are_swept():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0], sweep_interval=10)
    for i in range(1000):
        rl.reserve(f"login-fail:oneoff{i}@example.com", 5, 60)
    assert rl.size() == 1000
    t[0] = 75  # all expired, sweep interval elapsed
    rl.reserve("fresh", 5, 60)
    assert rl.size() == 1


def test_storage_is_bounded_without_evicting_live_lockouts():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0], max_keys=3, sweep_interval=1e9)
    for _ in range(2):
        rl.reserve("victim", 2, 60)
    assert rl.reserve("victim", 2, 60)[0] is None  # locked
    rl.reserve("x1", 5, 60)
    rl.reserve("x2", 5, 60)
    token, wait = rl.reserve("flood-new-key", 5, 60)
    assert token is None and wait  # table full of live keys: the newcomer is refused...
    assert rl.reserve("victim", 2, 60)[0] is None  # ...and the victim's lockout was NOT evicted
    t[0] = 61  # everything expires: room again
    assert rl.reserve("flood-new-key", 5, 60)[0] is not None and rl.size() == 1


def test_read_only_checks_do_not_create_keys():
    rl = RateLimiter()
    for i in range(100):
        assert rl.retry_after(f"probe{i}", 5, 60) is None
    assert rl.size() == 0


# ============================== 6. V5: password-change throttling ==================================

def test_password_change_failures_are_throttled(client):
    r = client.post("/api/auth/register", json={"name": "Owner", "email": f"o-{uuid.uuid4().hex[:6]}@example.com",
                                                "password": PASSWORD, "role": "student"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for i in range(PWCHANGE_MAX_FAILURES):
        r = client.post("/api/auth/change-password", json={"current_password": f"Wrong-{i}x", "new_password": "NewPassw0rd"},
                        headers=h)
        assert r.status_code == 403
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "NewPassw0rd"},
                    headers=h)
    assert r.status_code == 429 and 1 <= int(r.headers["Retry-After"]) <= PWCHANGE_WINDOW  # even the right one


def test_legitimate_password_change_still_works_and_resets_the_counter(client):
    email = f"ok-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/auth/register", json={"name": "Owner", "email": email, "password": PASSWORD, "role": "student"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for _ in range(PWCHANGE_MAX_FAILURES - 1):
        client.post("/api/auth/change-password", json={"current_password": "Wrong-1x", "new_password": "NewPassw0rd"}, headers=h)
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "NewPassw0rd"}, headers=h)
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}  # sprint 3: the old token is revoked; use the renewed one
    assert client.post("/api/auth/login", json={"email": email, "password": "NewPassw0rd"}).status_code == 200
    for _ in range(PWCHANGE_MAX_FAILURES - 1):  # counter was cleared by the success
        assert client.post("/api/auth/change-password", json={"current_password": "Wrong-1x", "new_password": "Other1234"},
                           headers=h).status_code == 403


def test_password_change_has_a_per_ip_cap(client):
    for _ in range(30):
        client.post("/api/auth/change-password", content=b"{}", headers={"Content-Type": "application/json"})
    r = client.post("/api/auth/change-password", json={"current_password": "x", "new_password": "NewPassw0rd"})
    assert r.status_code == 429  # counted before authentication or body parsing


# ============================== 7. real health endpoint + real preflight ============================

class _StubBackend:  # model-loading status only; nothing is scored
    name, model_name, fallback_reason = "embedding", "sentence-transformers/all-MiniLM-L6-v2", None


def _serve_health(monkeypatch, server_db):
    """Run the REAL /api/health against server_db with a pilot-like configuration; feed its exact JSON to the
    preflight's HTTP call."""
    from fastapi.testclient import TestClient

    from app import main
    from app.db import set_db

    s = get_settings()
    for k, v in dict(pilot_mode=True, environment="production", require_review_before_publish=True, preload_model=True,
                     teacher_invite_code=STRONG).items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(main, "loaded_backend", lambda: _StubBackend())
    monkeypatch.setenv("ANSWERWISE_CLIENT_ADDRESS_MODE", "direct")
    monkeypatch.setenv("ANSWERWISE_TRANSPORT", "tls-direct")  # sprint 3: the launcher reports TLS
    set_db(server_db)
    body = TestClient(main.app).get("/api/health").content  # no lifespan: nothing else starts
    monkeypatch.setattr(pf.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(body))
    return json.loads(body)


def test_real_health_and_preflight_agree_on_identity(scratch_db, database, monkeypatch):  # noqa: F811
    from app.db import set_db

    try:
        h = _serve_health(monkeypatch, scratch_db)
        ok, results = pf.run("https://pilot", supervisor_hash())
    finally:
        set_db(database)
    assert h["deployment"]["database_fingerprint"] == deployment.fingerprint(scratch_db, deployment.read_marker(scratch_db))
    assert ok, [r for r in results if r[1] not in ("PASS", "INFO", "NOTE")]


def test_real_health_on_another_database_is_rejected(scratch_db, database, monkeypatch):  # noqa: F811
    from pymongo import MongoClient

    from app.db import set_db

    other = MongoClient(get_settings().mongodb_uri)[f"answerwise_sec2_{os.getpid()}_other"]  # sprint 5 setup: MONGODB_URI
    deployment.write_marker(other, deployment.PILOT)
    try:
        _serve_health(monkeypatch, other)
        ok, results = pf.run("https://pilot", supervisor_hash())
    finally:
        set_db(database)
        other.client.drop_database(other.name)
    row = next(r for r in results if r[0] == "Server and preflight use the same pilot database")
    assert not ok and row[1] == "FAIL"


# ============================== 8. V8: seed safety on unmarked, non-user data ======================

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
        name = f"answerwise_sec2_{os.getpid()}_{tag}"
        assert name != "answerwise"
        names.append(name)
        return c[name]

    yield make
    for n in names:
        c.drop_database(n)


def _dev():
    return _settings(environment="development", pilot_mode=False)


def test_seed_refuses_unmarked_zero_user_database_with_other_data(mongo):
    db = mongo("nousers")
    db.assessments.insert_one({"title": "Real course work", "source": "teacher"})
    with pytest.raises(SystemExit, match="no demo accounts"):
        seed.check_seed_target(db, _dev(), reset=True)
    db2 = mongo("enrollonly")
    db2.enrollments.insert_one({"email": "pupil@school.example"})
    with pytest.raises(SystemExit, match="enrollments present"):
        seed.check_seed_target(db2, _dev(), reset=True)


def test_seed_refuses_demo_users_mixed_with_non_seed_data(mongo):
    db = mongo("mixed")
    db.users.insert_one({"email": "teacher@answerwise.dev"})
    a = db.assessments.insert_one({"source": "seed"}).inserted_id
    db.questions.insert_one({"assessment_id": a})
    db.submissions.insert_one({"source": "student"})  # not seed data
    with pytest.raises(SystemExit, match="submissions not created by the seed"):
        seed.check_seed_target(db, _dev(), reset=True)
    db.submissions.delete_many({})
    db.evaluations.insert_one({"submission_id": "elsewhere"})
    with pytest.raises(SystemExit, match="evaluations outside seeded submissions"):
        seed.check_seed_target(db, _dev(), reset=True)
    db.evaluations.delete_many({})
    seed.check_seed_target(db, _dev(), reset=True)  # now identifiably demo-only: allowed


def test_seed_refuses_malformed_markers(mongo):
    db = mongo("badmarker")
    db[deployment.MARKER_COLLECTION].insert_one({"_id": deployment.MARKER_ID, "kind": "development"})  # no instance_id
    with pytest.raises(SystemExit, match="instance_id"):
        seed.check_seed_target(db, _dev(), reset=True)


# ============================== 9. V8: marker validation, identity binding ==========================

@pytest.mark.parametrize("marker,problem", [
    ({"_id": "deployment", "kind": "pilot", "created_at": 1}, "instance_id"),
    ({"_id": "deployment", "kind": "pilot", "instance_id": "XYZ", "created_at": 1}, "instance_id"),
    ({"_id": "deployment", "kind": "pilot", "instance_id": "a" * 32}, "created_at"),
])
def test_pilot_server_refuses_malformed_markers(db, monkeypatch, launcher_env, marker, problem):
    from app import main

    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    os.environ["ANSWERWISE_LAUNCHER"] = "1"
    db[deployment.MARKER_COLLECTION].insert_one(marker)

    async def start():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match=problem):
        asyncio.run(start())
    assert deployment.fingerprint(db, deployment.read_marker(db)) is None


def test_fingerprint_is_bound_to_the_mongodb_server(mongo, monkeypatch):
    db = mongo("bound")
    marker = deployment.write_marker(db, deployment.PILOT)
    here = deployment.fingerprint(db, marker)
    assert here and len(here) == 16
    monkeypatch.setattr(deployment, "server_identity", lambda d: "other-host:27017")  # same name + marker, other server
    assert deployment.fingerprint(db, marker) not in (None, here)
    monkeypatch.setattr(deployment, "server_identity", lambda d: None)  # unknown server -> no identity (fail closed)
    assert deployment.fingerprint(db, marker) is None


def test_preflight_rejects_a_marker_without_instance_id(scratch_db):  # noqa: F811
    scratch_db[deployment.MARKER_COLLECTION].update_one({"_id": deployment.MARKER_ID}, {"$unset": {"instance_id": ""}})
    ok, results = pf.run(manifest_sha256=supervisor_hash())
    row = next(r for r in results if r[0] == "Database carries the pilot marker")
    assert not ok and row[1] == "FAIL" and "instance_id" in row[2]
