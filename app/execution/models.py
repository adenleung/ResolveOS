from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, JSON, String, UniqueConstraint
from app.models.base import Base

class ExecutionOperation(Base):
    __tablename__ = "execution_operations"
    __table_args__ = (UniqueConstraint("authorization_id", name="uq_execution_authorization"),
                     UniqueConstraint("logical_key", name="uq_execution_logical_key"))
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    authorization_id = Column(String, ForeignKey("control_authorizations.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(String, ForeignKey("actions.id"), nullable=False)
    logical_key = Column(String, nullable=False)
    status = Column(String, nullable=False)
    baseline = Column(JSON, nullable=False)
    event_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))


class CounterfactualSimulation(Base):
    """Immutable report per preview / queued operation; not an authorization."""
    __tablename__ = "counterfactual_simulations"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_counterfactual_operation"),
        CheckConstraint("outcome IN ('PASS','BLOCKED')", name="ck_counterfactual_outcome"),
    )
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    authorization_id = Column(String, ForeignKey("control_authorizations.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_id = Column(String, ForeignKey("execution_operations.id"), nullable=True)
    outcome = Column(String, nullable=False)
    projection = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
