"""Durable specialist attempts and evidence-backed results."""
from alembic import op
import sqlalchemy as sa
revision = "20261002_0007"
down_revision = "20261002_0006"
branch_labels = depends_on = None

def upgrade():
    op.create_table("investigation_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("orchestration_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False), sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("context", sa.JSON(), nullable=False), sa.Column("result", sa.JSON()),
        sa.Column("telemetry", sa.JSON(), nullable=False), sa.Column("error_code", sa.String()),
        sa.UniqueConstraint("task_id", "attempt", name="uq_investigation_attempt"),
        sa.CheckConstraint("attempt >= 1", name="ck_investigation_attempt"),
        sa.CheckConstraint("role IN ('TRANSACTION','TECHNOLOGY','RISK')", name="ck_investigation_role"),
        sa.CheckConstraint("status IN ('RUNNING','COMPLETED','NEEDS_ADDITIONAL_EVIDENCE','ESCALATION_REQUIRED','FAILED')", name="ck_investigation_status"))
    op.create_index("ix_investigation_runs_task_id", "investigation_runs", ["task_id"])
    op.create_index("ix_investigation_runs_case_id", "investigation_runs", ["case_id"])

def downgrade():
    op.drop_table("investigation_runs")
