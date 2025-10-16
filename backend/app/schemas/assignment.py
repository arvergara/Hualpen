from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, UUID4


class PlannedShiftBase(BaseModel):
    service_id: UUID4
    shift_date: datetime
    start_time: datetime
    end_time: datetime
    required_drivers: int = Field(default=1, ge=1)
    required_bus_type_id: Optional[UUID4] = None
    status: str = Field(default="pending", pattern="^(pending|assigned|confirmed|completed|cancelled)$")


class PlannedShift(PlannedShiftBase):
    id: UUID4
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DriverAssignmentBase(BaseModel):
    planned_shift_id: UUID4
    driver_id: UUID4
    position: str = Field(..., pattern="^(primary|secondary|backup)$")
    assigned_start_time: datetime
    assigned_end_time: datetime
    planned_driving_hours: Optional[Decimal] = Field(None)
    status: str = Field(default="scheduled", pattern="^(scheduled|confirmed|active|completed|cancelled|no_show)$")


class DriverAssignment(DriverAssignmentBase):
    id: UUID4
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    actual_driving_hours: Optional[Decimal] = Field(None)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DriverAssignmentUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(scheduled|confirmed|active|completed|cancelled|no_show)$")
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    actual_driving_hours: Optional[Decimal] = Field(None)


class BusAssignmentBase(BaseModel):
    planned_shift_id: UUID4
    bus_id: UUID4
    status: str = Field(default="assigned", pattern="^(assigned|active|completed|cancelled)$")


class BusAssignment(BusAssignmentBase):
    id: UUID4
    start_kilometers: Optional[int] = None
    end_kilometers: Optional[int] = None
    dead_kilometers: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusAssignmentUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(assigned|active|completed|cancelled)$")
    start_kilometers: Optional[int] = None
    end_kilometers: Optional[int] = None
    dead_kilometers: Optional[int] = None


class Assignment(BaseModel):
    id: str
    planned_shift: PlannedShift
    driver_assignment: DriverAssignment
    bus_assignment: Optional[BusAssignment] = None

    class Config:
        from_attributes = True


class AssignmentWithDetails(Assignment):
    planned_shift: Dict[str, Any]  # Include service details
    driver_assignment: Dict[str, Any]  # Include driver details
    bus_assignment: Optional[Dict[str, Any]] = None  # Include bus details

    class Config:
        from_attributes = True