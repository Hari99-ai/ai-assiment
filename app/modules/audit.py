from contextvars import ContextVar

from app.db.models import Audit, Outbox

request_id: ContextVar[str] = ContextVar("request_id", default="system")


def record(db, actor, action, resource, identity, outcome="success"):
    db.add(
        Audit(
            actor_user_id=actor,
            action=action,
            resource_type=resource,
            resource_id=str(identity),
            request_id=request_id.get(),
            outcome=outcome,
        )
    )


def emit(db, topic, payload):
    db.add(Outbox(topic=topic, payload=payload))
