from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import UUID4, BaseModel
from datetime import date, time, datetime

from app.db.session import get_async_db
from app.models.service import Service as ServiceModel
from app.services.service_service import ServiceService

router = APIRouter()


class ServiceBase(BaseModel):
    contract_id: UUID4
    service_code: str
    name: str
    origin_name: str
    destination_name: str
    distance_km: float
    estimated_duration_minutes: int
    zone_id: Optional[UUID4] = None
    is_urban: bool = True
    required_bus_type_id: Optional[UUID4] = None


class ServiceCreate(ServiceBase):
    origin_location: dict  # GeoJSON point
    destination_location: dict  # GeoJSON point
    route_path: Optional[dict] = None  # GeoJSON linestring


class Service(ServiceBase):
    id: UUID4
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ServiceScheduleCreate(BaseModel):
    service_id: UUID4
    start_time: time
    end_time: time
    frequency_minutes: Optional[int] = None
    operation_days: List[int]  # 0-6 (Sunday-Saturday)
    effective_from: date
    effective_until: Optional[date] = None


@router.get("/")
async def get_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    zone_id: Optional[UUID4] = None,
    contract_id: Optional[UUID4] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of services with optional filters and pagination
    """
    base_query = select(ServiceModel)
    
    # Apply filters
    if zone_id:
        base_query = base_query.where(ServiceModel.zone_id == zone_id)
    if contract_id:
        base_query = base_query.where(ServiceModel.contract_id == contract_id)
    if status:
        base_query = base_query.where(ServiceModel.status == status)
    if search:
        base_query = base_query.where(
            (ServiceModel.name.ilike(f"%{search}%")) |
            (ServiceModel.service_code.ilike(f"%{search}%")) |
            (ServiceModel.origin_name.ilike(f"%{search}%")) |
            (ServiceModel.destination_name.ilike(f"%{search}%"))
        )
    
    # Count total items
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0
    
    # Apply pagination
    query = base_query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    services = result.scalars().all()
    
    # Convert SQLAlchemy models to Pydantic models
    service_schemas = [Service.from_orm(service) for service in services]
    
    # Return paginated response
    return {
        "data": service_schemas,
        "totalItems": total_count,
        "totalPages": (total_count + limit - 1) // limit,
        "currentPage": (skip // limit) + 1,
        "pageSize": limit
    }


@router.post("/", response_model=Service)
async def create_service(
    service_data: ServiceCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new service
    """
    service_service = ServiceService(db)
    
    try:
        service = await service_service.create_service(service_data)
        return service
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{service_id}", response_model=Service)
async def get_service(
    service_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get service details by ID
    """
    query = select(ServiceModel).where(ServiceModel.id == service_id)
    result = await db.execute(query)
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return service


@router.put("/{service_id}", response_model=Service)
async def update_service(
    service_id: UUID4,
    service_update: ServiceBase,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Actualizar información de un servicio
    """
    service_service = ServiceService(db)
    try:
        service = await service_service.update_service(service_id, service_update)
        return service
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/{service_id}")
async def delete_service(
    service_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Eliminar un servicio (borrado físico)
    """
    service_service = ServiceService(db)
    try:
        await service_service.delete_service(service_id)
        return {"message": "Service deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{service_id}/schedules")
async def add_service_schedule(
    service_id: UUID4,
    schedule: ServiceScheduleCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Add a schedule to a service
    """
    service_service = ServiceService(db)
    
    try:
        result = await service_service.add_schedule(service_id, schedule)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{service_id}/metrics")
async def get_service_metrics(
    service_id: UUID4,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get service performance metrics for a date range
    """
    service_service = ServiceService(db)
    
    try:
        metrics = await service_service.get_service_metrics(
            service_id, start_date, end_date
        )
        return metrics
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{service_id}/coverage")
async def get_service_coverage(
    service_id: UUID4,
    date: date,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get service coverage details for a specific date
    
    Shows which shifts are assigned, pending, or uncovered.
    """
    service_service = ServiceService(db)
    
    try:
        coverage = await service_service.get_service_coverage(service_id, date)
        return coverage
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{service_id}/stops")
async def add_service_stops(
    service_id: UUID4,
    stops: List[dict],
    db: AsyncSession = Depends(get_async_db)
):
    """
    Add stops to a service route
    """
    service_service = ServiceService(db)
    
    try:
        result = await service_service.add_stops(service_id, stops)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{service_id}/status")
async def update_service_status(
    service_id: UUID4,
    status: str,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update service status (active, suspended, terminated)
    """
    valid_statuses = ["active", "suspended", "terminated"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Valid options: {', '.join(valid_statuses)}"
        )
    
    service_service = ServiceService(db)
    
    try:
        result = await service_service.update_status(service_id, status, reason)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Import after defining to avoid circular imports
from datetime import datetime