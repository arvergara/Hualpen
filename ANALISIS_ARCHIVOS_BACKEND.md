# Análisis de Archivos en Backend

## Resumen Ejecutivo

De **33 archivos** en `/backend/app/services/`, solo **~10 archivos se usan activamente**. El resto son **versiones antiguas, prototipos abandonados o archivos vacíos**.

---

## ARCHIVOS ACTUALMENTE EN USO ✅

### Scripts Principales (en `/backend/`)

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| **optimize_plus.py** | Script principal de optimización con regímenes laborales | ✅ ACTIVO |
| optimize_turns.py | Script antiguo con múltiples optimizadores comentados | ⚠️ DEPRECADO |
| analyze_capacity.py | Análisis de capacidad (tradicional) | ⚠️ USO OCASIONAL |
| diagnose_bimbo.py | Diagnóstico específico de cliente | ⚠️ USO OCASIONAL |

### Servicios Core (en `/backend/app/services/`)

| Archivo | Tamaño | Líneas | Usado por | Estado |
|---------|--------|--------|-----------|--------|
| **roster_optimizer_with_regimes.py** | 116 KB | 2,526 | optimize_plus.py | ✅ ACTIVO - Principal |
| **excel_reader.py** | 21 KB | ~500 | optimize_plus.py, optimize_turns.py | ✅ ACTIVO |
| **output_generator.py** | 25 KB | ~600 | optimize_plus.py, optimize_turns.py | ✅ ACTIVO |
| **html_report_generator.py** | 33 KB | ~800 | optimize_plus.py, optimize_turns.py | ✅ ACTIVO |
| **roster_optimizer_traditional.py** | 44 KB | 975 | optimize_turns.py, analyze_capacity.py | ⚠️ SECUNDARIO |
| **roster_optimizer_grouped.py** | 40 KB | 898 | optimize_turns.py | ⚠️ SECUNDARIO |
| **traditional_patterns.py** | 7.4 KB | ~180 | roster_optimizer_traditional.py | ⚠️ SECUNDARIO |
| simulation_service.py | 9.2 KB | ~220 | (no usado actualmente) | ⚠️ INACTIVO |
| driver_service.py | 8 KB | ~200 | (no usado actualmente) | ⚠️ INACTIVO |

---

## ARCHIVOS NO USADOS / DEPRECADOS ❌

### Optimizadores Antiguos (NO SE USAN)

| Archivo | Tamaño | Razón de Deprecación |
|---------|--------|----------------------|
| roster_optimizer_adaptive.py | 53 KB (1,064 líneas) | Reemplazado por roster_optimizer_with_regimes.py |
| roster_optimizer_fixed.py | 39 KB (837 líneas) | Prototipo antiguo |
| roster_optimizer_improved.py | 31 KB (691 líneas) | Prototipo antiguo |
| roster_optimizer_v2.py | 32 KB (709 líneas) | Versión intermedia abandonada |
| roster_optimizer_heuristic.py | 22 KB (551 líneas) | Enfoque heurístico descartado |
| roster_optimizer_annual_pattern.py | 21 KB (506 líneas) | Lógica integrada en with_regimes |
| roster_optimizer_simple.py | 15 KB (359 líneas) | Prototipo simple inicial |
| roster_optimizer_fixed_backup.py | 13 KB (334 líneas) | Backup de versión antigua |

### Archivos Vacíos (0 bytes)

| Archivo | Propósito Original |
|---------|-------------------|
| roster_optimizer.py | Clase base planeada (nunca implementada) |
| roster_optimizer_advanced.py | Versión avanzada planeada (nunca implementada) |
| roster_optimizer_compliant.py | Optimizador con cumplimiento (nunca implementado) |
| roster_optimizer_jornada.py | Optimizador por jornada (nunca implementado) |
| roster_optimizer_validated.py | Validador planeado (nunca implementado) |
| capacity_analyzer.py | Analizador de capacidad (nunca implementado) |
| optimization_service.py | Servicio de optimización (nunca implementado) |
| service_service.py | Servicio genérico (nunca implementado) |
| __init__.py | Módulo services (vacío) |

### Optimizadores Legacy (No Usados Actualmente)

| Archivo | Tamaño | Última Referencia |
|---------|--------|-------------------|
| optimization_engine.py | 8.7 KB | Código antiguo pre-OR-Tools |
| optimization_engine_ortools.py | 23 KB | Primera versión OR-Tools (deprecada) |
| output_generator_enhanced.py | 16 KB | Versión mejorada de output (no usada) |

---

## FLUJO DE EJECUCIÓN ACTUAL

### Script Principal: `optimize_plus.py`

```
optimize_plus.py
├── Importa: ExcelTemplateReader (excel_reader.py)
├── Importa: OutputGenerator (output_generator.py)
├── Importa: HTMLReportGenerator (html_report_generator.py)
└── Importa: RosterOptimizerWithRegimes (roster_optimizer_with_regimes.py)
    └── Este es el ÚNICO optimizador usado actualmente
```

### Script Secundario: `optimize_turns.py` (Deprecado)

```
optimize_turns.py
├── Importa: ExcelTemplateReader
├── Importa: OutputGenerator
├── Importa: EnhancedOutputGenerator (no usado)
├── Importa: HTMLReportGenerator
├── Importa COMENTADOS (no activos):
│   ├── AdaptiveRosterOptimizer
│   ├── ImprovedRosterOptimizer
│   ├── RobustRosterOptimizer
│   └── SimpleRosterOptimizer
└── Importa ACTIVOS (pero script deprecado):
    ├── GroupedRosterOptimizer
    └── TraditionalRosterOptimizer
```

---

## DEPENDENCIAS ACTIVAS (Grafo)

```
optimize_plus.py (PRINCIPAL)
    ↓
    ├─→ excel_reader.py ✅
    ├─→ output_generator.py ✅
    ├─→ html_report_generator.py ✅
    └─→ roster_optimizer_with_regimes.py ✅
            └─→ Google OR-Tools CP-SAT
            └─→ traditional_patterns.py (probablemente)

analyze_capacity.py (OCASIONAL)
    ↓
    ├─→ excel_reader.py ✅
    └─→ roster_optimizer_traditional.py ⚠️
            └─→ traditional_patterns.py ⚠️
```

---

## RECOMENDACIONES DE LIMPIEZA

### Acción 1: Eliminar Archivos Vacíos (9 archivos)
**Impacto**: CERO (0 bytes, nunca implementados)

```bash
rm backend/app/services/roster_optimizer.py
rm backend/app/services/roster_optimizer_advanced.py
rm backend/app/services/roster_optimizer_compliant.py
rm backend/app/services/roster_optimizer_jornada.py
rm backend/app/services/roster_optimizer_validated.py
rm backend/app/services/capacity_analyzer.py
rm backend/app/services/optimization_service.py
rm backend/app/services/service_service.py
```

### Acción 2: Mover Optimizadores Antiguos a `/archive/` (8 archivos)
**Impacto**: Libera ~250 KB, elimina confusión

```bash
mkdir -p backend/app/services/archive/

mv backend/app/services/roster_optimizer_adaptive.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_fixed.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_fixed_backup.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_improved.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_v2.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_heuristic.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_annual_pattern.py backend/app/services/archive/
mv backend/app/services/roster_optimizer_simple.py backend/app/services/archive/
```

### Acción 3: Mover Optimizadores Legacy a `/archive/` (3 archivos)
**Impacto**: Libera ~48 KB

```bash
mv backend/app/services/optimization_engine.py backend/app/services/archive/
mv backend/app/services/optimization_engine_ortools.py backend/app/services/archive/
mv backend/app/services/output_generator_enhanced.py backend/app/services/archive/
```

### Acción 4: Considerar Deprecar `optimize_turns.py`
**Razón**: `optimize_plus.py` es el script principal ahora

**Opciones**:
1. Eliminar completamente si no se usa
2. Mover a `/archive/` si quieren conservarlo
3. Dejarlo si aún se usa ocasionalmente

---

## ESTRUCTURA LIMPIA PROPUESTA

Después de limpieza, quedarían **solo 10 archivos** en `/services/`:

```
backend/app/services/
├── __init__.py (actualizar si es necesario)
├── excel_reader.py ✅ (21 KB)
├── output_generator.py ✅ (25 KB)
├── html_report_generator.py ✅ (33 KB)
├── roster_optimizer_with_regimes.py ✅ (116 KB) - PRINCIPAL
├── roster_optimizer_traditional.py ⚠️ (44 KB) - Solo si se usa en analyze_capacity
├── roster_optimizer_grouped.py ⚠️ (40 KB) - Solo si se usa en optimize_turns
├── traditional_patterns.py ⚠️ (7.4 KB) - Dependencia de traditional
├── simulation_service.py ? (9.2 KB) - Verificar si se usa
├── driver_service.py ? (8 KB) - Verificar si se usa
└── archive/ (20 archivos antiguos)
```

**Total archivos activos**: 10 (vs 33 actuales)
**Reducción**: 70% de archivos

---

## VERIFICACIÓN ANTES DE ELIMINAR

Antes de ejecutar cualquier limpieza, **verificar**:

1. ¿Se usa `optimize_turns.py` actualmente?
   ```bash
   # Buscar referencias en otros scripts
   grep -r "optimize_turns" backend/
   ```

2. ¿Se usa `roster_optimizer_traditional.py`?
   ```bash
   grep -r "roster_optimizer_traditional" backend/
   ```

3. ¿Se usa `roster_optimizer_grouped.py`?
   ```bash
   grep -r "roster_optimizer_grouped" backend/
   ```

4. ¿Se usa `simulation_service.py` o `driver_service.py`?
   ```bash
   grep -r "simulation_service\|driver_service" backend/
   ```

---

## RESPUESTA DIRECTA A TU PREGUNTA

**"¿Cuáles archivos realmente se usan?"**

### En `/backend/app/services/`, SOLO estos 4 archivos se usan activamente:

1. **excel_reader.py** - Lee template de Excel
2. **output_generator.py** - Genera archivos de salida
3. **html_report_generator.py** - Genera reportes HTML
4. **roster_optimizer_with_regimes.py** - Optimizador principal (2,526 líneas)

### Estos 3 archivos se usan ocasionalmente:

5. **roster_optimizer_traditional.py** - En `analyze_capacity.py`
6. **roster_optimizer_grouped.py** - En `optimize_turns.py` (si aún se usa)
7. **traditional_patterns.py** - Dependencia de traditional

### Los otros **26 archivos** (79%) están **OBSOLETOS** o **VACÍOS**:
- 9 archivos vacíos (0 bytes)
- 8 optimizadores antiguos reemplazados (250 KB)
- 3 engines legacy (48 KB)
- 2 servicios no usados (simulation, driver)
- 4 otros (backups, etc.)

**Conclusión**: El 79% de los archivos en `/services/` NO se usan.

---

*Análisis generado: 2025-10-14*
*Basado en: imports en scripts, tamaño de archivos, y flujo de ejecución*
