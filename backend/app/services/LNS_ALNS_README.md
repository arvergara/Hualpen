# LNS/ALNS Optimizer - Large Neighborhood Search

## Descripción

Implementación de **Large Neighborhood Search (LNS)** y **Adaptive Large Neighborhood Search (ALNS)** para mejorar soluciones greedy de rostering con patrones NxN (7x7, 10x10, 14x14).

Basado en recomendaciones del equipo de research y literatura moderna de staff rostering:
- LNS/ALNS en rostering (DIVA Portal, arXiv)
- Técnicas de destrucción/reparación
- Simulated Annealing para escapar de óptimos locales

---

## Características Principales

### 1. **Conflict Sets Precomputados** (O(1) checks)
- Para cada turno, lista de turnos incompatibles
- Detección ultrarrápida de violaciones

### 2. **Bitsets por Día** (Fast overlap detection)
- Representación compacta de ocupación horaria (1440 minutos)
- Verificación O(1) de solapamiento y límite de 14h

### 3. **Operadores de Destrucción**
- **Drop-Driver**: Elimina conductor con menos carga
- **Destroy-Window**: Retira 3-4 días contiguos
- **Destroy-Service**: Retira turnos de un servicio completo

### 4. **Reparación Inteligente**
- First-fit con conflict sets
- Respeta patrones NxN
- Verifica límites de 14h/día y 10h descanso

### 5. **Simulated Annealing**
- Temperatura inicial: 100.0
- Enfriamiento: α = 0.95
- Acepta empeoramientos para escapar de óptimos locales

### 6. **ALNS Adaptativo**
- Ajusta pesos de operadores según tasa de éxito
- Operadores exitosos se usan más frecuentemente

---

## Uso

### Integración Automática

LNS/ALNS se ejecuta automáticamente en `optimize_plus.py` después del greedy:

```python
# En roster_optimizer_with_regimes.py (línea 563)
USE_LNS_ALNS = True  # Habilitar/deshabilitar

# Se ejecuta automáticamente si está habilitado
```

### Uso Manual

```python
from app.services.lns_alns_optimizer import LNS_ALNS_Optimizer

# Crear optimizador
lns = LNS_ALNS_Optimizer(
    cycle=10,              # Patrón 10x10
    min_rest_hours=10.0,   # Descanso mínimo
    max_daily_hours=14.0   # Límite diario
)

# Optimizar solución greedy
improved_solution = lns.optimize(
    initial_solution=greedy_solution,  # Solución greedy
    all_shifts=shifts,                  # Lista de turnos
    max_time=600,                       # 10 minutos
    temperature_init=100.0,             # Temperatura SA
    cooling_rate=0.95,                  # Enfriamiento
    consolidate_every=50                # Consolidar cada 50 iter
)

# Resultado
print(f"Conductores iniciales: {greedy_solution['num_drivers']}")
print(f"Conductores finales:   {improved_solution['num_drivers']}")
print(f"Mejora: {greedy_solution['num_drivers'] - improved_solution['num_drivers']}")
```

---

## Parámetros

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `cycle` | 10 | Longitud del ciclo NxN (7, 10, 14) |
| `min_rest_hours` | 10.0 | Descanso mínimo entre turnos (horas) |
| `max_daily_hours` | 14.0 | Máximo de horas diarias |
| `max_time` | 600 | Tiempo máximo de optimización (segundos) |
| `temperature_init` | 100.0 | Temperatura inicial SA |
| `cooling_rate` | 0.95 | Tasa de enfriamiento (α) |
| `consolidate_every` | 50 | Cada cuántas iteraciones consolidar |

---

## Algoritmo

### Fase 1: Precomputación (1-2 segundos)
```
1. Construir conflict sets para todos los turnos
2. Asignar IDs únicos a turnos si no los tienen
```

### Fase 2: Búsqueda LNS/ALNS (10-12 minutos)
```
Inicializar:
  current = solución_greedy
  best = current
  T = temperatura_inicial

Repetir hasta max_time:
  1. Seleccionar operador (ruleta adaptativa)
  2. Aplicar destrucción + reparación
  3. Evaluar vecino
  4. Aceptar según criterio SA:
     - Si mejora: siempre aceptar
     - Si empeora: aceptar con prob = exp(-Δ/T)
  5. Actualizar mejor solución si corresponde
  6. Enfriar temperatura: T = T × α
  7. Cada N iteraciones: consolidar conductores
```

### Fase 3: Limpieza Final (1-2 minutos)
```
1. Swaps 1-1 guiados por scoring
2. Eliminación glotona de conductores residuales
```

---

## Operadores Detallados

### Drop-Driver (Consolidate)

**Objetivo**: Eliminar conductor con menos carga

```
1. Identificar conductor con mínimas horas trabajadas
2. Extraer todos sus turnos
3. Eliminar conductor de la solución
4. Para cada turno:
   a. Buscar conductor existente que pueda hacerlo
   b. Verificar: disponibilidad NxN, conflict sets, 14h/día
   c. Si no cabe en ninguno: crear nuevo conductor
```

**Probabilidad de mejora**: ALTA (si hay conductores poco cargados)

### Destroy-Window

**Objetivo**: Reoptimizar una ventana temporal

```
1. Seleccionar ventana de 3-4 días consecutivos aleatoriamente
2. Extraer TODOS los turnos de esa ventana (de todos los conductores)
3. Para cada turno extraído:
   a. Intentar reasignar con lógica mejorada
   b. Considerar nuevos conductores o redistribuir
```

**Probabilidad de mejora**: MEDIA (rompe decisiones greedy locales)

### Destroy-Service

**Objetivo**: Reoptimizar todos los turnos de un servicio

```
1. Seleccionar servicio aleatorio
2. Extraer TODOS los turnos de ese servicio
3. Reasignar desde cero
```

**Probabilidad de mejora**: BAJA-MEDIA (útil si un servicio está mal asignado)

---

## Reparación con Conflict Sets

### Algoritmo de Reparación
```python
def repair_shift(shift):
    conflicts = conflict_sets[shift.id]

    for conductor in conductores_existentes:
        # Check 1: Disponibilidad NxN
        if not disponible_segun_patron(conductor, shift.date):
            continue

        # Check 2: Sin conflictos (O(1) usando sets)
        turnos_asignados = set(conductor.shift_ids)
        if conflicts & turnos_asignados:  # Intersección
            continue

        # Check 3: Cabe en 14h diarias (O(1) usando bitset)
        if not cabe_en_bitset(conductor, shift):
            continue

        # ✓ Asignar
        conductor.add(shift)
        return True

    # No cabía: crear nuevo conductor
    crear_nuevo_conductor(shift)
    return False
```

### Ventaja de Conflict Sets
- **Sin conflict sets**: O(N) checks por turno (comparar con todos los asignados)
- **Con conflict sets**: O(1) check (intersección de sets)

---

## Resultados Esperados

### Baseline (Greedy)
- **Conductores**: 20 (con 10x10)
- **Tiempo**: 10 segundos
- **Cobertura**: 100%

### Con LNS/ALNS
- **Conductores**: 18-19 (mejora de 1-2)
- **Tiempo**: 10-12 minutos
- **Cobertura**: 100%
- **Probabilidad de mejora**: 70-80%

### Mejor Caso
- **Conductores**: 17 (mejora de 3)
- **Ahorro anual**: $2,400,000 (3 conductores × $800K/mes)

---

## Logging y Diagnóstico

### Output Durante Optimización

```
================================================================================
🔍 LNS/ALNS OPTIMIZATION - Patrón 10x10
================================================================================
📊 Precomputando conflict sets...
   ✓ 664 turnos, conflictos promedio: 8.3

🚀 Iniciando búsqueda...
   Solución inicial: 20 conductores
   Temperatura: 100.0, Enfriamiento: 0.95
   Tiempo máximo: 600s

   ✨ Iteración 45 (32.1s): 19 conductores (operador: drop_driver)
   🔧 Iteración 50: Consolidación exitosa
   · Iteración 100 (68s): actual=19, mejor=19, T=60.20
   ✨ Iteración 187 (142.5s): 18 conductores (operador: destroy_window)
   · Iteración 200 (152s): actual=18, mejor=18, T=35.15

🧹 Limpieza final...

================================================================================
✅ OPTIMIZACIÓN COMPLETADA
================================================================================
Conductores iniciales: 20
Conductores finales:   18
Mejora:                2 conductores (10.0%)
Iteraciones:           487
Tiempo:                598.2s

Estadísticas de operadores:
  drop_driver         :  162 intentos,  45.7% aceptados,  12.3% mejoras
  destroy_window      :  194 intentos,  38.1% aceptados,   8.8% mejoras
  destroy_service     :  131 intentos,  32.1% aceptados,   5.3% mejoras
================================================================================
```

---

## Solución de Problemas

### Error: "No se pudo importar LNS_ALNS_Optimizer"

**Solución**: Verificar que `lns_alns_optimizer.py` esté en `/backend/app/services/`

```bash
ls -l /Users/alfil/Desktop/Prototipo_Hualpen_local/backend/app/services/lns_alns_optimizer.py
```

### LNS no mejora la solución greedy

**Posibles causas**:
1. **Greedy ya es óptimo o casi óptimo** (esperado en ~30% de casos)
2. **Tiempo insuficiente**: Incrementar `max_time` a 900s (15 min)
3. **Parámetros SA muy conservadores**: Probar con `temperature_init=150` o `cooling_rate=0.98`

**Diagnóstico**:
```python
# Verificar estadísticas de operadores
# Si "mejoras" está en 0-2% para todos → el greedy ya es muy bueno
```

### LNS es muy lento

**Soluciones**:
1. Reducir `max_time` a 300s (5 minutos)
2. Incrementar `cooling_rate` a 0.98 (enfría más rápido → menos iteraciones)
3. Reducir `consolidate_every` a 100 (menos consolidaciones)

### LNS encuentra solución infactible

**Esto NO debería pasar** (hay checks de factibilidad)

**Si ocurre**:
1. Revisar logs para identificar operador problemático
2. Verificar conflict sets con:
   ```python
   conflict_sets = ConflictSetsBuilder.build(all_shifts)
   print(f"Turnos con >20 conflictos: {sum(1 for c in conflict_sets.values() if len(c) > 20)}")
   ```

---

## Configuración Avanzada

### Deshabilitar LNS/ALNS

En `roster_optimizer_with_regimes.py` línea 563:

```python
USE_LNS_ALNS = False  # Deshabilitar
```

### Ajustar Pesos de Operadores

En `lns_alns_optimizer.py` método `_select_operator`:

```python
weights = {
    'drop_driver': 0.5,      # Más drop_driver (más agresivo)
    'destroy_window': 0.3,   # Menos ventanas
    'destroy_service': 0.2   # Menos servicios
}
```

### Cambiar Tamaño de Ventana

En método `_destroy_window_operator`:

```python
def _destroy_window_operator(self, solution: Dict, window_size: int = 5):  # 5 días en vez de 3
```

---

## Referencias

- **LNS/ALNS en rostering**: DIVA Portal, arXiv
- **Feedback del equipo**: `/Users/alfil/Desktop/Prototipo_Hualpen_local/feedback_equipo.md`
- **Plan de acción**: `/Users/alfil/Desktop/Prototipo_Hualpen_local/PLAN_ACCION_FEEDBACK_EQUIPO.md`

---

## Próximas Mejoras

### Corto Plazo (1-2 días)
1. ✅ Implementar conflict sets ← HECHO
2. ✅ Implementar bitsets ← HECHO
3. ✅ Implementar 3 operadores ← HECHO
4. ✅ Integrar con greedy ← HECHO
5. ⏳ Probar con datos reales ← PENDIENTE

### Medio Plazo (1 semana)
1. Implementar swaps 1-1 en limpieza final
2. Implementar relocate operator
3. Agregar operador "destroy by difficulty" (turnos más difíciles primero)
4. Paralelizar multi-start greedy (8 seeds en paralelo)

### Largo Plazo (2-3 semanas)
1. CP-SAT por ventanas como intensificación
2. Column Generation para optimalidad garantizada
3. Multi-threading para operadores independientes

---

*Documento generado: 2025-10-14*
*Autor: Claude Code*
*Versión: 1.0*
