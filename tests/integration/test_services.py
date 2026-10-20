import os
from datetime import timedelta
from unittest.mock import patch

import pytest
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Consultation, Outbox, now
from app.workers.tasks import consume_event, publish_outbox, reconcile


def test_outbox_consumer_is_idempotent(database, actors, booking):
    booking()
    with Session(database) as db:
        identity = db.scalar(select(Outbox.id))

    def local_session():
        return Session(database, expire_on_commit=False)

    with patch("app.workers.tasks.session", local_session):
        assert consume_event.run(identity) == "LOCAL_INBOX"
        assert consume_event.run(identity) == "duplicate"
        with patch("app.workers.tasks.consume_event.delay") as task:
            assert publish_outbox.run() == 1
            assert publish_outbox.run() == 0
            assert task.call_count == 1


def test_expiration_releases_reservation(database, actors, booking):
    identity = booking().json()["id"]
    with Session(database) as db:
        db.get(Consultation, identity).created_at = now() - timedelta(minutes=16)
        db.commit()
    with patch("app.workers.tasks.session", lambda: Session(database, expire_on_commit=False)):
        assert reconcile.run()["expired"] == 1
    assert booking(actor="other", key="after-expiration").status_code == 201


@pytest.mark.integration
def test_real_redis_rate_limiter():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not configured")
    from app.core.redis import RATE_SCRIPT

    client = Redis.from_url(url)
    client.delete("test-rate")
    assert client.eval(RATE_SCRIPT, 1, "test-rate", 60) == 1
    assert client.eval(RATE_SCRIPT, 1, "test-rate", 60) == 2
    assert 0 < client.ttl("test-rate") <= 60
    client.delete("test-rate")


@pytest.mark.integration
def test_postgres_constraints(database, actors):
    if database.dialect.name != "postgresql":
        pytest.skip("PostgreSQL not configured")
    from sqlalchemy.exc import DBAPIError, IntegrityError

    from app.db.models import Audit, Slot

    with Session(database) as db:
        original = db.get(Slot, actors["slot_id"])
        db.add(
            Slot(
                doctor_id=actors["doctor_id"],
                start_time=original.start_time,
                end_time=original.end_time,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        audit = Audit(action="test", resource_type="test", resource_id="test", request_id="test")
        db.add(audit)
        db.commit()
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE audit_logs SET outcome='changed'"))
            db.commit()
        db.rollback()
