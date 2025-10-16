"""
Traditional work patterns (mallas) used in Chilean transport industry
"""

from typing import List, Dict, Tuple
from datetime import date, timedelta
import calendar

class TraditionalPattern:
    """Represents a traditional work pattern (malla)"""
    
    def __init__(self, name: str, work_days: int, rest_days: int, 
                 fixed_rest: List[int] = None, rotative: bool = False):
        """
        Args:
            name: Pattern name (e.g., "5X2 FIJO")
            work_days: Number of consecutive work days
            rest_days: Number of consecutive rest days
            fixed_rest: Fixed rest days (0=Monday, 6=Sunday) for FIJO patterns
            rotative: True for ROTATIVO patterns that rotate rest days
        """
        self.name = name
        self.work_days = work_days
        self.rest_days = rest_days
        self.fixed_rest = fixed_rest or []
        self.rotative = rotative
        self.cycle_length = work_days + rest_days
    
    def generate_month_schedule(self, year: int, month: int, 
                                start_offset: int = 0) -> Dict[date, bool]:
        """
        Generate work schedule for a month
        Returns dict of date -> is_working
        """
        schedule = {}
        first_day = date(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        
        if self.rotative:
            # Rotative pattern: cycles through work/rest
            cycle_position = start_offset % self.cycle_length
            
            for day_num in range(days_in_month):
                current_date = first_day + timedelta(days=day_num)
                
                # Check if it's a work day in the cycle
                if cycle_position < self.work_days:
                    schedule[current_date] = True
                else:
                    schedule[current_date] = False
                
                cycle_position = (cycle_position + 1) % self.cycle_length
        
        else:
            # Fixed pattern: specific days off each week
            for day_num in range(days_in_month):
                current_date = first_day + timedelta(days=day_num)
                weekday = current_date.weekday()
                
                # Check if it's a fixed rest day
                if weekday in self.fixed_rest:
                    schedule[current_date] = False
                else:
                    schedule[current_date] = True
        
        return schedule
    
    def count_work_days(self, year: int, month: int, start_offset: int = 0) -> int:
        """Count total work days in a month for this pattern"""
        schedule = self.generate_month_schedule(year, month, start_offset)
        return sum(1 for is_working in schedule.values() if is_working)
    
    def count_sundays_worked(self, year: int, month: int, start_offset: int = 0) -> int:
        """Count Sundays worked in a month"""
        schedule = self.generate_month_schedule(year, month, start_offset)
        return sum(1 for date, is_working in schedule.items() 
                  if is_working and date.weekday() == 6)


# Define common traditional patterns
TRADITIONAL_PATTERNS = [
    # Most common patterns
    TraditionalPattern("5X2 FIJO", 5, 2, fixed_rest=[5, 6], rotative=False),  # Mon-Fri work, Sat-Sun off
    TraditionalPattern("5X2 ROTATIVO", 5, 2, rotative=True),  # 5 work, 2 off rotating
    TraditionalPattern("6X1 FIJO", 6, 1, fixed_rest=[6], rotative=False),  # Mon-Sat work, Sun off
    TraditionalPattern("4X3 FIJO", 4, 3, fixed_rest=[4, 5, 6], rotative=False),  # Mon-Thu work, Fri-Sun off
    TraditionalPattern("4X3 ROTATIVO", 4, 3, rotative=True),  # 4 work, 3 off rotating
    
    # Mixed patterns
    TraditionalPattern("5X2-6X1 ROTATIVO", 5, 2, rotative=True),  # Alternates between 5x2 and 6x1
    
    # Special patterns for coverage
    TraditionalPattern("7X7 ROTATIVO", 7, 7, rotative=True),  # 7 work, 7 off (for special cases)
    TraditionalPattern("10X5 ROTATIVO", 10, 5, rotative=True),  # 10 work, 5 off (intensive)
]


def find_best_pattern(required_days: int, allows_sunday: bool = True, 
                      prefers_fixed: bool = True) -> TraditionalPattern:
    """
    Find the best traditional pattern for required work days
    
    Args:
        required_days: Number of days needed per month
        allows_sunday: Whether Sunday work is allowed
        prefers_fixed: Whether to prefer fixed over rotative patterns
    
    Returns:
        Best matching traditional pattern
    """
    candidates = []
    
    for pattern in TRADITIONAL_PATTERNS:
        # Skip patterns with Sunday work if not allowed
        if not allows_sunday and (pattern.rotative or 6 not in pattern.fixed_rest):
            continue
        
        # Calculate average work days for this pattern
        # Use a typical month (February 2025) for estimation
        work_days = pattern.count_work_days(2025, 2)
        
        # Calculate fitness score (closer to required is better)
        difference = abs(work_days - required_days)
        
        # Bonus for preferred type
        if prefers_fixed and not pattern.rotative:
            difference -= 0.5  # Small bonus for fixed patterns
        
        candidates.append((difference, pattern, work_days))
    
    # Sort by fitness (smallest difference first)
    candidates.sort(key=lambda x: x[0])
    
    if candidates:
        return candidates[0][1]
    
    # Fallback to 5X2 ROTATIVO if no match
    return TraditionalPattern("5X2 ROTATIVO", 5, 2, rotative=True)


def calculate_drivers_needed(total_shifts: int, pattern: TraditionalPattern,
                             year: int, month: int) -> int:
    """
    Calculate number of drivers needed for coverage using a traditional pattern
    
    Args:
        total_shifts: Total shifts to cover in the month
        pattern: Traditional pattern to use
        year: Year
        month: Month
    
    Returns:
        Number of drivers needed
    """
    # Calculate work days per driver with this pattern
    work_days_per_driver = pattern.count_work_days(year, month)
    
    # Calculate drivers needed (with small buffer)
    drivers_needed = (total_shifts + work_days_per_driver - 1) // work_days_per_driver
    
    # Add buffer for Sunday coverage if pattern includes Sundays
    if pattern.count_sundays_worked(year, month) > 0:
        # Each driver can work max 2 Sundays, need extra coverage
        sunday_buffer = max(1, total_shifts // 100)  # 1% buffer for Sunday rotation
        drivers_needed += sunday_buffer
    
    return drivers_needed


class PatternAssignment:
    """Assigns drivers to shifts using traditional patterns"""
    
    def __init__(self, pattern: TraditionalPattern):
        self.pattern = pattern
        self.driver_id = None
        self.schedule = {}
        self.assigned_shifts = []
        self.total_hours = 0
        self.sundays_worked = 0
    
    def can_work_on(self, check_date: date) -> bool:
        """Check if this driver can work on a specific date"""
        return self.schedule.get(check_date, False)
    
    def assign_shift(self, shift: Dict):
        """Assign a shift to this driver"""
        self.assigned_shifts.append(shift)
        self.total_hours += shift.get('duration_hours', 0)
        
        if shift['date'].weekday() == 6:
            self.sundays_worked += 1
    
    def get_utilization(self) -> float:
        """Calculate utilization percentage"""
        max_hours = 180  # Monthly maximum
        return (self.total_hours / max_hours) * 100 if max_hours > 0 else 0