from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_async_db
from app.models.driver import Driver as DriverModel
from app.models.bus import Bus as BusModel
from app.models.contract import Contract as ContractModel
from app.models.service import Service as ServiceModel
from app.models.assignment import DriverAssignment as DriverAssignmentModel

router = APIRouter()


@router.get("/drivers")
async def get_driver_stats(db: AsyncSession = Depends(get_async_db)):
    """Get driver statistics"""
    # Total drivers
    total_query = select(func.count(DriverModel.id))
    total_result = await db.execute(total_query)
    total_drivers = total_result.scalar() or 0
    
    # Active drivers
    active_query = select(func.count(DriverModel.id)).where(DriverModel.status == 'active')
    active_result = await db.execute(active_query)
    active_drivers = active_result.scalar() or 0
    
    # Medical leave
    medical_query = select(func.count(DriverModel.id)).where(DriverModel.status == 'medical_leave')
    medical_result = await db.execute(medical_query)
    medical_leave = medical_result.scalar() or 0
    
    # Average hours (simplified - would need actual hours tracking)
    avg_hours = 45  # Default for now
    
    return {
        "total": total_drivers,
        "active": active_drivers,
        "medical_leave": medical_leave,
        "inactive": total_drivers - active_drivers - medical_leave,
        "average_hours_week": avg_hours
    }


@router.get("/buses")
async def get_bus_stats(db: AsyncSession = Depends(get_async_db)):
    """Get bus statistics"""
    # Total buses
    total_query = select(func.count(BusModel.id))
    total_result = await db.execute(total_query)
    total_buses = total_result.scalar() or 0
    
    # Status counts
    active_query = select(func.count(BusModel.id)).where(BusModel.status == 'active')
    active_result = await db.execute(active_query)
    active_buses = active_result.scalar() or 0
    
    maintenance_query = select(func.count(BusModel.id)).where(BusModel.status == 'maintenance')
    maintenance_result = await db.execute(maintenance_query)
    maintenance_buses = maintenance_result.scalar() or 0
    
    return {
        "total": total_buses,
        "active": active_buses,
        "maintenance": maintenance_buses,
        "other": total_buses - active_buses - maintenance_buses
    }


@router.get("/contracts")
async def get_contract_stats(db: AsyncSession = Depends(get_async_db)):
    """Get contract statistics"""
    # Total contracts
    total_query = select(func.count(ContractModel.id))
    total_result = await db.execute(total_query)
    total_contracts = total_result.scalar() or 0
    
    # Active contracts and monthly value
    active_query = select(
        func.count(ContractModel.id),
        func.sum(ContractModel.monthly_value)
    ).where(ContractModel.status == 'active')
    active_result = await db.execute(active_query)
    active_count, monthly_value = active_result.one()
    
    return {
        "total": total_contracts,
        "active": active_count or 0,
        "monthly_value": monthly_value or 0
    }


@router.get("/services")
async def get_service_stats(db: AsyncSession = Depends(get_async_db)):
    """Get service statistics"""
    # Total services
    total_query = select(func.count(ServiceModel.id))
    total_result = await db.execute(total_query)
    total_services = total_result.scalar() or 0
    
    # Active services and total distance
    active_query = select(
        func.count(ServiceModel.id),
        func.sum(ServiceModel.distance_km)
    ).where(ServiceModel.status == 'active')
    active_result = await db.execute(active_query)
    active_count, total_distance = active_result.one()
    
    return {
        "total": total_services,
        "active": active_count or 0,
        "total_distance": total_distance or 0
    }