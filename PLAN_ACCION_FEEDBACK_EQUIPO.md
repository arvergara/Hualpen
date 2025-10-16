# Plan de Acción - Feedback del Equipo de Research

## Resumen Ejecutivo

El equipo de research identificó **1 problema crítico** y propone **2 soluciones prácticas**.

---

## 🚨 PRIORIDAD 0: Auditoría de Consistencia (2-3 horas)

### Problema Crítico Detectado

**Incoherencia matemática**:
- Total horas: 8,627.5h/mes
- Conductores greedy: 20
- **Cota inferior teórica: 48-52 conductores**

**Conclusión**: Los números NO cuadran. 20 conductores no pueden cubrir 8,627h/mes.

### Posibles Causas

1. "Conductor" no significa "persona trabajando 12h/día" (quizás es por vehículo o turno)
2. Las 8,627h incluyen horas ociosas que no necesitan conductor
3. El greedy está contando mal (vehículos en vez de personas)
4. Los patrones NxN no se aplican correctamente

### Acción Requerida

✅ **Ejecutar script de auditoría** (ver [AUDITORIA_CONSISTENCIA.md](AUDITORIA_CONSISTENCIA.md)):

```bash
python backend/optimize_plus.py [archivo] [cliente] 2025 2 --audit
```

**Verificar**:
1. Total horas efectivas (suma de duration_hours)
2. Horas asignadas por conductor
3. Días trabajados vs. patrón NxN
4. Cobertura 100%
5. Cota inferior matemática

**NO CONTINUAR** con optimización hasta resolver esta incoherencia.

---

## 📋 PRIORIDAD 1: LNS/ALNS (Greedy + Large Neighborhood Search)

### Por Qué Este Enfoque

✅ **Recomendación #1 del equipo**: "Para impacto inmediato, usa Greedy + LNS/ALNS"
✅ **Tiempo**: 10-15 minutos (cumple restricción)
✅ **Ganancia esperada**: 1-3 conductores menos que greedy
✅ **Literatura sólida**: Estándar en rostering moderno
✅ **Complejidad**: MEDIA (1-2 días de desarrollo)

### Flujo Propuesto

```
Fase A: Multi-Start Greedy (1 min)
  ├─ 8-16 semillas con diferentes ordenamientos
  ├─ Offsets rotados (0..19 para 10x10)
  └─ Selecciona mejor solución

Fase B: LNS/ALNS (10-12 min)
  ├─ Operadores de Destrucción:
  │   ├─ Drop-Driver: Elimina conductor de baja carga
  │   ├─ Destroy-Window: Retira 3-4 días contiguos
  │   └─ Destroy-Service: Retira turnos de un servicio
  ├─ Reparación:
  │   └─ First-fit con conflict sets precomputados
  └─ Aceptación:
      └─ Simulated Annealing (T₀=100, α=0.95)

Fase C: Limpieza Final (1-2 min)
  ├─ Swaps 1-1 guiados
  └─ Eliminación glotona de conductores residuales
```

### Operadores Clave

#### 1. Drop-Driver (Consolidate)
```python
def drop_driver_operator(solution):
    """
    Elimina conductor con menos horas y repara
    """
    # Seleccionar conductor con mínima carga
    min_driver = min(solution['drivers'], key=lambda d: d['total_hours'])

    # Extraer sus turnos
    shifts_to_reassign = min_driver['assignments']

    # Eliminar conductor
    solution['drivers'].remove(min_driver)

    # Reparar: intentar insertar turnos en otros conductores
    for shift in shifts_to_reassign:
        assigned = try_assign_to_existing(shift, solution['drivers'])
        if not assigned:
            # No cabía: crear nuevo conductor
            create_new_driver(shift)

    return solution
```

#### 2. Destroy-Window
```python
def destroy_window_operator(solution, window_size=3):
    """
    Elimina asignaciones de una ventana de días y repara
    """
    # Seleccionar ventana aleatoria
    start_day = random.randint(0, 28 - window_size)
    window_dates = [fecha for día in range(start_day, start_day + window_size)]

    # Extraer turnos de esa ventana
    destroyed_shifts = []
    for driver in solution['drivers']:
        driver['assignments'] = [
            a for a in driver['assignments']
            if a['date'] not in window_dates or destroyed_shifts.append(a)
        ]

    # Reparar
    for shift in destroyed_shifts:
        repair_shift(shift, solution)

    return solution
```

#### 3. Repair con Conflict Sets
```python
def repair_shift(shift, solution):
    """
    Intenta insertar turno en conductor existente
    O crea nuevo si no cabe
    """
    # Precomputado: conflict_sets[shift_id] = lista de turnos incompatibles
    conflicts = conflict_sets[shift['id']]

    # Buscar conductor compatible
    for driver in solution['drivers']:
        # Check rápido: ¿conductor disponible ese día según NxN?
        if not is_available_by_pattern(driver, shift['date']):
            continue

        # Check: ¿tiene conflictos con turnos ya asignados?
        has_conflict = any(
            assigned['id'] in conflicts
            for assigned in driver['assignments']
        )

        if not has_conflict:
            # Check: ¿cabe en 14h diarias?
            if fits_in_daily_limit(driver, shift):
                driver['assignments'].append(shift)
                return True

    # No cabía en ninguno: crear nuevo conductor
    create_new_driver_for_shift(shift, solution)
    return False
```

### Estructuras Optimizadas

#### Conflict Sets Precomputados
```python
def precompute_conflict_sets(all_shifts):
    """
    Para cada turno, lista de turnos incompatibles
    """
    conflict_sets = {}

    for shift in all_shifts:
        conflicts = []
        for other_shift in all_shifts:
            if shift['id'] == other_shift['id']:
                continue

            # Mismo día y se solapan
            if shift['date'] == other_shift['date']:
                if shifts_overlap(shift, other_shift):
                    conflicts.append(other_shift['id'])

            # Días consecutivos y < 10h descanso
            elif abs((shift['date'] - other_shift['date']).days) == 1:
                if rest_time_between(shift, other_shift) < 600:  # 10h
                    conflicts.append(other_shift['id'])

        conflict_sets[shift['id']] = set(conflicts)

    return conflict_sets
```

#### Bitsets por Día (Fast Overlap Check)
```python
def create_bitset_for_driver(driver, date):
    """
    Bitset de 1440 minutos (24h) indicando ocupación
    """
    bitset = [0] * 1440

    for assignment in driver['assignments']:
        if assignment['date'] == date:
            start = assignment['start_minutes']
            end = assignment['end_minutes']
            for minute in range(start, end):
                bitset[minute] = 1

    return bitset


def can_fit_shift_fast(driver, shift, date):
    """
    Check O(1) si turno cabe usando bitset
    """
    bitset = get_cached_bitset(driver, date)

    start = shift['start_minutes']
    end = shift['end_minutes']

    # Check overlap
    if any(bitset[m] == 1 for m in range(start, end)):
        return False

    # Check 14h limit
    total_minutes = sum(bitset) + (end - start)
    if total_minutes > 14 * 60:
        return False

    return True
```

### Aceptación: Simulated Annealing

```python
def accept_solution(current, neighbor, temperature):
    """
    Criterio de aceptación SA
    """
    current_cost = evaluate(current)
    neighbor_cost = evaluate(neighbor)

    delta = neighbor_cost - current_cost

    # Siempre aceptar mejoras
    if delta < 0:
        return True

    # Aceptar empeoramientos con probabilidad
    probability = math.exp(-delta / temperature)
    return random.random() < probability
```

### Algoritmo Completo

```python
def optimize_with_lns_alns(initial_solution, max_time=600):
    """
    LNS/ALNS sobre solución greedy inicial
    """
    current = initial_solution
    best = current

    T = 100.0  # Temperatura inicial
    alpha = 0.95  # Tasa de enfriamiento

    operators = [
        ('drop_driver', drop_driver_operator, 0.3),
        ('destroy_window', destroy_window_operator, 0.4),
        ('destroy_service', destroy_service_operator, 0.3)
    ]

    start_time = time.time()
    iteration = 0

    while time.time() - start_time < max_time:
        iteration += 1

        # Seleccionar operador (ruleta)
        operator_name, operator_func, weight = select_operator(operators)

        # Aplicar destrucción
        neighbor = operator_func(copy.deepcopy(current))

        # Evaluar
        if is_feasible(neighbor) and accept_solution(current, neighbor, T):
            current = neighbor

            if evaluate(current) < evaluate(best):
                best = current
                print(f"Iteración {iteration}: {best['drivers_used']} conductores")

        # Enfriar
        T *= alpha

        # Cada 50 iteraciones: intensificar con drop_driver
        if iteration % 50 == 0:
            current = try_consolidate_drivers(current)

    return best
```

---

## 📋 PRIORIDAD 2: CP-SAT con Intervalos (Fix para modelo actual)

### Por Qué CP-SAT Falla

❌ **Modelo denso**: Variables `x[d,s]` para TODOS los pares (conductor, turno), incluso imposibles
❌ **Simetrías**: Restricciones NxN modeladas como binarios
❌ **No usa intervals**: CP-SAT es fuerte en scheduling con `interval variables` + `NoOverlap`

### Solución: Reescribir con Intervals

```python
def model_with_intervals(model, shifts, drivers):
    """
    Modelar usando interval variables (CP-SAT native)
    """
    # Variables: intervalos opcionales
    intervals = {}
    presences = {}

    for driver in drivers:
        for shift in shifts:
            # Filtrar: solo crear variable si compatible con NxN
            if not is_available_by_pattern(driver, shift):
                continue

            # Variable de presencia
            presence = model.NewBoolVar(f'p_{driver.id}_{shift.id}')
            presences[driver.id, shift.id] = presence

            # Variable de intervalo opcional
            interval = model.NewOptionalIntervalVar(
                start=shift['start_minutes'],
                size=shift['duration_minutes'],
                end=shift['end_minutes'],
                is_present=presence,
                name=f'interval_{driver.id}_{shift.id}'
            )
            intervals[driver.id, shift.id] = interval

    # Restricción: NoOverlap por conductor
    for driver in drivers:
        driver_intervals = [
            intervals[driver.id, shift.id]
            for shift in shifts
            if (driver.id, shift.id) in intervals
        ]
        model.AddNoOverlap(driver_intervals)

    # Restricción: cada turno cubierto exactamente una vez
    for shift in shifts:
        model.Add(
            sum(presences[d.id, shift.id] for d in drivers if (d.id, shift.id) in presences) == 1
        )

    # Objetivo: minimizar conductores usados
    drivers_used = [model.NewBoolVar(f'used_{d.id}') for d in drivers]
    for i, driver in enumerate(drivers):
        # Si usa al menos 1 turno, está usado
        model.AddMaxEquality(
            drivers_used[i],
            [presences[driver.id, s.id] for s in shifts if (driver.id, s.id) in presences]
        )

    model.Minimize(sum(drivers_used))
```

### Ventana CP-SAT (Alternativa Más Rápida)

En vez de resolver todo el mes, resolver ventanas de 2-4 días:

```python
def optimize_with_sliding_window(solution, window_size=3, time_per_window=60):
    """
    Fix-and-optimize por ventanas
    """
    num_days = 28

    for start_day in range(0, num_days, window_size):
        end_day = min(start_day + window_size, num_days)

        print(f"Optimizando días {start_day+1}-{end_day}...")

        # Extraer turnos de la ventana
        window_shifts = [s for s in all_shifts if start_day <= s['day'] < end_day]

        # Fijar asignaciones fuera de la ventana
        # Optimizar solo la ventana con CP-SAT
        window_solution = optimize_window_with_cpsat(
            window_shifts,
            solution['drivers'],
            time_limit=time_per_window
        )

        # Actualizar solución global
        update_solution_with_window(solution, window_solution)

    return solution
```

---

## 📊 PRIORIDAD 3: Column Generation (Medio Plazo)

### Cuándo Considerar

- Si LNS/ALNS no mejora suficiente
- Si necesitas garantía de optimalidad
- Si tienes 1-2 semanas para desarrollar

### Concepto

**Master Problem**: Set-partitioning que cubre cada turno exactamente una vez
**Subproblem (Pricing)**: Genera "rutas" factibles (secuencias de turnos para 1 conductor)

**Ventaja**: Escala mucho mejor que CP-SAT en problemas grandes
**Desafío**: Complejo de implementar (requiere expertise en optimización)

---

## 🎯 Recomendación Final

### Fase 1: Auditoría (HOY - 2-3 horas)
✅ Ejecutar script de auditoría
✅ Resolver incoherencias detectadas
✅ Validar que greedy funciona correctamente

### Fase 2: LNS/ALNS (2-3 días)
✅ Implementar operadores drop_driver, destroy_window, destroy_service
✅ Precomputar conflict sets y bitsets
✅ Simulated Annealing para aceptación
✅ **Meta**: Reducir de 20 a 18-19 conductores en 10-15 min

### Fase 3: CP-SAT Ventanas (Opcional, +1 día)
✅ Si LNS no es suficiente
✅ Integrar como "operador de intensificación" dentro de LNS
✅ Optimizar ventanas difíciles (días con mayor span)

### Fase 4: Column Generation (Medio Plazo, +2 semanas)
✅ Solo si necesitas optimalidad garantizada
✅ Requiere infraestructura más compleja

---

## 📚 Referencias del Equipo

- **LNS/ALNS en rostering**: Estándar moderno (DIVA Portal, arXiv)
- **CP-SAT con intervals**: Documentación Google OR-Tools
- **Column Generation**: Desaulniers/Desrosiers/Solomon
- **Marco legal chileno**: Ley 21.561, Art. 38 DT

---

## 🚀 Próximo Paso Inmediato

**Ejecutar auditoría de consistencia**:

```bash
cd /Users/alfil/Desktop/Prototipo_Hualpen_local/backend
python optimize_plus.py [archivo_excel] Hualpen 2025 2 --audit
```

Una vez verificada la consistencia, implementar LNS/ALNS.
