from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.errors import require
from app.db.models import Consultation, Doctor, Payment, now
from app.modules.audit import record
from app.modules.auth import aware


class AnalyticsService:
    def __init__(self, repo):
        self.db = repo.db

    def report(self, user, kind, start, end):
        start, end = start or now() - timedelta(days=30), end or now()
        start, end = aware(start), aware(end)
        require(end > start and end - start <= timedelta(days=93), "invalid_report_window", 422)
        model: Any = {
            "overview": Consultation,
            "consultations": Consultation,
            "doctors": Doctor,
            "payments": Payment,
        }[kind]
        field = Doctor.verification_status if kind == "doctors" else model.status
        rows = self.db.execute(
            select(field, func.count())
            .where(model.created_at >= start, model.created_at < end)
            .group_by(field)
        ).all()
        counts = {status: count for status, count in rows}
        record(self.db, user.id, "admin_analytics", kind, "aggregate")
        self.db.commit()
        return {"start": start, "end": end, "total": sum(counts.values()), "by_status": counts}
