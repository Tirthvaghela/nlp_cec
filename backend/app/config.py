"""Application settings loaded from environment variables / backend/.env."""

from __future__ import annotations

import ipaddress
import logging
import re
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)
_PLACEHOLDER = "change-me"
ENVIRONMENTS = ("development", "production")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parent.parent / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AnswerWise AI"
    environment: str = "development"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "answerwise_dev"  # sprint 9: never the protected database "answerwise" (see PROTECTED_DATABASES)
    jwt_secret: str = Field(default="", description="HS256 signing secret - set a long random value")
    jwt_expire_minutes: int = 60 * 8
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # If set, registering as a teacher requires this code. Empty = open registration (development only).
    teacher_invite_code: str = ""
    similarity_backend: str = "auto"  # auto | embedding | tfidf
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    preload_model: bool = True
    # Classroom pilot safeguard (docs/PILOT_ACCEPTANCE_CRITERIA.md): when true, a result can only be published after
    # the teacher has reviewed every question (accepted or adjusted the AI suggestion). Off by default.
    require_review_before_publish: bool = False
    # Classroom pilot fail-safe (docs/PILOT_RUNBOOK.md): when true, the application refuses to start unless the
    # pilot configuration is confirmed (see pilot_config_problems). Off by default; changes no scoring.
    pilot_mode: bool = False
    # Security audit V1: reverse proxies whose X-Forwarded-For header may be trusted (comma-separated IP addresses or
    # networks). Empty (default) = no proxy: the launcher (scripts/run_server.py) turns proxy-header processing OFF and
    # the TCP peer address is the client address.
    trusted_proxies: str = ""
    # Security audit V12: who terminates TLS in the pilot. False (default) = this server itself, via the launcher's
    # --ssl-certfile/--ssl-keyfile. True = an IT-approved reverse proxy listed in TRUSTED_PROXIES does (an explicit
    # operator statement, never assumed).
    tls_terminated_by_proxy: bool = False
    log_level: str = "INFO"
    # Question authoring aid (POST /api/generation/*): reference answers and rubrics are drafted through Groq's API.
    # GROQ_API_KEY is read from the environment or backend/.env, stays on the server and is never logged or returned.
    # Without it the drafting endpoints answer 503 and teachers write the reference answer themselves (rubrics are then
    # derived locally). GENERATION_MODEL is any Groq chat-model id (https://console.groq.com/docs/models). Drafts are
    # suggestions only and are never used for scoring until the teacher saves the question.
    groq_api_key: SecretStr = SecretStr("")
    generation_model: str = "llama-3.3-70b-versatile"

    @field_validator("environment", mode="before")
    @classmethod
    def _known_environment(cls, v):
        """Sprint 5 (A5): every check compares with the exact string "production", so a spelling such as "Production"
        used to run silently as development. Case and surrounding spaces are normalised; unknown names are refused."""
        name = str(v).strip().lower()
        if name not in ENVIRONMENTS:
            raise ValueError(f"ENVIRONMENT must be one of {', '.join(ENVIRONMENTS)}")
        return name

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]


DEVELOPMENT_DB = "answerwise"  # the main development/demo database; never used for a pilot
# Sprint 9 (database incident of 2026-10-17, docs/SPRINT9_INCIDENT_CONTAINMENT.md): databases no application process
# may use at all, in any mode. "answerwise" is the main database under incident review; local development uses
# "answerwise_dev" (the default) or another name of the developer's choosing.
PROTECTED_DATABASES = ("answerwise",)
LOCAL_DEVELOPMENT_DB = "answerwise_dev"


def protected_database_problem(name: str) -> str | None:
    """Why the SELECTED database name (Settings.mongodb_db after environment and .env resolution) must not be used.
    Compared case-insensitively and without surrounding spaces: MongoDB refuses names that differ only in case from an
    existing database, so "Answerwise" would not be a different database either."""
    selected = (name or "").strip().lower()
    if not selected:
        return "MONGODB_DB is empty"
    if selected in PROTECTED_DATABASES:
        return (f"MONGODB_DB selects the protected database '{selected}', which is under incident review "
                f"(docs/SPRINT9_INCIDENT_CONTAINMENT.md). Set MONGODB_DB={LOCAL_DEVELOPMENT_DB} in backend/.env for "
                "local development")
    return None
MIN_INVITE_CODE_LENGTH = 16
MIN_INVITE_CODE_DISTINCT = 8
_TRIVIAL_INVITE_WORDS = ("invite", "teacher", "password", "changeme", "change-me", "answerwise", "secret", "pilot",
                         "code", "admin", "123456", "qwerty")


_KNOWN_PLACEHOLDER_SECRETS = ("change-me", "changeme", "password", "example", "test-secret", "your-secret", "<")


def secret_problems(secret: str) -> list[str]:
    """Security audit F6: why a JWT signing secret is unfit for production/pilot (never echoes the value).
    Heuristic quality gate, not a proof of randomness: length, placeholder words, distinct characters, repetition and
    a Shannon-entropy estimate (>= 128 bits). A value from secrets.token_urlsafe(48) passes comfortably."""
    import math
    from collections import Counter

    if not secret:
        return ["JWT_SECRET is missing"]
    low = secret.lower()
    problems = []
    if any(low.startswith(p) or p in low for p in _KNOWN_PLACEHOLDER_SECRETS):
        problems.append("JWT_SECRET looks like a placeholder or contains a common word")
    if len(secret) < 32:
        problems.append("JWT_SECRET must be at least 32 characters")
    if len(set(secret)) < 16:
        problems.append("JWT_SECRET has too few distinct characters (use a random value)")
    if any(secret[i:i + 4] * 2 in secret for i in range(len(secret) - 3)):
        problems.append("JWT_SECRET contains a repeated pattern")
    counts = Counter(secret)
    bits = -sum(c / len(secret) * math.log2(c / len(secret)) for c in counts.values()) * len(secret)
    if bits < 128:
        problems.append("JWT_SECRET is not random enough (estimated entropy below 128 bits); "
                        "use python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    return problems


_DNS_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
_DEFAULT_PORTS = {"http": 80, "https": 443}


def canonical_origin(origin: str) -> str:
    """The exact form a browser sends in its Origin header (lowercase scheme and host, compressed IPv6, no default
    port, no trailing slash). Raises ValueError if ``origin`` is not a plain http(s) origin."""
    from urllib.parse import urlsplit

    if not origin or any(c.isspace() for c in origin) or "*" in origin or not origin.isascii():
        raise ValueError("contains whitespace, a wildcard or non-ASCII characters (use the punycode host name)")
    u = urlsplit(origin)
    scheme = u.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not origin[len(u.scheme):].startswith("://"):
        raise ValueError("must start with http:// or https://")
    if u.path or u.query or u.fragment or "?" in origin or "#" in origin:
        raise ValueError("must not have a path (not even a trailing slash), query or fragment")
    if "@" in u.netloc:
        raise ValueError("must not contain credentials")
    host_port = u.netloc
    if host_port.endswith(":"):
        raise ValueError("has an empty port")
    try:
        port = u.port
    except ValueError:
        raise ValueError("has a malformed port (must be 1-65535)") from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("has a malformed port (must be 1-65535)")
    host = u.hostname or ""
    if host_port.startswith("["):
        try:
            ip = ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError("has a malformed IPv6 address") from None
        canon_host = f"[{ip.compressed}]"
    else:
        try:
            canon_host = str(ipaddress.IPv4Address(host))
        except ValueError:
            labels = host.split(".")
            if not host or len(host) > 253 or not all(_DNS_LABEL.fullmatch(lbl) for lbl in labels) or labels[-1].isdigit():
                raise ValueError("has an invalid host name") from None
            canon_host = host
    port_part = "" if port is None or port == _DEFAULT_PORTS[scheme] else f":{port}"
    return f"{scheme}://{canon_host}{port_part}"


def cors_problems(origins: list[str], require_https: bool) -> list[str]:
    """Security audit F6: CORS origins must be an explicit allowlist of well-formed origins (scheme://host[:port],
    nothing else). The VALUES are the operator's/IT's approved origins - never invented here.
    Sprint 5 (A9): parsed structurally. The browser's Origin header is compared with each entry as an exact string, so
    an entry is also refused when it is not already in that canonical form (e.g. a trailing slash, an uppercase
    scheme or host, or the default port): it would never match. It is reported with its canonical spelling, never
    rewritten silently."""
    if not origins:
        return ["CORS_ORIGINS must list the approved frontend origin(s)"]
    problems = []
    for o in origins:
        if o in ("*", "null"):
            problems.append(f"CORS_ORIGINS must not contain {o!r}")
            continue
        try:
            canon = canonical_origin(o)
        except ValueError as exc:
            problems.append(f"CORS_ORIGINS entry {o!r} is not a plain origin (scheme://host[:port]): {exc}")
            continue
        if canon != o:
            problems.append(f"CORS_ORIGINS entry {o!r} is not in the form browsers send; write it as {canon!r}")
        elif require_https and not canon.startswith("https://"):
            problems.append(f"CORS_ORIGINS entry {o!r} must use https in the pilot")
    return problems


def trusted_proxy_problems(proxies: list[str], pilot: bool) -> list[str]:
    """Each trusted proxy must be an explicit IP address or network. In the pilot, loopback/wildcard entries are
    refused: any other process on the host could then forge client addresses (V1)."""
    import ipaddress

    problems = []
    for p in proxies:
        if p == "*":
            problems.append("TRUSTED_PROXIES must not contain * (it would trust X-Forwarded-For from anyone)")
            continue
        try:
            net = ipaddress.ip_network(p, strict=False)
        except ValueError:
            problems.append(f"TRUSTED_PROXIES entry {p!r} is not an IP address or network")
            continue
        if pilot and (net.is_loopback or net.is_unspecified or net.prefixlen == 0):
            problems.append(f"TRUSTED_PROXIES entry {p!r} is loopback/unspecified: not allowed in the pilot (any local "
                            "process could forge client addresses); the supported pilot topology is a direct server")
    return problems


def invite_code_problem(code: str) -> str | None:
    """Why a teacher invite code is too weak for the pilot (None = acceptable). Never echoes the code."""
    c = code.strip()
    if not c:
        return "TEACHER_INVITE_CODE must be set (otherwise anyone, including students, can register as a teacher)"
    if c != code or any(ch.isspace() for ch in c):
        return "TEACHER_INVITE_CODE must not contain whitespace"
    if c.startswith("<") or c.startswith(_PLACEHOLDER):
        return "TEACHER_INVITE_CODE is still a template placeholder"
    if len(c) < MIN_INVITE_CODE_LENGTH or len(set(c)) < MIN_INVITE_CODE_DISTINCT:
        return (f"TEACHER_INVITE_CODE is too weak: use at least {MIN_INVITE_CODE_LENGTH} characters with at least "
                f"{MIN_INVITE_CODE_DISTINCT} different ones, e.g. python -c \"import secrets; print(secrets.token_urlsafe(18))\"")
    if any(w in c.lower() for w in _TRIVIAL_INVITE_WORDS):
        return "TEACHER_INVITE_CODE contains a common word; use a random value"
    return None


def pilot_config_problems(s: Settings) -> list[str]:
    """Why ``s`` is not a safe classroom-pilot configuration (empty list = confirmed)."""
    problems = []
    if not s.require_review_before_publish:
        problems.append("REQUIRE_REVIEW_BEFORE_PUBLISH must be true (every AI suggestion is reviewed before publication)")
    if s.environment != "production":
        problems.append("ENVIRONMENT must be production (enforces JWT_SECRET, blocks seeding and database resets)")
    problems += secret_problems(s.jwt_secret)
    if (invite := invite_code_problem(s.teacher_invite_code)):
        problems.append(invite)
    if not s.preload_model:
        problems.append("PRELOAD_MODEL must be true (the model loads at start-up, so the preflight can confirm it before "
                        "any evaluation; scoring is unchanged)")
    if s.mongodb_db.strip().lower() in (DEVELOPMENT_DB, LOCAL_DEVELOPMENT_DB, *PROTECTED_DATABASES):
        problems.append(f"MONGODB_DB must be a dedicated pilot database, not the development database "
                        f"'{s.mongodb_db.strip().lower()}'")
    if s.similarity_backend.lower() == "tfidf":
        problems.append("SIMILARITY_BACKEND must not be tfidf (the frozen system is the embedding engine)")
    problems += cors_problems(s.cors_origin_list, require_https=True)
    problems += trusted_proxy_problems(s.trusted_proxy_list, pilot=True)
    if s.tls_terminated_by_proxy and not s.trusted_proxy_list:
        problems.append("TLS_TERMINATED_BY_PROXY=true needs the proxy's address in TRUSTED_PROXIES")
    return problems


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.pilot_mode and (problems := pilot_config_problems(s)):
        # Fail closed: a pilot must not run on an unconfirmed configuration.
        raise RuntimeError("PILOT_MODE is on but the configuration is not safe for the pilot:\n- " + "\n- ".join(problems))
    if s.environment == "production" and (problems := secret_problems(s.jwt_secret) + cors_problems(s.cors_origin_list, False)):
        # F6: production refuses a missing, placeholder or weak secret and a malformed/wildcard CORS list.
        raise RuntimeError("Unsafe production configuration:\n- " + "\n- ".join(problems))
    if (problem := protected_database_problem(s.mongodb_db)):
        # Sprint 9: fail closed in EVERY mode, before anything can connect. get_settings() runs when app.main is
        # imported (so uvicorn and the launcher stop here) and inside get_db(), the seed and the pilot scripts.
        raise RuntimeError("Refusing to start: " + problem)
    if not s.jwt_secret or s.jwt_secret.startswith(_PLACEHOLDER):
        # Development convenience: a random per-process secret (tokens reset on restart).
        s.jwt_secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET not set - using a random development secret; sessions end when the server restarts.")
    return s
