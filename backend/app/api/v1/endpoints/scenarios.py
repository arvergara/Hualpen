from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_async_db as get_db
from datetime import datetime
from pydantic import BaseModel
import uuid
import random

router = APIRouter()

class ScenarioParams(BaseModel):
    maxComputeTime: int
    costWeight: float
    timeWeight: float
    equityWeight: float
    safetyWeight: float
    constraints: dict

class ScenarioCreate(BaseModel):
    name: str
    description: str
    params: ScenarioParams
    contracts: List[dict]
    drivers: List[dict]
    buses: List[dict]

class ScenarioResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    status: str
    params: ScenarioParams
    contracts: List[dict]
    drivers: List[dict]
    buses: List[dict]
    results: Optional[dict] = None

class ScenarioResult(BaseModel):
    shifts: List[dict]
    metrics: dict
    violations: dict
    recommendations: List[str]

# Almacenamiento temporal en memoria (en producción usaría la BD)
scenarios_store = {}

@router.get("/", response_model=List[ScenarioResponse])
async def get_scenarios(
    db: AsyncSession = Depends(get_db)
):
    """Obtener todos los escenarios"""
    try:
        # Por defecto, retornar escenarios predefinidos
        default_scenarios = [
            ScenarioResponse(
                id="1",
                name="Escenario Base",
                description="Configuración actual con todos los conductores",
                created_at=datetime(2024, 1, 1),
                status="completed",
                params=ScenarioParams(
                    maxComputeTime=180,
                    costWeight=0.4,
                    timeWeight=0.3,
                    equityWeight=0.2,
                    safetyWeight=0.1,
                    constraints={
                        "maxDriversPerShift": 50,
                        "minDriversPerShift": 10,
                        "maxOvertimeHours": 12,
                        "minRestDaysPerWeek": 2,
                        "maxConsecutiveShifts": 6,
                        "rotationEquity": True,
                        "geographicOptimization": True
                    }
                ),
                contracts=[],
                drivers=[],
                buses=[],
                results={
                    "shifts": [],
                    "metrics": {
                        "totalCost": 12500000,
                        "totalDrivers": 245,
                        "totalBuses": 180,
                        "averageUtilization": 87.5,
                        "complianceScore": 98.2,
                        "equityScore": 94.8,
                        "efficiencyScore": 91.3
                    },
                    "violations": {
                        "laborLaw": [],
                        "safety": [],
                        "equity": []
                    },
                    "recommendations": []
                }
            ),
            ScenarioResponse(
                id="2",
                name="Reducción 10% Flota",
                description="Simulación con 10% menos buses disponibles",
                created_at=datetime(2024, 1, 5),
                status="completed",
                params=ScenarioParams(
                    maxComputeTime=180,
                    costWeight=0.4,
                    timeWeight=0.3,
                    equityWeight=0.2,
                    safetyWeight=0.1,
                    constraints={
                        "maxDriversPerShift": 50,
                        "minDriversPerShift": 10,
                        "maxOvertimeHours": 12,
                        "minRestDaysPerWeek": 2,
                        "maxConsecutiveShifts": 6,
                        "rotationEquity": True,
                        "geographicOptimization": True
                    }
                ),
                contracts=[],
                drivers=[],
                buses=[],
                results={
                    "shifts": [],
                    "metrics": {
                        "totalCost": 11800000,
                        "totalDrivers": 245,
                        "totalBuses": 162,
                        "averageUtilization": 95.2,
                        "complianceScore": 94.5,
                        "equityScore": 89.3,
                        "efficiencyScore": 88.7
                    },
                    "violations": {
                        "laborLaw": ["2 conductores excedieron límite de horas continuas"],
                        "safety": ["1 ruta requiere conductor adicional"],
                        "equity": ["Distribución de horas extra desigual"]
                    },
                    "recommendations": [
                        "Considerar adquisición de 5 buses adicionales",
                        "Redistribuir rutas en zona norte"
                    ]
                }
            )
        ]
        
        # Combinar con escenarios almacenados
        all_scenarios = default_scenarios + list(scenarios_store.values())
        return all_scenarios
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario_by_id(
    scenario_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Obtener un escenario específico"""
    scenarios = await get_scenarios(db)
    scenario = next((s for s in scenarios if s.id == scenario_id), None)
    
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    return scenario

@router.post("/", response_model=ScenarioResponse)
async def create_scenario(
    scenario: ScenarioCreate,
    db: AsyncSession = Depends(get_db)
):
    """Crear un nuevo escenario"""
    try:
        new_scenario = ScenarioResponse(
            id=str(uuid.uuid4()),
            name=scenario.name,
            description=scenario.description,
            created_at=datetime.now(),
            status="draft",
            params=scenario.params,
            contracts=scenario.contracts,
            drivers=scenario.drivers,
            buses=scenario.buses,
            results=None
        )
        
        # Almacenar en memoria
        scenarios_store[new_scenario.id] = new_scenario
        
        return new_scenario
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{scenario_id}/run", response_model=ScenarioResult)
async def run_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Ejecutar simulación de un escenario"""
    try:
        # Obtener escenario
        scenario = scenarios_store.get(scenario_id)
        if not scenario and scenario_id not in ["1", "2"]:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # Simular ejecución
        results = ScenarioResult(
            shifts=[],
            metrics={
                "totalCost": 12000000 + random.randint(-1000000, 1000000),
                "totalDrivers": 245,
                "totalBuses": 180 + random.randint(-20, 20),
                "averageUtilization": 85 + random.random() * 10,
                "complianceScore": 95 + random.random() * 5,
                "equityScore": 90 + random.random() * 10,
                "efficiencyScore": 88 + random.random() * 12
            },
            violations={
                "laborLaw": [] if random.random() > 0.3 else ["Algunos conductores excedieron límites"],
                "safety": [] if random.random() > 0.4 else ["Verificar descansos entre turnos"],
                "equity": [] if random.random() > 0.5 else ["Distribución de horas extra desigual"]
            },
            recommendations=[
                "Optimizar rutas para reducir kilómetros en vacío",
                "Considerar ajuste en horarios de inicio",
                "Evaluar redistribución de conductores por zona"
            ]
        )
        
        # Actualizar estado del escenario
        if scenario:
            scenario.status = "completed"
            scenario.results = results.dict()
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{scenario_id}/status")
async def update_scenario_status(
    scenario_id: str,
    status_update: dict,
    db: AsyncSession = Depends(get_db)
):
    """Actualizar estado de un escenario"""
    scenario = scenarios_store.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    scenario.status = status_update["status"]
    return {"message": "Status updated successfully"}

@router.get("/{scenario_id}/results", response_model=ScenarioResult)
async def get_scenario_results(
    scenario_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Obtener resultados de un escenario"""
    scenario = await get_scenario_by_id(scenario_id, db)
    
    if not scenario.results:
        raise HTTPException(status_code=404, detail="Results not found")
    
    return ScenarioResult(**scenario.results)

@router.get("/compare")
async def compare_scenarios(
    scenario_id: List[str] = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Comparar múltiples escenarios"""
    scenarios = []
    for sid in scenario_id:
        try:
            scenario = await get_scenario_by_id(sid, db)
            scenarios.append(scenario)
        except:
            continue
    
    if len(scenarios) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 scenarios to compare")
    
    comparison = {
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "metrics": s.results["metrics"] if s.results else None
            }
            for s in scenarios
        ],
        "best_cost": min(scenarios, key=lambda s: s.results["metrics"]["totalCost"] if s.results else float('inf')).id,
        "best_compliance": max(scenarios, key=lambda s: s.results["metrics"]["complianceScore"] if s.results else 0).id,
        "best_efficiency": max(scenarios, key=lambda s: s.results["metrics"]["efficiencyScore"] if s.results else 0).id
    }
    
    return comparison

@router.get("/{scenario_id}/export")
async def export_scenario(
    scenario_id: str,
    format: str = Query("pdf", description="Format: pdf or excel"),
    db: AsyncSession = Depends(get_db)
):
    """Exportar escenario"""
    try:
        scenario = await get_scenario_by_id(scenario_id, db)
        
        # En producción, generaría un archivo real
        if format == "excel":
            content = b"Scenario Excel Data"
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"scenario_{scenario_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        else:
            content = b"Scenario PDF Data"
            media_type = "application/pdf"
            filename = f"scenario_{scenario_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))