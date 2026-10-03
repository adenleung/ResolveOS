"""Classification, priority, SLA, and routing assessment history.

Revision ID: 20261002_0004
Revises: 20261002_0003
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0004"
down_revision = "20261002_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("sla_rule_version", sa.String(), nullable=True))
    op.create_table(
        "assessment_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("exception_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.String(), nullable=False),
        sa.Column("classification_source", sa.String(), nullable=False),
        sa.Column("operational_eligible", sa.Boolean(), nullable=False),
        sa.Column("change_reason", sa.String(), nullable=False),
        sa.Column("assessment", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exception_id"], ["exceptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exception_id", "revision", name="uq_assessment_exception_revision"),
    )
    op.create_index("ix_assessment_history_exception_id", "assessment_history", ["exception_id"])
    op.create_index("ix_assessment_history_case_id", "assessment_history", ["case_id"])
    op.create_index("ix_assessment_history_created_at", "assessment_history", ["created_at"])


def downgrade() -> None:
    op.drop_table("assessment_history")
    op.drop_column("cases", "sla_rule_version")
    op.drop_column("cases", "sla_deadline")
    op.drop_column("cases", "sla_started_at")