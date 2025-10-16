"""
Large Neighborhood Search (LNS) / Adaptive Large Neighborhood Search (ALNS)
para mejorar soluciones greedy de rostering.

Implementa operadores de destrucción y reparación para explorar vecindarios grandes
con Simulated Annealing para escapar de óptimos locales.

Basado en literatura de rostering moderno:
- LNS/ALNS en staff rostering (DIVA Portal, arXiv)
- Técnicas de destrucción/reparación orientadas a eliminar conductores
"""

import copy
import random
import math
import time
from typing import Dict, List, Any, Set, Tuple, Optional
from datetime import date, datetime, timedelta
from collections import defaultdict


class ConflictSetsBuilder:
    """Construye conjuntos de conflictos entre turnos para chequeos O(1)"""

    @staticmethod
    def build(all_shifts: List[Dict], min_rest_hours: float = 5.0) -> Dict[int, Set[int]]:
        """
        Construye conflict sets: para cada turno, lista de turnos incompatibles

        Dos turnos son incompatibles si:
        1. Mismo día y se solapan temporalmente
        2. Mismo día y hay < 5h de descanso entre turnos
        3. Días consecutivos y hay < 10h de descanso
        4. Juntos superan 14h en el mismo día

        Args:
            all_shifts: Lista de turnos con id, date, start_minutes, end_minutes, duration_hours
            min_rest_hours: Descanso mínimo entre turnos mismo día (default: 5h)

        Returns:
            Dict[shift_id] -> Set[shift_ids incompatibles]
        """
        conflict_sets = defaultdict(set)
        min_rest_minutes = min_rest_hours * 60

        for i, shift in enumerate(all_shifts):
            shift_id = shift.get('id', i)

            for j, other_shift in enumerate(all_shifts):
                if i == j:
                    continue

                other_id = other_shift.get('id', j)

                # Caso 1: Mismo día y se solapan
                if shift['date'] == other_shift['date']:
                    if ConflictSetsBuilder._shifts_overlap(shift, other_shift):
                        conflict_sets[shift_id].add(other_id)
                        continue

                    # Caso 1b: Juntos superan 14h en el día
                    total_hours = shift['duration_hours'] + other_shift['duration_hours']
                    if total_hours > 14.0:
                        conflict_sets[shift_id].add(other_id)
                        continue

                # Caso 2: Días consecutivos y descanso insuficiente
                days_diff = abs((shift['date'] - other_shift['date']).days)
                if days_diff == 1:
                    rest_minutes = ConflictSetsBuilder._rest_time_between(shift, other_shift)
                    if rest_minutes < min_rest_minutes:
                        conflict_sets[shift_id].add(other_id)

        return dict(conflict_sets)

    @staticmethod
    def _shifts_overlap(shift1: Dict, shift2: Dict) -> bool:
        """Verifica si dos turnos se solapan temporalmente"""
        start1 = shift1['start_minutes']
        end1 = shift1['end_minutes']
        start2 = shift2['start_minutes']
        end2 = shift2['end_minutes']

        # Normalizar si cruza medianoche
        if end1 < start1:
            end1 += 1440
        if end2 < start2:
            end2 += 1440

        # Check overlap
        return not (end1 <= start2 or end2 <= start1)

    @staticmethod
    def _rest_time_between(shift1: Dict, shift2: Dict) -> float:
        """Calcula minutos de descanso entre dos turnos"""
        # Determinar cuál es primero
        if shift1['date'] < shift2['date']:
            first, second = shift1, shift2
        elif shift2['date'] < shift1['date']:
            first, second = shift2, shift1
        else:
            # Mismo día: usar end_minutes
            if shift1['end_minutes'] <= shift2['start_minutes']:
                return shift2['start_minutes'] - shift1['end_minutes']
            else:
                return shift1['start_minutes'] - shift2['end_minutes']

        days_diff = (second['date'] - first['date']).days
        minutes_diff = (days_diff * 1440) + second['start_minutes'] - first['end_minutes']

        return minutes_diff


class DailyBitset:
    """Bitset para ocupación horaria diaria de un conductor"""

    def __init__(self):
        """Inicializa bitset de 1440 minutos (24h)"""
        self.minutes = [0] * 1440

    def add_shift(self, start_minutes: int, end_minutes: int):
        """Marca minutos ocupados por un turno"""
        # Normalizar minutos al rango 0-1439
        start_minutes = start_minutes % 1440
        end_minutes = end_minutes % 1440

        if end_minutes < start_minutes or end_minutes == 0:
            # Cruza medianoche
            for m in range(start_minutes, 1440):
                self.minutes[m] = 1
            if end_minutes > 0:
                for m in range(0, end_minutes):
                    self.minutes[m] = 1
        else:
            for m in range(start_minutes, end_minutes):
                self.minutes[m] = 1

    def can_fit(self, start_minutes: int, end_minutes: int, max_daily_hours: float = 14.0) -> bool:
        """
        Verifica si un turno cabe sin solaparse y sin exceder límite de SPAN de 14h consecutivas

        Args:
            start_minutes: Inicio del turno
            end_minutes: Fin del turno (puede ser > 1440 para turnos que cruzan medianoche)
            max_daily_hours: Máximo de horas CONSECUTIVAS (span, no suma) (default: 14h)

        Returns:
            True si cabe, False si se solapa o excede span
        """
        # Normalizar minutos al rango 0-1439
        start_minutes = start_minutes % 1440
        end_minutes = end_minutes % 1440

        # Check overlap
        if end_minutes < start_minutes or end_minutes == 0:
            # Cruza medianoche (o end_minutes fue 1440 y se normalizó a 0)
            if any(self.minutes[m] == 1 for m in range(start_minutes, 1440)):
                return False
            if end_minutes > 0 and any(self.minutes[m] == 1 for m in range(0, end_minutes)):
                return False
        else:
            if any(self.minutes[m] == 1 for m in range(start_minutes, end_minutes)):
                return False

        # Check 14h SPAN limit (tiempo desde primer turno hasta último turno)
        # Encontrar primer y último minuto trabajado incluyendo este nuevo turno
        occupied_minutes = [i for i, v in enumerate(self.minutes) if v == 1]

        if occupied_minutes:
            # Agregar minutos del nuevo turno
            if end_minutes < start_minutes:
                # Cruza medianoche
                new_minutes = list(range(start_minutes, 1440)) + list(range(0, end_minutes))
            else:
                new_minutes = list(range(start_minutes, end_minutes))

            all_minutes = occupied_minutes + new_minutes
            first_minute = min(all_minutes)
            last_minute = max(all_minutes)

            # Calcular span (manejar cruce de medianoche)
            if last_minute < first_minute:
                # Span cruza medianoche
                span = (1440 - first_minute) + last_minute
            else:
                span = last_minute - first_minute

            # Verificar límite de 14h (840 minutos)
            if span > max_daily_hours * 60:
                return False

        return True

    def get_total_hours(self) -> float:
        """Retorna total de horas ocupadas"""
        return sum(self.minutes) / 60.0


class LNS_ALNS_Optimizer:
    """
    Large Neighborhood Search / Adaptive Large Neighborhood Search
    para optimización de rostering con patrones NxN
    """

    def __init__(
        self,
        cycle: int = 10,
        min_rest_hours: float = 10.0,
        max_daily_hours: float = 14.0,
        seed: Optional[int] = None
    ):
        """
        Args:
            cycle: Longitud del ciclo NxN (7, 10, 14)
            min_rest_hours: Descanso mínimo entre turnos
            max_daily_hours: Máximo de horas diarias
            seed: Semilla para reproducibilidad
        """
        self.cycle = cycle
        self.min_rest_hours = min_rest_hours
        self.max_daily_hours = max_daily_hours
        self.conflict_sets = {}
        self.all_shifts = []

        if seed is not None:
            random.seed(seed)

    def optimize(
        self,
        initial_solution: Dict[str, Any],
        all_shifts: List[Dict],
        max_time: float = 600,
        temperature_init: float = 100.0,
        cooling_rate: float = 0.95,
        consolidate_every: int = 50
    ) -> Dict[str, Any]:
        """
        Optimiza solución inicial usando LNS/ALNS

        Args:
            initial_solution: Solución greedy inicial
            all_shifts: Lista completa de turnos
            max_time: Tiempo máximo en segundos
            temperature_init: Temperatura inicial SA
            cooling_rate: Tasa de enfriamiento (alpha)
            consolidate_every: Cada cuántas iteraciones intentar consolidar

        Returns:
            Mejor solución encontrada
        """
        print(f"\n{'='*80}")
        print(f"🔍 LNS/ALNS OPTIMIZATION - Patrón {self.cycle}x{self.cycle}")
        print(f"{'='*80}")

        start_time = time.time()

        # Precomputar conflict sets
        print("📊 Precomputando conflict sets...")
        self.all_shifts = all_shifts

        # Asignar IDs a turnos si no los tienen
        for i, shift in enumerate(all_shifts):
            if 'id' not in shift:
                shift['id'] = i

        self.conflict_sets = ConflictSetsBuilder.build(all_shifts, self.min_rest_hours)
        print(f"   ✓ {len(self.conflict_sets)} turnos, conflictos promedio: "
              f"{sum(len(c) for c in self.conflict_sets.values()) / max(len(self.conflict_sets), 1):.1f}")

        # Inicializar
        current = self._deep_copy_solution(initial_solution)
        best = self._deep_copy_solution(current)

        T = temperature_init
        iteration = 0
        iterations_without_improvement = 0

        # Estadísticas de operadores
        operator_stats = {
            'drop_driver': {'attempts': 0, 'accepts': 0, 'improvements': 0},
            'destroy_window': {'attempts': 0, 'accepts': 0, 'improvements': 0},
            'destroy_service': {'attempts': 0, 'accepts': 0, 'improvements': 0}
        }

        print(f"\n🚀 Iniciando búsqueda...")
        print(f"   Solución inicial: {self._count_drivers(current)} conductores")
        print(f"   Temperatura: {T:.1f}, Enfriamiento: {cooling_rate}")
        print(f"   Tiempo máximo: {max_time}s\n")

        while time.time() - start_time < max_time:
            iteration += 1

            # Seleccionar operador (ruleta)
            operator_name = self._select_operator(operator_stats)
            operator_stats[operator_name]['attempts'] += 1

            # Aplicar operador de destrucción + reparación
            try:
                neighbor = self._apply_operator(current, operator_name)
            except Exception as e:
                import traceback
                print(f"   ⚠️  Error en operador {operator_name}: {e}")
                if iteration < 5:  # Solo mostrar traceback en las primeras 5 iteraciones
                    traceback.print_exc()
                continue

            # Verificar factibilidad
            if not self._is_feasible(neighbor):
                continue

            # Evaluar
            current_cost = self._evaluate(current)
            neighbor_cost = self._evaluate(neighbor)
            delta = neighbor_cost - current_cost

            # Criterio de aceptación (Simulated Annealing)
            accept = False
            if delta < 0:
                # Mejora: siempre aceptar
                accept = True
                operator_stats[operator_name]['improvements'] += 1
            else:
                # Empeoramento: aceptar con probabilidad
                probability = math.exp(-delta / T)
                if random.random() < probability:
                    accept = True

            if accept:
                current = neighbor
                operator_stats[operator_name]['accepts'] += 1

                # Verificar si es nueva mejor solución
                if self._evaluate(current) < self._evaluate(best):
                    best = self._deep_copy_solution(current)
                    iterations_without_improvement = 0

                    drivers_count = self._count_drivers(best)
                    elapsed = time.time() - start_time
                    print(f"   ✨ Iteración {iteration} ({elapsed:.1f}s): "
                          f"{drivers_count} conductores (operador: {operator_name})")
                else:
                    iterations_without_improvement += 1

            # Enfriar
            T *= cooling_rate

            # Cada N iteraciones: intentar consolidar conductores
            if iteration % consolidate_every == 0:
                consolidated = self._try_consolidate(current)
                if self._evaluate(consolidated) < self._evaluate(current):
                    current = consolidated
                    print(f"   🔧 Iteración {iteration}: Consolidación exitosa")

            # Progreso cada 100 iteraciones
            if iteration % 100 == 0:
                elapsed = time.time() - start_time
                drivers = self._count_drivers(current)
                best_drivers = self._count_drivers(best)
                print(f"   · Iteración {iteration} ({elapsed:.0f}s): "
                      f"actual={drivers}, mejor={best_drivers}, T={T:.2f}")

            # Early stopping si no mejora por mucho tiempo
            if iterations_without_improvement > 500:
                print(f"\n   ⏸️  Early stopping: {iterations_without_improvement} iteraciones sin mejora")
                break

        # Limpieza final
        print(f"\n🧹 Limpieza final...")
        best = self._final_cleanup(best)

        # Resultados
        elapsed = time.time() - start_time
        initial_drivers = self._count_drivers(initial_solution)
        final_drivers = self._count_drivers(best)
        improvement = initial_drivers - final_drivers

        print(f"\n{'='*80}")
        print(f"✅ OPTIMIZACIÓN COMPLETADA")
        print(f"{'='*80}")
        print(f"Conductores iniciales: {initial_drivers}")
        print(f"Conductores finales:   {final_drivers}")
        print(f"Mejora:                {improvement} conductores ({improvement/initial_drivers*100:.1f}%)")
        print(f"Iteraciones:           {iteration}")
        print(f"Tiempo:                {elapsed:.1f}s")
        print(f"\nEstadísticas de operadores:")
        for op_name, stats in operator_stats.items():
            if stats['attempts'] > 0:
                accept_rate = stats['accepts'] / stats['attempts'] * 100
                improve_rate = stats['improvements'] / stats['attempts'] * 100
                print(f"  {op_name:20s}: {stats['attempts']:4d} intentos, "
                      f"{accept_rate:5.1f}% aceptados, {improve_rate:5.1f}% mejoras")
        print(f"{'='*80}\n")

        return best

    def _select_operator(self, stats: Dict) -> str:
        """Selecciona operador usando ruleta adaptativa"""
        # Pesos base
        weights = {
            'drop_driver': 0.3,
            'destroy_window': 0.4,
            'destroy_service': 0.3
        }

        # Ajustar pesos según tasa de éxito (ALNS adaptativo)
        for op_name in weights:
            if stats[op_name]['attempts'] > 10:
                success_rate = stats[op_name]['improvements'] / stats[op_name]['attempts']
                weights[op_name] *= (1.0 + success_rate)

        # Ruleta
        total = sum(weights.values())
        r = random.random() * total

        cumsum = 0
        for op_name, weight in weights.items():
            cumsum += weight
            if r <= cumsum:
                return op_name

        return 'drop_driver'  # Fallback

    def _apply_operator(self, solution: Dict, operator_name: str) -> Dict:
        """Aplica operador de destrucción + reparación"""
        neighbor = self._deep_copy_solution(solution)

        if operator_name == 'drop_driver':
            return self._drop_driver_operator(neighbor)
        elif operator_name == 'destroy_window':
            return self._destroy_window_operator(neighbor)
        elif operator_name == 'destroy_service':
            return self._destroy_service_operator(neighbor)
        else:
            raise ValueError(f"Operador desconocido: {operator_name}")

    def _drop_driver_operator(self, solution: Dict) -> Dict:
        """
        Operador Drop-Driver: Elimina conductor con menos carga y redistribuye turnos
        """
        # Identificar conductor con mínima carga
        drivers = solution.get('drivers', {})
        if not drivers:
            return solution

        # Calcular horas por conductor
        hours_by_driver = {}
        for driver_id, driver_data in drivers.items():
            total_hours = sum(
                assignment['shift']['duration_hours']
                for assignment in solution.get('assignments', [])
                if assignment['driver_id'] == driver_id
            )
            hours_by_driver[driver_id] = total_hours

        # Seleccionar conductor con mínima carga
        if not hours_by_driver:
            return solution

        min_driver_id = min(hours_by_driver, key=hours_by_driver.get)

        # Extraer turnos de este conductor
        shifts_to_reassign = [
            assignment['shift']
            for assignment in solution['assignments']
            if assignment['driver_id'] == min_driver_id
        ]

        # Eliminar conductor
        solution['assignments'] = [
            a for a in solution['assignments']
            if a['driver_id'] != min_driver_id
        ]

        if min_driver_id in drivers:
            del drivers[min_driver_id]

        # Reparar: intentar reasignar turnos
        for shift in shifts_to_reassign:
            self._repair_shift(solution, shift)

        return solution

    def _destroy_window_operator(self, solution: Dict, window_size: int = 3) -> Dict:
        """
        Operador Destroy-Window: Elimina asignaciones de una ventana de días
        """
        # Identificar fechas únicas
        dates = set()
        for assignment in solution['assignments']:
            dates.add(assignment['shift']['date'])

        if not dates:
            return solution  # No hay fechas, retornar sin cambios

        dates_list = sorted(dates)

        # Ajustar window_size si es necesario
        if len(dates_list) < window_size:
            window_size = max(1, len(dates_list))

        # Seleccionar ventana aleatoria (proteger contra índices inválidos)
        if len(dates_list) <= window_size:
            # Si hay muy pocas fechas, usar todas
            window_dates = set(dates_list)
        else:
            start_idx = random.randint(0, len(dates_list) - window_size)
            window_dates = set(dates_list[start_idx:start_idx + window_size])

        # Extraer turnos de la ventana
        shifts_to_reassign = []
        remaining_assignments = []

        for assignment in solution['assignments']:
            if assignment['shift']['date'] in window_dates:
                shifts_to_reassign.append(assignment['shift'])
            else:
                remaining_assignments.append(assignment)

        solution['assignments'] = remaining_assignments

        # Reparar
        for shift in shifts_to_reassign:
            self._repair_shift(solution, shift)

        return solution

    def _destroy_service_operator(self, solution: Dict) -> Dict:
        """
        Operador Destroy-Service: Elimina todas las asignaciones de un servicio
        """
        # Verificar que hay asignaciones
        if not solution.get('assignments'):
            return solution

        # Identificar servicios
        services = set()
        for assignment in solution['assignments']:
            service_id = assignment['shift'].get('service_id', 'default')
            if service_id:  # Solo agregar si no es None o vacío
                services.add(service_id)

        if not services:
            return solution

        # Seleccionar servicio aleatorio
        services_list = list(services)
        if not services_list:
            return solution

        target_service = random.choice(services_list)

        # Extraer turnos de ese servicio
        shifts_to_reassign = []
        remaining_assignments = []

        for assignment in solution['assignments']:
            if assignment['shift'].get('service_id', 'default') == target_service:
                shifts_to_reassign.append(assignment['shift'])
            else:
                remaining_assignments.append(assignment)

        solution['assignments'] = remaining_assignments

        # Reparar
        for shift in shifts_to_reassign:
            self._repair_shift(solution, shift)

        return solution

    def _repair_shift(self, solution: Dict, shift: Dict) -> bool:
        """
        Intenta reparar (reasignar) un turno a conductores existentes
        O crea nuevo conductor si no cabe

        Returns:
            True si se reasignó exitosamente
        """
        shift_id = shift.get('id')
        conflicts = self.conflict_sets.get(shift_id, set())

        # Intentar asignar a conductores existentes
        drivers = solution.get('drivers', {})

        for driver_id in list(drivers.keys()):
            # Check 1: Conductor disponible ese día según NxN
            if not self._is_driver_available(solution, driver_id, shift['date']):
                continue

            # Check 2: No tiene conflictos con turnos ya asignados
            driver_shift_ids = set(
                a['shift'].get('id')
                for a in solution['assignments']
                if a['driver_id'] == driver_id
            )

            if conflicts & driver_shift_ids:
                continue

            # Check 3: Cabe en 14h diarias usando bitset
            if not self._fits_in_daily_limit(solution, driver_id, shift):
                continue

            # Check 4: No cambia de grupo en el mismo día (CRÍTICO para Faena Minera)
            if not self._can_work_group_same_day(solution, driver_id, shift):
                continue

            # Asignar
            solution['assignments'].append({
                'driver_id': driver_id,
                'shift': shift,
                'date': shift['date']
            })
            return True

        # No cabía: crear nuevo conductor
        self._create_new_driver_for_shift(solution, shift)
        return False

    def _is_driver_available(self, solution: Dict, driver_id: str, date: date) -> bool:
        """Verifica si conductor está disponible ese día según patrón NxN"""
        drivers = solution.get('drivers', {})
        if driver_id not in drivers:
            return False

        driver_data = drivers[driver_id]
        work_start_date = driver_data.get('work_start_date')

        if not work_start_date:
            return True

        if isinstance(work_start_date, str):
            work_start_date = datetime.fromisoformat(work_start_date).date()

        days_since_start = (date - work_start_date).days
        day_in_cycle = days_since_start % (2 * self.cycle)

        # Trabaja los primeros N días del ciclo
        return day_in_cycle < self.cycle

    def _fits_in_daily_limit(self, solution: Dict, driver_id: str, shift: Dict) -> bool:
        """Verifica si turno cabe en límite de 14h diarias usando bitset"""
        # Construir bitset del día
        bitset = DailyBitset()

        for assignment in solution['assignments']:
            if assignment['driver_id'] == driver_id and assignment['shift']['date'] == shift['date']:
                assigned_shift = assignment['shift']
                bitset.add_shift(assigned_shift['start_minutes'], assigned_shift['end_minutes'])

        # Check si el nuevo turno cabe
        return bitset.can_fit(shift['start_minutes'], shift['end_minutes'], self.max_daily_hours)

    def _can_work_group_same_day(self, solution: Dict, driver_id: str, shift: Dict) -> bool:
        """
        Verifica si el conductor puede trabajar este turno sin cambiar de grupo el mismo día.

        RESTRICCIÓN CRÍTICA para Faena Minera:
        Un conductor NO puede cambiar de grupo en el mismo día porque los grupos están
        en ubicaciones geográficas diferentes y los tiempos de traslado lo hacen imposible.

        Returns:
            True si puede trabajar el turno (mismo grupo o sin conflicto)
            False si requeriría cambio de grupo
        """
        shift_group = shift.get('service_group')

        # Si el turno no tiene grupo asignado, permitir
        if not shift_group:
            return True

        # Verificar turnos ya asignados al conductor en la misma fecha
        for assignment in solution['assignments']:
            if assignment['driver_id'] == driver_id and assignment['shift']['date'] == shift['date']:
                assigned_group = assignment['shift'].get('service_group')

                # Si ya trabajó en un grupo diferente ese día, NO puede tomar este turno
                if assigned_group and assigned_group != shift_group:
                    return False

        # No hay conflicto de grupo
        return True

    def _create_new_driver_for_shift(self, solution: Dict, shift: Dict):
        """Crea nuevo conductor para un turno"""
        drivers = solution.get('drivers', {})

        # Generar nuevo ID
        existing_ids = [int(d_id.replace('D', '')) for d_id in drivers.keys() if isinstance(d_id, str) and d_id.startswith('D')]
        new_id = max(existing_ids, default=0) + 1
        driver_id = f'D{new_id:03d}'

        # Calcular offset para que trabaje HOY
        # (Esto es simplificado, en producción usar lógica más robusta)
        drivers[driver_id] = {
            'pattern': f'{self.cycle}x{self.cycle}',
            'cycle': self.cycle,
            'work_start_date': shift['date']
        }

        solution['assignments'].append({
            'driver_id': driver_id,
            'shift': shift,
            'date': shift['date']
        })

    def _try_consolidate(self, solution: Dict) -> Dict:
        """Intenta consolidar conductores eliminando los de baja carga"""
        # Esto es una versión simplificada de drop_driver repetido
        return self._drop_driver_operator(self._deep_copy_solution(solution))

    def _final_cleanup(self, solution: Dict) -> Dict:
        """Limpieza final: swaps y eliminación glotona"""
        # Por ahora, solo retornar la solución
        # TODO: Implementar swaps 1-1 y relocates
        return solution

    def _is_feasible(self, solution: Dict) -> bool:
        """Verifica si solución es factible (cobertura 100%)"""
        covered_shifts = set()
        for assignment in solution['assignments']:
            shift_id = assignment['shift'].get('id')
            if shift_id is not None:
                covered_shifts.add(shift_id)

        total_shifts = len(self.all_shifts)
        return len(covered_shifts) == total_shifts

    def _evaluate(self, solution: Dict) -> float:
        """
        Función de evaluación (menor = mejor)

        Objetivo primario: Minimizar conductores
        Objetivo secundario: Minimizar costo total
        """
        num_drivers = self._count_drivers(solution)
        total_shifts = len(solution.get('assignments', []))

        # Penalizar fuertemente si no hay cobertura completa
        if not self._is_feasible(solution):
            return num_drivers * 1000000

        # Costo: salarios + bonos
        cost = (num_drivers * 800000) + (total_shifts * 5000)

        return cost

    def _count_drivers(self, solution: Dict) -> int:
        """Cuenta conductores únicos en la solución"""
        drivers = set()
        for assignment in solution['assignments']:
            drivers.add(assignment['driver_id'])
        return len(drivers)

    def _deep_copy_solution(self, solution: Dict) -> Dict:
        """Crea copia profunda de la solución"""
        return copy.deepcopy(solution)


# Fin del módulo
