import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import unseal
from app.db.models import Outbox


def test_registration_rotation_reuse(client):
    registration = {
        "email": "New@Example.com",
        "password": "a-long-test-password",
        "full_name": "New User",
    }
    assert (
        client.post("/api/v1/auth/register", json={**registration, "role": "ADMIN"}).status_code
        == 422
    )
    response = client.post("/api/v1/auth/register", json=registration)
    assert response.status_code == 201, response.text
    assert response.json()["email"] == "new@example.com"
    assert client.post("/api/v1/auth/register", json=registration).status_code == 409
    login = client.post(
        "/api/v1/auth/login",
        json={"email": registration["email"], "password": registration["password"]},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()
    assert "access_token" in rotated
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer " + rotated["access_token"]}
        ).status_code
        == 401
    )


def test_mfa_enrollment_recovery_and_logout(client, actors):
    headers = actors["patient"]["headers"]
    result = client.post("/api/v1/auth/mfa/enroll", headers=headers)
    assert result.status_code == 200
    secret = result.json()["secret"]
    assert (
        client.post(
            "/api/v1/auth/mfa/verify", headers=headers, json={"code": "invalid-code"}
        ).status_code
        == 401
    )
    verified = client.post(
        "/api/v1/auth/mfa/verify", headers=headers, json={"code": pyotp.TOTP(secret).now()}
    )
    assert verified.status_code == 200, verified.text
    auth = {"email": "patient@example.com", "password": "a-long-test-password"}
    assert client.post("/api/v1/auth/login", json=auth).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={**auth, "mfa_code": pyotp.TOTP(secret).now()}
        ).status_code
        == 401
    )
    recovery = verified.json()["recovery_codes"][0]
    login = client.post("/api/v1/auth/login", json={**auth, "mfa_code": recovery})
    assert login.status_code == 200, login.text
    assert client.post("/api/v1/auth/login", json={**auth, "mfa_code": recovery}).status_code == 401
    tokens = login.json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    assert (
        client.post(
            "/api/v1/auth/logout", headers=headers, json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_password_reset_generic_response(client, actors, database):
    existing = client.post("/api/v1/auth/password/forgot", json={"email": "patient@example.com"})
    absent = client.post("/api/v1/auth/password/forgot", json={"email": "absent@example.com"})
    assert existing.json() == absent.json()
    with Session(database) as db:
        event = db.scalar(select(Outbox).where(Outbox.topic == "password_reset"))
        token = unseal(event.payload["secret"])
    data = {"token": token, "password": "a-new-long-password"}
    assert client.post("/api/v1/auth/password/reset", json=data).status_code == 200
    assert client.post("/api/v1/auth/password/reset", json=data).status_code == 400
    assert client.get("/api/v1/users/me", headers=actors["patient"]["headers"]).status_code == 401
