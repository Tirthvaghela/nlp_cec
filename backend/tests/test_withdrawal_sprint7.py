"""Sprint 7: fail-closed, repeatable withdrawal (fix for sprint 6 finding S6-1).

(a) revoke clears the account's access flag first; (b) repeating a revoke completes an interrupted one without
duplicating history; (c) in PILOT_MODE assessment access needs BOTH the flag and an active enrollment.

Each failure case breaks exactly one database write and then checks what the student can ACTUALLY do on every
assessment entry point (list, detail, save draft, submit), not only the HTTP status of the revoke. No test runs the
scoring engine or loads the embedding model (no `backend` fixture; an autouse guard fails the test otherwise).
"""

from __future__ import annotations

import pytest
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.db import now
from app.services import evaluation_service
from tests.conftest import PASSWORD, make_assessment, register


@pytest.fixture(autouse=True)
def _no_scoring(monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("the scoring engine / embedding model must not run in this test module")

    monkeypatch.setattr(evaluation_service, "evaluate_answer", forbidden)
    monkeypatch.setattr(evaluation_service, "get_backend", forbidden)
    monkeypatch.setattr(evaluation_service, "run_engine", forbidden)


@pytest.fixture
def api(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def pilot(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "pilot_mode", True)  # after start-up (the lifespan checks the pilot marker)
    return api


EMAIL = "participant@example.com"
ALLOWED = (True, 200, 200)
DENIED = (False, 404, 404, 404)


def access(api, student, a, submit=False) -> tuple:
    """What the student can actually do: (listed, detail, draft[, submit]) - listed is a bool, the rest status codes."""
    h = student["headers"]
    body = {"assessment_id": a["id"], "answers": [{"question_id": a["question"]["id"], "text": "an answer"}]}
    listed = [x["id"] for x in api.get("/api/assessments", headers=h).json()] == [a["id"]]
    out = (listed, api.get(f"/api/assessments/{a['id']}", headers=h).status_code,
           api.put("/api/submissions/draft", json=body, headers=h).status_code)
    if submit:
        out += (api.post("/api/submissions/submit", json=body, headers=h).status_code,)
    return out


@pytest.fixture
def setup(pilot, db):
    """An enrolled, registered participant with access to one published assessment."""
    teacher = register(pilot, "teacher")
    assert pilot.post("/api/enrollments", json={"emails": [EMAIL]}, headers=teacher["headers"]).status_code == 201
    student = register(pilot, "student", email=EMAIL)
    a = make_assessment(pilot, teacher)
    assert access(pilot, student, a) == ALLOWED
    return pilot, teacher, student, a


def _events(db):
    return list(db.enrollment_events.find({"email": EMAIL}).sort([("at", 1), ("_id", 1)]))


def _actions(db):
    return [e["action"] for e in _events(db)]


def _fail(monkeypatch, method: str, collection: str):
    """Make one kind of write on one collection raise (as a lost database connection would); returns an undo."""
    original = getattr(Collection, method)

    def broken(self, *a, **k):
        if self.name == collection:
            raise PyMongoError(f"simulated failure of {collection}.{method}")
        return original(self, *a, **k)

    monkeypatch.setattr(Collection, method, broken)
    return lambda: monkeypatch.setattr(Collection, method, original)


def _revoke(api, teacher, email=EMAIL):
    return api.delete(f"/api/enrollments/{email}", headers=teacher["headers"])


def _listed_active(api, teacher):
    return {e["email"]: e["active"] for e in api.get("/api/enrollments", headers=teacher["headers"]).json()}


def _flag(db):
    return db.users.find_one({"email": EMAIL})["pilot_enrolled"]


# ============================== (a) + (b): revocation ==================================================

def test_successful_revocation_removes_access_everywhere(setup, db):
    api, teacher, student, a = setup
    r = _revoke(api, teacher)
    assert r.status_code == 200 and "revoked" in r.json()["detail"]
    assert access(api, student, a, submit=True) == DENIED
    assert _flag(db) is False and _listed_active(api, teacher) == {EMAIL: False}
    events = _events(db)
    assert [e["action"] for e in events] == ["enrolled", "registered", "revoked"]
    revoked_at = db.enrollments.find_one({"email": EMAIL})["revoked_at"]
    assert events[-1]["by"] == ObjectId(teacher["user"]["id"]) and events[-1]["at"] == revoked_at


def test_failure_before_anything_changed_leaves_a_consistent_active_state(setup, db, monkeypatch):
    """Step 1 (access flag) fails: nothing changed, the list and the access agree (still active); a retry works."""
    api, teacher, student, a = setup
    undo = _fail(monkeypatch, "update_one", "users")
    assert _revoke(api, teacher).status_code == 500
    undo()
    assert _listed_active(api, teacher) == {EMAIL: True} and _flag(db) is True
    assert access(api, student, a) == ALLOWED
    assert _actions(db) == ["enrolled", "registered"]
    assert _revoke(api, teacher).status_code == 200
    assert access(api, student, a, submit=True) == DENIED
    assert _actions(db) == ["enrolled", "registered", "revoked"]


def test_failure_after_access_is_disabled_fails_closed_and_retry_completes(setup, db, monkeypatch):
    """S6-1 scenario, reversed: step 2 (enrollment state) fails AFTER the flag is cleared."""
    api, teacher, student, a = setup
    undo = _fail(monkeypatch, "update_one", "enrollments")
    r = _revoke(api, teacher)
    undo()
    assert r.status_code == 500  # never reported as success
    assert _flag(db) is False
    assert access(api, student, a, submit=True) == DENIED  # access is ALREADY gone
    assert _listed_active(api, teacher) == {EMAIL: True}  # the list lags behind (fail-closed direction only)
    assert _actions(db) == ["enrolled", "registered"]  # no event for a change that did not happen
    r = _revoke(api, teacher)
    assert r.status_code == 200 and r.json()["detail"].startswith("Enrollment revoked")
    assert _listed_active(api, teacher) == {EMAIL: False}
    assert access(api, student, a, submit=True) == DENIED
    assert _actions(db) == ["enrolled", "registered", "revoked"]


def test_failure_of_the_audit_event_fails_closed_and_retry_records_it_once(setup, db, monkeypatch):
    api, teacher, student, a = setup
    undo = _fail(monkeypatch, "insert_one", "enrollment_events")
    assert _revoke(api, teacher).status_code == 500
    undo()
    assert access(api, student, a, submit=True) == DENIED
    assert _listed_active(api, teacher) == {EMAIL: False}
    assert _actions(db) == ["enrolled", "registered"]
    revoked_at = db.enrollments.find_one({"email": EMAIL})["revoked_at"]
    other = register(api, "teacher")
    r = _revoke(api, other)  # any teacher may complete it (existing rule: any teacher manages enrollment)
    assert r.status_code == 200 and "interrupted revocation was completed" in r.json()["detail"]
    events = _events(db)
    assert [e["action"] for e in events] == ["enrolled", "registered", "revoked"]
    last = events[-1]
    assert last["at"] == revoked_at and last["by"] == ObjectId(teacher["user"]["id"])  # who actually revoked
    assert last["completed_by"] == ObjectId(other["user"]["id"]) and last["completed_at"] >= revoked_at
    assert _revoke(api, other).json()["detail"].startswith("This enrollment was already revoked")
    assert _actions(db) == ["enrolled", "registered", "revoked"]  # no duplicate


def test_repeated_revocation_after_success_is_harmless(setup, db):
    api, teacher, student, a = setup
    assert _revoke(api, teacher).status_code == 200
    before = db.enrollments.find_one({"email": EMAIL})
    for _ in range(3):
        r = _revoke(api, teacher)
        assert r.status_code == 200 and r.json()["detail"].startswith("This enrollment was already revoked")
    after = db.enrollments.find_one({"email": EMAIL})
    assert after["revoked_at"] == before["revoked_at"] and after["revoked_by"] == before["revoked_by"]
    assert _actions(db) == ["enrolled", "registered", "revoked"]
    assert access(api, student, a, submit=True) == DENIED


def test_repeated_revoke_reasserts_a_flag_that_was_turned_back_on(setup, db):
    """Partial state left by an older version or a direct write: revoked enrollment, flag still on. Access is already
    denied by (c); a repeated revoke also clears the flag."""
    api, teacher, student, a = setup
    assert _revoke(api, teacher).status_code == 200
    db.users.update_one({"email": EMAIL}, {"$set": {"pilot_enrolled": True}})
    assert access(api, student, a, submit=True) == DENIED
    assert _revoke(api, teacher).status_code == 200 and _flag(db) is False
    assert _actions(db) == ["enrolled", "registered", "revoked"]


def test_unknown_participant_is_404_and_nothing_is_written(pilot, db):
    teacher = register(pilot, "teacher")
    users_before = db.users.count_documents({})
    r = _revoke(pilot, teacher, "never-enrolled@example.com")
    assert r.status_code == 404 and r.json()["detail"] == "No enrollment for this e-mail"
    assert db.enrollment_events.count_documents({}) == 0 and db.enrollments.count_documents({}) == 0
    assert db.users.count_documents({}) == users_before


def test_unregistered_enrollment_can_be_revoked(pilot, db):
    teacher = register(pilot, "teacher")
    pilot.post("/api/enrollments", json={"emails": [EMAIL]}, headers=teacher["headers"])
    assert _revoke(pilot, teacher).status_code == 200
    assert _actions(db) == ["enrolled", "revoked"]
    r = pilot.post("/api/auth/register", json={"name": "Test student", "email": EMAIL, "password": PASSWORD,
                                               "role": "student"})
    assert r.status_code == 403 and r.json()["code"] == "enrollment_required"  # existing registration rule


def test_concurrent_reenrollment_is_reported_not_overwritten(setup, db, monkeypatch):
    """If the enrollment becomes active again between the checks (another teacher re-enrolled), revoke does not
    touch the new state and says so (409); the flag clearing still fails closed until someone re-enrolls."""
    api, teacher, _, _ = setup
    original = Collection.update_one

    def lost_race(self, flt, update, *a, **k):
        if self.name == "enrollments" and "revoked_at" in str(update):
            from pymongo.results import UpdateResult

            return UpdateResult({"n": 0, "nModified": 0}, acknowledged=True)  # someone else changed it first
        return original(self, flt, update, *a, **k)

    monkeypatch.setattr(Collection, "update_one", lost_race)
    r = _revoke(api, teacher)
    monkeypatch.setattr(Collection, "update_one", original)
    assert r.status_code == 409 and r.json()["code"] == "enrollment_changed"
    assert db.enrollments.find_one({"email": EMAIL})["revoked_at"] is None and _actions(db) == ["enrolled", "registered"]


# ============================== (c): access needs flag AND active enrollment ===========================

def test_flag_off_denies_access_even_with_an_active_enrollment(setup, db):
    api, _, student, a = setup
    db.users.update_one({"email": EMAIL}, {"$set": {"pilot_enrolled": False}})
    assert access(api, student, a, submit=True) == DENIED


@pytest.mark.parametrize("break_enrollment", [
    lambda db, sid: db.enrollments.delete_one({"email": EMAIL}),  # missing
    lambda db, sid: db.enrollments.update_one({"email": EMAIL}, {"$set": {"revoked_at": now()}}),  # revoked/inactive
    lambda db, sid: db.enrollments.update_one({"email": EMAIL}, {"$set": {"user_id": ObjectId()}}),  # other account
], ids=["missing", "revoked", "linked-to-another-account"])
def test_flag_on_without_a_valid_active_enrollment_denies_access(setup, db, break_enrollment):
    api, _, student, a = setup
    break_enrollment(db, student["user"]["id"])
    assert db.users.find_one({"email": EMAIL})["pilot_enrolled"] is True
    assert access(api, student, a, submit=True) == DENIED


def test_access_only_when_flag_and_active_enrollment_are_both_valid(setup, db):
    api, _, student, a = setup
    assert access(api, student, a) == ALLOWED
    db.enrollments.update_one({"email": EMAIL}, {"$set": {"user_id": None}})  # registration link missing (A7 window)
    assert access(api, student, a) == ALLOWED  # same e-mail, active, not linked elsewhere


def test_reenrolling_restores_access(setup, db):
    api, teacher, student, a = setup
    _revoke(api, teacher)
    assert access(api, student, a, submit=True) == DENIED
    assert api.post("/api/enrollments", json={"emails": [EMAIL]}, headers=teacher["headers"]).status_code == 201
    assert access(api, student, a) == ALLOWED


def test_partial_enroll_failure_fails_closed(pilot, db, monkeypatch):
    """Re-enroll: enrollment active but the flag write fails -> no access until the request is repeated."""
    teacher = register(pilot, "teacher")
    pilot.post("/api/enrollments", json={"emails": [EMAIL]}, headers=teacher["headers"])
    student = register(pilot, "student", email=EMAIL)
    a = make_assessment(pilot, teacher)
    _revoke(pilot, teacher)
    undo = _fail(monkeypatch, "update_one", "users")
    assert pilot.post("/api/enrollments", json={"emails": [EMAIL]}, headers=teacher["headers"]).status_code == 500
    undo()
    assert _listed_active(pilot, teacher) == {EMAIL: True}
    assert access(pilot, student, a, submit=True) == DENIED
    assert pilot.post("/api/enrollments", json={"emails": [EMAIL]}, headers=teacher["headers"]).status_code == 201
    assert access(pilot, student, a) == ALLOWED


# ============================== authorisation and development-mode regressions =======================

def test_only_teachers_can_revoke(setup):
    api, _, student, a = setup
    assert api.delete(f"/api/enrollments/{EMAIL}", headers=student["headers"]).status_code == 403
    assert api.delete(f"/api/enrollments/{EMAIL}").status_code == 401
    assert access(api, student, a) == ALLOWED  # nothing changed


def test_development_mode_ignores_enrollment(api, db):
    teacher = register(api, "teacher")
    student = register(api, "student")  # no enrollment, no flag
    a = make_assessment(api, teacher)
    assert get_settings().pilot_mode is False
    assert access(api, student, a) == ALLOWED
