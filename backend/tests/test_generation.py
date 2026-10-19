"""Question-authoring drafts (POST /api/generation/*).

The drafting model is never called here: the service functions that talk to it are monkeypatched, so these tests check
the API contract - access control, the pilot refusal, honest 503s without credentials, validation of model rubrics and
the local rubric derivation - without network access or credentials.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.services import generation as gen
from tests.conftest import QUESTION, register

REF = QUESTION["reference_answer"]


def _unavailable(*_a, **_k):
    raise gen.GenerationUnavailable("No credentials.")


@pytest.fixture()
def teacher(client):
    return register(client, "teacher")


def test_students_cannot_request_drafts(client):
    student = register(client, "student")
    r = client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4},
                    headers=student["headers"])
    assert r.status_code == 403


def test_reference_answer_returns_the_models_draft(client, teacher, monkeypatch):
    seen = {}

    def fake(question, max_marks):
        seen.update(question=question, max_marks=max_marks)
        return "Tokenization splits text into tokens.", "claude-opus-5-5"

    monkeypatch.setattr(gen, "draft_reference_answer", fake)
    r = client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4},
                    headers=teacher["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {"reference_answer": "Tokenization splits text into tokens.", "model": "claude-opus-5-5"}
    assert seen == {"question": QUESTION["text"], "max_marks": 4}


def test_reference_answer_without_credentials_is_an_honest_503(client, teacher, monkeypatch):
    monkeypatch.setattr(gen, "draft_reference_answer", _unavailable)
    r = client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4},
                    headers=teacher["headers"])
    assert r.status_code == 503
    assert r.json()["code"] == "generation_unavailable"
    assert "write it yourself" in r.json()["detail"]


def test_reference_answer_validates_input(client, teacher):
    r = client.post("/api/generation/reference-answer", json={"question": "   ", "max_marks": 4}, headers=teacher["headers"])
    assert r.status_code == 422
    r = client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 1.3},
                    headers=teacher["headers"])
    assert r.status_code == 422


def test_reference_answer_is_refused_in_the_pilot(client, teacher, monkeypatch):
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    called = []
    monkeypatch.setattr(gen, "draft_reference_answer", lambda *a: called.append(a))
    r = client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4},
                    headers=teacher["headers"])
    assert r.status_code == 403
    assert r.json()["code"] == "generation_disabled_in_pilot"
    assert called == []


def test_rubric_from_the_model_is_returned_when_valid(client, teacher, monkeypatch):
    criteria = [{"label": "Definition", "description": "Splits text into tokens", "marks": 3},
                {"label": "Pipeline", "description": "First step of the pipeline", "marks": 1}]
    monkeypatch.setattr(gen, "draft_rubric_with_model", lambda *a: (criteria, "claude-opus-5-5"))
    r = client.post("/api/generation/rubric", json={"question": QUESTION["text"], "max_marks": 4, "reference_answer": REF},
                    headers=teacher["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {"rubric": criteria, "source": "model", "model": "claude-opus-5-5"}


def test_invalid_model_rubric_is_an_error_not_a_silent_repair(client, teacher, monkeypatch):
    def fake(*_a):
        raise gen.GenerationFailed("The drafted rubric is not valid: The criteria add up to 5 marks, but the question is worth 4.")

    monkeypatch.setattr(gen, "draft_rubric_with_model", fake)
    r = client.post("/api/generation/rubric", json={"question": QUESTION["text"], "max_marks": 4, "reference_answer": REF},
                    headers=teacher["headers"])
    assert r.status_code == 422
    assert r.json()["code"] == "generation_failed"


@pytest.mark.parametrize("pilot", [False, True])
def test_rubric_is_derived_locally_without_a_model(client, teacher, monkeypatch, pilot):
    monkeypatch.setattr(get_settings(), "pilot_mode", pilot)
    monkeypatch.setattr(gen, "draft_rubric_with_model", _unavailable)
    r = client.post("/api/generation/rubric", json={"question": QUESTION["text"], "max_marks": 4, "reference_answer": REF},
                    headers=teacher["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "derived" and body["model"] is None
    assert gen.rubric_problem(body["rubric"], 4) is None
    # the derived rubric is accepted by the question schema as-is
    a = client.post("/api/assessments", json={"title": "Drafts", "subject": "NLP"}, headers=teacher["headers"]).json()
    q = client.post("/api/questions", json={"assessment_id": a["id"], "text": QUESTION["text"], "max_marks": 4,
                                            "reference_answer": REF, "rubric": body["rubric"]}, headers=teacher["headers"])
    assert q.status_code == 201, q.text


@pytest.mark.parametrize("max_marks", [0.5, 1, 2.5, 5, 7.5, 10])
def test_derived_rubrics_always_satisfy_the_question_schema(max_marks):
    reference = ("### Tokenization\n\n**Tokenization** splits text into tokens.\n\n- It is the *first* step.\n"
                 "- Later steps use tokens.\n\n| Unit | Example |\n| --- | --- |\n| Word | cat |\n\nIt handles punctuation.")
    criteria = gen.derive_rubric(max_marks, reference)
    assert gen.rubric_problem(criteria, max_marks) is None
    assert all("**" not in c["description"] and "|" not in c["description"] for c in criteria)


def test_rubric_problem_mirrors_the_question_rules():
    ok = [{"label": "A", "description": "abc", "marks": 2}]
    assert gen.rubric_problem(ok, 2) is None
    assert "add up" in gen.rubric_problem(ok, 3)
    assert "steps of 0.5" in gen.rubric_problem([{**ok[0], "marks": 0.3}], 0.3)
    assert "unique" in gen.rubric_problem(ok + [{"label": "a", "description": "def", "marks": 1}], 3)
    assert "between 1" in gen.rubric_problem([], 1)


def test_generation_rate_limit(client, teacher, monkeypatch):
    from app.routers import generation as router

    monkeypatch.setattr(router, "GENERATION_LIMIT", 2)
    monkeypatch.setattr(gen, "draft_reference_answer", lambda *a: ("Answer.", "m"))
    codes = [client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4},
                         headers=teacher["headers"]).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
