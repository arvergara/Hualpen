from sqlalchemy import Column, String, Date, ForeignKey, Numeric, Integer, Enum, Boolean, Time, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class RunType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MANUAL = "manual"


class OptimizationStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"
    
    run_type = Column(Enum(RunType))
    
    # Optimization period
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # Parameters used
    parameters = Column(JSONB, nullable=False)
    constraints = Column(JSONB, nullable=False)
    
    # Results
    status = Column(Enum(OptimizationStatus))
    solution_quality = Column(Numeric(5, 2))  # 0-100
    compute_time_seconds = Column(Integer)
    
    # Result metrics
    total_cost = Column(Numeric(15, 2))
    driver_utilization = Column(Numeric(5, 2))
    services_covered = Column(Numeric(5, 2))
    compliance_score = Column(Numeric(5, 2))
    
    # Details
    assignments_created = Column(Integer, default=0)
    violations_detected = Column(Integer, default=0)
    warnings_generated = Column(Integer, default=0)
    
    # Metadata
    completed_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True))
    
    # Relationships
    results = relationship("OptimizationResult", back_populates="optimization_run", cascade="all, delete-orphan")


class OptimizationResult(Base):
    __tablename__ = "optimization_results"
    
    optimization_run_id = Column(UUID(as_uuid=True), ForeignKey("optimization_runs.id"), nullable=False)
    
    # Proposed assignment
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"))
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"))
    shift_date = Column(Date, nullable=False)
    
    # Details
    position = Column(String(20))
    start_time = Column(Time)
    end_time = Column(Time)
    
    # Status
    accepted = Column(Boolean, default=False)
    rejection_reason = Column(Text)
    
    # Relationships
    optimization_run = relationship("OptimizationRun", back_populates="results")
    driver = relationship("Driver")
    service = relationship("Service")