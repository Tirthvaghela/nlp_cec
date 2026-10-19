"""Groq provider layer of the drafting endpoints (services/generation.py).

groq.Groq is replaced by a fake client, so no request ever leaves the machine and no free-tier quota is used. The real
SDK exception classes are raised, so the error mapping is tested against the types the SDK actually throws.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import groq
import httpx
import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.services import generation as gen
from tests.conftest import QUESTION, register

SECRET = "gsk_test_DO_NOT_LEAK_0123456789"
REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def completion(content, finish="stop", model="llama-3.3-70b-versatile"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)], model=model)


def status_error(cls, status, code="", message="provider says no"):
    body = {"error": {"message": message, "type": "invalid_request_error", "code": code}}
    return cls(message, response=httpx.Response(status, request=REQ, json=body), body=body)


class FakeGroq:
    """Stands in for groq.Groq: records constructor arguments and requests, returns or raises what the test set."""

    instances: list["FakeGroq"] = []
    outcome = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.requests: list[dict] = []
        FakeGroq.instances.append(self)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(FakeGroq.outcome, BaseException):
            raise FakeGroq.outcome
        return FakeGroq.outcome


@pytest.fixture()
def fake_groq(monkeypatch):
    FakeGroq.instances = []
    FakeGroq.outcome = completion("Tokenization splits text into tokens.")
    monkeypatch.setattr(groq, "Groq", FakeGroq)
    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr(SECRET))
    monkeypatch.setattr(get_settings(), "generation_model", "llama-3.3-70b-versatile")
    return FakeGroq


@pytest.fixture()
def teacher(client):
    return register(client, "teacher")


def post_ref(client, teacher):
    return client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4}, headers=teacher["headers"])


# --- configuration -------------------------------------------------------------------------------------------------

def test_missing_key_is_reported_as_not_configured_without_calling_groq(client, teacher, monkeypatch, fake_groq):
    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr(""))
    r = post_ref(client, teacher)
    assert r.status_code == 503
    assert r.json()["code"] == "generation_unavailable"
    assert "GROQ_API_KEY is not configured" in r.json()["detail"]
    assert "write it yourself" in r.json()["detail"]
    assert fake_groq.instances == []


def test_the_env_example_placeholder_counts_as_not_configured(client, teacher, monkeypatch, fake_groq):
    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr("your_groq_api_key_here"))
    r = post_ref(client, teacher)
    assert r.status_code == 503 and "GROQ_API_KEY is not configured" in r.json()["detail"]
    assert fake_groq.instances == []


def test_key_is_passed_explicitly_with_bounded_timeout_and_retries(client, teacher, fake_groq):
    r = post_ref(client, teacher)
    assert r.status_code == 200, r.text
    assert r.json() == {"reference_answer": "Tokenization splits text into tokens.", "model": "llama-3.3-70b-versatile"}
    (inst,) = fake_groq.instances
    assert inst.kwargs == {"api_key": SECRET, "timeout": gen.REQUEST_TIMEOUT_S, "max_retries": gen.MAX_RETRIES}
    assert 0 < gen.MAX_RETRIES <= 2
    (req,) = inst.requests
    assert req["model"] == "llama-3.3-70b-versatile"
    assert req["messages"][0]["role"] == "system"
    assert QUESTION["text"] in req["messages"][1]["content"] and "4 marks" in req["messages"][1]["content"]
    assert "response_format" not in req


def test_generation_model_is_configurable(client, teacher, fake_groq, monkeypatch):
    monkeypatch.setattr(get_settings(), "generation_model", "openai/gpt-oss-20b")
    fake_groq.outcome = completion("Answer.", model="openai/gpt-oss-20b")
    r = post_ref(client, teacher)
    assert r.status_code == 200
    assert fake_groq.instances[0].requests[0]["model"] == "openai/gpt-oss-20b"
    assert r.json()["model"] == "openai/gpt-oss-20b"


def test_key_and_model_are_read_from_an_env_file_and_the_key_is_masked(tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GENERATION_MODEL", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"GROQ_API_KEY={SECRET}\nGENERATION_MODEL=openai/gpt-oss-20b\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.groq_api_key.get_secret_value() == SECRET
    assert s.generation_model == "openai/gpt-oss-20b"
    assert SECRET not in repr(s) and SECRET not in str(s)


def test_default_model_is_a_groq_model():
    from app.config import Settings

    assert Settings.model_fields["generation_model"].default == "llama-3.3-70b-versatile"
    assert not Settings.model_fields["groq_api_key"].default.get_secret_value()


# --- provider errors -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("error,status,code,phrase", [
    (lambda: status_error(groq.AuthenticationError, 401, "invalid_api_key"), 503, "generation_unavailable", "API key was rejected"),
    (lambda: status_error(groq.PermissionDeniedError, 403), 503, "generation_unavailable", "cannot use this model"),
    (lambda: status_error(groq.NotFoundError, 404, "model_not_found"), 503, "generation_unavailable", "is not available on Groq"),
    (lambda: status_error(groq.BadRequestError, 400, "model_decommissioned"), 503, "generation_unavailable", "is not available on Groq"),
    (lambda: status_error(groq.RateLimitError, 429, "rate_limit_exceeded"), 503, "generation_rate_limited", "rate limit or quota"),
    (lambda: groq.APITimeoutError(request=REQ), 503, "generation_temporarily_unavailable", "did not answer in time"),
    (lambda: groq.APIConnectionError(request=REQ), 503, "generation_temporarily_unavailable", "could not be reached"),
    (lambda: status_error(groq.InternalServerError, 503), 503, "generation_temporarily_unavailable", "temporary problem"),
    (lambda: status_error(groq.BadRequestError, 400, "context_length_exceeded"), 422, "generation_failed", "rejected the request"),
])
def test_provider_errors_map_to_safe_responses(client, teacher, fake_groq, error, status, code, phrase):
    fake_groq.outcome = error()
    r = post_ref(client, teacher)
    assert r.status_code == status, r.text
    assert r.json()["code"] == code
    assert phrase in r.json()["detail"]
    assert "provider says no" not in r.json()["detail"]  # no raw provider payload


@pytest.mark.parametrize("outcome,phrase", [
    (completion(""), "empty draft"),
    (completion("   \n "), "empty draft"),
    (completion(None), "empty draft"),
    (completion("A partial answer that was cut", finish="length"), "cut off"),
    (SimpleNamespace(choices=[], model="m"), "unexpected response"),
    (SimpleNamespace(model="m"), "unexpected response"),
    (completion("x" * 5001), "longer than a reference answer"),
])
def test_unusable_model_output_is_an_error_never_a_fabricated_answer(client, teacher, fake_groq, outcome, phrase):
    fake_groq.outcome = outcome
    r = post_ref(client, teacher)
    assert r.status_code == 422
    assert r.json()["code"] == "generation_failed"
    assert phrase in r.json()["detail"]


def test_code_fence_around_the_whole_answer_is_removed(client, teacher, fake_groq):
    fake_groq.outcome = completion("```markdown\n- Tokens are units.\n- First step.\n```")
    assert post_ref(client, teacher).json()["reference_answer"] == "- Tokens are units.\n- First step."


def test_the_key_never_appears_in_responses_or_logs(client, teacher, fake_groq, caplog):
    caplog.set_level(logging.DEBUG)
    for err in (status_error(groq.AuthenticationError, 401, "invalid_api_key", message=f"Invalid API Key {SECRET}"),
                status_error(groq.RateLimitError, 429), groq.APIConnectionError(request=REQ)):
        fake_groq.outcome = err
        r = post_ref(client, teacher)
        assert SECRET not in r.text
    assert SECRET not in caplog.text
    assert "Authorization" not in caplog.text


# --- access control and rate limiting --------------------------------------------------------------------------------

def test_students_and_anonymous_users_cannot_draft(client, fake_groq):
    student = register(client, "student")
    assert post_ref(client, student).status_code == 403
    assert client.post("/api/generation/reference-answer", json={"question": QUESTION["text"], "max_marks": 4}).status_code == 401
    assert fake_groq.instances == []


def test_invalid_question_input_never_reaches_groq(client, teacher, fake_groq):
    for body in ({"question": "   ", "max_marks": 4}, {"question": "Hi", "max_marks": 4}, {"question": QUESTION["text"], "max_marks": 0},
                 {"question": QUESTION["text"]}, {"question": "x" * 2001, "max_marks": 4}):
        assert client.post("/api/generation/reference-answer", json=body, headers=teacher["headers"]).status_code == 422
    assert fake_groq.instances == []


def test_existing_rate_limit_still_applies(client, teacher, fake_groq, monkeypatch):
    from app.routers import generation as router

    monkeypatch.setattr(router, "GENERATION_LIMIT", 2)
    assert [post_ref(client, teacher).status_code for _ in range(3)] == [200, 200, 429]
    assert len(fake_groq.instances) == 2


def test_pilot_mode_never_contacts_groq(client, teacher, fake_groq, monkeypatch):
    monkeypatch.setattr(get_settings(), "pilot_mode", True)
    assert post_ref(client, teacher).status_code == 403
    r = client.post("/api/generation/rubric", json={"question": QUESTION["text"], "max_marks": 4, "reference_answer": QUESTION["reference_answer"]},
                    headers=teacher["headers"])
    assert r.status_code == 200 and r.json()["source"] == "derived"
    assert fake_groq.instances == []


# --- rubric ---------------------------------------------------------------------------------------------------------

def post_rubric(client, teacher):
    return client.post("/api/generation/rubric", json={"question": QUESTION["text"], "max_marks": 4, "reference_answer": QUESTION["reference_answer"]},
                       headers=teacher["headers"])


def test_rubric_uses_json_mode_and_is_validated(client, teacher, fake_groq):
    fake_groq.outcome = completion('{"criteria": [{"label": "Definition", "description": "Splits text into tokens", "marks": 2.5},'
                                   ' {"label": "First step", "description": "It is the first pipeline step", "marks": 1.5}]}')
    r = post_rubric(client, teacher)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "model"
    assert [c["marks"] for c in r.json()["rubric"]] == [2.5, 1.5]
    assert fake_groq.instances[0].requests[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("content,phrase", [
    ('{"criteria": [{"label": "A", "description": "Something", "marks": 3}]}', "add up to 3"),
    ('{"criteria": [{"label": "A", "description": "Something", "marks": 1.3}, {"label": "B", "description": "Else", "marks": 2.7}]}', "steps of 0.5"),
    ('{"items": []}', "could not be read"),
    ("not json", "could not be read"),
])
def test_invalid_model_rubric_is_an_error_not_a_repair(client, teacher, fake_groq, content, phrase):
    fake_groq.outcome = completion(content)
    r = post_rubric(client, teacher)
    assert r.status_code == 422
    assert phrase in r.json()["detail"]


def test_rubric_is_derived_locally_without_a_key(client, teacher, fake_groq, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr(""))
    r = post_rubric(client, teacher)
    assert r.status_code == 200
    assert r.json()["source"] == "derived"
    assert gen.rubric_problem(r.json()["rubric"], 4) is None
    assert fake_groq.instances == []
