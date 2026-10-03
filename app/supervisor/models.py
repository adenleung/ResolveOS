from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from app.models.base import Base

class SupervisorReview(Base):
    __tablename__ = "supervisor_reviews"
    __table_args__ = (UniqueConstraint("task_id", "attempt", name="uq_supervisor_attempt"),
                     CheckConstraint("attempt >= 1", name="ck_supervisor_attempt"))
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("orchestration_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    attempt = Column(Integer, nullable=False)
    outcome = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    snapshot = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    telemetry = Column(JSON, nullable=False)
