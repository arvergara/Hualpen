from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import UUID4

from app.db.session import get_async_db
from app.schemas.optimization import (
    OptimizationRequest,
    OptimizationResult,
    OptimizationRun,
    OptimizationRunCreate
)
from app.services.optimization_service import OptimizationService
from app.models.optimization import OptimizationRun as OptimizationRunModel
from app.models.optimization import OptimizationStatus

router = APIRouter()


@router.post("/optimize", response_model=OptimizationRun)
async def create_optimization(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new optimization run
    
    This endpoint initiates an optimization process that runs in the background.
    The optimization engine will:
    1. Analyze available drivers and their constraints
    2. Match drivers to services based on requirements
    3. Minimize costs while maximizing compliance
    4. Generate assignments for the specified date range
    """
    # Create optimization run record
    optimization_run = OptimizationRunModel(
        run_type="manual",
        start_date=request.start_date,
        end_date=request.end_date,
        parameters=request.dict(include={'objective_weights', 'strategies', 'performance'}),
        constraints=request.constraints.dict(),
        status=OptimizationStatus.RUNNING
    )
    
    db.add(optimization_run)
    await db.commit()
    await db.refresh(optimization_run)
    
    # Start optimization in background
    optimization_service = OptimizationService(db)
    background_tasks.add_task(
        optimization_service.run_optimization,
        optimization_run.id,
        request
    )
    
    return optimization_run


@router.get("/optimize/{run_id}", response_model=OptimizationRun)
async def get_optimization_run(
    run_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """Get optimization run details"""
    query = select(OptimizationRunModel).where(OptimizationRunModel.id == run_id)
    result = await db.execute(query)
    optimization_run = result.scalar_one_or_none()
    
    if not optimization_run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    
    return optimization_run


@router.get("/optimize/{run_id}/results", response_model=OptimizationResult)
async def get_optimization_results(
    run_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """Get detailed results of an optimization run"""
    optimization_service = OptimizationService(db)
    results = await optimization_service.get_optimization_results(run_id)
    
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")
    
    return results


@router.post("/optimize/{run_id}/cancel")
async def cancel_optimization(
    run_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """Cancel a running optimization"""
    query = select(OptimizationRunModel).where(OptimizationRunModel.id == run_id)
    result = await db.execute(query)
    optimization_run = result.scalar_one_or_none()
    
    if not optimization_run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    
    if optimization_run.status != OptimizationStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Optimization is not running")
    
    optimization_run.status = OptimizationStatus.CANCELLED
    await db.commit()
    
    return {"message": "Optimization cancelled successfully"}


@router.post("/optimize/{run_id}/apply")
async def apply_optimization_results(
    run_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """Apply optimization results to create actual assignments"""
    optimization_service = OptimizationService(db)
    
    try:
        assignments_created = await optimization_service.apply_optimization_results(run_id)
        return {
            "message": "Optimization results applied successfully",
            "assignments_created": assignments_created
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to apply optimization results")


@router.post("/routes", response_model=dict)
async def optimize_routes(
    params: dict,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Optimize routes for a specific shift
    
    This endpoint optimizes vehicle routes considering:
    - Multiple pickup/dropoff points
    - Vehicle capacity constraints
    - Time windows
    - Cost minimization
    """
    try:
        # Extract parameters
        shift = params.get("shift", "morning")
        max_compute_time = params.get("maxComputeTime", 180)
        cost_weight = params.get("costWeight", 0.4)
        time_weight = params.get("timeWeight", 0.3)
        utilization_weight = params.get("utilizationWeight", 0.3)
        
        # Simulate optimization (replace with real OR-Tools implementation)
        import random
        
        result = {
            "totalCost": 2450000 + random.random() * 200000,
            "totalDistance": 125.3 + random.random() * 20,
            "routesGenerated": 18 + random.randint(0, 5),
            "fleetUsed": {
                "large": random.randint(3, 12),
                "medium": random.randint(5, 15),
                "small": random.randint(5, 20),
            },
            "avgTravelTime": 35 + random.random() * 15,
            "coverage": 95 + random.random() * 4,
            "computeTime": max_compute_time * 0.25 + random.random() * 30,
        }
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/routes/history")
async def get_route_optimization_history(
    limit: int = 10,
    db: AsyncSession = Depends(get_async_db)
):
    """Get history of route optimizations"""
    # For now, return empty list
    # In the future, this would query actual optimization history
    return {
        "data": [],
        "totalItems": 0,
        "totalPages": 0
    }

# Import after defining to avoid circular imports
from sqlalchemy import select