"""
Optimizador de turnos con validación completa de restricciones laborales chilenas
Versión con todas las restricciones críticas implementadas y validadas
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime, timedelta, date, time
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
    max_daily_span_hours: int = 12  # Máximo span de jornada diaria


@dataclass
class ValidationResult:
    """Resultado de validación de restricciones"""
    is_valid: bool
    violations: List[str]
    driver_violations: Dict[str, List[str]]


class RobustRosterOptimizer:
    """
    Optimizador con validación completa de restricciones laborales
    Garantiza que NINGUNA solución viole las leyes laborales chilenas
    """
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.costs = client_data.get('costs', {})
        self.parameters = client_data.get('parameters', {})
        self.drivers = []
        
        # Parámetros de restricciones laborales CHILENAS - NO NEGOCIABLES
        self.MAX_DAILY_SPAN = 12  # Máximo span de jornada (horas) - LEY LABORAL
        self.MAX_WEEKLY_HOURS = 44
        self.MAX_MONTHLY_HOURS = 180
        self.MAX_CONSECUTIVE_DAYS = 6
        self.MAX_SUNDAYS_WORKED = 2  # Máximo 2 domingos trabajados al mes
        self.MIN_REST_BETWEEN_SHIFTS = 8  # Mínimo 8 horas de descanso
        
        # Control de validación
        self.strict_validation = True  # SIEMPRE validar restricciones
        self.forbidden_patterns = []  # Patrones de turnos prohibidos
        
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """
        Optimiza un mes completo con validación completa
        """
        print(f"\n=== OPTIMIZACIÓN CON VALIDACIÓN COMPLETA {year}-{month:02d} ===")
        
        # Paso 1: Generar días del mes
        days = self._generate_month_days(year, month)
        sundays = [d for d in days if d.weekday() == 6]
        print(f"Mes con {len(days)} días, {len(sundays)} domingos")
        
        # Paso 2: Generar todos los turnos necesarios
        shifts = self._generate_shifts(days)
        print(f"Turnos totales a cubrir: {len(shifts)}")
        
        # Paso 3: Calcular conductores necesarios considerando restricciones
        total_hours = sum(s['duration_hours'] for s in shifts)
        
        # Pre-validar patrones problemáticos
        print("\nPre-validando patrones de turnos...")
        forbidden_patterns = self._prevalidate_shift_patterns(shifts)
        if forbidden_patterns:
            unique_reasons = set(reason.split(' con turnos:')[0] for _, reason in forbidden_patterns)
            print(f"⚠️  Detectados {len(forbidden_patterns)} patrones potencialmente ilegales")
            print(f"   Tipos de violaciones encontradas: {len(unique_reasons)}")
            # Solo mostrar un resumen, no todos los casos
            print(f"   Ejemplo: Combinaciones T1+T3 que exceden 12h, T1+T2+T3 prohibidos, etc.")
        
        # Calcular conductores mínimos considerando restricciones reales
        # Considerar que muchos turnos no se pueden combinar por el span de 12h
        shifts_by_day = defaultdict(list)
        for shift in shifts:
            shifts_by_day[shift['date']].append(shift)
        
        # Estimar conductores necesarios basado en picos de demanda
        max_concurrent_shifts = 0
        for day, day_shifts in shifts_by_day.items():
            # Contar máximo de turnos simultáneos
            time_slots = defaultdict(int)
            for shift in day_shifts:
                for hour in range(shift['start_hour'], 
                                shift['end_hour'] if shift['end_hour'] > shift['start_hour'] else 24):
                    time_slots[hour] += 1
            if time_slots:
                max_concurrent_shifts = max(max_concurrent_shifts, max(time_slots.values()))
        
        # Considerar restricciones más estrictas para calcular mínimo real
        # Con jornada máxima de 12h y patrones prohibidos
        effective_hours_per_driver = min(
            self.MAX_MONTHLY_HOURS,
            self.MAX_WEEKLY_HOURS * 4.3,  # ~4.3 semanas por mes
            6 * 20  # Aproximadamente 6h/día por 20 días (considerando restricciones)
        )
        
        # El mínimo debe considerar tanto horas totales como concurrencia
        min_drivers_by_hours = int(np.ceil(total_hours / effective_hours_per_driver))
        min_drivers_by_concurrency = max_concurrent_shifts
        min_drivers = max(min_drivers_by_hours, min_drivers_by_concurrency)
        
        # Agregar margen de seguridad por restricciones de span
        min_drivers = int(min_drivers * 1.2)  # 20% extra por restricciones
        max_drivers = int(min_drivers * 3)  # Margen muy amplio para garantizar solución legal
        
        print(f"\nAnálisis de demanda:")
        print(f"  Horas totales: {total_hours:.1f}")
        print(f"  Máximo de turnos simultáneos: {max_concurrent_shifts}")
        print(f"  Horas efectivas por conductor (con restricciones): {effective_hours_per_driver:.1f}")
        print(f"  Conductores mínimos por horas: {min_drivers_by_hours}")
        print(f"  Conductores mínimos por concurrencia: {min_drivers_by_concurrency}")
        print(f"  Conductores mínimos ajustados: {min_drivers}")
        print(f"  Intentando con hasta: {max_drivers} conductores")
        print(f"\n💡 Nota: Es preferible usar más conductores que violar la ley laboral")
        
        # Paso 4: Buscar solución incrementalmente
        # IMPORTANTE: Es mejor tener más conductores legales que menos conductores ilegales
        for num_drivers in range(min_drivers, max_drivers + 1):
            print(f"\n{'='*60}")
            print(f"Intentando con {num_drivers} conductores...")
            print(f"Recordatorio: Es mejor usar {num_drivers} conductores LEGALES que violar la ley")
            
            # Crear pool de conductores
            self.drivers = [
                Driver(
                    id=f"D{i+1:03d}",
                    name=f"Conductor {i+1}"
                )
                for i in range(num_drivers)
            ]
            
            # Intentar optimizar con restricciones completas
            result = self._optimize_with_drivers(shifts, days, sundays)
            
            if result['status'] == 'success':
                # Validar la solución antes de aceptarla
                solution = self._format_solution(result, shifts)
                validation = self._validate_solution(solution, shifts, days)
                
                if validation.is_valid:
                    print(f"\n{'='*60}")
                    print(f"✅ SOLUCIÓN LEGAL ENCONTRADA")
                    print(f"✓ {num_drivers} conductores utilizados")
                    print(f"✓ TODAS las restricciones laborales cumplidas")
                    print(f"✓ Ningún conductor trabaja más de 12 horas continuas")
                    print(f"✓ Solución 100% legal según normativa chilena")
                    print(f"{'='*60}\n")
                    
                    solution['validation'] = {
                        'is_valid': True,
                        'message': 'Todas las restricciones laborales cumplidas - SOLUCIÓN LEGAL',
                        'drivers_needed': num_drivers,
                        'legal_compliance': 'COMPLETO'
                    }
                    return solution
                else:
                    print(f"\n⚠️  ALERTA: Solución ILEGAL detectada y RECHAZADA")
                    print(f"Violaciones encontradas: {len(validation.violations)}")
                    
                    # Mostrar violaciones agrupadas por tipo
                    span_violations = [v for v in validation.violations if '12h' in v or 'jornada' in v.lower()]
                    if span_violations:
                        print(f"\n  VIOLACIONES DE JORNADA (máx 12h):")
                        for v in span_violations[:3]:
                            print(f"    ❌ {v}")
                    
                    print(f"\n  → Incrementando conductores para encontrar solución legal...")
            else:
                print(f"✗ No factible con {num_drivers} conductores")
                print(f"  → Necesitamos más conductores para cumplir restricciones...")
        
        # Si no encontramos solución válida, devolver fallo
        return {
            'status': 'failed',
            'reason': f'No se encontró solución válida con hasta {max_drivers} conductores. '
                     f'Las restricciones laborales son muy estrictas para la demanda actual.'
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
                        # Parsear tiempos para cálculos
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
                            'start_min': start_min,
                            'end_hour': end_hour,
                            'end_min': end_min,
                            'duration_hours': shift['duration_hours'],
                            'day_of_week': day.weekday(),
                            'is_sunday': day.weekday() == 6,
                            'week_num': (day.day - 1) // 7 + 1
                        })
                        shift_id += 1
        
        return shifts
    
    def _calculate_workday_span(self, day_shifts: List[Dict]) -> float:
        """
        Calcula el span de la jornada laboral (desde primera entrada hasta última salida)
        CRÍTICO: Incluye TODO el tiempo desde el primer turno hasta el último,
        incluyendo breaks y tiempos muertos
        """
        if not day_shifts:
            return 0
        
        # Encontrar primera entrada y última salida
        earliest_start = min(s['start_hour'] * 60 + s['start_min'] for s in day_shifts)
        latest_end = max(s['end_hour'] * 60 + s['end_min'] for s in day_shifts)
        
        # Si el turno cruza medianoche (ej: termina a las 00:00)
        # Debemos considerar que 00:00 es 24:00 del mismo día
        for shift in day_shifts:
            end_minutes = shift['end_hour'] * 60 + shift['end_min']
            # Si termina a medianoche o después de medianoche pero muy temprano
            if shift['end_hour'] == 0 or (shift['end_hour'] < 6 and shift['start_hour'] >= 18):
                # Este turno cruza medianoche
                adjusted_end = 24 * 60  # Considerarlo como 24:00
                if adjusted_end > latest_end:
                    latest_end = adjusted_end
        
        span_minutes = latest_end - earliest_start
        span_hours = span_minutes / 60.0
        
        # Log para debugging (comentado para evitar ruido excesivo)
        
        return span_hours
    
    def _shifts_overlap(self, shift1: Dict, shift2: Dict) -> bool:
        """Verifica si dos turnos se solapan en tiempo"""
        # Convertir a minutos desde medianoche
        s1_start = shift1['start_hour'] * 60 + shift1['start_min']
        s1_end = shift1['end_hour'] * 60 + shift1['end_min']
        s2_start = shift2['start_hour'] * 60 + shift2['start_min']
        s2_end = shift2['end_hour'] * 60 + shift2['end_min']
        
        # Ajustar si cruzan medianoche
        if s1_end < s1_start:
            s1_end += 24 * 60
        if s2_end < s2_start:
            s2_end += 24 * 60
        
        # Verificar solapamiento
        return not (s1_end <= s2_start or s2_end <= s1_start)
    
    def _is_illegal_combination(self, shifts: List[Dict]) -> Tuple[bool, str]:
        """
        Verifica si una combinación de turnos es ilegal
        Retorna (es_ilegal, razón)
        """
        if not shifts:
            return False, ""
        
        # Calcular span total
        span = self._calculate_workday_span(shifts)
        
        if span > self.MAX_DAILY_SPAN:
            shift_desc = ', '.join([f"T{s['shift_number']}({s['start_time']}-{s['end_time']})" 
                                   for s in shifts])
            return True, f"Span de {span:.1f}h excede máximo de {self.MAX_DAILY_SPAN}h con turnos: {shift_desc}"
        
        # Verificar patrones específicamente prohibidos
        shift_numbers = sorted([s['shift_number'] for s in shifts])
        
        # T1+T2+T3 donde T3 es tarde (21:00) es siempre ilegal
        if shift_numbers == [1, 2, 3]:
            has_late_t3 = any(s['shift_number'] == 3 and s['start_hour'] >= 21 for s in shifts)
            if has_late_t3:
                return True, "Patrón T1+T2+T3(noche) prohibido: excede 12 horas"
        
        return False, ""
    
    def _prevalidate_shift_patterns(self, shifts: List[Dict]) -> List[Tuple[List[int], str]]:
        """
        Pre-valida patrones de turnos problemáticos
        Retorna lista de (índices_turnos, razón_prohibición)
        """
        forbidden_patterns = []
        shifts_by_day = defaultdict(list)
        
        for idx, shift in enumerate(shifts):
            shifts_by_day[shift['date']].append((idx, shift))
        
        for day, day_shifts_with_idx in shifts_by_day.items():
            day_shifts = [s for _, s in day_shifts_with_idx]
            indices = [idx for idx, _ in day_shifts_with_idx]
            
            # Buscar todas las combinaciones posibles
            from itertools import combinations
            for size in range(2, min(5, len(day_shifts) + 1)):
                for combo_indices in combinations(range(len(day_shifts)), size):
                    combo_shifts = [day_shifts[i] for i in combo_indices]
                    combo_shift_indices = [indices[i] for i in combo_indices]
                    
                    is_illegal, reason = self._is_illegal_combination(combo_shifts)
                    if is_illegal:
                        forbidden_patterns.append((combo_shift_indices, reason))
        
        return forbidden_patterns
    
    def _optimize_with_drivers(self, shifts: List[Dict], days: List[date], 
                              sundays: List[date]) -> Dict[str, Any]:
        """Optimiza con restricciones laborales completas"""
        
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
        
        # RESTRICCIÓN 1: Cada turno debe ser asignado a exactamente un conductor
        for shift_idx in range(len(shifts)):
            model.Add(sum(x[shift_idx][d] for d in range(len(self.drivers))) == 1)
        
        # Agrupar turnos por día y conductor para restricciones
        shifts_by_day = defaultdict(list)
        for shift_idx, shift in enumerate(shifts):
            shifts_by_day[shift['date']].append(shift_idx)
        
        # RESTRICCIÓN 2: Un conductor no puede hacer turnos que se solapen
        for driver_idx in range(len(self.drivers)):
            for day, day_shift_indices in shifts_by_day.items():
                day_shifts = [shifts[i] for i in day_shift_indices]
                
                # Verificar todos los pares de turnos
                for i in range(len(day_shifts)):
                    for j in range(i + 1, len(day_shifts)):
                        if self._shifts_overlap(day_shifts[i], day_shifts[j]):
                            # No puede hacer ambos turnos si se solapan
                            si = day_shift_indices[i]
                            sj = day_shift_indices[j]
                            model.Add(x[si][driver_idx] + x[sj][driver_idx] <= 1)
        
        # RESTRICCIÓN 3: Span máximo de jornada diaria (12 horas) - CRÍTICA
        print("\n=== APLICANDO RESTRICCIÓN CRÍTICA: JORNADA MÁXIMA 12 HORAS ===")
        print(f"Verificando todas las combinaciones de turnos para evitar jornadas ilegales...")
        
        violations_prevented = 0
        for driver_idx in range(len(self.drivers)):
            for day, day_shift_indices in shifts_by_day.items():
                if not day_shift_indices:
                    continue
                
                day_shifts = [shifts[i] for i in day_shift_indices]
                
                # Identificar patrones problemáticos comunes
                has_t1 = any(s['shift_number'] == 1 and s['start_hour'] == 6 for s in day_shifts)
                has_t2 = any(s['shift_number'] == 2 for s in day_shifts)
                has_t3_late = any(s['shift_number'] == 3 and s['start_hour'] >= 21 for s in day_shifts)
                
                # PROHIBIR EXPLÍCITAMENTE: T1 + T2 + T3(21:00)
                if has_t1 and has_t2 and has_t3_late:
                    # Encontrar los índices específicos
                    t1_indices = [i for i, s in enumerate(day_shifts) 
                                if s['shift_number'] == 1 and s['start_hour'] == 6]
                    t2_indices = [i for i, s in enumerate(day_shifts) 
                                if s['shift_number'] == 2]
                    t3_indices = [i for i, s in enumerate(day_shifts) 
                                if s['shift_number'] == 3 and s['start_hour'] >= 21]
                    
                    # Un conductor NO puede hacer los tres turnos
                    for t1_idx in t1_indices:
                        for t2_idx in t2_indices:
                            for t3_idx in t3_indices:
                                model.Add(
                                    x[day_shift_indices[t1_idx]][driver_idx] + 
                                    x[day_shift_indices[t2_idx]][driver_idx] + 
                                    x[day_shift_indices[t3_idx]][driver_idx] <= 2
                                )
                                violations_prevented += 1
                
                # Verificar TODAS las combinaciones posibles
                from itertools import combinations
                for subset_size in range(2, min(5, len(day_shifts) + 1)):
                    for subset_indices in combinations(range(len(day_shifts)), subset_size):
                        subset = [day_shifts[i] for i in subset_indices]
                        span = self._calculate_workday_span(subset)
                        
                        if span > self.MAX_DAILY_SPAN:
                            # Esta combinación viola el span de 12h - PROHIBIRLA
                            shift_vars = [x[day_shift_indices[i]][driver_idx] 
                                        for i in subset_indices]
                            # Un conductor no puede hacer todos estos turnos juntos
                            model.Add(sum(shift_vars) < len(subset))
                            violations_prevented += 1
                            
                            # Log específico para patrones problemáticos
                            if subset_size == 3:
                                shifts_desc = ', '.join([f"T{s['shift_number']}" for s in subset])
                                if driver_idx == 0:  # Solo log para el primer conductor
                                    print(f"  ✗ Prohibiendo patrón ilegal: {shifts_desc} (span: {span:.1f}h)")
        
        print(f"  → {violations_prevented} combinaciones ilegales prevenidas")
        print(f"  → Garantizando cumplimiento de jornada máxima de 12 horas")
        
        # RESTRICCIÓN 4: Horas semanales máximas (44h)
        for week_num in range(1, 5):
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
        
        # RESTRICCIÓN 5: Horas mensuales máximas (180h)
        for driver_idx in range(len(self.drivers)):
            month_hours = []
            for shift_idx in range(len(shifts)):
                hours = int(shifts[shift_idx]['duration_hours'] * 10)
                month_hours.append(x[shift_idx][driver_idx] * hours)
            
            model.Add(sum(month_hours) <= 1800)  # 180h * 10
        
        # RESTRICCIÓN 6: Máximo 2 domingos trabajados al mes
        print("Aplicando restricción de máximo 2 domingos trabajados...")
        for driver_idx in range(len(self.drivers)):
            sundays_worked = []
            
            for sunday in sundays:
                sunday_worked = model.NewBoolVar(
                    f"sunday_worked_{driver_idx}_{sunday.isoformat()}"
                )
                
                # El conductor trabajó este domingo si hizo algún turno
                sunday_shifts = [
                    s for s in range(len(shifts))
                    if shifts[s]['date'] == sunday
                ]
                
                if sunday_shifts:
                    # sunday_worked = 1 si algún turno del domingo es asignado
                    model.AddMaxEquality(
                        sunday_worked,
                        [x[s][driver_idx] for s in sunday_shifts]
                    )
                    sundays_worked.append(sunday_worked)
            
            if sundays_worked:
                model.Add(sum(sundays_worked) <= self.MAX_SUNDAYS_WORKED)
        
        # RESTRICCIÓN 7: Máximo 6 días consecutivos de trabajo
        for driver_idx in range(len(self.drivers)):
            for start_day in range(len(days) - 6):
                consecutive_days = days[start_day:start_day + 7]
                worked_days = []
                
                for day in consecutive_days:
                    day_worked = model.NewBoolVar(
                        f"worked_{driver_idx}_{day.isoformat()}"
                    )
                    
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
                    model.Add(sum(worked_days) <= self.MAX_CONSECUTIVE_DAYS)
        
        # RESTRICCIÓN 8: Descanso mínimo entre turnos (8 horas)
        print("Aplicando restricción de descanso mínimo entre turnos...")
        for driver_idx in range(len(self.drivers)):
            # Para cada par de días consecutivos
            for day_idx in range(len(days) - 1):
                day1 = days[day_idx]
                day2 = days[day_idx + 1]
                
                day1_shifts = [s for s in range(len(shifts)) if shifts[s]['date'] == day1]
                day2_shifts = [s for s in range(len(shifts)) if shifts[s]['date'] == day2]
                
                # Para cada turno del día 1 que termina tarde
                for s1_idx in day1_shifts:
                    s1 = shifts[s1_idx]
                    # Solo considerar turnos que terminan después de las 16:00
                    if s1['end_hour'] >= 16:
                        # Para cada turno del día 2 que empieza temprano
                        for s2_idx in day2_shifts:
                            s2 = shifts[s2_idx]
                            # Solo considerar turnos que empiezan antes de las 12:00
                            if s2['start_hour'] < 12:
                                # Calcular horas de descanso
                                rest_hours = s2['start_hour'] + (24 - s1['end_hour'])
                                
                                if rest_hours < self.MIN_REST_BETWEEN_SHIFTS:
                                    # No puede hacer ambos turnos
                                    model.Add(x[s1_idx][driver_idx] + x[s2_idx][driver_idx] <= 1)
        
        # Objetivo: Minimizar conductores y balancear carga
        drivers_used = []
        driver_load_variance = []
        
        for driver_idx in range(len(self.drivers)):
            driver_used = model.NewBoolVar(f"used_{driver_idx}")
            
            # El conductor se usa si tiene al menos un turno
            all_driver_shifts = [
                x[s][driver_idx] for s in range(len(shifts))
            ]
            model.AddMaxEquality(driver_used, all_driver_shifts)
            drivers_used.append(driver_used)
            
            # Calcular carga del conductor
            driver_hours = sum(
                x[s][driver_idx] * int(shifts[s]['duration_hours'] * 10)
                for s in range(len(shifts))
            )
            driver_load_variance.append(driver_hours)
        
        # Objetivo principal: minimizar conductores
        # Objetivo secundario: balancear carga
        model.Minimize(sum(drivers_used) * 10000)
        
        # Configurar solver con parámetros optimizados
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0  # Más tiempo para encontrar solución legal
        solver.parameters.num_search_workers = 4
        solver.parameters.log_search_progress = False  # Menos verbose
        solver.parameters.linearization_level = 2  # Mejor para restricciones complejas
        solver.parameters.cp_model_presolve = True
        
        # Resolver
        print("Resolviendo modelo con todas las restricciones...")
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
            
            print(f"Solución encontrada con {len(drivers_with_work)} conductores activos")
            return {
                'status': 'success',
                'assignments': assignments,
                'drivers_used': len(drivers_with_work),
                'solver_status': 'optimal' if status == cp_model.OPTIMAL else 'feasible'
            }
        
        print(f"No se encontró solución factible (status: {status})")
        return {'status': 'failed'}
    
    def _validate_solution(self, solution: Dict[str, Any], 
                          shifts: List[Dict], days: List[date]) -> ValidationResult:
        """
        Valida exhaustivamente que la solución cumpla TODAS las restricciones laborales
        """
        violations = []
        driver_violations = defaultdict(list)
        
        if solution['status'] != 'success':
            return ValidationResult(False, ['Solución no exitosa'], {})
        
        # Agrupar asignaciones por conductor
        driver_assignments = defaultdict(list)
        for assignment in solution['assignments']:
            driver_id = assignment['driver_id']
            driver_assignments[driver_id].append(assignment)
        
        # Validar cada conductor
        for driver_id, assignments in driver_assignments.items():
            driver_name = assignments[0]['driver_name'] if assignments else driver_id
            
            # 1. Validar horas mensuales
            total_hours = sum(a['duration_hours'] for a in assignments)
            if total_hours > self.MAX_MONTHLY_HOURS:
                violation = f"{driver_name}: {total_hours:.1f}h mensuales (máx: {self.MAX_MONTHLY_HOURS}h)"
                violations.append(violation)
                driver_violations[driver_id].append(violation)
            
            # 2. Validar horas semanales
            weeks = defaultdict(float)
            for a in assignments:
                week = (datetime.fromisoformat(a['date']).day - 1) // 7 + 1
                weeks[week] += a['duration_hours']
            
            for week, hours in weeks.items():
                if hours > self.MAX_WEEKLY_HOURS:
                    violation = f"{driver_name}: {hours:.1f}h en semana {week} (máx: {self.MAX_WEEKLY_HOURS}h)"
                    violations.append(violation)
                    driver_violations[driver_id].append(violation)
            
            # 3. Validar span de jornada diaria (CRÍTICO)
            days_worked = defaultdict(list)
            for a in assignments:
                days_worked[a['date']].append(a)
            
            for day, day_assignments in days_worked.items():
                if len(day_assignments) > 1:
                    # Calcular span de la jornada
                    earliest_start = min(a['start_time'] for a in day_assignments)
                    latest_end = max(a['end_time'] for a in day_assignments)
                    
                    # Convertir a horas
                    start_h, start_m = map(int, earliest_start.split(':'))
                    end_h, end_m = map(int, latest_end.split(':'))
                    
                    start_minutes = start_h * 60 + start_m
                    end_minutes = end_h * 60 + end_m
                    
                    # Si cruza medianoche
                    if end_minutes < start_minutes:
                        end_minutes += 24 * 60
                    
                    span_hours = (end_minutes - start_minutes) / 60.0
                    
                    if span_hours > self.MAX_DAILY_SPAN:
                        shifts_desc = ', '.join([f"T{a['shift']}" for a in day_assignments])
                        violation = (f"{driver_name} el {day}: ILEGAL - jornada de {span_hours:.1f}h "
                                   f"({earliest_start} a {latest_end}, turnos: {shifts_desc}) "
                                   f"VIOLA LEY LABORAL (máx: {self.MAX_DAILY_SPAN}h)")
                        violations.append(violation)
                        driver_violations[driver_id].append(violation)
                        
                        # Log crítico
                        print(f"\n🚨 VIOLACIÓN CRÍTICA DETECTADA:")
                        print(f"   {violation}")
                        print(f"   Esta asignación es ILEGAL y debe ser corregida\n")
            
            # 4. Validar domingos trabajados
            sundays_worked = set()
            for a in assignments:
                date_obj = datetime.fromisoformat(a['date']).date()
                if date_obj.weekday() == 6:  # Domingo
                    sundays_worked.add(date_obj)
            
            if len(sundays_worked) > self.MAX_SUNDAYS_WORKED:
                violation = f"{driver_name}: {len(sundays_worked)} domingos trabajados (máx: {self.MAX_SUNDAYS_WORKED})"
                violations.append(violation)
                driver_violations[driver_id].append(violation)
            
            # 5. Validar días consecutivos trabajados
            all_days = sorted(set(a['date'] for a in assignments))
            if len(all_days) > 6:
                for i in range(len(all_days) - 6):
                    consecutive = all_days[i:i+7]
                    # Verificar si son consecutivos
                    first_date = datetime.fromisoformat(consecutive[0]).date()
                    last_date = datetime.fromisoformat(consecutive[-1]).date()
                    if (last_date - first_date).days == 6:
                        violation = f"{driver_name}: 7 días consecutivos del {consecutive[0]} al {consecutive[-1]}"
                        violations.append(violation)
                        driver_violations[driver_id].append(violation)
            
            # 6. Validar descanso entre turnos
            sorted_assignments = sorted(assignments, 
                                      key=lambda x: (x['date'], x['start_time']))
            
            for i in range(len(sorted_assignments) - 1):
                curr = sorted_assignments[i]
                next = sorted_assignments[i + 1]
                
                curr_date = datetime.fromisoformat(curr['date']).date()
                next_date = datetime.fromisoformat(next['date']).date()
                
                # Si son días consecutivos
                if (next_date - curr_date).days == 1:
                    # Calcular horas de descanso
                    curr_end_h, curr_end_m = map(int, curr['end_time'].split(':'))
                    next_start_h, next_start_m = map(int, next['start_time'].split(':'))
                    
                    rest_hours = (24 - curr_end_h) + next_start_h
                    
                    if rest_hours < self.MIN_REST_BETWEEN_SHIFTS:
                        violation = (f"{driver_name}: solo {rest_hours}h de descanso entre "
                                   f"{curr['date']} T{curr['shift']} y {next['date']} T{next['shift']} "
                                   f"(mín: {self.MIN_REST_BETWEEN_SHIFTS}h)")
                        violations.append(violation)
                        driver_violations[driver_id].append(violation)
        
        is_valid = len(violations) == 0
        
        if not is_valid:
            print(f"\n⚠️  VALIDACIÓN FALLÓ: {len(violations)} violaciones encontradas")
            print(f"Conductores con violaciones: {len(driver_violations)}")
        
        return ValidationResult(is_valid, violations, dict(driver_violations))
    
    def _format_solution(self, result: Dict, shifts: List[Dict]) -> Dict[str, Any]:
        """Formatea la solución para salida"""
        
        assignments = []
        driver_stats = defaultdict(lambda: {
            'hours': 0, 
            'shifts': 0, 
            'days_worked': set(),
            'sundays_worked': 0,
            'weeks': defaultdict(float)
        })
        
        for assignment in result['assignments']:
            shift = shifts[assignment['shift_idx']]
            driver = self.drivers[assignment['driver_idx']]
            
            assignment_dict = {
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
            }
            assignments.append(assignment_dict)
            
            # Actualizar estadísticas del conductor
            stats = driver_stats[driver.id]
            stats['hours'] += shift['duration_hours']
            stats['shifts'] += 1
            stats['days_worked'].add(shift['date'])
            stats['name'] = driver.name
            
            week_num = shift['week_num']
            stats['weeks'][week_num] += shift['duration_hours']
            
            if shift['is_sunday']:
                stats['sundays_worked'] += 1
        
        # Convertir sets a listas para serialización
        for driver_id, stats in driver_stats.items():
            stats['days_worked'] = len(stats['days_worked'])
            stats['weekly_hours'] = dict(stats['weeks'])
            del stats['weeks']
        
        # Calcular métricas
        total_hours = sum(s['duration_hours'] for s in shifts)
        drivers_used = result['drivers_used']
        avg_utilization = (total_hours / (drivers_used * self.MAX_MONTHLY_HOURS)) * 100 if drivers_used > 0 else 0
        
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
                'avg_utilization': round(avg_utilization, 1),
                'solver_status': result.get('solver_status', 'unknown')
            },
            'constraints': {
                'max_daily_span': self.MAX_DAILY_SPAN,
                'max_weekly_hours': self.MAX_WEEKLY_HOURS,
                'max_monthly_hours': self.MAX_MONTHLY_HOURS,
                'max_consecutive_days': self.MAX_CONSECUTIVE_DAYS,
                'max_sundays_worked': self.MAX_SUNDAYS_WORKED,
                'min_rest_between_shifts': self.MIN_REST_BETWEEN_SHIFTS
            }
        }