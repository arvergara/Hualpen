# Auditoría de Consistencia - PRIORIDAD 0

## Objetivo
Verificar que los datos y cálculos del greedy sean matemáticamente consistentes.

---

## Problema Detectado

**Incoherencia reportada por el equipo**:
- Total horas: 8,627.5h/mes
- Conductores greedy: 20
- Cota inferior teórica: 48-52 conductores

**Esto no tiene sentido matemático.**

---

## Verificaciones a Realizar

### 1. Recalcular Total de Horas Efectivas

```python
def audit_total_hours(all_shifts):
    """
    Recalcular horas totales sumando SOLO duration_hours de cada turno
    """
    total_hours = sum(shift['duration_hours'] for shift in all_shifts)
    print(f"Total horas efectivas: {total_hours:.1f}h")

    # Verificar por día
    by_date = {}
    for shift in all_shifts:
        date = shift['date']
        if date not in by_date:
            by_date[date] = 0
        by_date[date] += shift['duration_hours']

    print(f"\nHoras por día:")
    for date in sorted(by_date.keys()):
        print(f"  {date}: {by_date[date]:.1f}h")

    print(f"\nPromedio: {total_hours / len(by_date):.1f}h/día")

    return total_hours
```

### 2. Verificar Horas Asignadas por el Greedy

```python
def audit_greedy_assignments(solution):
    """
    Verificar que las asignaciones del greedy sumen las horas totales
    """
    # Por conductor
    hours_by_driver = {}
    for assignment in solution['assignments']:
        driver_id = assignment['driver_id']
        shift = assignment['shift']

        if driver_id not in hours_by_driver:
            hours_by_driver[driver_id] = 0
        hours_by_driver[driver_id] += shift['duration_hours']

    print(f"\nConductores usados: {len(hours_by_driver)}")
    print(f"\nHoras por conductor:")

    total_assigned = 0
    for driver_id in sorted(hours_by_driver.keys()):
        hours = hours_by_driver[driver_id]
        total_assigned += hours
        print(f"  D{driver_id:03d}: {hours:.1f}h")

    print(f"\nTotal asignado: {total_assigned:.1f}h")
    print(f"Promedio por conductor: {total_assigned / len(hours_by_driver):.1f}h/mes")

    return total_assigned, hours_by_driver
```

### 3. Verificar Capacidad Teórica de Patrones NxN

```python
def audit_pattern_capacity(pattern='10x10', days_in_month=28):
    """
    Calcular capacidad teórica de un patrón NxN
    """
    if pattern == '7x7':
        cycle = 7
    elif pattern == '10x10':
        cycle = 10
    elif pattern == '14x14':
        cycle = 14
    else:
        raise ValueError(f"Patrón desconocido: {pattern}")

    # Días trabajados en un mes de 28 días
    work_days = 0
    for day in range(days_in_month):
        day_in_cycle = day % (2 * cycle)
        if day_in_cycle < cycle:
            work_days += 1

    print(f"\nPatrón {pattern}:")
    print(f"  Días trabajados en mes de {days_in_month} días: {work_days}")

    # Capacidad asumiendo 12h/día
    capacity_12h = work_days * 12
    print(f"  Capacidad a 12h/día: {capacity_12h}h/mes")

    # Capacidad asumiendo 14h/día (máximo)
    capacity_14h = work_days * 14
    print(f"  Capacidad a 14h/día (máximo): {capacity_14h}h/mes")

    return capacity_12h, capacity_14h
```

### 4. Verificar Días Trabajados por Conductor

```python
def audit_driver_work_days(solution):
    """
    Verificar cuántos días trabajó cada conductor
    """
    days_by_driver = {}

    for assignment in solution['assignments']:
        driver_id = assignment['driver_id']
        date = assignment['date']

        if driver_id not in days_by_driver:
            days_by_driver[driver_id] = set()
        days_by_driver[driver_id].add(date)

    print(f"\nDías trabajados por conductor:")
    for driver_id in sorted(days_by_driver.keys()):
        days = len(days_by_driver[driver_id])
        pattern = solution['driver_summary'][f'D{driver_id:03d}']['pattern']
        print(f"  D{driver_id:03d} ({pattern}): {days} días")

    return days_by_driver
```

### 5. Calcular Cota Inferior Real

```python
def calculate_lower_bound(total_hours, pattern='10x10', days_in_month=28):
    """
    Calcular cota inferior de conductores necesarios
    """
    capacity_12h, capacity_14h = audit_pattern_capacity(pattern, days_in_month)

    # Cota inferior conservadora (12h/día)
    lb_conservative = math.ceil(total_hours / capacity_12h)

    # Cota inferior agresiva (14h/día)
    lb_aggressive = math.ceil(total_hours / capacity_14h)

    print(f"\n📊 Cota Inferior:")
    print(f"  Con {pattern} a 12h/día: {lb_conservative} conductores")
    print(f"  Con {pattern} a 14h/día: {lb_aggressive} conductores")

    return lb_conservative, lb_aggressive
```

---

## Script de Auditoría Completo

```python
def run_full_audit(all_shifts, greedy_solution, month=2, year=2025):
    """
    Ejecutar auditoría completa de consistencia
    """
    print("="*80)
    print("AUDITORÍA DE CONSISTENCIA")
    print("="*80)

    # 1. Total de horas en turnos
    print("\n1️⃣ HORAS TOTALES EN TURNOS")
    total_hours = audit_total_hours(all_shifts)

    # 2. Horas asignadas por greedy
    print("\n2️⃣ HORAS ASIGNADAS POR GREEDY")
    total_assigned, hours_by_driver = audit_greedy_assignments(greedy_solution)

    # 3. Verificar cobertura
    print("\n3️⃣ VERIFICACIÓN DE COBERTURA")
    print(f"  Horas en turnos: {total_hours:.1f}h")
    print(f"  Horas asignadas: {total_assigned:.1f}h")
    print(f"  Diferencia: {abs(total_hours - total_assigned):.1f}h")

    if abs(total_hours - total_assigned) > 0.1:
        print("  ❌ ERROR: Las horas no coinciden!")
    else:
        print("  ✅ OK: Cobertura completa")

    # 4. Días trabajados
    print("\n4️⃣ DÍAS TRABAJADOS")
    days_by_driver = audit_driver_work_days(greedy_solution)

    # 5. Capacidad teórica
    print("\n5️⃣ CAPACIDAD TEÓRICA DE PATRONES")
    days_in_month = calendar.monthrange(year, month)[1]

    for pattern in ['7x7', '10x10', '14x14']:
        capacity_12h, capacity_14h = audit_pattern_capacity(pattern, days_in_month)

    # 6. Cota inferior
    print("\n6️⃣ COTA INFERIOR")
    dominant_pattern = greedy_solution.get('dominant_pattern', '10x10')
    lb_conservative, lb_aggressive = calculate_lower_bound(
        total_hours,
        dominant_pattern,
        days_in_month
    )

    # 7. Comparación con greedy
    print("\n7️⃣ COMPARACIÓN CON GREEDY")
    drivers_used = len(hours_by_driver)
    print(f"  Conductores greedy: {drivers_used}")
    print(f"  Cota inferior (12h/día): {lb_conservative}")
    print(f"  Cota inferior (14h/día): {lb_aggressive}")

    if drivers_used < lb_aggressive:
        print(f"  ❌ INCOHERENCIA CRÍTICA: {drivers_used} < {lb_aggressive}")
        print(f"     El greedy usa MENOS conductores que la cota inferior matemática.")
        print(f"     Esto es IMPOSIBLE. Revisar cálculos.")
    elif drivers_used < lb_conservative:
        print(f"  ⚠️  ADVERTENCIA: {drivers_used} < {lb_conservative}")
        print(f"     El greedy usa menos conductores que la cota conservadora.")
        print(f"     Verificar que conductores estén trabajando más de 12h/día en promedio.")
    else:
        print(f"  ✅ OK: Greedy usa {drivers_used - lb_aggressive} conductores más que la cota agresiva")

    # 8. Resumen final
    print("\n" + "="*80)
    print("RESUMEN DE AUDITORÍA")
    print("="*80)

    issues = []

    if abs(total_hours - total_assigned) > 0.1:
        issues.append("Horas asignadas no coinciden con horas totales")

    if drivers_used < lb_aggressive:
        issues.append("Conductores greedy < cota inferior (IMPOSIBLE)")

    if not issues:
        print("✅ Sin problemas detectados")
        print(f"   Total horas: {total_hours:.1f}h")
        print(f"   Conductores: {drivers_used}")
        print(f"   Promedio: {total_assigned / drivers_used:.1f}h/conductor")
    else:
        print("❌ PROBLEMAS DETECTADOS:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")

    return {
        'total_hours': total_hours,
        'total_assigned': total_assigned,
        'drivers_used': drivers_used,
        'lb_conservative': lb_conservative,
        'lb_aggressive': lb_aggressive,
        'issues': issues
    }
```

---

## Ejecución

Agregar este código al final de `_greedy_assignment_single_pattern()`:

```python
# Al final del método, antes de return
audit_result = run_full_audit(all_shifts, solution, self.month, self.year)

if audit_result['issues']:
    print("\n⚠️⚠️⚠️ DETENER OPTIMIZACIÓN ⚠️⚠️⚠️")
    print("Resolver problemas de consistencia antes de continuar")
```

---

## Próximos Pasos Después de Auditoría

### Si NO hay problemas:
Continuar con LNS/ALNS como sugiere el equipo.

### Si HAY problemas:
1. Revisar cálculo de `duration_hours` en turnos
2. Revisar lógica de asignación en greedy
3. Verificar que patrones NxN se apliquen correctamente
4. Consultar con RR.HH. sobre régimen legal exacto
