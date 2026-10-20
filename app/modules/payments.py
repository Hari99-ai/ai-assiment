import hashlib
import hmac
import time
from typing import Protocol

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import DomainError, require
from app.core.security import digest
from app.db.models import Consultation, Doctor, Payment, Webhook
from app.db.repositories import Repository
from app.modules.audit import emit, record
from app.modules.consultations import transition
from app.modules.schemas import PaymentEvent


class PaymentProvider(Protocol):
    def create(self, identity: str, amount: str) -> str: ...
    def status(self, reference: str) -> str: ...
    def refund(self, reference: str) -> str: ...
    def verify(self, body: bytes, signature: str) -> bool: ...


class MockProvider:
    """No card collection or real money movement. Webhooks simulate settlement."""

    def create(self, identity, amount):
        return "mock_" + identity

    def status(self, reference):
        return "PENDING"

    def refund(self, reference):
        return "REFUNDED"

    def verify(self, body, signature):
        expected = hmac.new(settings().webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def view(value):
    return {
        "id": value.id,
        "consultation_id": value.consultation_id,
        "amount": str(value.amount),
        "currency": value.currency,
        "status": value.status,
        "provider": value.provider,
        "provider_reference": value.provider_reference,
    }


class PaymentService:
    def __init__(self, repo: Repository, provider: PaymentProvider):
        self.repo, self.db, self.provider = repo, repo.db, provider

    def create(self, user, identity):
        consultation = self.repo.get(Consultation, identity, True)
        require(consultation.patient_id == user.id)
        old = self.db.scalar(select(Payment).where(Payment.consultation_id == consultation.id))
        if old:
            return view(old)
        require(consultation.status == "BOOKED", "invalid_transition", 409)
        doctor = self.repo.get(Doctor, consultation.doctor_id)
        payment = self.repo.add(
            Payment(
                consultation_id=consultation.id,
                patient_id=user.id,
                amount=doctor.consultation_fee,
                provider_reference="mock_" + consultation.id,
            )
        )
        emit(self.db, "payment_create", {"payment_id": payment.id})
        record(self.db, user.id, "payment_create", "payment", payment.id)
        self.db.commit()
        return view(payment)

    def get(self, user, identity):
        payment = self.repo.get(Payment, identity)
        require(payment.patient_id == user.id)
        return view(payment)

    def webhook(self, body, signature):
        require(self.provider.verify(body, signature), "invalid_signature", 401)
        event = PaymentEvent.model_validate_json(body)
        require(abs(time.time() - event.timestamp) <= 300, "stale_webhook", 400)
        payment = self.db.scalar(
            select(Payment).where(Payment.provider_reference == event.reference)
        )
        if payment is None:
            raise DomainError(404, "payment_not_found")
        # Global lock order: consultation before payment, matching cancellation/refund.
        consultation = self.repo.get(Consultation, payment.consultation_id, True)
        payment = self.repo.get(Payment, payment.id, True)
        old = self.db.scalar(select(Webhook).where(Webhook.provider_event_id == event.event_id))
        if old:
            require(old.fingerprint == digest(body.decode()), "webhook_payload_mismatch", 409)
            return {"duplicate": True}
        require(
            payment.provider == "mock"
            and payment.amount == event.amount
            and payment.currency == event.currency,
            "payment_details_mismatch",
            400,
        )
        self.repo.add(Webhook(provider_event_id=event.event_id, fingerprint=digest(body.decode())))
        if payment.status in {"SUCCEEDED", "REFUNDED", "REFUND_PENDING", "FAILED"}:
            require(
                payment.status == event.status
                or (payment.status == "REFUND_PENDING" and event.status == "REFUNDED"),
                "invalid_payment_transition",
                409,
            )
        else:
            require(event.status in {"SUCCEEDED", "FAILED"}, "invalid_payment_transition", 409)
        payment.status = event.status
        if event.status == "SUCCEEDED":
            if consultation.status == "BOOKED":
                transition(self.db, consultation, "CONFIRMED")
            elif consultation.status in {"CANCELLED", "EXPIRED", "PAYMENT_FAILED"}:
                payment.status = "REFUND_PENDING"
                emit(self.db, "payment_refund", {"payment_id": payment.id})
        elif event.status == "FAILED" and consultation.status == "BOOKED":
            transition(self.db, consultation, "PAYMENT_FAILED")
        record(self.db, None, "payment_" + payment.status.lower(), "payment", payment.id)
        self.db.commit()
        return {"duplicate": False, "status": payment.status}
