"""Database-side deployment marker (security audits F3/F4, V8).

A pilot database carries one document ``deployment_meta/_id="deployment"`` with ``kind="pilot"``, a random 32-hex
``instance_id`` and ``created_at``. It is written once by ``python -m scripts.pilot_init_db`` on an EMPTY database.
Because the marker lives in the database itself, tools do not have to trust the environment of the shell they run in:

* the seed script refuses any database whose marker says ``pilot`` - or whose marker is malformed;
* in PILOT_MODE the server refuses to start unless its database carries a VALID pilot marker;
* ``/api/health`` reports a non-secret fingerprint and the preflight compares it with the fingerprint of the database
  it was configured with, so both are proven to use the same database on the same MongoDB server.

The fingerprint binds (MongoDB server address, database name, marker instance id): a copy of the database restored
under the same name on ANOTHER server has a different fingerprint. Consequence: the server and the preflight must use
the same MONGODB_URI host spelling ("localhost" and "127.0.0.1" are different identities - the check then fails closed).
"""

from __future__ import annotations

import hashlib
import re
import uuid

from pymongo.database import Database

from app.db import now

MARKER_COLLECTION = "deployment_meta"
MARKER_ID = "deployment"
PILOT, DEVELOPMENT = "pilot", "development"
KINDS = (PILOT, DEVELOPMENT)
_INSTANCE_ID = re.compile(r"[0-9a-f]{32}")


def read_marker(db: Database) -> dict | None:
    return db[MARKER_COLLECTION].find_one({"_id": MARKER_ID})


def marker_problems(marker, expected_kind: str | None = None) -> list[str]:
    """Why ``marker`` is not a valid deployment marker (empty list = valid)."""
    if marker is None:
        return ["no deployment marker"]
    if not isinstance(marker, dict):
        return ["deployment marker is not a document"]
    problems = []
    kind = marker.get("kind")
    if kind not in KINDS:
        problems.append(f"unknown marker kind {kind!r}")
    elif expected_kind and kind != expected_kind:
        problems.append(f"marker kind is {kind!r}, expected {expected_kind!r}")
    if not isinstance(marker.get("instance_id"), str) or not _INSTANCE_ID.fullmatch(marker["instance_id"]):
        problems.append("marker instance_id is missing or malformed")
    if marker.get("created_at") is None:
        problems.append("marker created_at is missing")
    return problems


def server_identity(db: Database) -> str | None:
    """host:port of the MongoDB server this client is connected to (hashed, never reported in clear)."""
    try:
        address = db.client.address
    except Exception:  # noqa: BLE001 - unknown server: no identity, callers fail closed
        return None
    if not address:
        return None
    return f"{str(address[0]).lower()}:{address[1]}"


def fingerprint(db: Database, marker: dict | None) -> str | None:
    """Stable, non-secret identifier of a validly marked database on a specific MongoDB server (no credentials,
    host or name in clear). None when the marker is invalid or the server identity is unknown."""
    if marker_problems(marker):
        return None
    server = server_identity(db)
    if not server:
        return None
    return hashlib.sha256(f"{server}\0{db.name}\0{marker['instance_id']}".encode()).hexdigest()[:16]


def write_marker(db: Database, kind: str) -> dict:
    doc = {"_id": MARKER_ID, "kind": kind, "instance_id": uuid.uuid4().hex, "created_at": now()}
    db[MARKER_COLLECTION].insert_one(doc)
    return doc
