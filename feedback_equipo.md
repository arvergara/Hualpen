0) Hallazgo crítico: incoherencia en las “horas por mes vs. conductores”

Con los datos que reportas para febrero 2025 (8.627,5 h totales), la cota inferior por capacidad depende de cuántas horas puede aportar un conductor/mes bajo el régimen 10×10:

Si asumes 10×10 con 12 h por día trabajado y trabajo el 50% de los días de un mes de 28 días (esperado en promedio por la estructura 10 on / 10 off), un conductor aporta ≈ 14 días × 12 h = 168 h/mes.
→ LB ≈ ceil(8.627,5 / 168) = 52 conductores.

Si fuerzas 180 h/mes por conductor (tu tabla), la cota es ceil(8.627,5 / 180) = 48.

Cualquiera de estas cotas contradice la solución greedy “20 conductores” (que sólo aportarían 3.600 h/mes si cada uno produce ~180 h). En consecuencia, o bien:

“Conductor” no equivale a “persona con 12 h/día” en tu métrica; o

Las 8.627,5 h suman conceptos que no requieren conductor exclusivo (p.ej., horas ociosas o de espera); o

Las horas por conductor/mes que usas (180/168) no aplican al régimen real aprobado para la faena; o

El greedy está contando mal (p. ej., cuenta vehículos o “cobertura de span” y no horas efectivas).

Antes de optimizar, te sugiero una auditoría de consistencia:

(A) Recalcular total_hours a partir de tus turnos (sólo duración efectiva conducida).

(B) Fijar horas mensuales por conductor y por patrón a partir del régimen excepcional aprobado por DT para esa faena (no la regla general). En Chile, la jornada ordinaria es ≤44 h/semana desde 26‑abr‑2024 y baja gradualmente hasta 40 h el 26‑abr‑2028, pero faenas con “sistema excepcional” (art. 38) requieren autorización DT con reglas propias por ciclo; hay que ceñirse a esa resolución, no a genéricos de internet. 
Ministerio del Trabajo
+1

Nota legal operativa (no asesoría legal): La regla general chilena limita la jornada diaria y el “span” del día; en excepcionales se permiten otras distribuciones siempre autorizadas por DT. Tu uso de 14 h/día y 10 h de descanso debe provenir de esa autorización/reglamento interno; en fuentes generales aparecen topes distintos (10–12 h/día) para jornadas ordinarias, no extrapolables sin la resolución excepcional. Verifica con RR. HH./legal. 
Gobierno de Chile
+1

Mientras cerramos esa brecha, abajo te doy un plan técnico que no depende de cuál sea exactamente la hora/mes por conductor: funciona con tus máscaras de disponibilidad NxN y tus reglas (14 h / 10 h).

1) Por qué CP‑SAT se cuelga y cómo destrabarlo

Causas probables

Modelo “denso” de x[d,s] para todos los (conductor, turno), con muchas asignaciones imposibles que el solver debe podar.

Restricciones de ciclo NxN modeladas a nivel de binarios (no como “disponibilidad”), causando simetrías.

Sin solution hint ni decision strategies sobre las variables de presencia; presolve intenta linealizar todo y se queda sin progreso.

Usar CP‑SAT como MIP binario puro en vez de explotar interval variables + no‑overlap (lo que CP‑SAT hace mejor). 
Google for Developers
+1

Correcciones de modelado (mínimo viable):

Filtra variables: crea x[d,s] solo si el día de s cae en día de trabajo del patrón + offset del conductor. (Esto te elimina ~50% de variables en 10×10).

Cambia el clúster de restricciones “no solape + 10 h descanso + ≤14 h/día” a intervalos opcionales y NoOverlap por conductor. Cada turno s se modela como interval_s opcional con presencia x[d,s]. Esto reduce simetrías y guía mejor la búsqueda. (OR‑Tools CP‑SAT es muy fuerte en scheduling de intervalos). 
Google for Developers

Fija el offset del patrón del conductor antes de resolver (o con un pequeño conjunto de offsets candidatos), convirtiendo NxN en máscaras de disponibilidad.

Hint inicial con tu solución greedy y branching primero en presencias x[d,s] (estrategia sobre literales), y luego en tiempos. Ajusta max_time_in_seconds, usa workers >1, y considera guías de parámetros (cpsat‑primer). 
D Krupke

2) Estrategia práctica en 15 minutos: Greedy + LNS (Large Neighborhood Search)

Esto capitaliza tu greedy (10 s) y lo refina con barridos de destrucción‑reparación orientados a eliminar conductores. Es un patrón estándar en rostering moderno (LNS/ALNS). 
DIVA Portal
+2
arXiv
+2

2.1 Flujo propuesto (end‑to‑end)

Fase A — Seeds (≤ 1 min)

Multi‑start greedy con 8–16 semillas (ordena turnos por: fecha, duración, “holgura de reasignación”, servicio).

Para cada seed, aplica offsets de patrón diferentes (rotaciones 0..19 para 10×10) para diversificar disponibilidad.

Fase B — LNS (≤ 10–12 min)

Ejecuta iteraciones con estas operaciones de destrucción (elige aleatoria/ruleta):

Consolidate/Drop‑Driver: elimina un conductor de baja carga y repara insertando sus turnos en otros.

Destroy ventana (3–4 días contiguos): saca todas las asignaciones en esa ventana y reoptimiza localmente.

Destroy por servicio/vehículo: retira todas las asignaciones de un servicio y repara.

Reparación: heurística “first‑fit‑best‑fit” sobre conductores existentes (prioriza coincidencia de patrón y offset, slack de horas diarias, último fin+10 h), creando nuevo conductor solo si no hay cabida.

Aceptación: Simulated annealing (T₀≈100, α≈0,95) o ALNS con pesos adaptativos por operador, para escapar de óptimos locales. 
arXiv

Criterio de parada: tiempo total 15 min o K iteraciones sin mejora.

Fase C — Limpieza final (≤ 1–2 min)

Shaking suave: intenta intercambios 1‑1 (swap) y relocates guiados por un scoring de “impacto en horas diarias / descanso”.

Eliminación glotona: intenta borrar conductores residuales y reinsertar.

Con buenos operadores, LNS/ALNS en rostering logra cerrar 1–3 “recursos” respecto a la semilla en tiempos cortos. La literatura lo respalda en rerostering y nurse rostering. 
DIVA Portal
+1

2.2 Detalles que marcan diferencia

Listas de conflicto precomputadas: para cada turno, mantener la lista de turnos que no pueden coexistir en el mismo conductor (solape temporal o descanso <10 h o romper 14 h/día). Esto hace que “reparar” sea O(#candidatos) con cheques O(1).

Bitsets por día: representa ocupación horaria del conductor en cada día (minutos/slots de 5–15 min). Chequeo ultrarrápido de solapes y 14 h/día.

Orden de inserción: primero turnos “duros” (cercanos al límite diario, terminan tarde y empiezan temprano al día siguiente), luego los fáciles.

Penalizaciones suaves: si una asignación dejaría a un conductor en “borde de 14 h” o “borde de 10 h descanso”, penaliza su score para evitar bloqueos a futuro.

3) Alternativa “matheurística” fix‑and‑optimize por ventanas (CP‑SAT local)

En vez de resolver el mes completo, resuelve ventanas de 2–4 días con CP‑SAT, fijando todo lo demás.
Ciclo: (Greedy) → (Fix 26 días, Optimiza 2) → sliding window.

Con intervals + NoOverlap y disponibilidad NxN ya filtrada, CP‑SAT sí converge en ventanas chicas.

Usa solution hint inicial de la asignación actual y max_time_in_seconds (30–60 s por ventana). 
Google for Developers
+1

4) Si quieres un exacto más potente: Set‑partitioning + Column Generation (a medio plazo)

Modela cada “columna” como una ruta factible de turnos para un conductor en el mes (o en una semana), cumpliendo NxN, 10 h descanso y 14 h/día.

Master: set‑partitioning que cubre cada turno exactamente una vez, minimiza salarios+bonos.

Pricing: RCSP que genera nuevas rutas de costo reducido.

Escala mucho mejor en problemas grandes; es el estándar en crew scheduling (transporte) y rostering. Requiere 1–2 semanas de dev si no tienes infraestructura. 
SpringerLink
+2
IDEAS/RePEc
+2

5) Parámetros y configuración recomendados

Para LNS/ALNS

Iteraciones: 5.000–15.000 (o 10–12 min).

Tamaño destrucción: 10–25% de las asignaciones de la vecindad elegida.

“Consolidate” cada X=50 iteraciones (si no mejora, baja X).

Semillas: 8–16 seeds con offsets 10×10 uniformemente espaciados.

Para CP‑SAT local (ventanas)

max_time_in_seconds = 30–60 por ventana; num_search_workers = #cores.

Decisión: branch primero en presencias de intervalos (máscarás NxN ya aplicadas).

Pasar solution hint desde LNS. Guía y estabilidad de parámetros: ver “cpsat‑primer”. 
D Krupke

6) Métricas y “guardrails” (para tu benchmark automático)

Primaria: drivers_used.

Secundarias: cobertura = 100%, costo total, violaciones = 0.

Desempeño: tiempo hasta 1ª solución factible, mejor valor vs. tiempo (trace).

Robustez: 10 corridas con distinta semilla → media y desviación.

Explainability: top‑5 cuellos de botella (días / servicios con mayor congestión).

Stop: 15 min muro.

7) Acciones concretas en tu repo (cambios mínimos y rápidos)

Pre‑proceso

Genera máscaras de disponibilidad por (patrón, offset, día) y filtra variables.

Construye conflict sets por turno.

Nueva capa LNS (módulo adicional)

Implementa operadores: swap, relocate, drop_driver, destroy_window, destroy_service.

Reparador con cheques O(1) usando bitsets y conflict sets.

Aceptación SA o ALNS (pesos adaptativos por operador).

CP‑SAT local opcional

Modelo por ventana de 2–4 días solo con los intervalos dentro de la ventana.

NoOverlap por conductor, AddCumulative no es necesario.

Hints desde el estado actual.

Hint y estrategia para tu CP‑SAT global (si insistes en global)

Reescribe a intervalos opcionales + máscaras de disponibilidad.

Elimina binarios imposibles; aplica AddDecisionStrategy (presencias primero).

Pasa la solución greedy como solution hint. 
Google for Developers
+1

8) Replicación anual (tu “módulo”)

Tu lógica modular por ciclo 20 días (10×10) es correcta conceptualmente. Asegura que:

El offset de cada conductor se fija en una fecha ancla por persona (p. ej., fecha de ingreso).

Para meses 28/30/31, el día‑en‑ciclo se calcula desde el ancla, no desde el 1 de cada mes, para respetar descansos reales.

Si combinas patrones (7×7, 10×10, 14×14), usa LCM de ciclos sólo para análisis; en práctica, calcula por patrón/offset por separado.
(Sin cita: es construcción algorítmica interna.)

9) Plan de validación — “quick wins” en 48 h

Auditoría de consistencia (2–3 h):

Recalcula horas y confirma el significado de “conductor” en tu greedy.

Congruencia: Σ horas asignadas = Σ horas de turnos cubiertos.

Multi‑start greedy + drop‑driver (0,5 día):

Implementa drop_driver() y repair() robustos. Mide si bajas de 20 a 19 en ≤15 min.

Ventanas CP‑SAT (0,5–1 día):

Con intervalos opcionales y máscaras. Optimiza una ventana difícil (días con mayor span).

Integra al lazo LNS como “operador de intensificación”.

Reporte y trazas (2–3 h):

Curvas “mejor costo vs. tiempo”, drivers vs. tiempo, %cobertura (debe quedar en 100%).

Lista de días/servicios cuello de botella.

10) Referencias clave (para rigor y evitar alucinaciones)

CP‑SAT y parámetros / scheduling con intervalos (documentación oficial y guía de parámetros). 
Google for Developers
+2
Google for Developers
+2

LNS/ALNS en staff (re)rostering (estado del arte reciente). 
DIVA Portal
+1

Revisiones clásicas de rostering (Ernst et al., 2004). 
ScienceDirect
+1

Column Generation / Set‑partitioning para crew scheduling (Desaulniers/Desrosiers/Solomon; “A Primer”). 
SpringerLink
+1

Marco laboral chileno (alto nivel):

Ley 21.561 “40 horas” y su gradualidad. 
Ministerio del Trabajo
+1

Autorización DT para sistemas excepcionales (art. 38), base para 7×7, 10×10, 14×14. 
Gobierno de Chile

11) Riesgos y mitigaciones

Si la auditoría confirma que 20 conductores no alcanzan la cota por horas, el objetivo de 18–19 es inviable; ajusta metas o redefine “conductor”/“turno” (p. ej., si un driver puede cubrir múltiples “subturnos” en un mismo bloque).

Datos con micro‑turnos: agrega una fase de agregación (consolidar subturnos contiguos por servicio y conductor candidato) para evitar explosión combinatoria.

Legal: valida que tus topes 14 h/10 h provengan de la resolución DT vigente para esa faena; si no, ajusta máscaras y límites.

12) Qué te entregaría (rápido)

Módulo LNS/ALNS plug‑and‑play encima de tu greedy, con operadores drop_driver / window / service y reparador O(1) vía bitsets.

Ventana CP‑SAT con intervalos opcionales y NoOverlap por conductor (para intensificación local).

Harness de benchmark con trazas y métricas (#drivers, %cobertura, costo, tiempo).

Si te parece, puedo integrarlo directo sobre roster_optimizer_with_regimes.py preparando hooks a tus estructuras (máscaras NxN, cheques 14 h/10 h, costos) y dejarte corridas reproducibles (8–12 seeds) bajo un muro de 15 minutos.

Resumen ejecutivo

Tu CP‑SAT no escala por modelado “denso” y simetrías; pásate a intervalos opcionales + máscaras NxN + hint, o usa ventanas.

Para impacto inmediato, usa Greedy + LNS/ALNS con operadores de eliminación de conductores; es lo más costo/beneficio en ≤15 min. 
DIVA Portal
+1

Audita ya la coherencia horas totales vs. horas por conductor/mes; hoy la cota por capacidad no cuadra con “20 conductores”.

Si necesitas exactitud y escalabilidad a gran escala, prepara Column Generation (siguiente fase). 
SpringerLink