from datetime import datetime, timedelta, timezone

from tests.conftest import QUESTION, make_assessment, register, submit


def test_teacher_creates_and_publishes_assessment(client):
    t = register(client, "teacher")
    r = client.post("/api/assessments", json={"title": "Unit 1", "subject": "NLP"}, headers=t["headers"])
    a = r.json()
    assert r.status_code == 201 and a["status"] == "draft" and a["question_count"] == 0
    # cannot publish without questions
    r = client.post(f"/api/assessments/{a['id']}/publish", headers=t["headers"])
    assert r.status_code == 409 and r.json()["code"] == "no_questions"
    r = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION}, headers=t["headers"])
    assert r.status_code == 201
    q = r.json()
    assert [i["id"] for i in q["rubric"]] == ["c1", "c2", "c3"] and q["rubric_version"] == 1
    r = client.post(f"/api/assessments/{a['id']}/publish", headers=t["headers"])
    assert r.status_code == 200 and r.json()["status"] == "published" and r.json()["total_marks"] == 4


def test_question_rubric_validation(client):
    t = register(client, "teacher")
    a = client.post("/api/assessments", json={"title": "Unit 1", "subject": "NLP"}, headers=t["headers"]).json()
    bad_sum = {**QUESTION, "max_marks": 5}
    r = client.post("/api/questions", json={"assessment_id": a["id"], **bad_sum}, headers=t["headers"])
    assert r.status_code == 422 and "add up" in r.json()["detail"]
    r = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION, "max_marks": 4.3}, headers=t["headers"])
    assert r.status_code == 422
    r = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION, "rubric": [], "reference_answer": ""},
                    headers=t["headers"])
    assert r.status_code == 422
    dup = [QUESTION["rubric"][0], {**QUESTION["rubric"][1], "label": "Definition"}, QUESTION["rubric"][2]]
    r = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION, "rubric": dup}, headers=t["headers"])
    assert r.status_code == 422
    r = client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION,
                                            "settings": {"match_threshold": 0.4, "partial_threshold": 0.6}},
                    headers=t["headers"])
    assert r.status_code == 422


def test_rubric_edit_bumps_version_but_cosmetic_edit_does_not(client):
    t = register(client, "teacher")
    a = make_assessment(client, t, publish=False)
    qid = a["question"]["id"]
    r = client.patch(f"/api/questions/{qid}", json={"rubric_levels": {"excellent": "All three concepts"}}, headers=t["headers"])
    assert r.json()["rubric_version"] == 1
    rubric = [dict(i) for i in QUESTION["rubric"]]
    rubric[2]["description"] = "A tokenizer has to handle punctuation and contractions correctly"
    r = client.patch(f"/api/questions/{qid}", json={"rubric": rubric}, headers=t["headers"])
    assert r.status_code == 200 and r.json()["rubric_version"] == 2
    # max_marks change validated against the existing rubric
    r = client.patch(f"/api/questions/{qid}", json={"max_marks": 10}, headers=t["headers"])
    assert r.status_code == 422


def test_teachers_cannot_access_each_others_assessments(client):
    t1, t2 = register(client, "teacher"), register(client, "teacher")
    a = make_assessment(client, t1)
    assert client.get(f"/api/assessments/{a['id']}", headers=t2["headers"]).status_code == 404
    assert client.patch(f"/api/assessments/{a['id']}", json={"title": "Mine now"}, headers=t2["headers"]).status_code == 404
    assert client.get(f"/api/questions/{a['question']['id']}", headers=t2["headers"]).status_code == 404
    assert client.post("/api/questions", json={"assessment_id": a["id"], **QUESTION}, headers=t2["headers"]).status_code == 404
    assert client.get("/api/assessments", headers=t2["headers"]).json() == []
    assert client.get("/api/assessments/not-an-id", headers=t1["headers"]).status_code == 404


def test_student_sees_only_published_assigned_assessments_without_rubric(client):
    t = register(client, "teacher")
    s1, s2 = register(client, "student"), register(client, "student")
    draft = make_assessment(client, t, publish=False)
    public = make_assessment(client, t)
    only_s1 = make_assessment(client, t, assigned_student_ids=[s1["user"]["id"]])

    ids_s1 = {a["id"] for a in client.get("/api/assessments", headers=s1["headers"]).json()}
    ids_s2 = {a["id"] for a in client.get("/api/assessments", headers=s2["headers"]).json()}
    assert ids_s1 == {public["id"], only_s1["id"]}
    assert ids_s2 == {public["id"]}
    assert client.get(f"/api/assessments/{draft['id']}", headers=s1["headers"]).status_code == 404
    assert client.get(f"/api/assessments/{only_s1['id']}", headers=s2["headers"]).status_code == 404

    detail = client.get(f"/api/assessments/{public['id']}", headers=s1["headers"])
    assert detail.status_code == 200
    raw = detail.text
    assert "reference_answer" not in raw and "rubric" not in raw and "threshold" not in raw
    assert QUESTION["reference_answer"][:40] not in raw
    assert detail.json()["questions"][0]["max_marks"] == 4 and detail.json()["can_edit"] is True
    # students cannot use teacher-only endpoints
    assert client.get(f"/api/questions/{public['question']['id']}", headers=s1["headers"]).status_code == 403
    assert client.get("/api/users/students", headers=s1["headers"]).status_code == 403


def test_assign_unknown_student_rejected(client):
    t = register(client, "teacher")
    other_teacher = register(client, "teacher")
    r = client.post("/api/assessments", json={"title": "Unit", "subject": "NLP", "assigned_student_ids": [other_teacher["user"]["id"]]},
                    headers=t["headers"])
    assert r.status_code == 422


def test_cannot_delete_assessment_with_submissions_and_close_reopen(client):
    t, s = register(client, "teacher"), register(client, "student")
    a = make_assessment(client, t)
    submit(client, s, a)
    assert client.delete(f"/api/assessments/{a['id']}", headers=t["headers"]).status_code == 409
    assert client.delete(f"/api/questions/{a['question']['id']}", headers=t["headers"]).status_code == 409
    r = client.post(f"/api/assessments/{a['id']}/close", headers=t["headers"])
    assert r.json()["status"] == "closed"
    assert client.post(f"/api/assessments/{a['id']}/publish", headers=t["headers"]).json()["status"] == "published"


def test_publish_with_past_deadline_rejected(client):
    t = register(client, "teacher")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    a = make_assessment(client, t, publish=False, deadline=past)
    r = client.post(f"/api/assessments/{a['id']}/publish", headers=t["headers"])
    assert r.status_code == 409 and r.json()["code"] == "deadline_passed"
    r = client.patch(f"/api/assessments/{a['id']}", json={"clear_deadline": True}, headers=t["headers"])
    assert r.json()["deadline"] is None
    assert client.post(f"/api/assessments/{a['id']}/publish", headers=t["headers"]).status_code == 200
