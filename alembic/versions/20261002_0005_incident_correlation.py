"""Deterministic incident correlation and lifecycle history.

Revision ID: 20261002_0005
Revises: 20261002_0004
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0005"
down_revision = "20261002_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("status", sa.String(), nullable=False, server_default="SUSPECTED"),
    )
    op.add_column("incidents", sa.Column("correlation_rule_version", sa.String(), nullable=True))
    op.add_column("incidents", sa.Column("merged_into_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_incidents_merged_into_incident", "incidents", "incidents", ["merged_into_id"], ["id"]
    )

    op.add_column("case_incidents", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("case_incidents", sa.Column("removal_reason", sa.Text(), nullable=True))

    op.create_table(
        "incident_correlation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("rule_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cases_examined", sa.Integer(), nullable=False),
        sa.Column("candidate_pairs_examined", sa.Integer(), nullable=False),
        sa.Column("groups_created", sa.Integer(), nullable=False),
        sa.Column("memberships_added", sa.Integer(), nullable=False),
        sa.Column("ungrouped_cases", sa.Integer(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "incident_correlation_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("correlation_run_id", sa.String(), nullable=True),
        sa.Column("incident_id", sa.String(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("correlation_key", sa.String(), nullable=True),
        sa.Column("rule_version", sa.String(), nullable=False),
        sa.Column("case_ids", sa.JSON(), nullable=False),
        sa.Column("shared_features", sa.JSON(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("contradictions", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["correlation_run_id"], ["incident_correlation_runs.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_incident_correlation_history_incident_id", "incident_correlation_history", ["incident_id"]
    )
    op.create_index(
        "ix_incident_correlation_history_run_id", "incident_correlation_history", ["correlation_run_id"]
    )
    op.create_index(
        "ix_incident_correlation_history_created_at", "incident_correlation_history", ["created_at"]
    )
    op.add_column(
        "case_incidents",
        sa.Column("correlation_history_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_case_incidents_correlation_history",
        "case_incidents",
        "incident_correlation_history",
        ["correlation_history_id"],
        ["id"],
    )
    op.create_index(
        "uq_case_incidents_active_case",
        "case_incidents",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index(
        "ix_case_incidents_active_incident",
        "case_incidents",
        ["incident_id"],
        postgresql_where=sa.text("removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_case_incidents_active_incident", table_name="case_incidents")
    op.drop_index("uq_case_incidents_active_case", table_name="case_incidents")
    op.drop_constraint("fk_case_incidents_correlation_history", "case_incidents", type_="foreignkey")
    op.drop_column("case_incidents", "correlation_history_id")
    op.drop_index("ix_incident_correlation_history_created_at", table_name="incident_correlation_history")
    op.drop_index("ix_incident_correlation_history_run_id", table_name="incident_correlation_history")
    op.drop_index("ix_incident_correlation_history_incident_id", table_name="incident_correlation_history")
    op.drop_table("incident_correlation_history")
    op.drop_table("incident_correlation_runs")
    op.drop_column("case_incidents", "removal_reason")
    op.drop_column("case_incidents", "removed_at")
    op.drop_constraint("fk_incidents_merged_into_incident", "incidents", type_="foreignkey")
    op.drop_column("incidents", "merged_into_id")
    op.drop_column("incidents", "correlation_rule_version")
    op.drop_column("incidents", "status")