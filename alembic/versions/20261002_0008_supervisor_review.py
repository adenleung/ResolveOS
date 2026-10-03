"""Evidence validation and bounded Supervisor review history."""
from alembic import op
import sqlalchemy as sa
revision = "20261002_0008"
down_revision = "20261002_0007"
branch_labels = depends_on = None

def upgrade():
    op.create_table("supervisor_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("orchestration_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False), sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False), sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False), sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("telemetry", sa.JSON(), nullable=False),
        sa.UniqueConstraint("task_id", "attempt", name="uq_supervisor_attempt"),
        sa.CheckConstraint("attempt >= 1", name="ck_supervisor_attempt"))
    op.create_index("ix_supervisor_reviews_task_id", "supervisor_reviews", ["task_id"])
    op.create_index("ix_supervisor_reviews_case_id", "supervisor_reviews", ["case_id"])

def downgrade():
    op.drop_table("supervisor_reviews")
