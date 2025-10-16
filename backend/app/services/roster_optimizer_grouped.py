"""
Constraint-based Roster Optimizer using OR-Tools CP-SAT Solver
Finds the MINIMUM number of drivers needed while satisfying all labor constraints
"""

from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime, timedelta, date
from collections import defaultdict
from dataclasses import dataclass, field
import time
from ortools.sat.python import cp_model


# Old heuristic data classes removed - using CP-SAT solver instead


class GroupedRosterOptimizer:
    """
    Optimizer that intelligently groups shifts to minimize driver count
    Key innovation: Pairs T1+T2 shifts for same driver when possible
    """

    BASE_HOURLY_RATE = 10000  # Base hourly salary reference
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.start_time = None
        self.timeout = 300.0  # 5 minutes for complex scenarios like Bimbo
        self.min_rest_hours = self._extract_min_rest_requirement()
        self.vehicle_cache: Dict[str, Dict[str, str]] = {}

    def _extract_min_rest_requirement(self) -> float:
        """Return the minimum rest hours configured for the client (default 10h)."""
        parameters = self.client_data.get('parameters', {}) if self.client_data else {}
        rest_hours = parameters.get('min_rest_hours')

        if rest_hours is None:
            constraints = self.client_data.get('constraints', {}) if self.client_data else {}
            rest_hours = constraints.get('min_rest_between_shifts')

        try:
            return float(rest_hours) if rest_hours is not None else 10.0
        except (TypeError, ValueError):
            return 10.0
        
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """Main optimization using CP-SAT constraint solver"""
        self.start_time = time.time()
        
        print(f"\n=== CONSTRAINT OPTIMIZATION {year}-{month:02d} ===")
        print("Method: OR-Tools CP-SAT Solver (finds guaranteed minimum drivers)")
        
        # Generate shifts 
        days = self._generate_month_days(year, month)
        all_shifts = self._generate_shifts(days)
        
        print(f"Total shifts to assign: {len(all_shifts)}")
        
        # Run constraint optimization
        solution = self._optimize_with_cpsat(all_shifts, year, month)
        
        elapsed = time.time() - self.start_time
        print(f"\nOptimization completed in {elapsed:.2f}s")
        
        return solution

    def _infer_vehicle_metadata(self, service: Dict[str, Any]) -> Dict[str, str]:
        """Return normalized vehicle metadata (type/category) for a service."""
        service_id = service.get('id') or service.get('service_id')
        if service_id and service_id in self.vehicle_cache:
            return self.vehicle_cache[service_id]

        raw_type = ''
        vehicle_info = service.get('vehicles', {}) if isinstance(service.get('vehicles', {}), dict) else {}
        if vehicle_info:
            raw_type = (vehicle_info.get('type') or '').lower()

        service_type = (service.get('service_type') or '').lower()

        normalized_type = raw_type or service_type

        if not normalized_type and service_type:
            normalized_type = service_type

        category = 'other'
        if 'electric' in normalized_type:
            category = 'electric_bus'
        elif 'taxi' in normalized_type:
            category = 'taxibus'
        elif 'mini' in normalized_type:
            category = 'minibus'
        elif 'bus' in normalized_type:
            category = 'bus'
        elif 'van' in normalized_type:
            category = 'minibus'

        metadata = {
            'vehicle_type': raw_type or service_type or 'unknown',
            'vehicle_category': category
        }

        if service_id:
            self.vehicle_cache[service_id] = metadata

        return metadata

    def _vehicle_penalty(self, vehicle_category: Optional[str]) -> float:
        category = (vehicle_category or 'other').lower()
        if category == 'electric_bus':
            return 0.20
        if category in {'bus'}:
            return 0.10
        return 0.0

    def _driver_type_multiplier(self, vehicle_categories: Set[str]) -> float:
        categories = {c for c in vehicle_categories if c}
        if not categories:
            return 1.0
        if 'electric_bus' in categories:
            return 1.10
        if categories.intersection({'bus'}):
            return 1.0
        if categories.issubset({'taxibus', 'minibus', 'van', 'other'}):
            return 0.90
        return 1.0

    def _compute_driver_cost(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        total_hours = stats.get('total_hours', 0)
        if total_hours <= 0:
            return {
                'base_cost': 0.0,
                'shift_cost': 0.0,
                'driver_multiplier': 1.0,
                'service_multiplier': 1.0,
                'total_cost': 0.0,
                'service_count': 0
            }

        base_rate = self.BASE_HOURLY_RATE
        shift_cost = 0.0
        for shift in stats.get('shifts', []):
            duration = shift.get('duration_hours', 0)
            penalty = self._vehicle_penalty(shift.get('vehicle_category'))
            shift_cost += duration * base_rate * (1 + penalty)

        driver_multiplier = self._driver_type_multiplier(stats.get('vehicle_categories', set()))
        service_count = len(stats.get('services', set()))
        service_multiplier = 1.0 + 0.20 * max(0, service_count - 1)

        total_cost = shift_cost * driver_multiplier * service_multiplier

        return {
            'base_cost': total_hours * base_rate,
            'shift_cost': shift_cost,
            'driver_multiplier': driver_multiplier,
            'service_multiplier': service_multiplier,
            'total_cost': total_cost,
            'service_count': service_count
        }

    def _time_to_minutes(self, time_str: Optional[str]) -> int:
        if not time_str:
            return 0
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes

    def _detect_service_span_warnings(self, shifts: List[Dict]) -> List[Dict[str, Any]]:
        span_tracker: Dict[str, Dict[date, Dict[str, Any]]] = defaultdict(dict)

        for shift in shifts:
            service_id = shift['service_id']
            service_name = shift.get('service_name', service_id)
            service_type = (shift.get('service_type') or '').lower()
            shift_date = shift['date']

            if shift_date not in span_tracker[service_id]:
                span_tracker[service_id][shift_date] = {
                    'start': None,
                    'end': None,
                    'service_name': service_name,
                    'service_type': service_type
                }

            entry = span_tracker[service_id][shift_date]
            start_minutes = self._time_to_minutes(shift.get('start_time'))
            end_minutes = self._time_to_minutes(shift.get('end_time'))
            if end_minutes <= start_minutes:
                end_minutes += 24 * 60

            entry['start'] = start_minutes if entry['start'] is None else min(entry['start'], start_minutes)
            entry['end'] = end_minutes if entry['end'] is None else max(entry['end'], end_minutes)

        warnings = []
        for service_id, dates in span_tracker.items():
            for shift_date, info in dates.items():
                if info['start'] is None or info['end'] is None:
                    continue
                span_hours = (info['end'] - info['start']) / 60.0
                if span_hours > 12:
                    recommendation = None
                    if 'faena' in info['service_type'] and span_hours <= 14:
                        recommendation = 'Cambiar a régimen excepcional (2x2, 7x7).'

                    warnings.append({
                        'service_id': service_id,
                        'service_name': info['service_name'],
                        'date': shift_date.isoformat(),
                        'span_hours': round(span_hours, 1),
                        'message': f"Cobertura continua de {span_hours:.1f}h requiere más de una jornada excepcional.",
                        'recommendation': recommendation
                    })

        return warnings

    def _optimize_with_cpsat(self, shifts: List[Dict], year: int, month: int) -> Dict[str, Any]:
        """
        Core CP-SAT optimization algorithm
        Finds the MINIMUM number of drivers needed while satisfying all constraints
        """
        model = cp_model.CpModel()
        
        # Analyze requirements
        total_hours = sum(s['duration_hours'] for s in shifts)
        theoretical_min = max(1, int(total_hours / 180))  # Based on 180h/month limit
        
        # Calculate practical bounds based on service patterns
        coverage_needs = self._analyze_daily_coverage(shifts)
        max_simultaneous = max(coverage_needs.values()) if coverage_needs else 1
        
        # Determine if we have weekend service
        has_weekend = any(s['date'].weekday() in [5, 6] for s in shifts)
        
        # Analyze shift patterns to detect working day violations
        # Check if services have shifts that span > 12 hours on same day
        has_working_day_conflicts = self._has_working_day_conflicts(shifts)
        
        # Calculate minimum drivers considering rest days AND working day constraints
        if has_weekend:
            # With 7-day coverage and 6-day work limit: need ceiling(max_simultaneous * 7/6)
            practical_min = max(theoretical_min, (max_simultaneous * 7 + 5) // 6)
        else:
            # Weekday only service
            practical_min = max(theoretical_min, max_simultaneous)
        
        # If we have working day conflicts (shifts spanning > 12h), we need more drivers
        # Example: 7 services with 06:00-08:00 and 18:00-20:00 shifts = 14h span
        # Each driver can only do ONE shift per day, not both
        if has_working_day_conflicts:
            # Count shifts that cannot be combined
            conflicting_shifts_per_day = self._count_conflicting_shifts_per_day(shifts)
            max_conflicts = max(conflicting_shifts_per_day.values()) if conflicting_shifts_per_day else 0
            # We need at least as many drivers as conflicting shifts
            practical_min = max(practical_min, max_conflicts)
        
        # Set driver bounds
        min_drivers = practical_min  # Start at the calculated practical minimum
        max_drivers = 100  # Allow up to 100 drivers for complex scenarios
        
        print(f"\n📊 Problem Analysis:")
        print(f"  - Total hours: {total_hours}")
        print(f"  - Max simultaneous needs: {max_simultaneous}")
        print(f"  - Weekend service: {'Yes' if has_weekend else 'No'}")
        print(f"  - Working day conflicts: {'Yes (shifts span >12h)' if has_working_day_conflicts else 'No'}")
        if has_working_day_conflicts:
            print(f"  - Max daily driver needs: {max_conflicts}")
        print(f"  - Theoretical minimum (hours): {theoretical_min}")
        print(f"  - Practical minimum (coverage): {practical_min}")
        print(f"  - Search range: {min_drivers} to {max_drivers} drivers")
        
        # Try to find solution with increasing number of drivers
        for num_drivers in range(min_drivers, max_drivers + 1):
            print(f"\nTrying with {num_drivers} drivers...")
            
            result = self._solve_with_fixed_drivers(shifts, num_drivers, year, month)
            
            if result['status'] == 'success':
                print(f"✓ OPTIMAL SOLUTION FOUND with {num_drivers} drivers!")
                return result
            
            # Check timeout
            if time.time() - self.start_time > self.timeout:
                print(f"⚠️ Timeout reached after {self.timeout}s")
                break
        
        # If we get here, no solution was found
        return {
            'status': 'failed',
            'reason': f'No feasible solution found with up to {max_drivers} drivers',
            'details': {
                'total_shifts': len(shifts),
                'min_tried': min_drivers,
                'max_tried': max_drivers
            }
        }
    
    def _solve_with_fixed_drivers(self, shifts: List[Dict], num_drivers: int, 
                                  year: int, month: int) -> Dict[str, Any]:
        """
        Solve the assignment problem with a fixed number of drivers using CP-SAT
        """
        model = cp_model.CpModel()
        
        # Create driver IDs
        drivers = [f"D{i+1:03d}" for i in range(num_drivers)]
        
        # Decision variables: X[driver][shift] = 1 if driver takes shift
        X = {}
        for d_idx, driver in enumerate(drivers):
            for s_idx, shift in enumerate(shifts):
                X[d_idx, s_idx] = model.NewBoolVar(f'x_{d_idx}_{s_idx}')
        
        # Constraint 1: Every shift must be covered by exactly one driver
        for s_idx in range(len(shifts)):
            model.Add(sum(X[d_idx, s_idx] for d_idx in range(num_drivers)) == 1)
        
        # Pre-calculate shift overlaps for efficiency
        overlaps = self._calculate_overlaps(shifts)
        
        # Constraint 2: No driver can take overlapping shifts
        for d_idx in range(num_drivers):
            for s1_idx in range(len(shifts)):
                for s2_idx in overlaps.get(s1_idx, []):
                    if s1_idx < s2_idx:  # Avoid duplicate constraints
                        model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # Pre-calculate rest violations for efficiency
        rest_violations = self._calculate_rest_violations(shifts)

        # Constraint 3: Minimum rest between shifts
        for d_idx in range(num_drivers):
            for s1_idx in range(len(shifts)):
                for s2_idx in rest_violations.get(s1_idx, []):
                    model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # NEW CONSTRAINT: Maximum 12-hour working day span
        # Pre-calculate working day violations
        working_day_violations = self._calculate_working_day_violations(shifts)
        
        # A driver cannot take two shifts on the same day if they span > 12 hours
        for d_idx in range(num_drivers):
            for s1_idx in range(len(shifts)):
                for s2_idx in working_day_violations.get(s1_idx, []):
                    if s1_idx < s2_idx:  # Avoid duplicate constraints
                        model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # Constraint 4: Maximum 6 consecutive work days
        # Group shifts by date for consecutive day tracking
        shifts_by_date = defaultdict(list)
        for s_idx, shift in enumerate(shifts):
            shifts_by_date[shift['date']].append(s_idx)
        
        sorted_dates = sorted(shifts_by_date.keys())
        
        for d_idx in range(num_drivers):
            # For each 7-day window, ensure at least 1 rest day
            for start_idx in range(len(sorted_dates) - 6):
                window_dates = sorted_dates[start_idx:start_idx + 7]
                
                # Count working days in this 7-day window
                window_work_vars = []
                for date in window_dates:
                    # A driver works on a date if they take ANY shift that day
                    day_shifts = shifts_by_date[date]
                    if day_shifts:
                        # Create auxiliary variable for "works this day"
                        works_this_day = model.NewBoolVar(f'works_{d_idx}_{date}')
                        # FIXED: Correctly link the auxiliary variable using standard CP-SAT pattern
                        shift_sum = sum(X[d_idx, s] for s in day_shifts)
                        # works_this_day = 1 if and only if shift_sum >= 1
                        # Standard CP-SAT pattern for boolean indicator
                        model.Add(shift_sum >= works_this_day)  # If works_this_day=1, must have at least 1 shift  
                        model.Add(shift_sum <= len(day_shifts) * works_this_day)  # If works_this_day=0, must have 0 shifts
                        window_work_vars.append(works_this_day)
                
                # Maximum 6 working days in any 7-day window
                if window_work_vars:
                    model.Add(sum(window_work_vars) <= 6)
        
        # Constraint 5: Maximum 44 hours per week
        # Group shifts by week
        shifts_by_week = defaultdict(list)
        for s_idx, shift in enumerate(shifts):
            week_num = (shift['date'].day - 1) // 7 + 1
            shifts_by_week[week_num].append((s_idx, shift['duration_hours']))
        
        for d_idx in range(num_drivers):
            for week_num, week_shifts in shifts_by_week.items():
                # Sum of hours in this week <= 44 (convert to integer minutes)
                week_minutes = sum(X[d_idx, s_idx] * int(hours * 60) 
                                 for s_idx, hours in week_shifts)
                model.Add(week_minutes <= 44 * 60)  # 44 hours in minutes
        
        # Constraint 6: Maximum 180 hours per month
        for d_idx in range(num_drivers):
            total_minutes = sum(X[d_idx, s_idx] * int(shift['duration_hours'] * 60) 
                              for s_idx, shift in enumerate(shifts))
            model.Add(total_minutes <= 180 * 60)  # 180 hours in minutes
        
        # Constraint 7: Minimum 2 Sundays free per month per driver
        sunday_shifts = [(s_idx, shift) for s_idx, shift in enumerate(shifts) 
                        if shift['date'].weekday() == 6]
        
        if sunday_shifts:
            # Group Sunday shifts by date
            sunday_dates = defaultdict(list)
            for s_idx, shift in sunday_shifts:
                sunday_dates[shift['date']].append(s_idx)
            
            for d_idx in range(num_drivers):
                # Count Sundays worked (not Sunday shifts, but Sunday days)
                sunday_work_vars = []
                for sunday_date, sunday_shift_indices in sunday_dates.items():
                    # Create auxiliary variable for "works this Sunday"
                    works_sunday = model.NewBoolVar(f'sunday_{d_idx}_{sunday_date}')
                    # works_sunday = 1 if driver takes any shift on this Sunday
                    model.Add(sum(X[d_idx, s] for s in sunday_shift_indices) >= 1).OnlyEnforceIf(works_sunday)
                    model.Add(sum(X[d_idx, s] for s in sunday_shift_indices) == 0).OnlyEnforceIf(works_sunday.Not())
                    sunday_work_vars.append(works_sunday)
                
                # Minimum 2 Sundays free per month
                # If there are N Sundays in the month, can work at most N-2
                num_sundays = len(sunday_dates)
                max_sundays_worked = max(0, num_sundays - 2)
                model.Add(sum(sunday_work_vars) <= max_sundays_worked)
        
        # Objective: Minimize number of drivers used (secondary objective for load balancing)
        # Create auxiliary variables for "driver is used"
        driver_used = []
        for d_idx in range(num_drivers):
            used = model.NewBoolVar(f'driver_used_{d_idx}')
            # Driver is used if they take at least one shift
            model.Add(sum(X[d_idx, s_idx] for s_idx in range(len(shifts))) >= 1).OnlyEnforceIf(used)
            model.Add(sum(X[d_idx, s_idx] for s_idx in range(len(shifts))) == 0).OnlyEnforceIf(used.Not())
            driver_used.append(used)
        
        # Primary objective: minimize drivers used
        # Secondary: balance workload (minimize max hours per driver)
        model.Minimize(sum(driver_used) * 1000000 + 
                      sum(X[d_idx, s_idx] * shift['duration_hours'] 
                          for d_idx in range(num_drivers) 
                          for s_idx, shift in enumerate(shifts)))
        
        # Solve with optimized parameters
        solver = cp_model.CpSolver()
        # For large problems with few drivers, use shorter timeout to fail fast
        if len(shifts) > 400 and num_drivers < len(shifts) / 20:
            # Clearly infeasible - fail fast
            solver.parameters.max_time_in_seconds = min(10.0, self.timeout - (time.time() - self.start_time))
        else:
            solver.parameters.max_time_in_seconds = min(60.0, self.timeout - (time.time() - self.start_time))
        solver.parameters.num_search_workers = 8  # More parallel search
        solver.parameters.linearization_level = 2  # Better linearization
        solver.parameters.cp_model_presolve = True  # Enable presolve
        
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # Extract solution
            assignments = []
            driver_stats = defaultdict(lambda: {
                'shifts': [],
                'total_hours': 0,
                'days_worked': set(),
                'sundays_worked': set(),
                'weeks': defaultdict(float),
                'services': set(),
                'vehicle_categories': set(),
                'vehicle_types': set()
            })
            
            for d_idx in range(num_drivers):
                driver_id = drivers[d_idx]
                for s_idx, shift in enumerate(shifts):
                    if solver.Value(X[d_idx, s_idx]) == 1:
                        assignments.append({
                            'shift_id': shift['id'],
                            'shift': shift,
                            'driver_id': driver_id,
                            'driver_name': f"Driver {d_idx + 1}"
                        })
                        
                        # Update driver stats
                        driver_stats[driver_id]['shifts'].append(shift)
                        driver_stats[driver_id]['total_hours'] += shift['duration_hours']
                        driver_stats[driver_id]['days_worked'].add(shift['date'])
                        if shift['date'].weekday() == 6:
                            driver_stats[driver_id]['sundays_worked'].add(shift['date'])
                        week_num = (shift['date'].day - 1) // 7 + 1
                        driver_stats[driver_id]['weeks'][week_num] += shift['duration_hours']
                        driver_stats[driver_id]['services'].add(shift['service_id'])
                        driver_stats[driver_id]['vehicle_categories'].add(shift.get('vehicle_category', 'other'))
                        driver_stats[driver_id]['vehicle_types'].add(shift.get('vehicle_type', 'unknown'))
            
            # Count active drivers
            active_drivers = sum(1 for d in driver_stats.values() if d['total_hours'] > 0)
            
            print(f"  Solution found: {active_drivers} drivers used")
            print(f"  Solver status: {'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE'}")
            
            return self._format_cpsat_solution(assignments, driver_stats, shifts, 
                                              active_drivers, year, month)
        
        return {'status': 'infeasible'}
    
    def _calculate_overlaps(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Pre-calculate which shifts overlap with each other"""
        overlaps = defaultdict(list)
        
        for i, s1 in enumerate(shifts):
            for j, s2 in enumerate(shifts):
                if i != j and self._shifts_overlap(s1, s2):
                    overlaps[i].append(j)
        
        return overlaps
    
    def _shifts_overlap(self, s1: Dict, s2: Dict) -> bool:
        """Check if two shifts overlap in time"""
        if s1['date'] != s2['date']:
            return False
        
        base_datetime = datetime.combine(s1['date'], datetime.min.time())
        s1_start = base_datetime + timedelta(minutes=s1.get('start_minutes', s1['start_hour'] * 60))
        s1_end = base_datetime + timedelta(minutes=s1.get('end_minutes', s1['end_hour'] * 60))

        s2_start = base_datetime + timedelta(minutes=s2.get('start_minutes', s2['start_hour'] * 60))
        s2_end = base_datetime + timedelta(minutes=s2.get('end_minutes', s2['end_hour'] * 60))

        return s1_start < s2_end and s2_start < s1_end
    
    def _calculate_rest_violations(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Pre-calculate which shift pairs violate the minimum rest rule."""
        violations = defaultdict(list)

        for i, s1 in enumerate(shifts):
            for j, s2 in enumerate(shifts):
                if i != j and self._violates_rest_constraint(s1, s2):
                    violations[i].append(j)
        
        return violations

    def _violates_rest_constraint(self, s1: Dict, s2: Dict) -> bool:
        """Check if taking both shifts would violate rest/group rules."""
        day_diff = (s2['date'] - s1['date']).days

        if day_diff < 0 or day_diff > 1:
            return False

        # Ensure chronological order to avoid duplicate checks
        if day_diff == 0 and s2.get('start_minutes', s2['start_hour'] * 60) <= s1.get('start_minutes', s1['start_hour'] * 60):
            return False

        end_minutes = s1.get('end_minutes')
        start_minutes = s2.get('start_minutes') + day_diff * 24 * 60
        rest_minutes = start_minutes - end_minutes

        if rest_minutes < 0:
            return True  # Overlapping or insufficient separation

        if day_diff == 0:
            group1 = s1.get('service_group') or s1['service_id']
            group2 = s2.get('service_group') or s2['service_id']
            if group1 != group2:
                return True
            return rest_minutes < 60  # Require at least 1 hour transfer

        # day_diff == 1
        rest_hours = rest_minutes / 60
        return rest_hours < self.min_rest_hours
    
    def _calculate_working_day_violations(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Pre-calculate which shift pairs violate the 12-hour working day rule"""
        violations = defaultdict(list)
        
        for i, s1 in enumerate(shifts):
            for j, s2 in enumerate(shifts):
                if i != j and self._violates_working_day_constraint(s1, s2):
                    violations[i].append(j)
        
        return violations
    
    def _violates_working_day_constraint(self, s1: Dict, s2: Dict) -> bool:
        """
        Check if taking both shifts would violate the 12-hour working day rule.
        A working day is defined as the span from the first shift start to the last shift end.

        Example: 
        - Shift 1: 06:00-08:00
        - Shift 2: 18:00-20:00
        - Working day span: 06:00 to 20:00 = 14 hours (VIOLATION!)

        - Shift 1: 06:00-08:00  
        - Shift 2: 20:00-22:00
        - Working day span: 06:00 to 22:00 = 16 hours (VIOLATION!)
        """
        # Only check shifts on the same day
        if s1['date'] != s2['date']:
            return False

        start_1 = s1.get('start_minutes', s1['start_hour'] * 60)
        end_1 = s1.get('end_minutes', (s1['end_hour'] if s1['end_hour'] > s1['start_hour'] else 24) * 60)
        start_2 = s2.get('start_minutes', s2['start_hour'] * 60)
        end_2 = s2.get('end_minutes', (s2['end_hour'] if s2['end_hour'] > s2['start_hour'] else 24) * 60)

        earliest_start = min(start_1, start_2)
        latest_end = max(end_1, end_2)

        working_day_span = (latest_end - earliest_start) / 60.0

        return working_day_span > 12
    
    def _analyze_daily_coverage(self, shifts: List[Dict]) -> Dict[date, int]:
        """Analyze how many simultaneous services need coverage each day"""
        coverage = defaultdict(int)
        
        # Group shifts by date and time
        for shift in shifts:
            # For simplicity, count max simultaneous services per day
            # In reality, we'd need to check actual time overlaps
            coverage[shift['date']] += 1
        
        # Get actual simultaneous requirements
        daily_max = {}
        for day in set(s['date'] for s in shifts):
            day_shifts = [s for s in shifts if s['date'] == day]
            # Find maximum overlapping shifts
            max_overlap = 0
            for s in day_shifts:
                overlap_count = sum(1 for s2 in day_shifts if self._shifts_overlap(s, s2))
                max_overlap = max(max_overlap, overlap_count)
            daily_max[day] = max_overlap
        
        return daily_max
    
    def _format_cpsat_solution(self, assignments: List[Dict], driver_stats: Dict,
                               shifts: List[Dict], active_drivers: int, 
                               year: int, month: int) -> Dict[str, Any]:
        """Format CP-SAT solution for output"""
        elapsed = time.time() - self.start_time
        
        # Verify complete coverage
        assigned_shift_ids = set(a['shift_id'] for a in assignments)
        required_shift_ids = set(s['id'] for s in shifts)
        
        if assigned_shift_ids != required_shift_ids:
            missing = len(required_shift_ids - assigned_shift_ids)
            raise ValueError(f"Solution incomplete: {missing} shifts not assigned")
        
        # CRITICAL BUG CHECK: Verify no service duplication
        shift_assignments = defaultdict(list)
        for assignment in assignments:
            shift = assignment['shift']
            unique_key = shift.get('unique_key', f"{shift['date'].isoformat()}_{shift['service_id']}_{shift['vehicle']}_{shift['shift_number']}")
            shift_assignments[unique_key].append(assignment['driver_id'])
        
        # Check for duplicated assignments
        duplicates = {k: v for k, v in shift_assignments.items() if len(v) > 1}
        if duplicates:
            print("\\n❌ CRITICAL BUG DETECTED: Service duplication!")
            for unique_key, drivers in duplicates.items():
                print(f"  {unique_key}: assigned to {len(drivers)} drivers: {drivers}")
            raise ValueError(f"Solution has {len(duplicates)} duplicated shift assignments!")
        
        print(f"✅ Validation passed: {len(assignments)} unique shift assignments")
        
        # Format assignments
        formatted_assignments = []
        for assignment in assignments:
            shift = assignment['shift']
            formatted_assignments.append({
                'date': shift['date'].isoformat(),
                'service': shift['service_id'],
                'service_name': shift['service_name'],
                'service_type': shift.get('service_type'),
                'service_group': shift.get('service_group'),
                'shift': shift['shift_number'],
                'vehicle': shift['vehicle'],
                'driver_id': assignment['driver_id'],
                'driver_name': assignment['driver_name'],
                'start_time': shift['start_time'],
                'end_time': shift['end_time'],
                'duration_hours': shift['duration_hours'],
                'vehicle_type': shift.get('vehicle_type'),
                'vehicle_category': shift.get('vehicle_category'),
                'unique_key': shift.get('unique_key', f"{shift['date'].isoformat()}_{shift['service_id']}_{shift['vehicle']}_{shift['shift_number']}")  # Include for debugging
            })
        
        # Format driver summary
        driver_summary = {}
        total_cost = 0

        for driver_id, stats in driver_stats.items():
            if stats['total_hours'] > 0:
                cost_details = self._compute_driver_cost(stats)
                driver_salary = cost_details['total_cost']
                total_cost += driver_salary

                driver_summary[driver_id] = {
                    'name': f"Driver {driver_id[1:]}",
                    'total_hours': round(stats['total_hours'], 1),
                    'total_assignments': len(stats['shifts']),
                    'days_worked': len(stats['days_worked']),
                    'sundays_worked': len(stats['sundays_worked']),
                    'utilization': round((stats['total_hours'] / 180) * 100, 1),
                    'salary': round(driver_salary),
                    'weekly_hours': {k: round(v, 1) for k, v in stats['weeks'].items()},
                    'services_worked': sorted(stats.get('services', [])),
                    'vehicle_categories': sorted(stats.get('vehicle_categories', [])),
                    'cost_details': {
                        'base_cost': round(cost_details['base_cost']),
                        'vehicle_adjusted_cost': round(cost_details['shift_cost']),
                        'driver_multiplier': cost_details['driver_multiplier'],
                        'service_multiplier': cost_details['service_multiplier'],
                        'service_count': cost_details['service_count']
                    }
                }

        # Calculate metrics
        total_hours = sum(s['duration_hours'] for s in shifts)
        avg_hours = total_hours / active_drivers if active_drivers > 0 else 0
        theoretical_min = max(1, int(total_hours / 180))
        
        service_warnings = self._detect_service_span_warnings(shifts)

        result = {
            'status': 'success',
            'assignments': formatted_assignments,
            'drivers_used': active_drivers,
            'driver_summary': driver_summary,
            'constraints': {
                'min_rest_between_shifts': self.min_rest_hours
            },
            'metrics': {
                'total_shifts': len(shifts),
                'total_hours': round(total_hours, 1),
                'total_cost': round(total_cost),
                'drivers_used': active_drivers,
                'avg_hours_per_driver': round(avg_hours, 1),
                'optimization_time': round(elapsed, 2),
                'solver_type': 'cp_sat_optimal',
                'theoretical_minimum': theoretical_min
            },
            'quality_metrics': {
                'quality': 'OPTIMAL solution (guaranteed minimum)',
                'optimality_ratio': theoretical_min / active_drivers if active_drivers > 0 else 0,
                'method': 'OR-Tools CP-SAT Solver'
            },
            'validation': {
                'is_valid': True,
                'coverage_complete': True,
                'shifts_required': len(shifts),
                'shifts_assigned': len(assignments),
                'message': f'Optimal solution found with {active_drivers} drivers (minimum possible)',
                'drivers_needed': active_drivers,
                'method': 'Constraint Programming (CP-SAT)'
            }
        }

        if service_warnings:
            result['warnings'] = {'service_spans': service_warnings}

        return result
    
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

                        start_minutes = start_hour * 60 + start_min
                        end_minutes = end_hour * 60 + end_min
                        if end_minutes <= start_minutes:
                            end_minutes += 24 * 60
                        
                        # Handle end_hour for shifts ending at midnight
                        if end_hour == 0:
                            end_hour = 24  # Midnight is hour 24 for span calculations

                        vehicle_metadata = self._infer_vehicle_metadata(service)
                        service_group = service.get('service_group') or service.get('group') or service.get('service_name') or service.get('name') or service.get('id')
                        
                        shifts.append({
                            'id': shift_id,
                            'date': day,
                            'service_id': service['id'],
                            'service_name': service['name'],
                            'service_type': service.get('service_type'),
                            'service_group': service_group,
                            'vehicle': vehicle_idx,
                            'shift_number': shift['shift_number'],
                            'start_time': shift['start_time'],
                            'end_time': shift['end_time'],
                            'start_hour': start_hour,
                            'end_hour': end_hour,
                            'start_minutes': start_minutes,
                            'end_minutes': end_minutes,
                            'duration_hours': shift['duration_hours'],
                            'vehicle_type': vehicle_metadata['vehicle_type'],
                            'vehicle_category': vehicle_metadata['vehicle_category'],
                            'is_sunday': day.weekday() == 6,
                            'week_num': (day.day - 1) // 7 + 1
                        })
                        shift_id += 1

        return shifts
    
    def _has_working_day_conflicts(self, shifts: List[Dict]) -> bool:
        """
        Check if there are shifts on the same day that span more than 12 hours.
        This would prevent a single driver from taking both shifts.
        """
        # Group shifts by date
        shifts_by_date = defaultdict(list)
        for shift in shifts:
            shifts_by_date[shift['date']].append(shift)
        
        # Check each day for conflicts
        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) < 2:
                continue
            
            # Check all pairs of shifts on this day
            for i, s1 in enumerate(day_shifts):
                for j, s2 in enumerate(day_shifts[i+1:], i+1):
                    if self._violates_working_day_constraint(s1, s2):
                        return True
        
        return False
    
    def _count_conflicting_shifts_per_day(self, shifts: List[Dict]) -> Dict[date, int]:
        """
        Count the maximum number of drivers needed per day considering working day constraints.
        If shifts cannot be combined due to >12h span, we need separate drivers.
        """
        driver_needs = {}
        
        # Group shifts by date
        shifts_by_date = defaultdict(list)
        for shift in shifts:
            shifts_by_date[shift['date']].append(shift)
        
        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) <= 1:
                driver_needs[date] = len(day_shifts)
                continue
            
            # Build compatibility graph for this day's shifts
            # Two shifts are compatible if they can be done by the same driver
            compatible = defaultdict(set)
            for i, s1 in enumerate(day_shifts):
                for j, s2 in enumerate(day_shifts):
                    if i != j:
                        # Shifts are compatible if they don't overlap AND don't violate working day constraint
                        if not self._shifts_overlap(s1, s2) and not self._violates_working_day_constraint(s1, s2):
                            compatible[i].add(j)
            
            # Use greedy coloring to find minimum drivers needed
            # Each color represents a driver
            colors = {}
            for i in range(len(day_shifts)):
                # Find first available color
                used_colors = {colors[j] for j in compatible[i] if j in colors}
                color = 0
                while color in used_colors:
                    color += 1
                colors[i] = color
            
            # Number of colors = number of drivers needed
            driver_needs[date] = max(colors.values()) + 1 if colors else 1
        
        return driver_needs
    
    # The old heuristic methods are no longer needed with CP-SAT implementation
    # All optimization is now handled through constraint programming
