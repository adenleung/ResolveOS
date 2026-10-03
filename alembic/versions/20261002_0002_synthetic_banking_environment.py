"""Synthetic banking environment tables.

Revision ID: 20261002_0002
Revises: 20261002_0001
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0002"
down_revision = "20261002_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sim_payments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("beneficiary", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("incident_key", sa.String(), nullable=True),
        sa.Column("scenario_name", sa.String(), nullable=False),
        sa.Column("processing_outcome", sa.String(), nullable=True),
        sa.Column("expected_root_cause", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_sim_payments_payment_id"), "sim_payments", ["payment_id"], unique=True)
    op.create_index(op.f("ix_sim_payments_idempotency_key"), "sim_payments", ["idempotency_key"], unique=True)
    op.create_index(op.f("ix_sim_payments_correlation_id"), "sim_payments", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_sim_payments_incident_key"), "sim_payments", ["incident_key"], unique=False)
    op.create_index(op.f("ix_sim_payments_scenario_name"), "sim_payments", ["scenario_name"], unique=False)

    op.create_table(
        "sim_ledger_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=False),
        sa.Column("ledger_transaction_id", sa.String(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["sim_payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_transaction_id"),
    )
    op.create_index(op.f("ix_sim_ledger_entries_payment_id"), "sim_ledger_entries", ["payment_id"], unique=False)

    op.create_table(
        "sim_confirmation_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["sim_payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(op.f("ix_sim_confirmation_events_payment_id"), "sim_confirmation_events", ["payment_id"], unique=False)
    op.create_index(op.f("ix_sim_confirmation_events_correlation_id"), "sim_confirmation_events", ["correlation_id"], unique=False)

    op.create_table(
        "sim_technology_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=True),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["sim_payments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sim_technology_logs_payment_id"), "sim_technology_logs", ["payment_id"], unique=False)
    op.create_index(op.f("ix_sim_technology_logs_service_name"), "sim_technology_logs", ["service_name"], unique=False)
    op.create_index(op.f("ix_sim_technology_logs_correlation_id"), "sim_technology_logs", ["correlation_id"], unique=False)

    op.create_table(
        "sim_workflow_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("payment_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("workflow_status", sa.String(), nullable=False),
        sa.Column("current_step", sa.String(), nullable=False),
        sa.Column("pending_tasks", sa.JSON(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_status", sa.String(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["sim_payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id"),
    )
    op.create_index(op.f("ix_sim_workflow_states_payment_id"), "sim_workflow_states", ["payment_id"], unique=False)

    op.create_table(
        "sim_policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("policy_code", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rule_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_code"),
    )
    op.create_index(op.f("ix_sim_policies_policy_code"), "sim_policies", ["policy_code"], unique=True)


def downgrade() -> None:
    op.drop_table("sim_policies")
    op.drop_table("sim_workflow_states")
    op.drop_table("sim_technology_logs")
    op.drop_table("sim_confirmation_events")
    op.drop_table("sim_ledger_entries")
    op.drop_table("sim_payments")
