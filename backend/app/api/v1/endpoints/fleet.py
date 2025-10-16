from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_async_db as get_db
from app.models.bus import Bus
from app.models.catalog import BusType
from datetime import datetime, date

router = APIRouter()

@router.get("/summary")
async def get_fleet_summary(
    db: AsyncSession = Depends(get_db)
):
    """Obtener resumen de la flota disponible"""
    try:
        # Contar buses por tipo
        bus_query = select(
            BusType.code,
            BusType.capacity,
            func.count(Bus.id).label('count')
        ).join(
            Bus, Bus.bus_type_id == BusType.id
        ).filter(
            Bus.status == 'active'
        ).group_by(BusType.code, BusType.capacity)
        
        result = await db.execute(bus_query)
        bus_counts = result.all()
        
        # Mapear a la estructura esperada
        fleet_summary = {
            "large": {"available": 0, "capacity": 40, "used": 0},
            "medium": {"available": 0, "capacity": 20, "used": 0},
            "small": {"available": 0, "capacity": 10, "used": 0}
        }
        
        for bus_type, capacity, count in bus_counts:
            if capacity >= 35:
                fleet_summary["large"]["available"] = count
            elif capacity >= 15:
                fleet_summary["medium"]["available"] = count
            else:
                fleet_summary["small"]["available"] = count
        
        # Si no hay buses en la BD, usar valores por defecto
        if not bus_counts:
            fleet_summary = {
                "large": {"available": 15, "capacity": 40, "used": 0},
                "medium": {"available": 20, "capacity": 20, "used": 0},
                "small": {"available": 25, "capacity": 10, "used": 0}
            }
        
        return fleet_summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/availability")
async def get_fleet_availability(
    shift: str = Query(..., description="Shift ID (morning, afternoon, night)"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db)
):
    """Obtener disponibilidad de la flota para un turno específico"""
    try:
        # Por ahora retornar la misma estructura que summary
        # En el futuro, esto podría calcular la disponibilidad real basada en asignaciones
        fleet_summary = await get_fleet_summary(db)
        
        # Simular uso basado en el turno
        if shift == "morning":
            fleet_summary["large"]["used"] = min(8, fleet_summary["large"]["available"])
            fleet_summary["medium"]["used"] = min(12, fleet_summary["medium"]["available"])
            fleet_summary["small"]["used"] = min(15, fleet_summary["small"]["available"])
        elif shift == "afternoon":
            fleet_summary["large"]["used"] = min(7, fleet_summary["large"]["available"])
            fleet_summary["medium"]["used"] = min(10, fleet_summary["medium"]["available"])
            fleet_summary["small"]["used"] = min(12, fleet_summary["small"]["available"])
        else:  # night
            fleet_summary["large"]["used"] = min(5, fleet_summary["large"]["available"])
            fleet_summary["medium"]["used"] = min(8, fleet_summary["medium"]["available"])
            fleet_summary["small"]["used"] = min(10, fleet_summary["small"]["available"])
        
        return fleet_summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/buses")
async def get_all_buses(
    status: Optional[str] = Query(None, description="Filter by status"),
    bus_type: Optional[str] = Query(None, description="Filter by bus type"),
    zone_id: Optional[str] = Query(None, description="Filter by zone"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Obtener lista de buses con filtros"""
    try:
        query = select(Bus).join(BusType, Bus.bus_type_id == BusType.id)
        
        if status:
            query = query.filter(Bus.status == status)
        if bus_type:
            query = query.filter(BusType.code == bus_type)
        if zone_id:
            query = query.filter(Bus.assigned_zone_id == zone_id)
        
        # Paginación
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        result = await db.execute(query)
        buses = result.scalars().all()
        
        # Contar total
        count_query = select(func.count(Bus.id))
        if status:
            count_query = count_query.filter(Bus.status == status)
        
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0
        
        return {
            "data": buses,
            "totalItems": total_count,
            "totalPages": (total_count + page_size - 1) // page_size,
            "currentPage": page,
            "pageSize": page_size
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))