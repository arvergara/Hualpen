"""
Optimizador de turnos robusto y eficiente
Versión simplificada para garantizar resultados rápidos y confiables
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta, date
import numpy as np
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class Driver:
    """Representa un conductor"""
    id: str
    name: str
    max_monthly_hours: int = 180
    max_weekly_hours: int = 44


class RobustRosterOptimizer:
    """
    Optimizador robusto con enfoque simplificado
    Prioriza encontrar soluciones válidas rápidamente
    """
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.costs = client_data.get('costs', {})
        self.parameters = client_data.get('parameters', {})
        self.drivers = []
        
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """
        Optimiza un mes completo con enfoque robusto
        """
        print(f"\n=== OPTIMIZACIÓN ROBUSTA {year}-{month:02d} ===")
        
        # Paso 1: Generar días del mes
        days = self._generate_month_days(year, month)
        
        # Paso 2: Generar todos los turnos necesarios
        shifts = self._generate_shifts(days)
        print(f"Turnos totales a cubrir: {len(shifts)}")
        
        # Paso 3: Calcular conductores necesarios
        total_hours = sum(s['duration_hours'] for s in shifts)
        min_drivers = int(np.ceil(total_hours / 160))  # 160h/mes por conductor
        max_drivers = min_drivers * 2  # Margen amplio para garantizar factibilidad
        
        print(f"Horas totales: {total_hours:.1f}")
        print(f"Conductores mínimos teóricos: {min_drivers}")
        print(f"Intentando con hasta: {max_drivers} conductores")
        
        # Paso 4: Buscar solución incrementalmente
        for num_drivers in range(min_drivers, max_drivers + 1):
            print(f"\nIntentando con {num_drivers} conductores...")
            
            # Crear pool de conductores
            self.drivers = [
                Driver(
                    id=f"D{i+1:03d}",
                    name=f"Conductor {i+1}"
                )
                for i in range(num_drivers)
            ]
            
            # Intentar optimizar
            result = self._optimize_with_drivers(shifts, days)
            
            if result['status'] == 'success':
                print(f"✓ Solución encontrada con {num_drivers} conductores")
                return self._format_solution(result, shifts)
            
            print(f"✗ No factible con {num_drivers} conductores")
        
        # Si no encontramos solución, devolver fallo
        return {
            'status': 'failed',
            'reason': f'No se encontró solución factible con hasta {max_drivers} conductores'
        }
    
    def _generate_month_days(self, year: int, month: int) -> List[date]:
        """Genera todos los días del mes"""
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
        """Genera todos los turnos que necesitan ser cubiertos"""
        shifts = []
        shift_id = 0
        
        for day in days:
            for service in self.services:
                # Verificar si el servicio opera este día
                if day.weekday() not in service['frequency']['days']:
                    continue
                
                # Para cada vehículo del servicio
                for vehicle_idx in range(service['vehicles']['quantity']):
                    # Para cada turno del servicio
                    for shift in service['shifts']:
                        shifts.append({
                            'id': shift_id,
                            'date': day,
                            'service_id': service['id'],
                            'service_name': service['name'],
                            'vehicle': vehicle_idx,
                            'shift_number': shift['shift_number'],
                            'start_time': shift['start_time'],
                            'end_time': shift['end_time'],
                            'duration_hours': shift['duration_hours'],
                            'day_of_week': day.weekday(),
                            'week_num': (day.day - 1) // 7 + 1
                        })
                        shift_id += 1
        
        return shifts
    
    def _optimize_with_drivers(self, shifts: List[Dict], days: List[date]) -> Dict[str, Any]:
        """Optimiza con un número fijo de conductores"""
        
        # Crear modelo
        model = cp_model.CpModel()
        
        # Variables: x[s][d] = 1 si el turno s es asignado al conductor d
        x = {}
        for shift_idx, shift in enumerate(shifts):
            x[shift_idx] = {}
            for driver_idx in range(len(self.drivers)):
                x[shift_idx][driver_idx] = model.NewBoolVar(
                    f"x_{shift_idx}_{driver_idx}"
                )
        
        # Restricción 1: Cada turno debe ser asignado a exactamente un conductor
        for shift_idx in range(len(shifts)):
            model.Add(sum(x[shift_idx][d] for d in range(len(self.drivers))) == 1)
        
        # Restricción 2: Un conductor no puede hacer dos turnos al mismo tiempo
        # Agrupar turnos por día
        shifts_by_day = defaultdict(list)
        for shift_idx, shift in enumerate(shifts):
            shifts_by_day[shift['date']].append(shift_idx)
        
        for driver_idx in range(len(self.drivers)):
            for day, day_shifts in shifts_by_day.items():
                # Agrupar por hora de inicio para detectar solapamientos
                overlapping_groups = self._find_overlapping_shifts(
                    [shifts[s] for s in day_shifts]
                )
                
                for group in overlapping_groups:
                    # Máximo 1 turno del grupo por conductor
                    group_indices = [day_shifts[i] for i in group]
                    model.Add(
                        sum(x[s][driver_idx] for s in group_indices) <= 1
                    )
        
        # Restricción 3: Horas semanales máximas (44h)
        for week_num in range(1, 5):  # Máximo 4 semanas completas
            week_shifts = [
                s for s in range(len(shifts)) 
                if shifts[s]['week_num'] == week_num
            ]
            
            for driver_idx in range(len(self.drivers)):
                week_hours = []
                for shift_idx in week_shifts:
                    hours = int(shifts[shift_idx]['duration_hours'] * 10)
                    week_hours.append(x[shift_idx][driver_idx] * hours)
                
                if week_hours:
                    model.Add(sum(week_hours) <= 440)  # 44h * 10
        
        # Restricción 4: Horas mensuales máximas (180h)
        for driver_idx in range(len(self.drivers)):
            month_hours = []
            for shift_idx in range(len(shifts)):
                hours = int(shifts[shift_idx]['duration_hours'] * 10)
                month_hours.append(x[shift_idx][driver_idx] * hours)
            
            model.Add(sum(month_hours) <= 1800)  # 180h * 10
        
        # Restricción 5: Máximo 6 días consecutivos de trabajo
        for driver_idx in range(len(self.drivers)):
            for start_day in range(len(days) - 6):
                consecutive_days = days[start_day:start_day + 7]
                worked_days = []
                
                for day in consecutive_days:
                    day_worked = model.NewBoolVar(
                        f"worked_{driver_idx}_{day.isoformat()}"
                    )
                    
                    # El conductor trabajó este día si hizo algún turno
                    day_shifts = [
                        s for s in range(len(shifts))
                        if shifts[s]['date'] == day
                    ]
                    
                    if day_shifts:
                        model.AddMaxEquality(
                            day_worked,
                            [x[s][driver_idx] for s in day_shifts]
                        )
                        worked_days.append(day_worked)
                
                if worked_days:
                    model.Add(sum(worked_days) <= 6)
        
        # Objetivo: Minimizar el número de conductores utilizados
        drivers_used = []
        for driver_idx in range(len(self.drivers)):
            driver_used = model.NewBoolVar(f"used_{driver_idx}")
            
            # El conductor se usa si tiene al menos un turno
            all_driver_shifts = [
                x[s][driver_idx] for s in range(len(shifts))
            ]
            model.AddMaxEquality(driver_used, all_driver_shifts)
            drivers_used.append(driver_used)
        
        # Minimizar conductores y balancear carga
        model.Minimize(sum(drivers_used) * 1000)
        
        # Configurar solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0  # Límite de tiempo corto
        solver.parameters.num_search_workers = 4
        
        # Resolver
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # Extraer solución
            assignments = []
            drivers_with_work = set()
            
            for shift_idx, shift in enumerate(shifts):
                for driver_idx in range(len(self.drivers)):
                    if solver.Value(x[shift_idx][driver_idx]):
                        drivers_with_work.add(driver_idx)
                        assignments.append({
                            'shift_idx': shift_idx,
                            'driver_idx': driver_idx
                        })
            
            return {
                'status': 'success',
                'assignments': assignments,
                'drivers_used': len(drivers_with_work)
            }
        
        return {'status': 'failed'}
    
    def _find_overlapping_shifts(self, shifts: List[Dict]) -> List[List[int]]:
        """Encuentra grupos de turnos que se solapan en tiempo"""
        groups = []
        
        # Agrupar por número de turno (1, 2, 3)
        by_shift_num = defaultdict(list)
        for i, shift in enumerate(shifts):
            by_shift_num[shift['shift_number']].append(i)
        
        # Cada grupo de mismo número de turno se solapa
        for shift_num, indices in by_shift_num.items():
            if len(indices) > 1:
                groups.append(indices)
        
        return groups
    
    def _format_solution(self, result: Dict, shifts: List[Dict]) -> Dict[str, Any]:
        """Formatea la solución para salida"""
        
        assignments = []
        driver_stats = defaultdict(lambda: {'hours': 0, 'shifts': 0})
        
        for assignment in result['assignments']:
            shift = shifts[assignment['shift_idx']]
            driver = self.drivers[assignment['driver_idx']]
            
            assignments.append({
                'date': shift['date'].isoformat(),
                'service': shift['service_id'],
                'service_name': shift['service_name'],
                'shift': shift['shift_number'],
                'vehicle': shift['vehicle'],
                'driver_id': driver.id,
                'driver_name': driver.name,
                'start_time': shift['start_time'],
                'end_time': shift['end_time'],
                'duration_hours': shift['duration_hours']
            })
            
            driver_stats[driver.id]['hours'] += shift['duration_hours']
            driver_stats[driver.id]['shifts'] += 1
            driver_stats[driver.id]['name'] = driver.name
        
        # Calcular métricas
        total_hours = sum(s['duration_hours'] for s in shifts)
        drivers_used = result['drivers_used']
        avg_utilization = (total_hours / (drivers_used * 180)) * 100 if drivers_used > 0 else 0
        
        # Calcular costo total estimado
        hourly_rate = 5000  # $5,000 por hora
        total_cost = total_hours * hourly_rate
        
        return {
            'status': 'success',
            'assignments': assignments,
            'drivers_used': drivers_used,
            'driver_stats': dict(driver_stats),
            'metrics': {
                'total_shifts': len(shifts),
                'total_hours': round(total_hours, 1),
                'total_cost': round(total_cost),
                'drivers_used': drivers_used,
                'avg_hours_per_driver': round(total_hours / drivers_used, 1) if drivers_used > 0 else 0,
                'avg_utilization': round(avg_utilization, 1)
            }
        }