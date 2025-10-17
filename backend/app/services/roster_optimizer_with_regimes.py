"""
Optimizador de turnos con regímenes laborales diferenciados
Aplica restricciones específicas según el tipo de servicio:
- Interurbano (Art. 25): Máx 5h conducción continua, 180h/mes conducción
- Urbano/Industrial: Sin límite conducción continua, 44h/semana trabajo
- Interurbano Bisemanal (Art. 39): Ciclos especiales 4x3, 7x7, etc.
- Faena Minera (Art. 38): Turnos excepcionales 7x7, 14x14, etc.
"""

from ortools.sat.python import cp_model
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, date, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
import time
import calendar

# Importar LNS/ALNS solo para Faena Minera (opcional)
try:
    from app.services.lns_alns_optimizer import LNS_ALNS_Optimizer
    HAS_LNS_ALNS = True
except ImportError:
    HAS_LNS_ALNS = False


@dataclass
class LaborRegime:
    """Define las restricciones de un régimen laboral"""
    name: str
    max_continuous_driving_hours: Optional[float] = None  # None = sin límite
    required_rest_after_driving: Optional[float] = None  # Horas de descanso después de conducción continua
    max_daily_hours: float = 10.0  # Máximo de horas diarias
    max_weekly_hours: float = 44.0  # Máximo de horas semanales
    max_monthly_hours: float = 180.0  # Máximo de horas mensuales (conducción o trabajo)
    min_rest_between_shifts: float = 10.0  # Descanso mínimo entre jornadas
    max_consecutive_days: int = 6  # Días consecutivos máximos
    min_free_sundays: int = 2  # Domingos libres mínimos al mes
    max_working_day_span: float = 12.0  # Máximo span de jornada diaria
    special_cycles: List[Tuple[int, int]] = field(default_factory=list)  # Ciclos especiales (trabajo, descanso)
    allows_split_shift: bool = True  # Permite turno partido
    
    @classmethod
    def interurbano_art25(cls):
        """Régimen Interurbano Art. 25 - Más restrictivo"""
        return cls(
            name="Interurbano (Art. 25)",
            max_continuous_driving_hours=5.0,
            required_rest_after_driving=2.0,
            max_daily_hours=16.0,  # Con descansos proporcionales
            max_weekly_hours=None,  # Se rige por mensual
            max_monthly_hours=180.0,  # Horas de CONDUCCIÓN
            min_rest_between_shifts=8.0,
            max_consecutive_days=6,
            min_free_sundays=2,
            max_working_day_span=16.0,
            special_cycles=[(9, 5), (10, 4)],  # Ciclos autorizados
            allows_split_shift=True
        )
    
    @classmethod
    def urbano_industrial(cls):
        """Régimen Urbano/Industrial - Jornada ordinaria"""
        return cls(
            name="Urbano/Industrial",
            max_continuous_driving_hours=None,  # Sin restricción específica
            required_rest_after_driving=None,
            max_daily_hours=10.0,
            max_weekly_hours=44.0,  # 40h desde 2028
            max_monthly_hours=None,  # Se rige por semanal
            min_rest_between_shifts=10.0,
            max_consecutive_days=6,  # 5-6 días
            min_free_sundays=2,
            max_working_day_span=12.0,
            special_cycles=[],
            allows_split_shift=True
        )
    
    @classmethod
    def interurbano_bisemanal(cls):
        """Régimen Interurbano Bisemanal Art. 39"""
        return cls(
            name="Interurbano Bisemanal (Art. 39)",
            max_continuous_driving_hours=None,
            required_rest_after_driving=None,
            max_daily_hours=14.0,  # Con turno cortado
            max_weekly_hours=44.0,  # Promedio en el ciclo
            max_monthly_hours=None,
            min_rest_between_shifts=10.0,
            max_consecutive_days=14,  # Depende del ciclo
            min_free_sundays=None,  # Según ciclo
            max_working_day_span=14.0,
            special_cycles=[(4, 3), (7, 7), (14, 14), (10, 5)],
            allows_split_shift=True
        )
    
    @classmethod
    def faena_minera(cls):
        """Régimen Faena Minera Art. 38

        Características:
        - Ciclos NxN (7x7, 8x8, 10x10, 14x14)
        - Trabajo: 12h diarias por N días consecutivos
        - Descanso: N días consecutivos completos
        - Sin límite semanal estricto

        Ejemplos de promedio:
        - 7x7: 7 días × 12h = 84h / 2 semanas = 42h/semana
        - 8x8: 8 días × 12h = 96h / 16 días = 42h/semana
        - 10x10: 10 días × 12h = 120h / 20 días = 42h/semana
        - 14x14: 14 días × 12h = 168h / 4 semanas = 42h/semana
        """
        return cls(
            name="Faena Minera (Art. 38)",
            max_continuous_driving_hours=None,
            required_rest_after_driving=None,
            max_daily_hours=14.0,  # Hasta 14h diarias (típicamente 12h)
            max_weekly_hours=None,  # NO aplica límite semanal estricto
            max_monthly_hours=None,  # Se controla por ciclos NxN
            min_rest_between_shifts=10.0,
            max_consecutive_days=14,  # Máximo ciclo 14x14
            min_free_sundays=None,  # Puede incluir domingos con autorización
            max_working_day_span=14.0,
            special_cycles=[(7, 7), (8, 8), (10, 10), (14, 14)],
            allows_split_shift=True
        )


class RosterOptimizerWithRegimes:
    """
    Optimizador que aplica restricciones diferenciadas según el régimen laboral
    """

    BASE_HOURLY_RATE = 10000
    
    def __init__(self, client_data: Dict[str, Any]):
        self.client_data = client_data
        self.services = client_data['services']
        self.costs = client_data.get('costs', {})
        self.parameters = client_data.get('parameters', {})
        self.vehicle_cache: Dict[str, Dict[str, str]] = {}
        
        # Detectar régimen único del cliente
        self.regime = self._detect_regime()
        self.regime_constraints = self._setup_regime_constraints()

        self.start_time = None
        # Timeout ajustado según régimen
        # Minera: 15 min, Urbano/Industrial: 10 min (permite búsqueda CP-SAT exhaustiva)
        self.timeout = 900.0 if self.regime in ['Faena Minera', 'Minera'] else 600.0  # 15 min minera, 10 min otros

    def _infer_vehicle_metadata(self, service: Dict[str, Any]) -> Dict[str, str]:
        service_id = service.get('id') or service.get('service_id')
        if service_id and service_id in self.vehicle_cache:
            return self.vehicle_cache[service_id]

        vehicle_info = service.get('vehicles', {}) if isinstance(service.get('vehicles', {}), dict) else {}
        raw_type = (vehicle_info.get('type') or '').lower() if vehicle_info else ''
        service_type = (service.get('service_type') or '').lower()

        normalized = raw_type or service_type
        category = 'minibus'  # Default más común

        # Detectar tipo específico (orden importa - más específico primero)
        if '4x4' in normalized and 'taxi' in normalized:
            category = 'taxibus_4x4'
        elif '2' in normalized and 'piso' in normalized:
            category = 'bus_2piso'
        elif 'electric' in normalized or 'eléctric' in normalized:
            category = 'bus_electrico'
        elif 'taxi' in normalized:
            category = 'taxibus'
        elif 'mini' in normalized or 'van' in normalized:
            category = 'minibus'
        elif 'bus' in normalized:
            category = 'bus'

        metadata = {
            'vehicle_type': raw_type or service_type or 'unknown',
            'vehicle_category': category
        }

        if service_id:
            self.vehicle_cache[service_id] = metadata

        return metadata

    def _vehicle_penalty(self, vehicle_category: Optional[str]) -> float:
        """
        Retorna el factor de recargo por tipo de vehículo según recargos_tipovehiculo.md
        El recargo se aplica sobre el salario base del conductor
        """
        category = (vehicle_category or 'minibus').lower()

        # Factores de recargo según tipo de vehículo
        recargos = {
            'taxibus_4x4': 0.40,      # 40% recargo (factor 1.40)
            'bus_2piso': 0.30,        # 30% recargo (factor 1.30)
            'bus': 0.25,              # 25% recargo (factor 1.25)
            'bus_electrico': 0.20,    # 20% recargo (factor 1.20)
            'taxibus': 0.10,          # 10% recargo (factor 1.10)
            'minibus': 0.00,          # 0% recargo (factor 1.00 - base)
        }

        return recargos.get(category, 0.0)

    def _driver_type_multiplier(self, vehicle_categories: Set[str]) -> float:
        """
        Calcula el multiplicador del conductor según el vehículo MÁS COMPLEJO que maneja en el mes

        Ejemplo:
        - Si conduce 1 turno en Taxibus 4x4 (40%) y 29 turnos en Minibus (0%)
        - TODO su salario del mes se paga con recargo del 40%

        Esto refleja que necesita certificación/licencia para el vehículo más complejo
        """
        categories = {c for c in vehicle_categories if c}
        if not categories:
            return 1.0

        # Encontrar el recargo MÁXIMO entre todos los vehículos que maneja
        max_recargo = max(self._vehicle_penalty(cat) for cat in categories)

        # El multiplicador es 1 + recargo máximo
        return 1.0 + max_recargo

    def _compute_driver_cost(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        total_hours = stats.get('total_hours', 0)
        if total_hours <= 0:
            return {
                'base_cost': 0.0,
                'vehicle_adjusted_cost': 0.0,
                'driver_multiplier': 1.0,
                'service_multiplier': 1.0,
                'total_cost': 0.0,
                'service_count': 0
            }

        base_rate = self.BASE_HOURLY_RATE

        # Costo base por horas trabajadas (sin recargos)
        base_cost = total_hours * base_rate

        # Multiplicador por tipo de vehículo MÁS COMPLEJO que maneja
        driver_multiplier = self._driver_type_multiplier(stats.get('vehicle_categories', set()))

        # Multiplicador por múltiples servicios
        service_count = len(stats.get('services', set()))
        service_multiplier = 1.0 + 0.20 * max(0, service_count - 1)

        # Costo total: base × recargo_vehiculo × recargo_servicios
        total_cost = base_cost * driver_multiplier * service_multiplier

        return {
            'base_cost': base_cost,
            'vehicle_adjusted_cost': base_cost * driver_multiplier,
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

    def _detect_service_span_warnings(self, shifts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
    
    def _detect_regime(self) -> str:
        """Detecta el régimen único del cliente (no hay mezclas)"""
        # Tomar el tipo del primer servicio - todos deben ser iguales
        if self.services:
            regime = self.services[0].get('service_type', 'Industrial')
            # Normalizar: Urbano e Industrial son equivalentes
            if regime == 'Urbano':
                regime = 'Industrial'
            
            # Verificar consistencia (todos los servicios deben tener el mismo tipo)
            for service in self.services[1:]:
                service_type = service.get('service_type', 'Industrial')
                if service_type == 'Urbano':
                    service_type = 'Industrial'
                if service_type != regime:
                    print(f"⚠️ ADVERTENCIA: Servicio con tipo diferente detectado: {service_type} vs {regime}")
            
            return regime
        return 'Industrial'  # Default
    
    def _setup_regime_constraints(self) -> LaborRegime:
        """Configura las restricciones para el régimen único del cliente"""
        if self.regime == 'Interurbano':
            return LaborRegime.interurbano_art25()
        elif self.regime in ['Industrial', 'Urbano', 'Interno']:
            return LaborRegime.urbano_industrial()
        elif self.regime == 'Interurbano Bisemanal':
            return LaborRegime.interurbano_bisemanal()
        elif self.regime in ['Minera', 'Faena Minera']:
            return LaborRegime.faena_minera()
        else:
            # Por defecto usar urbano/industrial
            print(f"⚠️ Régimen desconocido: {self.regime}, usando Industrial por defecto")
            return LaborRegime.urbano_industrial()
    
    def optimize_month(self, year: int, month: int) -> Dict[str, Any]:
        """
        Optimiza el mes aplicando restricciones diferenciadas por régimen
        """
        self.start_time = time.time()
        
        print(f"\n=== OPTIMIZACIÓN CON REGÍMENES LABORALES {year}-{month:02d} ===")

        # Mostrar régimen detectado
        print(f"Régimen laboral: {self.regime}")
        print(f"Timeout máximo: {self.timeout}s ({self.timeout/60:.1f} minutos)")

        constraints = self.regime_constraints
        print(f"\nRestricciones aplicables:")
        if constraints.max_continuous_driving_hours:
            print(f"  - Máx conducción continua: {constraints.max_continuous_driving_hours}h")
        print(f"  - Máx horas diarias: {constraints.max_daily_hours}h")
        if constraints.max_weekly_hours:
            print(f"  - Máx horas semanales: {constraints.max_weekly_hours}h")
        if constraints.max_monthly_hours:
            print(f"  - Máx horas mensuales: {constraints.max_monthly_hours}h")
        print(f"  - Descanso entre jornadas: {constraints.min_rest_between_shifts}h")
        print(f"  - Días consecutivos máx: {constraints.max_consecutive_days}")
        print(f"  - Domingos libres mín: {constraints.min_free_sundays}")
        if constraints.special_cycles:
            print(f"  - Ciclos especiales: {', '.join([f'{w}x{r}' for w, r in constraints.special_cycles])}")
        
        # Generar todos los turnos del mes
        all_shifts = self._generate_month_shifts(year, month)
        print(f"\nTotal turnos a asignar: {len(all_shifts)}")
        
        # Todos los turnos tienen el mismo régimen
        print(f"  - Todos con régimen {self.regime}")
        
        # Calcular número mínimo de conductores
        min_drivers = self._calculate_minimum_drivers(all_shifts)

        # Para Faena Minera, el cálculo es muy diferente por los ciclos NxN
        if self.regime in ['Faena Minera', 'Minera']:
            print(f"\n📊 ANÁLISIS INTELIGENTE - FAENA MINERA")
            print(f"{'='*80}\n")

            # PASO 1: Análisis de turnos y días
            total_shifts = len(all_shifts)
            shifts_by_date = {}
            for shift in all_shifts:
                date = shift['date']
                if date not in shifts_by_date:
                    shifts_by_date[date] = []
                shifts_by_date[date].append(shift)

            num_days = len(shifts_by_date)
            avg_shifts_per_day = total_shifts / num_days

            print(f"1️⃣  Análisis de Turnos:")
            print(f"    Total turnos: {total_shifts}")
            print(f"    Días en el mes: {num_days}")
            print(f"    Promedio turnos/día: {avg_shifts_per_day:.1f}")

            # PASO 2: Análisis de grupos de servicio
            service_groups = {}
            for shift in all_shifts:
                group = shift.get('service_group', shift.get('service_name', 'Sin grupo'))
                if group not in service_groups:
                    service_groups[group] = {'shifts': 0, 'dates': set()}
                service_groups[group]['shifts'] += 1
                service_groups[group]['dates'].add(shift['date'])

            print(f"\n2️⃣  Análisis de Grupos de Servicio:")
            print(f"    Total grupos: {len(service_groups)}")
            for group, data in sorted(service_groups.items(), key=lambda x: x[1]['shifts'], reverse=True):
                days_worked = len(data['dates'])
                shifts_count = data['shifts']
                print(f"    - {group}: {shifts_count} turnos en {days_worked} días")

            # PASO 3: Calcular HORAS TOTALES de trabajo
            total_hours = 0
            hours_by_date = {}

            for date, shifts in shifts_by_date.items():
                daily_hours = 0
                earliest_start = None
                latest_end = None

                for shift in shifts:
                    # Sumar horas de cada turno
                    duration = shift['duration_hours']
                    total_hours += duration
                    daily_hours += duration

                    # Calcular span diario (primera hora inicio - última hora fin)
                    start_mins = shift['start_minutes']
                    end_mins = shift['end_minutes']

                    if earliest_start is None or start_mins < earliest_start:
                        earliest_start = start_mins
                    if latest_end is None or end_mins > latest_end:
                        latest_end = end_mins

                # Span diario (puede ser > 24h si cruza medianoche)
                if earliest_start is not None and latest_end is not None:
                    if latest_end < earliest_start:
                        # Cruza medianoche
                        span_hours = (1440 - earliest_start + latest_end) / 60
                    else:
                        span_hours = (latest_end - earliest_start) / 60

                    hours_by_date[date] = {
                        'total_hours': daily_hours,
                        'span_hours': span_hours,
                        'num_shifts': len(shifts)
                    }

            avg_hours_per_day = total_hours / num_days
            max_daily_hours = max(h['total_hours'] for h in hours_by_date.values())
            max_daily_span = max(h['span_hours'] for h in hours_by_date.values())

            print(f"\n3️⃣  Análisis de Horas:")
            print(f"    Total horas mes: {total_hours:.1f}h")
            print(f"    Promedio horas/día: {avg_hours_per_day:.1f}h")
            print(f"    Máximo horas en un día: {max_daily_hours:.1f}h")
            print(f"    Máximo span diario: {max_daily_span:.1f}h (primera-última hora)")

            # Detectar si supera 12h o 14h diarias
            days_over_12h = sum(1 for h in hours_by_date.values() if h['total_hours'] > 12)
            days_over_14h = sum(1 for h in hours_by_date.values() if h['total_hours'] > 14)

            if days_over_14h > 0:
                print(f"    ⚠️  {days_over_14h} días superan 14h (límite legal)")
            elif days_over_12h > 0:
                print(f"    ⚠️  {days_over_12h} días superan 12h")

            # PASO 4: ESTIMACIÓN INTELIGENTE basada en horas
            print(f"\n4️⃣  Estimación de Conductores Mínimos:")

            # Opción A: Por ciclo 7x7 (84h en 7 días = 12h/día promedio)
            # Cada conductor puede trabajar 84h en 7 días, luego descansa 7
            # En un mes de 28 días, trabaja 14 días = 168h máximo
            hours_per_driver_7x7 = 14 * 12  # 168h por conductor/mes (ciclo 7x7)
            estimate_7x7 = int(total_hours / hours_per_driver_7x7) + 1

            # Opción B: Por ciclo 10x10 (120h en 10 días = 12h/día promedio)
            # En un mes de 30 días, trabaja 15 días = 180h máximo
            hours_per_driver_10x10 = 15 * 12  # 180h por conductor/mes (ciclo 10x10)
            estimate_10x10 = int(total_hours / hours_per_driver_10x10) + 1

            # Opción C: Por ciclo 14x14 (168h en 14 días = 12h/día promedio)
            # En un mes de 28 días, trabaja 14 días = 168h máximo
            hours_per_driver_14x14 = 14 * 12  # 168h por conductor/mes (ciclo 14x14)
            estimate_14x14 = int(total_hours / hours_per_driver_14x14) + 1

            print(f"    Ciclo 7x7:   {estimate_7x7} conductores ({total_hours:.0f}h / {hours_per_driver_7x7}h)")
            print(f"    Ciclo 10x10: {estimate_10x10} conductores ({total_hours:.0f}h / {hours_per_driver_10x10}h)")
            print(f"    Ciclo 14x14: {estimate_14x14} conductores ({total_hours:.0f}h / {hours_per_driver_14x14}h)")

            # Opción D: Por turnos simultáneos (necesario para cobertura)
            max_simultaneous = self._calculate_max_simultaneous(all_shifts)
            estimate_by_simultaneous = int(max_simultaneous * 2.2)  # Factor 2.2 por ciclos
            print(f"    Simultáneos: {estimate_by_simultaneous} conductores ({max_simultaneous} × 2.2)")

            # SELECCIONAR EL MAYOR (más restrictivo)
            min_drivers = max(estimate_7x7, estimate_10x10, estimate_14x14, estimate_by_simultaneous)

            print(f"\n    ✓ MÍNIMO ESTIMADO: {min_drivers} conductores")
            print(f"      (Usando el más restrictivo entre horas y simultáneos)")

            # MÁXIMO: 3x el mínimo pero nunca menos de 150
            max_drivers = max(150, int(min_drivers * 3))

            print(f"    ✓ MÁXIMO BÚSQUEDA: {max_drivers} conductores")
            print(f"      (3x mínimo para garantizar factibilidad)")

            print(f"\n{'='*80}")
        elif self.regime == 'Interurbano':
            # Comenzar con un número más realista basado en el análisis
            min_drivers = max(min_drivers, 15)  # Mínimo 15 para Molynor
            max_drivers = min(50, min_drivers * 2)  # Máximo 50 o 2x el mínimo
        else:
            max_drivers = max(100, min_drivers * 3)  # Para otros regímenes

        print(f"\nRango de búsqueda: {min_drivers} a {max_drivers} conductores")

        best_solution = None

        # ESTRATEGIA DE BÚSQUEDA:
        # - Faena Minera: búsqueda binaria (converge más rápido en rangos grandes)
        # - Otros regímenes: búsqueda lineal (más estable, encuentra óptimo garantizado)

        if self.regime in ['Faena Minera', 'Minera']:
            # FASE 1: CONSTRUCCIÓN GREEDY - Solo patrón 7x7 (simplificado)
            print(f"\n{'='*80}")
            print(f"FASE 1: CONSTRUCCIÓN GREEDY")
            print(f"Usando patrón 7x7 (7 días trabajo, 7 días descanso)...")
            print(f"  Razón: Turnos homogéneos, no hay ventaja en combinar patrones")
            print(f"{'='*80}")

            # Solo usar 7x7 para Faena Minera
            cycle = 7
            best_greedy = self._greedy_assignment_single_pattern(all_shifts, cycle)
            best_cycle = cycle

            print(f"\n  ✓ SOLUCIÓN GREEDY: {cycle}x{cycle} con {best_greedy['num_drivers']} conductores, cobertura {best_greedy['coverage']*100:.1f}%")

            # ESTRATEGIA DE OPTIMIZACIÓN:
            # 1. Greedy constructivo (Fase 1) - COMPLETADO
            # 2. LNS/ALNS (Fase 2) - Mejorar greedy con búsqueda de vecindad grande
            # 3. CP-SAT (Fase 3) - Solo si LNS no es suficiente (no converge actualmente)

            USE_LNS_ALNS = True  # HABILITADO: Optimizar solución greedy
            USE_CPSAT_OPTIMIZATION = False  # CP-SAT no converge para este problema

            # FASE 2: LNS/ALNS OPTIMIZATION
            if USE_LNS_ALNS and HAS_LNS_ALNS:
                try:
                    print(f"\n{'='*80}")
                    print(f"FASE 2: OPTIMIZACIÓN LNS/ALNS")
                    print(f"Mejorando solución greedy con Large Neighborhood Search...")
                    print(f"{'='*80}")

                    # Crear optimizador LNS/ALNS
                    lns_optimizer = LNS_ALNS_Optimizer(
                        cycle=best_cycle,
                        min_rest_hours=5.0,  # 5h descanso entre turnos mismo día
                        max_daily_hours=14.0
                    )

                    # Optimizar solución greedy
                    # Tiempo: 10-12 minutos (deja margen para replicación anual)
                    lns_solution = lns_optimizer.optimize(
                        initial_solution=best_greedy,
                        all_shifts=all_shifts,
                        max_time=600,  # 10 minutos
                        temperature_init=100.0,
                        cooling_rate=0.95,
                        consolidate_every=50
                    )

                    # Si LNS mejoró, usar esa solución
                    if lns_solution['num_drivers'] < best_greedy['num_drivers']:
                        print(f"\n✨ LNS/ALNS MEJORÓ la solución:")
                        print(f"   Greedy: {best_greedy['num_drivers']} conductores")
                        print(f"   LNS:    {lns_solution['num_drivers']} conductores")
                        print(f"   Mejora: {best_greedy['num_drivers'] - lns_solution['num_drivers']} conductores")
                        best_greedy = lns_solution
                        best_cycle = lns_solution['cycle']
                    else:
                        print(f"\n⚠️  LNS/ALNS no logró mejorar (greedy ya es muy bueno)")
                        print(f"   Solución final: {best_greedy['num_drivers']} conductores")
                except Exception as e:
                    print(f"\n⚠️  Error en LNS/ALNS: {e}")
                    print(f"   Continuando con solución greedy...")
            elif USE_LNS_ALNS and not HAS_LNS_ALNS:
                print(f"\n⚠️  LNS/ALNS no disponible (módulo no encontrado)")
                print(f"   Continuando con solución greedy...")

            if USE_CPSAT_OPTIMIZATION:
                print(f"\n{'='*80}")
                print(f"FASE 2: OPTIMIZACIÓN CP-SAT (Partiendo de solución greedy)")
                print(f"Iniciando desde {best_greedy['num_drivers']} conductores...")
                print(f"{'='*80}")

                # Usar la solución greedy como punto de partida para el rango
                # Intentar MEJORAR la solución greedy (menos conductores)
                greedy_num = best_greedy['num_drivers']
                min_drivers = max(int(greedy_num * 0.7), greedy_num - 5)  # 70% del greedy o -5
                max_drivers = greedy_num + 5  # Permitir un poco más por si necesita flexibilidad

                print(f"\nRango ajustado: {min_drivers} a {max_drivers} conductores")

                # Crear patrones híbridos para el máximo número de conductores
                # Los reutilizaremos tomando subconjuntos según el num_drivers actual
                max_patterns = self._create_hybrid_patterns(max_drivers, all_shifts)

                left = min_drivers
                right = max_drivers
                iteration = 0
                first_feasible = None  # Guardar la primera solución factible
                best_solution = None

                while left <= right:
                    iteration += 1

                    # Verificar timeout
                    if time.time() - self.start_time > self.timeout:
                        print(f"⚠️ Timeout alcanzado después de {self.timeout}s")
                        break

                    # EARLY STOPPING: Si encontramos factible y estamos dentro de 10% del mínimo, parar
                    if first_feasible and (right - left) <= max(3, int(min_drivers * 0.1)):
                        print(f"\n✓ Early stopping: Rango suficientemente estrecho ({right - left + 1} conductores)")
                        print(f"  Mejor solución encontrada usa {best_solution['metrics']['drivers_used']} conductores")
                        break

                    # Probar con el punto medio
                    num_drivers = (left + right) // 2

                    print(f"\n{'='*80}")
                    print(f"ITERACIÓN {iteration}: Probando con {num_drivers} conductores")
                    print(f"  Rango actual: [{left}, {right}]")
                    print(f"  Rango restante: {right - left + 1} opciones")
                    if first_feasible:
                        print(f"  Primera solución factible encontrada en: {first_feasible} conductores")
                    print(f"{'='*80}")

                    # Tomar solo los patrones necesarios para este intento
                    active_patterns = {d_idx: max_patterns[d_idx] for d_idx in range(num_drivers)}

                    result = self._solve_with_cpsat(all_shifts, num_drivers, year, month,
                                                   min_drivers, driver_patterns=active_patterns)

                    if result['status'] == 'success':
                        actual_used = result['metrics']['drivers_used']
                        print(f"\n{'🎉'*20}")
                        print(f"✓ FACTIBLE con {num_drivers} conductores disponibles")
                        print(f"  Conductores realmente usados: {actual_used}")
                        print(f"  Asignaciones creadas: {len(result['assignments'])}")
                        print(f"{'🎉'*20}\n")

                        best_solution = result

                        # Guardar primera solución factible
                        if first_feasible is None:
                            first_feasible = num_drivers
                            print(f"  💡 Esta es la PRIMERA solución factible!")
                            print(f"  → Ahora buscaremos optimizar reduciendo conductores\n")

                        # Buscar con menos conductores (optimizar)
                        print(f"  → Siguiente paso: Intentar con MENOS conductores (buscar en [{left}, {num_drivers-1}])")
                        right = num_drivers - 1
                    else:
                        print(f"\n{'❌'*20}")
                        print(f"✗ NO FACTIBLE con {num_drivers} conductores")
                        print(f"  Razón: {result.get('message', 'Solver no encontró solución')}")
                        print(f"{'❌'*20}\n")
                        print(f"  → Siguiente paso: Intentar con MÁS conductores (buscar en [{num_drivers+1}, {right}])\n")

                        # Necesitamos más conductores
                        left = num_drivers + 1
            else:
                # NO usar CP-SAT: Convertir solución greedy al formato esperado
                print(f"\n{'='*80}")
                print(f"USANDO SOLUCIÓN GREEDY DIRECTAMENTE (sin CP-SAT)")
                print(f"Conversión al formato estándar...")
                print(f"{'='*80}\n")

                best_solution = self._convert_greedy_to_standard(best_greedy, year, month)

        else:
            # Para regímenes no mineros, usar estrategia similar a Faena Minera:
            # 1. Greedy para solución inicial rápida
            # 2. LNS/ALNS para optimizar (opcional)

            print(f"\n{'='*80}")
            print(f"FASE 1: CONSTRUCCIÓN GREEDY PARA RÉGIMEN {self.regime.upper()}")
            print(f"Construyendo solución inicial sin ciclos fijos...")
            print(f"{'='*80}")

            # Usar greedy simple: asignar día por día sin patrón fijo
            # Este greedy respeta: 44h semanales, 10h diarias, 10h descanso, 6 días consecutivos máx
            greedy_result = self._greedy_assignment_no_cycles(all_shifts, year, month)

            if greedy_result['status'] == 'success':
                print(f"\n  ✓ SOLUCIÓN GREEDY: {greedy_result['num_drivers']} conductores, cobertura {greedy_result['coverage']*100:.1f}%")
                best_solution = greedy_result

                # FASE 2: OPTIMIZACIÓN CP-SAT
                # Todos los regímenes NO mineros usan el mismo sistema CP-SAT


                # FASE 2: OPTIMIZACIÓN CP-SAT (habilitado según instrucción "SI O SI CP-SAT")
                print(f"\n{'='*80}")
                print(f"FASE 2: OPTIMIZACIÓN CP-SAT DESDE SOLUCIÓN GREEDY")
                print(f"{'='*80}")
                print(f"  Objetivo: Mejorar desde {greedy_result['num_drivers']} conductores (greedy)")

                # Estrategia: Búsqueda agresiva descendente con timeout generoso
                greedy_drivers = greedy_result['num_drivers']

                # ESTRATEGIA: Probar hasta 50% menos que greedy
                # Timeout total: 600s (10 minutos) permite exploración exhaustiva
                min_drivers_target = max(1, int(greedy_drivers * 0.5))  # Hasta 50% menos

                # Todos los regímenes no mineros usan la misma estrategia
                initial_drivers = greedy_drivers - 1

                print(f"  Rango objetivo: {min_drivers_target} a {initial_drivers} conductores")
                print(f"  Estrategia: Búsqueda descendente desde greedy-1 con timeout 60s por intento")
                print(f"  Tiempo máximo total: {int(self.timeout)}s (~{int(self.timeout/60)} minutos)\n")

                best_cp_solution = None
                attempt = 0
                max_attempts = 15  # Hasta 15 intentos
                consecutive_feasible_count = 0  # Contador de FEASIBLE consecutivos sin OPTIMAL
                max_consecutive_feasible = 3  # Límite de FEASIBLE antes de aceptar solución

                # Probar descendiendo de a 1 conductor
                for num_drivers_to_try in range(initial_drivers, min_drivers_target - 1, -1):
                    # Verificar timeout global
                    elapsed = time.time() - self.start_time
                    if elapsed > self.timeout:
                        print(f"  ⏰ Timeout global alcanzado ({elapsed:.1f}s / {self.timeout}s)")
                        break

                    attempt += 1
                    if attempt > max_attempts:
                        print(f"  ℹ️  Alcanzado límite de {max_attempts} intentos")
                        break

                    remaining = self.timeout - elapsed
                    print(f"\n  🔍 CP-SAT intento {attempt}/{max_attempts}: {num_drivers_to_try} conductores (quedan {remaining:.0f}s)...", end=' ', flush=True)

                    result = self._solve_with_cpsat(all_shifts, num_drivers_to_try, year, month, min_drivers_target)

                    if result['status'] == 'success':
                        # ✓ Solución factible encontrada
                        best_cp_solution = result
                        best_solution = result
                        drivers_used = result['metrics']['drivers_used']
                        solver_status = result.get('solver_status', 'feasible')

                        if solver_status == 'optimal':
                            print(f"✅ ÓPTIMO ({drivers_used} conductores)")
                            consecutive_feasible_count = 0
                            break
                        else:
                            print(f"✓ Factible ({drivers_used} conductores)")
                            consecutive_feasible_count += 1

                            if consecutive_feasible_count >= max_consecutive_feasible:
                                print(f"  ⚠️  Aceptando solución tras {max_consecutive_feasible} intentos factibles")
                                break
                            # Continuar bajando para encontrar el mínimo
                    else:
                        # ✗ No factible con este número
                        print(f"❌ No factible")
                        print(f"  ✓ Mínimo encontrado: {num_drivers_to_try + 1} conductores")
                        consecutive_feasible_count = 0
                        break

                if best_cp_solution:
                    improvement = greedy_drivers - best_solution['metrics']['drivers_used']
                    pct = (improvement / greedy_drivers) * 100
                    print(f"\n  🎉 CP-SAT MEJORÓ LA SOLUCIÓN:")
                    print(f"     Greedy: {greedy_drivers} conductores")
                    print(f"     CP-SAT: {best_solution['metrics']['drivers_used']} conductores")
                    print(f"     Mejora: {improvement} conductores ({pct:.1f}%)")
                else:
                    print(f"\n  ℹ️  CP-SAT no logró mejorar solución greedy")
                    print(f"     Usando: {greedy_drivers} conductores (greedy)")
            else:
                print(f"\n  ✗ Greedy no encontró solución, fallback a CP-SAT...")

                # Fallback: usar CP-SAT si greedy falla
                print(f"\n{'='*80}")
                print(f"FALLBACK: OPTIMIZACIÓN CP-SAT")
                print(f"{'='*80}")

                max_attempts = min(10, max_drivers - min_drivers + 1)

                for attempt, num_drivers in enumerate(range(min_drivers, min_drivers + max_attempts), 1):
                    if time.time() - self.start_time > self.timeout:
                        break

                    result = self._solve_with_cpsat(all_shifts, num_drivers, year, month, min_drivers)

                    if result['status'] == 'success':
                        best_solution = result
                        break

        if best_solution:
            drivers_used = best_solution['metrics']['drivers_used']
            print(f"\n✓ MEJOR SOLUCIÓN: {drivers_used} conductores utilizados")
            return best_solution

        return {
            'status': 'failed',
            'message': 'No se encontró solución factible'
        }
    
    def optimize_year(self, year: int) -> Dict[str, Any]:
        """
        Optimiza un año completo (12 meses) con continuidad de patrones

        Estrategia mejorada:
        1. Optimiza FEBRERO (28 días = 4 semanas exactas, más restrictivo)
        2. Extrae el patrón semanal de cada conductor
        3. Replica el patrón hacia atrás (enero) y adelante (marzo-diciembre)
        4. Garantiza continuidad: si termina día 3 de ciclo 7x7, siguiente mes empieza día 4

        Returns:
            Dict con resultados anuales consolidados
        """
        self.start_time = time.time()

        print(f"\n{'='*80}")
        print(f"OPTIMIZACIÓN ANUAL {year} - RÉGIMEN {self.regime}")
        print(f"{'='*80}\n")

        # PASO 1: Optimizar FEBRERO (mes base de 4 semanas)
        print(f"📅 PASO 1: Optimizando febrero {year} (mes base - 4 semanas exactas)...")

        feb_solution = self.optimize_month(year, 2)

        if feb_solution['status'] != 'success':
            return {
                'status': 'failed',
                'message': f'No se pudo optimizar febrero {year}',
                'year': year
            }

        num_drivers = feb_solution['metrics']['drivers_used']
        print(f"\n✓ Plantilla base determinada: {num_drivers} conductores")
        print(f"✓ Patrón febrero establecido como referencia")

        # PASO 2: Extraer patrones de febrero
        print(f"\n📊 PASO 2: Extrayendo patrones de trabajo de febrero...")

        driver_patterns = self._extract_driver_patterns(feb_solution, year, 2)

        print(f"✓ Patrones extraídos para {len(driver_patterns)} conductores")
        for driver_id, pattern_info in list(driver_patterns.items())[:5]:
            print(f"  - {driver_id}: {pattern_info['pattern']} ({pattern_info['work_days']} días trabajados)")
        if len(driver_patterns) > 5:
            print(f"  ... y {len(driver_patterns) - 5} conductores más")

        # PASO 3: Replicar patrón a todos los meses
        monthly_solutions = {2: feb_solution}
        all_assignments = list(feb_solution['assignments'])

        print(f"\n📅 PASO 3: Replicando patrón a todos los meses del año...\n")

        # Meses antes de febrero (enero)
        for month in [1]:
            print(f"  Mes {month:02d}/{year} (hacia atrás)...", end=" ")
            month_solution = self._replicate_pattern_to_month(
                year, month, driver_patterns, num_drivers
            )

            if month_solution['status'] == 'success':
                monthly_solutions[month] = month_solution
                all_assignments.extend(month_solution['assignments'])
                print(f"✓ {len(month_solution['assignments'])} asignaciones")
            else:
                print(f"✗ Falló")
                return {
                    'status': 'failed',
                    'message': f'No se pudo replicar patrón a mes {month}/{year}',
                    'year': year
                }

        # Meses después de febrero (marzo-diciembre)
        for month in range(3, 13):
            print(f"  Mes {month:02d}/{year} (hacia adelante)...", end=" ")
            month_solution = self._replicate_pattern_to_month(
                year, month, driver_patterns, num_drivers
            )

            if month_solution['status'] == 'success':
                monthly_solutions[month] = month_solution
                all_assignments.extend(month_solution['assignments'])
                print(f"✓ {len(month_solution['assignments'])} asignaciones")
            else:
                print(f"✗ Falló")
                return {
                    'status': 'failed',
                    'message': f'No se pudo replicar patrón a mes {month}/{year}',
                    'year': year
                }

        # PASO 4: Consolidar resultados anuales
        print(f"\n📊 PASO 4: Consolidando resultados anuales...")

        annual_summary = self._consolidate_annual_results(monthly_solutions, year, num_drivers)

        print(f"\n{'='*80}")
        print(f"✓ OPTIMIZACIÓN ANUAL {year} COMPLETADA")
        print(f"{'='*80}")
        print(f"  - Conductores utilizados: {num_drivers}")
        print(f"  - Total asignaciones: {len(all_assignments)}")
        print(f"  - Costo anual: ${annual_summary['metrics']['total_annual_cost']:,.0f}")
        print(f"  - Patrones garantizados con continuidad mensual")
        print()

        return annual_summary

    def _extract_driver_patterns(self, solution: Dict[str, Any],
                                  year: int, month: int) -> Dict[str, Dict]:
        """
        Extrae el patrón de trabajo de cada conductor desde una solución mensual

        Returns:
            Dict[driver_id, {
                'pattern': '6x1' | '7x7' | etc,
                'work_days': [1,2,3,5,6,7,...],  # días del mes trabajados
                'assignments': [...],  # asignaciones del conductor
                'services': {...}  # servicios asignados
            }]
        """
        driver_patterns = {}
        driver_summary = solution.get('driver_summary', {})

        for driver_id, driver_data in driver_summary.items():
            # Convertir fechas trabajadas a días del mes
            dates_worked = driver_data.get('dates_worked', [])
            work_days = []

            for date in dates_worked:
                if isinstance(date, str):
                    date = datetime.fromisoformat(date).date()
                work_days.append(date.day)

            work_days = sorted(set(work_days))

            # Obtener asignaciones del conductor
            conductor_assignments = [
                a for a in solution['assignments']
                if a['driver_id'] == driver_id
            ]

            # Extraer servicios únicos (la clave puede ser 'service' o 'service_id')
            services = set(a.get('service') or a.get('service_id') for a in conductor_assignments)

            driver_patterns[driver_id] = {
                'pattern': driver_data.get('pattern', 'Flexible'),
                'work_days': work_days,
                'assignments': conductor_assignments,
                'services': services,
                'driver_name': driver_data.get('driver_name', driver_id)
            }

        return driver_patterns

    def _replicate_pattern_to_month(self, year: int, month: int,
                                     driver_patterns: Dict[str, Dict],
                                     num_drivers: int) -> Dict[str, Any]:
        """
        Replica EXACTAMENTE las asignaciones de febrero desplazando ±28 días

        Estrategia:
        - Feb 1 + 28 días = Mar 1 (misma asignación)
        - Feb 1 - 28 días = Ene 4 (misma asignación)
        - Feb 15 + 56 días = Abr 12 (misma asignación)

        Cada fecha del mes target se mapea a una fecha de febrero ±N*28 días
        """
        from datetime import timedelta

        # Generar turnos del mes target
        month_shifts = self._generate_month_shifts(year, month)

        # Crear mapeo: fecha_febrero → {(servicio, turno, vehículo): asignación}
        feb_assignments_by_date = {}

        for driver_id, pattern_info in driver_patterns.items():
            for assignment in pattern_info['assignments']:
                feb_date = assignment['date']
                if isinstance(feb_date, str):
                    feb_date = datetime.fromisoformat(feb_date).date()

                if feb_date not in feb_assignments_by_date:
                    feb_assignments_by_date[feb_date] = {}

                # Crear clave única por turno
                service = assignment.get('service') or assignment.get('service_id')
                shift_num = assignment.get('shift')
                vehicle = assignment.get('vehicle', 0)
                key = (service, shift_num, vehicle)

                feb_assignments_by_date[feb_date][key] = assignment

        # Replicar asignaciones desplazando ±28 días
        assignments = []

        for shift in month_shifts:
            shift_date = shift['date']
            if isinstance(shift_date, str):
                shift_date = datetime.fromisoformat(shift_date).date()

            # Calcular fecha equivalente en febrero
            # Encontrar el offset de días desde/hasta febrero
            if month < 2:
                # Enero: restar 28 días desde febrero
                # ene 4 ← feb 1 (resta 28)
                # ene 5 ← feb 2 (resta 28)
                days_from_feb_start = (datetime(year, 2, 1).date() - shift_date).days
                feb_day = 1 + (days_from_feb_start % 28)
                feb_equivalent = datetime(year, 2, min(feb_day, 28)).date()
            elif month > 2:
                # Marzo+: sumar 28 días desde febrero
                # mar 1 ← feb 1 (suma 28)
                # abr 1 ← feb 4 (suma 28*2-25)
                days_since_feb_start = (shift_date - datetime(year, 2, 1).date()).days
                feb_day = 1 + (days_since_feb_start % 28)
                feb_equivalent = datetime(year, 2, min(feb_day, 28)).date()
            else:
                # Febrero mismo
                feb_equivalent = shift_date

            # Buscar asignación en febrero para esa fecha
            date_assignments = feb_assignments_by_date.get(feb_equivalent, {})

            # Crear clave para buscar
            shift_service = shift.get('service_id') or shift.get('service')
            shift_num = shift.get('shift_number')
            vehicle = shift.get('vehicle', 0)
            key = (shift_service, shift_num, vehicle)

            matching_assignment = date_assignments.get(key)

            # Si no hay match exacto, buscar por servicio y turno
            if not matching_assignment:
                for (s, sh, v), assign in date_assignments.items():
                    if s == shift_service and sh == shift_num:
                        matching_assignment = assign
                        break

            # Si aún no hay match, buscar solo por servicio
            if not matching_assignment:
                for (s, sh, v), assign in date_assignments.items():
                    if s == shift_service:
                        matching_assignment = assign
                        break

            if matching_assignment:
                # Copiar asignación de febrero al mes target
                assignment = {
                    'date': shift_date.isoformat(),
                    'service': shift.get('service_id') or shift.get('service'),
                    'service_name': shift.get('service_name'),
                    'service_type': shift.get('service_type', 'Industrial'),
                    'service_group': shift.get('service_group'),
                    'shift': shift.get('shift_number'),
                    'vehicle': shift.get('vehicle', 0),
                    'driver_id': matching_assignment['driver_id'],
                    'driver_name': matching_assignment['driver_name'],
                    'start_time': shift['start_time'],
                    'end_time': shift['end_time'],
                    'duration_hours': shift['duration_hours'],
                    'vehicle_type': shift.get('vehicle_type'),
                    'vehicle_category': shift.get('vehicle_category')
                }

                assignments.append(assignment)

        # Calcular métricas del mes (mismo formato que optimize_month)
        driver_summary = {}
        for assignment in assignments:
            driver_id = assignment['driver_id']
            if driver_id not in driver_summary:
                # Obtener nombre del patrón de febrero
                pattern = driver_patterns.get(driver_id, {}).get('pattern', 'Flexible')
                work_start_date = driver_patterns.get(driver_id, {}).get('work_start_date')

                driver_summary[driver_id] = {
                    'driver_id': driver_id,
                    'driver_name': assignment['driver_name'],
                    'name': assignment['driver_name'],
                    'pattern': pattern,  # Preservar patrón de febrero
                    'work_start_date': work_start_date,  # Fecha de inicio del ciclo
                    'total_hours': 0,
                    'total_shifts': 0,
                    'sundays_worked_set': set(),
                    'dates_worked': set(),
                    'contract_type': 'fixed_term',
                    'regime': self.regime,
                    'services': set(),
                    'vehicle_categories': set(),
                    'vehicle_types': set(),
                    'shifts': []
                }

            driver_summary[driver_id]['total_hours'] += assignment['duration_hours']
            driver_summary[driver_id]['total_shifts'] += 1
            driver_summary[driver_id]['services'].add(assignment.get('service') or assignment.get('service_id'))
            driver_summary[driver_id]['vehicle_categories'].add(assignment.get('vehicle_category', 'other'))
            driver_summary[driver_id]['vehicle_types'].add(assignment.get('vehicle_type', 'unknown'))
            driver_summary[driver_id]['shifts'].append({
                'duration_hours': assignment['duration_hours'],
                'vehicle_category': assignment.get('vehicle_category'),
                'vehicle_type': assignment.get('vehicle_type')
            })

            # Contar domingos únicos
            date_obj = datetime.fromisoformat(assignment['date'])
            driver_summary[driver_id]['dates_worked'].add(date_obj.date())
            if date_obj.weekday() == 6:  # Domingo
                driver_summary[driver_id]['sundays_worked_set'].add(date_obj.date())

        # Convertir sets a listas y calcular métricas finales
        total_cost = 0
        for driver_id in driver_summary:
            driver_summary[driver_id]['dates_worked'] = sorted(list(driver_summary[driver_id]['dates_worked']))
            driver_summary[driver_id]['days_worked'] = len(driver_summary[driver_id]['dates_worked'])
            driver_summary[driver_id]['services_worked'] = sorted(list(driver_summary[driver_id]['services']))
            driver_summary[driver_id]['vehicle_categories'] = sorted(list(driver_summary[driver_id]['vehicle_categories']))
            driver_summary[driver_id]['vehicle_types'] = sorted(list(driver_summary[driver_id]['vehicle_types']))
            driver_summary[driver_id]['sundays_worked'] = len(driver_summary[driver_id]['sundays_worked_set'])
            del driver_summary[driver_id]['sundays_worked_set']

            # Calcular utilización y costo
            total_hours = driver_summary[driver_id]['total_hours']
            max_hours = 180 if self.regime == 'Interurbano' else 176
            utilization = (total_hours / max_hours * 100) if max_hours > 0 else 0
            driver_summary[driver_id]['utilization'] = round(utilization, 1)

            cost_details = self._compute_driver_cost(driver_summary[driver_id])
            driver_summary[driver_id]['salary'] = round(cost_details['total_cost'])
            driver_summary[driver_id]['cost_details'] = {
                'base_cost': round(cost_details['base_cost']),
                'vehicle_adjusted_cost': round(cost_details['vehicle_adjusted_cost']),
                'driver_multiplier': cost_details['driver_multiplier'],
                'service_multiplier': cost_details['service_multiplier'],
                'service_count': cost_details['service_count']
            }
            total_cost += cost_details['total_cost']
            driver_summary[driver_id].pop('services', None)
            driver_summary[driver_id].pop('shifts', None)

        return {
            'status': 'success',
            'year': year,
            'month': month,
            'regime': self.regime,
            'assignments': assignments,
            'driver_summary': driver_summary,
            'metrics': {
                'drivers_used': len(driver_summary),
                'total_assignments': len(assignments),
                'total_cost': total_cost
            }
        }

    def _consolidate_annual_results(self, monthly_solutions: Dict[int, Dict],
                                     year: int, num_drivers: int) -> Dict[str, Any]:
        """Consolida resultados de 12 meses en un resumen anual"""

        # Consolidar asignaciones
        all_assignments = []
        for month_solution in monthly_solutions.values():
            all_assignments.extend(month_solution['assignments'])

        # Consolidar métricas por conductor
        annual_driver_summary = {}

        for month, solution in monthly_solutions.items():
            driver_summary = solution.get('driver_summary', {})

            for driver_id, driver_data in driver_summary.items():
                if driver_id not in annual_driver_summary:
                    annual_driver_summary[driver_id] = {
                        'driver_id': driver_id,
                        'driver_name': driver_data.get('driver_name', driver_id),
                        'name': driver_data.get('name', driver_data.get('driver_name', driver_id)),
                        'pattern': driver_data.get('pattern', 'Flexible'),
                        'contract_type': driver_data.get('contract_type', 'fixed_term'),
                        'regime': driver_data.get('regime', self.regime),
                        'total_hours': 0,
                        'total_shifts': 0,
                        'sundays_worked': 0,
                        'days_worked': 0,
                        'months_worked': [],
                        'monthly_hours': {},
                        'dates_worked': [],
                        'services_worked': set(),
                        'vehicle_categories': set(),
                        'vehicle_types': set(),
                        'total_salary': 0
                    }

                annual_driver_summary[driver_id]['total_hours'] += driver_data.get('total_hours', 0)
                annual_driver_summary[driver_id]['total_shifts'] += driver_data.get('total_shifts', 0)
                annual_driver_summary[driver_id]['sundays_worked'] += driver_data.get('sundays_worked', 0)
                annual_driver_summary[driver_id]['days_worked'] += driver_data.get('days_worked', 0)
                annual_driver_summary[driver_id]['total_salary'] += driver_data.get('salary', 0)
                annual_driver_summary[driver_id]['months_worked'].append(month)
                annual_driver_summary[driver_id]['monthly_hours'][month] = driver_data.get('total_hours', 0)

                # Consolidar fechas trabajadas
                for date in driver_data.get('dates_worked', []):
                    annual_driver_summary[driver_id]['dates_worked'].append(date)

                # Consolidar servicios y vehículos
                for service in driver_data.get('services_worked', []):
                    annual_driver_summary[driver_id]['services_worked'].add(service)
                for cat in driver_data.get('vehicle_categories', []):
                    annual_driver_summary[driver_id]['vehicle_categories'].add(cat)
                for vtype in driver_data.get('vehicle_types', []):
                    annual_driver_summary[driver_id]['vehicle_types'].add(vtype)

        # Finalizar métricas anuales de conductores
        for driver_id in annual_driver_summary:
            # Convertir sets a listas
            annual_driver_summary[driver_id]['services_worked'] = sorted(list(annual_driver_summary[driver_id]['services_worked']))
            annual_driver_summary[driver_id]['vehicle_categories'] = sorted(list(annual_driver_summary[driver_id]['vehicle_categories']))
            annual_driver_summary[driver_id]['vehicle_types'] = sorted(list(annual_driver_summary[driver_id]['vehicle_types']))

            # Calcular utilización anual (promedio)
            total_hours = annual_driver_summary[driver_id]['total_hours']
            months_worked = len(annual_driver_summary[driver_id]['months_worked'])
            max_hours_annual = (180 if self.regime == 'Interurbano' else 176) * months_worked
            utilization = (total_hours / max_hours_annual * 100) if max_hours_annual > 0 else 0
            annual_driver_summary[driver_id]['utilization'] = round(utilization, 1)

            # Salario anual
            annual_driver_summary[driver_id]['salary'] = annual_driver_summary[driver_id]['total_salary']
            del annual_driver_summary[driver_id]['total_salary']

        # Calcular métricas anuales
        total_cost = sum(
            solution['metrics'].get('total_cost', 0)
            for solution in monthly_solutions.values()
        )

        total_hours = sum(
            driver_data['total_hours']
            for driver_data in annual_driver_summary.values()
        )

        return {
            'status': 'success',
            'year': year,
            'regime': self.regime,
            'assignments': all_assignments,
            'driver_summary': annual_driver_summary,
            'monthly_solutions': monthly_solutions,
            'metrics': {
                'drivers_used': num_drivers,
                'total_assignments': len(all_assignments),
                'total_hours': total_hours,
                'total_annual_cost': total_cost,
                'avg_monthly_cost': total_cost / 12,
                'avg_hours_per_driver': total_hours / num_drivers if num_drivers > 0 else 0
            }
        }

    def _generate_month_shifts(self, year: int, month: int) -> List[Dict[str, Any]]:
        """Genera todos los turnos del mes con información de régimen

        Soporta dos modos:
        1. Shifts ya expandidos (tienen campo 'date'): los usa directamente
        2. Shifts template (sin campo 'date'): los expande a cada día del mes
        """
        shifts = []
        shift_id = 0

        # Verificar si los shifts ya vienen expandidos (tienen campo 'date')
        if self.services and self.services[0].get('shifts'):
            first_shift = self.services[0]['shifts'][0]
            shifts_already_expanded = 'date' in first_shift and first_shift['date'] is not None
        else:
            shifts_already_expanded = False

        if shifts_already_expanded:
            # MODO 1: Shifts ya expandidos por el excel_reader
            # Solo necesitamos copiarlos con metadatos adicionales
            for service in self.services:
                service_type = service.get('service_type', 'Industrial')
                service_group = service.get('service_group') or service.get('group') or service.get('name') or service.get('id')
                vehicles = service.get('vehicles', {}).get('quantity', 1)
                vehicle_metadata = self._infer_vehicle_metadata(service)

                for shift_data in service['shifts']:
                    # Los shifts ya tienen fecha específica
                    shift_date = shift_data['date']
                    if not isinstance(shift_date, date):
                        continue  # Skip si no es fecha válida

                    # Verificar que la fecha corresponde al mes solicitado
                    if shift_date.year != year or shift_date.month != month:
                        continue

                    weekday = shift_date.weekday()

                    # Para servicios expandidos, vehicles=1 (ya viene multiplicado en el Excel si es necesario)
                    # Pero si service indica quantity > 1, debemos multiplicar
                    for vehicle_idx in range(vehicles):
                        shift = {
                            'id': shift_id,
                            'date': shift_date,
                            'service_id': shift_data.get('service_id', service.get('id')),
                            'service_name': shift_data.get('service_name', service.get('name')),
                            'service_type': shift_data.get('service_type', service_type),
                            'service_group': service_group,
                            'vehicle': vehicle_idx,
                            'shift_number': shift_data.get('shift_number', 1),
                            'start_time': shift_data['start_time'],
                            'end_time': shift_data['end_time'],
                            'duration_hours': shift_data['duration_hours'],
                            'vehicle_type': shift_data.get('vehicle_type', vehicle_metadata['vehicle_type']),
                            'vehicle_category': vehicle_metadata['vehicle_category'],
                            'is_sunday': weekday == 6,
                            'week_num': (shift_date.day - 1) // 7 + 1
                        }

                        # Usar start_minutes y end_minutes si ya vienen, sino calcular
                        if 'start_minutes' in shift_data and 'end_minutes' in shift_data:
                            shift['start_minutes'] = shift_data['start_minutes']
                            shift['end_minutes'] = shift_data['end_minutes']
                        else:
                            start_minutes = self._time_to_minutes(shift['start_time'])
                            end_minutes = self._time_to_minutes(shift['end_time'])
                            shift['start_minutes'] = start_minutes
                            shift['end_minutes'] = end_minutes
                            if shift['end_minutes'] < shift['start_minutes']:
                                shift['end_minutes'] += 24 * 60  # Ajustar si cruza medianoche

                        shifts.append(shift)
                        shift_id += 1
        else:
            # MODO 2: Shifts template (modo original)
            # Generar días del mes
            if month == 12:
                next_month = date(year + 1, 1, 1)
            else:
                next_month = date(year, month + 1, 1)

            current_date = date(year, month, 1)

            while current_date < next_month:
                weekday = current_date.weekday()

                for service in self.services:
                    # Verificar si el servicio opera este día
                    if weekday not in service['frequency']['days']:
                        continue

                    service_type = service.get('service_type', 'Industrial')
                    service_group = service.get('service_group') or service.get('group') or service.get('name') or service.get('id')
                    vehicles = service['vehicles']['quantity']
                    vehicle_metadata = self._infer_vehicle_metadata(service)

                    for shift_data in service['shifts']:
                        for vehicle_idx in range(vehicles):
                            shift = {
                                'id': shift_id,
                                'date': current_date,
                                'service_id': service['id'],
                                'service_name': service['name'],
                                'service_type': service_type,  # Importante: tipo de servicio
                                'service_group': service_group,
                                'vehicle': vehicle_idx,
                                'shift_number': shift_data['shift_number'],
                                'start_time': shift_data['start_time'],
                                'end_time': shift_data['end_time'],
                                'duration_hours': shift_data['duration_hours'],
                                'vehicle_type': vehicle_metadata['vehicle_type'],
                                'vehicle_category': vehicle_metadata['vehicle_category'],
                                'is_sunday': weekday == 6,
                                'week_num': (current_date.day - 1) // 7 + 1
                            }

                            # Calcular hora de inicio y fin en minutos para análisis
                            start_minutes = self._time_to_minutes(shift['start_time'])
                            end_minutes = self._time_to_minutes(shift['end_time'])

                            shift['start_minutes'] = start_minutes
                            shift['end_minutes'] = end_minutes
                            if shift['end_minutes'] < shift['start_minutes']:
                                shift['end_minutes'] += 24 * 60  # Ajustar si cruza medianoche

                            shifts.append(shift)
                            shift_id += 1

                current_date += timedelta(days=1)

        return shifts
    
    # Método eliminado - ya no necesario con régimen único
    
    def _calculate_minimum_drivers(self, all_shifts: List[Dict]) -> int:
        """Calcula el número mínimo de conductores según el régimen único"""

        constraints = self.regime_constraints

        # Mínimo por cobertura simultánea
        max_simultaneous = self._calculate_max_simultaneous(all_shifts)

        # Para Faena Minera, el cálculo por horas NO aplica (tienen ciclos NxN)
        if self.regime in ['Faena Minera', 'Minera']:
            # En Faena Minera, el mínimo es puramente por turnos simultáneos × 2
            # (porque con 7x7, la mitad está de descanso)
            return max_simultaneous * 2

        # Calcular horas totales para otros regímenes
        total_hours = sum(s['duration_hours'] for s in all_shifts)

        # Mínimo por horas mensuales o semanales
        if constraints.max_monthly_hours:
            min_by_hours = int(total_hours / constraints.max_monthly_hours) + 1
        elif constraints.max_weekly_hours:
            min_by_hours = int(total_hours / (constraints.max_weekly_hours * 4.3)) + 1
        else:
            min_by_hours = int(total_hours / 180) + 1  # Default
        
        # Para interurbano, ajustar considerando que los conductores pueden hacer
        # múltiples turnos en el día si hay descanso adecuado entre ellos
        if self.regime == 'Interurbano':
            # Análisis más inteligente: ver cuántos turnos se pueden combinar
            # Un conductor puede hacer hasta 2 turnos de 8h con descanso entre ellos
            # Esto reduce significativamente el número de conductores necesarios
            
            # Agrupar turnos por día para ver posibles combinaciones
            from collections import defaultdict
            shifts_by_date = defaultdict(list)
            for shift in all_shifts:
                shifts_by_date[shift['date']].append(shift)
            
            # Calcular conductores necesarios considerando combinaciones posibles
            total_driver_days = 0
            for date, day_shifts in shifts_by_date.items():
                # Ordenar por hora de inicio
                day_shifts.sort(key=lambda x: x['start_minutes'])
                
                # Contar turnos que se pueden combinar
                assigned = [False] * len(day_shifts)
                driver_count_for_day = 0
                
                for i in range(len(day_shifts)):
                    if assigned[i]:
                        continue
                    
                    driver_count_for_day += 1
                    assigned[i] = True
                    
                    # Ver si este conductor puede tomar otro turno
                    for j in range(i + 1, len(day_shifts)):
                        if assigned[j]:
                            continue
                        
                        # Verificar si puede tomar este turno adicional
                        gap = day_shifts[j]['start_minutes'] - day_shifts[i]['end_minutes']
                        
                        # Si hay al menos 60 minutos de descanso y no se solapan
                        if gap >= 60:
                            # Verificar que no exceda 16h de jornada total
                            total_span = (day_shifts[j]['end_minutes'] - day_shifts[i]['start_minutes']) / 60
                            if total_span <= 16:
                                assigned[j] = True
                                break  # Este conductor ya tiene 2 turnos
                
                total_driver_days += driver_count_for_day
            
            # El número mínimo es el máximo entre:
            # - Conductores necesarios por día (promedio)
            # - Conductores necesarios por horas mensuales
            avg_drivers_per_day = total_driver_days / len(shifts_by_date)
            estimated_min = max(int(avg_drivers_per_day * 1.3), min_by_hours)  # 30% margen
            
            return max(estimated_min, max_simultaneous)
        
        return max(min_by_hours, max_simultaneous)
    
    def _calculate_max_simultaneous(self, shifts: List[Dict]) -> int:
        """Calcula el máximo de turnos que se traslapan en cualquier momento"""
        if not shifts:
            return 0

        # Crear eventos de inicio y fin para cada turno
        events = []

        # Obtener fecha base (primera fecha del mes)
        min_date = min(shift['date'] for shift in shifts)

        for shift in shifts:
            # Convertir fecha + minutos a timestamp único
            date = shift['date']
            start_mins = shift['start_minutes']
            end_mins = shift['end_minutes']

            # Timestamp base: días desde min_date
            day_offset = (date - min_date).days
            base = day_offset * 24 * 60

            events.append((base + start_mins, 1))   # Inicio de turno: +1
            events.append((base + end_mins, -1))    # Fin de turno: -1

        # Ordenar eventos por tiempo
        events.sort()

        # Calcular máximo de turnos simultáneos usando sweep line
        max_simultaneous = 0
        current_simultaneous = 0

        for time, delta in events:
            current_simultaneous += delta
            max_simultaneous = max(max_simultaneous, current_simultaneous)

        # Silenciar: print(f"  DEBUG: Total eventos procesados: {len(events)}, Max simultáneos: {max_simultaneous}")

        return max_simultaneous

    def _detect_minera_pattern(self, dates_worked: List, year: int, month: int) -> str:
        """Detecta el patrón NxN de trabajo para Faena Minera

        Identifica el patrón por los DÍAS DE DESCANSO CONSECUTIVOS:
        - 7x7: 7 días consecutivos de descanso
        - 8x8: 8 días consecutivos de descanso
        - 10x10: 10 días consecutivos de descanso
        - 14x14: 14 días consecutivos de descanso
        """
        if not dates_worked:
            return 'Flexible'

        # Convertir a conjunto de días trabajados
        work_days = set()
        for date in dates_worked:
            if isinstance(date, str):
                date = datetime.fromisoformat(date).date()
            work_days.add(date.day)

        # Generar todos los días del mes
        num_days = calendar.monthrange(year, month)[1]
        all_days = list(range(1, num_days + 1))

        # Identificar secuencias de días NO trabajados (descansos)
        rest_sequences = []
        current_rest = 0

        for day in all_days:
            if day not in work_days:
                current_rest += 1
            else:
                if current_rest > 0:
                    rest_sequences.append(current_rest)
                    current_rest = 0

        # Agregar última secuencia si termina en descanso
        if current_rest > 0:
            rest_sequences.append(current_rest)

        if not rest_sequences:
            return 'Flexible'

        # Patrones esperados - SIN EXCEPCIONES
        pattern_map = {
            7: '7x7',
            8: '8x8',
            10: '10x10',
            14: '14x14'
        }

        # Contar secuencias de descanso por longitud
        from collections import Counter
        rest_counter = Counter(rest_sequences)

        # Calcular cuántas secuencias de N días DEBERÍAN aparecer en el mes
        for rest_days in sorted(pattern_map.keys(), reverse=True):
            cycle_length = rest_days * 2  # NxN: N trabajo + N descanso
            expected_rest_sequences = num_days // cycle_length

            # Si el mes tiene al menos un ciclo completo, debe tener al menos 1 secuencia
            # Si tiene 2+ ciclos, debe tener 2+ secuencias
            if expected_rest_sequences >= 1:
                actual_sequences = rest_counter.get(rest_days, 0)

                # DEBE tener al menos la cantidad esperada de secuencias
                if actual_sequences >= expected_rest_sequences:
                    return pattern_map[rest_days]

        return 'Flexible'

    def _detect_regular_pattern(self, dates_worked: List, year: int, month: int) -> str:
        """Detecta patrones de trabajo regulares (no mineros)

        Identifica el patrón por los DÍAS DE DESCANSO CONSECUTIVOS:
        - 6x1: 1 día de descanso (trabaja 6, descansa 1)
        - 5x2: 2 días consecutivos de descanso (trabaja 5, descansa 2)
        - Combinado: alterna entre 1 y 2 días de descanso (semana 6x1, semana 5x2)
        """
        if not dates_worked:
            return 'Flexible'

        # Convertir a conjunto de días trabajados
        work_days = set()
        for date in dates_worked:
            if isinstance(date, str):
                date = datetime.fromisoformat(date).date()
            work_days.add(date.day)

        # Generar todos los días del mes
        num_days = calendar.monthrange(year, month)[1]
        all_days = list(range(1, num_days + 1))

        # Identificar secuencias de días NO trabajados (descansos)
        rest_sequences = []
        current_rest = 0

        for day in all_days:
            if day not in work_days:
                current_rest += 1
            else:
                if current_rest > 0:
                    rest_sequences.append(current_rest)
                    current_rest = 0

        # Agregar última secuencia si termina en descanso
        if current_rest > 0:
            rest_sequences.append(current_rest)

        if not rest_sequences:
            return 'Flexible'

        # Contar secuencias de descanso
        from collections import Counter
        rest_counter = Counter(rest_sequences)

        # Determinar número de semanas completas en el mes
        num_weeks = num_days // 7

        # Patrón 6x1: SOLO secuencias de 1 día de descanso
        if rest_counter.get(1, 0) >= num_weeks and len(rest_counter) == 1:
            return '6x1'

        # Patrón 5x2: SOLO secuencias de 2 días consecutivos de descanso
        if rest_counter.get(2, 0) >= num_weeks and len(rest_counter) == 1:
            return '5x2'

        # Patrón Combinado: mezcla de 1 y 2 días de descanso
        # Debe tener AMBOS tipos de secuencias en proporción similar
        has_one_day = rest_counter.get(1, 0) > 0
        has_two_days = rest_counter.get(2, 0) > 0

        if has_one_day and has_two_days:
            # Verificar que la suma de secuencias coincida con las semanas
            total_rest_sequences = rest_counter.get(1, 0) + rest_counter.get(2, 0)
            if total_rest_sequences >= num_weeks:
                return 'Combinado (6x1/5x2)'

        return 'Flexible'

    def _greedy_assignment_single_pattern(self, all_shifts: List[Dict], cycle: int) -> Dict[str, Any]:
        """Algoritmo constructivo greedy para asignar turnos con un solo patrón NxN

        Lógica:
        1. Por cada día, si span < 12h → puede hacerlo 1 conductor
        2. Si span >= 12h → necesita 2+ conductores
        3. Verificar continuidad: último turno del día puede hacer primero del siguiente
           si (hora_fin_siguiente - hora_inicio_anterior) < 12h
        4. Asignar conductores siguiendo patrón NxN estricto

        Args:
            all_shifts: Lista de turnos a asignar
            cycle: Longitud del ciclo (7, 10, 14)

        Returns:
            Dict con asignaciones y número de conductores usados
        """
        from datetime import date, timedelta

        print(f"\n    🔧 Construyendo solución greedy con patrón {cycle}x{cycle}...")

        # Agrupar turnos por fecha
        shifts_by_date = {}
        for shift in all_shifts:
            d = shift['date']
            if d not in shifts_by_date:
                shifts_by_date[d] = []
            shifts_by_date[d].append(shift)

        all_dates = sorted(shifts_by_date.keys())

        # Ordenar turnos de cada día por hora de inicio
        for d in all_dates:
            shifts_by_date[d].sort(key=lambda s: s['start_minutes'])

        # Estructura: conductores[driver_id] = {
        #   'pattern': cycle,
        #   'work_days': [dates trabajando],
        #   'assignments': [shifts asignados],
        #   'last_shift_end': (date, end_minutes)
        # }
        drivers = {}
        driver_counter = 0

        # Para cada conductor, llevar track de su estado en el ciclo NxN
        # day_offset: 0-13 para 7x7 (0-6 trabaja, 7-13 descansa)
        driver_availability = {}  # driver_id -> {current_day_in_cycle, work_start_date}

        assignments = []

        # Procesar cada día
        for day_idx, date in enumerate(all_dates):
            day_shifts = shifts_by_date[date]

            print(f"\n      Día {day_idx + 1} ({date}): {len(day_shifts)} turnos")

            # Calcular span del día
            earliest_start = min(s['start_minutes'] for s in day_shifts)
            latest_end = max(s['end_minutes'] for s in day_shifts)

            if latest_end < earliest_start:
                # Cruza medianoche
                span_minutes = (1440 - earliest_start) + latest_end
            else:
                span_minutes = latest_end - earliest_start

            span_hours = span_minutes / 60

            print(f"        Span: {span_hours:.1f}h ({earliest_start//60:02d}:{earliest_start%60:02d} - {latest_end//60:02d}:{latest_end%60:02d})")

            # Encontrar conductores disponibles en este día (según patrón NxN)
            available_drivers = []
            for driver_id, state in driver_availability.items():
                work_start = state['work_start_date']
                days_since_start = (date - work_start).days
                day_in_cycle = days_since_start % (2 * cycle)

                # Trabaja los primeros N días del ciclo 2N
                if day_in_cycle < cycle:
                    available_drivers.append(driver_id)

            print(f"        Conductores disponibles por patrón: {len(available_drivers)}")

            # Asignar turnos del día usando greedy
            unassigned = day_shifts[:]

            # Intentar asignar con conductores existentes primero
            for driver_id in available_drivers:
                if not unassigned:
                    break

                driver = drivers[driver_id]
                last_end = driver.get('last_shift_end')

                # Buscar turnos que este conductor puede hacer
                assigned_today = []
                for shift in unassigned[:]:
                    # Verificar descanso desde último turno Y patrón 7x7
                    can_assign = True

                    # IMPORTANTE: Verificar que esté en su ventana de trabajo según patrón 7x7
                    # Este chequeo ya se hace en available_drivers, pero hay que asegurarse
                    # que el conductor realmente esté disponible HOY según su ciclo
                    work_start = driver.get('work_start_date')
                    if work_start:
                        days_since_start = (date - work_start).days
                        day_in_cycle = days_since_start % (2 * cycle)
                        if day_in_cycle >= cycle:
                            # Está en período de descanso
                            can_assign = False

                    # CRÍTICO: Verificar que no se solape con NINGÚN turno ya asignado HOY
                    if can_assign and assigned_today:
                        for prev_shift in assigned_today:
                            # Verificar solapamiento temporal (incluyendo turnos idénticos)
                            # Dos turnos NO se solapan SOLO SI uno termina antes/cuando empieza el otro
                            if shift['end_minutes'] > prev_shift['start_minutes'] and shift['start_minutes'] < prev_shift['end_minutes']:
                                # Se solapan (incluyendo turnos idénticos) - NO PERMITIDO
                                can_assign = False
                                break

                            # Verificar descanso mínimo entre turnos consecutivos (5h)
                            if shift['start_minutes'] >= prev_shift['end_minutes']:
                                # Este turno empieza después del previo
                                rest_minutes = shift['start_minutes'] - prev_shift['end_minutes']
                                if rest_minutes < 300:  # Menos de 5h
                                    can_assign = False
                                    break
                            elif prev_shift['start_minutes'] >= shift['end_minutes']:
                                # El previo empieza después de este
                                rest_minutes = prev_shift['start_minutes'] - shift['end_minutes']
                                if rest_minutes < 300:  # Menos de 5h
                                    can_assign = False
                                    break

                    if can_assign and last_end:
                        # Verificar descanso desde el último turno de CUALQUIER día anterior
                        days_diff = (date - last_end[0]).days

                        # Solo verificar si es día diferente (mismo día ya verificado arriba)
                        if days_diff > 0:
                            minutes_since_last = (days_diff * 1440) + shift['start_minutes'] - last_end[1]

                            # Más de 24h desde fin último turno: requiere 10h descanso mínimo
                            if minutes_since_last >= 1440 and minutes_since_last < 600:
                                can_assign = False

                    if can_assign:
                        # Verificar que no supere 14h CONSECUTIVAS (span desde primer turno hasta último)
                        # Esto asegura 10h de descanso antes de volver a trabajar
                        if assigned_today:
                            # Calcular span: desde inicio del primer turno hasta fin del último
                            all_shifts_today = assigned_today + [shift]
                            earliest_start = min(s['start_minutes'] for s in all_shifts_today)
                            latest_end = max(s['end_minutes'] for s in all_shifts_today)

                            # Manejar cruces de medianoche
                            if latest_end < earliest_start:
                                # Algún turno cruza medianoche
                                span_minutes = (1440 - earliest_start) + latest_end
                            else:
                                span_minutes = latest_end - earliest_start

                            span_hours = span_minutes / 60.0

                            if span_hours > 14.0:
                                # Excede 14h consecutivas - NO PERMITIDO
                                can_assign = False

                    # RESTRICCIÓN: Límite de 44h semanales (solo regímenes no mineros)
                    if can_assign and self.regime_constraints.max_weekly_hours:
                        # Calcular horas acumuladas en la semana actual
                        weekly_hours = self._calculate_weekly_hours(driver, date, assigned_today, shift)
                        if weekly_hours > self.regime_constraints.max_weekly_hours:
                            can_assign = False

                    if can_assign:
                        # RESTRICCIÓN CRÍTICA: No puede cambiar de grupo en el mismo día
                        # Los grupos están en ubicaciones geográficas diferentes
                        current_shift_group = shift.get('service_group')
                        if current_shift_group and assigned_today:
                            # Ya asignó turnos hoy - verificar que sean del mismo grupo
                            for prev_shift in assigned_today:
                                prev_group = prev_shift.get('service_group')
                                if prev_group and prev_group != current_shift_group:
                                    # Intenta cambiar de grupo - NO PERMITIDO
                                    can_assign = False
                                    break

                    if can_assign:
                        assigned_today.append(shift)
                        unassigned.remove(shift)

                        # Actualizar último turno
                        driver['last_shift_end'] = (date, shift['end_minutes'])

                        # Registrar asignación
                        assignments.append({
                            'driver_id': driver_id,
                            'shift': shift,
                            'date': date
                        })

                        # Registrar en historial del conductor
                        driver['assignments'].append({
                            'shift': shift,
                            'date': date
                        })

                if assigned_today:
                    print(f"          D{driver_id:03d}: {len(assigned_today)} turnos ({sum(s['duration_hours'] for s in assigned_today):.1f}h)")

            # Si quedan turnos sin asignar, crear nuevos conductores
            if unassigned:
                print(f"        ⚠️  {len(unassigned)} turnos sin asignar, creando nuevos conductores...")

                while unassigned:
                    driver_counter += 1
                    driver_id = driver_counter

                    # Determinar work_start_date para este conductor
                    # Queremos que trabaje HOY y los próximos (cycle-1) días
                    # Si estamos en day_idx, queremos: (date - work_start).days % (2*cycle) < cycle
                    # La forma más simple: work_start = fecha actual (empezar su ciclo hoy)
                    work_start_date = date

                    drivers[driver_id] = {
                        'pattern': f'{cycle}x{cycle}',
                        'cycle': cycle,
                        'work_days': [],
                        'assignments': [],
                        'last_shift_end': None,
                        'work_start_date': work_start_date  # Necesario para LNS/ALNS
                    }

                    driver_availability[driver_id] = {
                        'current_day_in_cycle': day_idx % (2 * cycle),
                        'work_start_date': work_start_date
                    }

                    # Asignar turnos a este nuevo conductor
                    assigned_today = []
                    for shift in unassigned[:]:
                        can_assign = True

                        # CRÍTICO: Verificar que no se solape con NINGÚN turno ya asignado HOY
                        if can_assign and assigned_today:
                            for prev_shift in assigned_today:
                                # Verificar solapamiento temporal (incluyendo turnos idénticos)
                                # Dos turnos NO se solapan SOLO SI uno termina antes/cuando empieza el otro
                                if shift['end_minutes'] > prev_shift['start_minutes'] and shift['start_minutes'] < prev_shift['end_minutes']:
                                    # Se solapan (incluyendo turnos idénticos) - NO PERMITIDO
                                    can_assign = False
                                    break

                                # Verificar descanso mínimo entre turnos consecutivos (5h)
                                if shift['start_minutes'] >= prev_shift['end_minutes']:
                                    rest_minutes = shift['start_minutes'] - prev_shift['end_minutes']
                                    if rest_minutes < 300:  # Menos de 5h
                                        can_assign = False
                                        break
                                elif prev_shift['start_minutes'] >= shift['end_minutes']:
                                    rest_minutes = prev_shift['start_minutes'] - shift['end_minutes']
                                    if rest_minutes < 300:  # Menos de 5h
                                        can_assign = False
                                        break

                        # Verificar que no supere 14h CONSECUTIVAS (span desde primer turno hasta último)
                        if can_assign and assigned_today:
                            # Calcular span: desde inicio del primer turno hasta fin del último
                            all_shifts_today = assigned_today + [shift]
                            earliest_start = min(s['start_minutes'] for s in all_shifts_today)
                            latest_end = max(s['end_minutes'] for s in all_shifts_today)

                            # Manejar cruces de medianoche
                            if latest_end < earliest_start:
                                span_minutes = (1440 - earliest_start) + latest_end
                            else:
                                span_minutes = latest_end - earliest_start

                            span_hours = span_minutes / 60.0

                            if span_hours > 14.0:
                                # Excede 14h consecutivas - NO PERMITIDO
                                can_assign = False

                        # RESTRICCIÓN: Límite de 44h semanales (solo regímenes no mineros)
                        # Para nuevos conductores, solo consideramos assigned_today porque es su primer día
                        if can_assign and self.regime_constraints.max_weekly_hours:
                            # Calcular horas del día actual (no tiene historial previo)
                            daily_hours = sum(s['duration_hours'] for s in assigned_today) + shift['duration_hours']
                            if daily_hours > self.regime_constraints.max_weekly_hours:
                                # Si ya en el primer día excedería semanal, no puede
                                can_assign = False

                        # RESTRICCIÓN CRÍTICA: No puede cambiar de grupo en el mismo día
                        if can_assign:
                            current_shift_group = shift.get('service_group')
                            if current_shift_group and assigned_today:
                                # Ya asignó turnos hoy - verificar que sean del mismo grupo
                                for prev_shift in assigned_today:
                                    prev_group = prev_shift.get('service_group')
                                    if prev_group and prev_group != current_shift_group:
                                        # Intenta cambiar de grupo - NO PERMITIDO
                                        can_assign = False
                                        break

                        if can_assign:
                            assigned_today.append(shift)
                            unassigned.remove(shift)

                            drivers[driver_id]['last_shift_end'] = (date, shift['end_minutes'])

                            assignments.append({
                                'driver_id': driver_id,
                                'shift': shift,
                                'date': date
                            })

                            # Registrar en historial del conductor
                            drivers[driver_id]['assignments'].append({
                                'shift': shift,
                                'date': date
                            })

                    print(f"          D{driver_id:03d} (NUEVO): {len(assigned_today)} turnos ({sum(s['duration_hours'] for s in assigned_today):.1f}h)")

                    if not assigned_today:
                        # No pudimos asignar nada, salir para evitar loop infinito
                        break

        # Calcular métricas
        total_drivers = len(drivers)
        total_assignments = len(assignments)

        print(f"\n      ✓ Solución {cycle}x{cycle} completa:")
        print(f"        Conductores usados: {total_drivers}")
        print(f"        Asignaciones: {total_assignments}/{len(all_shifts)}")

        return {
            'cycle': cycle,
            'drivers': drivers,
            'assignments': assignments,
            'num_drivers': total_drivers,
            'coverage': total_assignments / len(all_shifts) if all_shifts else 0
        }

    def _convert_greedy_to_standard(self, greedy_solution: Dict, year: int, month: int) -> Dict[str, Any]:
        """Convierte solución greedy al formato estándar esperado por el sistema

        Args:
            greedy_solution: Solución del algoritmo greedy
            year: Año
            month: Mes

        Returns:
            Dict en formato estándar con assignments, metrics, driver_summary
        """
        assignments = []
        driver_summary = {}

        # Convertir asignaciones greedy al formato estándar
        for assign in greedy_solution['assignments']:
            shift = assign['shift']
            # Manejar driver_id como int o string
            raw_driver_id = assign['driver_id']
            if isinstance(raw_driver_id, int):
                driver_id = f"D{raw_driver_id:03d}"
            else:
                driver_id = raw_driver_id  # Ya es string (ej: "D001")

            assignments.append({
                'date': assign['date'].isoformat() if hasattr(assign['date'], 'isoformat') else str(assign['date']),
                'service': shift.get('service_id'),
                'service_name': shift.get('service_name'),
                'service_type': shift.get('service_type'),
                'service_group': shift.get('service_group'),
                'shift': shift.get('shift_number'),
                'vehicle': shift.get('vehicle', 0),
                'driver_id': driver_id,
                'driver_name': f'Conductor {driver_id}',
                'start_time': shift.get('start_time'),
                'end_time': shift.get('end_time'),
                'duration_hours': shift.get('duration_hours'),
                'vehicle_type': shift.get('vehicle_type'),
                'vehicle_category': shift.get('vehicle_category')
            })

            # Actualizar driver_summary
            if driver_id not in driver_summary:
                # Obtener work_start_date del driver en greedy_solution
                driver_info = greedy_solution['drivers'].get(raw_driver_id, {})
                work_start_date = driver_info.get('work_start_date')

                driver_summary[driver_id] = {
                    'driver_id': driver_id,
                    'driver_name': f'Conductor {assign["driver_id"]}',
                    'name': f'Conductor {assign["driver_id"]}',
                    'total_hours': 0,
                    'total_shifts': 0,
                    'sundays_worked': 0,
                    'dates_worked': set(),
                    'pattern': f'{greedy_solution["cycle"]}x{greedy_solution["cycle"]}',
                    'work_start_date': work_start_date,  # Agregar work_start_date
                    'contract_type': 'fixed_term'
                }

            driver_summary[driver_id]['total_hours'] += shift.get('duration_hours', 0)
            driver_summary[driver_id]['total_shifts'] += 1
            driver_summary[driver_id]['dates_worked'].add(assign['date'])

        # Convertir sets a listas y contar domingos
        for driver_id in driver_summary:
            dates = driver_summary[driver_id]['dates_worked']
            driver_summary[driver_id]['dates_worked'] = len(dates)
            driver_summary[driver_id]['sundays_worked'] = sum(1 for d in dates if d.weekday() == 6)

        # Calcular métricas
        total_hours = sum(d['total_hours'] for d in driver_summary.values())
        total_shifts = len(assignments)

        return {
            'status': 'success',
            'year': year,
            'month': month,
            'assignments': assignments,
            'driver_summary': driver_summary,
            'metrics': {
                'drivers_used': greedy_solution['num_drivers'],
                'total_shifts': total_shifts,
                'total_hours': total_hours,
                'total_cost': total_hours * 5000,  # Aproximado
                'avg_hours_per_driver': total_hours / greedy_solution['num_drivers'] if greedy_solution['num_drivers'] > 0 else 0
            },
            'regime': self.regime,
            'regime_constraints': {
                'name': self.regime_constraints.name,
                'max_weekly_hours': self.regime_constraints.max_weekly_hours,
                'max_monthly_hours': self.regime_constraints.max_monthly_hours,
                'max_daily_hours': self.regime_constraints.max_daily_hours
            },
            'solver_status': 'greedy'
        }

    def _create_hybrid_patterns(self, num_drivers: int, all_shifts: List[Dict]) -> Dict[int, Dict]:
        """Crea patrones híbridos: 60% fijos (estructura) + 40% flexibles (optimización)

        Args:
            num_drivers: Número total de conductores
            all_shifts: Lista de turnos del mes

        Returns:
            Dict con patrón para cada conductor:
            {
                driver_idx: {
                    'fixed': True/False,
                    'cycle': 7/8/10/14 (o None si flexible),
                    'offset': 0-13 (o None si flexible)
                }
            }
        """
        # Analizar demanda por día para distribuir offsets inteligentemente
        shifts_per_day = {}
        for shift in all_shifts:
            date = shift['date']
            shifts_per_day[date] = shifts_per_day.get(date, 0) + 1

        all_dates = sorted(shifts_per_day.keys())

        # 60% de conductores con patrones FIJOS
        num_fixed = int(num_drivers * 0.6)

        driver_patterns = {}

        # PARTE 1: Conductores con patrones FIJOS (estructura base)
        print(f"\n  Creando patrones híbridos:")
        print(f"    - {num_fixed} conductores con patrón fijo (60%)")
        print(f"    - {num_drivers - num_fixed} conductores flexibles (40%)")

        # Distribuir conductores fijos entre los ciclos disponibles
        valid_cycles = [7, 14, 10, 8]  # Priorizados por uso común

        for d_idx in range(num_fixed):
            # Alternar entre ciclos para maximizar cobertura
            cycle = valid_cycles[d_idx % len(valid_cycles)]

            # Escalonar offsets para que siempre haya conductores disponibles
            # Por ejemplo, con 7x7: offsets 0, 3, 7, 10, 14... (cada ~3-4 días)
            offset_step = max(1, (2 * cycle) // (num_fixed // len(valid_cycles) + 1))
            offset = (d_idx // len(valid_cycles) * offset_step) % (2 * cycle)

            driver_patterns[d_idx] = {
                'fixed': True,
                'cycle': cycle,
                'offset': offset
            }

        # PARTE 2: Conductores FLEXIBLES (solver elige)
        for d_idx in range(num_fixed, num_drivers):
            driver_patterns[d_idx] = {
                'fixed': False,
                'cycle': None,
                'offset': None
            }

        # Mostrar distribución
        cycle_counts = {}
        for pattern in driver_patterns.values():
            if pattern['fixed']:
                cycle = pattern['cycle']
                cycle_counts[cycle] = cycle_counts.get(cycle, 0) + 1

        print(f"    Distribución de patrones fijos:")
        for cycle in sorted(cycle_counts.keys()):
            print(f"      - {cycle}x{cycle}: {cycle_counts[cycle]} conductores")

        return driver_patterns

    def _solve_with_cpsat(self, all_shifts: List[Dict],
                         num_drivers: int, year: int, month: int, min_drivers: int = 0,
                         driver_patterns: Dict[int, Dict] = None) -> Dict[str, Any]:
        """
        Resuelve usando CP-SAT con restricciones diferenciadas por régimen

        Args:
            driver_patterns: Patrones híbridos (fijos + flexibles) para Faena Minera
        """
        model = cp_model.CpModel()
        
        # Variables de decisión: X[driver][shift] = 1 si el conductor toma el turno
        X = {}
        for d_idx in range(num_drivers):
            for s_idx, shift in enumerate(all_shifts):
                X[d_idx, s_idx] = model.NewBoolVar(f'x_{d_idx}_{s_idx}')
        
        # RESTRICCIÓN 1: Cada turno debe ser cubierto por exactamente un conductor
        for s_idx in range(len(all_shifts)):
            model.Add(sum(X[d_idx, s_idx] for d_idx in range(num_drivers)) == 1)
        
        # RESTRICCIÓN 2: No solapamiento de turnos
        overlaps = self._calculate_overlaps(all_shifts)
        for d_idx in range(num_drivers):
            for s1_idx in range(len(all_shifts)):
                for s2_idx in overlaps.get(s1_idx, []):
                    if s1_idx < s2_idx:
                        model.Add(X[d_idx, s1_idx] + X[d_idx, s2_idx] <= 1)
        
        # RESTRICCIONES ESPECÍFICAS DEL RÉGIMEN
        self._add_regime_specific_constraints(model, X, all_shifts, num_drivers, driver_patterns)
        
        # Minimizar número de conductores utilizados
        drivers_used = []
        for d_idx in range(num_drivers):
            driver_used = model.NewBoolVar(f'driver_used_{d_idx}')
            model.AddMaxEquality(driver_used, [X[d_idx, s_idx] for s_idx in range(len(all_shifts))])
            drivers_used.append(driver_used)
        
        model.Minimize(sum(drivers_used))
        
        # Resolver con parámetros optimizados para encontrar soluciones más rápido
        solver = cp_model.CpSolver()

        # TIMEOUT AGRESIVO: Adaptativo según régimen y cercanía al óptimo
        remaining_time = self.timeout - (time.time() - self.start_time)

        if self.regime in ['Faena Minera', 'Minera']:
            # ESTRATEGIA: Timeout corto inicial, aumenta si parece prometedor
            # Esto evita quedarse atascado en soluciones infactibles

            # Calcular distancia al mínimo esperado
            distance_from_min = abs(num_drivers - min_drivers) / max(min_drivers, 1)

            if distance_from_min > 0.5:
                # Muy lejos del óptimo (>50% diferencia), fallar MUY rápido
                timeout_per_attempt = min(10.0, remaining_time)
            elif distance_from_min > 0.2:
                # Rango medio (20-50% diferencia), tiempo moderado
                timeout_per_attempt = min(20.0, remaining_time)
            else:
                # Cerca del óptimo (<20% diferencia), dar más tiempo
                timeout_per_attempt = min(45.0, remaining_time)

            solver.parameters.max_time_in_seconds = timeout_per_attempt

            # Agregar límite de soluciones: parar al encontrar la primera factible
            # Esto acelera mucho cuando solo queremos saber si es factible o no
            solver.parameters.num_search_workers = 16  # Más workers
            solver.parameters.stop_after_first_solution = False  # Buscar óptimo local

        else:
            # Para regímenes no mineros: timeout diferenciado según complejidad
            # Todos los regímenes no mineros usan timeout de 60s
            timeout_per_attempt = min(60.0, remaining_time)

            solver.parameters.max_time_in_seconds = timeout_per_attempt
            solver.parameters.num_search_workers = 8  # Más workers para paralelizar
            solver.parameters.log_search_progress = False  # DESHABILITADO: Demasiado verbose
            solver.parameters.stop_after_first_solution = False  # Buscar solución óptima (no solo primera)

        # Estrategia de búsqueda optimizada según feedback
        if self.regime in ['Faena Minera', 'Minera']:
            # Para Faena Minera: estrategia agresiva de fallar rápido
            solver.parameters.linearization_level = 0
            solver.parameters.cp_model_presolve = False  # Desactivar presolve en minera
            solver.parameters.search_branching = cp_model.FIXED_SEARCH
            solver.parameters.log_search_progress = False
            solver.parameters.num_search_workers = 8
            solver.parameters.max_number_of_conflicts = 100000
        else:
            # Para otros regímenes: usar presolve y configuración estándar (MEJORA CLAVE)
            solver.parameters.cp_model_presolve = True  # HABILITAR presolve
            solver.parameters.linearization_level = 2  # Nivel estándar
            # El resto usa defaults de CP-SAT que son buenos

        # LOGGING: Mostrar estadísticas del modelo ANTES de resolver
        print(f"\n    📊 Estadísticas del modelo CP-SAT:")
        print(f"       Variables: ~{num_drivers * len(all_shifts):,} (asignaciones)")
        if driver_patterns:
            num_fixed = sum(1 for p in driver_patterns.values() if p and p.get('fixed'))
            num_flex = num_drivers - num_fixed
            print(f"       Patrones: {num_fixed} fijos + {num_flex} flexibles")
            print(f"       Variables patrón: ~{num_flex * 4:,} (4 opciones por flexible)")
        print(f"       Timeout: {solver.parameters.max_time_in_seconds:.1f}s")
        print(f"       Workers: {solver.parameters.num_search_workers}")

        # Resolver
        print(f"\n    🔍 Iniciando solver CP-SAT...")
        solve_start = time.time()
        status = solver.Solve(model)
        solve_time = time.time() - solve_start

        # LOGGING: Mostrar resultado del solver
        print(f"\n    ⏱️  Tiempo de solver: {solve_time:.2f}s")

        if status == cp_model.OPTIMAL:
            print(f"    ✓ Estado: OPTIMAL (solución óptima garantizada)")
        elif status == cp_model.FEASIBLE:
            print(f"    ✓ Estado: FEASIBLE (solución válida, posiblemente sub-óptima)")
        elif status == cp_model.INFEASIBLE:
            print(f"    ✗ Estado: INFEASIBLE (no existe solución con estas restricciones)")
        elif status == cp_model.MODEL_INVALID:
            print(f"    ✗ Estado: MODEL_INVALID (error en el modelo)")
        else:
            print(f"    ✗ Estado: UNKNOWN (timeout o error)")

        print(f"    📈 Best bound: {solver.BestObjectiveBound()}")
        print(f"    🎯 Objective value: {solver.ObjectiveValue() if status in [cp_model.OPTIMAL, cp_model.FEASIBLE] else 'N/A'}")
        print(f"    🔢 Branches: {solver.NumBranches():,}")
        print(f"    💾 Conflicts: {solver.NumConflicts():,}")
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # Extraer solución
            print(f"\n    🔄 Extrayendo asignaciones ({num_drivers} conductores × {len(all_shifts)} turnos)...")
            print(f"    ⚡ Usando extracción optimizada (diccionario inverso)...")
            extract_start = time.time()
            assignments = []
            driver_regimes = defaultdict(set)

            # OPTIMIZACIÓN RADICAL: Crear diccionario shift_idx -> driver_idx en una sola pasada
            # Esto evita llamar solver.Value() miles de veces buscando el conductor
            shift_to_driver = {}

            # Iterar por conductor (outer loop), luego por turno (inner loop)
            # Esto es más cache-friendly y reduce llamadas a solver.Value()
            print(f"    📋 Paso 1/2: Construyendo mapeo turno→conductor...")
            for d_idx in range(num_drivers):
                for s_idx in range(len(all_shifts)):
                    if solver.Value(X[d_idx, s_idx]):
                        shift_to_driver[s_idx] = d_idx
                        # No break aquí porque necesitamos iterar todos de todos modos

            print(f"    📝 Paso 2/2: Creando asignaciones desde mapeo...")
            # Ahora construir assignments desde el diccionario (sin más solver.Value())
            for s_idx, shift in enumerate(all_shifts):
                if s_idx in shift_to_driver:
                    assigned_driver = shift_to_driver[s_idx]
                    assignments.append({
                        'date': shift['date'].isoformat(),
                        'service': shift['service_id'],
                        'service_name': shift['service_name'],
                        'service_type': shift['service_type'],
                        'service_group': shift.get('service_group'),
                        'shift': shift['shift_number'],
                        'vehicle': shift['vehicle'],
                        'driver_id': f'D{assigned_driver+1:03d}',
                        'driver_name': f'Conductor {assigned_driver+1}',
                        'start_time': shift['start_time'],
                        'end_time': shift['end_time'],
                        'duration_hours': shift['duration_hours'],
                        'vehicle_type': shift.get('vehicle_type'),
                        'vehicle_category': shift.get('vehicle_category')
                    })
                    driver_regimes[assigned_driver].add(shift['service_type'])
            
            # Análisis del régimen único
            regime_analysis = {
                self.regime: {
                    'drivers': len(set(a['driver_id'] for a in assignments)),
                    'shifts': len(assignments)
                }
            }
            
            # Calcular driver_summary para los reportes
            driver_summary = {}
            for assignment in assignments:
                driver_id = assignment['driver_id']
                if driver_id not in driver_summary:
                    driver_summary[driver_id] = {
                        'driver_id': driver_id,
                        'driver_name': assignment['driver_name'],
                        'name': assignment['driver_name'],
                        'total_hours': 0,
                        'total_shifts': 0,
                        'sundays_worked_set': set(),  # Usar set para días únicos
                        'dates_worked': set(),
                        'contract_type': 'fixed_term',  # Por defecto
                        'regime': self.regime,  # Agregar régimen laboral
                        'services': set(),
                        'vehicle_categories': set(),
                        'vehicle_types': set(),
                        'shifts': []
                    }
                
                driver_summary[driver_id]['total_hours'] += assignment['duration_hours']
                driver_summary[driver_id]['total_shifts'] += 1
                driver_summary[driver_id]['services'].add(assignment['service'])
                driver_summary[driver_id]['vehicle_categories'].add(assignment.get('vehicle_category', 'other'))
                driver_summary[driver_id]['vehicle_types'].add(assignment.get('vehicle_type', 'unknown'))
                # Guardar referencia del turno original para cálculo de costos
                driver_summary[driver_id]['shifts'].append({
                    'duration_hours': assignment['duration_hours'],
                    'vehicle_category': assignment.get('vehicle_category'),
                    'vehicle_type': assignment.get('vehicle_type')
                })
                
                # Contar domingos únicos (no turnos en domingo)
                date_obj = datetime.fromisoformat(assignment['date'])
                driver_summary[driver_id]['dates_worked'].add(date_obj.date())
                if date_obj.weekday() == 6:  # Domingo
                    driver_summary[driver_id]['sundays_worked_set'].add(date_obj.date())
            
            # Convertir sets a listas para serialización y calcular métricas finales
            overall_cost = 0.0
            for driver_id in driver_summary:
                driver_summary[driver_id]['dates_worked'] = sorted(list(driver_summary[driver_id]['dates_worked']))
                driver_summary[driver_id]['days_worked'] = len(driver_summary[driver_id]['dates_worked'])
                driver_summary[driver_id]['services_worked'] = sorted(list(driver_summary[driver_id]['services']))
                driver_summary[driver_id]['vehicle_categories'] = sorted(list(driver_summary[driver_id]['vehicle_categories']))
                driver_summary[driver_id]['vehicle_types'] = sorted(list(driver_summary[driver_id]['vehicle_types']))
                # Convertir set de domingos a conteo
                driver_summary[driver_id]['sundays_worked'] = len(driver_summary[driver_id]['sundays_worked_set'])
                del driver_summary[driver_id]['sundays_worked_set']  # Eliminar el set temporal

                # Detectar patrón de trabajo según régimen
                if self.regime == 'Faena Minera':
                    pattern = self._detect_minera_pattern(driver_summary[driver_id]['dates_worked'], year, month)
                else:
                    pattern = self._detect_regular_pattern(driver_summary[driver_id]['dates_worked'], year, month)
                driver_summary[driver_id]['pattern'] = pattern
                
                # CALCULAR UTILIZACIÓN Y COSTO
                total_hours = driver_summary[driver_id]['total_hours']
                max_hours = 180 if self.regime == 'Interurbano' else 176  # 44h * 4 semanas
                utilization = (total_hours / max_hours * 100) if max_hours > 0 else 0
                driver_summary[driver_id]['utilization'] = round(utilization, 1)
                
                cost_details = self._compute_driver_cost(driver_summary[driver_id])
                driver_summary[driver_id]['salary'] = round(cost_details['total_cost'])
                driver_summary[driver_id]['cost_details'] = {
                    'base_cost': round(cost_details['base_cost']),
                    'vehicle_adjusted_cost': round(cost_details['vehicle_adjusted_cost']),
                    'driver_multiplier': cost_details['driver_multiplier'],
                    'service_multiplier': cost_details['service_multiplier'],
                    'service_count': cost_details['service_count']
                }
                overall_cost += cost_details['total_cost']
                driver_summary[driver_id].pop('services', None)
                driver_summary[driver_id].pop('shifts', None)

            # Calcular métricas
            total_hours = sum(a['duration_hours'] for a in assignments)
            drivers_used_count = len(driver_summary)

            service_warnings = self._detect_service_span_warnings(all_shifts)

            extract_time = time.time() - extract_start
            print(f"    ✓ Extracción completada en {extract_time:.2f}s ({len(assignments)} asignaciones)\n")

            result = {
                'status': 'success',
                'assignments': assignments,
                'metrics': {
                    'drivers_used': drivers_used_count,
                    'total_hours': total_hours,
                    'total_cost': round(overall_cost),
                    'avg_hours_per_driver': total_hours / drivers_used_count if drivers_used_count > 0 else 0
                },
                'driver_summary': driver_summary,  # Agregar para los reportes
                'regime_analysis': regime_analysis,
                'regime': self.regime,  # Agregar régimen para los reportes
                'regime_constraints': {  # Agregar detalles de restricciones
                    'name': self.regime_constraints.name,
                    'max_weekly_hours': self.regime_constraints.max_weekly_hours,
                    'max_monthly_hours': self.regime_constraints.max_monthly_hours,
                    'max_continuous_driving': self.regime_constraints.max_continuous_driving_hours,
                    'max_consecutive_days': self.regime_constraints.max_consecutive_days,
                    'min_free_sundays': self.regime_constraints.min_free_sundays
                },
                'driver_regimes': dict(driver_regimes),  # Qué regímenes maneja cada conductor
                'solver_status': 'optimal' if status == cp_model.OPTIMAL else 'feasible'
            }

            if service_warnings:
                result['warnings'] = {'service_spans': service_warnings}

            return result
        
        return {'status': 'failed'}
    
    def _add_regime_specific_constraints(self, model: cp_model.CpModel, X: Dict,
                                        all_shifts: List[Dict],
                                        num_drivers: int,
                                        driver_patterns: Dict[int, Dict] = None):
        """Agrega restricciones laborales generales y específicas del régimen"""

        # Primero agregar restricciones laborales GENERALES para TODOS los conductores
        self._add_general_labor_constraints(model, X, all_shifts, num_drivers)

        # Luego agregar restricciones ESPECÍFICAS según el régimen
        if self.regime == 'Interurbano':
            # Restricciones específicas de interurbano para todos los conductores
            for d_idx in range(num_drivers):
                shifts_with_idx = [(s_idx, shift) for s_idx, shift in enumerate(all_shifts)]
                self._add_interurbano_constraints(model, X, d_idx, shifts_with_idx)

        elif self.regime in ['Industrial', 'Urbano', 'Interno']:
            # Restricciones urbanas/industriales (incluye colación de 60 min)
            for d_idx in range(num_drivers):
                shifts_with_idx = [(s_idx, shift) for s_idx, shift in enumerate(all_shifts)]
                self._add_urban_constraints(model, X, d_idx, shifts_with_idx)

        elif self.regime == 'Interurbano Bisemanal':
            # TODO: Implementar ciclos especiales (4x3, 7x7, etc.)
            pass

        elif self.regime in ['Faena Minera', 'Minera']:
            # Restricciones de faena minera (Art. 38) con patrones híbridos
            for d_idx in range(num_drivers):
                shifts_with_idx = [(s_idx, shift) for s_idx, shift in enumerate(all_shifts)]
                driver_pattern = driver_patterns.get(d_idx) if driver_patterns else None
                self._add_faena_minera_constraints(model, X, d_idx, shifts_with_idx, driver_pattern)
    
    def _add_general_labor_constraints(self, model: cp_model.CpModel, X: Dict,
                                      all_shifts: List[Dict], num_drivers: int):
        """Agrega restricciones laborales generales aplicables a todos los regímenes"""

        # Obtener fechas únicas
        dates = sorted(list(set(shift['date'] for shift in all_shifts)))

        for d_idx in range(num_drivers):
            # RESTRICCIÓN 3: Máximo 6 días consecutivos de trabajo
            # (NO aplica para Faena Minera que tiene ciclos específicos)
            if self.regime not in ['Faena Minera', 'Minera']:
                for start_idx in range(len(dates) - 6):
                    consecutive_days = []
                    for day_offset in range(7):  # 7 días consecutivos
                        date = dates[start_idx + day_offset]
                        day_shifts = [s_idx for s_idx, s in enumerate(all_shifts) if s['date'] == date]
                        # Si trabaja algún turno ese día
                        works_that_day = model.NewBoolVar(f'works_d{d_idx}_date_{date}')
                        model.AddMaxEquality(works_that_day, [X[d_idx, s_idx] for s_idx in day_shifts])
                        consecutive_days.append(works_that_day)

                    # Máximo 6 de 7 días consecutivos pueden ser trabajados
                    model.Add(sum(consecutive_days) <= 6)

            # RESTRICCIÓN 4: Mínimo 2 domingos libres al mes
            # (NO aplica para Faena Minera con autorización para trabajar domingos)
            if self.regime_constraints.min_free_sundays is not None:
                sunday_dates = [d for d in dates if d.weekday() == 6]
                sunday_work_vars = []
                for sunday in sunday_dates:
                    sunday_shifts = [s_idx for s_idx, s in enumerate(all_shifts) if s['date'] == sunday]
                    if sunday_shifts:
                        works_sunday = model.NewBoolVar(f'works_sunday_d{d_idx}_{sunday}')
                        model.AddMaxEquality(works_sunday, [X[d_idx, s_idx] for s_idx in sunday_shifts])
                        sunday_work_vars.append(works_sunday)

                # Mínimo 2 domingos libres = máximo (total_domingos - 2) domingos trabajados
                min_free_sundays = self.regime_constraints.min_free_sundays
                if len(sunday_dates) > min_free_sundays:
                    max_sundays_worked = len(sunday_dates) - min_free_sundays
                    model.Add(sum(sunday_work_vars) <= max_sundays_worked)
            
            # RESTRICCIÓN 5: Límites de horas según régimen
            # NOTA: Faena Minera NO tiene límite semanal estricto (trabajan 7x12h = 84h/semana en ciclo)
            if self.regime not in ['Faena Minera', 'Minera']:
                if self.regime_constraints.max_weekly_hours:
                    # Restricción semanal (Industrial/Urbano)
                    self._add_weekly_hours_constraint(model, X, d_idx, all_shifts)
                elif self.regime_constraints.max_monthly_hours:
                    # Restricción mensual (Interurbano)
                    self._add_monthly_hours_constraint(model, X, d_idx, all_shifts)
            
            # RESTRICCIÓN 6: Descanso mínimo entre jornadas
            self._add_rest_between_shifts_constraint(model, X, d_idx, all_shifts)
    
    def _add_weekly_hours_constraint(self, model: cp_model.CpModel, X: Dict,
                                    driver_idx: int, all_shifts: List[Dict]):
        """Restricción de máximo 44 horas semanales"""
        max_weekly = int(self.regime_constraints.max_weekly_hours * 60)  # En minutos
        
        # Agrupar por semanas
        weeks = defaultdict(list)
        for s_idx, shift in enumerate(all_shifts):
            week_num = (shift['date'].day - 1) // 7 + 1
            weeks[week_num].append((s_idx, shift['duration_hours']))
        
        for week_num, week_shifts in weeks.items():
            week_minutes = sum(
                X[driver_idx, s_idx] * int(hours * 60)
                for s_idx, hours in week_shifts
            )
            model.Add(week_minutes <= max_weekly)
    
    def _add_monthly_hours_constraint(self, model: cp_model.CpModel, X: Dict,
                                     driver_idx: int, all_shifts: List[Dict]):
        """Restricción de máximo 180 horas mensuales (Interurbano)"""
        max_monthly = int(self.regime_constraints.max_monthly_hours * 60)  # En minutos
        
        total_minutes = sum(
            X[driver_idx, s_idx] * int(shift['duration_hours'] * 60)
            for s_idx, shift in enumerate(all_shifts)
        )
        model.Add(total_minutes <= max_monthly)
    
    def _add_rest_between_shifts_constraint(self, model: cp_model.CpModel, X: Dict,
                                           driver_idx: int, all_shifts: List[Dict]):
        """Restricción de descanso mínimo entre jornadas"""
        min_rest_hours = self.regime_constraints.min_rest_between_shifts
        
        # Evaluar descansos entre pares de turnos que puede tomar un mismo conductor
        shifts_with_index = list(enumerate(all_shifts))

        transfer_minutes = 60  # Tiempo mínimo de traslado entre servicios del mismo grupo

        for s1_idx, shift1 in shifts_with_index:
            for s2_idx, shift2 in shifts_with_index:
                if s1_idx == s2_idx:
                    continue

                day_diff = (shift2['date'] - shift1['date']).days

                # Sólo comparar turnos dentro del mismo día o en el día siguiente
                if day_diff < 0 or day_diff > 1:
                    continue

                # Si es el mismo día, garantizar que analizamos s1 antes que s2 cronológicamente
                if day_diff == 0 and shift2['start_minutes'] <= shift1['start_minutes']:
                    continue

                # Calcular descanso disponible entre el fin de s1 y el inicio de s2
                end_minutes = shift1['end_minutes']
                start_minutes = shift2['start_minutes'] + day_diff * 24 * 60

                rest_minutes = start_minutes - end_minutes

                if rest_minutes < 0:
                    continue  # Turnos traslapados (ya cubierto por restricciones de solape)

                rest_hours = rest_minutes / 60

                if day_diff == 0:
                    group1 = shift1.get('service_group') or shift1['service_id']
                    group2 = shift2.get('service_group') or shift2['service_id']

                    if group1 != group2:
                        model.Add(X[driver_idx, s1_idx] + X[driver_idx, s2_idx] <= 1)
                    elif rest_minutes < transfer_minutes:
                        model.Add(X[driver_idx, s1_idx] + X[driver_idx, s2_idx] <= 1)
                else:  # day_diff == 1
                    if rest_hours < min_rest_hours:
                        model.Add(X[driver_idx, s1_idx] + X[driver_idx, s2_idx] <= 1)
    
    def _add_interurbano_constraints(self, model: cp_model.CpModel, X: Dict,
                                    driver_idx: int, shifts: List[Tuple[int, Dict]]):
        """Restricciones específicas para régimen interurbano
        
        IMPORTANTE: Las restricciones se interpretan correctamente según la normativa:
        - Máximo 5 horas de conducción CONTINUA (sin descanso)
        - Un descanso de 2+ horas REINICIA el contador de conducción continua
        - Permite jornadas de hasta 16 horas con descansos intercalados
        - Un conductor PUEDE hacer múltiples turnos si hay descanso adecuado
        """
        constraints = self.regime_constraints
        
        # Agrupar turnos por día
        shifts_by_date = defaultdict(list)
        for s_idx, shift in shifts:
            shifts_by_date[shift['date']].append((s_idx, shift))
        
        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) <= 1:
                continue
                
            # Ordenar por hora de inicio
            day_shifts.sort(key=lambda x: x[1]['start_minutes'])
            
            # RESTRICCIÓN CLAVE: Un conductor PUEDE tomar múltiples turnos en el día
            # siempre que:
            # 1. No supere 5h de conducción continua sin descanso de 2h
            # 2. El span total no exceda 16h
            # 3. Haya descanso adecuado entre turnos
            
            # Analizar combinaciones de turnos válidas
            for i in range(len(day_shifts)):
                s_idx_i, shift_i = day_shifts[i]
                
                for j in range(i + 1, len(day_shifts)):
                    s_idx_j, shift_j = day_shifts[j]
                    
                    # Calcular gap entre turnos
                    gap_minutes = shift_j['start_minutes'] - shift_i['end_minutes']
                    
                    # Si los turnos se solapan, no pueden ser asignados al mismo conductor
                    if gap_minutes < 0:
                        model.Add(X[driver_idx, s_idx_i] + X[driver_idx, s_idx_j] <= 1)
                        continue
                    
                    # Calcular conducción acumulada y span total
                    if shift_i['duration_hours'] <= 5.0 and shift_j['duration_hours'] <= 5.0:
                        # Ambos turnos individualmente cumplen con las 5h máx
                        
                        # Si hay menos de 2 horas de descanso entre turnos
                        if gap_minutes < 120:
                            # Verificar si la conducción continua excedería 5h
                            total_continuous = shift_i['duration_hours'] + shift_j['duration_hours']
                            if total_continuous > 5.0:
                                # No puede hacer ambos sin descanso de 2h
                                model.Add(X[driver_idx, s_idx_i] + X[driver_idx, s_idx_j] <= 1)
                                continue
                        
                        # Si hay 2+ horas de descanso, el contador se reinicia
                        # Verificar solo el span total de la jornada
                        total_span = (shift_j['end_minutes'] - shift_i['start_minutes']) / 60.0
                        
                        if total_span > 16.0:
                            # Excede el span máximo de 16h
                            model.Add(X[driver_idx, s_idx_i] + X[driver_idx, s_idx_j] <= 1)
                        # Si total_span <= 16h, el conductor PUEDE hacer ambos turnos
                        # No agregamos restricción, permitiendo la asignación
                    
                    else:
                        # Si algún turno individual ya excede 5h
                        # (no debería pasar en datos bien formados)
                        if shift_i['duration_hours'] > 5.0 or shift_j['duration_hours'] > 5.0:
                            # Requerir descanso obligatorio de 2h entre ellos
                            if gap_minutes < 120:
                                model.Add(X[driver_idx, s_idx_i] + X[driver_idx, s_idx_j] <= 1)
            
            # Restricción adicional: verificar combinaciones de 3+ turnos
            # para asegurar que no se violen las restricciones con múltiples asignaciones
            if len(day_shifts) >= 3:
                for combination_size in range(3, min(len(day_shifts) + 1, 5)):
                    from itertools import combinations
                    for combo in combinations(range(len(day_shifts)), combination_size):
                        shifts_in_combo = [day_shifts[idx] for idx in combo]
                        
                        # Calcular span total
                        first_start = min(s[1]['start_minutes'] for s in shifts_in_combo)
                        last_end = max(s[1]['end_minutes'] for s in shifts_in_combo)
                        total_span = (last_end - first_start) / 60.0
                        
                        if total_span > 16.0:
                            # No puede hacer todos estos turnos
                            model.Add(sum(X[driver_idx, shifts_in_combo[idx][0]] 
                                        for idx in range(len(shifts_in_combo))) < len(shifts_in_combo))
    
    def _add_urban_constraints(self, model: cp_model.CpModel, X: Dict,
                              driver_idx: int, shifts: List[Tuple[int, Dict]]):
        """Restricciones específicas para régimen urbano/industrial

        Incluye:
        - Tiempo de colación obligatorio de 60 minutos para jornadas > 5 horas
        """
        # Agrupar turnos por día para verificar jornadas y colación
        shifts_by_date = defaultdict(list)
        for s_idx, shift in shifts:
            shifts_by_date[shift['date']].append((s_idx, shift))

        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) > 1:
                # Ordenar por hora de inicio
                day_shifts.sort(key=lambda x: x[1]['start_minutes'])

                # Si el conductor trabaja múltiples turnos en el día
                # debe tener al menos 60 minutos de colación entre turnos
                # si la jornada total supera 5 horas

                # Variables para rastrear si se asignan turnos
                day_assignments = [X[driver_idx, s_idx] for s_idx, _ in day_shifts]

                # Si trabaja más de un turno en el día
                works_multiple = model.NewBoolVar(f'works_multiple_d{driver_idx}_date{date}')
                model.Add(sum(day_assignments) >= 2).OnlyEnforceIf(works_multiple)
                model.Add(sum(day_assignments) <= 1).OnlyEnforceIf(works_multiple.Not())

                # Si trabaja múltiples turnos, verificar colación
                if len(day_shifts) > 1:
                    for i in range(len(day_shifts) - 1):
                        s_idx1, shift1 = day_shifts[i]
                        s_idx2, shift2 = day_shifts[i + 1]

                        # Gap entre turnos (en minutos)
                        gap_minutes = shift2['start_minutes'] - shift1['end_minutes']

                        # Si ambos turnos se asignan al conductor
                        both_assigned = model.NewBoolVar(f'both_d{driver_idx}_s{s_idx1}_s{s_idx2}')
                        model.Add(X[driver_idx, s_idx1] + X[driver_idx, s_idx2] == 2).OnlyEnforceIf(both_assigned)
                        model.Add(X[driver_idx, s_idx1] + X[driver_idx, s_idx2] <= 1).OnlyEnforceIf(both_assigned.Not())

                        # Si trabaja ambos turnos y la jornada total > 5h, necesita 60 min de colación
                        total_hours = shift1['duration_hours'] + shift2['duration_hours']
                        if total_hours > 5.0 and gap_minutes < 60:
                            # No puede hacer ambos turnos si no hay suficiente tiempo para colación
                            model.Add(X[driver_idx, s_idx1] + X[driver_idx, s_idx2] <= 1)

    def _add_faena_minera_constraints(self, model: cp_model.CpModel, X: Dict,
                                     driver_idx: int, shifts: List[Tuple[int, Dict]],
                                     driver_pattern: Dict = None):
        """Restricciones específicas para régimen de Faena Minera (Art. 38)

        ENFOQUE HÍBRIDO:
        - Si driver_pattern['fixed'] == True: Aplica patrón pre-asignado (más rápido)
        - Si driver_pattern['fixed'] == False: Solver elige entre 4 opciones (flexible)
        """
        constraints = self.regime_constraints

        # Obtener todas las fechas únicas
        all_dates = sorted(list(set(shift['date'] for _, shift in shifts)))

        if not all_dates:
            return

        # Agrupar turnos por fecha
        shifts_by_date = defaultdict(list)
        for s_idx, shift in shifts:
            shifts_by_date[shift['date']].append((s_idx, shift))

        # Crear variables booleanas para cada día (trabaja/no trabaja)
        works_on_day = {}
        for date in all_dates:
            day_shift_indices = [s_idx for s_idx, _ in shifts_by_date.get(date, [])]
            if day_shift_indices:
                works_on_day[date] = model.NewBoolVar(f'minera_works_d{driver_idx}_date{date}')
                model.AddMaxEquality(works_on_day[date], [X[driver_idx, s_idx] for s_idx in day_shift_indices])

        # CASO 1: CONDUCTOR CON PATRÓN FIJO
        if driver_pattern and driver_pattern.get('fixed'):
            cycle_len = driver_pattern['cycle']
            offset = driver_pattern['offset']

            # Aplicar patrón fijo directamente (sin variables booleanas)
            for day_idx, date in enumerate(all_dates):
                days_from_start = (day_idx + offset) % (2 * cycle_len)
                should_work = days_from_start < cycle_len

                day_shifts = shifts_by_date.get(date, [])
                if day_shifts and not should_work:
                    # DEBE descansar este día (restricción dura)
                    for s_idx, _ in day_shifts:
                        model.Add(X[driver_idx, s_idx] == 0)

        # CASO 2: CONDUCTOR FLEXIBLE (solver elige patrón)
        else:
            # Solo generar 4 patrones (uno por ciclo, offset=0)
            # Esto reduce de 39 variables a 4 por conductor flexible
            valid_cycles = [7, 8, 10, 14]
            pattern_vars = []

            for cycle_len in valid_cycles:
                # Solo offset=0 para reducir complejidad
                pattern_var = model.NewBoolVar(f'flex_pattern_d{driver_idx}_c{cycle_len}')
                pattern_vars.append(pattern_var)

                # Si elige este patrón, debe seguirlo
                for day_idx, date in enumerate(all_dates):
                    days_from_start = day_idx % (2 * cycle_len)
                    should_work = days_from_start < cycle_len

                    day_shifts = shifts_by_date.get(date, [])
                    if day_shifts and not should_work:
                        # Si elige este patrón, DEBE descansar
                        for s_idx, _ in day_shifts:
                            model.Add(X[driver_idx, s_idx] == 0).OnlyEnforceIf(pattern_var)

            # Debe elegir exactamente UN patrón si trabaja
            any_work = model.NewBoolVar(f'any_work_d{driver_idx}')
            all_work_vars = [v for v in works_on_day.values() if v is not None]
            if all_work_vars:
                model.AddMaxEquality(any_work, all_work_vars)
                model.Add(sum(pattern_vars) == 1).OnlyEnforceIf(any_work)
                model.Add(sum(pattern_vars) == 0).OnlyEnforceIf(any_work.Not())

        # RESTRICCIÓN CRÍTICA: Máximo 14 horas CONSECUTIVAS (span desde primer turno hasta último)
        # Esto asegura 10h de descanso antes de volver a trabajar
        max_span_minutes = int(constraints.max_daily_hours * 60)  # 14h = 840 min

        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) < 2:
                # Solo un turno, verificar que no exceda 14h de duración
                if day_shifts:
                    s_idx, shift = day_shifts[0]
                    duration_min = int(shift['duration_hours'] * 60)
                    # Solo aplicar si el conductor toma este turno
                    model.Add(duration_min <= max_span_minutes).OnlyEnforceIf(X[driver_idx, s_idx])
                continue

            # Para múltiples turnos, verificar span total (inicio más temprano - fin más tardío)
            # Crear variables para inicio/fin efectivos
            min_start = min(shift['start_minutes'] for _, shift in day_shifts)
            max_end = max(shift['end_minutes'] for _, shift in day_shifts)

            # Calcular span (manejar cruce de medianoche)
            if max_end < min_start:
                # Cruza medianoche
                span = (1440 - min_start) + max_end
            else:
                span = max_end - min_start

            # Si toma ALGÚN turno ese día, el span debe ser ≤ 14h
            works_any_shift = model.NewBoolVar(f'works_any_d{driver_idx}_date{date}')
            model.AddMaxEquality(works_any_shift, [X[driver_idx, s_idx] for s_idx, _ in day_shifts])

            # NOTA: La restricción de span es compleja de modelar en CP-SAT porque requiere
            # saber qué combinación de turnos toma el conductor (no todos).
            # Por ahora, dejamos que el greedy y la validación final verifiquen el span.
            # TODO: Implementar restricción de span correctamente en CP-SAT usando variables auxiliares

            # if span > max_span_minutes:
            #     # Esta restricción es demasiado restrictiva - prohibe TODO el día
            #     model.Add(works_any_shift == 0)

        # RESTRICCIÓN CRÍTICA: Un conductor NO puede cambiar de grupo en el mismo día
        # Los grupos están en ubicaciones geográficas diferentes y los tiempos de traslado
        # lo hacen imposible (puede tomar horas ir de un grupo a otro)
        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) < 2:
                continue  # Solo un turno, no hay posibilidad de cambio

            # Agrupar turnos del día por grupo
            groups_in_day = defaultdict(list)
            for s_idx, shift in day_shifts:
                group = shift.get('service_group', 'DEFAULT')
                groups_in_day[group].append(s_idx)

            # Si hay múltiples grupos disponibles ese día, asegurar que el conductor
            # solo trabaje en UN grupo
            if len(groups_in_day) > 1:
                # Para cada grupo, crear variable booleana: trabaja en este grupo hoy
                group_vars = []
                for group, shift_indices in groups_in_day.items():
                    works_in_group = model.NewBoolVar(f'works_d{driver_idx}_date{date}_group{group}')
                    # works_in_group = 1 si trabaja ALGÚN turno de este grupo
                    model.AddMaxEquality(works_in_group, [X[driver_idx, s_idx] for s_idx in shift_indices])
                    group_vars.append(works_in_group)

                # Puede trabajar en MÁXIMO un grupo por día
                model.Add(sum(group_vars) <= 1)
    
    def _calculate_overlaps(self, shifts: List[Dict]) -> Dict[int, List[int]]:
        """Calcula qué turnos se solapan"""
        overlaps = defaultdict(list)
        
        for i in range(len(shifts)):
            for j in range(i + 1, len(shifts)):
                if self._shifts_overlap(shifts[i], shifts[j]):
                    overlaps[i].append(j)
                    overlaps[j].append(i)
        
        return dict(overlaps)
    
    def _shifts_overlap(self, shift1: Dict, shift2: Dict) -> bool:
        """Verifica si dos turnos se solapan"""
        if shift1['date'] != shift2['date']:
            return False
        
        # Los turnos se solapan si uno empieza antes de que termine el otro
        return not (shift1['end_minutes'] <= shift2['start_minutes'] or 
                   shift2['end_minutes'] <= shift1['start_minutes'])

    def _greedy_assignment_no_cycles(self, all_shifts: List[Dict], year: int, month: int) -> Dict[str, Any]:
        """
        Greedy para regímenes SIN ciclos fijos (Urbano/Industrial/Interurbano).

        Estrategia:
        - Asignar día por día
        - Crear conductores según demanda
        - Respetar: 44h semanales, 10h diarias, 10h descanso, max 6 días consecutivos, min 2 domingos libres
        - No asumir patrón NxN fijo

        Returns:
            Dict con status, assignments, driver_summary, etc.
        """
        print(f"\n    🔧 Construyendo solución greedy sin ciclos fijos...")

        # Agrupar turnos por fecha
        shifts_by_date = defaultdict(list)
        for shift in all_shifts:
            date_obj = datetime.fromisoformat(shift['date']).date() if isinstance(shift['date'], str) else shift['date']
            shifts_by_date[date_obj].append(shift)

        # Ordenar fechas
        sorted_dates = sorted(shifts_by_date.keys())

        # Inicializar estructuras
        drivers = {}
        driver_counter = 0
        assignments = []

        # Procesar día por día
        total_days = len(sorted_dates)
        for day_idx, date in enumerate(sorted_dates):
            day_shifts = shifts_by_date[date]

            # Mostrar progreso cada 5 días o días especiales
            if day_idx % 5 == 0 or day_idx == 0 or day_idx == total_days - 1:
                print(f"\n      📅 Procesando día {day_idx + 1}/{total_days} ({date}): {len(day_shifts)} turnos, {len(drivers)} conductores activos")

            # Ordenar turnos del día por hora de inicio
            day_shifts.sort(key=lambda s: s['start_minutes'])

            unassigned = day_shifts[:]

            # Determinar conductores disponibles hoy
            # Disponibles = los que pueden trabajar (no han superado límites)
            available_drivers = []
            unavailable_count = 0
            for driver_id, driver_info in drivers.items():
                # Verificar si puede trabajar hoy
                can_work = self._can_driver_work_today_no_cycles(driver_info, date)
                if can_work:
                    available_drivers.append(driver_id)
                else:
                    unavailable_count += 1

            # MEJORA: Ordenar conductores disponibles por días consecutivos trabajados (ASCENDENTE)
            # Esto distribuye la carga: primero usan conductores con menos días consecutivos
            # Permite que algunos lleguen a 6 días mientras otros recién empiezan
            # Resultado: descansos escalonados en lugar de todos el mismo día
            available_drivers.sort(key=lambda d_id: drivers[d_id]['consecutive_days'])

            # Intentar asignar con conductores existentes
            for driver_id in available_drivers:
                if not unassigned:
                    break

                driver = drivers[driver_id]
                assigned_count = self._assign_shifts_to_driver_no_cycles(
                    driver, date, unassigned, assignments
                )

            # Si quedan turnos, crear nuevos conductores
            max_new_drivers_per_day = 50  # SAFETY: Limitar creación de conductores por día
            new_drivers_created = 0

            while unassigned and new_drivers_created < max_new_drivers_per_day:
                driver_counter += 1
                driver_id = driver_counter
                new_drivers_created += 1

                drivers[driver_id] = {
                    'assignments': [],
                    'work_days': [],
                    'last_shift_date': None,
                    'consecutive_days': 0,
                    'sundays_worked': 0
                }

                assigned_count = self._assign_shifts_to_driver_no_cycles(
                    drivers[driver_id], date, unassigned, assignments
                )

                if assigned_count > 0:
                    print(f"          D{driver_id:03d} (NUEVO): {assigned_count} turnos")
                else:
                    # No pudo asignar nada, algo está mal
                    print(f"          ⚠️ No se pudo asignar ningún turno al nuevo conductor D{driver_id:03d}")
                    print(f"          ⚠️ Turnos restantes: {len(unassigned)}")
                    if unassigned:
                        print(f"          ⚠️ Ejemplo turno: {unassigned[0]['service_name']} {unassigned[0]['start_time']}-{unassigned[0]['end_time']}")
                    break

            if unassigned and new_drivers_created >= max_new_drivers_per_day:
                print(f"          ⚠️ SAFETY LIMIT: Alcanzado máximo de {max_new_drivers_per_day} conductores nuevos por día")
                print(f"          ⚠️ Turnos sin asignar: {len(unassigned)}")
                break  # Salir del loop principal de días

        # Calcular cobertura
        total_shifts = len(all_shifts)
        covered = len(assignments)
        coverage = covered / total_shifts if total_shifts > 0 else 0.0

        print(f"\n      ✅ Greedy completado:")
        print(f"         Conductores: {driver_counter}")
        print(f"         Turnos asignados: {covered}/{total_shifts} ({coverage*100:.1f}%)")
        print(f"         Días procesados: {total_days}")

        # Convertir al formato estándar
        return self._convert_greedy_no_cycles_to_standard(
            drivers, assignments, driver_counter, coverage, year, month
        )

    def _can_driver_work_today_no_cycles(self, driver: Dict, date: date) -> bool:
        """
        Verifica si un conductor puede trabajar hoy según restricciones sin ciclos fijos.

        Estrategia 6x1 flexible:
        - Máximo 6 días consecutivos
        - Mínimo 2 domingos libres al mes
        - 44h semanales máximo
        - 10h descanso entre jornadas

        Returns:
            True si puede trabajar, False si no
        """
        # 1. Verificar días consecutivos (máximo 6)
        # IMPORTANTE: Solo si ayer trabajó. Si ha descansado, puede volver.
        if driver['last_shift_date']:
            days_since_last = (date - driver['last_shift_date']).days

            if days_since_last == 0:
                # Mismo día, permitido (múltiples turnos)
                pass
            elif days_since_last == 1:
                # Día consecutivo: verificar si ya llegó al máximo
                if driver['consecutive_days'] >= 6:
                    return False  # Ya trabajó 6 días, necesita descansar
            else:
                # Ha descansado al menos 1 día: puede volver a trabajar
                # El contador se reseteará en _assign_shifts_to_driver_no_cycles
                pass

        # 2. Verificar descanso entre jornadas (10h mínimo)
        # Por simplicidad, asumimos que entre días diferentes siempre hay 10h

        # 3. Verificar domingos (si es domingo, verificar cuántos ha trabajado)
        if date.weekday() == 6:  # Domingo
            # Contar domingos del mes actual
            month_start = date.replace(day=1)
            if date.month == 12:
                month_end = date.replace(year=date.year+1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = date.replace(month=date.month+1, day=1) - timedelta(days=1)

            sundays_this_month = 0
            for assign in driver['assignments']:
                assign_date = assign['date']
                if isinstance(assign_date, str):
                    assign_date = datetime.fromisoformat(assign_date).date()

                if month_start <= assign_date <= month_end and assign_date.weekday() == 6:
                    sundays_this_month += 1

            total_sundays = len([d for d in range((month_end - month_start).days + 1)
                                if (month_start + timedelta(days=d)).weekday() == 6])

            # Debe dejar al menos 2 domingos libres
            if sundays_this_month >= (total_sundays - 2):
                return False  # Ya trabajó suficientes domingos

        return True

    def _assign_shifts_to_driver_no_cycles(self, driver: Dict, date: date,
                                           unassigned: List[Dict], assignments: List[Dict]) -> int:
        """
        Asigna turnos del día a un conductor específico.

        Respeta:
        - 44h semanales máximo
        - 12h span máximo por día
        - 10h diarias máximo
        - No solapamiento
        - Mismo grupo geográfico

        Returns:
            Número de turnos asignados
        """
        assigned_today = []

        for shift in unassigned[:]:
            can_assign = True

            # 1. Verificar solapamiento con turnos ya asignados hoy
            for prev_shift in assigned_today:
                if shift['end_minutes'] > prev_shift['start_minutes'] and shift['start_minutes'] < prev_shift['end_minutes']:
                    can_assign = False
                    break

            # 2. Verificar span de 12h
            if can_assign and assigned_today:
                all_shifts_today = assigned_today + [shift]
                earliest_start = min(s['start_minutes'] for s in all_shifts_today)
                latest_end = max(s['end_minutes'] for s in all_shifts_today)
                span_minutes = latest_end - earliest_start
                if span_minutes > 720:  # 12h
                    can_assign = False

            # 3. Verificar 10h diarias
            if can_assign:
                daily_hours = sum(s['duration_hours'] for s in assigned_today) + shift['duration_hours']
                if daily_hours > 10.0:
                    can_assign = False

            # 4. Verificar 44h semanales
            if can_assign and self.regime_constraints.max_weekly_hours:
                weekly_hours = self._calculate_weekly_hours_no_cycles(driver, date, assigned_today, shift)
                if weekly_hours > self.regime_constraints.max_weekly_hours:
                    can_assign = False

            # 5. Verificar mismo grupo geográfico
            if can_assign and assigned_today:
                current_group = shift.get('service_group')
                for prev_shift in assigned_today:
                    prev_group = prev_shift.get('service_group')
                    if current_group and prev_group and current_group != prev_group:
                        can_assign = False
                        break

            if can_assign:
                assigned_today.append(shift)
                unassigned.remove(shift)

        # Registrar asignaciones
        for shift in assigned_today:
            date_str = date.isoformat()

            driver['assignments'].append({
                'date': date_str,  # Usar string para consistencia
                'shift': shift,
                'duration_hours': shift['duration_hours']
            })

            # Crear assignment con estructura completa (flatten shift details)
            assignments.append({
                'driver_id': len(driver.get('assignments', [])),  # Temporal (se corregirá después)
                'shift': shift,
                'date': date_str,
                'start_time': shift.get('start_time'),
                'end_time': shift.get('end_time'),
                'duration_hours': shift.get('duration_hours'),
                'service': shift.get('service'),
                'service_name': shift.get('service_name')
            })

        # Actualizar estado del conductor
        if assigned_today:
            if driver['last_shift_date'] and (date - driver['last_shift_date']).days == 1:
                driver['consecutive_days'] += 1
            else:
                driver['consecutive_days'] = 1

            driver['last_shift_date'] = date

            if date not in driver['work_days']:
                driver['work_days'].append(date)

        return len(assigned_today)

    def _calculate_weekly_hours_no_cycles(self, driver: Dict, current_date: date,
                                          assigned_today: List[Dict], new_shift: Dict) -> float:
        """
        Calcula horas semanales para greedy sin ciclos.
        Similar a _calculate_weekly_hours pero adaptado a estructura de driver diferente.
        """
        weekday = current_date.weekday()
        week_start = current_date - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)

        weekly_hours = 0.0

        for assignment in driver.get('assignments', []):
            assign_date = assignment['date']
            if isinstance(assign_date, str):
                assign_date = datetime.fromisoformat(assign_date).date()

            if week_start <= assign_date <= week_end:
                weekly_hours += assignment['duration_hours']

        for shift in assigned_today:
            weekly_hours += shift['duration_hours']

        weekly_hours += new_shift['duration_hours']

        return weekly_hours

    def _convert_greedy_no_cycles_to_standard(self, drivers: Dict, assignments: List[Dict],
                                               num_drivers: int, coverage: float,
                                               year: int, month: int) -> Dict[str, Any]:
        """
        Convierte resultado del greedy sin ciclos al formato estándar.
        """
        driver_summary = {}

        for driver_id, driver_info in drivers.items():
            total_hours = sum(a['duration_hours'] for a in driver_info['assignments'])
            work_days = sorted(driver_info['work_days'])
            formatted_id = f'D{driver_id:03d}'
            driver_name = f'Conductor {formatted_id}'

            # Contar domingos trabajados
            sundays_worked = sum(1 for d in work_days
                                if (d if isinstance(d, date) else datetime.fromisoformat(d).date()).weekday() == 6)

            # Calcular utilización (44h * 4 semanas = 176h para no-mineros)
            max_hours = 176
            utilization = round((total_hours / max_hours * 100), 1) if max_hours > 0 else 0

            driver_summary[formatted_id] = {
                'name': driver_name,
                'driver_name': driver_name,
                'total_hours': total_hours,
                'total_shifts': len(driver_info['assignments']),
                'total_assignments': len(driver_info['assignments']),
                'work_days': len(work_days),
                'sundays_worked': sundays_worked,
                'utilization': utilization,
                'pattern': '6x1 flexible',
                'regime': self.regime,
                'contract_type': 'fixed_term'
            }

        # Corregir driver_id y añadir driver_name en assignments
        for i, assignment in enumerate(assignments):
            # Encontrar a qué conductor pertenece basándonos en el orden
            found = False
            for driver_id, driver_info in drivers.items():
                if any(a['shift'] == assignment['shift'] and a['date'] == assignment['date']
                       for a in driver_info['assignments']):
                    formatted_id = f'D{driver_id:03d}'
                    assignment['driver_id'] = formatted_id
                    assignment['driver_name'] = f'Conductor {formatted_id}'
                    found = True
                    break

            if not found:
                # Fallback en caso de no encontrar driver
                print(f"⚠️ Warning: No driver found for assignment #{i}")
                assignment['driver_id'] = 'D000'
                assignment['driver_name'] = 'Conductor D000'

        # Calcular costo total
        total_cost = sum(shift.get('cost', 0) for shift in [a['shift'] for a in assignments])

        return {
            'status': 'success',
            'num_drivers': num_drivers,
            'coverage': coverage,
            'assignments': assignments,
            'driver_summary': driver_summary,
            'metrics': {
                'drivers_used': num_drivers,
                'total_assignments': len(assignments),
                'total_cost': total_cost
            }
        }

    def _greedy_assignment_flexible(self, all_shifts: List[Dict], year: int, month: int) -> Dict[str, Any]:
        """
        Algoritmo greedy flexible para regímenes sin ciclos fijos (Urbano, Industrial, Interurbano)
        Asigna conductores dinámicamente según disponibilidad y restricciones del régimen
        """
        print(f"Ejecutando greedy flexible para {len(all_shifts)} turnos...")
        
        # Ordenar turnos por fecha y hora de inicio
        sorted_shifts = sorted(all_shifts, key=lambda s: (s['date'], s['start_minutes']))
        
        # Estructura de conductores: {driver_id: {'assignments': [], 'last_shift_end': None, 'stats': {}}}
        drivers = {}
        next_driver_id = 1
        unassigned_shifts = []
        
        constraints = self.regime_constraints
        shift_counter = 0

        for shift in sorted_shifts:
            shift_counter += 1

            # Normalizar fecha a objeto date
            if isinstance(shift['date'], str):
                shift_date = datetime.fromisoformat(shift['date']).date()
            elif hasattr(shift['date'], 'date'):
                shift_date = shift['date'].date()
            else:
                shift_date = shift['date']

            # Asegurar que la fecha en el shift sea string ISO
            shift_date_str = shift_date.isoformat()
            shift_assigned = False

            # Generar shift_id único si no existe
            shift_id = shift.get('shift_id', f"shift_{shift_counter}")

            # Intentar asignar a un conductor existente
            # Ordenar conductores por total de horas trabajadas (menos cargados primero)
            sorted_drivers = sorted(
                drivers.items(),
                key=lambda x: sum(a['duration_hours'] for a in x[1]['assignments'])
            )

            for driver_id, driver_info in sorted_drivers:
                # Verificar si puede tomar este turno
                can_assign = self._can_driver_take_shift_flexible(
                    driver_info, shift, shift_date, constraints, year, month
                )

                if can_assign:
                    # Asignar turno
                    driver_info['assignments'].append({
                        'shift_id': shift_id,
                        'driver_id': driver_id,
                        'date': shift_date_str,  # Usar string ISO
                        'service': shift.get('service_name', ''),
                        'shift_number': shift.get('shift_number', 0),
                        'vehicle': shift.get('vehicle', 0),
                        'start_time': shift.get('start_time'),
                        'end_time': shift.get('end_time'),
                        'duration_hours': shift['duration_hours']
                    })

                    # Actualizar última hora de fin
                    driver_info['last_shift_end'] = (shift_date, shift['end_minutes'])
                    shift_assigned = True
                    break

            # Si no se pudo asignar a ningún conductor existente, crear uno nuevo
            if not shift_assigned:
                driver_id = next_driver_id
                next_driver_id += 1

                drivers[driver_id] = {
                    'assignments': [{
                        'shift_id': shift_id,
                        'driver_id': driver_id,
                        'date': shift_date_str,  # Usar string ISO
                        'service': shift.get('service_name', ''),
                        'shift_number': shift.get('shift_number', 0),
                        'vehicle': shift.get('vehicle', 0),
                        'start_time': shift.get('start_time'),
                        'end_time': shift.get('end_time'),
                        'duration_hours': shift['duration_hours']
                    }],
                    'last_shift_end': (shift_date, shift['end_minutes'])
                }
                shift_assigned = True
            
            if not shift_assigned:
                unassigned_shifts.append(shift)
        
        # Calcular métricas
        total_assigned = sum(len(d['assignments']) for d in drivers.values())
        coverage = (total_assigned / len(all_shifts) * 100) if all_shifts else 0
        
        print(f"  Conductores creados: {len(drivers)}")
        print(f"  Turnos asignados: {total_assigned}/{len(all_shifts)} ({coverage:.1f}%)")
        print(f"  Turnos sin asignar: {len(unassigned_shifts)}")
        
        return {
            'status': 'success' if coverage >= 99.0 else 'partial',
            'drivers': drivers,
            'drivers_used': len(drivers),
            'coverage': coverage,
            'total_shifts': len(all_shifts),
            'assigned_shifts': total_assigned,
            'unassigned_shifts': unassigned_shifts
        }
    
    def _can_driver_take_shift_flexible(self, driver_info: Dict, shift: Dict, 
                                         shift_date: date, constraints: 'LaborRegime',
                                         year: int, month: int) -> bool:
        """
        Verifica si un conductor puede tomar un turno en régimen flexible
        Aplica las restricciones del régimen sin asumir ciclos fijos
        """
        last_end = driver_info.get('last_shift_end')
        
        # Si no tiene turnos previos, puede tomar cualquier turno
        if not last_end:
            return True
        
        last_date, last_end_minutes = last_end
        
        # Calcular tiempo desde último turno
        days_diff = (shift_date - last_date).days
        
        # Si es el mismo día, verificar que no se solapen
        if days_diff == 0:
            if shift['start_minutes'] < last_end_minutes:
                return False  # Se solapan
            
            # Verificar descanso mínimo en mismo día
            rest_minutes = shift['start_minutes'] - last_end_minutes
            if rest_minutes < constraints.min_rest_between_shifts * 60:
                return False
        
        # Si es día consecutivo
        elif days_diff == 1:
            # Verificar descanso mínimo entre jornadas
            # Tiempo desde fin del último turno hasta inicio del siguiente
            minutes_since_last = (days_diff - 1) * 1440 + (1440 - last_end_minutes) + shift['start_minutes']
            if minutes_since_last < constraints.min_rest_between_shifts * 60:
                return False
        
        # Verificar máximo de horas diarias
        if days_diff == 0:
            # Calcular total de horas en el día
            day_hours = sum(a['duration_hours'] for a in driver_info['assignments'] 
                           if a['date'] == shift['date'])
            if day_hours + shift['duration_hours'] > constraints.max_daily_hours:
                return False
        
        # Verificar máximo de horas mensuales (si aplica)
        if constraints.max_monthly_hours:
            month_hours = sum(a['duration_hours'] for a in driver_info['assignments'])
            if month_hours + shift['duration_hours'] > constraints.max_monthly_hours:
                return False
        
        # Verificar días consecutivos
        if constraints.max_consecutive_days and days_diff <= 1:
            # Contar días consecutivos trabajados
            dates_worked = sorted(set(a['date'] for a in driver_info['assignments']))
            if dates_worked:
                consecutive_days = 1
                for i in range(len(dates_worked) - 1, 0, -1):
                    # Convertir a date si es string
                    prev_date_val = dates_worked[i-1]
                    curr_date_val = dates_worked[i]

                    if isinstance(prev_date_val, str):
                        prev_date = datetime.fromisoformat(prev_date_val).date()
                    elif hasattr(prev_date_val, 'date'):
                        prev_date = prev_date_val.date()
                    else:
                        prev_date = prev_date_val

                    if isinstance(curr_date_val, str):
                        curr_date = datetime.fromisoformat(curr_date_val).date()
                    elif hasattr(curr_date_val, 'date'):
                        curr_date = curr_date_val.date()
                    else:
                        curr_date = curr_date_val

                    if (curr_date - prev_date).days == 1:
                        consecutive_days += 1
                    else:
                        break

                if consecutive_days >= constraints.max_consecutive_days:
                    return False
        
        return True

    def _calculate_weekly_hours(self, driver: Dict, current_date: date,
                                 assigned_today: List[Dict], new_shift: Dict) -> float:
        """
        Calcula las horas totales que el conductor trabajaría en la semana actual
        si se le asigna el nuevo turno.

        Semana se define como Lunes-Domingo. Si estamos a mitad de semana,
        contamos desde el lunes de la semana actual.

        Args:
            driver: Diccionario con información del conductor
            current_date: Fecha actual
            assigned_today: Turnos ya asignados hoy
            new_shift: Turno que se quiere asignar

        Returns:
            Total de horas en la semana (incluyendo el nuevo turno)
        """
        # Calcular inicio de la semana (lunes)
        weekday = current_date.weekday()  # 0=Lunes, 6=Domingo
        week_start = current_date - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)

        # Sumar horas de asignaciones previas en esta semana
        weekly_hours = 0.0

        for assignment in driver.get('assignments', []):
            assign_date = assignment['date']
            if isinstance(assign_date, str):
                assign_date = datetime.fromisoformat(assign_date).date()

            # Si está en la semana actual
            if week_start <= assign_date <= week_end:
                weekly_hours += assignment['shift']['duration_hours']

        # Sumar horas de turnos asignados hoy (aún no en assignments)
        for shift in assigned_today:
            weekly_hours += shift['duration_hours']

        # Sumar el nuevo turno
        weekly_hours += new_shift['duration_hours']

        return weekly_hours

    def _convert_greedy_flexible_to_standard(self, greedy_result: Dict, year: int, month: int) -> Dict[str, Any]:
        """
        Convierte resultado del greedy flexible al formato estándar esperado por output_generator
        """
        drivers = greedy_result['drivers']
        all_assignments = []
        driver_summary = {}
        
        for driver_id, driver_info in drivers.items():
            assignments = driver_info['assignments']
            
            # Calcular estadísticas del conductor
            total_hours = sum(a['duration_hours'] for a in assignments)
            dates_worked = set(a['date'] for a in assignments)

            # Contar domingos trabajados (manejar tanto strings como objetos date)
            sundays_worked = 0
            for d in dates_worked:
                if isinstance(d, str):
                    date_obj = datetime.fromisoformat(d)
                elif hasattr(d, 'weekday'):
                    date_obj = d
                else:
                    continue

                if date_obj.weekday() == 6:
                    sundays_worked += 1
            
            driver_summary[driver_id] = {
                'driver_id': driver_id,
                'driver_name': f'Conductor {driver_id}',
                'name': f'Conductor {driver_id}',
                'total_hours': total_hours,
                'total_shifts': len(assignments),
                'sundays_worked': sundays_worked,
                'dates_worked': dates_worked,
                'pattern': 'Flexible',  # No hay patrón fijo
                'work_start_date': None,  # No aplica para flexible
                'contract_type': 'fixed_term'
            }
            
            # Agregar nombre del conductor a cada asignación
            for assignment in assignments:
                assignment['driver_name'] = f'Conductor {driver_id}'
                all_assignments.append(assignment)
        
        return {
            'status': 'success',
            'regime': self.regime,
            'year': year,
            'month': month,
            'assignments': all_assignments,
            'driver_summary': driver_summary,
            'metrics': {
                'drivers_used': len(drivers),
                'total_shifts': greedy_result['total_shifts'],
                'assigned_shifts': greedy_result['assigned_shifts'],
                'coverage': greedy_result['coverage'],
                'total_cost': 0  # Calcular si es necesario
            }
        }
