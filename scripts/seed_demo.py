"""Create synthetic local demo data. Never run against a production database."""

import argparse
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pyotp

from app.core.config import settings
from app.core.security import access, digest, passwords, seal
from app.db.models import Doctor, Profile, Refresh, Slot, User, now
from app.db.session import session
from app.modules.audit import record


def seed(count=100):
    if settings().environment == "production":
        raise RuntimeError("Demo seeding is disabled in production")
    batch = str(uuid4())[:8]
    data = {}
    with session() as db:
        for name, role in (("patient", "PATIENT"), ("doctor", "DOCTOR"), ("admin", "ADMIN")):
            user = User(
                email=f"{name}-{batch}@example.com",
                password_hash=passwords.hash(str(uuid4())),
                role=role,
                mfa_enabled=role == "ADMIN",
                mfa_secret=seal(pyotp.random_base32()) if role == "ADMIN" else None,
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id, full_name="Synthetic " + name))
            refresh = Refresh(
                user_id=user.id,
                token_hash=digest(str(uuid4())),
                family=str(uuid4()),
                expires_at=now() + timedelta(hours=2),
                mfa=role == "ADMIN",
            )
            db.add(refresh)
            db.flush()
            data[name + "_token"] = access(user.id, refresh.id, refresh.mfa)
            data[name + "_id"] = user.id
            record(db, None, "demo_seed", "user", user.id)
        doctor = Doctor(
            user_id=data["doctor_id"],
            license_number=seal("SYNTHETIC-" + batch),
            qualifications=seal("Synthetic demo credential"),
            specialization="Ayurveda",
            verification_status="VERIFIED",
            consultation_fee=500,
            experience_years=5,
        )
        db.add(doctor)
        db.flush()
        data["doctor_id"] = doctor.id
        slot_ids = []
        for index in range(count):
            start = now() + timedelta(days=1, minutes=index * 30)
            slot = Slot(
                doctor_id=doctor.id, start_time=start, end_time=start + timedelta(minutes=30)
            )
            db.add(slot)
            db.flush()
            slot_ids.append(slot.id)
        data["slots"] = slot_ids
        db.commit()
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/demo.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Created {count} synthetic slots; short-lived demo tokens are in artifacts/demo.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slots", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.slots <= 10000:
        parser.error("slots must be 1..10000")
    seed(args.slots)
