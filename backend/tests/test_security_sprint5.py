"""Sprint 5: closing audit findings A1-A9 (pilot override API, https preflight, every settings key, model cache
location, environment names, enrollment events, re-evaluation publication record, strict CORS).

No test here runs the scoring engine or loads the embedding model: the API fixture below does not request the session
``backend`` fixture, ``run_engine`` is replaced by a stub where an evaluation is needed, and an autouse guard fails the
test if the real engine or model loader is reached. Model-cache tests use fake cache directories under tmp_path.
"""

from __future__ import annotations

import datetime
import http.server
import io
import ipaddress
import json
import ssl
import threading

import pytest
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app import model_cache
from app.config import Settings, canonical_origin, cors_problems, get_settings
from app.services import evaluation_service, publication
from scripts import pilot_preflight as pf
from scripts import run_server
from tests.conftest import make_assessment, register, submit


@pytest.fixture(autouse=True)
def _no_scoring(monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("the scoring engine / embedding model must not run in this test module")

    monkeypatch.setattr(evaluation_service, "evaluate_answer", forbidden)
    monkeypatch.setattr(evaluation_service, "get_backend", forbidden)


@pytest.fixture
def api(db):
    """TestClient without the session `backend` fixture: the embedding model is never loaded."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def pilot(monkeypatch):
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    return monkeypatch


# ============================== A1: overrides cannot be saved in PILOT_MODE ===========================

def _question(assessment_id, **settings):
    from tests.conftest import QUESTION

    return {"assessment_id": assessment_id, **QUESTION, "settings": settings}


def test_pilot_refuses_saving_threshold_overrides(api, pilot, db):
    teacher = register(api, "teacher")
    a = make_assessment(api, teacher, publish=False)
    r = api.post("/api/questions", json=_question(a["id"], match_threshold=0.7), headers=teacher["headers"])
    assert r.status_code == 403 and r.json()["code"] == "pilot_overrides_disabled"
    qid = a["question"]["id"]
    r = api.patch(f"/api/questions/{qid}", json={"settings": {"partial_threshold": 0.3}}, headers=teacher["headers"])
    assert r.status_code == 403 and r.json()["code"] == "pilot_overrides_disabled"
    assert db.questions.find_one({"text": a["question"]["text"]})["settings"] == {}  # nothing was written
    # removing or not setting an override stays possible
    r = api.patch(f"/api/questions/{qid}", json={"settings": {"match_threshold": None, "partial_threshold": None}},
                  headers=teacher["headers"])
    assert r.status_code == 200
    r = api.post("/api/questions", json=_question(a["id"]), headers=teacher["headers"])
    assert r.status_code == 201


def test_overrides_still_work_outside_the_pilot(api, db):
    teacher = register(api, "teacher")
    a = make_assessment(api, teacher, publish=False)
    r = api.patch(f"/api/questions/{a['question']['id']}", json={"settings": {"match_threshold": 0.7}},
                  headers=teacher["headers"])
    assert r.status_code == 200 and r.json()["settings"] == {"match_threshold": 0.7}


# ============================== A2: https-only preflight with real certificate checks =================

@pytest.mark.parametrize("url,https,expected", [
    ("https://pilot.example:8000", True, None),
    ("https://pilot.example", True, None),
    ("https://pilot.example/", True, None),
    ("http://pilot.example:8000", True, "must use https"),
    ("http://localhost:8000", False, None),  # development target outside the pilot
    ("pilot.example:8000", True, "absolute URL"),
    ("//pilot.example", True, "absolute URL"),
    ("ftp://pilot.example", True, "absolute URL"),
    ("https://", True, "no host"),
    ("https://pilot.example:99999", True, "malformed"),
    ("https://pilot.example:abc", True, "malformed"),
    ("https://[::1", True, "malformed"),
    ("https://user:pw@pilot.example", True, "base URL only"),
    ("https://pilot.example/api", True, "base URL only"),
    ("https://pilot.example?x=1", True, "base URL only"),
    (" https://pilot.example", True, "whitespace"),
    ("", True, "empty"),
])
def test_preflight_url_must_be_an_absolute_https_base_url(url, https, expected):
    problems = pf.target_url_problems(url, require_https=https)
    if expected is None:
        assert problems == []
    else:
        assert any(expected in p for p in problems), problems


def test_preflight_refuses_a_plain_http_url_in_pilot_mode_before_connecting(monkeypatch):
    monkeypatch.setenv("PILOT_MODE", "true")
    monkeypatch.setattr(pf.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not connect"))
    results = []
    pf.check_server(results, "http://pilot.example:8000", None)
    assert results == [("Server URL is an absolute https URL", "FAIL", results[0][2])] and "https" in results[0][2]
    results = []
    pf.check_server(results, "", None)  # an empty --url is a failure (run() no longer treats it as "no --url")
    assert results[0][:2] == ("Server URL is an absolute https URL", "FAIL")


def test_preflight_always_verifies_certificates():
    ctx = pf.tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_preflight_passes_a_verifying_context_and_rejects_redirects(monkeypatch):
    seen = {}

    class Response(io.BytesIO):
        def __init__(self, final):
            super().__init__(b"{}")
            self.final = final

        def geturl(self):
            return self.final

    def fake(url, timeout, context):
        seen["context"] = context
        return Response(url)

    monkeypatch.setattr(pf.urllib.request, "urlopen", fake)
    results = []
    pf.check_server(results, "https://pilot.example", None)
    assert seen["context"].verify_mode == ssl.CERT_REQUIRED and seen["context"].check_hostname
    assert ("Preflight reached the server over HTTPS and verified its certificate and host name itself", "PASS", "") in results
    monkeypatch.setattr(pf.urllib.request, "urlopen", lambda url, timeout, context: Response("http://elsewhere/api/health"))
    results = []
    pf.check_server(results, "https://pilot.example", None)
    assert results[-1][0] == "Server answered at the requested URL (no redirect)" and results[-1][1] == "FAIL"


def _certificate(tmp_path, dns=(), ips=()):
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sprint5 throw-away test certificate")])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return str(cert_file), str(key_file)


@pytest.fixture
def tls_health_server():
    """A minimal stdlib HTTPS server on 127.0.0.1 (NOT the application) answering /api/health with {}."""
    servers = []

    def start(cert, key):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"https://127.0.0.1:{srv.server_address[1]}"

    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def _row(results, name):
    return next((r for r in results if r[0] == name), None)


VERIFIED_ROW = "Preflight reached the server over HTTPS and verified its certificate and host name itself"


def test_preflight_fails_on_an_unverifiable_certificate(tmp_path, tls_health_server):
    cert, key = _certificate(tmp_path, ips=("127.0.0.1",))
    url = tls_health_server(cert, key)
    results = []
    pf.check_server(results, url, None)  # self-signed, CA not supplied
    row = _row(results, "Running server /api/health")
    assert row[1] == "UNVERIFIED" and "certificate could not be verified" in row[2]
    assert _row(results, VERIFIED_ROW) is None


def test_preflight_fails_on_a_certificate_for_another_host(tmp_path, tls_health_server):
    cert, key = _certificate(tmp_path, dns=("pilot.example",))
    url = tls_health_server(cert, key)
    results = []
    pf.check_server(results, url, None, cafile=cert)  # trusted CA, but the name does not match 127.0.0.1
    assert _row(results, "Running server /api/health")[1] == "UNVERIFIED"


def test_preflight_accepts_a_certificate_from_the_supplied_ca(tmp_path, tls_health_server):
    cert, key = _certificate(tmp_path, ips=("127.0.0.1",))
    url = tls_health_server(cert, key)
    results = []
    pf.check_server(results, url, None, cafile=cert)
    assert _row(results, VERIFIED_ROW) == (VERIFIED_ROW, "PASS", "")
    # this stub server reports no deployment identity, so the preflight still fails closed
    assert _row(results, "Server reports its deployment identity")[1] == "FAIL"


# ============================== A3: every per-question settings key ===================================

def test_every_engine_config_field_counts_as_a_scoring_override():
    from app.nlp.config import EvaluationConfig

    for field in EvaluationConfig.__dataclass_fields__:
        assert pf.settings_override_problems({field: 1}) == [f"scoring override '{field}'"]


@pytest.mark.parametrize("settings,expected", [
    (None, []), ({}, []), ({"match_threshold": None, "partial_threshold": None}, []),
    ({"match_threshold": 0.7}, ["scoring override 'match_threshold'"]),
    ({"keyword_weight": 0.0}, ["scoring override 'keyword_weight'"]),  # not settable by the API, still applied
    ({"debias_weight": 0.5, "round_to": 1.0}, ["scoring override 'debias_weight'", "scoring override 'round_to'"]),
    ({"colour": "blue"}, ["unknown settings key 'colour'"]),
    ("loose", ["settings is not an object (str)"]),
    ([1], ["settings is not an object (list)"]),
])
def test_settings_override_classification(settings, expected):
    assert pf.settings_override_problems(settings) == expected


def test_preflight_fails_on_any_settings_key_written_directly_to_the_database(db):
    name = "No per-question scoring overrides of any kind (they are outside the frozen identity)"
    db.questions.insert_many([{"text": "a", "settings": {}}, {"text": "b", "settings": {"match_threshold": None}}])
    results = []
    pf.check_database(results)
    assert _row(results, name)[1] == "PASS"
    db.questions.insert_many([{"text": "c", "settings": {"keyword_weight": 0.9}}, {"text": "d", "settings": {"x": 1}},
                              {"text": "e", "settings": {"keyword_weight": 0.1}}])
    results = []
    pf.check_database(results)
    row = _row(results, name)
    assert row[1] == "FAIL"
    assert "scoring override 'keyword_weight' (2 question(s))" in row[2] and "unknown settings key 'x' (1" in row[2]
    assert "0.9" not in row[2]  # names only, never values
    assert db.questions.count_documents({}) == 5  # read-only: nothing removed or rewritten


# ============================== A4: one model location ================================================

def _env(**kw):
    return {k: str(v) for k, v in kw.items()}


def test_hub_cache_precedence_matches_the_libraries(tmp_path):
    a, b, c, d = (tmp_path / x for x in "abcd")
    assert model_cache.hub_cache_dir(_env(HF_HUB_CACHE=a, HUGGINGFACE_HUB_CACHE=b, HF_HOME=c, XDG_CACHE_HOME=d)) == a
    assert model_cache.hub_cache_dir(_env(HUGGINGFACE_HUB_CACHE=b, HF_HOME=c, XDG_CACHE_HOME=d)) == b
    assert model_cache.hub_cache_dir(_env(HF_HOME=c, XDG_CACHE_HOME=d)) == c / "hub"
    assert model_cache.hub_cache_dir(_env(XDG_CACHE_HOME=d)) == d / "huggingface" / "hub"


MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@pytest.mark.parametrize("var", model_cache.REDIRECT_VARS)
def test_variables_that_redirect_the_model_are_conflicts(tmp_path, var):
    hub = tmp_path / "hub"
    assert model_cache.cache_problems(MODEL, _env(HF_HUB_CACHE=hub, **{var: tmp_path / "elsewhere"}))
    assert model_cache.cache_problems(MODEL, _env(HF_HUB_CACHE=hub, **{var: hub})) == []  # same place: fine
    assert any("set but empty" in p for p in model_cache.cache_problems(MODEL, {"HF_HUB_CACHE": str(hub), var: ""}))


def test_conflicting_hub_variables_and_local_shadow_directory(tmp_path):
    assert model_cache.cache_problems(MODEL, _env(HF_HUB_CACHE=tmp_path / "a", HUGGINGFACE_HUB_CACHE=tmp_path / "b"))
    (tmp_path / "work" / MODEL).mkdir(parents=True)
    problems = model_cache.cache_problems(MODEL, _env(HF_HUB_CACHE=tmp_path / "hub"), workdirs=(tmp_path / "work",))
    assert any("local path" in p for p in problems)


def _fake_cache(root, files: dict[str, bytes], revision="a" * 40):
    repo = root / ("models--" + MODEL.replace("/", "--"))
    (repo / "refs").mkdir(parents=True)
    (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    snap = repo / "snapshots" / revision
    snap.mkdir(parents=True)
    for name, data in files.items():
        (snap / name).write_bytes(data)
    return revision


def _model_rows(monkeypatch, cache, manifest_files, revision="a" * 40):
    import hashlib

    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    for var in (*model_cache.REDIRECT_VARS, "HUGGINGFACE_HUB_CACHE"):
        monkeypatch.delenv(var, raising=False)
    manifest = {"model": MODEL, "runtime": {}, "model_artifacts": {
        "revision": revision, "files": {k: hashlib.sha256(v).hexdigest() for k, v in manifest_files.items()}}}
    results = []
    pf.check_model_and_runtime(results, manifest)
    return {n: (s, d) for n, s, d in results}


MODEL_ROW = "Model weights, tokenizer and config on disk equal the frozen snapshot (exact bytes)"
LOCATION_ROW = "Model location is unambiguous (only the hashed cache can be loaded)"


def test_preflight_hashes_the_resolved_cache_and_fails_on_conflicts(tmp_path, monkeypatch):
    files = {"config.json": b"{}", "model.safetensors": b"fake weights"}  # not a real model: nothing can load it
    _fake_cache(tmp_path / "hub", files)
    rows = _model_rows(monkeypatch, tmp_path / "hub", files)
    assert rows[MODEL_ROW][0] == "PASS" and rows[LOCATION_ROW][0] == "PASS"
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(tmp_path / "other"))
    results = []
    pf.check_model_and_runtime(results, {"model": MODEL, "runtime": {}, "model_artifacts": {"revision": "a" * 40,
                                                                                           "files": {}}})
    row = _row(results, LOCATION_ROW)
    assert row[1] == "FAIL" and "SENTENCE_TRANSFORMERS_HOME" in row[2]
    assert str(tmp_path) not in row[2]  # names the variable, not its value


def test_preflight_fails_on_missing_or_different_model_files(tmp_path, monkeypatch):
    files = {"config.json": b"{}", "model.safetensors": b"fake weights"}
    _fake_cache(tmp_path / "hub", {"config.json": b"{}"})  # weights missing
    assert _model_rows(monkeypatch, tmp_path / "hub", files)[MODEL_ROW][0] == "FAIL"
    _fake_cache(tmp_path / "hub2", {**files, "model.safetensors": b"other weights"})
    assert "differs" in _model_rows(monkeypatch, tmp_path / "hub2", files)[MODEL_ROW][1]
    assert "not found" in _model_rows(monkeypatch, tmp_path / "empty", files)[MODEL_ROW][1]


def test_preflight_fails_when_the_configured_model_is_not_the_frozen_one(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
    files = {"config.json": b"{}"}
    _fake_cache(tmp_path / "hub", files)
    rows = _model_rows(monkeypatch, tmp_path / "hub", files)
    assert rows["Configured model (EMBEDDING_MODEL) is the frozen model"][0] == "FAIL"


@pytest.mark.parametrize("server_cache,ok", [
    (lambda rev: {"cache_id": model_cache.cache_id(), "revision": rev, "conflicts": False}, True),
    (lambda rev: {"cache_id": "0" * 16, "revision": rev, "conflicts": False}, False),  # other cache path
    (lambda rev: {"cache_id": model_cache.cache_id(), "revision": "b" * 40, "conflicts": False}, False),
    (lambda rev: {"cache_id": model_cache.cache_id(), "revision": rev, "conflicts": True}, False),
    (lambda rev: None, False),  # older server: not reported -> fail closed
])
def test_preflight_binds_to_the_cache_the_server_resolves(monkeypatch, server_cache, ok):
    rev = json.loads(pf.FROZEN.read_text(encoding="utf-8"))["model_artifacts"]["revision"]
    payload = {"deployment": {"model_cache": server_cache(rev)}}
    monkeypatch.setattr(pf.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))
    results = []
    pf.check_server(results, "https://pilot.example", None)
    row = _row(results, "Server: resolves the model cache hashed here, at the frozen revision, with no conflicting "
                        "cache settings")
    assert row[1] == ("PASS" if ok else "FAIL")


def test_launcher_refuses_an_ambiguous_model_location_in_pilot_mode(tmp_path, monkeypatch):
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "ANSWERWISE_LAUNCHER", "ANSWERWISE_CLIENT_ADDRESS_MODE",
              "ANSWERWISE_TRANSPORT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(tmp_path / "elsewhere"))
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.write_text("dummy")
    key.write_text("dummy")
    s = Settings()
    s.pilot_mode = True
    with pytest.raises(SystemExit, match="SENTENCE_TRANSFORMERS_HOME"):
        run_server.build_config(s, "0.0.0.0", 8443, str(cert), str(key))
    import os

    assert "ANSWERWISE_LAUNCHER" not in os.environ  # refused before the process was marked as launched


def test_health_reports_the_model_cache_without_its_path(api):
    h = api.get("/api/health").json()
    mc = h["deployment"]["model_cache"]
    assert set(mc) == {"cache_id", "revision", "conflicts"} and mc["cache_id"] == model_cache.cache_id()
    assert "huggingface" not in json.dumps(h).lower() and "users" not in json.dumps(h).lower()  # no path


# ============================== A5: environment names ================================================

@pytest.mark.parametrize("value,expected", [
    ("production", "production"), ("Production", "production"), ("PRODUCTION", "production"),
    (" production ", "production"), ("development", "development"), ("Development", "development"),
])
def test_environment_names_are_normalised(value, expected):
    assert Settings(_env_file=None, environment=value).environment == expected


@pytest.mark.parametrize("value", ["prod", "pilot", "staging", "", "production2", "dev"])
def test_unknown_environment_names_are_refused(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="ENVIRONMENT must be one of development, production"):
        Settings(_env_file=None, environment=value)


def test_missing_environment_is_development(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert Settings(_env_file=None).environment == "development"


@pytest.mark.parametrize("spelling", ["Production", "PRODUCTION"])
def test_capitalised_production_still_enforces_secret_and_cors_checks(monkeypatch, spelling):
    from app import config

    monkeypatch.setenv("ENVIRONMENT", spelling)
    monkeypatch.setenv("PILOT_MODE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://school.example")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    with pytest.raises(RuntimeError, match="JWT_SECRET") as exc:
        config.get_settings.__wrapped__()
    assert "x" * 48 not in str(exc.value)  # the secret is never echoed
    monkeypatch.setenv("JWT_SECRET", "R7q2Vx9LmT4pW8zK1sN6bY3hJ5dF0gC2aE7uQ9iO4wZ")
    monkeypatch.setenv("CORS_ORIGINS", "HTTPS://school.example/")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        config.get_settings.__wrapped__()


@pytest.mark.parametrize("spelling", ["Production", "PRODUCTION"])
def test_capitalised_production_still_blocks_seeding(monkeypatch, spelling):
    from scripts import seed

    monkeypatch.setattr(seed, "get_settings", lambda: Settings(_env_file=None, environment=spelling))
    monkeypatch.setattr(seed, "get_db", lambda: pytest.fail("seed must not touch the database"))
    monkeypatch.setattr("sys.argv", ["seed"])
    with pytest.raises(SystemExit, match="Refusing to seed"):
        seed.main()


def test_development_keeps_its_random_fallback_secret(monkeypatch):
    from app import config

    monkeypatch.setenv("ENVIRONMENT", "Development")
    monkeypatch.setenv("PILOT_MODE", "false")
    monkeypatch.setenv("JWT_SECRET", "")
    s = config.get_settings.__wrapped__()
    assert s.environment == "development" and len(s.jwt_secret) >= 48


# ============================== A7: enrollment events ================================================

def _events(db, email):
    return [(e["action"], e["by"]) for e in db.enrollment_events.find({"email": email}).sort([("at", 1), ("_id", 1)])]


def test_enroll_register_revoke_each_leave_an_event_in_order(api, pilot, db):
    teacher = register(api, "teacher")
    email = "pilot-student@example.com"
    assert api.post("/api/enrollments", json={"emails": [email]}, headers=teacher["headers"]).status_code == 201
    student = register(api, "student", email=email)
    assert api.delete(f"/api/enrollments/{email}", headers=teacher["headers"]).status_code == 200
    from bson import ObjectId

    t, s = ObjectId(teacher["user"]["id"]), ObjectId(student["user"]["id"])
    assert _events(db, email) == [("enrolled", t), ("registered", s), ("revoked", t)]
    assert all(e["at"] is not None for e in db.enrollment_events.find({"email": email}))


def test_registration_outside_the_pilot_writes_no_enrollment_event(api, db):
    register(api, "student", email="dev-student@example.com")
    assert db.enrollment_events.count_documents({}) == 0


def test_event_log_failure_is_not_hidden_and_never_logs_a_change_that_did_not_happen(api, pilot, db, monkeypatch):
    """Characterises the documented limit (two writes, no transaction): the state change stands, the request fails
    with a server error, and no event exists for it."""
    teacher = register(api, "teacher")
    email = "withdrawing@example.com"
    api.post("/api/enrollments", json={"emails": [email]}, headers=teacher["headers"])
    original = Collection.insert_one
    monkeypatch.setattr(Collection, "insert_one", lambda self, doc, *a, **k: (_ for _ in ()).throw(
        PyMongoError("simulated")) if self.name == "enrollment_events" else original(self, doc, *a, **k))
    r = api.delete(f"/api/enrollments/{email}", headers=teacher["headers"])
    assert r.status_code == 500
    assert db.enrollments.find_one({"email": email})["revoked_at"] is not None  # access IS revoked (fail safe)
    assert [a for a, _ in _events(db, email)] == ["enrolled"]  # but the revocation has no event
    r = api.delete("/api/enrollments/nobody@example.com", headers=teacher["headers"])
    assert r.status_code == 404 and _events(db, "nobody@example.com") == []


# ============================== A8: re-evaluation of a published result ==============================

def _stub_engine(q, answer):
    return {"suggested_score": float(q["max_marks"]) / 2, "max_marks": q["max_marks"], "concepts": [],
            "holistic_similarity": None, "relevance_ratio": None, "word_count": len(answer.split()), "flags": [],
            "confidence": "low", "needs_review": False,
            "feedback": {"summary": "stub", "strengths": [], "partial": [], "missing": [], "suggestions": [], "text": "stub"},
            "corrections": [], "metadata": {"rubric_fingerprint": "stub", "config_fingerprint": "stub",
                                            "engine_version": "stub", "backend": "embedding", "model_name": "stub"}}


def _published_submission(api, db, monkeypatch):
    monkeypatch.setattr(evaluation_service, "run_engine", _stub_engine)  # the real engine never runs
    teacher, student = register(api, "teacher"), register(api, "student")
    a = make_assessment(api, teacher)
    sub = submit(api, student, a)
    assert api.post(f"/api/evaluations/submission/{sub['id']}", headers=teacher["headers"]).status_code == 200
    assert api.post(f"/api/results/submission/{sub['id']}/publish", headers=teacher["headers"]).status_code == 200
    from bson import ObjectId

    return teacher, ObjectId(sub["id"])


def test_reevaluating_a_published_result_records_who_and_when(api, db, monkeypatch):
    teacher, sid = _published_submission(api, db, monkeypatch)
    before = db.submissions.find_one({"_id": sid})
    assert [e["action"] for e in before["publication_log"]] == ["published"]
    start = datetime.datetime.now(datetime.timezone.utc)
    r = api.post(f"/api/evaluations/submission/{sid}?allow_unpublish=true", headers=teacher["headers"])
    assert r.status_code == 200
    after = db.submissions.find_one({"_id": sid})
    from bson import ObjectId

    tid = ObjectId(teacher["user"]["id"])
    log = after["publication_log"]
    assert log[0] == before["publication_log"][0]  # the earlier record is not rewritten
    assert log[-1]["action"] == publication.UNPUBLISHED_FOR_REEVALUATION and log[-1]["by"] == tid
    assert start - datetime.timedelta(seconds=1) <= log[-1]["at"].replace(tzinfo=datetime.timezone.utc) \
        <= datetime.datetime.now(datetime.timezone.utc)
    assert after["status"] == "evaluated" and after["published_by"] is None and after["unpublished_by"] == tid
    assert all(not e["published"] and e.get("published_by") is None for e in db.evaluations.find({"submission_id": sid}))
    assert db.evaluation_history.count_documents({"submission_id": sid}) == 1  # previous version archived


def test_reevaluation_without_confirmation_leaves_publication_untouched(api, db, monkeypatch):
    teacher, sid = _published_submission(api, db, monkeypatch)
    r = api.post(f"/api/evaluations/submission/{sid}", headers=teacher["headers"])
    assert r.status_code == 409 and r.json()["code"] == "published"
    sub = db.submissions.find_one({"_id": sid})
    assert sub["status"] == "published" and [e["action"] for e in sub["publication_log"]] == ["published"]


def test_publication_record_failure_after_reevaluation_is_visible_not_silent(api, db, monkeypatch):
    """Characterises the documented limit: re-evaluation and its publication record are separate writes. If the record
    fails, the request fails (500) and the result is unpublished WITHOUT a log entry - it is never shown as published."""
    teacher, sid = _published_submission(api, db, monkeypatch)

    def broken(*_a, **_k):
        raise PyMongoError("simulated publication-log failure")

    monkeypatch.setattr(publication, "record", broken)
    r = api.post(f"/api/evaluations/submission/{sid}?allow_unpublish=true", headers=teacher["headers"])
    assert r.status_code == 500
    sub = db.submissions.find_one({"_id": sid})
    assert sub["status"] == "evaluated"  # no longer visible to the student as published
    assert [e["action"] for e in sub["publication_log"]] == ["published"]  # the unpublication has no record
    student_view = db.evaluations.count_documents({"submission_id": sid, "published": True})
    assert student_view == 0


# ============================== A9: strict CORS origins =============================================

@pytest.mark.parametrize("origin,canonical", [
    ("https://pilot.example", "https://pilot.example"),
    ("https://pilot.example:8443", "https://pilot.example:8443"),
    ("http://localhost:5173", "http://localhost:5173"),
    ("http://127.0.0.1:5173", "http://127.0.0.1:5173"),
    ("https://[::1]:8443", "https://[::1]:8443"),
    ("https://[2001:DB8::1]", "https://[2001:db8::1]"),
    ("HTTPS://pilot.example", "https://pilot.example"),
    ("https://Pilot.Example", "https://pilot.example"),
    ("https://pilot.example:443", "https://pilot.example"),
    ("http://pilot.example:80", "http://pilot.example"),
])
def test_canonical_origin(origin, canonical):
    assert canonical_origin(origin) == canonical


@pytest.mark.parametrize("origin", [
    "https://pilot.example/", "https://pilot.example/app", "https://pilot.example?x=1", "https://pilot.example#f",
    "https://pilot.example:99999", "https://pilot.example:0", "https://pilot.example:", "https://pilot.example:8a",
    "https://user@pilot.example", "https://*.pilot.example", "https://", "pilot.example", "ftp://pilot.example",
    "https:/pilot.example", "https://pilot..example", "https://-pilot.example", "https://pilot_example.org",
    "https://[::1", "https://[zz::1]", "https://1.2.3", "https://pilöt.example", "https://pilot example", "",
])
def test_malformed_origins_are_refused(origin):
    with pytest.raises(ValueError):
        canonical_origin(origin)
    assert cors_problems([origin], require_https=False)


@pytest.mark.parametrize("origin", ["https://pilot.example/", "HTTPS://pilot.example", "https://Pilot.example",
                                    "https://pilot.example:443"])
def test_non_canonical_origins_are_refused_not_rewritten(origin):
    problems = cors_problems([origin], require_https=True)
    assert problems and origin in problems[0]


def test_pilot_still_requires_https_origins():
    assert cors_problems(["https://pilot.example", "https://[::1]:8443"], require_https=True) == []
    assert any("https" in p for p in cors_problems(["http://localhost:5173"], require_https=True))
    assert cors_problems(["http://localhost:5173", "http://127.0.0.1:5173"], require_https=False) == []
