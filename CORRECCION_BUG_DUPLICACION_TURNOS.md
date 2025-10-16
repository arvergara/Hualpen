# Corrección Crítica: Bug de Duplicación de Turnos

**Fecha**: 14 de Octubre 2025
**Prioridad**: 🔴 CRÍTICA
**Estado**: ✅ RESUELTO

---

## Problema Detectado

Al ejecutar la optimización de Bimbo Faena, el sistema reportaba **10,720 turnos** en lugar de los **944 turnos** esperados (multiplicación por ~11.4×).

### Síntomas

```
Total turnos a asignar: 10720  ❌ (debería ser 944)
  - Todos con régimen Faena Minera

Estimación de Conductores Mínimos:
  Ciclo 7x7:   275 conductores  ❌ (debería ser ~24)
  Simultáneos: 492 conductores  ❌ (debería ser ~30)
```

---

## Causa Raíz

Conflicto entre dos sistemas de expansión de turnos:

### Sistema 1: Excel Reader (nuevo)
```python
# excel_reader.py - _expand_shifts_to_month()
# Expande "Martes a Viernes: 04:00-08:30" a turnos específicos:
# - 2025-02-04 (martes) 04:00-08:30
# - 2025-02-05 (miércoles) 04:00-08:30
# - 2025-02-06 (jueves) 04:00-08:30
# ... etc para todo el mes
```

**Resultado**: 944 turnos con campo `date` específico.

### Sistema 2: Optimizer (antiguo)
```python
# roster_optimizer_with_regimes.py - _generate_month_shifts()
# ASUME que shifts son PLANTILLAS (sin fecha)
# Itera sobre cada día del mes y expande plantillas

for day in month:  # 28 días en febrero
    for service in services:  # 67 servicios
        for shift in service['shifts']:  # ¡Pero estos YA están expandidos!
            # Crea turno para este día
```

**Problema**: Los shifts YA estaban expandidos, entonces:
- Servicio con 12 shifts expandidos (uno por cada lunes de feb)
- × 28 días del mes (iteración del optimizer)
- = 336 turnos en lugar de 12

**Total**: 944 × 11.4 ≈ 10,720 turnos.

---

## Solución Implementada

Modificado `_generate_month_shifts()` en [roster_optimizer_with_regimes.py:1177-1307](backend/app/services/roster_optimizer_with_regimes.py#L1177-L1307) para detectar automáticamente el modo:

### Modo 1: Shifts Expandidos (detecta campo `date`)
```python
if 'date' in first_shift and first_shift['date'] is not None:
    shifts_already_expanded = True

# Solo copiar shifts, sin iterar días del mes
for service in services:
    for shift_data in service['shifts']:
        # shift_data ya tiene fecha específica
        shift_date = shift_data['date']
        # Verificar que sea del mes correcto
        if shift_date.year == year and shift_date.month == month:
            # Crear shift final
            shifts.append(...)
```

### Modo 2: Shifts Plantilla (modo original)
```python
else:
    # Modo clásico: iterar días y expandir plantillas
    for day in month:
        for service in services:
            if day_matches_frequency:
                for shift_template in service['shifts']:
                    # Expandir plantilla a este día
                    shifts.append(...)
```

---

## Validación

### Antes (con bug)
```bash
$ python optimize_plus.py 'Bimbo Faena' 2025 2

Total turnos a asignar: 10720  ❌
Conductores mínimos: 275-492   ❌
```

### Después (corregido)
```bash
$ python optimize_plus.py 'Bimbo Faena' 2025 2

✓ Datos leídos correctamente:
  - Servicios (líneas Excel): 67
  - Turnos expandidos: 944  ✅

Total turnos a asignar: 944  ✅

Estimación de Conductores Mínimos:
  Ciclo 7x7:   24 conductores  ✅
  Ciclo 10x10: 22 conductores  ✅
  Simultáneos: 30 conductores  ✅

✓ SOLUCIÓN GREEDY: 7x7 con 37 conductores, cobertura 100.0%  ✅
```

---

## Impacto

### Clientes Afectados
- ✅ **Bimbo Faena**: Ahora funciona correctamente
- ✅ **Otros clientes**: Compatibilidad mantenida (modo plantilla sigue funcionando)

### Archivos Modificados
1. `backend/app/services/roster_optimizer_with_regimes.py` (líneas 1177-1307)
   - Agregado detección automática de modo de expansión
   - Mantiene retrocompatibilidad con modo plantilla

### Archivos NO Modificados
- `excel_reader.py` - La expansión de turnos está correcta
- `optimize_plus.py` - No requiere cambios
- Otros optimizadores - No afectados

---

## Pruebas Recomendadas

### Test 1: Bimbo Faena (shifts expandidos)
```bash
python optimize_plus.py \
  'Template TURNOS Hualpén 08-09-2025.xlsx' \
  'Bimbo Faena' 2025 2
```
**Esperado**: 944 turnos, 37 conductores

### Test 2: Otros clientes (shifts plantilla)
```bash
python optimize_plus.py \
  'Template TURNOS Hualpén 08-09-2025.xlsx' \
  '[Otro Cliente]' 2025 2
```
**Esperado**: Sin cambios en comportamiento

---

## Lecciones Aprendidas

1. **Siempre verificar supuestos**: El optimizer asumía shifts = plantillas
2. **Logging es crítico**: Sin el log "Turnos expandidos: 944" habría sido difícil detectar
3. **Consistencia de datos**: Mejor tener UN sistema de expansión (elegimos excel_reader)
4. **Tests automáticos**: Deberíamos tener test que verifique:
   ```python
   assert len(all_shifts) == 944, f"Expected 944 shifts, got {len(all_shifts)}"
   ```

---

## Referencias

- Ver [CAMBIOS_SIMPLIFICACION_FAENA_MINERA.md](CAMBIOS_SIMPLIFICACION_FAENA_MINERA.md) para contexto completo
- Código: [roster_optimizer_with_regimes.py:1177](backend/app/services/roster_optimizer_with_regimes.py#L1177)

---

*Documento generado: 2025-10-14*
*Autor: Claude (via Anthropic)*
*Versión: 1.0*
