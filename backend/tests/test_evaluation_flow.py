"""End-to-end teacher/student workflow with the real NLP engine."""

from tests.conftest import QUESTION, make_assessment, register, submit


def setup_flow(client):
    t, s = register(client, "teacher"), register(client, "student")
    a = make_assessment(client, t)
    sub = submit(client, s, a)
    return t, s, a, sub


def evaluate(client, t, sub, **params):
    return client.post(f"/api/evaluations/submission/{sub['id']}", params=params, headers=t["headers"])


def test_full_workflow_evaluate_review_publish_view(client):
    t, s, a, sub = setup_flow(client)

    # student sees no result before evaluation/publication
    assert client.get(f"/api/results/submission/{sub['id']}", headers=s["headers"]).status_code == 404

    r = evaluate(client, t, sub)
    assert r.status_code == 200, r.text
    review = r.json()
    assert review["status"] == "evaluated"
    ev = review["questions"][0]["evaluation"]
    assert ev["version"] == 1 and ev["status"] == "ai_suggested" and not ev["published"]
    assert 0 <= ev["ai_score"] <= 4 and ev["final_score"] == ev["ai_score"]
    res = ev["result"]
    assert len(res["concepts"]) == 3 and res["feedback"]["summary"]
    assert {c["level"] for c in res["concepts"]} <= {"matched", "partial", "missing"}
    assert ev["engine_version"] and ev["config_fingerprint"] and ev["rubric_version"] == 1

    # still hidden from the student while only evaluated
    assert client.get(f"/api/results/submission/{sub['id']}", headers=s["headers"]).status_code == 404
    assert client.get("/api/results/mine", headers=s["headers"]).json() == []
    mine = client.get("/api/submissions/mine", headers=s["headers"]).json()
    assert mine[0]["status"] == "evaluated" and mine[0]["total_score"] is None

    # teacher review: change requires a reason; bounds enforced
    url = f"/api/evaluations/{ev['id']}"
    new_score = 3.5 if ev["ai_score"] != 3.5 else 3.0
    assert client.patch(url, json={"teacher_score": new_score}, headers=t["headers"]).status_code == 422
    assert client.patch(url, json={"teacher_score": 4.5, "adjustment_reason": "x"}, headers=t["headers"]).status_code == 422
    assert client.patch(url, json={"teacher_score": 1.1, "adjustment_reason": "x"}, headers=t["headers"]).status_code == 422
    r = client.patch(url, json={"teacher_score": new_score, "adjustment_reason": "Example was good",
                                "teacher_feedback": "Nice work - add an example of a contraction."}, headers=t["headers"])
    assert r.status_code == 200
    ev2 = r.json()
    assert ev2["teacher_score"] == new_score and ev2["ai_score"] == ev["ai_score"]  # AI suggestion preserved
    assert ev2["final_score"] == new_score and ev2["status"] == "reviewed"

    # publish
    r = client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"])
    assert r.status_code == 200
    # editing a published result is blocked
    assert client.patch(url, json={"teacher_score": 1, "adjustment_reason": "x"}, headers=t["headers"]).status_code == 409

    # student now sees the result
    r = client.get(f"/api/results/submission/{sub['id']}", headers=s["headers"])
    assert r.status_code == 200
    result = r.json()
    assert result["total_score"] == new_score and result["max_total"] == 4
    q = result["questions"][0]
    assert q["adjusted_by_teacher"] and q["ai_score"] == ev["ai_score"]
    assert q["teacher_feedback"].startswith("Nice work")
    assert "reference_answer" not in r.text and "combined_score" not in r.text and "threshold" not in r.text
    # concept labels/descriptions are shown after publication, but never the full reference answer text
    assert QUESTION["reference_answer"] not in r.text
    summaries = client.get("/api/results/mine", headers=s["headers"]).json()
    assert summaries[0]["percentage"] == round(100 * new_score / 4, 1)
    progress = client.get("/api/analytics/student", headers=s["headers"]).json()
    assert progress["results"][0]["score"] == new_score


def test_other_users_cannot_evaluate_or_view(client):
    t, s, a, sub = setup_flow(client)
    t2, s2 = register(client, "teacher"), register(client, "student")
    assert evaluate(client, t2, sub).status_code == 404
    assert evaluate(client, s, sub).status_code == 403
    evaluate(client, t, sub)
    client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"])
    assert client.get(f"/api/results/submission/{sub['id']}", headers=s2["headers"]).status_code == 404
    assert client.get(f"/api/evaluations/submission/{sub['id']}", headers=t2["headers"]).status_code == 404
    assert client.get(f"/api/evaluations/submission/{sub['id']}", headers=s["headers"]).status_code == 403
    assert client.post(f"/api/results/submission/{sub['id']}/unpublish", headers=t2["headers"]).status_code == 404
    assert client.get(f"/api/analytics/assessment/{a['id']}", headers=t2["headers"]).status_code == 404


def test_reevaluation_versions_and_published_guard(client, db):
    t, s, a, sub = setup_flow(client)
    evaluate(client, t, sub)
    client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"])
    r = evaluate(client, t, sub)
    assert r.status_code == 409 and r.json()["code"] == "published"
    r = evaluate(client, t, sub, allow_unpublish="true")
    assert r.status_code == 200
    ev = r.json()["questions"][0]["evaluation"]
    assert ev["version"] == 2 and ev["history_count"] == 1 and not ev["published"]
    assert r.json()["status"] == "evaluated"
    hist = client.get(f"/api/evaluations/{ev['id']}/history", headers=t["headers"]).json()
    assert hist[0]["version"] == 1
    # the student no longer sees the (unpublished) result
    assert client.get(f"/api/results/submission/{sub['id']}", headers=s["headers"]).status_code == 404
    assert db.evaluations.count_documents({"submission_id": ev and db.evaluations.find_one()["submission_id"]}) == 1


def test_teacher_overrides_are_logged_append_only(client, db):
    """Audit fix: a second review used to overwrite the first adjustment and its reason without a trace."""
    t, s, a, sub = setup_flow(client)
    ev = evaluate(client, t, sub).json()["questions"][0]["evaluation"]
    url = f"/api/evaluations/{ev['id']}"
    first, second = (1.0, 2.0) if ev["ai_score"] not in (1.0, 2.0) else (0.5, 3.0)
    assert client.patch(url, json={"teacher_score": first, "adjustment_reason": "Missed the definition"},
                        headers=t["headers"]).status_code == 200
    assert client.patch(url, json={"teacher_score": second, "adjustment_reason": "Re-read: definition is implied"},
                        headers=t["headers"]).status_code == 200
    log = db.evaluations.find_one({"_id": db.evaluations.find_one()["_id"]})["review_log"]
    assert [e["teacher_score"] for e in log] == [first, second]
    assert [e["adjustment_reason"] for e in log] == ["Missed the definition", "Re-read: definition is implied"]
    assert all(e["ai_score"] == ev["ai_score"] and e["reviewed_by"] and e["at"] for e in log)
    # re-evaluation archives the log with the evaluation instead of dropping it
    evaluate(client, t, sub)
    archived = db.evaluation_history.find_one({"version": 1})
    assert len(archived["review_log"]) == 2
    assert "review_log" not in db.evaluations.find_one()


def test_pilot_setting_requires_teacher_review_before_publication(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "require_review_before_publish", True)
    assert client.get("/api/health").json()["require_review_before_publish"] is True
    t, s, a, sub = setup_flow(client)
    ev = evaluate(client, t, sub).json()["questions"][0]["evaluation"]
    r = client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"])
    assert r.status_code == 409 and r.json()["code"] == "review_required"
    bulk = client.post(f"/api/results/assessment/{a['id']}/publish", json={}, headers=t["headers"]).json()
    assert bulk["published_submissions"] == 0 and "reviewed" in bulk["skipped"][0]["reason"]
    assert client.get(f"/api/results/submission/{sub['id']}", headers=s["headers"]).status_code == 404
    # accepting the AI suggestion counts as a review
    assert client.patch(f"/api/evaluations/{ev['id']}", json={"teacher_score": None, "mark_reviewed": True},
                        headers=t["headers"]).status_code == 200
    assert client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"]).status_code == 200


def test_default_setting_keeps_existing_publication_workflow(client):
    from app.config import get_settings

    assert get_settings().require_review_before_publish is False
    assert client.get("/api/health").json()["require_review_before_publish"] is False


def test_rubric_change_marks_evaluation_outdated_and_blocks_publication(client):
    t, s, a, sub = setup_flow(client)
    evaluate(client, t, sub)
    rubric = [dict(i) for i in QUESTION["rubric"]]
    rubric[1]["description"] = "Tokenization happens before all other preprocessing steps"
    client.patch(f"/api/questions/{a['question']['id']}", json={"rubric": rubric}, headers=t["headers"])

    review = client.get(f"/api/evaluations/submission/{sub['id']}", headers=t["headers"]).json()
    assert review["questions"][0]["evaluation"]["rubric_outdated"] is True
    r = client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"])
    assert r.status_code == 409 and r.json()["code"] == "rubric_outdated"

    batch = client.post(f"/api/evaluations/assessment/{a['id']}", params={"scope": "outdated"}, headers=t["headers"]).json()
    assert batch["evaluated_submissions"] == 1
    review = client.get(f"/api/evaluations/submission/{sub['id']}", headers=t["headers"]).json()
    ev = review["questions"][0]["evaluation"]
    assert ev["rubric_version"] == 2 and not ev["rubric_outdated"] and ev["version"] == 2
    assert client.post(f"/api/results/submission/{sub['id']}/publish", headers=t["headers"]).status_code == 200


def test_batch_evaluate_publish_and_analytics(client):
    t = register(client, "teacher")
    a = make_assessment(client, t)
    answers = [
        "Tokenisation means breaking text into tokens such as words or characters, it is the first step and later "
        "steps use the tokens. Tokenizers handle punctuation and contractions.",
        "A tokenizer must handle punctuation and contractions.",
        "Cricket is played with a bat and a ball by two teams of eleven players.",
    ]
    for text in answers:
        submit(client, register(client, "student"), a, text)
    r = client.post(f"/api/evaluations/assessment/{a['id']}", headers=t["headers"]).json()
    assert r == {"evaluated_submissions": 3, "skipped_submissions": 0, "evaluations_created": 3}
    again = client.post(f"/api/evaluations/assessment/{a['id']}", headers=t["headers"]).json()
    assert again["evaluated_submissions"] == 0

    stats = client.get(f"/api/analytics/assessment/{a['id']}", headers=t["headers"]).json()
    assert stats["basis"] == {"evaluated": 3, "published": 0}
    assert sum(b["count"] for b in stats["distribution"]) == 3
    q = stats["questions"][0]
    assert q["n"] == 3 and len(q["concepts"]) == 3
    assert all(c["matched"] + c["partial"] + c["missing"] == 3 for c in q["concepts"])

    pub = client.post(f"/api/results/assessment/{a['id']}/publish", json={}, headers=t["headers"]).json()
    assert pub["published_submissions"] == 3
    overview = client.get("/api/analytics/overview", headers=t["headers"]).json()
    assert overview["results_published"] == 3 and overview["average_published_percentage"] is not None
    page = client.get(f"/api/submissions?assessment_id={a['id']}", headers=t["headers"]).json()
    assert all(i["status"] == "published" for i in page["items"])


def test_test_answer_sandbox_does_not_persist(client, db):
    t = register(client, "teacher")
    a = make_assessment(client, t, publish=False)
    r = client.post(f"/api/questions/{a['question']['id']}/test-answer", json={"answer": "Tokens are words."},
                    headers=t["headers"])
    assert r.status_code == 200 and "concepts" in r.json()
    assert db.evaluations.count_documents({}) == 0


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
