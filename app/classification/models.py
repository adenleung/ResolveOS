from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint

from app.models.base import Base


class AssessmentHistory(Base):
    __tablename__ = "assessment_history"
    __table_args__ = (UniqueConstraint("exception_id", "revision", name="uq_assessment_exception_revision"),)

    id = Column(String, primary_key=True)
    exception_id = Column(String, ForeignKey("exceptions.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    assessment_version = Column(String, nullable=False)
    classification_source = Column(String, nullable=False)
    operational_eligible = Column(Boolean, nullable=False)
    change_reason = Column(String, nullable=False)
    assessment = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)