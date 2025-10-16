from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_async_db as get_db
from app.models.service import Service
from app.models.contract import Contract
from app.models.catalog import Zone
from datetime import datetime

router = APIRouter()

# Estructura de datos para plantas
class PlantShift:
    def __init__(self, id: str, name: str, start_time: str, end_time: str, operator_count: int):
        self.id = id
        self.name = name
        self.startTime = start_time
        self.endTime = end_time
        self.operatorCount = operator_count

class Plant:
    def __init__(self, id: str, name: str, lat: float, lng: float, address: str, operator_count: int, shifts: List[PlantShift]):
        self.id = id
        self.name = name
        self.location = {"lat": lat, "lng": lng}
        self.address = address
        self.operatorCount = operator_count
        self.shifts = [s.__dict__ for s in shifts]

@router.get("/", response_model=List[dict])
async def get_plants(
    db: AsyncSession = Depends(get_db)
):
    """Obtener todas las plantas con información de turnos"""
    try:
        # Obtener zonas principales como "plantas"
        zones_query = select(Zone).filter(Zone.allow_driver_sharing == True)
        result = await db.execute(zones_query)
        zones = result.scalars().all()
        
        plants = []
        
        # Planta Principal (Zona Norte)
        if len(zones) > 0:
            zone = zones[0]
            shifts = [
                PlantShift("morning", "Mañana", "06:00", "14:00", 400),
                PlantShift("afternoon", "Tarde", "14:00", "22:00", 350),
                PlantShift("night", "Noche", "22:00", "06:00", 250)
            ]
            plant = Plant(
                id=str(zone.id),
                name="Planta Principal",
                lat=-36.7326,
                lng=-73.1172,
                address="Av. Industrial 1000, Hualpén",
                operator_count=500,
                shifts=shifts
            )
            plants.append(plant.__dict__)
        
        # Planta Norte (Zona Centro)
        if len(zones) > 1:
            zone = zones[1]
            shifts = [
                PlantShift("morning", "Mañana", "06:00", "14:00", 250),
                PlantShift("afternoon", "Tarde", "14:00", "22:00", 200),
                PlantShift("night", "Noche", "22:00", "06:00", 150)
            ]
            plant = Plant(
                id=str(zone.id),
                name="Planta Norte",
                lat=-36.7126,
                lng=-73.1072,
                address="Camino Norte 500, Hualpén",
                operator_count=300,
                shifts=shifts
            )
            plants.append(plant.__dict__)
        
        # Planta Sur
        shifts = [
            PlantShift("morning", "Mañana", "06:00", "14:00", 150),
            PlantShift("afternoon", "Tarde", "14:00", "22:00", 150),
            PlantShift("night", "Noche", "22:00", "06:00", 100)
        ]
        plant = Plant(
            id="p3",
            name="Planta Sur",
            lat=-36.7526,
            lng=-73.1272,
            address="Ruta Sur 200, Hualpén",
            operator_count=200,
            shifts=shifts
        )
        plants.append(plant.__dict__)
        
        return plants
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{plant_id}")
async def get_plant_by_id(
    plant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Obtener una planta específica por ID"""
    plants = await get_plants(db)
    plant = next((p for p in plants if p["id"] == plant_id), None)
    
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    
    return plant

@router.get("/{plant_id}/shifts")
async def get_plant_shifts(
    plant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Obtener los turnos de una planta específica"""
    plant = await get_plant_by_id(plant_id, db)
    return plant["shifts"]