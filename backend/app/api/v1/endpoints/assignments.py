from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from pydantic import UUID4

from app.db.session import get_async_db
from app.models.assignment import PlannedShift as PlannedShiftModel, DriverAssignment as DriverAssignmentModel, BusAssignment as BusAssignmentModel
from app.schemas.assignment import (
    Assignment, AssignmentWithDetails, DriverAssignmentUpdate, BusAssignmentUpdate,
    PlannedShift, DriverAssignment, BusAssignment
)

router = APIRouter()


@router.get("/", response_model=dict)
async def get_assignments(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[List[str]] = Query(None),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    driver_id: Optional[UUID4] = None,
    service_id: Optional[UUID4] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of assignments with pagination and filters
    """
    # Main query joining all assignment tables
    query = select(
        PlannedShiftModel,
        DriverAssignmentModel,
        BusAssignmentModel
    ).select_from(PlannedShiftModel).join(
        DriverAssignmentModel,
        PlannedShiftModel.id == DriverAssignmentModel.planned_shift_id
    ).outerjoin(
        BusAssignmentModel,
        PlannedShiftModel.id == BusAssignmentModel.planned_shift_id
    ).options(
        selectinload(PlannedShiftModel.service),
        selectinload(DriverAssignmentModel.driver),
        selectinload(BusAssignmentModel.bus)
    )
    
    # Apply filters
    if date_from:
        query = query.where(PlannedShiftModel.shift_date >= date_from)
    
    if date_to:
        query = query.where(PlannedShiftModel.shift_date <= date_to)
    
    if driver_id:
        query = query.where(DriverAssignmentModel.driver_id == driver_id)
    
    if service_id:
        query = query.where(PlannedShiftModel.service_id == service_id)
    
    if status:
        query = query.where(DriverAssignmentModel.status.in_(status))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar()
    
    # Apply pagination
    query = query.offset(skip).limit(limit).order_by(
        PlannedShiftModel.shift_date.desc(),
        PlannedShiftModel.start_time.desc()
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Transform to assignment format
    assignments = []
    for shift, driver_assignment, bus_assignment in rows:
        assignment_data = Assignment(
            id=str(driver_assignment.id),
            planned_shift=PlannedShift.from_orm(shift),
            driver_assignment=DriverAssignment.from_orm(driver_assignment),
            bus_assignment=BusAssignment.from_orm(bus_assignment) if bus_assignment else None
        )
        assignments.append(assignment_data)
    
    return {
        "data": assignments,
        "totalItems": total_items,
        "totalPages": (total_items + limit - 1) // limit,
        "currentPage": (skip // limit) + 1,
        "pageSize": limit
    }


@router.get("/by-date", response_model=List[AssignmentWithDetails])
async def get_assignments_by_date(
    date: date = Query(...),
    zone_id: Optional[UUID4] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all assignments for a specific date
    """
    query = select(
        PlannedShiftModel,
        DriverAssignmentModel,
        BusAssignmentModel
    ).select_from(PlannedShiftModel).join(
        DriverAssignmentModel,
        PlannedShiftModel.id == DriverAssignmentModel.planned_shift_id
    ).outerjoin(
        BusAssignmentModel,
        PlannedShiftModel.id == BusAssignmentModel.planned_shift_id
    ).where(
        PlannedShiftModel.shift_date == date
    ).options(
        selectinload(PlannedShiftModel.service),
        selectinload(DriverAssignmentModel.driver),
        selectinload(BusAssignmentModel.bus)
    )
    
    if zone_id:
        # Filter by zone through service
        query = query.join(
            PlannedShiftModel.service
        ).where(
            PlannedShiftModel.service.has(zone_id=zone_id)
        )
    
    result = await db.execute(query)
    rows = result.all()
    
    assignments = []
    for shift, driver_assignment, bus_assignment in rows:
        assignments.append({
            "id": str(driver_assignment.id),
            "planned_shift": shift,
            "driver_assignment": driver_assignment,
            "bus_assignment": bus_assignment
        })
    
    return assignments


@router.get("/{assignment_id}", response_model=AssignmentWithDetails)
async def get_assignment(
    assignment_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific assignment by driver assignment ID
    """
    query = select(
        PlannedShiftModel,
        DriverAssignmentModel,
        BusAssignmentModel
    ).select_from(DriverAssignmentModel).join(
        PlannedShiftModel,
        PlannedShiftModel.id == DriverAssignmentModel.planned_shift_id
    ).outerjoin(
        BusAssignmentModel,
        PlannedShiftModel.id == BusAssignmentModel.planned_shift_id
    ).where(
        DriverAssignmentModel.id == assignment_id
    ).options(
        selectinload(PlannedShiftModel.service),
        selectinload(DriverAssignmentModel.driver),
        selectinload(BusAssignmentModel.bus)
    )
    
    result = await db.execute(query)
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    shift, driver_assignment, bus_assignment = row
    
    return {
        "id": str(driver_assignment.id),
        "planned_shift": shift,
        "driver_assignment": driver_assignment,
        "bus_assignment": bus_assignment
    }


@router.put("/{assignment_id}/status", response_model=dict)
async def update_assignment_status(
    assignment_id: UUID4,
    status: str = Query(..., pattern="^(scheduled|confirmed|active|completed|cancelled|no_show)$"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update assignment status
    """
    result = await db.execute(
        select(DriverAssignmentModel).where(DriverAssignmentModel.id == assignment_id)
    )
    assignment = result.scalar()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Validate status transitions
    valid_transitions = {
        "scheduled": ["confirmed", "cancelled"],
        "confirmed": ["active", "cancelled", "no_show"],
        "active": ["completed", "cancelled"],
        "completed": [],
        "cancelled": [],
        "no_show": []
    }
    
    if status not in valid_transitions.get(assignment.status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition from {assignment.status} to {status}"
        )
    
    assignment.status = status
    
    # Set actual times based on status
    if status == "active" and not assignment.actual_start_time:
        assignment.actual_start_time = datetime.utcnow()
    elif status == "completed" and not assignment.actual_end_time:
        assignment.actual_end_time = datetime.utcnow()
    
    await db.commit()
    
    return {
        "message": "Status updated successfully",
        "assignment_id": str(assignment_id),
        "new_status": status
    }


@router.put("/{assignment_id}/actual-times", response_model=dict)
async def record_actual_times(
    assignment_id: UUID4,
    actual_start_time: Optional[datetime] = None,
    actual_end_time: Optional[datetime] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Record actual start/end times for an assignment
    """
    result = await db.execute(
        select(DriverAssignmentModel).where(DriverAssignmentModel.id == assignment_id)
    )
    assignment = result.scalar()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if actual_start_time:
        assignment.actual_start_time = actual_start_time
        if assignment.status == "confirmed":
            assignment.status = "active"
    
    if actual_end_time:
        assignment.actual_end_time = actual_end_time
        if assignment.status == "active":
            assignment.status = "completed"
        
        # Calculate actual driving hours
        if assignment.actual_start_time:
            duration = actual_end_time - assignment.actual_start_time
            assignment.actual_driving_hours = duration.total_seconds() / 3600
    
    await db.commit()
    
    return {
        "message": "Actual times recorded successfully",
        "assignment_id": str(assignment_id),
        "actual_start_time": actual_start_time.isoformat() if actual_start_time else None,
        "actual_end_time": actual_end_time.isoformat() if actual_end_time else None
    }


@router.put("/{assignment_id}/bus-kilometers", response_model=dict)
async def update_bus_kilometers(
    assignment_id: UUID4,
    start_kilometers: Optional[int] = None,
    end_kilometers: Optional[int] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update bus kilometers for an assignment
    """
    # Get the bus assignment through driver assignment
    driver_result = await db.execute(
        select(DriverAssignmentModel).where(DriverAssignmentModel.id == assignment_id)
    )
    driver_assignment = driver_result.scalar()
    
    if not driver_assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    bus_result = await db.execute(
        select(BusAssignmentModel).where(
            BusAssignmentModel.planned_shift_id == driver_assignment.planned_shift_id
        )
    )
    bus_assignment = bus_result.scalar()
    
    if not bus_assignment:
        raise HTTPException(status_code=404, detail="Bus assignment not found")
    
    if start_kilometers is not None:
        bus_assignment.start_kilometers = start_kilometers
    
    if end_kilometers is not None:
        bus_assignment.end_kilometers = end_kilometers
        
        # Calculate dead kilometers if we have both values
        if bus_assignment.start_kilometers is not None:
            # This is simplified - actual calculation would consider service distance
            total_km = end_kilometers - bus_assignment.start_kilometers
            # Assuming service distance is known, dead_km = total_km - service_distance
            # For now, we'll leave it to be calculated elsewhere
    
    await db.commit()
    
    return {
        "message": "Kilometers updated successfully",
        "assignment_id": str(assignment_id),
        "start_kilometers": start_kilometers,
        "end_kilometers": end_kilometers
    }