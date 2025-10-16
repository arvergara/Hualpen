from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import UUID4

from app.db.session import get_async_db
from app.models.bus import Bus as BusModel
from app.schemas.bus import Bus, BusCreate, BusUpdate, BusWithDetails

router = APIRouter()


@router.get("/", response_model=dict)
async def get_buses(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[List[str]] = Query(None),
    zone: Optional[List[UUID4]] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of buses with pagination and filters
    """
    query = select(BusModel).options(
        selectinload(BusModel.bus_type),
        selectinload(BusModel.assigned_zone)
    )
    
    # Apply filters
    if search:
        query = query.where(
            (BusModel.plate_number.ilike(f"%{search}%")) |
            (BusModel.brand.ilike(f"%{search}%")) |
            (BusModel.model.ilike(f"%{search}%"))
        )
    
    if status:
        query = query.where(BusModel.status.in_(status))
    
    if zone:
        query = query.where(BusModel.assigned_zone_id.in_(zone))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar()
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    buses = result.scalars().all()
    
    # Convert SQLAlchemy models to Pydantic models
    bus_schemas = [Bus.from_orm(bus) for bus in buses]
    
    return {
        "data": bus_schemas,
        "totalItems": total_items,
        "totalPages": (total_items + limit - 1) // limit,
        "currentPage": (skip // limit) + 1,
        "pageSize": limit
    }


@router.get("/{bus_id}", response_model=BusWithDetails)
async def get_bus(
    bus_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific bus by ID
    """
    query = select(BusModel).where(BusModel.id == bus_id).options(
        selectinload(BusModel.bus_type),
        selectinload(BusModel.assigned_zone)
    )
    
    result = await db.execute(query)
    bus = result.scalar()
    
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")
    
    return bus


@router.post("/", response_model=Bus)
async def create_bus(
    bus_data: BusCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new bus
    """
    # Check if plate number already exists
    existing = await db.execute(
        select(BusModel).where(BusModel.plate_number == bus_data.plate_number)
    )
    if existing.scalar():
        raise HTTPException(status_code=400, detail="Plate number already exists")
    
    bus = BusModel(**bus_data.dict())
    db.add(bus)
    await db.commit()
    await db.refresh(bus)
    
    return bus


@router.put("/{bus_id}", response_model=Bus)
async def update_bus(
    bus_id: UUID4,
    bus_update: BusUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Actualizar información de un bus
    """
    result = await db.execute(select(BusModel).where(BusModel.id == bus_id))
    bus = result.scalar()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")
    update_data = bus_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bus, field, value)
    await db.commit()
    await db.refresh(bus)
    return bus


@router.put("/{bus_id}/location", response_model=dict)
async def update_bus_location(
    bus_id: UUID4,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update bus current location
    """
    from geoalchemy2 import func as geo_func
    
    result = await db.execute(select(BusModel).where(BusModel.id == bus_id))
    bus = result.scalar()
    
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")
    
    # Update location using PostGIS
    bus.current_location = geo_func.ST_SetSRID(
        geo_func.ST_MakePoint(longitude, latitude), 4326
    )
    
    await db.commit()
    
    return {
        "message": "Location updated successfully",
        "bus_id": str(bus_id),
        "latitude": latitude,
        "longitude": longitude
    }


@router.delete("/{bus_id}")
async def delete_bus(
    bus_id: UUID4,
    hard: bool = False,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Eliminar un bus (por defecto soft delete, pero permite hard delete si se pasa hard=true)
    """
    result = await db.execute(select(BusModel).where(BusModel.id == bus_id))
    bus = result.scalar()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")
    if hard:
        await db.delete(bus)
        await db.commit()
        return {"message": "Bus deleted permanently"}
    else:
        bus.status = "retired"
        await db.commit()
        return {"message": "Bus retired successfully"}