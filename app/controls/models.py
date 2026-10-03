from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from app.models.base import Base

class ControlAuthorization(Base):
    __tablename__ = "control_authorizations"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_control_fingerprint"),
        CheckConstraint("outcome IN ('AUTO_ELIGIBLE','HUMAN_APPROVAL_REQUIRED','BLOCKED','ESCALATED')", name="ck_control_outcome"))
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    supervisor_review_id = Column(String, ForeignKey("supervisor_reviews.id", ondelete="CASCADE"), nullable=False)
    policy_version_id = Column(String, ForeignKey("policy_versions.id"))
    decision_id = Column(String, ForeignKey("decisions.id"), nullable=False)
    fingerprint = Column(String, nullable=False)
    outcome = Column(String, nullable=False)
    action = Column(JSON, nullable=False)
    snapshot = Column(JSON, nullable=False)
    reasons = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class ActionApproval(Base):
    __tablename__ = "action_approvals"
    __table_args__ = (UniqueConstraint("authorization_id", name="uq_action_approval_authorization"),
        CheckConstraint("status IN ('OPEN','APPROVED','REJECTED','MORE_INVESTIGATION','REVOKED')", name="ck_action_approval_status"))
    id = Column(String, primary_key=True)
    authorization_id = Column(String, ForeignKey("control_authorizations.id", ondelete="CASCADE"), nullable=False)
    assigned_role = Column(String, nullable=False)
    assigned_user = Column(String)
    status = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    human_approval_id = Column(String, ForeignKey("human_approvals.id"))
    created_at = Column(DateTime(timezone=True), nullable=False)

class ActionApprovalHistory(Base):
    __tablename__ = "action_approval_history"
    id = Column(String, primary_key=True)
    approval_id = Column(String, ForeignKey("action_approvals.id", ondelete="CASCADE"), nullable=False, index=True)
    actor = Column(String, nullable=False)
    operation = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
