# Archivos Obsoletos / Old Files

Esta carpeta contiene archivos que **ya no se usan** en el sistema actual.

Fueron movidos aquí el **14 de Octubre 2025** para limpiar el directorio `/services/`.

---

## Contenido (21 archivos, ~324 KB total)

### Archivos Vacíos (9 archivos, 0 bytes)
Nunca fueron implementados:

- `roster_optimizer.py`
- `roster_optimizer_advanced.py`
- `roster_optimizer_compliant.py`
- `roster_optimizer_jornada.py`
- `roster_optimizer_validated.py`
- `capacity_analyzer.py`
- `optimization_service.py`
- `service_service.py`

**Acción recomendada**: Pueden eliminarse permanentemente.

---

### Optimizadores Antiguos Reemplazados (8 archivos, ~226 KB)
Prototipos y versiones anteriores reemplazadas por `roster_optimizer_with_regimes.py`:

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `roster_optimizer_adaptive.py` | 53 KB | Optimizador adaptativo (reemplazado) |
| `roster_optimizer_fixed.py` | 39 KB | Versión con patrones fijos (reemplazado) |
| `roster_optimizer_improved.py` | 31 KB | Versión mejorada intermedia (reemplazado) |
| `roster_optimizer_v2.py` | 32 KB | Versión 2 (reemplazado) |
| `roster_optimizer_heuristic.py` | 22 KB | Enfoque heurístico (reemplazado) |
| `roster_optimizer_annual_pattern.py` | 21 KB | Patrones anuales (integrado en with_regimes) |
| `roster_optimizer_simple.py` | 15 KB | Prototipo simple inicial (reemplazado) |
| `roster_optimizer_fixed_backup.py` | 13 KB | Backup de versión antigua (reemplazado) |

**Razón de reemplazo**: Todos fueron reemplazados por `roster_optimizer_with_regimes.py` que:
- Soporta múltiples regímenes laborales (Interurbano, Urbano, Faena Minera, etc.)
- Implementa greedy constructivo + CP-SAT optimization
- Maneja patrones NxN (7x7, 10x10, 14x14)
- Es más robusto y completo

**Acción recomendada**: Mantener 6 meses como backup, luego eliminar si no se necesitan.

---

### Engines Legacy (3 archivos, ~48 KB)
Versiones pre-OR-Tools del motor de optimización:

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `optimization_engine_ortools.py` | 23 KB | Primera versión OR-Tools (deprecada) |
| `output_generator_enhanced.py` | 16 KB | Generador de salida mejorado (no usado) |
| `optimization_engine.py` | 8.7 KB | Motor pre-OR-Tools (deprecado) |

**Acción recomendada**: Mantener como referencia histórica o eliminar.

---

### Servicios No Usados (2 archivos, ~17 KB)

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `simulation_service.py` | 9.2 KB | Servicio de simulación (nunca usado) |
| `driver_service.py` | 8 KB | Servicio de conductores (nunca usado) |

**Acción recomendada**: Evaluar si se necesitarán en el futuro. Si no, eliminar.

---

## Archivos ACTIVOS que permanecen en `/services/`

Solo **8 archivos** permanecen activos:

1. **`roster_optimizer_with_regimes.py`** (116 KB) - **OPTIMIZADOR PRINCIPAL**
2. `excel_reader.py` (21 KB) - Lee template Excel
3. `output_generator.py` (25 KB) - Genera archivos de salida
4. `html_report_generator.py` (33 KB) - Genera reportes HTML
5. `roster_optimizer_traditional.py` (44 KB) - Usado en `analyze_capacity.py`
6. `roster_optimizer_grouped.py` (40 KB) - Usado en `optimize_turns.py`
7. `traditional_patterns.py` (7.4 KB) - Patrones tradicionales
8. `__init__.py` (0 B) - Módulo Python

---

## Historial de Cambios

**2025-10-14**:
- Movidos 21 archivos obsoletos desde `/services/` a `/services/old/`
- Reducción: 29 → 8 archivos activos (72% menos archivos)
- Sistema actual usa **solo** `roster_optimizer_with_regimes.py` como optimizador principal

---

## Contacto

Para preguntas sobre archivos específicos, revisar:
- Análisis completo: `/ANALISIS_ARCHIVOS_BACKEND.md`
- Git history: `git log --follow -- <archivo>`
