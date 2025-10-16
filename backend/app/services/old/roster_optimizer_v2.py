"""
Optimizador de turnos v2 - Mejorado para maximizar utilización de conductores
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from dataclasses import dataclass
import json


@dataclass
class Driver:
    """Representa un conductor"""
    id: str
    name: str
    contract_type: str  # 'full_time', 'part_time_20h', 'part_time_30h'
    base_salary: float
    home_location: Tuple[float, float] = (-36.8201, -73.0444)  # Concepción
    max_monthly_hours: int = 180
    max_weekly_hours: int = 44  # Límite legal Chile
    current_month_hours: float = 0
    sundays_worked: int = 0
    last_shift_end: datetime = None
    skills: List[str] = None
    
    def __post_init__(self):
        if self.skills is None:
            self.skills = ['bus', 'minibus']


class RosterOptimizerV2:
    """
    Optimizador mejorado que maximiza la utilización de conductores
    respetando los límites legales chilenos
    """
    
    def __init__(self, client_data: Dict[str, Any], drivers: List[Driver] = None):
        self.client_data = client_data
        self.services = client_data['services']
        self.costs = client_data['costs']
        self.parameters = client_data['parameters']
        
        if drivers is None:
            self.drivers = self._create_optimal_driver_pool()
        else:
            self.drivers = drivers
        
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.assignments = {}
        self.solution_metrics = {}
    
    def _create_optimal_driver_pool(self) -> List[Driver]:
        """Crea un pool óptimo de conductores basado en la carga real"""
        drivers = []
        
        # Calcular horas totales necesarias
        total_hours_needed = sum(
            service['vehicles']['quantity'] * 
            sum(shift['duration_hours'] for shift in service['shifts']) * 
            len(service['frequency']['days']) * 4.3  # 4.3 semanas promedio
            for service in self.services
        )
        
        print(f"Horas totales necesarias al mes: {total_hours_needed:.1f}")
        
        # Análisis mejorado: Un conductor puede hacer múltiples turnos por día
        # si hay suficiente separación entre ellos (mínimo 5 horas de descanso)
        
        # Agrupar turnos por horario para ver cuáles son simultáneos
        morning_shifts = 0
        afternoon_shifts = 0
        night_shifts = 0
        
        for service in self.services:
            for shift in service['shifts']:
                start_hour = int(shift['start_time'].split(':')[0])
                if start_hour < 12:
                    morning_shifts += service['vehicles']['quantity']
                elif start_hour < 18:
                    afternoon_shifts += service['vehicles']['quantity']
                else:
                    night_shifts += service['vehicles']['quantity']
        
        # El máximo de turnos simultáneos en cualquier período
        max_simultaneous = max(morning_shifts, afternoon_shifts, night_shifts)
        
        print(f"Turnos mañana: {morning_shifts}")
        print(f"Turnos tarde: {afternoon_shifts}")
        print(f"Turnos noche: {night_shifts}")
        
        # Un conductor puede hacer hasta 2 turnos por día (mañana+tarde o tarde+noche)
        # si hay al menos 5 horas de separación
        daily_capacity_per_driver = 2  # turnos
        min_drivers_for_coverage = max_simultaneous
        
        # También calcular por horas totales
        avg_effective_hours = 160  # horas/mes por conductor
        drivers_by_hours = int(total_hours_needed / avg_effective_hours)
        
        print(f"Conductores mínimos por cobertura simultánea: {min_drivers_for_coverage}")
        print(f"Conductores por horas totales: {drivers_by_hours}")
        
        # Tomar el máximo y agregar buffer suficiente
        # Para El Soldado: necesitamos 8 en la mañana, pero algunos pueden hacer doble turno
        # Sin embargo, con domingos libres y descansos, necesitamos más buffer
        base_drivers_needed = max(min_drivers_for_coverage, drivers_by_hours)
        total_drivers = int(base_drivers_needed * 1.5)  # 50% buffer para cubrir descansos y domingos libres
        
        # Asegurar un mínimo absoluto
        total_drivers = max(total_drivers, min_drivers_for_coverage + 4)
        
        # Mix óptimo: 80% full time, 15% part time 30h, 5% part time 20h
        num_full_time = max(int(total_drivers * 0.8), base_drivers_needed)
        num_part_30h = int(total_drivers * 0.15)
        num_part_20h = int(total_drivers * 0.05)
        
        # Crear conductores Full Time
        for i in range(num_full_time):
            drivers.append(Driver(
                id=f"FT_{i+1:03d}",
                name=f"Conductor Full Time {i+1}",
                contract_type='full_time',
                base_salary=self.costs['full_time']['base_salary'],
                max_monthly_hours=180,
                max_weekly_hours=44
            ))
        
        # Crear conductores Part Time 30h
        for i in range(num_part_30h):
            drivers.append(Driver(
                id=f"PT30_{i+1:03d}",
                name=f"Conductor Part Time 30h {i+1}",
                contract_type='part_time_30h',
                base_salary=self.costs['part_time_30h']['base_salary'],
                max_monthly_hours=120,
                max_weekly_hours=30
            ))
        
        # Crear conductores Part Time 20h
        for i in range(num_part_20h):
            drivers.append(Driver(
                id=f"PT20_{i+1:03d}",
                name=f"Conductor Part Time 20h {i+1}",
                contract_type='part_time_20h',
                base_salary=self.costs['part_time_20h']['base_salary'],
                max_monthly_hours=80,
                max_weekly_hours=20
            ))
        
        print(f"Pool óptimo creado: {len(drivers)} conductores")
        print(f"  - Full Time: {num_full_time} (pueden trabajar hasta 180h/mes)")
        print(f"  - Part Time 30h: {num_part_30h} (hasta 120h/mes)")
        print(f"  - Part Time 20h: {num_part_20h} (hasta 80h/mes)")
        print(f"  - Capacidad total: {num_full_time*180 + num_part_30h*120 + num_part_20h*80} horas/mes")
        
        return drivers
    
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """Optimiza los turnos para un mes completo"""
        print(f"\n=== OPTIMIZANDO {year}-{month:02d} ===")
        
        # Generar días del mes
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
        
        print(f"Período: {len(days)} días")
        print(f"Servicios: {len(self.services)}")
        print(f"Conductores disponibles: {len(self.drivers)}")
        
        # Crear variables
        self._create_decision_variables(days)
        
        # Restricciones obligatorias
        print("\nAgregando restricciones...")
        self._add_service_coverage_constraints(days)
        self._add_no_overlap_constraints(days)
        self._add_weekly_hours_constraints(days)  # 44h/semana
        self._add_monthly_hours_constraints(days)  # 180h/mes
        self._add_sunday_constraints(days)  # 2 domingos libres
        self._add_rest_day_constraints(days)  # 1 día libre por semana
        
        # Función objetivo mejorada
        self._set_balanced_objective(days)
        
        # Resolver
        print("\nResolviendo modelo...")
        self.solver.parameters.max_time_in_seconds = 120.0
        self.solver.parameters.num_search_workers = 8
        
        # Agregar hint para acelerar búsqueda
        self._add_initial_solution_hint(days)
        
        status = self.solver.Solve(self.model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"✓ Solución {'ÓPTIMA' if status == cp_model.OPTIMAL else 'FACTIBLE'} encontrada")
            return self._extract_solution(days)
        else:
            print(f"✗ No se encontró solución. Status: {status}")
            return {'status': 'failed', 'message': self._get_failure_reason(status)}
    
    def _create_decision_variables(self, days: List[date]):
        """Crea variables binarias para cada posible asignación"""
        for day in days:
            day_key = day.isoformat()
            self.assignments[day_key] = {}
            
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                service_id = service['id']
                self.assignments[day_key][service_id] = {}
                
                for shift in service['shifts']:
                    shift_num = shift['shift_number']
                    self.assignments[day_key][service_id][shift_num] = {}
                    
                    for vehicle_idx in range(service['vehicles']['quantity']):
                        self.assignments[day_key][service_id][shift_num][vehicle_idx] = {}
                        
                        for driver_idx, driver in enumerate(self.drivers):
                            var = self.model.NewBoolVar(
                                f"x_{day_key}_{service_id}_s{shift_num}_v{vehicle_idx}_d{driver_idx}"
                            )
                            self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx] = var
    
    def _add_service_coverage_constraints(self, days: List[date]):
        """Cada servicio debe estar cubierto"""
        for day in days:
            day_key = day.isoformat()
            
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                service_id = service['id']
                
                for shift in service['shifts']:
                    shift_num = shift['shift_number']
                    
                    for vehicle_idx in range(service['vehicles']['quantity']):
                        if (day_key in self.assignments and 
                            service_id in self.assignments[day_key] and
                            shift_num in self.assignments[day_key][service_id]):
                            
                            # Exactamente un conductor por vehículo
                            self.model.Add(
                                sum(self.assignments[day_key][service_id][shift_num][vehicle_idx][d]
                                    for d in range(len(self.drivers))) == 1
                            )
    
    def _add_no_overlap_constraints(self, days: List[date]):
        """Un conductor no puede estar en dos servicios que se solapen o no tengan suficiente descanso"""
        MIN_REST_HOURS = 5  # Mínimo 5 horas de descanso entre turnos
        
        for day in days:
            day_key = day.isoformat()
            
            for driver_idx in range(len(self.drivers)):
                # Recopilar todos los posibles turnos del día para este conductor
                day_shifts = []
                
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in self.assignments and
                                service_id in self.assignments[day_key] and
                                shift_num in self.assignments[day_key][service_id]):
                                
                                day_shifts.append({
                                    'var': self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx],
                                    'start': shift['start_time'],
                                    'end': shift['end_time'],
                                    'duration': shift['duration_hours']
                                })
                
                # Para cada par de turnos, verificar si se pueden hacer ambos
                for i, shift1 in enumerate(day_shifts):
                    for j, shift2 in enumerate(day_shifts[i+1:], i+1):
                        # Calcular tiempo entre turnos
                        end1_hour = int(shift1['end'].split(':')[0])
                        start2_hour = int(shift2['start'].split(':')[0])
                        end2_hour = int(shift2['end'].split(':')[0])
                        start1_hour = int(shift1['start'].split(':')[0])
                        
                        # Verificar si se solapan o no hay suficiente descanso
                        if start2_hour >= end1_hour:
                            # shift2 empieza después que shift1
                            gap_hours = start2_hour - end1_hour
                        elif start1_hour >= end2_hour:
                            # shift1 empieza después que shift2
                            gap_hours = start1_hour - end2_hour
                        else:
                            # Se solapan
                            gap_hours = 0
                        
                        if gap_hours < MIN_REST_HOURS:
                            # No se pueden hacer ambos turnos
                            self.model.Add(shift1['var'] + shift2['var'] <= 1)
    
    def _add_weekly_hours_constraints(self, days: List[date]):
        """Máximo 44 horas semanales por conductor"""
        weeks = self._group_days_by_week(days)
        
        for week_days in weeks:
            for driver_idx, driver in enumerate(self.drivers):
                week_hours = []
                
                for day in week_days:
                    day_key = day.isoformat()
                    
                    for service in self.services:
                        if day.weekday() not in service['frequency']['days']:
                            continue
                        
                        service_id = service['id']
                        
                        for shift in service['shifts']:
                            shift_num = shift['shift_number']
                            hours = int(shift['duration_hours'] * 10)
                            
                            for vehicle_idx in range(service['vehicles']['quantity']):
                                if (day_key in self.assignments and
                                    service_id in self.assignments[day_key] and
                                    shift_num in self.assignments[day_key][service_id]):
                                    
                                    week_hours.append(
                                        self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx] * hours
                                    )
                
                # Aplicar límite semanal (44 horas = 440 en escala x10)
                if week_hours:
                    self.model.Add(sum(week_hours) <= driver.max_weekly_hours * 10)
    
    def _add_monthly_hours_constraints(self, days: List[date]):
        """Máximo 180 horas mensuales por conductor"""
        for driver_idx, driver in enumerate(self.drivers):
            month_hours = []
            
            for day in days:
                day_key = day.isoformat()
                
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    
                    service_id = service['id']
                    
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        hours = int(shift['duration_hours'] * 10)
                        
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in self.assignments and
                                service_id in self.assignments[day_key] and
                                shift_num in self.assignments[day_key][service_id]):
                                
                                month_hours.append(
                                    self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx] * hours
                                )
            
            # Aplicar límite mensual
            if month_hours:
                self.model.Add(sum(month_hours) <= driver.max_monthly_hours * 10)
    
    def _add_sunday_constraints(self, days: List[date]):
        """Mínimo 2 domingos libres al mes"""
        sundays = [d for d in days if d.weekday() == 6]
        
        if len(sundays) < 2:
            return  # No hay suficientes domingos
        
        for driver_idx in range(len(self.drivers)):
            sundays_worked = []
            
            for sunday in sundays:
                day_key = sunday.isoformat()
                sunday_assignments = []
                
                for service in self.services:
                    if sunday.weekday() not in service['frequency']['days']:
                        continue
                    
                    service_id = service['id']
                    
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in self.assignments and
                                service_id in self.assignments[day_key] and
                                shift_num in self.assignments[day_key][service_id]):
                                
                                sunday_assignments.append(
                                    self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                )
                
                # Si trabajó algún turno ese domingo
                if sunday_assignments:
                    worked = self.model.NewBoolVar(f"sunday_worked_{driver_idx}_{day_key}")
                    self.model.AddMaxEquality(worked, sunday_assignments)
                    sundays_worked.append(worked)
            
            # Máximo trabajar (total_domingos - 2) domingos
            if sundays_worked:
                max_sundays = max(0, len(sundays) - 2)
                self.model.Add(sum(sundays_worked) <= max_sundays)
    
    def _add_rest_day_constraints(self, days: List[date]):
        """Al menos 1 día de descanso por semana"""
        weeks = self._group_days_by_week(days)
        
        for week_days in weeks:
            for driver_idx in range(len(self.drivers)):
                days_worked = []
                
                for day in week_days:
                    day_key = day.isoformat()
                    day_assignments = []
                    
                    for service in self.services:
                        if day.weekday() not in service['frequency']['days']:
                            continue
                        
                        service_id = service['id']
                        
                        for shift in service['shifts']:
                            shift_num = shift['shift_number']
                            
                            for vehicle_idx in range(service['vehicles']['quantity']):
                                if (day_key in self.assignments and
                                    service_id in self.assignments[day_key] and
                                    shift_num in self.assignments[day_key][service_id]):
                                    
                                    day_assignments.append(
                                        self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                    )
                    
                    if day_assignments:
                        worked = self.model.NewBoolVar(f"day_worked_{driver_idx}_{day_key}")
                        self.model.AddMaxEquality(worked, day_assignments)
                        days_worked.append(worked)
                
                # Máximo 6 días trabajados (mínimo 1 de descanso)
                if days_worked:
                    self.model.Add(sum(days_worked) <= 6)
    
    def _set_balanced_objective(self, days: List[date]):
        """Función objetivo que balancea minimización de conductores y maximización de utilización"""
        
        # Componente 1: Minimizar número de conductores usados
        drivers_used = []
        
        # Componente 2: Maximizar utilización (minimizar horas no trabajadas)
        underutilization_penalty = []
        
        for driver_idx, driver in enumerate(self.drivers):
            # Variable: ¿Este conductor fue usado?
            driver_used = self.model.NewBoolVar(f"driver_used_{driver_idx}")
            
            all_assignments = []
            total_hours = []
            
            for day in days:
                day_key = day.isoformat()
                
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    
                    service_id = service['id']
                    
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        hours = int(shift['duration_hours'] * 10)
                        
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in self.assignments and
                                service_id in self.assignments[day_key] and
                                shift_num in self.assignments[day_key][service_id]):
                                
                                var = self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                all_assignments.append(var)
                                total_hours.append(var * hours)
            
            if all_assignments:
                # El conductor fue usado si tiene al menos una asignación
                self.model.AddMaxEquality(driver_used, all_assignments)
                
                # Peso alto para minimizar conductores
                drivers_used.append(driver_used * 100000)
                
                # Penalizar si trabaja menos del 80% de su capacidad
                if total_hours:
                    target_hours = int(driver.max_monthly_hours * 0.8 * 10)  # 80% de capacidad
                    hours_worked = sum(total_hours)
                    
                    # Penalidad = max(0, target - actual)
                    penalty = self.model.NewIntVar(0, target_hours, f"underutil_{driver_idx}")
                    self.model.Add(penalty >= target_hours - hours_worked)
                    self.model.Add(penalty >= 0)
                    
                    # Solo penalizar si el conductor fue usado
                    conditional_penalty = self.model.NewIntVar(0, target_hours, f"cond_penalty_{driver_idx}")
                    # Usar AddMultiplicationEquality para multiplicar variables
                    self.model.AddMultiplicationEquality(conditional_penalty, [penalty, driver_used])
                    
                    underutilization_penalty.append(conditional_penalty)
        
        # Objetivo combinado
        self.model.Minimize(sum(drivers_used) + sum(underutilization_penalty))
    
    def _find_overlapping_shifts(self) -> List[List[Tuple[str, int]]]:
        """Encuentra grupos de turnos que se solapan en tiempo"""
        overlapping_groups = []
        
        all_shifts = []
        for service in self.services:
            for shift in service['shifts']:
                all_shifts.append((service['id'], shift['shift_number'], shift['start_time'], shift['end_time']))
        
        # Agrupar turnos que se solapan
        for i, (sid1, snum1, start1, end1) in enumerate(all_shifts):
            for j, (sid2, snum2, start2, end2) in enumerate(all_shifts[i+1:], i+1):
                # Verificar si se solapan
                if not (end1 <= start2 or end2 <= start1):
                    # Buscar si ya existe un grupo con alguno de estos turnos
                    found_group = None
                    for group in overlapping_groups:
                        if (sid1, snum1) in group or (sid2, snum2) in group:
                            found_group = group
                            break
                    
                    if found_group:
                        found_group.append((sid1, snum1))
                        found_group.append((sid2, snum2))
                    else:
                        overlapping_groups.append([(sid1, snum1), (sid2, snum2)])
        
        # Eliminar duplicados en cada grupo
        for group in overlapping_groups:
            group = list(set(group))
        
        return overlapping_groups
    
    def _group_days_by_week(self, days: List[date]) -> List[List[date]]:
        """Agrupa los días en semanas"""
        weeks = []
        current_week = []
        
        for day in days:
            current_week.append(day)
            
            # Si es domingo o es el último día, cerrar la semana
            if day.weekday() == 6 or day == days[-1]:
                if current_week:
                    weeks.append(current_week)
                    current_week = []
        
        return weeks
    
    def _add_initial_solution_hint(self, days: List[date]):
        """Agrega una solución inicial para acelerar la búsqueda"""
        # Estrategia simple: asignar rotativamente
        driver_idx = 0
        
        for day in days[:7]:  # Solo primera semana como hint
            day_key = day.isoformat()
            
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                service_id = service['id']
                
                for shift in service['shifts']:
                    shift_num = shift['shift_number']
                    
                    for vehicle_idx in range(service['vehicles']['quantity']):
                        if (day_key in self.assignments and
                            service_id in self.assignments[day_key] and
                            shift_num in self.assignments[day_key][service_id]):
                            
                            # Asignar al siguiente conductor disponible
                            var = self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                            self.model.AddHint(var, 1)
                            
                            # Rotar al siguiente conductor
                            driver_idx = (driver_idx + 1) % len(self.drivers)
    
    def _extract_solution(self, days: List[date]) -> Dict[str, Any]:
        """Extrae y formatea la solución"""
        solution = {
            'status': 'success',
            'assignments': [],
            'metrics': {},
            'driver_summary': {},
            'service_coverage': {}
        }
        
        # Extraer asignaciones
        for day in days:
            day_key = day.isoformat()
            
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                service_id = service['id']
                
                for shift in service['shifts']:
                    shift_num = shift['shift_number']
                    
                    for vehicle_idx in range(service['vehicles']['quantity']):
                        if (day_key not in self.assignments or
                            service_id not in self.assignments[day_key] or
                            shift_num not in self.assignments[day_key][service_id]):
                            continue
                        
                        for driver_idx, driver in enumerate(self.drivers):
                            if self.solver.Value(self.assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]):
                                solution['assignments'].append({
                                    'date': day_key,
                                    'service': service['name'],
                                    'service_id': service_id,
                                    'shift': shift_num,
                                    'vehicle': vehicle_idx + 1,
                                    'driver_id': driver.id,
                                    'driver_name': driver.name,
                                    'start_time': shift['start_time'],
                                    'end_time': shift['end_time'],
                                    'duration_hours': shift['duration_hours']
                                })
        
        # Calcular métricas por conductor
        for driver in self.drivers:
            driver_assignments = [a for a in solution['assignments'] if a['driver_id'] == driver.id]
            total_hours = sum(a['duration_hours'] for a in driver_assignments)
            
            # Calcular horas por semana
            weekly_hours = {}
            for assignment in driver_assignments:
                week = datetime.fromisoformat(assignment['date']).isocalendar()[1]
                if week not in weekly_hours:
                    weekly_hours[week] = 0
                weekly_hours[week] += assignment['duration_hours']
            
            max_weekly = max(weekly_hours.values()) if weekly_hours else 0
            
            solution['driver_summary'][driver.id] = {
                'name': driver.name,
                'contract_type': driver.contract_type,
                'total_assignments': len(driver_assignments),
                'total_hours': round(total_hours, 2),
                'max_weekly_hours': round(max_weekly, 2),
                'utilization': round(total_hours / driver.max_monthly_hours * 100, 1) if driver.max_monthly_hours > 0 else 0,
                'sundays_worked': len([a for a in driver_assignments if 
                                      datetime.fromisoformat(a['date']).weekday() == 6]),
                'compliant': total_hours <= driver.max_monthly_hours and max_weekly <= driver.max_weekly_hours
            }
        
        # Métricas generales
        drivers_used = len([d for d in solution['driver_summary'].values() if d['total_assignments'] > 0])
        total_hours = sum(d['total_hours'] for d in solution['driver_summary'].values())
        avg_utilization = np.mean([d['utilization'] for d in solution['driver_summary'].values() if d['total_assignments'] > 0])
        
        solution['metrics'] = {
            'drivers_used': drivers_used,
            'total_hours': round(total_hours, 2),
            'avg_hours_per_driver': round(total_hours / drivers_used, 2) if drivers_used > 0 else 0,
            'avg_utilization': round(avg_utilization, 1),
            'compliance_rate': len([d for d in solution['driver_summary'].values() if d['compliant']]) / len(self.drivers) * 100
        }
        
        print(f"\n✓ Solución extraída:")
        print(f"  - Conductores utilizados: {drivers_used} de {len(self.drivers)}")
        print(f"  - Utilización promedio: {avg_utilization:.1f}%")
        print(f"  - Total asignaciones: {len(solution['assignments'])}")
        
        return solution
    
    def _get_failure_reason(self, status) -> str:
        """Diagnóstico de por qué falló la optimización"""
        if status == cp_model.INFEASIBLE:
            return "El problema no tiene solución factible con las restricciones actuales"
        elif status == cp_model.MODEL_INVALID:
            return "El modelo tiene errores en su formulación"
        elif status == cp_model.UNKNOWN:
            return "No se pudo determinar si existe solución en el tiempo límite"
        else:
            return f"Estado desconocido: {status}"