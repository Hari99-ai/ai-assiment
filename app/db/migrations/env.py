from alembic import context
from sqlalchemy import create_engine

from app.core.config import settings
from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def run():
    if context.is_offline_mode():
        context.configure(
            url=settings().database_url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        supplied = config.attributes.get("connection")
        if supplied is not None:
            context.configure(
                connection=supplied, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
            return
        engine = create_engine(settings().database_url)
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()


run()
