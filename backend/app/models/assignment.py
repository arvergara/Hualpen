from sqlalchemy import Column, String, ForeignKey, Numeric, Integer, Enum, DateTime, Date, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class ShiftStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PlannedShift(Base):
    __tablename__ = "planned_shifts"
    
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    shift_date = Column(Date, nullable=False)
    
    # Shift schedule
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Requirements
    required_drivers = Column(Integer, default=1)
    required_bus_type_id = Column(UUID(as_uuid=True), ForeignKey("bus_types.id"))
    
    # Status
    status = Column(Enum(ShiftStatus), default=ShiftStatus.PENDING)
    
    # Relationships
    service = relationship("Service", back_populates="planned_shifts")
    required_bus_type = relationship("BusType")
    driver_assignments = relationship("DriverAssignment", back_populates="planned_shift")
    bus_assignments = relationship("BusAssignment", back_populates="planned_shift")


class DriverPosition(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    BACKUP = "backup"


class AssignmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class DriverAssignment(Base):
    __tablename__ = "driver_assignments"
    
    planned_shift_id = Column(UUID(as_uuid=True), ForeignKey("planned_shifts.id"), nullable=False)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    
    # Role in shift
    position = Column(Enum(DriverPosition), nullable=False)
    
    # Assigned schedule (may differ from shift for secondary drivers)
    assigned_start_time = Column(DateTime(timezone=True), nullable=False)
    assigned_end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Planned hours and breaks
    planned_driving_hours = Column(Numeric(4, 2))
    planned_breaks = Column(JSONB)  # [{start_time, end_time, duration, type}]
    
    # Status
    status = Column(Enum(AssignmentStatus), default=AssignmentStatus.SCHEDULED)
    
    # Actual tracking
    actual_start_time = Column(DateTime(timezone=True))
    actual_end_time = Column(DateTime(timezone=True))
    actual_driving_hours = Column(Numeric(4, 2))
    actual_breaks = Column(JSONB)
    
    # Metadata
    assigned_by = Column(UUID(as_uuid=True))
    
    # Relationships
    planned_shift = relationship("PlannedShift", back_populates="driver_assignments")
    driver = relationship("Driver", back_populates="assignments")


class BusAssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BusAssignment(Base):
    __tablename__ = "bus_assignments"
    
    planned_shift_id = Column(UUID(as_uuid=True), ForeignKey("planned_shifts.id"), nullable=False)
    bus_id = Column(UUID(as_uuid=True), ForeignKey("buses.id"), nullable=False)
    
    # Mileage
    start_kilometers = Column(Integer)
    end_kilometers = Column(Integer)
    dead_kilometers = Column(Integer)  # Empty kilometers
    
    # Status
    status = Column(Enum(BusAssignmentStatus), default=BusAssignmentStatus.ASSIGNED)
    
    # Relationships
    planned_shift = relationship("PlannedShift", back_populates="bus_assignments")
    bus = relationship("Bus", back_populates="assignments")