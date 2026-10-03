from sqlalchemy import Column, String, ForeignKey, JSON, DateTime, Boolean, CheckConstraint, Index
from app.models.base import Base


class ShadowEvaluation(Base):
    __tablename__ = "shadow_evaluations"
    __table_args__ = (
        CheckConstraint("mode = 'SHADOW' AND action_authorization = 'NOT_EVALUATED' AND execution_permitted = false", name="ck_shadow_nonexecution"),
        CheckConstraint("outcome IN ('WOULD_AUTO_ELIGIBLE','WOULD_HUMAN_APPROVAL_REQUIRED','WOULD_BLOCK','WOULD_ESCALATE')", name="ck_shadow_outcome"),
        Index("ix_shadow_case_time", "case_id", "created_at"),
    )
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    actor = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    action_authorization = Column(String, nullable=False)
    execution_permitted = Column(Boolean, nullable=False)
    fingerprint = Column(String, nullable=False, unique=True)
    outcome = Column(String, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
