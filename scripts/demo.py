"""Exercise the HTTP workflow using synthetic credentials from seed_demo."""

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import settings


def run():
    data = json.loads(Path("artifacts/demo.json").read_text())
    with httpx.Client(
        base_url=os.getenv("BASE_URL", "http://127.0.0.1:8000"), timeout=10
    ) as client:
        patient = {
            "Authorization": "Bearer " + data["patient_token"],
            "Idempotency-Key": str(uuid4()),
        }
        payload = {
            "availability_slot_id": data["slots"][0],
            "reason_for_visit": "Synthetic demo only",
        }
        booked = client.post("/api/v1/consultations", json=payload, headers=patient)
        booked.raise_for_status()
        replay = client.post("/api/v1/consultations", json=payload, headers=patient)
        assert replay.json() == booked.json()
        conflict = client.post(
            "/api/v1/consultations",
            json=payload,
            headers={**patient, "Idempotency-Key": str(uuid4())},
        )
        assert conflict.status_code == 409
        identity = booked.json()["id"]
        payment = client.post(
            "/api/v1/payments", json={"consultation_id": identity}, headers=patient
        )
        payment.raise_for_status()
        event = {
            "event_id": str(uuid4()),
            "reference": payment.json()["provider_reference"],
            "amount": payment.json()["amount"],
            "currency": "INR",
            "status": "SUCCEEDED",
            "timestamp": int(time.time()),
        }
        body = json.dumps(event).encode()
        signature = hmac.new(settings().webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        result = client.post(
            "/api/v1/payments/webhooks/mock",
            content=body,
            headers={"X-Signature": signature, "Content-Type": "application/json"},
        )
        result.raise_for_status()
        assert (
            client.get(f"/api/v1/consultations/{identity}", headers=patient).json()["status"]
            == "CONFIRMED"
        )
        admin = {"Authorization": "Bearer " + data["admin_token"]}
        client.get("/api/v1/admin/analytics/overview", headers=admin).raise_for_status()
        print(
            "PASS: booking, idempotent replay, slot conflict, signed mock payment, confirmation, admin analytics"
        )
        print(
            "Clinical lifecycle and prescription issuance are demonstrated by tests/api/test_workflows.py"
        )


if __name__ == "__main__":
    run()
