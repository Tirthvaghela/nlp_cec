"""Read-only pre-flight check for the classroom pilot deployment (docs/PILOT_RUNBOOK.md).

    python -m scripts.pilot_preflight --manifest-sha256 <hash kept by the supervisor>                # offline
    python -m scripts.pilot_preflight --manifest-sha256 <hash> --url https://<server>:8000          # bind to the server
    (add --cafile <IT CA certificate> when the server certificate comes from an internal CA)

--url must be an absolute https:// URL in PILOT_MODE (sprint 5, A2): the preflight then checks the server's certificate
and host name itself, instead of trusting only the transport the server reports about itself.

--manifest-sha256 is MANDATORY (security audit V2): without the supervisor's independently kept hash of
scripts/pilot_frozen_engine.json the preflight FAILS - a manifest stored beside the code proves nothing on its own.

Exit code 0 only if every check PASSES. Anything that cannot be confirmed (database or server unreachable, model
still loading, missing marker, missing or malformed manifest, server that does not report its identity) is a
failure: the pilot does not start on an unconfirmed configuration. Nothing is written; no names, e-mail addresses,
credentials, invite codes or secrets are printed.

What a PASS does NOT mean: the check is a snapshot. It cannot guarantee that the fallback scorer will not be used
after the check (for example after a restart that fails to load the model) - run it again after every restart and
before every session. The frozen-engine manifest is an unsigned file stored next to the code: it detects accidental
or partial changes, not a deliberate edit of code and manifest together, which is why --manifest-sha256 (the hash
the supervisor keeps independently) is required.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FROZEN = Path(__file__).resolve().parent / "pilot_frozen_engine.json"
DEMO_DOMAIN = "@answerwise.dev"
MANIFEST_KEYS = ("engine_version", "model", "backend", "config_fingerprint", "nlp_source_sha256", "files",
                 "scoring_relevant_globs", "model_artifacts", "runtime")
RUNTIME_PACKAGES = ("sentence-transformers", "transformers", "tokenizers", "huggingface-hub", "torch", "scikit-learn",
                    "numpy", "scipy", "nltk", "safetensors")


def hf_cache_dir() -> Path:
    """Sprint 5 (A4): resolved exactly as the libraries do, including XDG_CACHE_HOME and the legacy variable."""
    from app import model_cache

    return model_cache.hub_cache_dir()


def model_snapshot(model: str) -> tuple[str | None, Path | None]:
    """(revision, snapshot directory) of the locally cached model that `main` resolves to - read from disk only;
    the model is NOT loaded."""
    from app import model_cache

    return model_cache.snapshot(model)


def model_file_hashes(snapshot: Path) -> dict[str, str]:
    return {p.relative_to(snapshot).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(snapshot.rglob("*")) if p.is_file()}


def runtime_versions() -> dict[str, str]:
    """Python and scoring-library versions from installed package metadata (nothing is imported)."""
    import importlib.metadata as md
    import platform

    out = {"python": platform.python_version()}
    for pkg in RUNTIME_PACKAGES:
        try:
            out[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            out[pkg] = "missing"
    return out
FALLBACK_NOTE = ("a PASS is a snapshot: it does not guarantee that fallback (TF-IDF) scoring cannot occur after this "
                 "check - run the preflight after every server restart and before every session; fallback-scored "
                 "results need a teacher-entered mark with a reason (PILOT_RUNBOOK.md section 5)")


def _settings():
    from app.config import Settings

    return Settings()  # not get_settings(): report every problem instead of stopping at the PILOT_MODE guard


def check_config(results: list) -> None:
    from app.config import pilot_config_problems

    s = _settings()
    results.append(("PILOT_MODE enabled (app refuses to start on an unsafe configuration)",
                    "PASS" if s.pilot_mode else "FAIL", "" if s.pilot_mode else "set PILOT_MODE=true"))
    problems = pilot_config_problems(s)
    results.append(("Pilot configuration (review gate, production, secret, strong invite code, dedicated DB, preload, "
                    "backend, CORS)", "PASS" if not problems else "FAIL", "; ".join(problems)))


def settings_override_problems(settings) -> list[str]:
    """Why a question's stored ``settings`` is not "no override" (empty list = none). Names keys, never values.
    A key whose value is None is ignored by the engine (evaluation_service.question_spec drops it), so it is not an
    override; anything else is - a scoring-affecting EvaluationConfig field, an unknown key, or a non-object value."""
    from app.nlp.config import EvaluationConfig

    if settings is None:
        return []
    if not isinstance(settings, dict):
        return [f"settings is not an object ({type(settings).__name__})"]
    scoring = set(EvaluationConfig.__dataclass_fields__)
    out = []
    for key in sorted(str(k)[:60] for k, v in settings.items() if v is not None):
        out.append(f"scoring override '{key}'" if key in scoring else f"unknown settings key '{key}'")
    return out


def check_database(results: list) -> str | None:
    """Returns the local database fingerprint (None if it cannot be established)."""
    from pymongo import MongoClient

    from app import deployment

    from app.config import protected_database_problem

    s = _settings()
    if (problem := protected_database_problem(s.mongodb_db)):
        # Sprint 9: the preflight builds Settings() itself (not get_settings()), so it repeats the guard: it never
        # connects to - not even reads - the protected database.
        results.append(("Pilot database reachable", "FAIL", problem + " - not inspected"))
        return None
    try:
        client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[s.mongodb_db]
        marker = deployment.read_marker(db)
    except Exception as exc:  # noqa: BLE001
        results.append(("Pilot database reachable", "UNVERIFIED", type(exc).__name__))
        return None
    results.append(("Pilot database reachable", "PASS", ""))
    problems = deployment.marker_problems(marker, deployment.PILOT)
    fp = deployment.fingerprint(db, marker) if not problems else None
    results.append(("Database carries the pilot marker", "PASS" if fp else "FAIL",
                    f"fingerprint {fp}" if fp else ("; ".join(problems) or "server identity unknown")
                    + " - run python -m scripts.pilot_init_db on a new, empty database"))
    demo_users = db.users.count_documents({"email": {"$regex": f"{DEMO_DOMAIN.replace('.', '[.]')}$", "$options": "i"}})
    seeded = sum(db[c].count_documents({"source": "seed"}) for c in ("assessments", "submissions"))
    results.append(("No demo accounts or seeded demo data in the pilot database",
                    "PASS" if not (demo_users or seeded) else "FAIL",
                    f"demo accounts: {demo_users}, seeded documents: {seeded}"))
    # Sprint 5 (A3): EVERY settings key, not only the two thresholds the API accepts - the engine applies any
    # EvaluationConfig field found there (EvaluationConfig.with_overrides), and a direct database write is not limited
    # by the API. No override is permitted until faculty decision D5 says otherwise.
    flagged = {}
    for q in db.questions.find({}, {"settings": 1}):
        for problem in settings_override_problems(q.get("settings")):
            flagged[problem] = flagged.get(problem, 0) + 1
    results.append(("No per-question scoring overrides of any kind (they are outside the frozen identity)",
                    "PASS" if not flagged else "FAIL",
                    "" if not flagged else "; ".join(f"{p} ({n} question(s))" for p, n in sorted(flagged.items()))
                    + " - remove them, or obtain faculty authorisation and a recorded override policy first (D5)"))
    roles = {r: db.users.count_documents({"role": r}) for r in ("teacher", "student")}
    results.append(("Pilot database contents (counts only)", "INFO", f"users by role {roles}, "
                    f"active enrollments {db.enrollments.count_documents({'revoked_at': None})}"))
    return fp


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()  # exact bytes


def check_engine(results: list, manifest_sha256: str | None = None) -> None:
    from evaluation.real_study import frozen_engine

    name = "Installed engine equals the frozen pilot engine (manifest present, complete, every scoring file matches)"
    try:
        raw = FROZEN.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        results.append((name, "FAIL", f"manifest missing: {FROZEN.name}"))
        return
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        results.append((name, "FAIL", f"manifest unreadable or malformed ({type(exc).__name__})"))
        return
    if not isinstance(manifest, dict) or (missing := [k for k in MANIFEST_KEYS if k not in manifest]):
        results.append((name, "FAIL", f"manifest incomplete: missing {missing if isinstance(manifest, dict) else 'object'}"))
        return
    problems = []
    identity = {k: manifest[k] for k in ("engine_version", "model", "backend", "config_fingerprint", "nlp_source_sha256")}
    actual = frozen_engine()
    problems += [f"{k} differs" for k in identity if actual.get(k) != identity[k]]
    files: dict = manifest["files"]
    covered = {p.relative_to(BACKEND).as_posix() for g in manifest["scoring_relevant_globs"]
               for p in map(Path, glob.glob(str(BACKEND / g)))}
    if not covered:
        problems.append("scoring_relevant_globs match no files")
    problems += [f"{f} not listed in manifest (incomplete)" for f in sorted(covered - set(files))]
    for rel, expected in sorted(files.items()):
        path = BACKEND / rel
        if not path.exists():
            problems.append(f"{rel} missing")
        elif _sha(path) != expected:
            problems.append(f"{rel} changed")
    results.append((name, "PASS" if not problems else "FAIL", "; ".join(problems) or f"{len(files)} files"))
    check_manifest_hash(results, raw, manifest_sha256)
    check_model_and_runtime(results, manifest)


def check_model_and_runtime(results: list, manifest: dict) -> None:
    """V7: the exact model weights/tokenizer files and the runtime that can change scores, against the manifest."""
    from app import model_cache

    configured = _settings().embedding_model
    results.append(("Configured model (EMBEDDING_MODEL) is the frozen model", "PASS" if configured == manifest["model"]
                    else "FAIL", "" if configured == manifest["model"] else "the server would load a different model "
                    "than the one hashed here"))
    problems = model_cache.cache_problems(manifest["model"], workdirs=(Path.cwd(), BACKEND))
    results.append(("Model location is unambiguous (only the hashed cache can be loaded)",
                    "PASS" if not problems else "FAIL", "; ".join(problems)))
    m = manifest.get("model_artifacts") or {}
    rev, snap = model_snapshot(manifest["model"])
    name = "Model weights, tokenizer and config on disk equal the frozen snapshot (exact bytes)"
    if not m.get("revision") or not isinstance(m.get("files"), dict) or not m["files"]:
        results.append((name, "FAIL", "manifest has no model_artifacts revision/files"))
    elif not snap:
        results.append((name, "FAIL", f"model {manifest['model']} not found in the local cache {hf_cache_dir()}"))
    elif rev != m["revision"]:
        results.append((name, "FAIL", f"cached revision {rev[:12]} != frozen {str(m['revision'])[:12]}"))
    else:
        actual = model_file_hashes(snap)
        diff = sorted(k for k in set(actual) | set(m["files"]) if actual.get(k) != m["files"].get(k))
        results.append((name, "PASS" if not diff else "FAIL", f"revision {rev[:12]}, {len(actual)} files" if not diff
                        else f"differs: {diff[:5]}"))
    want = manifest.get("runtime") or {}
    have = runtime_versions()
    diff = sorted(k for k in set(want) | set(have) if want.get(k) != have.get(k))
    results.append(("Python and scoring-library versions equal the frozen runtime", "PASS" if want and not diff else "FAIL",
                    "" if want and not diff else f"differs: {[(k, want.get(k), have.get(k)) for k in diff][:5]}"))


def check_manifest_hash(results: list, raw: bytes, supplied: str | None) -> None:
    """V2: the supervisor's independently kept SHA-256 of the manifest's EXACT bytes is required."""
    name = "Manifest equals the hash kept independently by the supervisor"
    if not supplied:
        results.append((name, "FAIL", "missing: pass --manifest-sha256 with the supervisor's value (required)"))
        return
    value = supplied.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        results.append((name, "FAIL", "malformed: expected 64 hexadecimal characters"))
        return
    ok = hashlib.sha256(raw).hexdigest() == value
    results.append((name, "PASS" if ok else "FAIL", "" if ok else "the manifest's bytes differ from the supervisor's "
                    "record (wrong, stale or tampered)"))


def target_url_problems(url: str, require_https: bool) -> list[str]:
    """Sprint 5 (A2): the --url must be an absolute http(s) URL with a host and nothing else - in the pilot, https."""
    from urllib.parse import urlsplit

    if not url or url != url.strip() or any(c.isspace() for c in url):
        return ["--url is empty or contains whitespace"]
    try:
        u = urlsplit(url)
        u.port  # noqa: B018 - raises ValueError for a malformed or out-of-range port
    except ValueError:
        return ["--url is malformed (invalid host or port)"]
    if u.scheme not in ("http", "https"):
        return ["--url must be an absolute URL starting with https:// (e.g. https://<server>:8000)"]
    problems = []
    if not u.hostname:
        problems.append("--url has no host")
    if u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
        problems.append("--url must be the server's base URL only (no credentials, path, query or fragment)")
    if require_https and u.scheme != "https":
        problems.append("--url must use https in the pilot: the preflight verifies the server's certificate itself "
                        "instead of relying on the transport the server reports")
    return problems


def tls_context(cafile: str | None = None):
    """Certificate and host-name verification are always ON (ssl.create_default_context). --cafile only ADDS the
    IT-supplied CA certificate for an internal CA; nothing here can switch verification off."""
    import ssl

    return ssl.create_default_context(cafile=cafile)


def check_server(results: list, url: str, local_fp: str | None, cafile: str | None = None) -> None:
    s = _settings()
    problems = target_url_problems(url, require_https=s.pilot_mode)
    if problems:
        results.append(("Server URL is an absolute https URL", "FAIL", "; ".join(problems)))
        return
    target = url.rstrip("/") + "/api/health"
    try:
        context = tls_context(cafile) if url.startswith("https://") else None
        with urllib.request.urlopen(target, timeout=10, context=context) as r:
            final = r.geturl() if hasattr(r, "geturl") else target
            h = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        reason = getattr(exc, "reason", exc)
        detail = type(reason).__name__
        if "CERTIFICATE_VERIFY_FAILED" in str(reason) or type(reason).__name__ == "SSLCertVerificationError":
            detail += " - the server's certificate could not be verified (wrong host name, expired, self-signed or an " \
                      "unknown CA; pass IT's CA certificate with --cafile, never disable verification)"
        results.append(("Running server /api/health", "UNVERIFIED", detail))
        return
    if final != target:
        results.append(("Server answered at the requested URL (no redirect)", "FAIL", "the health check was redirected"))
        return
    if url.startswith("https://"):
        results.append(("Preflight reached the server over HTTPS and verified its certificate and host name itself",
                        "PASS", ""))
    expected = json.loads(FROZEN.read_text(encoding="utf-8")) if FROZEN.exists() else {}
    d = h.get("deployment")
    if not isinstance(d, dict):
        results.append(("Server reports its deployment identity", "FAIL", "no deployment summary (older or other server)"))
        return
    server_fp = d.get("database_fingerprint")
    if not server_fp or not local_fp:
        results.append(("Server and preflight use the same pilot database", "FAIL",
                        "fingerprint unavailable on " + ("server" if not server_fp else "preflight side")))
    else:
        results.append(("Server and preflight use the same pilot database",
                        "PASS" if server_fp == local_fp else "FAIL",
                        "" if server_fp == local_fp else f"server {server_fp} != preflight {local_fp}"))
    from app import model_cache

    mc = d.get("model_cache") if isinstance(d.get("model_cache"), dict) else {}
    checks = [
        ("Server: review before publish enforced", d.get("require_review_before_publish") is True),
        ("Server: PILOT_MODE on", d.get("pilot_mode") is True),
        ("Server: ENVIRONMENT=production", d.get("environment") == "production"),
        ("Server: model preloading on", d.get("preload_model") is True),
        ("Server: strong teacher invite code configured", d.get("teacher_invite_code_strong") is True),
        ("Server: database carries a valid pilot marker", d.get("database_marker") == "pilot" and d.get("database_marker_valid") is True),
        ("Server: started by the pilot launcher (client address not taken from untrusted proxy headers)",
         d.get("client_address_mode") in ("direct", "trusted_proxies")),
        ("Server: TLS in place (served by the launcher with a certificate, or by the declared TLS-terminating proxy)",
         d.get("transport") in ("tls-direct", "tls-proxy")),
        ("Server configuration matches the preflight's configuration",
         d.get("environment") == s.environment and d.get("pilot_mode") == s.pilot_mode
         and d.get("require_review_before_publish") == s.require_review_before_publish),
        ("Server: engine version is the frozen one", h.get("engine_version") == expected.get("engine_version")),
        # Sprint 5 (A4): the server must resolve the cache this preflight hashed (same machine, same environment), at
        # the frozen revision, with no variable or local directory that could redirect the model. Self-reported.
        ("Server: resolves the model cache hashed here, at the frozen revision, with no conflicting cache settings",
         mc.get("cache_id") == model_cache.cache_id() and mc.get("conflicts") is False
         and mc.get("revision") is not None and mc.get("revision") == (expected.get("model_artifacts") or {}).get("revision")),
    ]
    for name, ok in checks:
        results.append((name, "PASS" if ok else "FAIL", ""))
    backend = h.get("similarity_backend")
    if backend == "loading":
        results.append(("Server: embedding model loaded (not the TF-IDF fallback)", "UNVERIFIED",
                        "model still loading - run the check again in a minute"))
    else:
        ok = backend == "embedding" and h.get("model") == expected.get("model") and not h.get("fallback_reason")
        results.append(("Server: embedding model loaded (not the TF-IDF fallback)", "PASS" if ok else "FAIL",
                        f"backend={backend}, fallback_reason={h.get('fallback_reason')}"))


def run(url: str | None = None, manifest_sha256: str | None = None, cafile: str | None = None) -> tuple[bool, list]:
    results: list = []
    check_config(results)
    fp = check_database(results)
    check_engine(results, manifest_sha256)
    if url is not None:
        check_server(results, url, fp, cafile)
    results.append(("Limitation", "NOTE", FALLBACK_NOTE))
    ok = all(status in ("PASS", "INFO", "NOTE") for _, status, _ in results)  # NOT VERIFIED / UNVERIFIED = FAIL
    return ok, results


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="base URL of the running pilot server; in PILOT_MODE it must be https://<server>[:port]")
    ap.add_argument("--manifest-sha256", help="SHA-256 of scripts/pilot_frozen_engine.json kept by the supervisor")
    ap.add_argument("--cafile", help="IT's CA certificate (PEM) when the server certificate is issued by an internal CA; "
                                     "verification can never be switched off")
    args = ap.parse_args(argv)
    ok, results = run(args.url, args.manifest_sha256, args.cafile)
    for name, status, detail in results:
        print(f"[{status:12}] {name}" + (f" - {detail}" if detail else ""))
    if args.url is None:
        print("[NOTE        ] the running server was not checked; repeat with --url once it is started")
    print("PREFLIGHT PASSED" if ok else "PREFLIGHT FAILED - do not start the pilot")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
