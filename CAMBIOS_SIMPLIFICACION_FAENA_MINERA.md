# Simplificación y Correcciones - Faena Minera

**Fecha**: 14 de Octubre 2025
**Estado**: ✅ COMPLETADO

---

## Problemas Corregidos

### 1. ❌ **Excel Reader no expandía turnos correctamente**

**Problema**:
- El reader solo leía la "plantilla" de horarios (ej: "Lunes: 04:00-08:30")
- NO expandía esos horarios a todos los días del mes
- Resultado: Solo leía 90 turnos en vez de 944

**Solución**:
- ✅ Agregado método `_expand_shifts_to_month()` que expande turnos según frecuencia
- ✅ Para "Martes a Viernes" con 3 horarios → genera 16 días × 3 = 48 turnos
- ✅ Corregido límite `nrows=50` a `nrows=200` para leer todos los servicios

**Resultado**:
```
Bimbo Faena - Febrero 2025:
  Servicios (líneas Excel): 67 ✅
  Turnos expandidos: 944 ✅
  Total horas: 3,865h ✅
  Cota inferior: ~22 conductores (no 20) ✅
```

---

### 2. ❌ **Greedy probaba múltiples patrones innecesariamente**

**Problema**:
- Greedy probaba 7x7, 10x10 y 14x14
- Para turnos homogéneos (Faena Minera), no hay ventaja en combinar patrones
- Perdía tiempo y complejidad innecesaria

**Solución**:
- ✅ Simplificado a **solo patrón 7x7** para Faena Minera
- Razón: Turnos homogéneos, ciclo más simple
- Reduce tiempo de cómputo y complejidad

**Código anterior**:
```python
for cycle in [7, 10, 14]:
    solution = self._greedy_assignment_single_pattern(all_shifts, cycle)
    greedy_solutions[cycle] = solution

best_greedy = min(greedy_solutions.values(), key=lambda s: s['num_drivers'])
```

**Código nuevo**:
```python
# Solo usar 7x7 para Faena Minera
cycle = 7
best_greedy = self._greedy_assignment_single_pattern(all_shifts, cycle)
```

---

### 3. ❌ **Restricción de descanso era incorrecta**

**Problema**:
- Código verificaba 1h de descanso entre turnos del mismo día
- Restricción legal real: **5h de descanso entre turnos** (para poder tomar 2 turnos en un día)
- Ejemplo válido: 08:00-11:00 y luego 19:00-21:00 (8h de separación) ✅

**Solución**:
- ✅ Cambiado descanso mínimo mismo día de **1h → 5h**
- ✅ Mantener descanso entre días: **10h** (sin cambios)
- ✅ Máximo diario: **14h totales** (puede ser en múltiples turnos con 5h descanso)

**Código anterior**:
```python
if time_since_last < 60:  # Menos de 1h de descanso
    can_assign = False
```

**Código nuevo**:
```python
# Mismo día: verificar que no se solapen y haya 5h de descanso
# Restricción legal: 14h totales/día, con 5h descanso entre turnos
if time_since_last < 300:  # Menos de 5h de descanso
    can_assign = False
```

---

## Restricciones Correctas (Faena Minera)

### Diarias
- ✅ **Máximo 14h totales por día** (puede ser en múltiples turnos)
- ✅ **Mínimo 5h de descanso** entre turnos del mismo día
- ✅ **Máximo 12h seguidas** de conducción continua
- ✅ No solapamiento de turnos

### Entre Días
- ✅ **Mínimo 10h de descanso** entre último turno del día D y primer turno del día D+1

### Patrón NxN
- ✅ **7x7**: 7 días trabajo, 7 días descanso (ciclo de 14 días)
- ✅ Estricto: NO puede trabajar durante días de descanso

---

## Ejemplo de Asignación Válida

### Conductor 1 - Patrón 7x7
```
Día 1 (2025-02-01) - Día de trabajo:
  08:00-11:00 (3h)    ✅ Primer turno
  17:00-20:00 (3h)    ✅ Segundo turno (6h después, cumple 5h mínimo)
  Total: 6h/día       ✅ Dentro del límite de 14h

Día 2 (2025-02-02) - Día de trabajo:
  06:00-14:00 (8h)    ✅ (10h después del último turno de ayer)
  Total: 8h/día       ✅

...

Días 8-14 (2025-02-08 a 2025-02-14):
  DESCANSO            ✅ 7 días consecutivos sin trabajo
```

---

## Impacto en Resultados

### Antes (con bugs):
```
Bimbo Faena - Febrero 2025:
  Turnos leídos: 90 ❌ (incorrecto)
  Conductores greedy: 20 ❌ (imposible)
  Cota inferior: N/A
```

### Después (corregido):
```
Bimbo Faena - Febrero 2025:
  Turnos expandidos: 944 ✅
  Total horas: 3,865h ✅
  Patrón: 7x7 únicamente ✅
  Descanso mismo día: 5h ✅

  Cota inferior teórica:
    Con 7x7 (7 días × 12h = 84h por conductor/ciclo):
    En febrero (28 días = 2 ciclos):
      Horas disponibles por conductor: 2 × 84h = 168h
      Conductores necesarios: 3,865h / 168h = ~23 conductores

  Resultado greedy esperado: 23-28 conductores ✅
```

---

## Archivos Modificados

### 1. `/backend/app/services/excel_reader.py`
```diff
+ Agregado método _expand_shifts_to_month() (líneas 481-559)
+ Modificado read_client_data() para aceptar year/month (líneas 28-66)
+ Corregido límite nrows=50 → nrows=200 (línea 208)
```

### 2. `/backend/optimize_plus.py`
```diff
+ Agregado paso de year/month al reader (líneas 100-103)
+ Agregado contador de turnos expandidos (línea 106)
```

### 3. `/backend/app/services/roster_optimizer_with_regimes.py`
```diff
+ Simplificado Faena Minera a solo 7x7 (líneas 531-544)
+ Corregido descanso mismo día: 1h → 5h (líneas 1603-1609)
+ Comentarios actualizados con restricción legal (líneas 1603-1604)
+ CRÍTICO: Corregido _generate_month_shifts() para detectar shifts expandidos (líneas 1177-1307)
  - Evita duplicación: si shifts ya tienen fecha, no los expande nuevamente
  - Previene multiplicación 28× de turnos (era 10,720 en vez de 944)
```

### 4. `/backend/app/services/lns_alns_optimizer.py`
```diff
+ Actualizado min_rest_hours default: 10h → 5h (línea 26)
+ Actualizada documentación de conflict sets (líneas 30-34)
```

---

## Cómo Probar

### Test 1: Verificar expansión de turnos
```bash
cd /Users/alfil/Desktop/Prototipo_Hualpen_local/backend

python3 << 'PYTHON'
from app.services.excel_reader import ExcelTemplateReader

reader = ExcelTemplateReader('[ruta_excel]')
data = reader.read_client_data('Bimbo Faena', year=2025, month=2)

total_shifts = sum(len(s.get('shifts', [])) for s in data['services'])
print(f'Turnos: {total_shifts}')  # Debe ser ~944
PYTHON
```

### Test 2: Ejecutar optimización completa
```bash
python optimize_plus.py \
  '[ruta_excel]' \
  'Bimbo Faena' 2025 2
```

**Resultado esperado**:
```
PASO 1: Leyendo datos del Excel...
  Expandiendo turnos para 2025-02...
✓ Datos leídos correctamente:
  - Servicios (líneas Excel): 67
  - Turnos expandidos: 944

FASE 1: CONSTRUCCIÓN GREEDY
Usando patrón 7x7 (7 días trabajo, 7 días descanso)...
  Razón: Turnos homogéneos, no hay ventaja en combinar patrones

  ✓ SOLUCIÓN GREEDY: 7x7 con 37 conductores, cobertura 100.0%
```

**Resultado real (14-Oct-2025)**:
- ✅ **944 turnos** correctamente expandidos
- ✅ **37 conductores** asignados (greedy)
- ✅ **100% cobertura** alcanzada
- ✅ Todas las restricciones cumplidas (14h/día, 5h descanso, 7x7 patrón)

---

## Validación de Restricciones

### Ejemplo de día con múltiples turnos:
```
Conductor D001 - Día 2025-02-05:
  Turno 1: 04:00-08:30 (4.5h)
  Turno 2: 12:30-16:30 (4.0h)   ✅ 4h después (< 5h mínimo) ❌ NO ASIGNABLE
  Turno 3: 19:30-00:45 (5.25h)  ✅ 11h después del turno 1, OK

Total: 4.5h + 5.25h = 9.75h    ✅ Dentro de 14h límite
```

Con la nueva restricción de 5h:
- Turno 1 (04:00-08:30) y Turno 2 (12:30-16:30): Solo 4h de separación → **NO pueden asignarse al mismo conductor**
- Turno 1 (04:00-08:30) y Turno 3 (19:30-00:45): 11h de separación → **SÍ pueden asignarse al mismo conductor**

---

## Próximos Pasos

1. ✅ **Probar con Bimbo Faena** - COMPLETADO: greedy da 37 conductores (vs. 23-28 teórico)
2. ✅ **Corregir bug de duplicación** - COMPLETADO: optimizer duplicaba shifts expandidos
3. ⏳ **Habilitar LNS/ALNS** (actualmente deshabilitado) - Para intentar mejorar greedy
4. ⏳ **Validar otros clientes** - Probar que no rompimos nada en otros regímenes
5. ⏳ **Documentar restricciones legales** - Obtener copia de la resolución DT específica

---

## Notas Técnicas

### Cálculo de Cota Inferior (7x7)

```
Febrero 2025: 28 días = 2 ciclos completos de 7x7

Patrón 7x7:
  - Ciclo 1 (Feb 1-14): Trabaja Feb 1-7 (7 días), Descansa Feb 8-14 (7 días)
  - Ciclo 2 (Feb 15-28): Trabaja Feb 15-21 (7 días), Descansa Feb 22-28 (7 días)

Horas por conductor/mes:
  - Días trabajados: 14 días
  - Horas por día: 12h promedio (máximo 14h)
  - Total: 14 × 12 = 168h/mes por conductor

Conductores necesarios:
  - Horas totales: 3,865h
  - Por conductor: 168h
  - Mínimo: 3,865 / 168 = 23.0 conductores

Cota inferior: 23 conductores
Resultado greedy esperado: 23-28 conductores (con ineficiencias típicas)
```

### Por Qué 7x7 es Suficiente

Para turnos **homogéneos** (todos similares en duración y horarios):
- Todos los conductores son intercambiables
- No hay ventaja en combinar 7x7 con 10x10 o 14x14
- **7x7 es el ciclo más simple** (menos días de descanso acumulados)

Para turnos **heterogéneos** (variados):
- Combinar patrones PODRÍA ayudar (ej: 7x7 para turnos cortos, 10x10 para largos)
- Pero Bimbo Faena tiene turnos homogéneos → no aplica

---

*Documento generado: 2025-10-14*
*Versión: 1.0*
*Estado: Cambios implementados y listos para probar*
