import json
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError, require
from app.core.security import digest, seal, unseal
from app.db.models import Consultation, Doctor, History, Idempotency, Slot, now
from app.db.repositories import Repository
from app.modules.audit import emit, record
from app.modules.auth import aware

TRANSITIONS = {
    "BOOKED": {"CONFIRMED", "CANCELLED", "PAYMENT_FAILED", "EXPIRED"},
    "CONFIRMED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED"},
}


def transition(db, consultation, status, actor=None):
    require(status in TRANSITIONS.get(consultation.status, set()), "invalid_transition", 409)
    consultation.status = status
    if status in {"CANCELLED", "PAYMENT_FAILED", "EXPIRED"}:
        db.execute(
            update(Slot)
            .where(Slot.id == consultation.availability_slot_id)
            .values(status="AVAILABLE", version=Slot.version + 1)
        )
        if status == "CANCELLED":
            consultation.cancelled_at = now()
    db.add(History(consultation_id=consultation.id, status=status, actor_user_id=actor))
    record(db, actor, "consultation_" + status.lower(), "consultation", consultation.id)
    emit(db, "consultation_status", {"consultation_id": consultation.id, "status": status})


def consultation_view(value, medical=True):
    result = {
        "id": value.id,
        "patient_id": value.patient_id,
        "doctor_id": value.doctor_id,
        "availability_slot_id": value.availability_slot_id,
        "status": value.status,
        "scheduled_start": value.scheduled_start.isoformat(),
        "scheduled_end": value.scheduled_end.isoformat(),
    }
    if medical:
        result["reason_for_visit"] = unseal(value.reason_for_visit)
    return result


class ConsultationService:
    def __init__(self, repo: Repository):
        self.repo, self.db = repo, repo.db

    def authorized(self, user, identity, lock=False):
        consultation = self.repo.get(Consultation, identity, lock)
        doctor = self.repo.get(Doctor, consultation.doctor_id)
        require(
            consultation.patient_id == user.id
            or (doctor.user_id == user.id and doctor.verification_status == "VERIFIED"),
            "medical_record_forbidden",
        )
        return consultation

    def replay(self, user, key, fingerprint):
        row = self.db.scalar(
            select(Idempotency).where(
                Idempotency.principal == user.id,
                Idempotency.operation == "booking",
                Idempotency.key == key,
            )
        )
        if row:
            require(row.fingerprint == fingerprint, "idempotency_payload_mismatch", 409)
            return row.response
        return None

    def book(self, user, data, key):
        require(user.role == "PATIENT", "patient_required")
        require(key and 1 <= len(key) <= 128, "idempotency_key_required", 400)
        fingerprint = digest(json.dumps(data.model_dump(mode="json"), sort_keys=True))
        previous = self.replay(user, key, fingerprint)
        if previous is not None:
            return previous
        try:
            idem = self.repo.add(
                Idempotency(
                    principal=user.id,
                    operation="booking",
                    key=key,
                    fingerprint=fingerprint,
                    expires_at=now() + timedelta(hours=24),
                )
            )
            slot = self.repo.get(Slot, data.availability_slot_id)
            doctor = self.repo.get(Doctor, slot.doctor_id, True)
            require(doctor.verification_status == "VERIFIED", "doctor_unverified", 409)
            require(aware(slot.start_time) > now(), "slot_in_past", 409)
            require(doctor.user_id != user.id, "self_booking_forbidden")
            reserved = self.db.scalar(
                update(Slot)
                .where(Slot.id == slot.id, Slot.status == "AVAILABLE")
                .values(status="RESERVED", version=Slot.version + 1)
                .returning(Slot.id)
            )
            require(reserved is not None, "slot_conflict", 409)
            consultation = self.repo.add(
                Consultation(
                    patient_id=user.id,
                    doctor_id=doctor.id,
                    availability_slot_id=slot.id,
                    scheduled_start=slot.start_time,
                    scheduled_end=slot.end_time,
                    reason_for_visit=seal(data.reason_for_visit),
                )
            )
            self.db.add(
                History(consultation_id=consultation.id, status="BOOKED", actor_user_id=user.id)
            )
            record(self.db, user.id, "consultation_booked", "consultation", consultation.id)
            emit(self.db, "consultation_booked", {"consultation_id": consultation.id})
            # Persist no plaintext medical data in the idempotency table.
            result = consultation_view(consultation, medical=False)
            idem.response = result
            self.db.commit()
            return result
        except IntegrityError:
            self.db.rollback()
            previous = self.replay(user, key, fingerprint)
            if previous is not None:
                return previous
            raise DomainError(409, "booking_conflict") from None

    def get(self, user, identity):
        value = self.authorized(user, identity)
        record(self.db, user.id, "medical_record_read", "consultation", value.id)
        self.db.commit()
        return consultation_view(value)

    def listing(self, user, status, limit, cursor):
        stmt = select(Consultation)
        if user.role == "DOCTOR":
            doc = self.db.scalar(
                select(Doctor).where(
                    Doctor.user_id == user.id, Doctor.verification_status == "VERIFIED"
                )
            )
            if doc is None:
                raise DomainError(403, "doctor_required")
            stmt = stmt.where(Consultation.doctor_id == doc.id)
        else:
            stmt = stmt.where(Consultation.patient_id == user.id)
        if status:
            stmt = stmt.where(Consultation.status == status)
        if cursor:
            stmt = stmt.where(Consultation.id > cursor)
        rows = list(self.db.scalars(stmt.order_by(Consultation.id).limit(limit + 1)))
        record(self.db, user.id, "medical_history_read", "user", user.id)
        self.db.commit()
        return {
            "items": [consultation_view(row, False) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    def change(self, user, identity, status):
        value = self.authorized(user, identity, True)
        doctor = self.repo.get(Doctor, value.doctor_id)
        if status in {"IN_PROGRESS", "COMPLETED"}:
            require(doctor.user_id == user.id and user.role == "DOCTOR")
        elif status == "CONFIRMED":
            # Confirmation is exclusively driven by a verified successful payment.
            from app.db.models import Payment

            require(
                self.db.scalar(
                    select(Payment.id).where(
                        Payment.consultation_id == value.id, Payment.status == "SUCCEEDED"
                    )
                )
                is not None,
                "payment_required",
                409,
            )
            require(doctor.user_id == user.id)
        if status == "IN_PROGRESS":
            require(
                aware(value.scheduled_start) <= now() <= aware(value.scheduled_end),
                "outside_consultation_window",
                409,
            )
        if status == "CANCELLED" and value.patient_id == user.id:
            require(
                aware(value.scheduled_start) > now() + timedelta(hours=2),
                "cancellation_window_closed",
                409,
            )
        if status == "CANCELLED":
            require(aware(value.scheduled_start) > now(), "consultation_already_started", 409)
        transition(self.db, value, status, user.id)
        if status == "CANCELLED":
            from app.db.models import Payment

            payment = self.db.scalar(
                select(Payment).where(Payment.consultation_id == value.id).with_for_update()
            )
            if payment and payment.status == "SUCCEEDED":
                payment.status = "REFUND_PENDING"
                emit(self.db, "payment_refund", {"payment_id": payment.id})
        self.db.commit()
        return consultation_view(value, False)
