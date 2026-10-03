"""Action-bound deterministic authorization and human approval."""
from alembic import op
import sqlalchemy as sa
revision = "20261002_0009"
down_revision = "20261002_0008"
branch_labels = depends_on = None

def upgrade():
    op.create_table("control_authorizations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("supervisor_review_id", sa.String(), sa.ForeignKey("supervisor_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_version_id", sa.String(), sa.ForeignKey("policy_versions.id")),
        sa.Column("decision_id", sa.String(), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False), sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("action", sa.JSON(), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_control_fingerprint"),
        sa.CheckConstraint("outcome IN ('AUTO_ELIGIBLE','HUMAN_APPROVAL_REQUIRED','BLOCKED','ESCALATED')", name="ck_control_outcome"))
    op.create_index("ix_control_authorizations_case_id", "control_authorizations", ["case_id"])
    op.create_table("action_approvals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("authorization_id", sa.String(), sa.ForeignKey("control_authorizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_role", sa.String(), nullable=False), sa.Column("assigned_user", sa.String()),
        sa.Column("status", sa.String(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("human_approval_id", sa.String(), sa.ForeignKey("human_approvals.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("authorization_id", name="uq_action_approval_authorization"),
        sa.CheckConstraint("status IN ('OPEN','APPROVED','REJECTED','MORE_INVESTIGATION','REVOKED')", name="ck_action_approval_status"))
    op.create_table("action_approval_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("approval_id", sa.String(), sa.ForeignKey("action_approvals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False), sa.Column("operation", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_action_approval_history_approval_id", "action_approval_history", ["approval_id"])

def downgrade():
    for table in ("action_approval_history", "action_approvals", "control_authorizations"):
        op.drop_table(table)
