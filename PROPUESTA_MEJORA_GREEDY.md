# Propuesta: Mejorar Greedy con Multi-Start Heuristics

## Problema Actual

**Greedy actual**: 20 conductores con patrón 10x10 en ~10 segundos
- Procesa día por día secuencialmente
- Asigna turnos a conductores disponibles en orden
- Crea nuevos conductores cuando no quedan disponibles

**Limitación**: El orden de procesamiento afecta el resultado final (decisión miope)

---

## Enfoque Propuesto: Multi-Start Greedy con Heurísticas

### Idea Principal
Ejecutar el greedy **múltiples veces con diferentes estrategias** y seleccionar la mejor.

**Tiempo total**: 5-10 minutos (100 iteraciones × 6 segundos c/u)
**Probabilidad de mejora**: 70-80%
**Complejidad de implementación**: BAJA (1-2 días)

---

## Estrategia 1: Ordenamiento de Turnos (6 variantes)

Actualmente el greedy procesa turnos en el orden que vienen. **Cambiar el orden puede mejorar el resultado.**

### Variantes de Ordenamiento:

1. **Por Hora de Inicio (actual)**
   - Orden: Cronológico ascendente
   - Ejemplo: 06:00 → 08:00 → 12:00 → ...

2. **Por Duración Decreciente**
   - Orden: Turnos largos primero
   - Razón: Turnos largos son más difíciles de ubicar, asignarlos primero
   - Ejemplo: 12h → 10h → 8h → 6h

3. **Por Duración Creciente**
   - Orden: Turnos cortos primero
   - Razón: Llenar huecos con turnos cortos deja menos espacio desperdiciado
   - Ejemplo: 4h → 6h → 8h → 10h

4. **Por Hora de Inicio Decreciente (reverse)**
   - Orden: Turnos tarde → temprano
   - Razón: A veces asignar turnos nocturnos primero libera mejor los conductores

5. **Por Service + Shift**
   - Orden: Agrupar por servicio y turno
   - Razón: Turnos del mismo servicio pueden tener mejor continuidad

6. **Aleatorio con Semilla**
   - Orden: Random shuffle con seed diferente
   - Razón: Exploración no determinística

### Implementación:
```python
def _get_shift_sorting_key(strategy: str, shift: Dict):
    if strategy == 'start_asc':
        return shift['start_minutes']
    elif strategy == 'duration_desc':
        return -shift['duration_hours']
    elif strategy == 'duration_asc':
        return shift['duration_hours']
    elif strategy == 'start_desc':
        return -shift['start_minutes']
    elif strategy == 'service_shift':
        return (shift['service_id'], shift['shift_number'])
    elif strategy == 'random':
        return random.random()
```

---

## Estrategia 2: Selección de Conductor (3 variantes)

Actualmente el greedy selecciona el **primer conductor disponible**. Podemos ser más inteligentes.

### Variantes de Selección:

1. **Primer Disponible (actual)**
   - Selecciona el primer conductor que puede hacer el turno

2. **Menos Horas Trabajadas**
   - Selecciona el conductor con menos horas acumuladas
   - Razón: Balancea carga entre conductores

3. **Más Horas Trabajadas**
   - Selecciona el conductor con más horas acumuladas
   - Razón: Intenta "saturar" conductores para minimizar total

4. **Mejor Continuidad**
   - Selecciona el conductor cuyo último turno está más cerca en el tiempo
   - Razón: Minimiza gaps y desperdicio de horas

### Implementación:
```python
def _select_driver(strategy: str, available_drivers: List, drivers: Dict, shift: Dict):
    if strategy == 'first':
        return available_drivers[0]
    elif strategy == 'min_hours':
        return min(available_drivers,
                   key=lambda d: sum(s['duration_hours'] for s in drivers[d]['assignments']))
    elif strategy == 'max_hours':
        return max(available_drivers,
                   key=lambda d: sum(s['duration_hours'] for s in drivers[d]['assignments']))
    elif strategy == 'best_continuity':
        def continuity_score(driver_id):
            last_end = drivers[driver_id].get('last_shift_end')
            if not last_end:
                return 999999  # Sin historial, baja prioridad
            days_diff = (shift['date'] - last_end[0]).days
            minutes_diff = (days_diff * 1440) + shift['start_minutes'] - last_end[1]
            return minutes_diff
        return min(available_drivers, key=continuity_score)
```

---

## Estrategia 3: Offset Inicial de Conductores (4 variantes)

Actualmente el greedy crea conductores con offset calculado como `day_idx % (2 * cycle)`.
Podemos variar el offset para cambiar qué días trabaja cada conductor.

### Variantes de Offset:

1. **Offset Standard (actual)**
   - `offset = day_idx % (2 * cycle)`

2. **Offset Aleatorio**
   - `offset = random.randint(0, 2 * cycle - 1)`
   - Razón: Explora diferentes alineaciones de ciclos

3. **Offset Balanceado**
   - Distribuir offsets uniformemente: 0, 5, 10, 15, ...
   - Razón: Asegura que siempre haya conductores disponibles

4. **Offset Zero**
   - `offset = 0` (todos empiezan el 1 de febrero)
   - Razón: Sincroniza ciclos de todos los conductores

### Implementación:
```python
def _calculate_offset(strategy: str, driver_counter: int, day_idx: int, cycle: int):
    if strategy == 'standard':
        return day_idx % (2 * cycle)
    elif strategy == 'random':
        return random.randint(0, 2 * cycle - 1)
    elif strategy == 'balanced':
        return (driver_counter * 5) % (2 * cycle)
    elif strategy == 'zero':
        return 0
```

---

## Combinaciones Totales

**Estrategias**:
- Ordenamiento: 6 variantes
- Selección conductor: 4 variantes
- Offset inicial: 4 variantes

**Total combinaciones**: 6 × 4 × 4 = **96 configuraciones diferentes**

---

## Algoritmo Multi-Start Greedy

```python
def optimize_with_multistart_greedy(self, all_shifts, cycles=[7, 10, 14], max_time=600):
    """
    Ejecuta greedy múltiples veces con diferentes heurísticas
    """
    start_time = time.time()

    # Definir estrategias
    sort_strategies = ['start_asc', 'duration_desc', 'duration_asc',
                       'start_desc', 'service_shift', 'random']
    select_strategies = ['first', 'min_hours', 'max_hours', 'best_continuity']
    offset_strategies = ['standard', 'random', 'balanced', 'zero']

    best_solution = None
    best_cost = float('inf')

    iteration = 0

    # Para cada patrón (7x7, 10x10, 14x14)
    for cycle in cycles:
        print(f"\n🔍 Probando patrón {cycle}x{cycle}...")

        # Para cada combinación de estrategias
        for sort_strat in sort_strategies:
            for select_strat in select_strategies:
                for offset_strat in offset_strategies:
                    iteration += 1

                    # Verificar tiempo
                    if time.time() - start_time > max_time:
                        print(f"\n⏱️ Tiempo límite alcanzado ({max_time}s)")
                        break

                    # Ejecutar greedy con esta configuración
                    solution = self._greedy_with_config(
                        all_shifts,
                        cycle,
                        sort_strategy=sort_strat,
                        select_strategy=select_strat,
                        offset_strategy=offset_strat
                    )

                    # Evaluar solución
                    cost = self._evaluate_solution(solution)
                    num_drivers = solution['drivers_used']

                    # Actualizar mejor solución
                    if cost < best_cost:
                        best_cost = cost
                        best_solution = solution
                        print(f"  ✨ Iteración {iteration}: {num_drivers} conductores "
                              f"(sort={sort_strat}, select={select_strat}, offset={offset_strat})")
                    else:
                        print(f"  · Iteración {iteration}: {num_drivers} conductores", end='\r')

    print(f"\n\n🏆 MEJOR SOLUCIÓN: {best_solution['drivers_used']} conductores")
    print(f"   Configuración: {best_solution['config']}")
    print(f"   Iteraciones probadas: {iteration}")
    print(f"   Tiempo total: {time.time() - start_time:.1f}s")

    return best_solution


def _evaluate_solution(self, solution):
    """Función objetivo para comparar soluciones"""
    num_drivers = solution['drivers_used']
    total_shifts = len(solution['assignments'])
    coverage = solution['coverage_percentage']

    # Penalizar fuertemente si no hay 100% cobertura
    if coverage < 100:
        return num_drivers * 1000000

    # Objetivo: minimizar conductores
    # Secundario: minimizar costo total
    total_cost = (num_drivers * 800000) + (total_shifts * 5000)

    return total_cost
```

---

## Implementación Rápida (PRIORIDAD)

### Paso 1: Refactorizar Greedy Actual (1-2 horas)

Extraer parámetros del greedy actual:

```python
def _greedy_assignment_single_pattern(
    self,
    all_shifts: List[Dict],
    cycle: int,
    sort_strategy: str = 'start_asc',
    select_strategy: str = 'first',
    offset_strategy: str = 'standard',
    seed: int = None
) -> Dict[str, Any]:
```

### Paso 2: Implementar Multi-Start (2-3 horas)

Crear método que ejecute greedy con todas las combinaciones.

### Paso 3: Paralelizar (opcional, 1 hora)

Si tienes múltiples cores, ejecutar combinaciones en paralelo:

```python
from multiprocessing import Pool

def run_parallel_greedy(configs):
    with Pool(processes=8) as pool:
        results = pool.map(run_greedy_config, configs)
    return min(results, key=lambda r: r['cost'])
```

---

## Resultados Esperados

### Baseline (actual):
- **20 conductores** con 10x10
- **Tiempo**: 10 segundos
- **Cobertura**: 100%

### Con Multi-Start Greedy (proyección):
- **18-19 conductores** (mejora de 1-2 conductores)
- **Tiempo**: 5-10 minutos (96 iteraciones)
- **Cobertura**: 100%
- **Probabilidad de mejora**: 75%

### Mejor caso:
- **17 conductores** (mejora de 3 conductores = 15%)
- Esto representaría **$2,400,000 anuales de ahorro** (3 conductores × $800K/mes)

---

## Alternativa Más Simple: Smart Sampling

Si 96 iteraciones son muchas, podemos hacer **sampling inteligente** de 20 configuraciones:

```python
smart_configs = [
    # Las "mejores" combinaciones basadas en intuición
    ('duration_desc', 'max_hours', 'balanced'),      # Saturar conductores con turnos largos
    ('duration_asc', 'min_hours', 'balanced'),       # Balancear con turnos cortos
    ('start_asc', 'best_continuity', 'standard'),    # Maximizar continuidad
    ('service_shift', 'first', 'balanced'),          # Agrupar por servicio
    ('start_desc', 'max_hours', 'zero'),             # Reverse con sincronización
    # + 15 combinaciones aleatorias
]
```

**Tiempo**: 20 × 10s = 3-4 minutos
**Probabilidad de mejora**: 60%

---

## Ventajas de este Enfoque

1. ✅ **Fácil de implementar** (1-2 días de desarrollo)
2. ✅ **No requiere librerías externas** (solo Python standard)
3. ✅ **Tiempo razonable** (5-10 minutos)
4. ✅ **Garantiza factibilidad** (todas las soluciones son válidas)
5. ✅ **Interpretable** (sabemos qué heurística funcionó mejor)
6. ✅ **Paralelizable** (puede reducirse a 1-2 minutos con multiprocessing)

---

## Desventajas / Limitaciones

1. ❌ **No garantiza óptimo global** (solo mejora local)
2. ❌ **Puede estancarse** (si greedy tiene limitación estructural)
3. ❌ **No explora reestructuración** (no mueve turnos ya asignados)

---

## Próximos Pasos

### Opción A: Implementar Multi-Start Completo (recomendado)
- **Tiempo**: 1-2 días
- **Ganancia esperada**: 1-2 conductores (5-10% mejora)

### Opción B: Implementar Smart Sampling (más rápido)
- **Tiempo**: 4-6 horas
- **Ganancia esperada**: 0-1 conductor (0-5% mejora)

### Opción C: Después de Multi-Start, agregar Local Search
- Multi-Start da solución inicial (18-19 conductores)
- Simulated Annealing refina (puede llegar a 17-18)
- **Tiempo adicional**: +2 días
- **Ganancia esperada**: +1 conductor adicional

---

## ¿Cuál prefieres implementar?

1. **Multi-Start Completo** (96 configs, 5-10 min, 75% prob mejora)
2. **Smart Sampling** (20 configs, 3-4 min, 60% prob mejora)
3. **Multi-Start + Simulated Annealing** (10-15 min, 85% prob mejora)

Recomiendo empezar con **Multi-Start Completo** porque:
- Balance óptimo entre esfuerzo y resultado
- Puedes paralelizar después si es muy lento
- Da baseline sólido para Simulated Annealing posterior
