"""Isolated non-executable shadow evaluations; no operational data conversion."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0013"
down_revision = "20261004_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("shadow_evaluations",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False), sa.Column("mode", sa.String(), nullable=False),
        sa.Column("action_authorization", sa.String(), nullable=False), sa.Column("execution_permitted", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False, unique=True), sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode = 'SHADOW' AND action_authorization = 'NOT_EVALUATED' AND execution_permitted = false", name="ck_shadow_nonexecution"),
        sa.CheckConstraint("outcome IN ('WOULD_AUTO_ELIGIBLE','WOULD_HUMAN_APPROVAL_REQUIRED','WOULD_BLOCK','WOULD_ESCALATE')", name="ck_shadow_outcome"))
    op.create_index("ix_shadow_case_time", "shadow_evaluations", ["case_id", "created_at"])


def downgrade():
    op.drop_table("shadow_evaluations")
