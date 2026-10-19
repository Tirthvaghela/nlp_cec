from datetime import datetime, timedelta, timezone

from tests.conftest import GOOD_ANSWER, make_assessment, register, submit


def body(a, text=GOOD_ANSWER):
    return {"assessment_id": a["id"], "answers": [{"question_id": a["question"]["id"], "text": text}]}


def test_draft_then_submit(client):
    t, s = register(client, "teacher"), register(client, "student")
    a = make_assessment(client, t)
    r = client.put("/api/submissions/draft", json=body(a, "first draft"), headers=s["headers"])
    assert r.status_code == 200 and r.json()["status"] == "draft"
    r = client.put("/api/submissions/draft", json=body(a, "second draft"), headers=s["headers"])
    assert r.json()["answers"][0]["text"] == "second draft"
    detail = client.get(f"/api/assessments/{a['id']}", headers=s["headers"]).json()
    assert detail["my_status"] == "draft" and detail["answers"][0]["text"] == "second draft"
    # drafts are invisible to the teacher
    assert client.get(f"/api/submissions?assessment_id={a['id']}", headers=t["headers"]).json()["total"] == 0

    r = client.post("/api/submissions/submit", json=body(a), headers=s["headers"])
    assert r.status_code == 200 and r.json()["status"] == "submitted" and r.json()["submitted_at"]
    page = client.get(f"/api/submissions?assessment_id={a['id']}", headers=t["headers"]).json()
    assert page["total"] == 1 and page["items"][0]["status"] == "submitted"


def test_duplicate_submission_and_editing_after_submit_rejected(client):
    t, s = register(client, "teacher"), register(client, "student")
    a = make_assessment(client, t)
    submit(client, s, a)
    r = client.post("/api/submissions/submit", json=body(a, "again"), headers=s["headers"])
    assert r.status_code == 409 and r.json()["code"] == "already_submitted"
    r = client.put("/api/submissions/draft", json=body(a, "edit"), headers=s["headers"])
    assert r.status_code == 409


def test_deadline_and_closed_assessments(client, db):
    t, s = register(client, "teacher"), register(client, "student")
    soon = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    a = make_assessment(client, t, deadline=soon)
    # move the deadline into the past directly in the DB (simulating time passing)
    from bson import ObjectId

    db.assessments.update_one({"_id": ObjectId(a["id"])}, {"$set": {"deadline": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    r = client.post("/api/submissions/submit", json=body(a), headers=s["headers"])
    assert r.status_code == 403 and r.json()["code"] == "deadline_passed"
    assert client.get(f"/api/assessments/{a['id']}", headers=s["headers"]).json()["my_status"] == "missed"

    b = make_assessment(client, t)
    client.post(f"/api/assessments/{b['id']}/close", headers=t["headers"])
    r = client.put("/api/submissions/draft", json=body(b), headers=s["headers"])
    assert r.status_code == 403 and r.json()["code"] == "assessment_closed"


def test_submission_validation(client):
    t, s = register(client, "teacher"), register(client, "student")
    a = make_assessment(client, t)
    other = make_assessment(client, t)
    r = client.post("/api/submissions/submit", json=body(a, "   "), headers=s["headers"])
    assert r.status_code == 422 and r.json()["code"] == "empty_submission"
    bad = {"assessment_id": a["id"], "answers": [{"question_id": other["question"]["id"], "text": "x"}]}
    assert client.post("/api/submissions/submit", json=bad, headers=s["headers"]).status_code == 422
    dup = {"assessment_id": a["id"], "answers": [{"question_id": a["question"]["id"], "text": "x"}] * 2}
    assert client.post("/api/submissions/submit", json=dup, headers=s["headers"]).status_code == 422
    too_long = body(a, "x" * 10001)
    assert client.post("/api/submissions/submit", json=too_long, headers=s["headers"]).status_code == 422


def test_teacher_cannot_submit_and_students_are_isolated(client):
    t = register(client, "teacher")
    s1, s2 = register(client, "student"), register(client, "student")
    a = make_assessment(client, t)
    assert client.post("/api/submissions/submit", json=body(a), headers=t["headers"]).status_code == 403
    sub = submit(client, s1, a)
    # another student can neither read the submission nor see it in their list
    assert client.get(f"/api/submissions/{sub['id']}", headers=s2["headers"]).status_code == 404
    assert client.get("/api/submissions/mine", headers=s2["headers"]).json() == []
    # students cannot list submissions of an assessment
    assert client.get(f"/api/submissions?assessment_id={a['id']}", headers=s1["headers"]).status_code == 403
    own = client.get(f"/api/submissions/{sub['id']}", headers=s1["headers"]).json()
    assert own["status"] == "submitted" and "evaluation" not in own


def test_unassigned_student_cannot_submit(client):
    t = register(client, "teacher")
    s1, s2 = register(client, "student"), register(client, "student")
    a = make_assessment(client, t, assigned_student_ids=[s1["user"]["id"]])
    assert client.post("/api/submissions/submit", json=body(a), headers=s2["headers"]).status_code == 404


def test_pagination(client):
    t = register(client, "teacher")
    a = make_assessment(client, t)
    for _ in range(3):
        submit(client, register(client, "student"), a)
    page = client.get(f"/api/submissions?assessment_id={a['id']}&skip=1&limit=1", headers=t["headers"]).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["skip"] == 1
