from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from app.models.base import Base

class InvestigationRun(Base):
    __tablename__ = "investigation_runs"
    __table_args__ = (UniqueConstraint("task_id", "attempt", name="uq_investigation_attempt"),
        CheckConstraint("attempt >= 1", name="ck_investigation_attempt"),
        CheckConstraint("role IN ('TRANSACTION','TECHNOLOGY','RISK')", name="ck_investigation_role"),
        CheckConstraint("status IN ('RUNNING','COMPLETED','NEEDS_ADDITIONAL_EVIDENCE','ESCALATION_REQUIRED','FAILED')", name="ck_investigation_status"))
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("orchestration_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    attempt = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    context = Column(JSON, nullable=False)
    result = Column(JSON)
    telemetry = Column(JSON, nullable=False)
    error_code = Column(String)
