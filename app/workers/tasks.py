from datetime import timedelta

from celery import Celery
from celery.signals import worker_process_init
from kombu.exceptions import OperationalError as BrokerError
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Consultation, Notification, Outbox, Payment, now
from app.db.repositories import Repository
from app.db.session import session
from app.modules.audit import record
from app.modules.consultations import transition
from app.modules.payments import MockProvider
from app.observability.metrics import JOBS


@worker_process_init.connect
def worker_tracing(**kwargs):
    from app.db.session import engine
    from app.observability.tracing import configure

    configure(None, engine(), settings().otel_endpoint)


celery = Celery("amrutam", broker=settings().redis_url)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=5,
    broker_transport_options={"visibility_timeout": 300},
    task_soft_time_limit=45,
    task_time_limit=60,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "outbox": {"task": "app.workers.tasks.publish_outbox", "schedule": 5.0},
        "reconcile": {"task": "app.workers.tasks.reconcile", "schedule": 60.0},
    },
)


@celery.task(
    autoretry_for=(ConnectionError, TimeoutError, BrokerError),
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=60,
    max_retries=5,
)
def publish_outbox():
    with session() as db:
        rows = db.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for event in rows:
            # Broker delivery may duplicate after a crash; consumers key on durable event ID.
            consume_event.delay(event.id)
            event.published_at = now()
            event.attempts += 1
        db.commit()
        return len(rows)


@celery.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=120,
    max_retries=5,
)
def consume_event(event_id):
    try:
        with session() as db:
            repo = Repository(db)
            event = repo.get(Outbox, event_id, True)
            notification = db.scalar(select(Notification).where(Notification.event_id == event.id))
            if notification:
                return "duplicate"
            if event.topic in {"payment_create", "payment_refund"}:
                payment = repo.get(Payment, event.payload["payment_id"], True)
                provider = MockProvider()
                if event.topic == "payment_create":
                    payment.provider_reference = provider.create(
                        payment.consultation_id, str(payment.amount)
                    )
                elif payment.status == "REFUND_PENDING":
                    payment.status = provider.refund(payment.provider_reference)
                    record(db, None, "payment_refunded", "payment", payment.id)
                status = "PROCESSED"
            else:
                # Durable local inbox, deliberately not a claim of email/SMS delivery.
                status = "LOCAL_INBOX"
            db.add(Notification(event_id=event.id, payload=event.payload, status=status))
            db.commit()
        JOBS.labels("success").inc()
        return status
    except Exception:
        JOBS.labels("failure").inc()
        raise


@celery.task
def reconcile():
    """Expire unpaid 15-minute reservations; mock status is always pending until webhook."""
    with session() as db:
        consultations = db.scalars(
            select(Consultation)
            .where(
                Consultation.status == "BOOKED",
                Consultation.created_at < now() - timedelta(minutes=15),
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for consultation in consultations:
            transition(db, consultation, "EXPIRED")
        # Republish events whose consumers exhausted retries; consumer dedup makes this safe.
        events = db.scalars(
            select(Outbox)
            .where(
                Outbox.published_at < now() - timedelta(minutes=10),
                ~select(Notification.id).where(Notification.event_id == Outbox.id).exists(),
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for event in events:
            event.published_at = None
        db.commit()
        return {"expired": len(consultations), "requeued": len(events)}
