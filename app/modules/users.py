from sqlalchemy import select

from app.core.errors import require
from app.core.security import unseal
from app.db.models import Doctor, Profile, Slot, now
from app.modules.audit import record
from app.modules.doctors import slot_view


class UserService:
    def __init__(self, repo):
        self.repo, self.db = repo, repo.db

    def get(self, user):
        profile = self.db.scalar(select(Profile).where(Profile.user_id == user.id))
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": profile.full_name if profile else "",
            "mfa_enabled": user.mfa_enabled,
        }

    def patch(self, user, data):
        profile = self.db.scalar(select(Profile).where(Profile.user_id == user.id))
        require(profile is not None, "profile_not_found", 404)
        profile.full_name = data.full_name
        record(self.db, user.id, "profile_updated", "user", user.id)
        self.db.commit()
        return self.get(user)

    def credentials(self, user, identity):
        doctor = self.repo.get(Doctor, identity)
        record(self.db, user.id, "credentials_read", "doctor", doctor.id)
        self.db.commit()
        return {
            "license_number": unseal(doctor.license_number),
            "qualifications": unseal(doctor.qualifications),
        }

    def slots(self, identity, limit, offset):
        doctor = self.repo.get(Doctor, identity)
        require(doctor.verification_status == "VERIFIED", "not_found", 404)
        rows = self.db.scalars(
            select(Slot)
            .where(Slot.doctor_id == doctor.id, Slot.status == "AVAILABLE", Slot.start_time > now())
            .order_by(Slot.start_time, Slot.id)
            .limit(limit)
            .offset(offset)
        )
        return {"items": [slot_view(row) for row in rows], "limit": limit, "offset": offset}
