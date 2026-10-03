"""Durable case orchestration, fenced queue and workflow review.

Revision ID: 20261002_0006
Revises: 20261002_0005
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0006"
down_revision = "20261002_0005"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL enum additions must commit before a new value can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE case_status ADD VALUE IF NOT EXISTS 'INVESTIGATION_QUEUED'")
        op.execute("ALTER TYPE case_status ADD VALUE IF NOT EXISTS 'EXECUTION_QUEUED'")
    op.add_column("cases", sa.Column("orchestration_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cases", sa.Column("orchestration_fingerprint", sa.String(), nullable=True))
    op.create_table("orchestration_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("incident_id", sa.String(), sa.ForeignKey("incidents.id")),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("task_version", sa.String(), nullable=False),
        sa.Column("workflow_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String()),
        sa.Column("lease_token", sa.String()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("idempotency_key", sa.String(), nullable=False, unique=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10", name="ck_task_attempts"),
        sa.CheckConstraint("status IN ('PENDING','WAITING_HANDLER','RUNNING','RETRY_WAIT','COMPLETED','DEAD_LETTER','CANCELLED')", name="ck_task_status"),
        sa.CheckConstraint("(status = 'RUNNING' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status <> 'RUNNING' AND lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)", name="ck_task_lease"),
    )
    for name, columns in (
        ("ix_tasks_poll", ["status", "scheduled_at", "priority", "created_at"]),
        ("ix_tasks_lease", ["status", "lease_expires_at"]),
        ("ix_tasks_deadline", ["status", "deadline"]),
        ("ix_tasks_case_history", ["case_id", "created_at"]),
        ("ix_tasks_incident", ["incident_id", "status"]),
    ):
        op.create_index(name, "orchestration_tasks", columns)
    op.create_index("ix_tasks_ready_priority", "orchestration_tasks", ["priority", "scheduled_at", "created_at", "id"],
        postgresql_where=sa.text("status IN ('PENDING','RETRY_WAIT')"))
    op.create_index("ix_tasks_ready_age", "orchestration_tasks", ["created_at", "id"],
        postgresql_where=sa.text("status IN ('PENDING','RETRY_WAIT')"))
    op.create_table("orchestration_task_consumers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("orchestration_tasks.id"), nullable=False),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("assessment_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "case_id", name="uq_task_consumer"),
    )
    op.create_index("ix_task_consumers_case", "orchestration_task_consumers", ["case_id", "active"])
    op.create_table("orchestration_task_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("orchestration_tasks.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_history_task", "orchestration_task_history", ["task_id", "created_at"])
    op.create_table("workflow_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("task_id", sa.String(), sa.ForeignKey("orchestration_tasks.id")),
        sa.Column("idempotency_key", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assigned_role", sa.String(), nullable=False),
        sa.Column("assigned_reviewer", sa.String()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assessment_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('OPEN','APPROVED','REJECTED','MORE_INVESTIGATION','EXPIRED','SUPERSEDED')", name="ck_review_status"),
    )
    op.create_index("ix_reviews_queue", "workflow_reviews", ["status", "deadline"])
    op.create_index("ix_reviews_case", "workflow_reviews", ["case_id", "created_at"])
    op.create_table("workflow_review_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("review_id", sa.String(), sa.ForeignKey("workflow_reviews.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_history_review", "workflow_review_history", ["review_id", "created_at"])
    op.create_index("ix_cases_sla_deadline", "cases", ["sla_deadline"])


def downgrade():
    # Refuse conversion of live queued state; no silent lifecycle/history rewrite.
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM cases WHERE status::text IN ('INVESTIGATION_QUEUED','EXECUTION_QUEUED')")).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade while cases use Phase 6 queued states")
    for table in ("workflow_review_history", "workflow_reviews", "orchestration_task_history", "orchestration_task_consumers", "orchestration_tasks"):
        op.drop_table(table)
    op.drop_index("ix_cases_sla_deadline", table_name="cases")
    op.drop_column("cases", "orchestration_fingerprint")
    op.drop_column("cases", "orchestration_generation")
    op.execute("CREATE TYPE case_status_previous AS ENUM ('DETECTED','TRIAGED','INVESTIGATING','AWAITING_DECISION','AWAITING_HUMAN','APPROVED','EXECUTING','VERIFYING','RESOLVED','BLOCKED','ESCALATED','FAILED')")
    op.execute("ALTER TABLE cases ALTER COLUMN status TYPE case_status_previous USING status::text::case_status_previous")
    op.execute("DROP TYPE case_status")
    op.execute("ALTER TYPE case_status_previous RENAME TO case_status")
