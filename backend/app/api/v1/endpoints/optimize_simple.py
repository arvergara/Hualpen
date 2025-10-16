from typing import Dict, Any
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
import asyncio
import random
import uuid

router = APIRouter()

# Simple storage for optimization results
optimization_results = {}


class OptimizationRequest(BaseModel):
    start_date: str
    end_date: str
    constraints: Dict[str, Any]
    objective_weights: Dict[str, float]
    strategies: Dict[str, bool]
    performance: Dict[str, Any]
    zones: list


class OptimizationRun(BaseModel):
    id: str
    status: str
    created_at: datetime


@router.post("/optimize", response_model=OptimizationRun)
async def create_optimization(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks
):
    """
    Create a new optimization run (simplified version)
    """
    run_id = str(uuid.uuid4())
    
    # Store initial status
    optimization_results[run_id] = {
        "id": run_id,
        "status": "running",
        "created_at": datetime.now()
    }
    
    # Run optimization in background
    background_tasks.add_task(run_optimization, run_id, request)
    
    return OptimizationRun(
        id=run_id,
        status="running",
        created_at=datetime.now()
    )


async def run_optimization(run_id: str, request: OptimizationRequest):
    """Simulate optimization process"""
    await asyncio.sleep(3)  # Simulate processing
    
    # Generate mock results
    optimization_results[run_id] = {
        "run_id": run_id,
        "status": "success",
        "assignments": generate_mock_assignments(),
        "metrics": {
            "total_cost": random.uniform(80000000, 120000000),
            "labor_cost": random.uniform(60000000, 90000000),
            "overtime_cost": random.uniform(5000000, 15000000),
            "dead_kilometers": random.uniform(200, 500),
            "driver_utilization": random.uniform(75, 90),
            "services_covered": random.uniform(95, 100),
            "compliance_score": random.uniform(90, 98),
            "equity_score": random.uniform(80, 95),
            "efficiency_score": random.uniform(85, 95)
        },
        "violations": generate_mock_violations(),
        "warnings": [],
        "recommendations": [
            "Consider hiring 5 additional drivers to improve coverage",
            "Optimize shift patterns to reduce overtime costs",
            "Review zone assignments to minimize dead kilometers"
        ],
        "compute_time": random.uniform(2, 4),
        "solution_quality": random.uniform(85, 95)
    }


def generate_mock_assignments():
    """Generate mock driver assignments"""
    assignments = []
    for i in range(20):
        assignments.append({
            "driver_id": f"driver_{i}",
            "service_id": f"service_{i % 5}",
            "position": "primary",
            "date": "2024-01-15",
            "shift_start": f"{6 + (i % 3)}:00",
            "shift_end": f"{14 + (i % 3)}:00",
            "actual_driving_hours": random.uniform(6, 8),
            "breaks_taken": [
                {
                    "start_time": "10:00",
                    "end_time": "10:30",
                    "duration": 30,
                    "type": "mandatory"
                }
            ],
            "status": "scheduled"
        })
    return assignments


def generate_mock_violations():
    """Generate mock violations"""
    violations = []
    
    if random.random() > 0.7:
        violations.append({
            "type": "soft",
            "constraint": "max_weekly_driving_hours",
            "description": "Driver D001 exceeds preferred weekly hours by 2 hours",
            "affected_drivers": ["driver_1"],
            "affected_services": [],
            "severity": "minor",
            "suggested_fix": "Redistribute shifts or assign backup driver"
        })
    
    if random.random() > 0.8:
        violations.append({
            "type": "hard",
            "constraint": "min_rest_between_shifts",
            "description": "Insufficient rest time between shifts for Driver D005",
            "affected_drivers": ["driver_5"],
            "affected_services": ["service_2"],
            "severity": "major",
            "suggested_fix": "Adjust shift timing or assign different driver"
        })
    
    return violations


@router.get("/optimize/{run_id}")
async def get_optimization_run(run_id: str):
    """Get optimization run status"""
    if run_id in optimization_results:
        result = optimization_results[run_id]
        return {
            "id": run_id,
            "status": result.get("status", "unknown"),
            "created_at": result.get("created_at", datetime.now())
        }
    return {"error": "Optimization run not found"}


@router.get("/optimize/{run_id}/results")
async def get_optimization_results(run_id: str):
    """Get detailed results of an optimization run"""
    if run_id in optimization_results and optimization_results[run_id].get("status") == "success":
        return optimization_results[run_id]
    return {"error": "Results not available"}