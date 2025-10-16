from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, UUID4
from app.models.catalog import FuelType


class LicenseTypeBase(BaseModel):
    code: str
    name: str
    vehicle_types: List[str]
    max_passengers: Optional[int] = None


class LicenseTypeCreate(LicenseTypeBase):
    pass


class LicenseType(LicenseTypeBase):
    id: UUID4
    created_at: datetime

    class Config:
        orm_mode = True


class WorkModalityBase(BaseModel):
    code: str
    name: str
    work_days: int
    rest_days: int
    allowed_urban: bool = True
    description: Optional[str] = None


class WorkModalityCreate(WorkModalityBase):
    pass


class WorkModality(WorkModalityBase):
    id: UUID4
    created_at: datetime

    class Config:
        orm_mode = True


class BusTypeBase(BaseModel):
    code: str
    name: str
    capacity: int
    fuel_type: Optional[FuelType] = None
    cost_per_km: Optional[float] = None
    features: Optional[Dict[str, Any]] = None


class BusTypeCreate(BusTypeBase):
    pass


class BusType(BusTypeBase):
    id: UUID4
    created_at: datetime

    class Config:
        orm_mode = True


class ZoneBase(BaseModel):
    code: str
    name: str
    region: Optional[str] = None
    allow_driver_sharing: bool = True
    max_dead_kilometers: int = 30


class ZoneCreate(ZoneBase):
    polygon: Optional[Dict[str, Any]] = None  # GeoJSON polygon


class Zone(ZoneBase):
    id: UUID4
    polygon: Optional[Dict[str, Any]] = None  # GeoJSON representation
    created_at: datetime

    class Config:
        orm_mode = True


# Import to avoid circular dependency
from datetime import datetime