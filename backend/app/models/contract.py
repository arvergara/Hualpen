from sqlalchemy import Column, String, Date, Numeric, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    BIWEEKLY = "biweekly"
    WEEKLY = "weekly"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class Contract(Base):
    __tablename__ = "contracts"
    
    contract_number = Column(String(50), unique=True, nullable=False)
    client_name = Column(String(255), nullable=False)
    client_rut = Column(String(12))
    
    # Contract dates
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    
    # Financial information
    monthly_value = Column(Numeric(15, 2))
    currency = Column(String(3), default="CLP")
    billing_cycle = Column(Enum(BillingCycle))
    
    # SLA
    sla_on_time_performance = Column(Numeric(5, 2))  # Percentage
    sla_max_cancellations = Column(Integer)
    sla_min_availability = Column(Numeric(5, 2))  # Percentage
    
    # Status
    status = Column(Enum(ContractStatus), default=ContractStatus.ACTIVE)
    
    # Metadata
    created_by = Column(UUID(as_uuid=True))
    
    # Relationships
    services = relationship("Service", back_populates="contract", cascade="all, delete-orphan")