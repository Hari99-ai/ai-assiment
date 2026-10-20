from sqlalchemy import exists, select

from app.core.errors import require
from app.core.security import seal
from app.db.models import Doctor, Slot, User
from app.db.repositories import Repository
from app.modules.audit import record


def public_doctor(doc):
    return {
        "id": doc.id,
        "specialization": doc.specialization,
        "verification_status": doc.verification_status,
        "consultation_fee": str(doc.consultation_fee),
        "experience_years": doc.experience_years,
    }


def slot_view(slot):
    return {
        "id": slot.id,
        "doctor_id": slot.doctor_id,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "status": slot.status,
        "version": slot.version,
    }


class DoctorService:
    def __init__(self, repo: Repository):
        self.repo, self.db = repo, repo.db

    def owned(self, user, identity, lock=False):
        doc = self.repo.get(Doctor, identity, lock)
        require(doc.user_id == user.id or user.role == "ADMIN")
        return doc

    def create(self, user, data):
        require(user.role == "PATIENT", "doctor_application_not_allowed")
        doc = self.repo.add(
            Doctor(
                user_id=user.id,
                **data.model_dump(exclude={"license_number", "qualifications"}),
                license_number=seal(data.license_number),
                qualifications=seal(data.qualifications),
            )
        )
        record(self.db, user.id, "doctor_apply", "doctor", doc.id)
        self.db.commit()
        return public_doctor(doc)

    def patch(self, user, identity, data):
        doc = self.owned(user, identity, True)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(doc, key, value)
        record(self.db, user.id, "doctor_update", "doctor", doc.id)
        self.db.commit()
        return public_doctor(doc)

    def verify(self, user, identity, status):
        require(user.role == "ADMIN")
        doc = self.repo.get(Doctor, identity, True)
        doc.verification_status = status
        target = self.repo.get(User, doc.user_id, True)
        target.role = "DOCTOR" if status == "VERIFIED" else "PATIENT"
        record(self.db, user.id, "doctor_verification", "doctor", doc.id)
        record(self.db, user.id, "role_change", "user", target.id)
        self.db.commit()
        return public_doctor(doc)

    def search(self, specialization, minimum, maximum, after, before, limit, offset):
        stmt = select(Doctor).where(Doctor.verification_status == "VERIFIED")
        if specialization:
            stmt = stmt.where(Doctor.specialization == specialization)
        if minimum is not None:
            stmt = stmt.where(Doctor.consultation_fee >= minimum)
        if maximum is not None:
            stmt = stmt.where(Doctor.consultation_fee <= maximum)
        if after or before:
            query = select(Slot.id).where(Slot.doctor_id == Doctor.id, Slot.status == "AVAILABLE")
            if after:
                query = query.where(Slot.start_time >= after)
            if before:
                query = query.where(Slot.end_time <= before)
            stmt = stmt.where(exists(query))
        return {
            "items": [
                public_doctor(doc)
                for doc in self.db.scalars(stmt.order_by(Doctor.id).limit(limit).offset(offset))
            ],
            "limit": limit,
            "offset": offset,
        }

    def add_slot(self, user, identity, data):
        doc = self.owned(user, identity, True)
        require(doc.verification_status == "VERIFIED", "doctor_unverified", 409)
        overlap = self.db.scalar(
            select(Slot.id).where(
                Slot.doctor_id == doc.id,
                Slot.status != "CLOSED",
                Slot.start_time < data.end_time,
                Slot.end_time > data.start_time,
            )
        )
        require(not overlap, "overlapping_availability", 409)
        slot = self.repo.add(Slot(doctor_id=doc.id, **data.model_dump()))
        record(self.db, user.id, "availability_create", "slot", slot.id)
        self.db.commit()
        return slot_view(slot)

    def delete_slot(self, user, identity, slot_id):
        self.owned(user, identity, True)
        slot = self.repo.get(Slot, slot_id, True)
        require(slot.doctor_id == str(identity), "not_found", 404)
        require(slot.status == "AVAILABLE", "slot_reserved", 409)
        slot.status = "CLOSED"
        slot.version += 1
        record(self.db, user.id, "availability_delete", "slot", slot.id)
        self.db.commit()
        return {"status": "CLOSED"}
