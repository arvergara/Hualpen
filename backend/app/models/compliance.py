from sqlalchemy import Column, String, ForeignKey, Numeric, Integer, Enum, Date, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class ViolationSeverity(str, enum.Enum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class ViolationStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    APPEALED = "appealed"


class ComplianceViolation(Base):
    __tablename__ = "compliance_violations"
    
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"))
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("driver_assignments.id"))
    violation_date = Column(Date, nullable=False)
    
    # Type and severity
    violation_type = Column(String(50), nullable=False)
    severity = Column(Enum(ViolationSeverity))
    
    # Details
    description = Column(Text, nullable=False)
    regulation_reference = Column(String(100))  # Reference to law/regulation
    
    # Impact
    fine_amount = Column(Numeric(10, 2))
    fine_utm = Column(Numeric(5, 2))
    
    # Resolution
    status = Column(Enum(ViolationStatus), default=ViolationStatus.OPEN)
    resolution_date = Column(Date)
    resolution_notes = Column(Text)
    
    # Metadata
    created_by = Column(UUID(as_uuid=True))
    
    # Relationships
    driver = relationship("Driver", back_populates="violations")
    assignment = relationship("DriverAssignment")


class DriverHoursLog(Base):
    __tablename__ = "driver_hours_log"
    
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    log_date = Column(Date, nullable=False)
    
    # Hours worked
    regular_hours = Column(Numeric(4, 2), default=0)
    overtime_hours = Column(Numeric(4, 2), default=0)
    night_hours = Column(Numeric(4, 2), default=0)
    holiday_hours = Column(Numeric(4, 2), default=0)
    
    # Additional metrics
    driving_hours = Column(Numeric(4, 2), default=0)
    break_time_minutes = Column(Integer, default=0)
    services_completed = Column(Integer, default=0)
    
    # Relationships
    driver = relationship("Driver", back_populates="hours_logs")


class ServiceMetric(Base):
    __tablename__ = "service_metrics"
    
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    metric_date = Column(Date, nullable=False)
    
    # Compliance metrics
    trips_scheduled = Column(Integer, default=0)
    trips_completed = Column(Integer, default=0)
    trips_cancelled = Column(Integer, default=0)
    trips_delayed = Column(Integer, default=0)
    
    # Efficiency metrics
    total_passengers = Column(Integer, default=0)
    total_kilometers = Column(Numeric(10, 2), default=0)
    dead_kilometers = Column(Numeric(10, 2), default=0)
    fuel_consumed_liters = Column(Numeric(10, 2), default=0)
    
    # Time metrics
    total_delay_minutes = Column(Integer, default=0)
    average_delay_minutes = Column(Numeric(5, 2), default=0)
    on_time_performance = Column(Numeric(5, 2), default=0)  # Percentage
    
    # Relationships
    service = relationship("Service", back_populates="metrics")