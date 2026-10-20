from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


@lru_cache
def engine():
    url = settings().database_url
    options: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        options.update(
            pool_size=10,
            max_overflow=10,
            pool_timeout=5,
            connect_args={"options": "-c statement_timeout=5000 -c lock_timeout=3000"},
        )
    result = create_engine(url, **options)
    if url.startswith("sqlite"):

        @event.listens_for(result, "connect")
        def pragmas(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")

    return result


def session() -> Session:
    return sessionmaker(engine(), expire_on_commit=False)()


def get_db():
    with session() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
