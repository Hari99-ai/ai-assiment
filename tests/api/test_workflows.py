import hashlib
import hmac
import json
import time
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Consultation,
    Doctor,
    Idempotency,
    Outbox,
    Prescription,
    Slot,
    now,
)


def signed(client, event):
    body = json.dumps(event).encode()
    signature = hmac.new(settings().webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/payments/webhooks/mock",
        content=body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )


def test_booking_isolation_and_idempotency(client, actors, booking, database):
    response = booking()
    assert response.status_code == 201, response.text
    assert booking().json() == response.json()
    assert booking(reason="Different").status_code == 409
    assert booking(actor="other", key="other").status_code == 409
    identity = response.json()["id"]
    assert (
        client.get(
            f"/api/v1/consultations/{identity}", headers=actors["other"]["headers"]
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/consultations/{identity}", headers=actors["admin"]["headers"]
        ).status_code
        == 403
    )
    result = client.get(f"/api/v1/consultations/{identity}", headers=actors["patient"]["headers"])
    assert result.json()["reason_for_visit"] == "Consultation"
    assert (
        client.post(
            f"/api/v1/consultations/{identity}/complete", headers=actors["doctor"]["headers"]
        ).status_code
        == 409
    )
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Consultation)) == 1
        assert db.scalar(select(func.count()).select_from(Idempotency)) == 1
        assert db.scalar(select(Consultation)).reason_for_visit != "Consultation"
        assert db.scalar(select(Outbox)).topic == "consultation_booked"


def test_cancellation_releases_slot(client, actors, booking):
    identity = booking().json()["id"]
    assert (
        client.post(
            f"/api/v1/consultations/{identity}/cancel", headers=actors["patient"]["headers"]
        ).status_code
        == 200
    )
    assert booking(actor="other", key="new").status_code == 201


def test_unverified_and_rollback(client, actors, booking, database):
    with Session(database) as db:
        db.get(Doctor, actors["doctor_id"]).verification_status = "PENDING"
        db.commit()
    assert booking().status_code == 409
    with Session(database) as db:
        assert db.get(Slot, actors["slot_id"]).status == "AVAILABLE"
        assert db.scalar(select(func.count()).select_from(Idempotency)) == 0
        assert db.scalar(select(func.count()).select_from(Consultation)) == 0


def test_payments_prescriptions(client, actors, booking, database):
    identity = booking().json()["id"]
    patient, doctor = actors["patient"]["headers"], actors["doctor"]["headers"]
    request = {"consultation_id": identity}
    payment = client.post("/api/v1/payments", headers=patient, json=request)
    assert payment.status_code == 201, payment.text
    assert client.post("/api/v1/payments", headers=patient, json=request).json() == payment.json()
    event = {
        "event_id": "evt-1",
        "reference": payment.json()["provider_reference"],
        "amount": "500.00",
        "currency": "INR",
        "status": "SUCCEEDED",
        "timestamp": int(time.time()),
    }
    assert (
        client.post(
            "/api/v1/payments/webhooks/mock", json=event, headers={"X-Signature": "invalid"}
        ).status_code
        == 401
    )
    assert signed(client, event).status_code == 200
    assert signed(client, event).json()["duplicate"] is True
    assert signed(client, {**event, "amount": "1.00"}).status_code == 409
    medication = {
        "medications": [
            {
                "name": "Demo medicine",
                "dosage": "Clinician supplied",
                "instructions": "Demo only",
                "duration_days": 3,
            }
        ]
    }
    assert (
        client.post(
            f"/api/v1/consultations/{identity}/prescriptions", json=medication, headers=patient
        ).status_code
        == 403
    )
    assert client.post(f"/api/v1/consultations/{identity}/start", headers=doctor).status_code == 409
    with Session(database) as db:
        consultation = db.get(Consultation, identity)
        consultation.scheduled_start = now() - timedelta(minutes=5)
        consultation.scheduled_end = now() + timedelta(minutes=25)
        db.commit()
    assert client.post(f"/api/v1/consultations/{identity}/start", headers=doctor).status_code == 200
    assert (
        client.post(f"/api/v1/consultations/{identity}/complete", headers=doctor).status_code == 200
    )
    prescription = client.post(
        f"/api/v1/consultations/{identity}/prescriptions", json=medication, headers=doctor
    )
    assert prescription.status_code == 201, prescription.text
    pid = prescription.json()["id"]
    assert (
        client.post(
            f"/api/v1/prescriptions/{pid}/revisions", headers=doctor, json=medication
        ).json()["version"]
        == 2
    )
    assert len(client.get(f"/api/v1/prescriptions/{pid}", headers=patient).json()["revisions"]) == 2
    assert (
        client.get(f"/api/v1/prescriptions/{pid}", headers=actors["other"]["headers"]).status_code
        == 403
    )
    with Session(database) as db:
        assert "Demo medicine" not in db.get(Prescription, pid).prescription_data


def test_availability_search_authorization(client, actors):
    doctor_id = actors["doctor_id"]
    assert (
        client.get("/api/v1/doctors?specialization=Ayurveda").json()["items"][0]["id"] == doctor_id
    )
    assert client.get("/api/v1/doctors?min_fee=600").json()["items"] == []
    assert client.get("/api/v1/doctors?limit=101").status_code == 422
    interval = {
        "start_time": (now() + timedelta(days=1, minutes=1)).isoformat(),
        "end_time": (now() + timedelta(days=1, minutes=31)).isoformat(),
    }
    assert (
        client.post(
            f"/api/v1/doctors/{doctor_id}/availability",
            json=interval,
            headers=actors["doctor"]["headers"],
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/doctors/{doctor_id}",
            json={"consultation_fee": 100},
            headers=actors["patient"]["headers"],
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/admin/analytics/overview", headers=actors["patient"]["headers"]
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/admin/analytics/overview", headers=actors["admin"]["headers"]
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/admin/analytics/overview", headers=actors["support"]["headers"]
        ).status_code
        == 403
    )


def test_headers_and_validation(client):
    result = client.get("/health/live")
    assert result.status_code == 200
    assert result.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/v1/users/me").status_code == 401
    result = client.post("/api/v1/auth/register", json={"email": "bad", "password": "sensitive"})
    assert result.status_code == 422
    assert "sensitive" not in result.text
    assert client.get("/openapi.json").status_code == 200
