from typing import Optional
from datetime import date, datetime
from pydantic import BaseModel, Field, UUID4


class BusTypeBase(BaseModel):
    code: str
    name: str
    capacity: int
    fuel_type: str
    cost_per_km: Optional[float] = None


class BusType(BusTypeBase):
    id: UUID4

    class Config:
        from_attributes = True


class BusBase(BaseModel):
    plate_number: str = Field(..., max_length=10)
    bus_type_id: UUID4
    vin: Optional[str] = Field(None, max_length=17)
    year: Optional[int] = None
    brand: Optional[str] = Field(None, max_length=50)
    model: Optional[str] = Field(None, max_length=50)
    status: str = Field(default="active", pattern="^(active|maintenance|repair|retired)$")
    assigned_zone_id: Optional[UUID4] = None
    total_kilometers: int = Field(default=0, ge=0)
    last_maintenance_date: Optional[date] = None
    next_maintenance_date: Optional[date] = None


class BusCreate(BusBase):
    pass


class BusUpdate(BaseModel):
    plate_number: Optional[str] = Field(None, max_length=10)
    bus_type_id: Optional[UUID4] = None
    vin: Optional[str] = Field(None, max_length=17)
    year: Optional[int] = None
    brand: Optional[str] = Field(None, max_length=50)
    model: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, pattern="^(active|maintenance|repair|retired)$")
    assigned_zone_id: Optional[UUID4] = None
    total_kilometers: Optional[int] = Field(None, ge=0)
    last_maintenance_date: Optional[date] = None
    next_maintenance_date: Optional[date] = None


class Bus(BusBase):
    id: UUID4
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusWithDetails(Bus):
    bus_type: Optional[BusType] = None
    assigned_zone: Optional[dict] = None  # Zone schema would be defined separately
    current_location: Optional[dict] = None  # {"lat": float, "lng": float}

    class Config:
        from_attributes = True