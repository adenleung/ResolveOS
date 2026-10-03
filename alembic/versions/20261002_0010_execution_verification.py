"""Idempotent synthetic confirmation replay and independent verification."""
from alembic import op
import sqlalchemy as sa
revision = "20261002_0010"
down_revision = "20261002_0009"
branch_labels = depends_on = None

def upgrade():
    op.create_table("execution_operations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("authorization_id", sa.String(), sa.ForeignKey("control_authorizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.String(), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("logical_key", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False), sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("authorization_id", name="uq_execution_authorization"),
        sa.UniqueConstraint("logical_key", name="uq_execution_logical_key"))
    op.create_index("ix_execution_operations_case_id", "execution_operations", ["case_id"])

def downgrade():
    op.drop_table("execution_operations")
