"""Initialise a NEW, EMPTY database for the classroom pilot (docs/PILOT_RUNBOOK.md, step 2).

    python -m scripts.pilot_init_db

Writes the pilot deployment marker (app/deployment.py) so that:
* the server in PILOT_MODE accepts this database (it refuses an unmarked one);
* the seed script refuses this database even when run from a development shell;
* the preflight can prove that it and the running server use this same database.

Refuses unless PILOT_MODE is on with a safe configuration (otherwise app.config raises) and the configured
database is completely empty. It never drops, modifies or reads any user data. It prints the database
fingerprint (non-secret) for the deployment record.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import deployment  # noqa: E402
from app.config import DEVELOPMENT_DB, LOCAL_DEVELOPMENT_DB, PROTECTED_DATABASES, get_settings  # noqa: E402
from app.db import ensure_indexes, get_db  # noqa: E402


def init(db, settings) -> dict:
    if not settings.pilot_mode:
        sys.exit("Refusing: PILOT_MODE is not on. Configure backend/.env from .env.pilot.example first.")
    if db.name.lower() in (DEVELOPMENT_DB, LOCAL_DEVELOPMENT_DB, *PROTECTED_DATABASES):
        sys.exit("Refusing: the development database can never become a pilot database.")
    try:
        collections = db.list_collection_names()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Refusing: the database could not be inspected ({type(exc).__name__}).")
    if collections:
        marker = deployment.read_marker(db)
        if marker is not None and not deployment.marker_problems(marker, deployment.PILOT):
            sys.exit(f"Already initialised as a pilot database (fingerprint {deployment.fingerprint(db, marker)}).")
        sys.exit(f"Refusing: database '{db.name}' is not empty ({len(collections)} collection(s)). Use a new database name.")
    marker = deployment.write_marker(db, deployment.PILOT)
    ensure_indexes(db)
    return marker


def main() -> None:
    settings = get_settings()  # raises if PILOT_MODE is on with an unsafe configuration
    db = get_db()
    marker = init(db, settings)
    print(f"Pilot database initialised. Fingerprint {deployment.fingerprint(db, marker)} "
          "(record it with the deployment notes; /api/health and the preflight report the same value).")


if __name__ == "__main__":
    main()
