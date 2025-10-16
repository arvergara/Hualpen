"""
Optimizador adaptativo que incrementa conductores hasta encontrar solución factible
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from dataclasses import dataclass
import json


class SolutionPrinter(cp_model.CpSolverSolutionCallback):
    """Callback para monitorear progreso de la optimización"""
    
    def __init__(self, num_drivers):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.num_drivers = num_drivers
        self.solution_count = 0
        self.start_time = datetime.now()
        self.best_objective = float('inf')
    
    def on_solution_callback(self):
        self.solution_count += 1
        elapsed = (datetime.now() - self.start_time).total_seconds()
        current_objective = self.ObjectiveValue()
        
        if current_objective < self.best_objective:
            self.best_objective = current_objective
            print(f"    → Mejor solución {self.solution_count} ({elapsed:.1f}s) - Objetivo: {current_objective}")


@dataclass
class Driver:
    """Representa un conductor"""
    id: str
    name: str
    contract_type: str  # 'full_time', 'part_time_20h', 'part_time_30h'
    base_salary: float
    home_location: Tuple[float, float] = (-36.8201, -73.0444)
    max_monthly_hours: int = 180
    max_weekly_hours: int = 44
    current_month_hours: float = 0
    sundays_worked: int = 0
    last_shift_end: datetime = None
    skills: List[str] = None
    
    def __post_init__(self):
        if self.skills is None:
            self.skills = ['bus', 'minibus']


class AdaptiveRosterOptimizer:
    """
    Optimizador adaptativo que incrementa automáticamente el número de conductores
    hasta encontrar una solución factible
    """
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.costs = client_data['costs']
        self.parameters = client_data['parameters']
        self.drivers = []
        self.solution = None
        
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """
        Optimiza iterativamente agregando conductores hasta encontrar solución
        """
        print(f"\n=== OPTIMIZACIÓN ADAPTATIVA {year}-{month:02d} ===")
        
        # Calcular pool inicial mínimo
        initial_drivers = self._calculate_minimum_drivers()
        
        # Empezar con el mínimo
        current_drivers = initial_drivers
        max_attempts = 60  # Aumentado a 60 intentos para encontrar solución
        solution_found = False
        
        for attempt in range(1, max_attempts + 1):
            print(f"\nIntento {attempt}: Probando con {current_drivers} conductores...")
            
            # Crear pool de conductores
            self.drivers = self._create_driver_pool(current_drivers)
            
            # Intentar optimizar
            result = self._try_optimize(year, month)
            
            if result['status'] == 'success':
                print(f"✓ SOLUCIÓN ENCONTRADA con {current_drivers} conductores")
                self.solution = result
                solution_found = True
                break
            else:
                print(f"✗ No factible con {current_drivers} conductores")
                
                # Mostrar diagnóstico de restricciones violadas si está disponible
                if 'constraint_violations' in result:
                    print("\n  📊 DIAGNÓSTICO DE RESTRICCIONES:")
                    for violation in result['constraint_violations']:
                        print(f"    {violation}")
                
                # Solo agregar conductores full-time
                print("\n  → Agregando 1 conductor Full-Time")
                current_drivers['full_time'] += 1
        
        if not solution_found:
            return {
                'status': 'failed',
                'message': f'No se encontró solución después de {max_attempts} intentos',
                'last_attempt': current_drivers
            }
        
        # Optimización exitosa - calcular métricas finales
        solution_with_metrics = self._finalize_solution(self.solution)
        
        # Verificar calidad de la solución
        solution_with_quality = self._verify_solution_quality(solution_with_metrics)
        
        return solution_with_quality
    
    def _calculate_minimum_drivers(self) -> Dict[str, int]:
        """Calcula el número mínimo inicial de conductores"""
        
        # Calcular horas totales necesarias
        total_hours_month = sum(
            service['vehicles']['quantity'] * 
            sum(shift['duration_hours'] for shift in service['shifts']) * 
            len(service['frequency']['days']) * 4.3
            for service in self.services
        )
        
        # Calcular turnos simultáneos máximos
        morning_shifts = 0
        afternoon_shifts = 0
        evening_shifts = 0
        
        for service in self.services:
            for shift in service['shifts']:
                start_hour = int(shift['start_time'].split(':')[0])
                vehicles = service['vehicles']['quantity']
                
                if start_hour < 12:
                    morning_shifts += vehicles
                elif start_hour < 17:
                    afternoon_shifts += vehicles
                else:
                    evening_shifts += vehicles
        
        max_simultaneous = max(morning_shifts, afternoon_shifts, evening_shifts)
        
        print(f"Análisis inicial:")
        print(f"  - Horas totales mes: {total_hours_month:.1f}")
        print(f"  - Turnos simultáneos máx: {max_simultaneous}")
        print(f"  - Turnos mañana/tarde/noche: {morning_shifts}/{afternoon_shifts}/{evening_shifts}")
        
        # Calcular mínimo inicial conservador
        min_by_hours = int(total_hours_month / 160)  # 160h efectivas por conductor
        min_by_coverage = max_simultaneous
        
        # Considerar restricción de domingos y división T1/T3
        # Con restricción de no T1+T3, necesitamos 2 grupos
        # Con 50% disponibilidad en domingos, necesitamos el doble para domingos
        min_by_sunday = max_simultaneous * 2  # Doble por restricción de domingos
        
        base_needed = max(min_by_hours, min_by_coverage, min_by_sunday)
        
        # Agregar margen del 10% para factibilidad
        base_needed = int(base_needed * 1.1)
        
        # Solo usar conductores full-time
        return {
            'full_time': base_needed,
            'part_time_30h': 0,
            'part_time_20h': 0
        }
    
    def _create_driver_pool(self, driver_counts: Dict[str, int]) -> List[Driver]:
        """Crea el pool de conductores con las cantidades especificadas"""
        drivers = []
        driver_id = 1
        
        # Crear conductores genéricos (se categorizarán después según horas trabajadas)
        total_drivers = driver_counts.get('full_time', 0)  # Ahora son solo conductores genéricos
        
        for i in range(total_drivers):
            drivers.append(Driver(
                id=f"D_{driver_id:03d}",
                name=f"Conductor {driver_id}",
                contract_type='undefined',  # Se definirá después
                base_salary=0,  # Se calculará después según horas trabajadas
                max_monthly_hours=180,
                max_weekly_hours=44
            ))
            driver_id += 1
        
        total_capacity = sum(d.max_monthly_hours for d in drivers)
        print(f"  Pool: {len(drivers)} conductores, capacidad {total_capacity}h/mes")
        
        return drivers
    
    def _try_optimize(self, year: int, month: int) -> Dict[str, Any]:
        """Intenta optimizar con el pool actual de conductores"""
        
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
        
        # Crear modelo
        model = cp_model.CpModel()
        solver = cp_model.CpSolver()
        
        # Variables de decisión
        assignments = {}
        for day in days:
            day_key = day.isoformat()
            assignments[day_key] = {}
            
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                service_id = service['id']
                assignments[day_key][service_id] = {}
                
                for shift in service['shifts']:
                    shift_num = shift['shift_number']
                    assignments[day_key][service_id][shift_num] = {}
                    
                    for vehicle_idx in range(service['vehicles']['quantity']):
                        assignments[day_key][service_id][shift_num][vehicle_idx] = {}
                        
                        for driver_idx in range(len(self.drivers)):
                            var = model.NewBoolVar(
                                f"x_{day_key}_{service_id}_{shift_num}_{vehicle_idx}_{driver_idx}"
                            )
                            assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx] = var
        
        # RESTRICCIÓN 1: Cobertura de servicios
        for day in days:
            day_key = day.isoformat()
            for service in self.services:
                if day.weekday() not in service['frequency']['days']:
                    continue
                service_id = service['id']
                for shift in service['shifts']:
                    shift_num = shift['shift_number']
                    for vehicle_idx in range(service['vehicles']['quantity']):
                        if (day_key in assignments and 
                            service_id in assignments[day_key] and
                            shift_num in assignments[day_key][service_id]):
                            # Cada vehículo necesita exactamente un conductor
                            model.Add(
                                sum(assignments[day_key][service_id][shift_num][vehicle_idx][d]
                                    for d in range(len(self.drivers))) == 1
                            )
        
        # RESTRICCIÓN 2: No solapamiento con descanso mínimo
        # Un conductor no puede hacer dos servicios al mismo tiempo o sin descanso suficiente
        MIN_REST_HOURS = 5
        
        # Primero, verificar turnos dentro del mismo día
        for day in days:
            day_key = day.isoformat()
            for driver_idx in range(len(self.drivers)):
                day_shifts = []
                
                # Recolectar todos los posibles turnos del día para este conductor
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in assignments and
                                service_id in assignments[day_key] and
                                shift_num in assignments[day_key][service_id]):
                                day_shifts.append({
                                    'var': assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx],
                                    'start': shift['start_time'],
                                    'end': shift['end_time'],
                                    'service': service_id,
                                    'shift_num': shift_num
                                })
                
                # Verificar todos los pares de turnos del mismo día
                for i, shift1 in enumerate(day_shifts):
                    for shift2 in day_shifts[i+1:]:
                        # Convertir tiempos a minutos para comparación más precisa
                        def time_to_minutes(time_str):
                            h, m = map(int, time_str.split(':'))
                            # Manejar medianoche (00:00 = 24:00 del día anterior)
                            if h == 0:
                                h = 24
                            return h * 60 + m
                        
                        start1 = time_to_minutes(shift1['start'])
                        end1 = time_to_minutes(shift1['end'])
                        start2 = time_to_minutes(shift2['start'])
                        end2 = time_to_minutes(shift2['end'])
                        
                        # Ajustar si cruza medianoche
                        if end1 < start1:  # Turno 1 cruza medianoche
                            end1 += 24 * 60
                        if end2 < start2:  # Turno 2 cruza medianoche
                            end2 += 24 * 60
                        
                        # Verificar solapamiento o falta de descanso
                        # Caso 1: Turnos se solapan (mismo horario o se traslapan)
                        if (start1 <= start2 < end1) or (start2 <= start1 < end2):
                            # No pueden hacer ambos turnos
                            model.Add(shift1['var'] + shift2['var'] <= 1)
                        # Caso 2: Turnos no se solapan pero no hay suficiente descanso
                        elif start2 >= end1:  # Turno 2 después de turno 1
                            gap_minutes = start2 - end1
                            if gap_minutes < MIN_REST_HOURS * 60:
                                model.Add(shift1['var'] + shift2['var'] <= 1)
                        elif start1 >= end2:  # Turno 1 después de turno 2
                            gap_minutes = start1 - end2
                            if gap_minutes < MIN_REST_HOURS * 60:
                                model.Add(shift1['var'] + shift2['var'] <= 1)
        
        # Verificar descanso mínimo entre días consecutivos (especialmente Turno 3 → Turno 1)
        for day_idx in range(len(days) - 1):
            day1 = days[day_idx]
            day2 = days[day_idx + 1]
            day1_key = day1.isoformat()
            day2_key = day2.isoformat()
            
            for driver_idx in range(len(self.drivers)):
                # Recolectar turnos nocturnos del día 1 (que terminan tarde)
                night_shifts_day1 = []
                for service in self.services:
                    if day1.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        # Solo turnos que terminan tarde (después de las 20:00 o en 00:00)
                        if shift['end_time'] in ['00:00', '23:00', '22:00', '21:00'] or \
                           (shift['shift_type'] == 'night' if 'shift_type' in shift else False):
                            shift_num = shift['shift_number']
                            for vehicle_idx in range(service['vehicles']['quantity']):
                                if (day1_key in assignments and
                                    service_id in assignments[day1_key] and
                                    shift_num in assignments[day1_key][service_id]):
                                    night_shifts_day1.append({
                                        'var': assignments[day1_key][service_id][shift_num][vehicle_idx][driver_idx],
                                        'end': shift['end_time']
                                    })
                
                # Recolectar turnos matutinos del día 2 (que empiezan temprano)
                morning_shifts_day2 = []
                for service in self.services:
                    if day2.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        # Solo turnos que empiezan temprano (antes de las 10:00)
                        start_hour = int(shift['start_time'].split(':')[0])
                        if start_hour < 10:
                            shift_num = shift['shift_number']
                            for vehicle_idx in range(service['vehicles']['quantity']):
                                if (day2_key in assignments and
                                    service_id in assignments[day2_key] and
                                    shift_num in assignments[day2_key][service_id]):
                                    morning_shifts_day2.append({
                                        'var': assignments[day2_key][service_id][shift_num][vehicle_idx][driver_idx],
                                        'start': shift['start_time']
                                    })
                
                # Verificar descanso entre turno nocturno y turno matutino
                for night_shift in night_shifts_day1:
                    for morning_shift in morning_shifts_day2:
                        # Calcular gap entre fin del turno nocturno y inicio del turno matutino
                        # Por ejemplo: Turno 3 termina a las 00:00, Turno 1 empieza a las 05:00 = 5 horas
                        end_hour = 24 if night_shift['end'] == '00:00' else int(night_shift['end'].split(':')[0])
                        start_hour = int(morning_shift['start'].split(':')[0])
                        
                        # El gap es desde medianoche (o fin del turno) hasta el inicio del turno matutino
                        if night_shift['end'] == '00:00':
                            gap_hours = start_hour  # De 00:00 a inicio
                        else:
                            gap_hours = (24 - end_hour) + start_hour  # De fin a medianoche + medianoche a inicio
                        
                        if gap_hours < MIN_REST_HOURS:
                            model.Add(night_shift['var'] + morning_shift['var'] <= 1)
        
        # RESTRICCIÓN 2.5: Restricción explícita de no simultaneidad para mismo horario
        # Para cada conductor, día y horario único, máximo 1 asignación
        for day in days:
            day_key = day.isoformat()
            for driver_idx in range(len(self.drivers)):
                # Agrupar asignaciones por horario
                assignments_by_time = {}
                
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        time_key = f"{shift['start_time']}-{shift['end_time']}"
                        
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in assignments and
                                service_id in assignments[day_key] and
                                shift_num in assignments[day_key][service_id]):
                                
                                if time_key not in assignments_by_time:
                                    assignments_by_time[time_key] = []
                                
                                assignments_by_time[time_key].append(
                                    assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                )
                
                # Para cada horario único, el conductor puede estar en máximo 1 servicio
                for time_key, vars_list in assignments_by_time.items():
                    if len(vars_list) > 1:
                        # Solo una de estas variables puede ser verdadera
                        model.Add(sum(vars_list) <= 1)
        
        # RESTRICCIÓN 2.6: Máximo 12 horas de jornada laboral continua
        # La jornada empieza cuando entra al primer turno y termina cuando sale del último
        # Máximo 12 horas continuas, puede cruzar días (ej: 21:00 a 09:00 del siguiente día)
        MAX_DAILY_SPAN_HOURS = 12
        
        # Verificar jornadas que pueden cruzar días
        for day_idx in range(len(days)):
            for driver_idx in range(len(self.drivers)):
                # Recolectar turnos de este día y el siguiente (para jornadas que cruzan medianoche)
                all_shifts = []
                
                # Turnos del día actual
                day = days[day_idx]
                day_key = day.isoformat()
                
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in assignments and
                                service_id in assignments[day_key] and
                                shift_num in assignments[day_key][service_id]):
                                
                                all_shifts.append({
                                    'var': assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx],
                                    'start': shift['start_time'],
                                    'end': shift['end_time'],
                                    'day': 0  # Día actual
                                })
                
                # Turnos del día siguiente (si existe)
                if day_idx + 1 < len(days):
                    next_day = days[day_idx + 1]
                    next_day_key = next_day.isoformat()
                    
                    for service in self.services:
                        if next_day.weekday() not in service['frequency']['days']:
                            continue
                        service_id = service['id']
                        for shift in service['shifts']:
                            shift_num = shift['shift_number']
                            # Solo considerar turnos tempranos del día siguiente (antes del mediodía)
                            if int(shift['start_time'].split(':')[0]) < 12:
                                for vehicle_idx in range(service['vehicles']['quantity']):
                                    if (next_day_key in assignments and
                                        service_id in assignments[next_day_key] and
                                        shift_num in assignments[next_day_key][service_id]):
                                        
                                        all_shifts.append({
                                            'var': assignments[next_day_key][service_id][shift_num][vehicle_idx][driver_idx],
                                            'start': shift['start_time'],
                                            'end': shift['end_time'],
                                            'day': 1  # Día siguiente
                                        })
                
                # Verificar todas las combinaciones de turnos
                for i, shift1 in enumerate(all_shifts):
                    for shift2 in all_shifts[i+1:]:
                        # Convertir a minutos absolutos considerando el día
                        def time_to_absolute_minutes(time_str, day):
                            h, m = map(int, time_str.split(':'))
                            return day * 24 * 60 + h * 60 + m
                        
                        start1 = time_to_absolute_minutes(shift1['start'], shift1['day'])
                        end1 = time_to_absolute_minutes(shift1['end'], shift1['day'])
                        start2 = time_to_absolute_minutes(shift2['start'], shift2['day'])
                        end2 = time_to_absolute_minutes(shift2['end'], shift2['day'])
                        
                        # Ajustar si el turno cruza medianoche
                        if shift1['end'] < shift1['start'] and shift1['day'] == 0:
                            end1 += 24 * 60
                        if shift2['end'] < shift2['start'] and shift2['day'] == 0:
                            end2 += 24 * 60
                        
                        # Calcular el span total
                        earliest_start = min(start1, start2)
                        latest_end = max(end1, end2)
                        
                        total_span_minutes = latest_end - earliest_start
                        
                        # Si el span total excede 12 horas, no pueden hacer ambos turnos
                        if total_span_minutes > MAX_DAILY_SPAN_HOURS * 60:
                            model.Add(shift1['var'] + shift2['var'] <= 1)
        
        # RESTRICCIÓN 3: Máximo 44 horas semanales
        for week_start in range(0, len(days), 7):
            week_days = days[week_start:min(week_start+7, len(days))]
            
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
                                if (day_key in assignments and
                                    service_id in assignments[day_key] and
                                    shift_num in assignments[day_key][service_id]):
                                    week_hours.append(
                                        assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx] * hours
                                    )
                
                if week_hours:
                    model.Add(sum(week_hours) <= driver.max_weekly_hours * 10)
        
        # RESTRICCIÓN 4: Máximo horas mensuales
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
                            if (day_key in assignments and
                                service_id in assignments[day_key] and
                                shift_num in assignments[day_key][service_id]):
                                month_hours.append(
                                    assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx] * hours
                                )
            
            if month_hours:
                model.Add(sum(month_hours) <= driver.max_monthly_hours * 10)
        
        # RESTRICCIÓN 5: Máximo 5 horas continuas de conducción
        # Un turno individual no puede ser mayor a 5 horas
        for service in self.services:
            for shift in service['shifts']:
                if shift['duration_hours'] > 5:
                    print(f"  ⚠ ADVERTENCIA: El turno {shift['shift_number']} del servicio {service['name']} ")
                    print(f"    dura {shift['duration_hours']} horas (máximo permitido: 5 horas)")
        
        # RESTRICCIÓN 6: Descanso proporcional
        # 2h de descanso por cada 5h continuas de conducción
        # Aplica tanto dentro del mismo día como entre días consecutivos
        
        for driver_idx in range(len(self.drivers)):
            for day_idx, day in enumerate(days[:-1]):  # No revisar el último día
                day1_key = day.isoformat()
                day2_key = days[day_idx + 1].isoformat()
                
                # Recolectar todos los turnos de ambos días para este conductor
                day1_shifts = []
                day2_shifts = []
                
                # Turnos del día 1
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day1_key in assignments and
                                service_id in assignments[day1_key] and
                                shift_num in assignments[day1_key][service_id]):
                                
                                day1_shifts.append({
                                    'var': assignments[day1_key][service_id][shift_num][vehicle_idx][driver_idx],
                                    'start_time': shift['start_time'],
                                    'end_time': shift['end_time'],
                                    'duration': shift['duration_hours']
                                })
                
                # Turnos del día 2
                next_day = days[day_idx + 1]
                for service in self.services:
                    if next_day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day2_key in assignments and
                                service_id in assignments[day2_key] and
                                shift_num in assignments[day2_key][service_id]):
                                
                                day2_shifts.append({
                                    'var': assignments[day2_key][service_id][shift_num][vehicle_idx][driver_idx],
                                    'start_time': shift['start_time'],
                                    'end_time': shift['end_time'],
                                    'duration': shift['duration_hours']
                                })
                
                # Para cada combinación de turnos entre días consecutivos
                # Aplicar descanso proporcional: 2h por cada 5h de conducción
                
                for shift1 in day1_shifts:
                    for shift2 in day2_shifts:
                        # Calcular tiempo entre turnos
                        end_h1, end_m1 = map(int, shift1['end_time'].split(':'))
                        start_h2, start_m2 = map(int, shift2['start_time'].split(':'))
                        
                        end_minutes1 = end_h1 * 60 + end_m1
                        start_minutes2 = start_h2 * 60 + start_m2
                        
                        # Si el turno 1 termina después de medianoche
                        if end_h1 < 6:
                            end_minutes1 += 24 * 60
                        
                        # Calcular gap
                        if start_minutes2 < end_minutes1:
                            gap_minutes = (24 * 60 - end_minutes1) + start_minutes2
                        else:
                            gap_minutes = start_minutes2 - end_minutes1
                        
                        # Descanso proporcional: 2h por cada 5h de conducción
                        required_rest_minutes = int((shift1['duration'] * 2 * 60) / 5)
                        
                        # Aplicar restricción de descanso proporcional
                        if gap_minutes < required_rest_minutes:
                            model.Add(shift1['var'] + shift2['var'] <= 1)
                
                # RESTRICCIÓN ADICIONAL: Descanso proporcional durante la jornada
                # Si hay múltiples turnos el mismo día, verificar descanso entre ellos
                for shifts in [day1_shifts, day2_shifts]:
                    if len(shifts) >= 2:
                        for i in range(len(shifts)):
                            for j in range(i+1, len(shifts)):
                                shift_a = shifts[i]
                                shift_b = shifts[j]
                                
                                # Determinar orden temporal
                                start_a = int(shift_a['start_time'].split(':')[0])
                                start_b = int(shift_b['start_time'].split(':')[0])
                                
                                if start_a < start_b:
                                    first = shift_a
                                    second = shift_b
                                else:
                                    first = shift_b
                                    second = shift_a
                                
                                # Calcular gap
                                end_h, end_m = map(int, first['end_time'].split(':'))
                                start_h, start_m = map(int, second['start_time'].split(':'))
                                
                                gap_minutes = (start_h * 60 + start_m) - (end_h * 60 + end_m)
                                
                                # Descanso proporcional: 2h por cada 5h de conducción
                                required_rest = (first['duration'] * 2 * 60) / 5
                                
                                if gap_minutes < required_rest:
                                    model.Add(first['var'] + second['var'] <= 1)
        
        # RESTRICCIÓN 7: Máximo 6 días consecutivos de trabajo
        for driver_idx in range(len(self.drivers)):
            # Para cada ventana de 7 días consecutivos
            for start_idx in range(len(days) - 6):
                consecutive_days = []
                
                for day_offset in range(7):
                    day = days[start_idx + day_offset]
                    day_key = day.isoformat()
                    day_worked = []
                    
                    for service in self.services:
                        if day.weekday() not in service['frequency']['days']:
                            continue
                        service_id = service['id']
                        for shift in service['shifts']:
                            shift_num = shift['shift_number']
                            for vehicle_idx in range(service['vehicles']['quantity']):
                                if (day_key in assignments and
                                    service_id in assignments[day_key] and
                                    shift_num in assignments[day_key][service_id]):
                                    day_worked.append(
                                        assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                    )
                    
                    if day_worked:
                        # Variable que indica si el conductor trabajó este día
                        worked_this_day = model.NewBoolVar(f"day_worked_{driver_idx}_{day_key}")
                        model.AddMaxEquality(worked_this_day, day_worked)
                        consecutive_days.append(worked_this_day)
                    else:
                        # Si no hay turnos ese día, agregar 0
                        consecutive_days.append(0)
                
                # Restricción: en cualquier ventana de 7 días, máximo 6 días trabajados
                if consecutive_days:
                    model.Add(sum(consecutive_days) <= 6)
        
        # RESTRICCIÓN 6: Mínimo 2 domingos libres
        sundays = [d for d in days if d.weekday() == 6]
        
        if len(sundays) >= 2:
            for driver_idx in range(len(self.drivers)):
                sundays_worked = []
                
                for sunday in sundays:
                    day_key = sunday.isoformat()
                    sunday_shifts = []
                    
                    for service in self.services:
                        if sunday.weekday() not in service['frequency']['days']:
                            continue
                        service_id = service['id']
                        for shift in service['shifts']:
                            shift_num = shift['shift_number']
                            for vehicle_idx in range(service['vehicles']['quantity']):
                                if (day_key in assignments and
                                    service_id in assignments[day_key] and
                                    shift_num in assignments[day_key][service_id]):
                                    sunday_shifts.append(
                                        assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                    )
                    
                    if sunday_shifts:
                        worked = model.NewBoolVar(f"sun_{driver_idx}_{day_key}")
                        model.AddMaxEquality(worked, sunday_shifts)
                        sundays_worked.append(worked)
                
                if sundays_worked:
                    model.Add(sum(sundays_worked) <= len(sundays) - 2)
        
        # OBJETIVO: Minimizar conductores usados y balancear carga
        objective = []
        
        for driver_idx in range(len(self.drivers)):
            driver_used = model.NewBoolVar(f"used_{driver_idx}")
            all_assignments = []
            
            for day in days:
                day_key = day.isoformat()
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in assignments and
                                service_id in assignments[day_key] and
                                shift_num in assignments[day_key][service_id]):
                                all_assignments.append(
                                    assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]
                                )
            
            if all_assignments:
                model.AddMaxEquality(driver_used, all_assignments)
                # Penalizar más a conductores part-time (son más caros por hora)
                if self.drivers[driver_idx].contract_type == 'full_time':
                    objective.append(driver_used * 1000)
                else:
                    objective.append(driver_used * 1500)
        
        model.Minimize(sum(objective))
        
        # Configurar solver con parámetros más agresivos para mejor calidad
        solver.parameters.max_time_in_seconds = 60.0  # Más tiempo para mejor solución
        solver.parameters.num_search_workers = 8  # Más workers para búsqueda paralela
        solver.parameters.linearization_level = 2  # Mejor linearización
        solver.parameters.cp_model_presolve = True  # Activar presolve
        solver.parameters.cp_model_probing_level = 2  # Más probing
        
        # Registrar callback para monitorear progreso
        solution_printer = SolutionPrinter(len(self.drivers))
        
        status = solver.Solve(model, solution_printer)
        
        # Obtener estadísticas del solver
        print(f"  Estado: {solver.StatusName(status)}")
        print(f"  Tiempo: {solver.WallTime():.2f}s")
        print(f"  Ramas exploradas: {solver.NumBranches()}")
        print(f"  Conflictos: {solver.NumConflicts()}")
        
        # Diagnóstico adicional si es infactible
        violations = []  # Mover fuera del if para poder usarlo en el return
        
        if status == cp_model.INFEASIBLE:
            print("  ⚠️ ANÁLISIS DE RESTRICCIONES NO CUMPLIDAS:")
            
            # Calcular requerimientos teóricos
            total_shifts_needed = len(days) * sum(
                service['vehicles']['quantity'] * len(service['shifts']) 
                for service in self.services
            )
            total_hours_needed = sum(
                service['vehicles']['quantity'] * 
                sum(shift['duration_hours'] for shift in service['shifts']) * 
                len([d for d in days if d.weekday() in service['frequency']['days']])
                for service in self.services
            )
            
            current_capacity = len(self.drivers) * 180
            print(f"    Capacidad: {current_capacity}h vs Necesidad: {total_hours_needed:.0f}h")
            
            # 1. RESTRICCIÓN DE HORAS TOTALES
            if current_capacity < total_hours_needed:
                violations.append(f"❌ HORAS INSUFICIENTES: Faltan {total_hours_needed - current_capacity:.0f}h")
            
            # 2. RESTRICCIÓN DE 44H SEMANALES
            weeks = (len(days) + 6) // 7
            max_hours_per_driver_weekly = 44 * weeks
            min_drivers_by_weekly = total_hours_needed / max_hours_per_driver_weekly
            if len(self.drivers) < min_drivers_by_weekly:
                violations.append(f"❌ 44H SEMANALES: Necesita {min_drivers_by_weekly:.0f} conductores (tiene {len(self.drivers)})")
            
            # 3. RESTRICCIÓN DE DOMINGOS
            sundays = sum(1 for d in days if d.weekday() == 6)
            shifts_per_sunday = sum(
                service['vehicles']['quantity'] * len(service['shifts'])
                for service in self.services
                if 6 in service['frequency']['days']
            )
            
            # Con restricción T1+T3 y 50% disponibilidad domingo
            min_drivers_by_sundays = (sundays * shifts_per_sunday) / 4  # 2 domingos × 2 turnos
            if len(self.drivers) < min_drivers_by_sundays:
                violations.append(f"❌ DOMINGOS LIBRES: Necesita {min_drivers_by_sundays:.0f} conductores (tiene {len(self.drivers)})")
            
            
            # 5. RESTRICCIÓN DE COBERTURA SIMULTÁNEA
            max_simultaneous = max(
                sum(s['vehicles']['quantity'] for s in self.services 
                    for shift in s['shifts'] if int(shift['start_time'].split(':')[0]) < 12),
                sum(s['vehicles']['quantity'] for s in self.services 
                    for shift in s['shifts'] if 12 <= int(shift['start_time'].split(':')[0]) < 17),
                sum(s['vehicles']['quantity'] for s in self.services 
                    for shift in s['shifts'] if int(shift['start_time'].split(':')[0]) >= 17)
            )
            if len(self.drivers) < max_simultaneous:
                violations.append(f"❌ COBERTURA SIMULTÁNEA: Necesita mínimo {max_simultaneous} conductores")
            
            # Mostrar violaciones encontradas
            if violations:
                print("    RESTRICCIONES VIOLADAS:")
                for v in violations:
                    print(f"      {v}")
            else:
                print("    ⚠️ No se detectaron violaciones obvias.")
                print("    Posible problema con combinación compleja de restricciones.")
        
        if status == cp_model.OPTIMAL:
            print(f"  ✓ SOLUCIÓN ÓPTIMA ENCONTRADA")
        elif status == cp_model.FEASIBLE:
            print(f"  ✓ Solución factible (puede no ser óptima)")
            if solver.BestObjectiveBound() != solver.ObjectiveValue():
                gap = abs(solver.ObjectiveValue() - solver.BestObjectiveBound()) / max(1, abs(solver.ObjectiveValue())) * 100
                print(f"  Gap de optimalidad: {gap:.2f}%")
        
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
                for service in self.services:
                    if day.weekday() not in service['frequency']['days']:
                        continue
                    service_id = service['id']
                    for shift in service['shifts']:
                        shift_num = shift['shift_number']
                        for vehicle_idx in range(service['vehicles']['quantity']):
                            if (day_key in assignments and
                                service_id in assignments[day_key] and
                                shift_num in assignments[day_key][service_id]):
                                for driver_idx in range(len(self.drivers)):
                                    if solver.Value(assignments[day_key][service_id][shift_num][vehicle_idx][driver_idx]):
                                        drivers_with_assignments.add(driver_idx)
                                        solution['assignments'].append({
                                            'date': day_key,
                                            'service': service['name'],
                                            'shift': shift_num,
                                            'vehicle': vehicle_idx,
                                            'driver_id': self.drivers[driver_idx].id,
                                            'driver_name': self.drivers[driver_idx].name,
                                            'hours': shift['duration_hours'],
                                            'duration_hours': shift['duration_hours'],
                                            'start_time': shift['start_time'],
                                            'end_time': shift['end_time']
                                        })
            
            solution['drivers_used'] = len(drivers_with_assignments)
            return solution
        
        return {
            'status': 'failed', 
            'reason': f'Status: {status}',
            'constraint_violations': violations if violations else []
        }
    
    def _verify_solution_quality(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica la calidad de la solución encontrada"""
        quality_metrics = {
            'conductors_used': solution.get('drivers_used', 0),
            'total_hours': sum(a.get('hours', 0) for a in solution.get('assignments', [])),
            'coverage': len(solution.get('assignments', [])),
            'efficiency_metrics': {}
        }
        
        # Calcular eficiencia de utilización
        if solution.get('driver_summary'):
            utilizations = [d['utilization'] for d in solution['driver_summary'].values() if d.get('assignments', 0) > 0]
            if utilizations:
                quality_metrics['efficiency_metrics'] = {
                    'avg_utilization': np.mean(utilizations),
                    'min_utilization': min(utilizations),
                    'max_utilization': max(utilizations),
                    'std_utilization': np.std(utilizations)
                }
        
        # Calcular límite teórico inferior de conductores
        total_hours_needed = quality_metrics['total_hours']
        theoretical_min_drivers = int(np.ceil(total_hours_needed / 160)) if total_hours_needed > 0 else 1
        quality_metrics['theoretical_min_drivers'] = theoretical_min_drivers
        quality_metrics['optimality_ratio'] = quality_metrics['conductors_used'] / max(1, theoretical_min_drivers)
        
        # Evaluar calidad
        if quality_metrics['optimality_ratio'] <= 1.1:
            quality_metrics['quality'] = 'EXCELENTE (≤10% del óptimo teórico)'
        elif quality_metrics['optimality_ratio'] <= 1.2:
            quality_metrics['quality'] = 'BUENA (≤20% del óptimo teórico)'
        elif quality_metrics['optimality_ratio'] <= 1.3:
            quality_metrics['quality'] = 'ACEPTABLE (≤30% del óptimo teórico)'
        else:
            quality_metrics['quality'] = 'MEJORABLE (>30% del óptimo teórico)'
        
        solution['quality_metrics'] = quality_metrics
        
        print(f"\n=== MÉTRICAS DE CALIDAD DE LA SOLUCIÓN ===")
        print(f"Conductores utilizados: {quality_metrics['conductors_used']}")
        print(f"Límite teórico inferior: {quality_metrics['theoretical_min_drivers']}")
        print(f"Ratio de optimalidad: {quality_metrics['optimality_ratio']:.2f}")
        print(f"Calidad de la solución: {quality_metrics['quality']}")
        
        if quality_metrics.get('efficiency_metrics'):
            em = quality_metrics['efficiency_metrics']
            print(f"\nEficiencia de utilización:")
            print(f"  - Promedio: {em['avg_utilization']:.1f}%")
            print(f"  - Mínimo: {em['min_utilization']:.1f}%")
            print(f"  - Máximo: {em['max_utilization']:.1f}%")
            print(f"  - Desviación: {em['std_utilization']:.1f}%")
        
        return solution
    
    def _finalize_solution(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Finaliza la solución con métricas y resúmenes, categorizando conductores por horas trabajadas"""
        
        # Calcular métricas por conductor y categorizar
        driver_summary = {}
        full_time_count = 0
        part_time_count = 0
        total_cost = 0
        
        for driver in self.drivers:
            driver_assignments = [a for a in solution['assignments'] if a['driver_id'] == driver.id]
            total_hours = sum(a['hours'] for a in driver_assignments)
            
            # Contar solo domingos únicos (no turnos)
            sunday_dates = set([a['date'] for a in driver_assignments 
                               if datetime.fromisoformat(a['date']).weekday() == 6])
            sundays_worked = len(sunday_dates)
            
            # CATEGORIZACIÓN POST-OPTIMIZACIÓN
            if total_hours > 120:  # Más de 120 horas = Full Time
                contract_type = 'full_time'
                salary = self.costs['full_time']['base_salary']
                full_time_count += 1
            else:  # 120 horas o menos = Part Time
                contract_type = 'part_time'
                salary = self.costs.get('part_time_30h', {'base_salary': 600000})['base_salary']
                part_time_count += 1
            
            # Solo agregar costo si el conductor trabajó
            if len(driver_assignments) > 0:
                total_cost += salary
            
            # Contar días únicos trabajados
            days_worked = len(set(a['date'] for a in driver_assignments))
            
            driver_summary[driver.id] = {
                'name': driver.name.replace('Full Time ', '').replace('Part Time 30h ', ''),  # Limpiar nombre
                'contract_type': contract_type,
                'assignments': len(driver_assignments),
                'total_assignments': len(driver_assignments),
                'total_hours': round(total_hours, 1),
                'days_worked': days_worked,
                'utilization': round(total_hours / 180 * 100, 1),  # Siempre sobre 180h máximo
                'sundays_worked': sundays_worked,
                'salary': salary
            }
        
        # Métricas globales
        total_drivers = len(self.drivers)
        drivers_used = solution['drivers_used']
        total_hours = sum(d['total_hours'] for d in driver_summary.values())
        avg_utilization = np.mean([d['utilization'] for d in driver_summary.values() if d['assignments'] > 0])
        
        solution['driver_summary'] = driver_summary
        solution['metrics'] = {
            'total_drivers': total_drivers,
            'drivers_used': drivers_used,
            'total_hours': round(total_hours, 1),
            'avg_utilization': round(avg_utilization, 1),
            'full_time_count': full_time_count,
            'part_time_count': part_time_count,
            'part_time_30h_count': part_time_count,  # Para compatibilidad
            'part_time_20h_count': 0,  # Para compatibilidad
            'total_cost': total_cost
        }
        
        print(f"\n=== RESUMEN FINAL ===")
        print(f"Conductores totales: {total_drivers}")
        print(f"Conductores utilizados: {drivers_used}")
        print(f"  - Full Time (>120h): {full_time_count}")
        print(f"  - Part Time (≤120h): {part_time_count}")
        print(f"Utilización promedio: {avg_utilization:.1f}%")
        print(f"Total asignaciones: {len(solution['assignments'])}")
        
        return solution