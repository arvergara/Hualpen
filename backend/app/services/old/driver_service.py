from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from pydantic import UUID4

from app.models.driver import Driver, DriverLicense, DriverRestriction, DriverPreference
from app.models.assignment import DriverAssignment
from app.models.compliance import ComplianceViolation, DriverHoursLog
from app.schemas.driver import DriverCreate, DriverUpdate


class DriverService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_driver(self, driver_data: DriverCreate) -> Driver:
        """Create a new driver"""
        # Check if driver already exists
        query = select(Driver).where(
            or_(
                Driver.rut == driver_data.rut,
                Driver.employee_code == driver_data.employee_code
            )
        )
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError("Driver with this RUT or employee code already exists")
        
        driver = Driver(**driver_data.dict())
        self.db.add(driver)
        await self.db.commit()
        await self.db.refresh(driver)
        
        return driver
    
    async def update_driver(self, driver_id: UUID4, driver_update: DriverUpdate) -> Driver:
        """Update driver information"""
        query = select(Driver).where(Driver.id == driver_id)
        result = await self.db.execute(query)
        driver = result.scalar_one_or_none()
        
        if not driver:
            raise ValueError("Driver not found")
        
        update_data = driver_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(driver, field, value)
        
        await self.db.commit()
        await self.db.refresh(driver)
        
        return driver
    
    async def get_driver_availability(
        self, 
        driver_id: UUID4, 
        start_date: date, 
        end_date: date
    ) -> Dict[str, Any]:
        """Get driver availability for a date range"""
        # Get driver
        query = select(Driver).where(Driver.id == driver_id)
        result = await self.db.execute(query)
        driver = result.scalar_one_or_none()
        
        if not driver:
            raise ValueError("Driver not found")
        
        # Get assignments
        query = select(DriverAssignment).where(
            and_(
                DriverAssignment.driver_id == driver_id,
                DriverAssignment.date >= start_date,
                DriverAssignment.date <= end_date
            )
        )
        result = await self.db.execute(query)
        assignments = result.scalars().all()
        
        # Get restrictions
        query = select(DriverRestriction).where(
            and_(
                DriverRestriction.driver_id == driver_id,
                DriverRestriction.is_active == True,
                or_(
                    DriverRestriction.end_date.is_(None),
                    DriverRestriction.end_date >= start_date
                )
            )
        )
        result = await self.db.execute(query)
        restrictions = result.scalars().all()
        
        # Build availability calendar
        availability = {}
        current_date = start_date
        
        while current_date <= end_date:
            day_assignments = [
                a for a in assignments 
                if a.date == current_date
            ]
            
            day_restrictions = [
                r for r in restrictions
                if self._restriction_applies_on_date(r, current_date)
            ]
            
            availability[str(current_date)] = {
                "date": current_date,
                "assignments": len(day_assignments),
                "available_hours": 8 - sum(a.planned_driving_hours or 0 for a in day_assignments),
                "restrictions": len(day_restrictions),
                "status": "available" if len(day_assignments) == 0 else "partial"
            }
            
            current_date += timedelta(days=1)
        
        return {
            "driver_id": driver_id,
            "start_date": start_date,
            "end_date": end_date,
            "availability": availability,
            "total_assignments": len(assignments),
            "total_restrictions": len(restrictions)
        }
    
    async def get_hours_summary(self, driver_id: UUID4, period: str) -> Dict[str, Any]:
        """Get driver hours summary for the specified period"""
        # Calculate date range based on period
        end_date = date.today()
        if period == "week":
            start_date = end_date - timedelta(days=7)
        elif period == "month":
            start_date = end_date - timedelta(days=30)
        else:  # year
            start_date = end_date - timedelta(days=365)
        
        # Get hours logs
        query = select(DriverHoursLog).where(
            and_(
                DriverHoursLog.driver_id == driver_id,
                DriverHoursLog.log_date >= start_date,
                DriverHoursLog.log_date <= end_date
            )
        )
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        # Calculate totals
        total_regular = sum(log.regular_hours or 0 for log in logs)
        total_overtime = sum(log.overtime_hours or 0 for log in logs)
        total_night = sum(log.night_hours or 0 for log in logs)
        total_holiday = sum(log.holiday_hours or 0 for log in logs)
        
        return {
            "driver_id": driver_id,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "total_hours": total_regular + total_overtime,
            "regular_hours": total_regular,
            "overtime_hours": total_overtime,
            "night_hours": total_night,
            "holiday_hours": total_holiday,
            "average_daily": (total_regular + total_overtime) / max(len(logs), 1)
        }
    
    async def get_driver_violations(
        self, 
        driver_id: UUID4, 
        status: Optional[str] = None
    ) -> List[ComplianceViolation]:
        """Get driver's compliance violations"""
        query = select(ComplianceViolation).where(
            ComplianceViolation.driver_id == driver_id
        )
        
        if status:
            query = query.where(ComplianceViolation.status == status)
        
        result = await self.db.execute(query)
        violations = result.scalars().all()
        
        return violations
    
    async def add_preference(self, driver_id: UUID4, preference_data: dict) -> DriverPreference:
        """Add a preference for the driver"""
        preference = DriverPreference(
            driver_id=driver_id,
            **preference_data
        )
        
        self.db.add(preference)
        await self.db.commit()
        await self.db.refresh(preference)
        
        return preference
    
    async def add_restriction(self, driver_id: UUID4, restriction_data: dict) -> DriverRestriction:
        """Add a restriction for the driver"""
        restriction = DriverRestriction(
            driver_id=driver_id,
            **restriction_data
        )
        
        self.db.add(restriction)
        await self.db.commit()
        await self.db.refresh(restriction)
        
        return restriction
    
    def _restriction_applies_on_date(self, restriction: DriverRestriction, check_date: date) -> bool:
        """Check if a restriction applies on a specific date"""
        # Check date range
        if restriction.start_date and check_date < restriction.start_date:
            return False
        if restriction.end_date and check_date > restriction.end_date:
            return False
        
        # Check day of week
        if restriction.affected_days:
            weekday = check_date.weekday()
            # Convert Python weekday (0=Monday) to our format (0=Sunday)
            our_weekday = (weekday + 1) % 7
            if our_weekday not in restriction.affected_days:
                return False
        
        return True