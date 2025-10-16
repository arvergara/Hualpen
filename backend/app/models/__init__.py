# Import all models to ensure they are registered with SQLAlchemy
from app.models.catalog import LicenseType, WorkModality, BusType, Zone
from app.models.driver import Driver, DriverLicense, DriverRestriction, DriverPreference
from app.models.bus import Bus
from app.models.contract import Contract
from app.models.service import Service, ServiceSchedule, ServiceStop
from app.models.assignment import PlannedShift, DriverAssignment, BusAssignment
from app.models.compliance import ComplianceViolation, DriverHoursLog, ServiceMetric
from app.models.optimization import OptimizationRun, OptimizationResult

# For easy imports
__all__ = [
    # Catalogs
    "LicenseType",
    "WorkModality", 
    "BusType",
    "Zone",
    # Drivers
    "Driver",
    "DriverLicense",
    "DriverRestriction",
    "DriverPreference",
    # Buses
    "Bus",
    # Contracts and Services
    "Contract",
    "Service",
    "ServiceSchedule",
    "ServiceStop",
    # Assignments
    "PlannedShift",
    "DriverAssignment",
    "BusAssignment",
    # Compliance
    "ComplianceViolation",
    "DriverHoursLog",
    "ServiceMetric",
    # Optimization
    "OptimizationRun",
    "OptimizationResult"
]