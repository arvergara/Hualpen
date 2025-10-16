from sqlalchemy import Column, String, Integer, ForeignKey, Date, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
# from geoalchemy2 import Geography  # Requires PostGIS extension
import enum

from app.db.base import Base


class BusStatus(str, enum.Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    REPAIR = "repair"
    RETIRED = "retired"


class Bus(Base):
    __tablename__ = "buses"
    
    plate_number = Column(String(10), unique=True, nullable=False)
    bus_type_id = Column(UUID(as_uuid=True), ForeignKey("bus_types.id"), nullable=False)
    vin = Column(String(17), unique=True)
    
    # Vehicle information
    year = Column(Integer)
    brand = Column(String(50))
    model = Column(String(50))
    
    # Status
    status = Column(Enum(BusStatus), default=BusStatus.ACTIVE)
    # current_location = Column(Geography(geometry_type='POINT', srid=4326))  # Requires PostGIS
    current_location = Column(JSONB)  # Temporarily store as JSON {"lat": float, "lng": float}
    last_maintenance_date = Column(Date)
    next_maintenance_date = Column(Date)
    total_kilometers = Column(Integer, default=0)
    
    # Assignment
    assigned_zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id"))
    
    # Relationships
    bus_type = relationship("BusType", back_populates="buses")
    assigned_zone = relationship("Zone", back_populates="buses")
    assignments = relationship("BusAssignment", back_populates="bus")