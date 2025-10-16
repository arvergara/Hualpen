Resumen de Restricciones del Modelo de Optimización

1. COBERTURA DE SERVICIOS

Restricción: Cada turno de cada servicio debe ser cubierto por exactamente
un conductor.

# Para cada día, servicio y turno, exactamente 1 conductor asignado

sum(x[day, service, shift, driver] for driver in drivers) == 1

2. NO SIMULTANEIDAD

Restricción: Un conductor no puede estar en dos lugares al mismo tiempo.

# Para cada horario específico, el conductor puede estar en máximo 1

servicio
sum(x[day, service, shift, driver] for service in services_at_time) <= 1

3. JORNADA MÁXIMA DE 12 HORAS

Restricción: La jornada continua no puede exceder 12 horas desde el inicio
del primer turno hasta el fin del último.

Lógica de cálculo:

- Recolecta todos los turnos del día actual y turnos tempranos del día
  siguiente (antes del mediodía)
- Para cada par de turnos, calcula el span total:
  - earliest_start = hora de inicio más temprana
  - latest_end = hora de fin más tardía
  - span = latest_end - earliest_start
- Si span > 12 horas, los turnos no pueden ser asignados al mismo conductor
- Ejemplo: T3 (21:00-00:00) + T1 siguiente (06:00-09:00) = 12h span ✅

4. MÁXIMO 44 HORAS SEMANALES

Restricción: Un conductor no puede trabajar más de 44 horas por semana.

# Para cada semana y conductor

sum(horas_trabajadas_en_semana) <= 44

5. MÁXIMO 180 HORAS MENSUALES

Restricción: Un conductor no puede trabajar más de 180 horas al mes.

# Para cada conductor en todo el mes

sum(todas_las_horas_del_mes) <= 180

6. DESCANSO PROPORCIONAL

Restricción: 2 horas de descanso por cada 5 horas de conducción continua.

Lógica de cálculo:

- Entre turnos (mismo día o días consecutivos):
  - descanso_requerido = (horas_conducidas \* 2) / 5
  - gap = hora_inicio_turno2 - hora_fin_turno1
- Si gap < descanso_requerido, no pueden hacer ambos turnos
- Ejemplo: Después de 3h de conducción → necesita 1.2h de descanso

7. MÁXIMO 6 DÍAS CONSECUTIVOS

Restricción: Un conductor no puede trabajar más de 6 días seguidos.

Lógica de cálculo:

- Para cada ventana de 7 días consecutivos:
  - Cuenta los días trabajados (día con al menos un turno)
  - sum(días_trabajados_en_ventana) <= 6

8. MÍNIMO 2 DOMINGOS LIBRES AL MES

Restricción: Un conductor debe tener al menos 2 domingos libres en el mes.

Lógica de cálculo:

- Identifica todos los domingos del mes
- Para cada conductor, cuenta domingos trabajados
- domingos_trabajados <= total_domingos - 2
- Ejemplo: En febrero con 4 domingos → máximo 2 trabajados

9. MÁXIMO 5 HORAS CONTINUAS DE CONDUCCIÓN

Advertencia: Se genera una alerta si un turno individual excede 5 horas.
if shift['duration_hours'] > 5:
print("⚠ ADVERTENCIA: Turno excede 5 horas continuas")

Función Objetivo

Minimizar: Número de conductores utilizados y balancear la carga

# Penaliza más a conductores part-time (son más caros por hora)

objective = sum(driver_used \* peso)

# peso = 1000 para full-time, 1500 para part-time

Diagnóstico de Infactibilidad

Cuando no encuentra solución, el sistema analiza qué restricciones están
causando el problema:

1. HORAS INSUFICIENTES: Capacidad total < Horas necesarias
2. 44H SEMANALES: No hay suficientes conductores para cumplir límite semanal
3. DOMINGOS LIBRES: No hay suficientes conductores para dar 2 domingos
   libres
4. JORNADA 12H: Hay combinaciones de turnos que exceden 12h
5. COBERTURA SIMULTÁNEA: No hay suficientes conductores para turnos
   simultáneos

El optimizador agrega conductores iterativamente hasta encontrar una
solución factible que cumpla todas las restricciones.

Las filas ocultas son combinaciones validas o se pueden eliminar?

Se pueden eliminar, ya que son información referencial nuestra, pero lo que verdaderamente genera valor es lo visible.

Lo enviado son todas las mallas validas o podrían haber otras?. En caso que la respuesta sea que si hay otras mallas validas: ¿cual es el criterio para crear nuevas mallas?

Las mallas enviadas son todas las mallas validas que hemos creado hasta el momento según las restricciones de cada jornada.

Si se pueden crear nuevas mallas y el criterio será siempre las restricciones de cada articulo y que logren seguir un patrón para la gestión operacional y relación contractual con el trabajador.

Respecto de los artículos de cada malla, ¿debemos entender que cada persona solo puede estar en uno de estos?: Art25, Art 38 n°2 , Bisemanal, Jornada Excepcional.

Si, solo puede estar en un único artículo. La personas si puede ser cambiada de articulo y rotativa distinta, pero deberá ser acordado por ambas partes mediante un anexo de cambio de jornada y con una anticipación de 30 días antes de que el cambio se efectué.

Art.25 = Interubano

Art.38 N°2 = Urbano / Industrial

Bisemanal / Jornada Excepcional = Fuera del radio Urbano, generalmente en faena.

¿Es posible combinar todas las mallas de un mismo articulo?, por ejemplo: ¿podemos hacer que un conductor sea Art 38 n°2 y una semana tenga la malla 2x2 y luego tenga 5X2 - 6X1 ROTATIVO 9, y luego vuelva 2x2?. Estoy exagerando pero quiero entender cuales son los criterios para combinar mallas. Es importante notar que es poco realista contratar gente con combinaciones asi de locas, por tanto va a ser necesario que una alternativa del sistema sea forzar (o no) a usar solo una malla por persona.

Si, es posible siempre y cuando, la persona no cambie de articulo, la malla respete los criterios de dicho articulo y exista una rotativa de malla en un ciclo periódico que cumpla un patrón especifico

Ejemplo:

Semana 1: 2x2

Semana 2: 5x2

Semana 3: 4x3

Semana 4: 6x1

--Se reinicia el patrón—

Semana 5: 2x2

Semana 6: 5x2

Semana 7: 4x3

Semana 8: 6x1

….
Veamos mas en detalle:

ORDENAMIENTO
Jornadas Ordinarias de Trabajo Distribución de Jornada Necesita Resolución Observacion
Art.22 inciso 1 TURNO 5X2 No 44 Hrs Semanales
TURNO 6X1
TURNO 5X2 - 6X1
TURNO 4X3 40 hrs Semanales
Art.22 Inciso 2 no tiene jornada No "Solo Gerentes
No registran Marcaciones"
Art.25 TURNO 5X2 No 180 Horas Mensuales
TURNO 6X1 No
2X2 No
6X6 No
4X3 No
TURNO 9X3 / RE 1440 Si
TURNO 10X4 / RE 1440 Si
TURNO 10X5 / RE 1440 Si
TURNO 8X4/ RE 1440 Si
TURNO 6x3 / RE 1440 Si
TURNO 4x2 / RE 1440 Si
Art 39 TURNO 10X5 No "Jornada Bisemanal
88 horas del ciclo"
TURNO 8X6
TURNO 9X5
TURNO 11x4
TURNO 12x3
TURNO 7x2
Art. 38 N°2 TURNO 5X2 No 44 Hrs Semanales
TURNO 6X1
TURNO 5X2 - 6X1
TURNO 4X3 40 hrs Semanales
Art 38 Excepcional TURNO 4X3 Si 45 Hrs Semanales
TURNO 4X4 Si
TURNO 6X3 Si
TURNO 7X7 Si
"TURNO 20x20
TURNO 10X10" Si
TURNO 14X14 Si
"Art 40 bis
Jornada Parcial" "1x6
2x5
3x4
4x3" No "30 Hrs Semanales (respeta los dos domingos al mes y 7mo dia)
20 Hrs Fin de Semana
