# Research Prompt: Optimización de Turnos para Faena Minera

## 1. OBJETIVO PRINCIPAL

Encontrar el **número mínimo de conductores** necesario para cubrir todos los turnos de trabajo en una faena minera durante un año completo, respetando todas las restricciones laborales y operativas.

### Métricas de Éxito
- **Primaria**: Minimizar número total de conductores
- **Secundaria**: Maximizar cobertura de turnos (objetivo: 100%)
- **Terciaria**: Minimizar costo total (salarios + bonos)
- **Restricción de Tiempo**: Solución debe encontrarse en máximo 15 minutos

---

## 2. INPUTS DEL PROBLEMA

### 2.1 Turnos a Cubrir
- **Cantidad**: ~664 turnos por mes (varía según mes)
- **Período**: 12 meses (año completo)
- **Información por turno**:
  - `service_id`: Identificador del servicio
  - `shift_number`: Número del turno
  - `date`: Fecha (YYYY-MM-DD)
  - `start_time`: Hora inicio (HH:MM)
  - `end_time`: Hora fin (HH:MM)
  - `duration_hours`: Duración en horas (float)
  - `service_type`: 'Faena Minera' o 'Minera'
  - `vehicle`: Número de vehículo (opcional)

**Ejemplo de datos reales (Febrero 2025):**
```
Total de turnos: 664
Total de horas: 8,627.5 horas
Promedio por día: 307.8 horas/día
Días con turnos: 28 días
Span diario típico: 17-19 horas (requiere 2-3 conductores por día)
```

### 2.2 Patrones de Trabajo (NxN)
Conductores deben seguir uno de estos patrones cíclicos:

| Patrón | Descripción | Ciclo Total | Horas/Mes | Horas/Ciclo |
|--------|-------------|-------------|-----------|-------------|
| **7x7** | 7 días trabajo, 7 días descanso | 14 días | 168h | 84h |
| **10x10** | 10 días trabajo, 10 días descanso | 20 días | 180h | 120h |
| **14x14** | 14 días trabajo, 14 días descanso | 28 días | 168h | 168h |

**Restricción Crítica**: Un conductor con patrón NxN **NO puede trabajar** durante sus N días de descanso. El patrón es estricto y predefinido desde el día de inicio del conductor.

### 2.3 Restricciones Laborales (Art. 38 - Faena Minera)

#### Restricciones Diarias
- **Máximo 14 horas de trabajo por día**
- **Mínimo 10 horas de descanso entre días consecutivos de trabajo**
- Un conductor NO puede tener turnos que se solapen en el mismo día

#### Restricciones Semanales
- **Promedio de 44 horas por semana** (calculado sobre el ciclo completo)
- En práctica: Los patrones NxN cumplen automáticamente si se respetan las 14h/día

#### Restricciones de Continuidad
- Si un conductor termina turno a las 20:00 del día D, puede comenzar el día D+1 solo si:
  - Hay al menos 10 horas de descanso
  - Ejemplo: puede trabajar desde 06:00 del día D+1

### 2.4 Costos
- **Salario base**: $800,000 por conductor/mes
- **Bono por turno**: $5,000 por turno asignado
- **Objetivo**: Minimizar: `(num_conductores × 800,000) + (turnos_asignados × 5,000)`

---

## 3. OUTPUTS ESPERADOS

### 3.1 Asignaciones
Para cada turno, determinar:
```python
{
    'driver_id': 'D001',           # ID del conductor asignado
    'date': '2025-02-15',          # Fecha del turno
    'service': 'Servicio_A',       # Servicio
    'shift': 1,                    # Número de turno
    'start_time': '06:00',         # Hora inicio
    'end_time': '18:00',           # Hora fin
    'duration_hours': 12.0,        # Duración
    'pattern': '10x10'             # Patrón del conductor
}
```

### 3.2 Resumen de Conductores
Para cada conductor utilizado:
```python
{
    'driver_id': 'D001',
    'pattern': '10x10',                    # Patrón asignado
    'work_start_date': '2025-02-01',       # Inicio del primer ciclo
    'total_shifts': 56,                    # Turnos asignados en el año
    'total_hours': 672.0,                  # Horas trabajadas
    'months_active': [2, 3, 4, ...],       # Meses donde trabaja
    'cost': 1,080,000                      # Costo total del conductor
}
```

### 3.3 Métricas Globales
```python
{
    'drivers_used': 18,                    # Total de conductores
    'total_shifts': 7968,                  # Turnos cubiertos (664 × 12)
    'coverage_percentage': 100.0,          # % de turnos cubiertos
    'total_annual_cost': 19,920,000,       # Costo anual total
    'avg_monthly_cost': 1,660,000,         # Costo promedio mensual
    'solution_time_seconds': 45.2          # Tiempo de cómputo
}
```

---

## 4. ESTADO ACTUAL DEL PROBLEMA

### 4.1 Enfoque Implementado (NO FUNCIONA)

**Fase 1: Greedy Constructivo** ✅ FUNCIONA
- Algoritmo: Asigna turnos día por día, creando conductores bajo demanda
- Resultados: **20 conductores con patrón 10x10, 100% cobertura, 10 segundos**
- Código: `_greedy_assignment_single_pattern()` en `roster_optimizer_with_regimes.py:1412-1612`

**Fase 2: CP-SAT Optimization** ❌ NO CONVERGE
- Herramienta: Google OR-Tools CP-SAT Solver
- Objetivo: Mejorar solución greedy (intentar reducir de 20 a 18-19 conductores)
- Variables: ~13,280 variables binarias (20 conductores × 664 turnos)
- Problema: **Se queda colgado indefinidamente** (>3 horas sin progreso)
- Ubicación donde se cuelga: Inmediatamente después de "🔍 Iniciando solver CP-SAT..."

### 4.2 Configuraciones CP-SAT Probadas (Todas Fallan)

```python
# Intento 1: Configuración estándar
solver.parameters.max_time_in_seconds = 120
solver.parameters.num_search_workers = 16
solver.parameters.cp_model_presolve = True
# Resultado: Colgado en presolve (30+ minutos)

# Intento 2: Sin presolve
solver.parameters.cp_model_presolve = False
solver.parameters.num_search_workers = 8
# Resultado: Colgado en fase de búsqueda

# Intento 3: Límite de conflictos
solver.parameters.max_number_of_conflicts = 100000
solver.parameters.linearization_level = 0
# Resultado: Aún colgado, no llega al límite

# Intento 4: Búsqueda simplificada
solver.parameters.search_branching = cp_model.FIXED_SEARCH
# Resultado: Sin mejora
```

### 4.3 Diagnóstico

**Complejidad del Modelo CP-SAT:**
- Variables de asignación: `X[d,s]` ∈ {0,1} para cada conductor d y turno s (13,280 vars)
- Variables de patrón: 4 booleanas por conductor flexible (7x7, 8x8, 10x10, 14x14)
- Restricciones por conductor: ~50 restricciones (diarias, ciclos, descansos)
- Restricciones globales: Cobertura de turnos (664 constraints)
- **Total estimado: 14,000+ variables y 15,000+ restricciones**

**Hipótesis del fallo:**
1. La combinación de patrones NxN con asignaciones binarias crea un espacio de búsqueda demasiado grande
2. Las restricciones de ciclo (días trabajo/descanso) son altamente no-lineales
3. CP-SAT no encuentra un buen "branching" para este tipo de problema
4. Posiblemente hay conflictos lógicos que el solver no puede resolver eficientemente

---

## 5. ESTRATEGIA DE OPTIMIZACIÓN ANUAL

Una vez encontrada la solución óptima para **Febrero 2025** (mes base), se replica a los 11 meses restantes usando **replicación modular**.

### 5.1 Algoritmo de Replicación

**Paso 1: Detectar Patrón Dominante**
```python
# De la solución de febrero, contar patrones
pattern_counts = {'7x7': 2, '10x10': 18, '14x14': 0}
dominant_pattern = '10x10'  # Máximo
cycle_num = 10
modulo = cycle_num * 2  # 20 días
```

**Paso 2: Indexar Asignaciones de Febrero**
```python
# Para cada asignación de febrero
feb_date = datetime(2025, 2, 15)
days_from_feb1 = (feb_date - datetime(2025, 2, 1)).days  # 14
day_in_cycle = (days_from_feb1 % modulo) + 1  # (14 % 20) + 1 = 15

# Indexar por clave compuesta
key = (day_in_cycle, service_id, shift_number, vehicle)
feb_assignments[key] = assignment
```

**Paso 3: Replicar a Otros Meses**
```python
# Para cada turno de marzo
march_date = datetime(2025, 3, 17)
days_from_feb1 = (march_date - datetime(2025, 2, 1)).days  # 44
day_in_cycle = (days_from_feb1 % modulo) + 1  # (44 % 20) + 1 = 5

# Buscar asignación correspondiente
key = (day_in_cycle, service_id, shift_number, vehicle)
if key in feb_assignments:
    # Copiar asignación con nueva fecha
    new_assignment = {**feb_assignments[key], 'date': '2025-03-17'}
```

### 5.2 Justificación del Modulo

| Patrón | Ciclo | Módulo | Razón |
|--------|-------|--------|-------|
| 7x7 | 14 días | **14** | Después de 14 días, el patrón se repite exactamente |
| 10x10 | 20 días | **20** | Después de 20 días, el patrón se repite exactamente |
| 14x14 | 28 días | **28** | Después de 28 días, el patrón se repite exactamente |

**Ejemplo 10x10:**
- Conductor D001 inicia Febrero 1 → trabaja Feb 1-10, descansa Feb 11-20, trabaja Feb 21-28
- El día 21 de febrero es equivalente al día 1 del ciclo (21 - 20 = 1)
- Por tanto, Marzo 13 (41 días desde Feb 1) ≡ día 1 del ciclo (41 % 20 = 1)

---

## 6. TÉCNICAS DE OPTIMIZACIÓN A EVALUAR

### 6.1 Métodos Constructivos Mejorados

#### A. Greedy con Backtracking Limitado
- **Idea**: Extender greedy actual permitiendo "deshacer" últimas N asignaciones
- **Ventaja**: Más rápido que búsqueda completa, mejor que greedy puro
- **Parámetros**: Depth de backtracking (2-5 pasos)

#### B. Greedy con Lookahead
- **Idea**: Al asignar día D, considerar impacto en días D+1, D+2, D+3
- **Ventaja**: Evita decisiones miopes que bloquean asignaciones futuras
- **Costo**: Más lento, pero aún manejable (< 1 minuto)

#### C. Multi-Start Greedy
- **Idea**: Ejecutar greedy 100 veces con diferentes semillas/prioridades
- **Variaciones**: Ordenar turnos por duración, hora inicio, servicio
- **Ventaja**: Probabilidad alta de encontrar solución cercana al óptimo
- **Costo**: 100 × 10 segundos = 16 minutos (aceptable)

### 6.2 Búsqueda Local (Local Search)

#### A. Hill Climbing con Swaps
```
Partir de solución greedy (20 conductores)
Repetir:
    1. Seleccionar 2 conductores aleatorios
    2. Intentar intercambiar algunos turnos entre ellos
    3. Verificar factibilidad (restricciones NxN, 14h/día, 10h descanso)
    4. Si mejora (reduce conductores o costo): aceptar
    5. Si no mejora: rechazar
Hasta: no hay mejoras por K iteraciones
```

**Operadores de vecindad:**
- **Swap**: Intercambiar turno entre conductor A y B
- **Relocate**: Mover turno de A a B
- **Consolidate**: Intentar eliminar conductor con pocos turnos redistribuyendo

#### B. Simulated Annealing
- **Extensión** del Hill Climbing: aceptar soluciones peores con probabilidad decreciente
- **Ventaja**: Escapar de óptimos locales
- **Parámetros clave**:
  - Temperatura inicial: T₀ = 100
  - Tasa de enfriamiento: α = 0.95
  - Criterio aceptación: P = exp(-(cost_new - cost_old) / T)

#### C. Tabu Search
- **Idea**: Mantener lista de movimientos prohibidos (tabu) para evitar ciclos
- **Ventaja**: Exploración más sistemática que Simulated Annealing
- **Parámetros**: Tabu tenure = 10-20 iteraciones

### 6.3 Métodos Poblacionales

#### A. Algoritmos Genéticos
```
Población: 50 soluciones (cada una es una asignación completa)
Generaciones: 100-500

Operadores:
- Crossover: Combinar conductores de padre A con turnos de padre B
- Mutación: Cambiar patrón de un conductor (7x7 → 10x10)
- Selección: Torneo (mejores 20% pasan a siguiente generación)

Función fitness:
  F = -num_conductores × 1000 - costo_total + penalización_violaciones
```

**Desafío**: Mantener factibilidad después de crossover/mutación

#### B. Particle Swarm Optimization (PSO)
- Menos común para problemas combinatorios
- Requiere adaptación (espacio discreto → continuo)
- **No recomendado** para este problema específico

### 6.4 Métodos Exactos Alternativos

#### A. Mixed Integer Programming (MIP) con Gurobi/CPLEX
```python
Variables:
  x[d,s] ∈ {0,1}  # Conductor d asigna turno s
  y[d,p] ∈ {0,1}  # Conductor d usa patrón p
  z[d] ∈ {0,1}    # Conductor d es utilizado

Función objetivo:
  Minimize: Σ z[d] × 800000 + Σ x[d,s] × 5000

Restricciones:
  - Cobertura: Σ_d x[d,s] = 1  ∀ turno s
  - Patrón único: Σ_p y[d,p] = 1  ∀ conductor d
  - Ciclo NxN: Si y[d,'10x10'] = 1 y día t no es día de trabajo → Σ_s en día t: x[d,s] = 0
  - Max 14h/día: Σ_s en día t: x[d,s] × duration[s] ≤ 14
  - Descanso 10h: Si conductor termina turno s1 a hora h1, no puede hacer turno s2 si start[s2] < h1 + 10
```

**Ventaja sobre CP-SAT**: MIP solvers (Gurobi, CPLEX) suelen ser más robustos para problemas de asignación

**Restricción**: Requiere licencia comercial (Gurobi/CPLEX) o usar COIN-OR CBC (gratuito, más lento)

#### B. Column Generation (Descomposición de Dantzig-Wolfe)
```
Master Problem:
  Minimizar: Σ (costo_ruta × usa_ruta)
  Sujeto a: Cada turno está cubierto por alguna ruta

Subproblem (Pricing):
  Generar nuevas "rutas" (secuencias factibles de turnos para 1 conductor)
  que mejoren la solución del master problem

Iteración:
  1. Resolver master con rutas actuales
  2. Resolver pricing para generar nueva ruta con costo reducido negativo
  3. Agregar ruta al master
  4. Repetir hasta convergencia
```

**Ventaja**: Excelente para problemas de gran escala (miles de turnos)
**Desafío**: Complejo de implementar, requiere expertise en optimización

#### C. Constraint Programming con MiniZinc
- Alternativa a CP-SAT: Usar otro solver (Gecode, Chuffed, OR-Tools via MiniZinc)
- **Ventaja**: Sintaxis declarativa más clara
- **Desventaja**: Probablemente mismos problemas de convergencia

### 6.5 Enfoques Híbridos (RECOMENDADOS)

#### A. Greedy + Local Search
```
Fase 1: Multi-Start Greedy (1 minuto)
  → Genera 100 soluciones factibles
  → Selecciona las 10 mejores

Fase 2: Simulated Annealing en cada una (10 × 1 min = 10 min)
  → Refina cada solución independientemente
  → Retorna la mejor encontrada

Total: ~11 minutos (dentro del límite de 15 min)
```

**Probabilidad de éxito**: ALTA
**Complejidad de implementación**: MEDIA

#### B. Greedy + MIP para Refinamiento
```
Fase 1: Greedy (10 segundos)
  → Solución inicial: 20 conductores

Fase 2: MIP con variables fijas parciales (5 minutos)
  → Fijar 15 conductores (los más cargados)
  → Optimizar asignaciones de los 5 restantes
  → Intentar eliminar 1-2 conductores

Total: ~5 minutos
```

**Probabilidad de éxito**: MEDIA-ALTA
**Complejidad de implementación**: MEDIA

#### C. Matheuristic: Descomposición Temporal
```
Dividir mes en 4 semanas (7 días cada una)

Para cada semana w:
  1. Extraer turnos de semana w
  2. Resolver con MIP/CP-SAT (solo 7 días, 160-180 turnos)
     → Más pequeño, converge rápido (1-2 minutos)
  3. Fijar conductores y patrones de semana w

Semana 5 (días 29-30): Asignar greedy considerando continuidad

Total: 4 × 2 min = 8 minutos
```

**Ventaja**: Reduce complejidad exponencial
**Desafío**: Mantener continuidad entre semanas (días 7-8, 14-15, etc.)

---

## 7. COMPARACIÓN DE ENFOQUES

| Enfoque | Tiempo Esperado | Complejidad Impl. | Prob. Mejora Greedy | Garantía Optimalidad |
|---------|----------------|-------------------|---------------------|----------------------|
| Multi-Start Greedy | 1-2 min | BAJA | 60% | NO |
| Simulated Annealing | 5-10 min | MEDIA | 70% | NO |
| Tabu Search | 5-10 min | MEDIA | 70% | NO |
| Algoritmos Genéticos | 10-30 min | ALTA | 60% | NO |
| MIP (Gurobi/CPLEX) | 5-15 min | MEDIA | 80% | SÍ (si converge) |
| Column Generation | 10-30 min | MUY ALTA | 90% | SÍ (si converge) |
| **Greedy + Simulated Annealing** | **10 min** | **MEDIA** | **75%** | **NO** |
| **Greedy + MIP Refinamiento** | **5-10 min** | **MEDIA** | **80%** | **NO** |
| **Matheuristic (Descomp. Semanal)** | **8-12 min** | **MEDIA-ALTA** | **85%** | **NO** |

---

## 8. EXPERIMENTOS PROPUESTOS

### Experimento 1: Validar Baseline Greedy
**Objetivo**: Confirmar si 20 conductores (10x10) es razonable o demasiado alto

**Método**: Cálculo teórico de cota inferior
```python
total_hours = 8627.5 horas/mes (datos reales febrero)

Cota inferior (asumiendo uso perfecto):
- Con 7x7:  ceil(8627.5 / 168) = 52 conductores
- Con 10x10: ceil(8627.5 / 180) = 48 conductores
- Con 14x14: ceil(8627.5 / 168) = 52 conductores

PERO considerando restricciones:
- Span diario ~18h → necesitas 2-3 conductores simultáneos por día
- Ciclos NxN → no todos están disponibles cada día

Cota inferior realista: ~18-22 conductores
```

**Conclusión**: Greedy con 20 conductores está CERCA del óptimo (probablemente a 0-2 conductores del mínimo)

### Experimento 2: Probar MIP con Restricciones Relajadas
**Hipótesis**: Quizás las restricciones de ciclo NxN son demasiado estrictas

**Método**: Resolver MIP con:
1. Solo restricciones diarias (14h/día, 10h descanso) → Ver cuántos conductores se necesitan
2. Agregar restricción de "al menos 7 días descanso cada 14 días" (más flexible que NxN)
3. Comparar con solución greedy estricta (NxN)

**Pregunta**: ¿Cuánto ganaríamos relajando los ciclos NxN?

### Experimento 3: Sensitivity Analysis en Parámetros
**Variables a analizar**:
- ¿Qué pasa si permitimos 15h/día en vez de 14h? → Reduce conductores?
- ¿Qué pasa si el descanso es 9h en vez de 10h? → Reduce conductores?
- ¿Qué pasa si agregamos patrón 8x8 (8 trabajo, 8 descanso)? → Más flexibilidad?

**Método**: Ejecutar greedy modificando cada parámetro y medir impacto

### Experimento 4: Benchmark de Solvers
**Objetivo**: Comparar velocidad y calidad de diferentes solvers

**Solvers a probar**:
1. Google OR-Tools CP-SAT (actual, no funciona)
2. Google OR-Tools MIP Solver (SCIP backend)
3. Gurobi MIP (requiere licencia)
4. COIN-OR CBC (gratuito, menos eficiente)
5. MiniZinc con Gecode

**Método**: Mismo modelo MIP, ejecutar en todos los solvers con límite de 10 minutos

---

## 9. IMPLEMENTACIÓN RECOMENDADA (Prioridad)

### PRIORIDAD 1: Greedy + Simulated Annealing (1-2 días de desarrollo)

**Razón**:
- Aprovecha solución greedy actual (ya funciona)
- Simulated Annealing es relativamente simple de implementar
- Alta probabilidad de mejorar 1-2 conductores
- Tiempo de ejecución aceptable (<15 min)

**Pseudocódigo**:
```python
def optimize_with_simulated_annealing(initial_solution, max_time=600):
    current = initial_solution  # 20 conductores
    best = current
    T = 100.0  # Temperatura inicial
    alpha = 0.95

    while time.elapsed() < max_time and T > 0.01:
        # Generar vecino
        neighbor = generate_neighbor(current)  # Swap, relocate, consolidate

        if not is_feasible(neighbor):
            continue

        delta_cost = cost(neighbor) - cost(current)

        # Aceptar si mejora o con probabilidad
        if delta_cost < 0 or random() < exp(-delta_cost / T):
            current = neighbor
            if cost(current) < cost(best):
                best = current
                print(f"Nueva mejor solución: {best.num_drivers} conductores")

        T *= alpha  # Enfriar

    return best
```

**Operadores de vecindad a implementar**:
1. **Swap**: Intercambiar 1 turno entre 2 conductores
2. **Relocate**: Mover 1 turno de conductor A a B
3. **Consolidate**: Tomar conductor con menos turnos, redistribuir a otros, eliminar conductor

### PRIORIDAD 2: Matheuristic con Descomposición Semanal (3-5 días de desarrollo)

**Razón**:
- Reduce el problema de 28 días a 7 días por iteración
- CP-SAT probablemente SÍ convergerá en problemas de 7 días (160-180 turnos)
- Mantiene factibilidad semana por semana

**Pseudocódigo**:
```python
def optimize_weekly_decomposition(all_shifts, year, month):
    solution = {'assignments': [], 'drivers': {}}
    available_drivers = []  # Pool de conductores creados

    # Dividir mes en semanas
    weeks = split_into_weeks(all_shifts)  # 4 semanas de 7 días

    for week_num, week_shifts in enumerate(weeks):
        print(f"Optimizando semana {week_num+1}/4...")

        # Subproblema: Asignar turnos de esta semana
        # Considerar: conductores ya existentes + posibilidad de crear nuevos
        week_solution = optimize_week_with_cpsat(
            week_shifts,
            available_drivers,
            max_new_drivers=5,
            time_limit=120  # 2 minutos por semana
        )

        # Actualizar solución global
        solution['assignments'].extend(week_solution['assignments'])

        # Agregar nuevos conductores al pool
        for driver in week_solution['new_drivers']:
            available_drivers.append(driver)
            solution['drivers'][driver['id']] = driver

    return solution
```

**Desafío técnico**: Asegurar continuidad entre semanas (día 7→8, 14→15, 21→22)
- Solución: Agregar restricciones de "linkage" que respeten descanso de 10h entre semanas

### PRIORIDAD 3: MIP con Gurobi (si está disponible) (2-3 días de desarrollo)

**Razón**:
- Si tienen licencia académica o comercial de Gurobi → probablemente mejor que CP-SAT
- Gurobi tiene heurísticas MIP muy avanzadas (RINS, Local Branching, etc.)
- Mismo modelo, solo cambiar solver

**Código (skeleton)**:
```python
import gurobipy as gp
from gurobipy import GRB

def optimize_with_gurobi(shifts, drivers, patterns):
    model = gp.Model("roster_optimization")
    model.Params.TimeLimit = 600  # 10 minutos

    # Variables
    X = {}
    for d in drivers:
        for s in shifts:
            X[d,s] = model.addVar(vtype=GRB.BINARY, name=f"x_{d}_{s}")

    Y = {}
    for d in drivers:
        for p in patterns:
            Y[d,p] = model.addVar(vtype=GRB.BINARY, name=f"y_{d}_{p}")

    Z = {}
    for d in drivers:
        Z[d] = model.addVar(vtype=GRB.BINARY, name=f"z_{d}")

    # Objetivo
    model.setObjective(
        gp.quicksum(Z[d] * 800000 for d in drivers) +
        gp.quicksum(X[d,s] * 5000 for d in drivers for s in shifts),
        GRB.MINIMIZE
    )

    # Restricciones
    # (1) Cobertura
    for s in shifts:
        model.addConstr(gp.quicksum(X[d,s] for d in drivers) == 1)

    # (2) Patrón único
    for d in drivers:
        model.addConstr(gp.quicksum(Y[d,p] for p in patterns) == 1)

    # (3) Ciclo NxN - Esta es la parte compleja
    for d in drivers:
        for p in patterns:  # Ejemplo: p = '10x10' → cycle = 10
            cycle = int(p.split('x')[0])
            for day in range(28):
                # Si driver usa patrón p, entonces...
                # (Implementar lógica de días trabajo/descanso)
                pass

    # (4) Max 14h/día
    # ...

    # Resolver
    model.optimize()

    if model.status == GRB.OPTIMAL:
        return extract_solution(model, X, Y, Z)
    else:
        return None
```

---

## 10. MÉTRICAS DE EVALUACIÓN

Para cada técnica evaluada, reportar:

### Métricas de Calidad
- **Número de conductores**: Objetivo principal (minimizar)
- **Cobertura de turnos**: % de turnos asignados (objetivo: 100%)
- **Costo total**: Salarios + bonos
- **Violaciones**: Número de restricciones violadas (debe ser 0)

### Métricas de Desempeño
- **Tiempo de cómputo**: Segundos hasta encontrar mejor solución
- **Tiempo hasta factible**: Segundos hasta primera solución válida
- **Gap de optimalidad**: Si aplicable, distancia al óptimo teórico

### Métricas de Robustez
- **Consistencia**: Ejecutar 10 veces, reportar media y desviación estándar
- **Escalabilidad**: Probar con 1 mes, 3 meses, 12 meses

---

## 11. RECURSOS Y HERRAMIENTAS

### Bibliotecas de Optimización (Python)
- **Google OR-Tools**: CP-SAT, MIP, Routing (gratuito)
- **Gurobi**: MIP comercial (licencia académica gratuita) - RECOMENDADO
- **CPLEX**: MIP comercial (IBM, licencia académica)
- **COIN-OR CBC**: MIP open-source (más lento que Gurobi)
- **PuLP**: Interfaz Python para varios solvers MIP
- **pyomo**: Framework de modelado avanzado

### Frameworks de Metaheurísticas
- **pymhlib**: Biblioteca de metaheurísticas (SA, TS, GA, etc.)
- **DEAP**: Framework de algoritmos evolutivos
- **scikit-opt**: Algoritmos de optimización (PSO, GA, SA)

### Papers Relevantes
1. **"Rostering of Personnel" (Ernst et al., 2004)**: Survey de técnicas
2. **"A Survey of Automated Timetabling" (Burke et al., 1997)**: Aplicable a turnos
3. **"Column Generation for Vehicle Routing" (Desaulniers et al., 2005)**: Técnica de Column Generation
4. **"Hybrid Metaheuristics for the Vehicle Routing Problem" (Vidal et al., 2013)**: Enfoques híbridos

---

## 12. ENTREGABLES ESPERADOS

1. **Reporte Técnico** (10-15 páginas):
   - Análisis comparativo de técnicas evaluadas
   - Resultados experimentales (tablas, gráficos)
   - Recomendación final con justificación

2. **Implementación de Mejor Técnica**:
   - Código Python documentado
   - Integración con sistema actual (reemplazo de CP-SAT)
   - Tests automatizados

3. **Documentación de Usuario**:
   - Guía de uso
   - Explicación de parámetros configurables
   - Troubleshooting

---

## 13. CRONOGRAMA SUGERIDO

| Semana | Actividad | Entregable |
|--------|-----------|------------|
| 1 | Investigación bibliográfica + diseño experimentos | Plan detallado |
| 2 | Implementación de Simulated Annealing | Prototipo funcional |
| 3 | Implementación de Matheuristic (descomp. semanal) | Prototipo funcional |
| 4 | Pruebas con datos reales + comparación con greedy | Resultados preliminares |
| 5 | Refinamiento de mejor técnica + documentación | Código final + reporte |

---

## 14. CONTACTO Y SOPORTE

Para dudas sobre:
- **Datos de entrada**: Revisar archivo Excel template en `/Users/alfil/Library/CloudStorage/GoogleDrive.../Template TURNOS Hualpén...`
- **Código actual**: Ver `roster_optimizer_with_regimes.py` (greedy funcional)
- **Restricciones laborales**: Art. 38 Código del Trabajo de Chile (Faena Minera)

---

## 15. DATOS DE PRUEBA

Usar **Febrero 2025** como mes de referencia:
- 664 turnos
- 8,627.5 horas totales
- 28 días
- Span diario: 17-19 horas
- Solución greedy baseline: **20 conductores con patrón 10x10**

**Objetivo del Research**: Encontrar técnica que consistentemente produzca soluciones de **18-19 conductores** (o demostrar que 20 es óptimo).

---

*Documento generado para equipo de Research - Optimización de Turnos Faena Minera*
*Fecha: 2025-10-14*
*Versión: 1.0*
