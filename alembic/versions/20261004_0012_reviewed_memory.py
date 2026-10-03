"""Reviewed operational memory and append-only publication provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0012"
down_revision = "20261002_0011"
branch_labels = depends_on = None


def upgrade():
    op.create_table("operational_memories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "category", name="uq_memory_case_category"))
    op.create_table("memory_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("memory_id", sa.String(), sa.ForeignKey("operational_memories.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("failure_pattern", sa.String(300), nullable=False),
        sa.Column("resolution_type", sa.String(200), nullable=False),
        sa.Column("verification_id", sa.String(), sa.ForeignKey("verification_results.id"), nullable=False),
        sa.Column("authorization_id", sa.String(), sa.ForeignKey("control_authorizations.id"), nullable=False),
        sa.Column("policy_version_id", sa.String(), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("governance_version", sa.String(), nullable=False),
        sa.Column("trust_snapshot", sa.JSON(), nullable=False),
        sa.Column("reviewer", sa.String()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("supersedes_id", sa.String(), sa.ForeignKey("memory_versions.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("memory_id", "version", name="uq_memory_version"),
        sa.CheckConstraint("version > 0", name="ck_memory_positive_version"),
        sa.CheckConstraint("status IN ('CANDIDATE','PENDING_REVIEW','ACTIVE','REJECTED','REVOKED','SUPERSEDED')", name="ck_memory_status"),
        sa.CheckConstraint("length(summary) BETWEEN 1 AND 1000 AND length(failure_pattern) <= 300", name="ck_memory_summary_bound"),
        sa.CheckConstraint("status <> 'ACTIVE' OR (reviewer IS NOT NULL AND reviewed_at IS NOT NULL)", name="ck_memory_active_review"))
    op.create_index("uq_memory_active", "memory_versions", ["memory_id"], unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_index("ix_memory_retrieval", "memory_versions", ["category", "status", "created_at", "id"])
    op.create_table("memory_evidence",
        sa.Column("version_id", sa.String(), sa.ForeignKey("memory_versions.id"), primary_key=True),
        sa.Column("evidence_id", sa.String(), sa.ForeignKey("evidence.id"), primary_key=True),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event_records.id"), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False))
    op.create_table("memory_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("version_id", sa.String(), sa.ForeignKey("memory_versions.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=False),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("replacement_id", sa.String(), sa.ForeignKey("memory_versions.id")),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_memory_reviews_version_id", "memory_reviews", ["version_id"])
    op.create_table("memory_retrievals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("version_ids", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_memory_retrievals_case_id", "memory_retrievals", ["case_id"])


def downgrade():
    # Explicit destructive downgrade of Phase 11 artifacts only. Existing source,
    # action, verification and audit records are never deleted or rewritten.
    op.drop_table("memory_retrievals")
    op.drop_table("memory_reviews")
    op.drop_table("memory_evidence")
    op.drop_table("memory_versions")
    op.drop_table("operational_memories")
