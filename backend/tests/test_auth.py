from app.config import get_settings
from tests.conftest import PASSWORD, register


def test_register_login_and_me(client, db):
    t = register(client, "teacher", email="Mixed.Case@Example.COM")
    assert t["user"]["email"] == "mixed.case@example.com"  # normalised
    stored = db.users.find_one({"email": "mixed.case@example.com"})
    assert stored["password_hash"] != PASSWORD and stored["password_hash"].startswith("$2")
    assert "password" not in stored

    r = client.post("/api/auth/login", json={"email": "MIXED.case@example.com", "password": PASSWORD})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "teacher" and "password_hash" not in me


def test_duplicate_email_conflict(client):
    register(client, "student", email="dup@example.com")
    r = client.post("/api/auth/register", json={"name": "Other", "email": "DUP@example.com", "password": PASSWORD, "role": "teacher"})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"


def test_registration_validation(client):
    base = {"name": "Valid Name", "email": "v@example.com", "password": PASSWORD, "role": "student"}
    cases = [
        ({"password": "short1"}, "password"),
        ({"password": "onlyletters"}, "password"),
        ({"email": "not-an-email"}, "email"),
        ({"role": "admin"}, "role"),
        ({"name": " "}, "name"),
    ]
    for override, field in cases:
        r = client.post("/api/auth/register", json={**base, **override})
        assert r.status_code == 422, override
        body = r.json()
        assert body["code"] == "validation_error" and any(e["field"] == field for e in body["errors"])
    # unknown fields (e.g. trying to smuggle a role-like attribute) are rejected
    r = client.post("/api/auth/register", json={**base, "is_admin": True})
    assert r.status_code == 422


def test_login_failures_are_generic(client):
    register(client, "student", email="s1@example.com")
    wrong_pw = client.post("/api/auth/login", json={"email": "s1@example.com", "password": "Wrong1234"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong1234"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]


def test_protected_routes_need_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/assessments").status_code == 401


def test_role_comes_from_database_not_from_request(client, db):
    s = register(client, "student")
    # Even if the database role is the only source of truth, a student token cannot act as teacher.
    r = client.post("/api/assessments", json={"title": "Hack", "subject": "NLP"}, headers=s["headers"])
    assert r.status_code == 403
    # Promoting the user in the DB is reflected immediately (role is re-read per request).
    db.users.update_one({"email": s["email"]}, {"$set": {"role": "teacher"}})
    r = client.post("/api/assessments", json={"title": "Now allowed", "subject": "NLP"}, headers=s["headers"])
    assert r.status_code == 201


def test_teacher_invite_code(client):
    settings = get_settings()
    settings.teacher_invite_code = "secret-code"
    try:
        body = {"name": "New Teacher", "email": "nt@example.com", "password": PASSWORD, "role": "teacher"}
        assert client.post("/api/auth/register", json=body).status_code == 403
        assert client.post("/api/auth/register", json={**body, "invite_code": "wrong"}).status_code == 403
        assert client.post("/api/auth/register", json={**body, "invite_code": "secret-code"}).status_code == 201
        # students never need a code
        assert client.post("/api/auth/register", json={**body, "email": "st@example.com", "role": "student"}).status_code == 201
    finally:
        settings.teacher_invite_code = ""


def test_profile_and_password_change(client):
    s = register(client, "student", email="pw@example.com")
    r = client.patch("/api/auth/me", json={"name": "Renamed Student"}, headers=s["headers"])
    assert r.status_code == 200 and r.json()["name"] == "Renamed Student"
    bad = client.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "NewPassw0rd"},
                      headers=s["headers"])
    assert bad.status_code == 403
    ok = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "NewPassw0rd"},
                     headers=s["headers"])
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"email": "pw@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "pw@example.com", "password": "NewPassw0rd"}).status_code == 200
