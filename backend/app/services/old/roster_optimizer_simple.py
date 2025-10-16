"""
Simplified Fast Roster Optimizer
Uses a simpler, more practical approach for quick legal solutions
"""

from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime, timedelta, date
from collections import defaultdict
from dataclasses import dataclass, field
import random
import time


@dataclass
class SimpleDriver:
    """Simple driver representation"""
    id: str
    name: str
    shifts: List[Dict] = field(default_factory=list)
    hours_by_week: Dict[int, float] = field(default_factory=lambda: defaultdict(float))
    total_hours: float = 0.0
    sundays_worked: Set[date] = field(default_factory=set)
    days_worked: Set[date] = field(default_factory=set)
    
    def can_work_shift(self, shift: Dict, is_sunday: bool = False) -> bool:
        """Check if driver can work a shift"""
        # Check weekly hours
        week = shift['week_num']
        if self.hours_by_week[week] + shift['duration_hours'] > 44:
            return False
        
        # Check monthly hours
        if self.total_hours + shift['duration_hours'] > 180:
            return False
        
        # Check if already working that day
        if shift['date'] in self.days_worked:
            # Check for span violation if adding another shift
            same_day_shifts = [s for s in self.shifts if s['date'] == shift['date']]
            if same_day_shifts:
                # Calculate span
                all_shifts = same_day_shifts + [shift]
                earliest = min(s['start_hour'] for s in all_shifts)
                latest = max(s['end_hour'] if s['end_hour'] > s['start_hour'] else 24 for s in all_shifts)
                span = latest - earliest
                if span > 12:
                    return False
        
        # Check Sunday limit
        if is_sunday and shift['date'] not in self.sundays_worked:
            if len(self.sundays_worked) >= 2:
                return False
        
        return True
    
    def assign_shift(self, shift: Dict, is_sunday: bool = False):
        """Assign a shift to this driver"""
        self.shifts.append(shift)
        self.total_hours += shift['duration_hours']
        self.hours_by_week[shift['week_num']] += shift['duration_hours']
        self.days_worked.add(shift['date'])
        if is_sunday:
            self.sundays_worked.add(shift['date'])


class SimpleRosterOptimizer:
    """
    Simple optimizer that finds legal solutions quickly
    Prioritizes feasibility over optimality
    """
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.start_time = None
        self.timeout = 10.0  # 10 second timeout
        
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """Main optimization"""
        self.start_time = time.time()
        
        print(f"\n=== SIMPLE FAST OPTIMIZATION {year}-{month:02d} ===")
        
        # Generate shifts
        days = self._generate_month_days(year, month)
        shifts = self._generate_shifts(days)
        
        print(f"Total shifts to assign: {len(shifts)}")
        
        # CRITICAL FIX: Sort shifts with weekly balancing to prevent early-week bias
        print(f"\n🔧 APPLYING WEEKLY BALANCING FIX TO SIMPLE OPTIMIZER")
        print("  Problem: Chronological sorting causes uneven weekly distribution")
        print("  Solution: Round-robin by week_num for balanced driver distribution")
        
        # Group shifts by week for balanced processing
        from collections import defaultdict
        shifts_by_week = defaultdict(list)
        for shift in shifts:
            shifts_by_week[shift['week_num']].append(shift)
        
        # Sort within each week, then round-robin across weeks
        for week_shifts in shifts_by_week.values():
            week_shifts.sort(key=lambda s: (not s['is_sunday'], s['date'].day, s['start_hour']))
        
        # Create balanced order
        balanced_shifts = []
        week_numbers = sorted(shifts_by_week.keys())
        max_shifts_per_week = max(len(shifts) for shifts in shifts_by_week.values()) if shifts_by_week else 0
        
        for shift_index in range(max_shifts_per_week):
            for week_num in week_numbers:
                week_shifts = shifts_by_week[week_num]
                if shift_index < len(week_shifts):
                    balanced_shifts.append(week_shifts[shift_index])
        
        shifts = balanced_shifts
        
        print(f"  - Balanced order created: {len(shifts)} shifts across {len(week_numbers)} weeks")
        
        # Calculate minimum drivers needed
        # Be generous - better to have more drivers than fail
        total_hours = sum(s['duration_hours'] for s in shifts)
        # Adaptive minimum based on actual workload
        adaptive_min = max(5, len(shifts) // 20)  # At least 5, or enough for 20 shifts/driver
        min_drivers = max(
            int(total_hours / 150) + 2,  # Monthly hours with small buffer
            adaptive_min  # Use adaptive minimum instead of fixed 45
        )
        max_drivers = min(120, min_drivers + 30)  # Give more room
        
        print(f"Trying {min_drivers} to {max_drivers} drivers")
        
        # Try with increasing drivers
        for num_drivers in range(min_drivers, max_drivers + 1):
            if time.time() - self.start_time > self.timeout:
                break
            
            print(f"\nAttempt with {num_drivers} drivers...", end=' ')
            
            # Create drivers
            drivers = [
                SimpleDriver(id=f"D{i+1:03d}", name=f"Driver {i+1}")
                for i in range(num_drivers)
            ]
            
            # Try to assign all shifts
            assignments = []
            unassigned = []
            
            for shift in shifts:
                assigned = False
                is_sunday = shift['is_sunday']
                
                # Find best available driver
                # Prioritize drivers with fewer hours for load balancing
                available_drivers = [
                    d for d in drivers 
                    if d.can_work_shift(shift, is_sunday)
                ]
                
                if available_drivers:
                    # Pick driver with least hours (load balancing)
                    best_driver = min(available_drivers, key=lambda d: d.total_hours)
                    best_driver.assign_shift(shift, is_sunday)
                    
                    assignments.append({
                        'shift_id': shift['id'],
                        'shift': shift,
                        'driver_id': best_driver.id,
                        'driver_name': best_driver.name
                    })
                    assigned = True
                
                if not assigned:
                    unassigned.append(shift)
            
            # Check if we got everything
            if len(unassigned) == 0:
                elapsed = time.time() - self.start_time
                print(f"SUCCESS in {elapsed:.2f}s!")
                
                # Count active drivers
                active_drivers = [d for d in drivers if len(d.shifts) > 0]
                
                print(f"  ✓ All {len(shifts)} shifts assigned")
                print(f"  ✓ Using {len(active_drivers)} drivers")
                print(f"  ✓ Solution is LEGAL")
                
                return self._format_solution(assignments, drivers, shifts, elapsed)
            else:
                print(f"Failed ({len(unassigned)} unassigned)")
        
        return {
            'status': 'failed',
            'reason': f'Could not assign all shifts with up to {max_drivers} drivers'
        }
    
    def _generate_month_days(self, year: int, month: int) -> List[date]:
        """Generate all days in month"""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        days = []
        current = start_date
        while current <= end_date:
            days.append(current)
            current += timedelta(days=1)
        return days
    
    def _generate_shifts(self, days: List[date]) -> List[Dict]:
        """Generate all shifts"""
        shifts = []
        shift_id = 0
        
        for day in days:
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                for vehicle_idx in range(service['vehicles']['quantity']):
                    for shift in service['shifts']:
                        start_hour, start_min = map(int, shift['start_time'].split(':'))
                        end_hour, end_min = map(int, shift['end_time'].split(':'))
                        
                        shifts.append({
                            'id': shift_id,
                            'date': day,
                            'service_id': service['id'],
                            'service_name': service['name'],
                            'vehicle': vehicle_idx,
                            'shift_number': shift['shift_number'],
                            'start_time': shift['start_time'],
                            'end_time': shift['end_time'],
                            'start_hour': start_hour,
                            'end_hour': end_hour,
                            'duration_hours': shift['duration_hours'],
                            'is_sunday': day.weekday() == 6,
                            'week_num': (day.day - 1) // 7 + 1
                        })
                        shift_id += 1
        
        return shifts
    
    def _format_solution(self, assignments: List[Dict], drivers: List[SimpleDriver], 
                        shifts: List[Dict], elapsed: float) -> Dict[str, Any]:
        """Format solution for output"""
        # Build assignment list
        formatted_assignments = []
        for assignment in assignments:
            shift = assignment['shift']
            formatted_assignments.append({
                'date': shift['date'].isoformat(),
                'service': shift['service_id'],
                'service_name': shift['service_name'],
                'shift': shift['shift_number'],
                'vehicle': shift['vehicle'],
                'driver_id': assignment['driver_id'],
                'driver_name': assignment['driver_name'],
                'start_time': shift['start_time'],
                'end_time': shift['end_time'],
                'duration_hours': shift['duration_hours']
            })
        
        # Build driver stats
        driver_stats = {}
        active_count = 0
        
        for driver in drivers:
            if driver.total_hours > 0:
                active_count += 1
                driver_stats[driver.id] = {
                    'name': driver.name,
                    'hours': round(driver.total_hours, 1),
                    'days_worked': len(driver.days_worked),
                    'sundays_worked': len(driver.sundays_worked),
                    'shifts_count': len(driver.shifts),
                    'weekly_hours': {k: round(v, 1) for k, v in driver.hours_by_week.items()}
                }
        
        # Calculate metrics with proper salary rates
        total_hours = sum(s['duration_hours'] for s in shifts)
        avg_hours = total_hours / active_count if active_count > 0 else 0
        
        # Calculate total cost with different rates for full-time and part-time
        total_cost = 0
        FULL_TIME_HOURLY_RATE = 10000  # $10,000 per hour for full-time
        PART_TIME_HOURLY_RATE = 12000  # $12,000 per hour for part-time
        PART_TIME_MIN_SALARY = 500000  # $500,000 minimum for part-time
        
        # Create driver_summary for HTML report compatibility
        driver_summary = {}
        for driver in drivers:
            if driver.total_hours > 0:
                # Determine contract type based on hours worked
                # Full-time: >100 hours/month, Part-time: <=100 hours/month
                is_full_time = driver.total_hours > 100
                contract_type = 'full_time' if is_full_time else 'part_time'
                
                # Calculate driver salary
                if is_full_time:
                    driver_salary = driver.total_hours * FULL_TIME_HOURLY_RATE
                else:
                    # Part-time: higher hourly rate with minimum salary
                    driver_salary = max(driver.total_hours * PART_TIME_HOURLY_RATE, PART_TIME_MIN_SALARY)
                
                total_cost += driver_salary
                
                driver_summary[driver.id] = {
                    'name': driver.name,
                    'contract_type': contract_type,
                    'total_hours': round(driver.total_hours, 1),
                    'total_assignments': len(driver.shifts),
                    'utilization': round((driver.total_hours / 180) * 100, 1) if driver.total_hours > 0 else 0,  # 180 hours max per month
                    'sundays_worked': len(driver.sundays_worked),
                    'days_worked': len(driver.days_worked),
                    'salary': round(driver_salary)  # Added salary field
                }
        
        # Calculate quality metrics
        avg_utilization = sum(d['utilization'] for d in driver_summary.values()) / len(driver_summary) if driver_summary else 0
        theoretical_min_drivers = max(1, int(total_hours / 180))  # 180 hours max per driver per month
        optimality_ratio = theoretical_min_drivers / active_count if active_count > 0 else 0
        
        quality_description = "EXCELENTE" if optimality_ratio > 0.8 else "BUENA" if optimality_ratio > 0.6 else "ACEPTABLE"
        
        return {
            'status': 'success',
            'assignments': formatted_assignments,
            'drivers_used': active_count,
            'driver_stats': driver_stats,
            'driver_summary': driver_summary,  # Added for HTML report compatibility
            'metrics': {
                'total_shifts': len(shifts),
                'total_hours': round(total_hours, 1),
                'total_cost': round(total_cost),
                'drivers_used': active_count,
                'avg_hours_per_driver': round(avg_hours, 1),
                'optimization_time': round(elapsed, 2),
                'solver_type': 'simple_heuristic'
            },
            'quality_metrics': {
                'quality': f"Solución {quality_description}",
                'optimality_ratio': optimality_ratio,
                'theoretical_min_drivers': theoretical_min_drivers,
                'efficiency_metrics': {
                    'avg_utilization': round(avg_utilization, 1),
                    'max_utilization': round(max(d['utilization'] for d in driver_summary.values()) if driver_summary else 0, 1),
                    'min_utilization': round(min(d['utilization'] for d in driver_summary.values()) if driver_summary else 0, 1)
                }
            },
            'validation': {
                'is_valid': True,
                'message': f'Legal solution found in {elapsed:.2f}s',
                'drivers_needed': active_count,
                'method': 'Simple Fast Heuristic'
            }
        }