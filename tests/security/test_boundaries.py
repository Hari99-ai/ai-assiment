import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Audit, Consultation, Idempotency, Slot, now
from app.workers.tasks import consume_event


def send(client, event):
    body = json.dumps(event).encode()
    signature = hmac.new(settings().webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/payments/webhooks/mock", content=body, headers={"X-Signature": signature}
    )


def test_failure_after_reservation_rolls_back(client, actors, database, booking):
    with patch(
        "app.modules.consultations.emit", side_effect=RuntimeError("simulated persistence failure")
    ):
        assert booking().status_code == 500
    with Session(database) as db:
        assert db.get(Slot, actors["slot_id"]).status == "AVAILABLE"
        assert db.scalar(select(func.count()).select_from(Consultation)) == 0
        assert db.scalar(select(func.count()).select_from(Idempotency)) == 0
        assert db.scalar(select(func.count()).select_from(Audit)) == 0
    assert booking().status_code == 201


def test_doctor_application_verification_and_profiles(client, actors, database):
    patient = actors["patient"]["headers"]
    data = {
        "license_number": "SYNTHETIC-123",
        "specialization": "Ayurveda",
        "qualifications": "Demo",
        "consultation_fee": "700.00",
        "experience_years": 3,
    }
    application = client.post("/api/v1/doctors", headers=patient, json=data)
    assert application.status_code == 201, application.text
    doctor_id = application.json()["id"]
    interval = {
        "start_time": (now() + timedelta(days=2)).isoformat(),
        "end_time": (now() + timedelta(days=2, minutes=30)).isoformat(),
    }
    assert (
        client.post(
            f"/api/v1/doctors/{doctor_id}/availability", headers=patient, json=interval
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/admin/doctors/{doctor_id}/verify",
            headers=patient,
            json={"status": "VERIFIED"},
        ).status_code
        == 403
    )
    admin = actors["admin"]["headers"]
    assert (
        client.get(f"/api/v1/admin/doctors/{doctor_id}/credentials", headers=admin).json()[
            "license_number"
        ]
        == "SYNTHETIC-123"
    )
    assert (
        client.post(
            f"/api/v1/admin/doctors/{doctor_id}/verify", headers=admin, json={"status": "VERIFIED"}
        ).status_code
        == 200
    )
    slot = client.post(f"/api/v1/doctors/{doctor_id}/availability", headers=patient, json=interval)
    assert slot.status_code == 201, slot.text
    assert (
        client.delete(
            f"/api/v1/doctors/{doctor_id}/availability/{slot.json()['id']}", headers=patient
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/doctors/{doctor_id}", headers=patient, json={"consultation_fee": "750.00"}
        ).status_code
        == 200
    )
    assert (
        client.patch("/api/v1/users/me", headers=patient, json={"full_name": "Updated"}).json()[
            "full_name"
        ]
        == "Updated"
    )
    assert client.get("/api/v1/users/me", headers=patient).json()["role"] == "DOCTOR"
    assert "license_number" not in client.get(f"/api/v1/doctors/{doctor_id}").json()


def test_reserved_slot_cannot_be_deleted(client, actors, booking):
    booking()
    response = client.delete(
        f"/api/v1/doctors/{actors['doctor_id']}/availability/{actors['slot_id']}",
        headers=actors["doctor"]["headers"],
    )
    assert response.status_code == 409
    assert client.get("/api/v1/consultations?limit=1", headers=actors["doctor"]["headers"]).json()[
        "items"
    ]
    assert (
        client.get("/api/v1/consultations?limit=1", headers=actors["other"]["headers"]).json()[
            "items"
        ]
        == []
    )


def test_webhook_validation_and_mock_refund(client, actors, booking, database):
    identity = booking().json()["id"]
    patient = actors["patient"]["headers"]
    payment = client.post(
        "/api/v1/payments", headers=patient, json={"consultation_id": identity}
    ).json()
    event = {
        "event_id": "payment-1",
        "reference": payment["provider_reference"],
        "amount": "500.00",
        "currency": "INR",
        "status": "SUCCEEDED",
        "timestamp": int(time.time()),
    }
    assert send(client, {**event, "timestamp": int(time.time()) - 600}).status_code == 400
    assert send(client, {**event, "amount": "1.00"}).status_code == 400
    assert send(client, event).status_code == 200
    assert (
        client.post(f"/api/v1/consultations/{identity}/cancel", headers=patient).status_code == 200
    )
    from app.db.models import Outbox

    with Session(database) as db:
        refund = db.scalar(select(Outbox.id).where(Outbox.topic == "payment_refund"))
    with patch("app.workers.tasks.session", lambda: Session(database, expire_on_commit=False)):
        consume_event.run(refund)
        assert consume_event.run(refund) == "duplicate"
    assert (
        client.get(f"/api/v1/payments/{payment['id']}", headers=patient).json()["status"]
        == "REFUNDED"
    )
    assert (
        client.get(
            f"/api/v1/payments/{payment['id']}", headers=actors["other"]["headers"]
        ).status_code
        == 403
    )


def test_payment_failure_releases_slot(client, actors, booking):
    identity = booking().json()["id"]
    payment = client.post(
        "/api/v1/payments", headers=actors["patient"]["headers"], json={"consultation_id": identity}
    ).json()
    event = {
        "event_id": "failed-1",
        "reference": payment["provider_reference"],
        "amount": "500.00",
        "currency": "INR",
        "status": "FAILED",
        "timestamp": int(time.time()),
    }
    assert send(client, event).status_code == 200
    assert booking(actor="other", key="after-failure").status_code == 201


def test_invalid_login_and_audit(client, actors, database):
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "patient@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "absent@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    with Session(database) as db:
        assert len(db.scalars(select(Audit).where(Audit.outcome == "failure")).all()) == 2


def test_readiness_and_metrics(client):
    assert client.get("/health/ready").status_code == 200
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "amrutam_http_requests_total" in metrics.text


def test_expired_token_and_bounded_body(client, actors):
    from datetime import UTC, datetime

    import jwt

    payload = {
        "sub": actors["patient"]["user"].id,
        "sid": "unused",
        "mfa": False,
        "iss": "amrutam",
        "aud": "amrutam-api",
        "iat": datetime.now(UTC) - timedelta(minutes=2),
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    token = jwt.encode(payload, settings().jwt_secret, algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )
    assert client.get("/unknown").json()["error"]["code"] == "not_found"
    assert client.post("/api/v1/auth/login", content=b"x" * 65537).status_code == 413

    def chunks():
        yield b"x" * 32768
        yield b"x" * 32769

    assert client.post("/api/v1/auth/login", content=chunks()).status_code == 413
