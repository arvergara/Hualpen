from sqlalchemy import Column, String, Integer, Boolean, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
# from geoalchemy2 import Geography  # Requires PostGIS extension
import enum

from app.db.base import Base


class LicenseType(Base):
    __tablename__ = "license_types"
    
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    vehicle_types = Column(ARRAY(String))
    max_passengers = Column(Integer)
    
    # Relationships
    driver_licenses = relationship("DriverLicense", back_populates="license_type")


class WorkModality(Base):
    __tablename__ = "work_modalities"
    
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(50), nullable=False)
    work_days = Column(Integer, nullable=False)
    rest_days = Column(Integer, nullable=False)
    allowed_urban = Column(Boolean, default=True)
    description = Column(String)
    
    # Relationships
    drivers = relationship("Driver", back_populates="work_modality")


class FuelType(str, enum.Enum):
    DIESEL = "diesel"
    ELECTRIC = "electric"
    HYBRID = "hybrid"


class BusType(Base):
    __tablename__ = "bus_types"
    
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=False)
    fuel_type = Column(Enum(FuelType))
    cost_per_km = Column(Numeric(10, 2))
    features = Column(JSONB)  # { wifi: true, ac: true, accessibility: true }
    
    # Relationships
    buses = relationship("Bus", back_populates="bus_type")


class Zone(Base):
    __tablename__ = "zones"
    
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    region = Column(String(100))
    # polygon = Column(Geography(geometry_type='POLYGON', srid=4326))  # Geographic boundaries - requires PostGIS
    polygon = Column(JSONB)  # Temporarily store as JSON until PostGIS is configured
    allow_driver_sharing = Column(Boolean, default=True)
    max_dead_kilometers = Column(Integer, default=30)
    
    # Relationships
    drivers = relationship("Driver", back_populates="base_zone")
    services = relationship("Service", back_populates="zone")
    buses = relationship("Bus", back_populates="assigned_zone")