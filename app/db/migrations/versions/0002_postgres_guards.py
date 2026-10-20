"""PostgreSQL interval exclusion and append-only audit/revision guards."""

from alembic import op

revision = "0002_postgres_guards"
down_revision = "bdcd8db3295b"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""ALTER TABLE availability_slots ADD CONSTRAINT no_overlapping_slots
        EXCLUDE USING gist (doctor_id WITH =,
        tstzrange(start_time, end_time, '[)') WITH &&) WHERE (status <> 'CLOSED')""")
    op.execute("""CREATE FUNCTION reject_immutable_change() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'append-only table'; END;
        $$ LANGUAGE plpgsql""")
    for table in ("audit_logs", "prescription_revisions", "consultation_history"):
        op.execute(
            f"CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()"
        )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("audit_logs", "prescription_revisions", "consultation_history"):
        op.execute(f"DROP TRIGGER immutable_rows ON {table}")
    op.execute("DROP FUNCTION reject_immutable_change()")
    op.execute("ALTER TABLE availability_slots DROP CONSTRAINT no_overlapping_slots")
