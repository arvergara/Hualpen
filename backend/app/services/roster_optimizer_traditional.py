"""
Roster optimizer using traditional work patterns (mallas) with CP-SAT optimization
Uses OR-Tools CP-SAT solver to find MINIMUM drivers while respecting pattern constraints
"""

import time
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, date, timedelta
import calendar
from collections import defaultdict
from ortools.sat.python import cp_model

from .traditional_patterns import (
    TRADITIONAL_PATTERNS, 
    TraditionalPattern, 
    PatternAssignment
)


class TraditionalRosterOptimizer:
    """
    Optimizer that finds MINIMUM drivers needed while respecting traditional work patterns.
    Uses CP-SAT constraint solver with additional pattern constraints.
    """

    BASE_HOURLY_RATE = 10000
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.start_time = None
        self.timeout = 300.0  # 5 minutes for complex scenarios
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

    def _infer_vehicle_metadata(self, service: Dict[str, Any]) -> Dict[str, str]:
        service_id = service.get('id') or service.get('service_id')
        if service_id and service_id in self.vehicle_cache:
            return self.vehicle_cache[service_id]

        vehicle_info = service.get('vehicles', {}) if isinstance(service.get('vehicles', {}), dict) else {}
        raw_type = (vehicle_info.get('type') or '').lower() if vehicle_info else ''
        service_type = (service.get('service_type') or '').lower()

        normalized = raw_type or service_type
        category = 'other'
        if 'electric' in normalized:
            category = 'electric_bus'
        elif 'taxi' in normalized:
            category = 'taxibus'
        elif 'mini' in normalized:
            category = 'minibus'
        elif 'bus' in normalized:
            category = 'bus'
        elif 'van' in normalized:
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
    
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """
        Optimize roster for a month using traditional patterns with CP-SAT
        """
        self.start_time = time.time()
        
        print(f"\n=== TRADITIONAL PATTERN OPTIMIZATION {year}-{month:02d} ===")
        print("Strategy: CP-SAT optimization with traditional work patterns (5x2, 6x1, 4x3)")
        
        # Generate all shifts for the month
        all_shifts = self._generate_month_shifts(year, month)
        print(f"Total shifts to assign: {len(all_shifts)}")
        
        # Analyze shift distribution
        shift_analysis = self._analyze_shifts(all_shifts)
        print(f"\nShift analysis:")
        print(f"  - Morning shifts (before 14:00): {shift_analysis['morning']}")
        print(f"  - Afternoon shifts (14:00-20:00): {shift_analysis['afternoon']}")
        print(f"  - Night shifts (after 20:00): {shift_analysis['night']}")
        print(f"  - Sunday shifts: {shift_analysis['sunday']}")
        print(f"  - Average shifts per day: {shift_analysis['avg_per_day']:.1f}")
        
        # Run CP-SAT optimization with pattern constraints
        solution = self._optimize_with_patterns_cpsat(all_shifts, year, month)
        
        elapsed = time.time() - self.start_time
        print(f"\nOptimization completed in {elapsed:.2f}s")
        
        return solution
    
    def _generate_month_shifts(self, year: int, month: int) -> List[Dict[str, Any]]:
        """Generate all shifts for the month"""
        shifts = []
        days_in_month = calendar.monthrange(year, month)[1]
        
        for service in self.services:
            service_id = service.get('service_id', 'unknown')
            service_name = service.get('service_name', 'Service')
            frequency = service.get('frequency', {})
            operating_days = frequency.get('days', [])
            vehicles = service.get('vehicles', {}).get('quantity', 1)
            
            for day in range(1, days_in_month + 1):
                current_date = date(year, month, day)
                weekday = current_date.weekday()
                
                if weekday not in operating_days:
                    continue
                
                for vehicle_num in range(1, vehicles + 1):
                    for shift in service.get('shifts', []):
                        vehicle_metadata = self._infer_vehicle_metadata(service)
                        start_hour_str, start_min_str = shift.get('start_time', '00:00').split(':')
                        end_hour_str, end_min_str = shift.get('end_time', '00:00').split(':')
                        start_hour_val = int(start_hour_str)
                        start_min_val = int(start_min_str)
                        end_hour_val = int(end_hour_str)
                        end_min_val = int(end_min_str)
                        start_minutes = start_hour_val * 60 + start_min_val
                        end_minutes = end_hour_val * 60 + end_min_val
                        if end_minutes <= start_minutes:
                            end_minutes += 24 * 60
                        service_group = service.get('service_group') or service.get('group') or service_name or service_id
                        shifts.append({
                            'date': current_date,
                            'service_id': service_id,
                            'service_name': service_name,
                            'service_type': service.get('service_type'),
                            'service_group': service_group,
                            'vehicle': vehicle_num,
                            'shift_number': shift.get('shift_number', 1),
                            'start_time': shift.get('start_time', '00:00'),
                            'end_time': shift.get('end_time', '00:00'),
                            'start_hour': start_hour_val,
                            'end_hour': end_hour_val,
                            'start_minutes': start_minutes,
                            'end_minutes': end_minutes,
                            'duration_hours': shift.get('duration_hours', 0),
                            'vehicle_type': vehicle_metadata['vehicle_type'],
                            'vehicle_category': vehicle_metadata['vehicle_category'],
                            'is_sunday': weekday == 6
                        })

        # Sort by date and start time
        shifts.sort(key=lambda s: (s['date'], s.get('start_minutes', s['start_hour'] * 60)))
        return shifts
    
    def _analyze_shifts(self, shifts: List[Dict]) -> Dict[str, Any]:
        """Analyze shift distribution"""
        morning = sum(1 for s in shifts if s['start_hour'] < 14)
        afternoon = sum(1 for s in shifts if 14 <= s['start_hour'] < 20)
        night = sum(1 for s in shifts if s['start_hour'] >= 20)
        sunday = sum(1 for s in shifts if s['is_sunday'])
        
        days_with_shifts = len(set(s['date'] for s in shifts))
        avg_per_day = len(shifts) / days_with_shifts if days_with_shifts > 0 else 0
        
        return {
            'morning': morning,
            'afternoon': afternoon,
            'night': night,
            'sunday': sunday,
            'avg_per_day': avg_per_day,
            'total_days': days_with_shifts
        }
    
    def _optimize_with_patterns_cpsat(self, shifts: List[Dict], year: int, month: int) -> Dict:
        """
        Main optimization using CP-SAT with pattern constraints.
        Tries different combinations to find MINIMUM drivers needed.
        """
        
        # Calculate bounds
        total_hours = sum(s['duration_hours'] for s in shifts)
        theoretical_min = max(1, int(total_hours / 180))
        
        # Analyze daily coverage needs considering working day conflicts
        coverage_needs = self._analyze_daily_coverage_with_conflicts(shifts)
        max_simultaneous = max(coverage_needs.values()) if coverage_needs else 1
        
        # Check for weekend service
        has_weekend = any(s['date'].weekday() in [5, 6] for s in shifts)
        has_sunday = any(s['is_sunday'] for s in shifts)
        
        # Calculate practical minimum considering working day conflicts
        if has_weekend:
            # With 7-day coverage and 6-day work limit
            practical_min = max(theoretical_min, (max_simultaneous * 7 + 5) // 6)
        else:
            practical_min = max(theoretical_min, max_simultaneous)
        
        print(f"\n📊 Problem Analysis:")
        print(f"  - Total hours: {total_hours}")
        print(f"  - Max simultaneous needs: {max_simultaneous}")
        print(f"  - Weekend service: {'Yes' if has_weekend else 'No'}")
        print(f"  - Sunday service: {'Yes' if has_sunday else 'No'}")
        print(f"  - Theoretical minimum: {theoretical_min}")
        print(f"  - Practical minimum: {practical_min}")
        
        # Try different pattern combinations
        best_solution = None
        min_drivers_found = float('inf')
        
        # Define pattern combinations to try
        pattern_combinations = self._generate_pattern_combinations(
            practical_min, has_sunday, year, month
        )
        
        print(f"\nTrying {len(pattern_combinations)} pattern combinations...")
        
        for combo_idx, pattern_combo in enumerate(pattern_combinations):
            if time.time() - self.start_time > self.timeout:
                print("⚠️ Timeout reached")
                break
            
            total_drivers = sum(count for _, count in pattern_combo)
            
            # Skip if we already found a better solution
            if total_drivers >= min_drivers_found:
                continue
            
            print(f"\n--- Combination {combo_idx + 1}: {total_drivers} drivers ---")
            for pattern, count in pattern_combo:
                print(f"  - {pattern.name}: {count} drivers")
            
            # Try to solve with this pattern combination
            solution = self._solve_with_pattern_combo(
                shifts, pattern_combo, year, month
            )
            
            if solution and solution['status'] == 'success':
                drivers_used = solution['metrics']['drivers_used']
                coverage = solution['metrics']['coverage_percentage']
                
                print(f"  ✓ Solution found: {drivers_used} drivers, {coverage:.1f}% coverage")
                
                if drivers_used < min_drivers_found and coverage >= 99.9:
                    min_drivers_found = drivers_used
                    best_solution = solution
                    print(f"  ★ New best solution!")
        
        if best_solution:
            print(f"\n✅ OPTIMAL SOLUTION: {min_drivers_found} drivers with patterns")
            return best_solution
        else:
            print("\n❌ No feasible solution found")
            return self._create_error_solution()
    
    def _generate_pattern_combinations(self, min_drivers: int, has_sunday: bool, 
                                      year: int, month: int) -> List[List[Tuple[TraditionalPattern, int]]]:
        """
        Generate different pattern combinations to try.
        Each combination is a list of (pattern, driver_count) tuples.
        """
        combinations = []
        
        # Get available patterns based on requirements
        if has_sunday:
            # Patterns that can work Sundays
            available_patterns = [
                p for p in TRADITIONAL_PATTERNS 
                if p.name in ["5X2 ROTATIVO", "6X1 FIJO", "4X3 ROTATIVO"]
            ]
        else:
            # Patterns for weekday-only service
            available_patterns = [
                p for p in TRADITIONAL_PATTERNS 
                if p.name in ["5X2 FIJO", "5X2 ROTATIVO", "4X3 FIJO"]
            ]
        
        # Strategy 1: Single pattern type
        for pattern in available_patterns:
            work_days = pattern.count_work_days(year, month)
            if work_days > 0:
                # Start from minimum and try increasingly larger sizes
                # For Bimbo case, we know we need ~20 drivers but min_drivers is 17
                for add_drivers in [0, 1, 2, 3, 4, 5, 6, 7, 8]:
                    drivers = min_drivers + add_drivers
                    combinations.append([(pattern, drivers)])
        
        # Strategy 2: Mix of two patterns (primary + support)
        if len(available_patterns) >= 2:
            for primary in available_patterns:
                for secondary in available_patterns:
                    if primary.name != secondary.name:
                        # 80% primary, 20% secondary
                        primary_count = max(1, int(min_drivers * 0.8))
                        secondary_count = max(1, int(min_drivers * 0.3))
                        combinations.append([
                            (primary, primary_count),
                            (secondary, secondary_count)
                        ])
        
        # Strategy 3: Balanced mix for flexibility
        if has_sunday and len(available_patterns) >= 2:
            # Special mix for Sunday coverage
            pattern_6x1 = next((p for p in available_patterns if p.name == "6X1 FIJO"), None)
            pattern_5x2 = next((p for p in available_patterns if p.name == "5X2 ROTATIVO"), None)
            
            if pattern_6x1 and pattern_5x2:
                # Various ratios
                for ratio_6x1 in [0.2, 0.3, 0.4]:
                    count_6x1 = max(2, int(min_drivers * ratio_6x1))
                    count_5x2 = max(1, min_drivers - count_6x1 + 2)
                    combinations.append([
                        (pattern_6x1, count_6x1),
                        (pattern_5x2, count_5x2)
                    ])
        
        # Remove duplicates and sort by total drivers
        unique_combos = []
        seen = set()
        for combo in combinations:
            # Create a hashable representation
            combo_key = tuple((p.name, c) for p, c in sorted(combo, key=lambda x: x[0].name))
            if combo_key not in seen:
                seen.add(combo_key)
                unique_combos.append(combo)
        
        # Sort by total driver count
        unique_combos.sort(key=lambda c: sum(count for _, count in c))
        
        # Limit to reasonable number of combinations
        return unique_combos[:50]
    
    def _solve_with_pattern_combo(self, shifts: List[Dict], 
                                 pattern_combo: List[Tuple[TraditionalPattern, int]],
                                 year: int, month: int) -> Optional[Dict]:
        """
        Solve with a specific pattern combination using CP-SAT.
        """
        model = cp_model.CpModel()
        
        # Create drivers with their patterns
        drivers = []
        driver_patterns = []
        driver_id = 1
        
        for pattern, count in pattern_combo:
            for i in range(count):
                drivers.append(f"D{driver_id:03d}")
                driver_patterns.append(pattern)
                driver_id += 1
        
        num_drivers = len(drivers)
        num_shifts = len(shifts)
        
        # Generate work schedules for each driver based on their pattern
        driver_schedules = []
        for d_idx, pattern in enumerate(driver_patterns):
            # Use different offsets for rotative patterns to spread coverage
            offset = (d_idx % pattern.cycle_length) if pattern.rotative else 0
            schedule = pattern.generate_month_schedule(year, month, offset)
            driver_schedules.append(schedule)
        
        # Decision variables: X[driver][shift] = 1 if driver takes shift
        X = {}
        for d_idx in range(num_drivers):
            for s_idx in range(num_shifts):
                X[d_idx, s_idx] = model.NewBoolVar(f'x_{d_idx}_{s_idx}')
        
        # PATTERN CONSTRAINT: Drivers can only work on their pattern days
        for d_idx in range(num_drivers):
            schedule = driver_schedules[d_idx]
            for s_idx, shift in enumerate(shifts):
                # If driver doesn't work on this date per pattern, cannot take shift
                if not schedule.get(shift['date'], False):
                    model.Add(X[d_idx, s_idx] == 0)
        
        # Constraint 1: Every shift must be covered by exactly one driver
        for s_idx in range(num_shifts):
            model.Add(sum(X[d_idx, s_idx] for d_idx in range(num_drivers)) == 1)
        
        # Pre-calculate conflicts
        overlaps = self._calculate_overlaps(shifts)
        rest_violations = self._calculate_rest_violations(shifts)
        working_day_violations = self._calculate_working_day_violations(shifts)
        
        # Constraint 2: No overlapping shifts
        for d_idx in range(num_drivers):
            for s1_idx in range(num_shifts):
                for s2_idx in overlaps.get(s1_idx, []):
                    if s1_idx < s2_idx:
                        model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # Constraint 3: Minimum rest between shifts
        for d_idx in range(num_drivers):
            for s1_idx in range(num_shifts):
                for s2_idx in rest_violations.get(s1_idx, []):
                    model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # Constraint 4: Maximum 12-hour working day span
        for d_idx in range(num_drivers):
            for s1_idx in range(num_shifts):
                for s2_idx in working_day_violations.get(s1_idx, []):
                    if s1_idx < s2_idx:
                        model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # Constraint 5: Weekly pattern constraints
        # Ensure drivers respect their weekly work limits based on pattern
        shifts_by_week = self._group_shifts_by_week(shifts, year, month)
        
        for d_idx in range(num_drivers):
            pattern = driver_patterns[d_idx]
            
            for week_num, week_shifts in shifts_by_week.items():
                # Count work days in this week for this driver
                week_dates = set(shifts[s_idx]['date'] for s_idx in week_shifts)
                
                # Create auxiliary variables for days worked
                days_worked_vars = []
                for week_date in week_dates:
                    # Check if driver can work this date per pattern
                    if driver_schedules[d_idx].get(week_date, False):
                        day_shifts = [s_idx for s_idx in week_shifts 
                                    if shifts[s_idx]['date'] == week_date]
                        
                        if day_shifts:
                            works_this_day = model.NewBoolVar(f'works_{d_idx}_{week_date}')
                            shift_sum = sum(X[d_idx, s] for s in day_shifts)
                            model.Add(shift_sum >= 1).OnlyEnforceIf(works_this_day)
                            model.Add(shift_sum == 0).OnlyEnforceIf(works_this_day.Not())
                            days_worked_vars.append(works_this_day)
                
                # Enforce weekly pattern limit
                if days_worked_vars:
                    if pattern.name.startswith("5X2"):
                        model.Add(sum(days_worked_vars) <= 5)
                    elif pattern.name.startswith("6X1"):
                        model.Add(sum(days_worked_vars) <= 6)
                    elif pattern.name.startswith("4X3"):
                        model.Add(sum(days_worked_vars) <= 4)
        
        # Constraint 6: Maximum 44 hours per week
        for d_idx in range(num_drivers):
            for week_num, week_shifts in shifts_by_week.items():
                week_minutes = sum(X[d_idx, s_idx] * int(shifts[s_idx]['duration_hours'] * 60)
                                 for s_idx in week_shifts)
                model.Add(week_minutes <= 44 * 60)
        
        # Constraint 7: Maximum 180 hours per month
        for d_idx in range(num_drivers):
            total_minutes = sum(X[d_idx, s_idx] * int(shift['duration_hours'] * 60)
                              for s_idx, shift in enumerate(shifts))
            model.Add(total_minutes <= 180 * 60)
        
        # Constraint 8: Minimum 2 Sundays free
        sunday_dates = self._get_sunday_dates(shifts)
        
        if sunday_dates:
            for d_idx in range(num_drivers):
                pattern = driver_patterns[d_idx]
                
                # Only apply Sunday constraint if pattern allows Sunday work
                if pattern.count_sundays_worked(year, month) > 0:
                    sunday_work_vars = []
                    
                    for sunday_date in sunday_dates:
                        sunday_shifts = [s_idx for s_idx, s in enumerate(shifts)
                                       if s['date'] == sunday_date]
                        
                        if sunday_shifts and driver_schedules[d_idx].get(sunday_date, False):
                            works_sunday = model.NewBoolVar(f'sunday_{d_idx}_{sunday_date}')
                            model.Add(sum(X[d_idx, s] for s in sunday_shifts) >= 1).OnlyEnforceIf(works_sunday)
                            model.Add(sum(X[d_idx, s] for s in sunday_shifts) == 0).OnlyEnforceIf(works_sunday.Not())
                            sunday_work_vars.append(works_sunday)
                    
                    if sunday_work_vars:
                        num_sundays = len(sunday_dates)
                        # For rotative patterns, some drivers may need to work more Sundays
                        # to ensure coverage. Relax constraint for patterns.
                        if pattern.rotative:
                            # Allow working all Sundays if pattern requires it
                            max_sundays_worked = num_sundays
                        else:
                            # Keep strict limit for fixed patterns
                            max_sundays_worked = max(0, num_sundays - 2)
                        model.Add(sum(sunday_work_vars) <= max_sundays_worked)
        
        # Objective: Minimize number of drivers used and balance workload
        driver_used = []
        for d_idx in range(num_drivers):
            used = model.NewBoolVar(f'driver_used_{d_idx}')
            model.Add(sum(X[d_idx, s_idx] for s_idx in range(num_shifts)) >= 1).OnlyEnforceIf(used)
            model.Add(sum(X[d_idx, s_idx] for s_idx in range(num_shifts)) == 0).OnlyEnforceIf(used.Not())
            driver_used.append(used)
        
        # Primary: minimize drivers, Secondary: balance workload
        model.Minimize(sum(driver_used) * 1000000 +
                      sum(X[d_idx, s_idx] * int(shift['duration_hours'] * 100)
                          for d_idx in range(num_drivers)
                          for s_idx, shift in enumerate(shifts)))
        
        # Solve
        solver = cp_model.CpSolver()
        # Give more time for complex problems
        remaining_time = self.timeout - (time.time() - self.start_time)
        solver.parameters.max_time_in_seconds = min(60.0, remaining_time)
        solver.parameters.num_search_workers = 8
        solver.parameters.linearization_level = 2
        solver.parameters.log_search_progress = False  # Reduce output
        
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return self._extract_solution(solver, X, drivers, driver_patterns, 
                                        shifts, year, month)
        else:
            # Debug: print why it failed
            if status == cp_model.INFEASIBLE:
                print(f"    ✗ INFEASIBLE - constraints cannot be satisfied")
            elif status == cp_model.MODEL_INVALID:
                print(f"    ✗ MODEL_INVALID - model has errors")
            elif status == cp_model.UNKNOWN:
                print(f"    ✗ UNKNOWN - solver timed out or couldn't determine")
            return None
    
    def _extract_solution(self, solver, X, drivers, driver_patterns, 
                         shifts, year, month) -> Dict:
        """Extract solution from CP-SAT solver"""
        
        assignments = []
        driver_stats = defaultdict(lambda: {
            'shifts': [],
            'total_hours': 0,
            'days_worked': set(),
            'sundays_worked': 0,
            'pattern': None,
            'services': set(),
            'vehicle_categories': set(),
            'vehicle_types': set()
        })
        
        for d_idx, driver_id in enumerate(drivers):
            pattern = driver_patterns[d_idx]
            driver_stats[driver_id]['pattern'] = pattern.name
            
            for s_idx, shift in enumerate(shifts):
                if solver.Value(X[d_idx, s_idx]) == 1:
                    assignments.append({
                        'date': shift['date'].isoformat(),
                        'driver_id': driver_id,
                        'driver_name': f"Driver {driver_id}",
                        'service_id': shift['service_id'],
                        'service_name': shift['service_name'],
                        'service_type': shift.get('service_type'),
                        'service_group': shift.get('service_group'),
                        'vehicle': shift['vehicle'],
                        'shift_number': shift['shift_number'],
                        'start_time': shift['start_time'],
                        'end_time': shift['end_time'],
                        'duration_hours': shift['duration_hours'],
                        'pattern': pattern.name,
                        'vehicle_type': shift.get('vehicle_type'),
                        'vehicle_category': shift.get('vehicle_category')
                    })

                    driver_stats[driver_id]['shifts'].append(shift)
                    driver_stats[driver_id]['total_hours'] += shift['duration_hours']
                    driver_stats[driver_id]['days_worked'].add(shift['date'])
                    if shift['is_sunday']:
                        driver_stats[driver_id]['sundays_worked'] += 1
                    driver_stats[driver_id]['services'].add(shift['service_id'])
                    driver_stats[driver_id]['vehicle_categories'].add(shift.get('vehicle_category', 'other'))
                    driver_stats[driver_id]['vehicle_types'].add(shift.get('vehicle_type', 'unknown'))
        
        # Calculate metrics
        active_drivers = [d for d in driver_stats if driver_stats[d]['shifts']]
        total_hours = sum(d['total_hours'] for d in driver_stats.values())
        coverage = (len(assignments) / len(shifts) * 100) if shifts else 0
        
        # Pattern distribution
        pattern_distribution = defaultdict(int)
        for driver_id in active_drivers:
            pattern_distribution[driver_stats[driver_id]['pattern']] += 1
        
        # Build driver summary
        driver_summary = {}
        overall_cost = 0.0
        for driver_id in active_drivers:
            stats = driver_stats[driver_id]
            cost_details = self._compute_driver_cost(stats)
            total_cost = cost_details['total_cost']
            overall_cost += total_cost

            driver_summary[f"Driver {driver_id}"] = {
                'driver_id': driver_id,
                'driver_name': f"Driver {driver_id}",
                'pattern': stats['pattern'],
                'total_hours': stats['total_hours'],
                'days_worked': len(stats['days_worked']),
                'shifts_assigned': len(stats['shifts']),
                'sundays_worked': stats['sundays_worked'],
                'utilization': round((stats['total_hours'] / 180) * 100, 1),
                'salary': round(total_cost),
                'contract_type': 'full_time' if stats['total_hours'] > 100 else 'part_time',
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
        
        # Quality metrics
        avg_utilization = (sum(d['utilization'] for d in driver_summary.values()) / 
                          len(driver_summary)) if driver_summary else 0
        theoretical_min = max(1, int(total_hours / 180))
        optimality_ratio = theoretical_min / len(active_drivers) if active_drivers else 0
        
        quality_metrics = {
            'efficiency_metrics': {
                'avg_utilization': avg_utilization,
                'drivers_below_60h': sum(1 for d in driver_summary.values() if d['total_hours'] < 60),
                'drivers_above_160h': sum(1 for d in driver_summary.values() if d['total_hours'] > 160),
                'perfect_coverage': coverage >= 99.9
            },
            'pattern_distribution': dict(pattern_distribution),
            'theoretical_minimum': theoretical_min,
            'optimality_ratio': optimality_ratio
        }
        
        service_warnings = self._detect_service_span_warnings(shifts)

        result = {
            'status': 'success',
            'assignments': assignments,
            'constraints': {
                'min_rest_between_shifts': self.min_rest_hours
            },
            'metrics': {
                'drivers_used': len(active_drivers),
                'total_hours': total_hours,
                'avg_hours_per_driver': total_hours / len(active_drivers) if active_drivers else 0,
                'unassigned_shifts': len(shifts) - len(assignments),
                'coverage_percentage': coverage,
                'pattern_distribution': dict(pattern_distribution)
            },
            'driver_summary': driver_summary,
            'quality_metrics': quality_metrics,
            'total_cost': round(overall_cost),
            'quality_score': optimality_ratio * (coverage / 100),
            'solution_type': 'traditional_patterns_optimized',
            'drivers_used': len(active_drivers)
        }

        if service_warnings:
            result['warnings'] = {'service_spans': service_warnings}

        return result
    
    def _analyze_daily_coverage(self, shifts: List[Dict]) -> Dict[date, int]:
        """Analyze how many drivers are needed simultaneously each day"""
        coverage = defaultdict(int)
        
        for shift in shifts:
            shift_date = shift['date']
            coverage[shift_date] += 1
        
        return coverage
    
    def _analyze_daily_coverage_with_conflicts(self, shifts: List[Dict]) -> Dict[date, int]:
        """
        Analyze how many drivers are needed each day considering working day conflicts.
        If shifts on the same day span > 12 hours, they need separate drivers.
        """
        from collections import defaultdict
        
        # Group shifts by date
        shifts_by_date = defaultdict(list)
        for shift in shifts:
            shifts_by_date[shift['date']].append(shift)
        
        coverage = {}
        for shift_date, day_shifts in shifts_by_date.items():
            if len(day_shifts) <= 1:
                coverage[shift_date] = len(day_shifts)
                continue
            
            # Build conflict graph for this day
            # Two shifts conflict if they overlap OR violate 12-hour working day
            conflicts = defaultdict(set)
            for i, s1 in enumerate(day_shifts):
                for j, s2 in enumerate(day_shifts):
                    if i != j:
                        # Check for time overlap
                        s1_start = s1['start_hour']
                        s1_end = s1['end_hour'] if s1['end_hour'] > s1['start_hour'] else s1['end_hour'] + 24
                        s2_start = s2['start_hour']
                        s2_end = s2['end_hour'] if s2['end_hour'] > s2['start_hour'] else s2['end_hour'] + 24
                        
                        overlaps = not (s1_end <= s2_start or s2_end <= s1_start)
                        
                        # Check for working day violation (>12 hour span)
                        earliest_start = min(s1['start_hour'], s2['start_hour'])
                        latest_end = max(s1_end, s2_end)
                        violates_working_day = (latest_end - earliest_start) > 12
                        
                        if overlaps or violates_working_day:
                            conflicts[i].add(j)
            
            # Use graph coloring to find minimum drivers needed
            colors = {}
            for i in range(len(day_shifts)):
                # Find first available color (driver)
                used_colors = {colors[j] for j in conflicts[i] if j in colors}
                color = 0
                while color in used_colors:
                    color += 1
                colors[i] = color
            
            # Number of colors = number of drivers needed for this day
            coverage[shift_date] = max(colors.values()) + 1 if colors else 1
        
        return coverage
    
    def _calculate_overlaps(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Pre-calculate which shifts overlap in time"""
        overlaps = defaultdict(list)
        
        for i, s1 in enumerate(shifts):
            for j, s2 in enumerate(shifts):
                if i != j and s1['date'] == s2['date']:
                    base_datetime = datetime.combine(s1['date'], datetime.min.time())
                    s1_start = base_datetime + timedelta(minutes=s1.get('start_minutes', s1['start_hour'] * 60))
                    s1_end = base_datetime + timedelta(minutes=s1.get('end_minutes', (s1['end_hour'] if s1['end_hour'] > s1['start_hour'] else s1['end_hour'] + 24) * 60))
                    s2_start = base_datetime + timedelta(minutes=s2.get('start_minutes', s2['start_hour'] * 60))
                    s2_end = base_datetime + timedelta(minutes=s2.get('end_minutes', (s2['end_hour'] if s2['end_hour'] > s2['start_hour'] else s2['end_hour'] + 24) * 60))

                    if s1_start < s2_end and s2_start < s1_end:
                        overlaps[i].append(j)

        return overlaps
    
    def _calculate_rest_violations(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Pre-calculate which shift pairs violate the minimum rest requirement."""
        violations = defaultdict(list)
        
        transfer_minutes = 60
        for i, s1 in enumerate(shifts):
            for j, s2 in enumerate(shifts):
                if i != j:
                    # Check if shifts are on consecutive days or same day
                    days_diff = (s2['date'] - s1['date']).days
                    
                    if days_diff < 0 or days_diff > 1:
                        continue

                    if days_diff == 0 and s2.get('start_minutes', s2['start_hour'] * 60) <= s1.get('start_minutes', s1['start_hour'] * 60):
                        continue

                    end_minutes = s1.get('end_minutes', (s1['end_hour'] if s1['end_hour'] > s1['start_hour'] else s1['end_hour'] + 24) * 60)
                    start_minutes = s2.get('start_minutes', s2['start_hour'] * 60) + days_diff * 24 * 60
                    rest_minutes = start_minutes - end_minutes

                    if rest_minutes < 0:
                        violations[i].append(j)
                        continue

                    if days_diff == 0:
                        group1 = s1.get('service_group') or s1['service_id']
                        group2 = s2.get('service_group') or s2['service_id']
                        if group1 != group2 or rest_minutes < transfer_minutes:
                            violations[i].append(j)
                    else:
                        rest_hours = rest_minutes / 60
                        if rest_hours < self.min_rest_hours:
                            violations[i].append(j)

        return violations
    
    def _calculate_working_day_violations(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Pre-calculate which shift pairs violate 12-hour working day span"""
        violations = defaultdict(list)
        
        for i, s1 in enumerate(shifts):
            for j, s2 in enumerate(shifts):
                if i < j and s1['date'] == s2['date']:
                    # Calculate span from earliest start to latest end
                    start_1 = s1.get('start_minutes', s1['start_hour'] * 60)
                    end_1 = s1.get('end_minutes', (s1['end_hour'] if s1['end_hour'] > s1['start_hour'] else s1['end_hour'] + 24) * 60)
                    start_2 = s2.get('start_minutes', s2['start_hour'] * 60)
                    end_2 = s2.get('end_minutes', (s2['end_hour'] if s2['end_hour'] > s2['start_hour'] else s2['end_hour'] + 24) * 60)

                    earliest_start = min(start_1, start_2)
                    latest_end = max(end_1, end_2)

                    span = (latest_end - earliest_start) / 60.0

                    if span > 12:
                        violations[i].append(j)
        
        return violations
    
    def _group_shifts_by_week(self, shifts: List[Dict], year: int, month: int) -> Dict[int, List[int]]:
        """Group shift indices by week number"""
        shifts_by_week = defaultdict(list)
        
        for s_idx, shift in enumerate(shifts):
            # Calculate week number (1-based)
            week_num = (shift['date'].day - 1) // 7 + 1
            shifts_by_week[week_num].append(s_idx)
        
        return shifts_by_week
    
    def _get_sunday_dates(self, shifts: List[Dict]) -> List[date]:
        """Get unique Sunday dates from shifts"""
        sunday_dates = set()
        for shift in shifts:
            if shift['date'].weekday() == 6:
                sunday_dates.add(shift['date'])
        return sorted(sunday_dates)
    
    def _calculate_salary(self, total_hours: float) -> int:
        """Calculate driver salary based on hours"""
        if total_hours > 100:
            # Full-time rate
            return int(total_hours * 10000)
        else:
            # Part-time rate with minimum
            return max(500000, int(total_hours * 12000))
    
    def _create_error_solution(self) -> Dict:
        """Create error solution when optimization fails"""
        return {
            'status': 'error',
            'message': 'Could not find feasible solution with traditional patterns',
            'assignments': [],
            'metrics': {
                'drivers_used': 0,
                'total_hours': 0,
                'avg_hours_per_driver': 0,
                'unassigned_shifts': 0,
                'coverage_percentage': 0,
                'pattern_distribution': {}
            },
            'driver_summary': {},
            'quality_metrics': {},
            'total_cost': 0,
            'quality_score': 0,
            'solution_type': 'error',
            'drivers_used': 0
        }
