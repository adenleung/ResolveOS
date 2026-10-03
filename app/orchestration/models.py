from datetime import datetime, timezone

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index,
                        Integer, JSON, String, Text, UniqueConstraint, text)
from app.models.base import Base


def now_utc():
    return datetime.now(timezone.utc)


class WorkTask(Base):
    __tablename__ = "orchestration_tasks"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10", name="ck_task_attempts"),
        CheckConstraint("status IN ('PENDING','WAITING_HANDLER','RUNNING','RETRY_WAIT','COMPLETED','DEAD_LETTER','CANCELLED')", name="ck_task_status"),
        CheckConstraint("(status = 'RUNNING' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status <> 'RUNNING' AND lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)", name="ck_task_lease"),
        Index("ix_tasks_poll", "status", "scheduled_at", "priority", "created_at"),
        Index("ix_tasks_lease", "status", "lease_expires_at"),
        Index("ix_tasks_deadline", "status", "deadline"),
        Index("ix_tasks_case_history", "case_id", "created_at"),
        Index("ix_tasks_incident", "incident_id", "status"),
        Index("ix_tasks_ready_priority", "priority", "scheduled_at", "created_at", "id",
              postgresql_where=text("status IN ('PENDING','RETRY_WAIT')")),
        Index("ix_tasks_ready_age", "created_at", "id",
              postgresql_where=text("status IN ('PENDING','RETRY_WAIT')")),
    )
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=True)
    task_type = Column(String, nullable=False)
    task_version = Column(String, nullable=False)
    workflow_version = Column(String, nullable=False)
    status = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    priority = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False)
    lease_owner = Column(String, nullable=True)
    lease_token = Column(String, nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)


class TaskConsumer(Base):
    __tablename__ = "orchestration_task_consumers"
    __table_args__ = (UniqueConstraint("task_id", "case_id", name="uq_task_consumer"),
                     Index("ix_task_consumers_case", "case_id", "active"))
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("orchestration_tasks.id"), nullable=False)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    assessment_ids = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)


class TaskHistory(Base):
    __tablename__ = "orchestration_task_history"
    __table_args__ = (Index("ix_task_history_task", "task_id", "created_at"),)
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("orchestration_tasks.id"), nullable=False)
    event_type = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False)
    details = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)


class WorkflowReview(Base):
    __tablename__ = "workflow_reviews"
    __table_args__ = (CheckConstraint("status IN ('OPEN','APPROVED','REJECTED','MORE_INVESTIGATION','EXPIRED','SUPERSEDED')", name="ck_review_status"),
                     Index("ix_reviews_queue", "status", "deadline"), Index("ix_reviews_case", "case_id", "created_at"))
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    task_id = Column(String, ForeignKey("orchestration_tasks.id"), nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="OPEN")
    assigned_role = Column(String, nullable=False)
    assigned_reviewer = Column(String, nullable=True)
    reason = Column(Text, nullable=False)
    assessment_ids = Column(JSON, nullable=False)
    evidence_references = Column(JSON, nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    decided_at = Column(DateTime(timezone=True), nullable=True)


class ReviewHistory(Base):
    __tablename__ = "workflow_review_history"
    __table_args__ = (Index("ix_review_history_review", "review_id", "created_at"),)
    id = Column(String, primary_key=True)
    review_id = Column(String, ForeignKey("workflow_reviews.id"), nullable=False)
    actor = Column(String, nullable=False)
    operation = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    details = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
