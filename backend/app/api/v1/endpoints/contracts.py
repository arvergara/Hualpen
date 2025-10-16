from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import UUID4

from app.db.session import get_async_db
from app.models.contract import Contract as ContractModel
from app.models.service import Service as ServiceModel
from app.schemas.contract import Contract, ContractCreate, ContractUpdate, ContractWithServices

router = APIRouter()


@router.get("/", response_model=dict)
async def get_contracts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[List[str]] = Query(None),
    client_name: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of contracts with pagination and filters
    """
    query = select(ContractModel)
    
    # Apply filters
    if search:
        query = query.where(
            (ContractModel.contract_number.ilike(f"%{search}%")) |
            (ContractModel.client_name.ilike(f"%{search}%"))
        )
    
    if status:
        query = query.where(ContractModel.status.in_(status))
    
    if client_name:
        query = query.where(ContractModel.client_name.ilike(f"%{client_name}%"))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_items = total_result.scalar()
    
    # Apply pagination
    query = query.offset(skip).limit(limit).order_by(ContractModel.created_at.desc())
    
    result = await db.execute(query)
    contracts = result.scalars().all()
    
    # Convert SQLAlchemy models to Pydantic models
    contract_schemas = [Contract.from_orm(contract) for contract in contracts]
    
    return {
        "data": contract_schemas,
        "totalItems": total_items,
        "totalPages": (total_items + limit - 1) // limit,
        "currentPage": (skip // limit) + 1,
        "pageSize": limit
    }


@router.get("/{contract_id}", response_model=ContractWithServices)
async def get_contract(
    contract_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific contract by ID with its services
    """
    query = select(ContractModel).where(ContractModel.id == contract_id).options(
        selectinload(ContractModel.services)
    )
    
    result = await db.execute(query)
    contract = result.scalar()
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    return contract


@router.get("/{contract_id}/services", response_model=List[dict])
async def get_contract_services(
    contract_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all services for a specific contract
    """
    query = select(ServiceModel).where(ServiceModel.contract_id == contract_id).options(
        selectinload(ServiceModel.zone),
        selectinload(ServiceModel.required_bus_type),
        selectinload(ServiceModel.schedules)
    )
    
    result = await db.execute(query)
    services = result.scalars().all()
    
    return services


@router.post("/", response_model=Contract)
async def create_contract(
    contract_data: ContractCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new contract
    """
    # Check if contract number already exists
    existing = await db.execute(
        select(ContractModel).where(ContractModel.contract_number == contract_data.contract_number)
    )
    if existing.scalar():
        raise HTTPException(status_code=400, detail="Contract number already exists")
    
    contract = ContractModel(**contract_data.dict())
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    
    return contract


@router.put("/{contract_id}", response_model=Contract)
async def update_contract(
    contract_id: UUID4,
    contract_data: ContractUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update a contract
    """
    result = await db.execute(select(ContractModel).where(ContractModel.id == contract_id))
    contract = result.scalar()
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    update_data = contract_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contract, field, value)
    
    await db.commit()
    await db.refresh(contract)
    
    return contract


@router.get("/{contract_id}/metrics", response_model=dict)
async def get_contract_metrics(
    contract_id: UUID4,
    month: Optional[str] = Query(None, pattern="^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get contract metrics (performance, compliance, etc.)
    """
    # This would typically aggregate data from service_metrics table
    # For now, returning mock metrics
    
    return {
        "contract_id": str(contract_id),
        "month": month or "current",
        "metrics": {
            "on_time_performance": 98.5,
            "services_completed": 450,
            "services_cancelled": 5,
            "total_passengers": 15000,
            "revenue_generated": 450000000,
            "sla_compliance": {
                "on_time": True,
                "availability": True,
                "cancellations": True
            }
        }
    }


@router.post("/{contract_id}/terminate", response_model=Contract)
async def terminate_contract(
    contract_id: UUID4,
    termination_date: date = Query(...),
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Terminate a contract
    """
    result = await db.execute(select(ContractModel).where(ContractModel.id == contract_id))
    contract = result.scalar()
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    if contract.status != "active":
        raise HTTPException(status_code=400, detail="Only active contracts can be terminated")
    
    contract.status = "terminated"
    contract.end_date = termination_date
    
    await db.commit()
    await db.refresh(contract)
    
    return contract


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: UUID4,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Eliminar un contrato (borrado físico)
    """
    result = await db.execute(select(ContractModel).where(ContractModel.id == contract_id))
    contract = result.scalar()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    await db.delete(contract)
    await db.commit()
    return {"message": "Contract deleted successfully"}