import os
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ["DATABASE_URL"] = "sqlite:///" + str(
    Path(tempfile.gettempdir()) / f"amrutam-test-{os.getpid()}.db"
)
os.environ["REDIS_REQUIRED"] = "false"
os.environ["REDIS_URL"] = "redis://localhost:6398/0"

from app.core.security import access, digest, passwords, seal
from app.db.models import Base, Doctor, Profile, Refresh, Slot, User, now
from app.db.session import get_db
from app.main import app


@pytest.fixture
def database(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30}
        if url.startswith("sqlite")
        else {},
    )
    if engine.dialect.name == "postgresql":
        from alembic import command
        from alembic.config import Config

        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
            command.upgrade(config, "head")
    else:
        Base.metadata.create_all(engine)
    yield engine
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
    else:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(database):
    def override():
        with Session(database, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def actors(database):
    with Session(database, expire_on_commit=False) as db:
        result = {}
        for name, role in (
            ("patient", "PATIENT"),
            ("other", "PATIENT"),
            ("doctor", "DOCTOR"),
            ("admin", "ADMIN"),
            ("support", "SUPPORT"),
        ):
            user = User(
                email=name + "@example.com",
                role=role,
                password_hash=passwords.hash("a-long-test-password"),
                mfa_enabled=role == "ADMIN",
            )
            db.add(user)
            db.flush()
            db.add(Profile(user_id=user.id, full_name=name))
            row = Refresh(
                user_id=user.id,
                token_hash=digest(str(uuid4())),
                family=str(uuid4()),
                expires_at=now() + timedelta(days=1),
                mfa=role == "ADMIN",
            )
            db.add(row)
            db.flush()
            result[name] = {
                "user": user,
                "headers": {"Authorization": "Bearer " + access(user.id, row.id, row.mfa)},
            }
        doctor = Doctor(
            user_id=result["doctor"]["user"].id,
            license_number=seal("TEST123"),
            qualifications=seal("MBBS"),
            specialization="Ayurveda",
            verification_status="VERIFIED",
            consultation_fee=500,
            experience_years=5,
        )
        db.add(doctor)
        db.flush()
        slot = Slot(
            doctor_id=doctor.id,
            start_time=now() + timedelta(days=1),
            end_time=now() + timedelta(days=1, minutes=30),
        )
        db.add(slot)
        db.commit()
        result.update(doctor_id=doctor.id, slot_id=slot.id)
        return result


@pytest.fixture
def booking(client, actors):
    def make(actor="patient", key="booking-1", reason="Consultation", slot=None):
        return client.post(
            "/api/v1/consultations",
            headers={**actors[actor]["headers"], "Idempotency-Key": key},
            json={"availability_slot_id": slot or actors["slot_id"], "reason_for_visit": reason},
        )

    return make
