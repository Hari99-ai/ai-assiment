from sqlalchemy import select

from app.core.errors import require
from app.core.security import seal, unseal
from app.db.models import Doctor, Prescription, Revision
from app.db.repositories import Repository
from app.modules.audit import record
from app.modules.consultations import ConsultationService


def view(value):
    import json

    return {
        "id": value.id,
        "consultation_id": value.consultation_id,
        "version": value.version,
        "prescription_data": json.loads(unseal(value.prescription_data)),
        "issued_at": value.issued_at,
    }


class PrescriptionService:
    def __init__(self, repo: Repository):
        self.repo, self.db = repo, repo.db
        self.consultations = ConsultationService(repo)

    def clinician(self, user, consultation):
        doc = self.repo.get(Doctor, consultation.doctor_id)
        require(
            user.role == "DOCTOR"
            and doc.user_id == user.id
            and doc.verification_status == "VERIFIED"
        )
        require(
            consultation.status in {"IN_PROGRESS", "COMPLETED"}, "consultation_not_clinical", 409
        )

    def create(self, user, identity, data):
        consultation = self.consultations.authorized(user, identity, True)
        self.clinician(user, consultation)
        prescription = self.repo.add(
            Prescription(
                consultation_id=consultation.id,
                doctor_id=consultation.doctor_id,
                patient_id=consultation.patient_id,
                prescription_data=seal(data.model_dump_json()),
            )
        )
        self.repo.add(
            Revision(
                prescription_id=prescription.id,
                version=1,
                prescription_data=prescription.prescription_data,
            )
        )
        record(self.db, user.id, "prescription_issued", "prescription", prescription.id)
        self.db.commit()
        return view(prescription)

    def revision(self, user, identity, data):
        prescription = self.repo.get(Prescription, identity, True)
        consultation = self.consultations.authorized(user, prescription.consultation_id)
        self.clinician(user, consultation)
        prescription.version += 1
        prescription.prescription_data = seal(data.model_dump_json())
        self.repo.add(
            Revision(
                prescription_id=prescription.id,
                version=prescription.version,
                prescription_data=prescription.prescription_data,
            )
        )
        record(self.db, user.id, "prescription_revised", "prescription", prescription.id)
        self.db.commit()
        return view(prescription)

    def get(self, user, identity):
        prescription = self.repo.get(Prescription, identity)
        self.consultations.authorized(user, prescription.consultation_id)
        revisions = self.db.scalars(
            select(Revision)
            .where(Revision.prescription_id == prescription.id)
            .order_by(Revision.version)
        ).all()
        import json

        record(self.db, user.id, "prescription_read", "prescription", prescription.id)
        self.db.commit()
        return {
            **view(prescription),
            "revisions": [
                {"version": r.version, "prescription_data": json.loads(unseal(r.prescription_data))}
                for r in revisions
            ],
        }

    def listing(self, user, identity, limit, offset):
        consultation = self.consultations.authorized(user, identity)
        rows = self.db.scalars(
            select(Prescription)
            .where(Prescription.consultation_id == consultation.id)
            .order_by(Prescription.id)
            .limit(limit)
            .offset(offset)
        ).all()
        record(self.db, user.id, "prescription_list", "consultation", consultation.id)
        self.db.commit()
        return {"items": [view(row) for row in rows], "limit": limit, "offset": offset}
