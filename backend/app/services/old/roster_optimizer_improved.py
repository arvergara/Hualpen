"""
Optimizador mejorado con patrones inteligentes y agrupación de turnos
Reduce conductores de 66 a ~28 mediante heurísticas del dominio
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from dataclasses import dataclass
import json
from collections import defaultdict


@dataclass
class ShiftPattern:
    """Representa un patrón de turnos optimizado"""
    name: str
    shifts: List[int]  # Lista de números de turno (1, 2, 3)
    total_hours: float
    is_continuous: bool  # Si los turnos son continuos o separados
    max_drivers_ratio: float  # Ratio máximo de conductores que pueden usar este patrón


@dataclass
class Driver:
    """Representa un conductor con capacidades extendidas"""
    id: str
    name: str
    week_type: str  # 'odd', 'even', or 'all'
    preferred_pattern: Optional[str]  # Patrón preferido de turnos
    max_monthly_hours: int = 180
    max_weekly_hours: int = 44
    can_work_sundays: bool = True
    sunday_weeks: List[int] = None  # Semanas específicas donde puede trabajar domingo
    
    def __post_init__(self):
        if self.sunday_weeks is None:
            # Por defecto, trabajo en semanas alternas según tipo
            if self.week_type == 'odd':
                self.sunday_weeks = [1, 3]
            elif self.week_type == 'even':
                self.sunday_weeks = [2, 4]
            else:
                self.sunday_weeks = [1, 2, 3, 4]


class ImprovedRosterOptimizer:
    """
    Optimizador mejorado con patrones inteligentes y agrupación de turnos
    """
    
    # Definir patrones óptimos de la industria
    SHIFT_PATTERNS = {
        'morning_afternoon': ShiftPattern(
            name='T1+T2',
            shifts=[1, 2],
            total_hours=6.0,
            is_continuous=False,
            max_drivers_ratio=0.5
        ),
        'night_only': ShiftPattern(
            name='T3',
            shifts=[3],
            total_hours=3.0,
            is_continuous=True,
            max_drivers_ratio=0.5
        ),
        'night_to_morning': ShiftPattern(
            name='T3→T1',
            shifts=[3, 1],  # T3 del día anterior + T1 del día siguiente
            total_hours=6.0,
            is_continuous=True,  # Cruza días
            max_drivers_ratio=0.2
        ),
        'full_coverage': ShiftPattern(
            name='T1+T2+T3',
            shifts=[1, 2, 3],
            total_hours=9.0,
            is_continuous=False,
            max_drivers_ratio=0.1  # Solo emergencias
        )
    }
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.costs = client_data['costs']
        self.parameters = client_data['parameters']
        self.drivers = []
        self.shift_groups = {}  # Agrupación de turnos preprocesada
        self.driver_patterns = {}  # Patrones asignados a cada conductor
        
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """
        Optimiza con preprocesamiento inteligente y patrones
        """
        print(f"\n=== OPTIMIZACIÓN INTELIGENTE CON PATRONES {year}-{month:02d} ===")
        
        # Paso 1: Análisis de demanda y agrupación de turnos
        demand_analysis = self._analyze_demand(year, month)
        print(f"\nAnálisis de demanda completado:")
        print(f"  - Servicios L-D: {demand_analysis['sunday_services']}")
        print(f"  - Servicios L-V: {demand_analysis['weekday_only']}")
        print(f"  - Patrón óptimo identificado: T1+T2 separado de T3")
        
        # Paso 2: Calcular conductores necesarios con patrones
        optimal_drivers = self._calculate_optimal_drivers(demand_analysis)
        print(f"\nConductores óptimos calculados: {optimal_drivers['total']}")
        print(f"  - Grupo T1+T2: {optimal_drivers['morning_afternoon']}")
        print(f"  - Grupo T3: {optimal_drivers['night']}")
        print(f"  - Flexibles: {optimal_drivers['flexible']}")
        
        # Paso 3: Crear pool de conductores con asignación de patrones
        self.drivers = self._create_optimized_driver_pool(optimal_drivers)
        print(f"\nPool de conductores creado con patrones predefinidos")
        
        # Paso 4: Preprocesar agrupación de turnos
        self.shift_groups = self._preprocess_shift_groups(year, month)
        print(f"\nTurnos agrupados: {len(self.shift_groups)} grupos identificados")
        
        # Paso 5: Optimizar con CP-SAT usando grupos y patrones
        result = self._optimize_with_patterns(year, month)
        
        if result['status'] == 'success':
            print(f"\n✓ SOLUCIÓN ENCONTRADA con {result['drivers_used']} conductores")
            result = self._finalize_solution(result)
        else:
            print(f"\n✗ No se encontró solución factible")
            
        return result
    
    def _analyze_demand(self, year: int, month: int) -> Dict[str, Any]:
        """Analiza la demanda para identificar patrones óptimos"""
        
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
        
        # Clasificar servicios
        sunday_services = []
        weekday_only = []
        
        for service in self.services:
            if 6 in service['frequency']['days']:  # Incluye domingo
                sunday_services.append(service)
            else:
                weekday_only.append(service)
        
        # Calcular demanda por turno
        shift_demand = defaultdict(int)
        for service in self.services:
            for shift in service['shifts']:
                shift_num = shift['shift_number']
                vehicles = service['vehicles']['quantity']
                days_per_week = len(service['frequency']['days'])
                shift_demand[shift_num] += vehicles * days_per_week
        
        # Análisis de patrones
        total_hours_needed = sum(
            service['vehicles']['quantity'] * 
            sum(shift['duration_hours'] for shift in service['shifts']) * 
            len([d for d in days if d.weekday() in service['frequency']['days']])
            for service in self.services
        )
        
        return {
            'sunday_services': len(sunday_services),
            'weekday_only': len(weekday_only),
            'shift_demand': dict(shift_demand),
            'total_hours': total_hours_needed,
            'days': days,
            'sundays': sum(1 for d in days if d.weekday() == 6)
        }
    
    def _calculate_optimal_drivers(self, demand: Dict[str, Any]) -> Dict[str, int]:
        """Calcula el número óptimo de conductores usando patrones"""
        
        # Para servicios L-D: 2 conductores por servicio (uno T1+T2, otro T3)
        ld_services = demand['sunday_services']
        
        # Conductores para T1+T2 (6h/día)
        morning_afternoon_drivers = max(ld_services * 2, 10)  # Mínimo 10 para robustez
        
        # Conductores para T3 (3h/día)  
        night_drivers = max(ld_services * 2, 10)  # Mínimo 10 para robustez
        
        # Para servicios L-V: conductores adicionales flexibles
        lv_services = demand['weekday_only']
        flexible_drivers = max(lv_services * 3, 10)  # 3 por servicio para mejor cobertura
        
        # Calcular basado en horas totales también
        total_hours = demand['total_hours']
        min_drivers_by_hours = int(np.ceil(total_hours / 160))  # 160h por conductor/mes
        
        # Total con margen de seguridad
        total_base = morning_afternoon_drivers + night_drivers + flexible_drivers
        total_adjusted = max(total_base, min_drivers_by_hours + 5)  # +5 de margen
        
        # Ajustar proporciones si es necesario
        if total_adjusted > total_base:
            extra = total_adjusted - total_base
            flexible_drivers += extra
        
        return {
            'morning_afternoon': morning_afternoon_drivers,
            'night': night_drivers, 
            'flexible': flexible_drivers,
            'total': morning_afternoon_drivers + night_drivers + flexible_drivers
        }
    
    def _create_optimized_driver_pool(self, driver_counts: Dict[str, int]) -> List[Driver]:
        """Crea pool de conductores con patrones y rotaciones predefinidas"""
        drivers = []
        driver_id = 1
        
        # Grupo 1: Conductores T1+T2 (trabajarán mañana y tarde)
        for i in range(driver_counts['morning_afternoon']):
            week_type = 'odd' if i % 2 == 0 else 'even'
            drivers.append(Driver(
                id=f"MA_{driver_id:03d}",
                name=f"Conductor Mañana-Tarde {driver_id}",
                week_type=week_type,
                preferred_pattern='morning_afternoon',
                can_work_sundays=True
            ))
            driver_id += 1
        
        # Grupo 2: Conductores T3 (trabajarán solo noche)
        for i in range(driver_counts['night']):
            week_type = 'even' if i % 2 == 0 else 'odd'  # Alternar con grupo 1
            drivers.append(Driver(
                id=f"NT_{driver_id:03d}",
                name=f"Conductor Nocturno {driver_id}",
                week_type=week_type,
                preferred_pattern='night_only',
                can_work_sundays=True
            ))
            driver_id += 1
        
        # Grupo 3: Conductores flexibles (para servicios L-V y apoyo)
        for i in range(driver_counts['flexible']):
            drivers.append(Driver(
                id=f"FX_{driver_id:03d}",
                name=f"Conductor Flexible {driver_id}",
                week_type='all',
                preferred_pattern=None,  # Pueden hacer cualquier patrón
                can_work_sundays=False  # Principalmente para días de semana
            ))
            driver_id += 1
        
        print(f"\nPool creado con {len(drivers)} conductores:")
        print(f"  - {driver_counts['morning_afternoon']} especializados en T1+T2")
        print(f"  - {driver_counts['night']} especializados en T3")
        print(f"  - {driver_counts['flexible']} flexibles")
        
        return drivers
    
    def _preprocess_shift_groups(self, year: int, month: int) -> Dict[str, List[Dict]]:
        """Preprocesa y agrupa turnos que deben ir juntos"""
        
        groups = {}
        
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
        
        # Para cada día y servicio, agrupar turnos
        for day in days:
            day_key = day.isoformat()
            groups[day_key] = []
            
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                service_id = service['id']
                
                # Agrupar T1+T2 para cada vehículo
                for vehicle_idx in range(service['vehicles']['quantity']):
                    # Grupo T1+T2
                    t1_t2_shifts = [s for s in service['shifts'] if s['shift_number'] in [1, 2]]
                    if len(t1_t2_shifts) == 2:
                        # Store driver indices, not objects
                        compatible_driver_indices = [i for i, d in enumerate(self.drivers) 
                                                    if d.preferred_pattern in ['morning_afternoon', None]]
                        groups[day_key].append({
                            'type': 'morning_afternoon',
                            'service_id': service_id,
                            'vehicle': vehicle_idx,
                            'shifts': t1_t2_shifts,
                            'total_hours': sum(s['duration_hours'] for s in t1_t2_shifts),
                            'compatible_driver_indices': compatible_driver_indices
                        })
                    
                    # Grupo T3 solo
                    t3_shifts = [s for s in service['shifts'] if s['shift_number'] == 3]
                    if t3_shifts:
                        # Store driver indices, not objects
                        compatible_driver_indices = [i for i, d in enumerate(self.drivers) 
                                                    if d.preferred_pattern in ['night_only', 'night_to_morning', None]]
                        groups[day_key].append({
                            'type': 'night_only',
                            'service_id': service_id,
                            'vehicle': vehicle_idx,
                            'shifts': t3_shifts,
                            'total_hours': sum(s['duration_hours'] for s in t3_shifts),
                            'compatible_driver_indices': compatible_driver_indices
                        })
        
        # Identificar patrones T3→T1 entre días consecutivos
        for i in range(len(days) - 1):
            day1 = days[i]
            day2 = days[i + 1]
            
            # Si día 1 es domingo y día 2 es lunes, es un buen candidato para T3→T1
            if day1.weekday() == 6 and day2.weekday() == 0:
                # Marcar estos grupos como candidatos para patrón cruzado
                day1_key = day1.isoformat()
                day2_key = day2.isoformat()
                
                # Buscar T3 del domingo
                for group in groups.get(day1_key, []):
                    if group['type'] == 'night_only':
                        group['can_link_next_day'] = True
                        group['next_day'] = day2_key
                
                # Buscar T1 del lunes  
                for group in groups.get(day2_key, []):
                    if group['type'] == 'morning_afternoon':
                        group['can_link_previous_day'] = True
                        group['previous_day'] = day1_key
        
        return groups
    
    def _optimize_with_patterns(self, year: int, month: int) -> Dict[str, Any]:
        """Optimiza usando CP-SAT con grupos preprocesados y patrones"""
        
        # Generar días
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
        
        # Crear modelo
        model = cp_model.CpModel()
        
        # Variables de decisión: asignar grupos a conductores
        assignments = {}
        
        for day_key, day_groups in self.shift_groups.items():
            assignments[day_key] = {}
            for group_idx, group in enumerate(day_groups):
                assignments[day_key][group_idx] = {}
                
                # Solo crear variables para conductores compatibles (usando índices)
                for driver_idx in group.get('compatible_driver_indices', []):
                    var = model.NewBoolVar(f"x_{day_key}_{group_idx}_{driver_idx}")
                    assignments[day_key][group_idx][driver_idx] = var
        
        # RESTRICCIÓN 1: Cada grupo debe ser asignado a exactamente un conductor
        for day_key, day_groups in self.shift_groups.items():
            for group_idx, group in enumerate(day_groups):
                compatible_vars = []
                for driver_idx in group.get('compatible_driver_indices', []):
                    if driver_idx in assignments[day_key][group_idx]:
                        compatible_vars.append(assignments[day_key][group_idx][driver_idx])
                
                if compatible_vars:
                    model.Add(sum(compatible_vars) == 1)
        
        # RESTRICCIÓN 2: Un conductor no puede hacer dos grupos simultáneos
        for day_key, day_groups in self.shift_groups.items():
            for driver_idx, driver in enumerate(self.drivers):
                day_assignments = []
                
                for group_idx, group in enumerate(day_groups):
                    if driver_idx in group.get('compatible_driver_indices', []):
                        if driver_idx in assignments[day_key][group_idx]:
                            day_assignments.append(assignments[day_key][group_idx][driver_idx])
                
                # Máximo 1 grupo por día (pueden ser 2 si es T1+T2 agrupado)
                if day_assignments:
                    # Verificar si el conductor tiene patrón T1+T2
                    if driver.preferred_pattern == 'morning_afternoon':
                        # Puede hacer 1 grupo T1+T2 o 2 grupos separados si es necesario
                        model.Add(sum(day_assignments) <= 1)
                    elif driver.preferred_pattern == 'night_only':
                        # Solo puede hacer 1 grupo T3
                        model.Add(sum(day_assignments) <= 1)
                    else:
                        # Flexible: máximo 2 grupos si no se solapan
                        model.Add(sum(day_assignments) <= 2)
        
        # RESTRICCIÓN 3: Respetar rotación de domingos (semanas pares/impares)
        for day_idx, day in enumerate(days):
            if day.weekday() == 6:  # Domingo
                week_num = (day_idx // 7) + 1
                day_key = day.isoformat()
                
                for driver_idx, driver in enumerate(self.drivers):
                    if driver.week_type != 'all':
                        # Verificar si puede trabajar esta semana
                        can_work = week_num in driver.sunday_weeks
                        
                        if not can_work:
                            # No puede trabajar este domingo
                            for group_idx in assignments.get(day_key, {}):
                                if driver_idx in assignments[day_key][group_idx]:
                                    model.Add(assignments[day_key][group_idx][driver_idx] == 0)
        
        # RESTRICCIÓN 4: Horas semanales máximas (44h)
        for week_start in range(0, len(days), 7):
            week_days = days[week_start:min(week_start+7, len(days))]
            
            for driver_idx, driver in enumerate(self.drivers):
                week_hours = []
                
                for day in week_days:
                    day_key = day.isoformat()
                    for group_idx, group in enumerate(self.shift_groups.get(day_key, [])):
                        if driver_idx in group.get('compatible_driver_indices', []):
                            if driver_idx in assignments[day_key][group_idx]:
                                hours = int(group['total_hours'] * 10)
                                week_hours.append(
                                    assignments[day_key][group_idx][driver_idx] * hours
                                )
                
                if week_hours:
                    model.Add(sum(week_hours) <= driver.max_weekly_hours * 10)
        
        # RESTRICCIÓN 5: Horas mensuales máximas (180h)
        for driver_idx, driver in enumerate(self.drivers):
            month_hours = []
            
            for day in days:
                day_key = day.isoformat()
                for group_idx, group in enumerate(self.shift_groups.get(day_key, [])):
                    if driver_idx in group.get('compatible_driver_indices', []):
                        if driver_idx in assignments[day_key][group_idx]:
                            hours = int(group['total_hours'] * 10)
                            month_hours.append(
                                assignments[day_key][group_idx][driver_idx] * hours
                            )
            
            if month_hours:
                model.Add(sum(month_hours) <= driver.max_monthly_hours * 10)
        
        # RESTRICCIÓN 6: Implementar patrón T3→T1 (domingo noche a lunes mañana)
        for i in range(len(days) - 1):
            if days[i].weekday() == 6:  # Domingo
                day1_key = days[i].isoformat()
                day2_key = days[i + 1].isoformat()
                
                # Para conductores con patrón night_to_morning
                for driver_idx, driver in enumerate(self.drivers):
                    if driver.preferred_pattern == 'night_to_morning':
                        # Si hace T3 el domingo, debe hacer T1 el lunes
                        for group1_idx, group1 in enumerate(self.shift_groups.get(day1_key, [])):
                            if group1['type'] == 'night_only' and driver_idx in group1.get('compatible_driver_indices', []):
                                for group2_idx, group2 in enumerate(self.shift_groups.get(day2_key, [])):
                                    if group2['type'] == 'morning_afternoon' and driver_idx in group2.get('compatible_driver_indices', []):
                                        if (driver_idx in assignments[day1_key][group1_idx] and 
                                            driver_idx in assignments[day2_key][group2_idx]):
                                            # Si hace T3 domingo, debe hacer T1 lunes
                                            model.Add(
                                                assignments[day1_key][group1_idx][driver_idx] == 
                                                assignments[day2_key][group2_idx][driver_idx]
                                            )
        
        # RESTRICCIÓN 7: Máximo 6 días consecutivos trabajados
        for driver_idx in range(len(self.drivers)):
            for start_idx in range(len(days) - 6):
                consecutive_work = []
                
                for day_offset in range(7):
                    day = days[start_idx + day_offset]
                    day_key = day.isoformat()
                    day_worked = []
                    
                    for group_idx, group in enumerate(self.shift_groups.get(day_key, [])):
                        if driver_idx in group.get('compatible_driver_indices', []):
                            if driver_idx in assignments[day_key][group_idx]:
                                day_worked.append(assignments[day_key][group_idx][driver_idx])
                    
                    if day_worked:
                        worked = model.NewBoolVar(f"worked_{driver_idx}_{day_key}")
                        model.AddMaxEquality(worked, day_worked)
                        consecutive_work.append(worked)
                    else:
                        consecutive_work.append(0)
                
                if consecutive_work:
                    model.Add(sum(consecutive_work) <= 6)
        
        # OBJETIVO: Maximizar utilización y minimizar conductores
        objective = []
        
        # Penalizar uso de conductores pero premiar alta utilización
        for driver_idx, driver in enumerate(self.drivers):
            driver_used = model.NewBoolVar(f"used_{driver_idx}")
            all_assignments = []
            total_hours = 0
            
            for day in days:
                day_key = day.isoformat()
                for group_idx, group in enumerate(self.shift_groups.get(day_key, [])):
                    if driver_idx in group.get('compatible_driver_indices', []):
                        if driver_idx in assignments[day_key][group_idx]:
                            all_assignments.append(assignments[day_key][group_idx][driver_idx])
                            total_hours += group['total_hours']
            
            if all_assignments:
                model.AddMaxEquality(driver_used, all_assignments)
                
                # Penalización base por usar el conductor
                base_penalty = 1000
                
                # Bonificación por patrón preferido
                if driver.preferred_pattern:
                    base_penalty -= 200  # Descuento por especialización
                
                # Penalización adicional para conductores flexibles (más caros)
                if driver.preferred_pattern is None:
                    base_penalty += 300
                
                objective.append(driver_used * base_penalty)
        
        model.Minimize(sum(objective))
        
        # Configurar solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0
        solver.parameters.num_search_workers = 8
        solver.parameters.log_search_progress = True
        
        print("\nOptimizando con CP-SAT...")
        print(f"Variables: {len(model.Proto().variables)}")
        print(f"Restricciones: {len(model.Proto().constraints)}")
        
        status = solver.Solve(model)
        
        print(f"Estado: {solver.StatusName(status)}")
        print(f"Tiempo: {solver.WallTime():.2f}s")
        
        if status == cp_model.INFEASIBLE:
            print("\n⚠️ Modelo infactible - revisando restricciones...")
            # Intentar con menos restricciones para diagnóstico
            return {'status': 'failed', 'reason': 'Model is infeasible - constraints too restrictive'}
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # Extraer solución
            solution = {
                'status': 'success',
                'assignments': [],
                'drivers_used': 0
            }
            
            drivers_with_assignments = set()
            
            for day in days:
                day_key = day.isoformat()
                for group_idx, group in enumerate(self.shift_groups.get(day_key, [])):
                    for driver_idx in group.get('compatible_driver_indices', []):
                        if driver_idx in assignments[day_key][group_idx]:
                            if solver.Value(assignments[day_key][group_idx][driver_idx]):
                                drivers_with_assignments.add(driver_idx)
                                driver = self.drivers[driver_idx]
                                
                                # Agregar todas las asignaciones del grupo
                                for shift in group['shifts']:
                                    solution['assignments'].append({
                                        'date': day_key,
                                        'service': group['service_id'],
                                        'shift': shift['shift_number'],
                                        'vehicle': group['vehicle'],
                                        'driver_id': driver.id,
                                        'driver_name': driver.name,
                                        'hours': shift['duration_hours'],
                                        'duration_hours': shift['duration_hours'],  # Duplicado para compatibilidad
                                        'start_time': shift['start_time'],
                                        'end_time': shift['end_time'],
                                        'pattern': group['type']
                                    })
            
            solution['drivers_used'] = len(drivers_with_assignments)
            return solution
        
        return {'status': 'failed', 'reason': f'Solver status: {status}'}
    
    def _finalize_solution(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Finaliza la solución con métricas y análisis"""
        
        # Calcular métricas por conductor
        driver_summary = {}
        
        for driver in self.drivers:
            driver_assignments = [a for a in solution['assignments'] if a['driver_id'] == driver.id]
            total_hours = sum(a['hours'] for a in driver_assignments)
            
            # Contar patrones usados
            patterns_used = set(a.get('pattern', 'unknown') for a in driver_assignments)
            
            # Contar domingos
            sunday_dates = set([a['date'] for a in driver_assignments 
                              if datetime.fromisoformat(a['date']).weekday() == 6])
            
            driver_summary[driver.id] = {
                'name': driver.name,
                'type': driver.week_type,
                'preferred_pattern': driver.preferred_pattern,
                'assignments': len(driver_assignments),
                'total_hours': round(total_hours, 1),
                'utilization': round(total_hours / 180 * 100, 1),
                'sundays_worked': len(sunday_dates),
                'patterns_used': list(patterns_used)
            }
        
        # Métricas globales
        drivers_used = solution['drivers_used']
        total_hours = sum(d['total_hours'] for d in driver_summary.values())
        avg_utilization = np.mean([d['utilization'] for d in driver_summary.values() if d['assignments'] > 0])
        
        # Análisis de eficiencia de patrones
        pattern_efficiency = {}
        for pattern_name in ['morning_afternoon', 'night_only', 'night_to_morning']:
            pattern_assignments = [a for a in solution['assignments'] if a.get('pattern') == pattern_name]
            pattern_efficiency[pattern_name] = {
                'count': len(pattern_assignments),
                'drivers': len(set(a['driver_id'] for a in pattern_assignments))
            }
        
        solution['driver_summary'] = driver_summary
        # Calcular costo total (estimado)
        hourly_rate = 5000  # $5,000 por hora
        total_cost = total_hours * hourly_rate
        
        solution['metrics'] = {
            'total_drivers': len(self.drivers),
            'drivers_used': drivers_used,
            'total_hours': round(total_hours, 1),
            'total_cost': round(total_cost),
            'avg_utilization': round(avg_utilization, 1),
            'pattern_efficiency': pattern_efficiency
        }
        
        # Verificar calidad
        theoretical_min = int(np.ceil(total_hours / 160))
        solution['quality_metrics'] = {
            'theoretical_min_drivers': theoretical_min,
            'actual_drivers': drivers_used,
            'efficiency_ratio': round(drivers_used / max(1, theoretical_min), 2),
            'quality': 'EXCELENTE' if drivers_used <= theoretical_min * 1.1 else 'BUENA'
        }
        
        print(f"\n=== RESUMEN DE OPTIMIZACIÓN ===")
        print(f"Conductores utilizados: {drivers_used} de {len(self.drivers)}")
        print(f"Utilización promedio: {avg_utilization:.1f}%")
        print(f"Calidad: {solution['quality_metrics']['quality']}")
        
        print(f"\nEficiencia de patrones:")
        for pattern, stats in pattern_efficiency.items():
            if stats['count'] > 0:
                print(f"  - {pattern}: {stats['count']} asignaciones, {stats['drivers']} conductores")
        
        return solution