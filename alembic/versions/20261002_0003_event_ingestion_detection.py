"""Durable event ingestion and deterministic exception detection.

Revision ID: 20261002_0003
Revises: 20261002_0002
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0003"
down_revision = "20261002_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exceptions", sa.Column("detection_key", sa.String(), nullable=True))
    op.add_column("exceptions", sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "exceptions",
        sa.Column("condition_status", sa.String(), nullable=False, server_default="OPEN"),
    )
    op.create_index("ix_exceptions_detection_key", "exceptions", ["detection_key"], unique=True)

    op.create_table(
        "event_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("entity_reference", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("source_record_reference", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processing_status", sa.String(), nullable=False),
        sa.Column("processing_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("duplicate_receipts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "event_id", name="uq_event_source_event_id"),
    )
    op.create_index("ix_event_records_source_system", "event_records", ["source_system"])
    op.create_index("ix_event_records_event_type", "event_records", ["event_type"])
    op.create_index("ix_event_records_entity_reference", "event_records", ["entity_reference"])
    op.create_index("ix_event_records_correlation_id", "event_records", ["correlation_id"])
    op.create_index("ix_event_records_occurred_at", "event_records", ["occurred_at"])
    op.create_index("ix_event_records_processing_status", "event_records", ["processing_status"])

    op.create_table(
        "ingestion_errors",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_record_reference", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_errors_source_system", "ingestion_errors", ["source_system"])

    op.create_table(
        "exception_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("exception_id", sa.String(), nullable=False),
        sa.Column("event_record_id", sa.String(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exception_id"], ["exceptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_record_id"], ["event_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exception_id", "event_record_id", name="uq_exception_event_evidence"),
    )
    op.create_index("ix_exception_evidence_exception_id", "exception_evidence", ["exception_id"])
    op.create_index("ix_exception_evidence_event_record_id", "exception_evidence", ["event_record_id"])

    op.create_table(
        "detection_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("exception_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["exception_id"], ["exceptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detection_history_exception_id", "detection_history", ["exception_id"])


def downgrade() -> None:
    op.drop_table("detection_history")
    op.drop_table("exception_evidence")
    op.drop_table("ingestion_errors")
    op.drop_table("event_records")
    op.drop_index("ix_exceptions_detection_key", table_name="exceptions")
    op.drop_column("exceptions", "condition_status")
    op.drop_column("exceptions", "detected_at")
    op.drop_column("exceptions", "detection_key")