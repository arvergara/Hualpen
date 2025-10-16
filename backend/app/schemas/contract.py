from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, UUID4


class ContractBase(BaseModel):
    contract_number: str = Field(..., max_length=50)
    client_name: str = Field(..., max_length=255)
    client_rut: Optional[str] = Field(None, max_length=12)
    start_date: date
    end_date: Optional[date] = None
    monthly_value: Optional[Decimal] = Field(None)
    currency: str = Field(default="CLP", max_length=3)
    billing_cycle: Optional[str] = Field(default="monthly", pattern="^(monthly|biweekly|weekly)$")
    sla_on_time_performance: Optional[Decimal] = Field(None, ge=0, le=100)
    sla_max_cancellations: Optional[int] = Field(None, ge=0)
    sla_min_availability: Optional[Decimal] = Field(None, ge=0, le=100)
    status: str = Field(default="draft", pattern="^(draft|active|suspended|terminated)$")


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    contract_number: Optional[str] = Field(None, max_length=50)
    client_name: Optional[str] = Field(None, max_length=255)
    client_rut: Optional[str] = Field(None, max_length=12)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    monthly_value: Optional[Decimal] = Field(None)
    currency: Optional[str] = Field(None, max_length=3)
    billing_cycle: Optional[str] = Field(None, pattern="^(monthly|biweekly|weekly)$")
    sla_on_time_performance: Optional[Decimal] = Field(None, ge=0, le=100)
    sla_max_cancellations: Optional[int] = Field(None, ge=0)
    sla_min_availability: Optional[Decimal] = Field(None, ge=0, le=100)
    status: Optional[str] = Field(None, pattern="^(draft|active|suspended|terminated)$")


class Contract(ContractBase):
    id: UUID4
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ServiceSummary(BaseModel):
    id: UUID4
    service_code: str
    name: str
    origin_name: str
    destination_name: str
    status: str

    class Config:
        from_attributes = True


class ContractWithServices(Contract):
    services: List[ServiceSummary] = []

    class Config:
        from_attributes = True