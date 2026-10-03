"""Persist bounded counterfactual previews and operation-bound projections."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0011"
down_revision = "20261002_0010"
branch_labels = depends_on = None


def upgrade():
    op.create_table("counterfactual_simulations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("authorization_id", sa.String(), sa.ForeignKey("control_authorizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_id", sa.String(), sa.ForeignKey("execution_operations.id"), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("projection", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", name="uq_counterfactual_operation"),
        sa.CheckConstraint("outcome IN ('PASS','BLOCKED')", name="ck_counterfactual_outcome"))
    op.create_index("ix_counterfactual_simulations_case_id", "counterfactual_simulations", ["case_id"])
    op.create_index("ix_counterfactual_simulations_authorization_id", "counterfactual_simulations", ["authorization_id"])


def downgrade():
    op.drop_table("counterfactual_simulations")
