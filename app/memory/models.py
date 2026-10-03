from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from app.models.base import Base


class OperationalMemory(Base):
    __tablename__ = "operational_memories"
    __table_args__ = (UniqueConstraint("case_id", "category", name="uq_memory_case_category"),)
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    category = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class MemoryVersion(Base):
    __tablename__ = "memory_versions"
    __table_args__ = (
        UniqueConstraint("memory_id", "version", name="uq_memory_version"),
        CheckConstraint("version > 0", name="ck_memory_positive_version"),
        CheckConstraint("status IN ('CANDIDATE','PENDING_REVIEW','ACTIVE','REJECTED','REVOKED','SUPERSEDED')", name="ck_memory_status"),
        CheckConstraint("length(summary) BETWEEN 1 AND 1000 AND length(failure_pattern) <= 300", name="ck_memory_summary_bound"),
        CheckConstraint("status <> 'ACTIVE' OR (reviewer IS NOT NULL AND reviewed_at IS NOT NULL)", name="ck_memory_active_review"),
        Index("uq_memory_active", "memory_id", unique=True, postgresql_where=text("status = 'ACTIVE'"), sqlite_where=text("status = 'ACTIVE'")),
        Index("ix_memory_retrieval", "category", "status", "created_at", "id"),
    )
    id = Column(String, primary_key=True)
    memory_id = Column(String, ForeignKey("operational_memories.id"), nullable=False)
    version = Column(Integer, nullable=False)
    category = Column(String(200), nullable=False)
    status = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    failure_pattern = Column(String(300), nullable=False)
    resolution_type = Column(String(200), nullable=False)
    verification_id = Column(String, ForeignKey("verification_results.id"), nullable=False)
    authorization_id = Column(String, ForeignKey("control_authorizations.id"), nullable=False)
    policy_version_id = Column(String, ForeignKey("policy_versions.id"), nullable=False)
    governance_version = Column(String, nullable=False)
    trust_snapshot = Column(JSON, nullable=False)
    reviewer = Column(String)
    reviewed_at = Column(DateTime(timezone=True))
    supersedes_id = Column(String, ForeignKey("memory_versions.id"))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class MemoryEvidence(Base):
    __tablename__ = "memory_evidence"
    version_id = Column(String, ForeignKey("memory_versions.id"), primary_key=True)
    evidence_id = Column(String, ForeignKey("evidence.id"), primary_key=True)
    event_id = Column(String, ForeignKey("event_records.id"), nullable=False)
    fingerprint = Column(String, nullable=False)


class MemoryReview(Base):
    __tablename__ = "memory_reviews"
    id = Column(String, primary_key=True)
    version_id = Column(String, ForeignKey("memory_versions.id"), nullable=False, index=True)
    actor = Column(String, nullable=False)
    operation = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    previous_status = Column(String, nullable=False)
    new_status = Column(String, nullable=False)
    replacement_id = Column(String, ForeignKey("memory_versions.id"))
    content_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class MemoryRetrieval(Base):
    __tablename__ = "memory_retrievals"
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    actor = Column(String, nullable=False)
    category = Column(String(200), nullable=False)
    version_ids = Column(JSON, nullable=False)
    limits = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
