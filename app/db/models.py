from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="PATIENT")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_counter: Mapped[int] = mapped_column(Integer, default=-1)
    recovery_hashes: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    __table_args__ = (CheckConstraint("role IN ('PATIENT','DOCTOR','ADMIN','SUPPORT')"),)


class Profile(Entity, Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    profile_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class Refresh(Entity, Base):
    __tablename__ = "refresh_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa: Mapped[bool] = mapped_column(Boolean, default=False)


class Reset(Entity, Base):
    __tablename__ = "password_resets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Doctor(Entity, Base):
    __tablename__ = "doctors"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    license_number: Mapped[str] = mapped_column(Text)
    specialization: Mapped[str] = mapped_column(String(100), index=True)
    qualifications: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    consultation_fee: Mapped[float] = mapped_column(Numeric(10, 2))
    experience_years: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("consultation_fee >= 0 AND experience_years >= 0"),)


class Slot(Entity, Base):
    __tablename__ = "availability_slots"
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("end_time > start_time"),
        CheckConstraint("status IN ('AVAILABLE','RESERVED','CLOSED')"),
        Index("ix_doctor_schedule", "doctor_id", "start_time", "end_time"),
    )


class Consultation(Entity, Base):
    __tablename__ = "consultations"
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    availability_slot_id: Mapped[str] = mapped_column(ForeignKey("availability_slots.id"))
    status: Mapped[str] = mapped_column(String(20), default="BOOKED", index=True)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason_for_visit: Mapped[str] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_patient_history", "patient_id", "created_at", "id"),
        Index("ix_doctor_consultations", "doctor_id", "scheduled_start"),
        CheckConstraint(
            "status IN ('BOOKED','CONFIRMED','IN_PROGRESS','COMPLETED','CANCELLED','PAYMENT_FAILED','EXPIRED')"
        ),
        Index(
            "uq_active_slot",
            "availability_slot_id",
            unique=True,
            postgresql_where=__import__("sqlalchemy").text(
                "status IN ('BOOKED','CONFIRMED','IN_PROGRESS','COMPLETED')"
            ),
            sqlite_where=__import__("sqlalchemy").text(
                "status IN ('BOOKED','CONFIRMED','IN_PROGRESS','COMPLETED')"
            ),
        ),
    )


class History(Entity, Base):
    __tablename__ = "consultation_history"
    consultation_id: Mapped[str] = mapped_column(ForeignKey("consultations.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Prescription(Entity, Base):
    __tablename__ = "prescriptions"
    consultation_id: Mapped[str] = mapped_column(ForeignKey("consultations.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    prescription_data: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Revision(Entity, Base):
    __tablename__ = "prescription_revisions"
    prescription_id: Mapped[str] = mapped_column(ForeignKey("prescriptions.id"))
    version: Mapped[int] = mapped_column(Integer)
    prescription_data: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("prescription_id", "version"),)


class Payment(Entity, Base):
    __tablename__ = "payments"
    consultation_id: Mapped[str] = mapped_column(ForeignKey("consultations.id"), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    provider: Mapped[str] = mapped_column(String(20), default="mock")
    provider_reference: Mapped[str] = mapped_column(String(100), unique=True)
    __table_args__ = (CheckConstraint("amount >= 0"),)


class Webhook(Entity, Base):
    __tablename__ = "payment_webhooks"
    provider_event_id: Mapped[str] = mapped_column(String(100), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class Idempotency(Entity, Base):
    __tablename__ = "idempotency_records"
    principal: Mapped[str] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("principal", "operation", "key"),)


class Audit(Entity, Base):
    __tablename__ = "audit_logs"
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(100))
    request_id: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Outbox(Entity, Base):
    __tablename__ = "outbox_events"
    topic: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Notification(Entity, Base):
    __tablename__ = "notification_jobs"
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    payload: Mapped[dict] = mapped_column(JSON)
