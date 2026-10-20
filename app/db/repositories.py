from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError


class Repository:
    """Small SQLAlchemy adapter injected into application services."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, model, identity, lock=False):
        stmt = select(model).where(model.id == str(identity))
        if lock:
            stmt = stmt.with_for_update()
        result = self.db.scalar(stmt.execution_options(populate_existing=True))
        if result is None:
            raise DomainError(404, "not_found")
        return result

    def add(self, value):
        self.db.add(value)
        self.db.flush()
        return value
