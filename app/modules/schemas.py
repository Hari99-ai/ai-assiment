from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Password = Annotated[str, Field(min_length=12, max_length=128)]
Name = Annotated[str, Field(min_length=1, max_length=150)]


class Register(Input):
    email: EmailStr
    password: Password
    full_name: Name


class Login(Input):
    email: EmailStr
    password: str = Field(max_length=128)
    mfa_code: str | None = Field(default=None, max_length=100)


class Token(Input):
    refresh_token: str = Field(min_length=1, max_length=200)


class MFA(Input):
    code: str = Field(min_length=6, max_length=100)


class Forgot(Input):
    email: EmailStr


class ResetPassword(Input):
    token: str = Field(max_length=200)
    password: Password


class ProfilePatch(Input):
    full_name: Name


class DoctorCreate(Input):
    license_number: str = Field(min_length=3, max_length=100)
    specialization: str = Field(min_length=2, max_length=100)
    qualifications: str = Field(min_length=2, max_length=1000)
    consultation_fee: Decimal = Field(ge=0, le=100000, decimal_places=2)
    experience_years: int = Field(ge=0, le=80)


class DoctorPatch(Input):
    specialization: str | None = Field(default=None, min_length=2, max_length=100)
    consultation_fee: Decimal | None = Field(default=None, ge=0, le=100000, decimal_places=2)

    @model_validator(mode="after")
    def nonnull(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Explicit null is not supported")
        return self


class Verification(Input):
    status: Literal["VERIFIED", "REJECTED"]


class SlotCreate(Input):
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone offset is required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def interval(self):
        if self.end_time <= self.start_time or self.start_time <= datetime.now(UTC):
            raise ValueError("Provide a future, positive interval")
        if (self.end_time - self.start_time).total_seconds() > 14400:
            raise ValueError("Maximum slot duration is four hours")
        return self


class Booking(Input):
    availability_slot_id: UUID
    reason_for_visit: str = Field(min_length=1, max_length=4000)


class Medication(Input):
    name: str = Field(min_length=1, max_length=150)
    dosage: str = Field(min_length=1, max_length=150)
    instructions: str = Field(min_length=1, max_length=1000)
    duration_days: int = Field(ge=1, le=365)


class PrescriptionInput(Input):
    medications: list[Medication] = Field(min_length=1, max_length=30)
    notes: str = Field(default="", max_length=2000)


class PaymentInput(Input):
    consultation_id: UUID


class PaymentEvent(Input):
    event_id: str = Field(min_length=1, max_length=100)
    reference: str = Field(min_length=1, max_length=100)
    status: Literal["SUCCEEDED", "FAILED", "REFUNDED"]
    amount: Decimal = Field(ge=0, decimal_places=2)
    currency: Literal["INR"]
    timestamp: int
