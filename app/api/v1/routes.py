from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.core.errors import require
from app.core.redis import cached_public, rate_limit
from app.db.models import Doctor
from app.db.models import User as UserModel
from app.db.repositories import Repository
from app.dependencies import admin_user, current_user, protected_user, repository
from app.modules import schemas as s
from app.modules.analytics import AnalyticsService
from app.modules.auth import AuthService
from app.modules.consultations import ConsultationService
from app.modules.doctors import DoctorService, public_doctor
from app.modules.payments import MockProvider, PaymentService
from app.modules.prescriptions import PrescriptionService

router = APIRouter(prefix="/api/v1")
Repo = Annotated[Repository, Depends(repository)]
User = Annotated[UserModel, Depends(protected_user)]
Admin = Annotated[UserModel, Depends(admin_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]


def auth_limit(request: Request):
    rate_limit(request.client.host if request.client else "unknown")


auth = APIRouter(prefix="/auth", tags=["Identity"], dependencies=[Depends(auth_limit)])


@auth.post("/register", status_code=201)
def register(data: s.Register, repo: Repo):
    return AuthService(repo).register(data)


@auth.post("/login")
def login(data: s.Login, repo: Repo):
    return AuthService(repo).login(data)


@auth.post("/refresh")
def refresh(data: s.Token, repo: Repo):
    return AuthService(repo).refresh(data.refresh_token)


@auth.post("/logout")
def logout(data: s.Token, repo: Repo, user=Depends(current_user)):
    return AuthService(repo).logout(user, data.refresh_token)


@auth.post("/mfa/enroll")
def enroll(repo: Repo, user=Depends(current_user)):
    return AuthService(repo).enroll(user)


@auth.post("/mfa/verify")
def verify(data: s.MFA, repo: Repo, user=Depends(current_user)):
    return AuthService(repo).verify(user, data.code)


@auth.post("/password/forgot")
def forgot(data: s.Forgot, repo: Repo):
    return AuthService(repo).forgot(data.email)


@auth.post("/password/reset")
def reset(data: s.ResetPassword, repo: Repo):
    return AuthService(repo).reset(data)


router.include_router(auth)


@router.get("/users/me", tags=["Profiles"])
def me(user: User, repo: Repo):
    from app.modules.users import UserService

    return UserService(repo).get(user)


@router.patch("/users/me", tags=["Profiles"])
def update_me(data: s.ProfilePatch, user: User, repo: Repo):
    from app.modules.users import UserService

    return UserService(repo).patch(user, data)


@router.get("/doctors", tags=["Doctors"])
def doctors(
    repo: Repo,
    specialization: str | None = Query(None, max_length=100),
    min_fee: float | None = Query(None, ge=0),
    max_fee: float | None = Query(None, ge=0),
    available_after: datetime | None = None,
    available_before: datetime | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return DoctorService(repo).search(
        specialization, min_fee, max_fee, available_after, available_before, limit, offset
    )


@router.get("/doctors/{doctor_id}", tags=["Doctors"])
def doctor(doctor_id: UUID, repo: Repo):
    return cached_public(
        "doctor:" + str(doctor_id), lambda: public_doctor(repo.get(Doctor, doctor_id))
    )


@router.post("/doctors", status_code=201, tags=["Doctors"])
def create_doctor(data: s.DoctorCreate, user: User, repo: Repo):
    return DoctorService(repo).create(user, data)


@router.patch("/doctors/{doctor_id}", tags=["Doctors"])
def patch_doctor(doctor_id: UUID, data: s.DoctorPatch, user: User, repo: Repo):
    return DoctorService(repo).patch(user, doctor_id, data)


@router.post("/admin/doctors/{doctor_id}/verify", tags=["Administration"])
def verify_doctor(doctor_id: UUID, data: s.Verification, user: Admin, repo: Repo):
    return DoctorService(repo).verify(user, doctor_id, data.status)


@router.get("/admin/doctors/{doctor_id}/credentials", tags=["Administration"])
def credentials(doctor_id: UUID, user: Admin, repo: Repo):
    from app.modules.users import UserService

    return UserService(repo).credentials(user, doctor_id)


@router.post("/doctors/{doctor_id}/availability", status_code=201, tags=["Availability"])
def add_slot(doctor_id: UUID, data: s.SlotCreate, user: User, repo: Repo):
    return DoctorService(repo).add_slot(user, doctor_id, data)


@router.get("/doctors/{doctor_id}/availability", tags=["Availability"])
def slots(doctor_id: UUID, repo: Repo, limit: Limit = 20, offset: Offset = 0):
    from app.modules.users import UserService

    return UserService(repo).slots(doctor_id, limit, offset)


@router.delete("/doctors/{doctor_id}/availability/{slot_id}", tags=["Availability"])
def delete_slot(doctor_id: UUID, slot_id: UUID, user: User, repo: Repo):
    return DoctorService(repo).delete_slot(user, doctor_id, slot_id)


@router.post("/consultations", status_code=201, tags=["Consultations"])
def book(
    data: s.Booking,
    user: User,
    repo: Repo,
    idempotency_key: str = Header(..., min_length=1, max_length=128),
):
    return ConsultationService(repo).book(user, data, idempotency_key)


@router.get("/consultations", tags=["Consultations"])
def consultations(
    user: User,
    repo: Repo,
    limit: Limit = 20,
    cursor: UUID | None = None,
    status: Literal[
        "BOOKED", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "PAYMENT_FAILED", "EXPIRED"
    ]
    | None = None,
):
    return ConsultationService(repo).listing(user, status, limit, str(cursor) if cursor else None)


@router.get("/consultations/{consultation_id}", tags=["Consultations"])
def consultation(consultation_id: UUID, user: User, repo: Repo):
    return ConsultationService(repo).get(user, consultation_id)


@router.post("/consultations/{consultation_id}/confirm", tags=["Consultations"])
def confirm(consultation_id: UUID, user: User, repo: Repo):
    return ConsultationService(repo).change(user, consultation_id, "CONFIRMED")


@router.post("/consultations/{consultation_id}/start", tags=["Consultations"])
def start(consultation_id: UUID, user: User, repo: Repo):
    return ConsultationService(repo).change(user, consultation_id, "IN_PROGRESS")


@router.post("/consultations/{consultation_id}/cancel", tags=["Consultations"])
def cancel(consultation_id: UUID, user: User, repo: Repo):
    return ConsultationService(repo).change(user, consultation_id, "CANCELLED")


@router.post("/consultations/{consultation_id}/complete", tags=["Consultations"])
def complete(consultation_id: UUID, user: User, repo: Repo):
    return ConsultationService(repo).change(user, consultation_id, "COMPLETED")


@router.post(
    "/consultations/{consultation_id}/prescriptions", status_code=201, tags=["Prescriptions"]
)
def prescribe(consultation_id: UUID, data: s.PrescriptionInput, user: User, repo: Repo):
    return PrescriptionService(repo).create(user, consultation_id, data)


@router.get("/consultations/{consultation_id}/prescriptions", tags=["Prescriptions"])
def prescriptions(
    consultation_id: UUID, user: User, repo: Repo, limit: Limit = 20, offset: Offset = 0
):
    return PrescriptionService(repo).listing(user, consultation_id, limit, offset)


@router.get("/prescriptions/{prescription_id}", tags=["Prescriptions"])
def prescription(prescription_id: UUID, user: User, repo: Repo):
    return PrescriptionService(repo).get(user, prescription_id)


@router.post("/prescriptions/{prescription_id}/revisions", tags=["Prescriptions"])
def revise(prescription_id: UUID, data: s.PrescriptionInput, user: User, repo: Repo):
    return PrescriptionService(repo).revision(user, prescription_id, data)


def provider():
    return MockProvider()


@router.post("/payments", status_code=201, tags=["Payments"])
def pay(data: s.PaymentInput, user: User, repo: Repo, adapter=Depends(provider)):
    return PaymentService(repo, adapter).create(user, data.consultation_id)


@router.get("/payments/{payment_id}", tags=["Payments"])
def payment(payment_id: UUID, user: User, repo: Repo, adapter=Depends(provider)):
    return PaymentService(repo, adapter).get(user, payment_id)


@router.post("/payments/webhooks/mock", tags=["Payments"])
async def webhook(
    request: Request,
    repo: Repo,
    adapter=Depends(provider),
    x_signature: str = Header(..., max_length=128),
):
    body = await request.body()
    require(len(body) <= 16384, "payload_too_large", 413)
    return PaymentService(repo, adapter).webhook(body, x_signature)


@router.get("/admin/analytics/{report}", tags=["Administration"])
def analytics(
    report: Literal["overview", "consultations", "doctors", "payments"],
    user: Admin,
    repo: Repo,
    start: datetime | None = None,
    end: datetime | None = None,
):
    return AnalyticsService(repo).report(user, report, start, end)
