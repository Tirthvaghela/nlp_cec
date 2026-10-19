"""Shared fixtures.

* API tests use a throw-away MongoDB database (``answerwise_test_<pid>``) on the
  configured server, or mongomock when no server is reachable.
* The real sentence-embedding model is loaded once per session, so NLP and API
  tests exercise the actual engine (no mocks of the scoring logic).
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("JWT_SECRET", "test-secret-" + uuid.uuid4().hex)
os.environ["MONGODB_DB"] = f"answerwise_test_{os.getpid()}"
os.environ["PRELOAD_MODEL"] = "false"
os.environ["TEACHER_INVITE_CODE"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import ensure_indexes, set_db  # noqa: E402
from app.nlp.similarity import get_backend  # noqa: E402


def _make_db():
    s = get_settings()
    try:
        client = MongoClient(s.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        return client, client[s.mongodb_db]
    except PyMongoError:
        import mongomock

        client = mongomock.MongoClient(tz_aware=True)
        return client, client[s.mongodb_db]


@pytest.fixture(scope="session")
def database():
    client, db = _make_db()
    set_db(db)
    yield db
    client.drop_database(db.name)
    set_db(None)


@pytest.fixture(scope="session")
def backend():
    return get_backend()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate-limit counters are process memory: isolate every test (security tests set their own counts)."""
    from app.ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def db(database):
    for name in database.list_collection_names():
        database.drop_collection(name)
    ensure_indexes(database)
    return database


@pytest.fixture()
def client(db, backend):
    from app.main import app

    with TestClient(app) as c:
        yield c


# --- helpers -----------------------------------------------------------------------

PASSWORD = "Passw0rd!"


def register(client, role: str, name: str | None = None, email: str | None = None) -> dict:
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"name": name or f"Test {role}", "email": email,
                                                "password": PASSWORD, "role": role})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "user": data["user"], "email": email}


QUESTION = {
    "text": "Explain tokenization in NLP and why it is important.",
    "max_marks": 4,
    "reference_answer": "Tokenization splits raw text into smaller units called tokens such as words, subwords or "
    "characters. It is the first step of an NLP pipeline and later steps operate on tokens. A tokenizer must handle "
    "punctuation, contractions and special cases.",
    "rubric": [
        {"label": "Definition", "description": "Tokenization splits raw text into smaller units called tokens such as words, subwords or characters", "marks": 2},
        {"label": "First pipeline step", "description": "Tokenization is the first preprocessing step and later NLP steps operate on the tokens", "marks": 1},
        {"label": "Special cases", "description": "A tokenizer must handle punctuation, contractions and other special cases", "marks": 1},
    ],
}

GOOD_ANSWER = (
    "Tokenisation means breaking text into small pieces called tokens, usually words but sometimes sub-words or "
    "characters. It is done first because every later NLP stage such as stemming or tagging works on these tokens. "
    "A good tokenizer also has to deal with punctuation marks and contractions like don't."
)


def make_assessment(client, teacher: dict, publish: bool = True, deadline: str | None = None, **extra) -> dict:
    body = {"title": "NLP Unit Test", "subject": "Natural Language Processing", "instructions": "Answer all questions."}
    if deadline:
        body["deadline"] = deadline
    body.update(extra)
    r = client.post("/api/assessments", json=body, headers=teacher["headers"])
    assert r.status_code == 201, r.text
    a = r.json()
    r = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION}, headers=teacher["headers"])
    assert r.status_code == 201, r.text
    a["question"] = r.json()
    if publish:
        r = client.post(f"/api/assessments/{a['id']}/publish", headers=teacher["headers"])
        assert r.status_code == 200, r.text
    return a


def submit(client, student: dict, assessment: dict, text: str = GOOD_ANSWER) -> dict:
    r = client.post("/api/submissions/submit",
                    json={"assessment_id": assessment["id"],
                          "answers": [{"question_id": assessment["question"]["id"], "text": text}]},
                    headers=student["headers"])
    assert r.status_code == 200, r.text
    return r.json()
