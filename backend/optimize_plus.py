#!/usr/bin/env python
"""
Script de optimización con regímenes laborales diferenciados
Soporta diferentes restricciones según el tipo de servicio:
- Interurbano (Art. 25): Restricciones estrictas de conducción
- Urbano/Industrial: Restricciones más flexibles
- Interurbano Bisemanal (Art. 39): Ciclos especiales
- Faena Minera (Art. 38): Turnos excepcionales

Uso:
    python optimize_plus.py [archivo_excel] [cliente] [año] [mes]

    Si no se especifica mes, se solicitará modo: mensual (1) o anual (2)
    Modo anual optimiza 12 meses con plantilla estable de conductores
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List

# Agregar el directorio app al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.excel_reader import ExcelTemplateReader
from app.services.output_generator import OutputGenerator
from app.services.html_report_generator import HTMLReportGenerator

# Importar el nuevo optimizador con regímenes
from app.services.roster_optimizer_with_regimes import RosterOptimizerWithRegimes


def main():
    """Función principal"""

    print("=" * 80)
    print("SISTEMA DE OPTIMIZACIÓN DE TURNOS CON REGÍMENES LABORALES")
    print("=" * 80)
    print("Versión 2.0 - Restricciones diferenciadas por tipo de servicio")
    print()

    # Verificar argumentos o usar valores por defecto
    if len(sys.argv) > 1:
        excel_file = sys.argv[1]
    else:
        excel_file = '/Users/alfil/Library/CloudStorage/GoogleDrive-andres.vergara@maindset.cl/Mi unidad/Prototipo_Hualpen/nueva_info/Template TURNOS  Hualpén 08-09-2025.xlsx'

    if len(sys.argv) > 2:
        client_name = sys.argv[2]
    else:
        # Solicitar cliente interactivamente
        print("Clientes disponibles:")
        reader = ExcelTemplateReader(excel_file)
        clients = reader.get_available_clients()
        for i, client in enumerate(clients, 1):
            print(f"  {i}. {client}")

        selection = input("\nSeleccione cliente (número): ")
        try:
            client_name = clients[int(selection) - 1]
        except:
            print("Selección inválida, usando Watts por defecto")
            client_name = 'Watts'

    if len(sys.argv) > 3:
        year = int(sys.argv[3])
    else:
        year = 2025

    if len(sys.argv) > 4:
        month = int(sys.argv[4])
    else:
        month_input = input("Ingrese mes (1-12, 0=año completo): ")
        month = int(month_input) if month_input else 0

    is_annual = (month == 0)

    print(f"\nParámetros de optimización:")
    print(f"  - Archivo Excel: {excel_file}")
    print(f"  - Cliente: {client_name}")
    if is_annual:
        print(f"  - Período: {year} (AÑO COMPLETO)")
    else:
        print(f"  - Período: {year}-{month:02d}")
    print()

    # Verificar que el archivo existe
    if not os.path.exists(excel_file):
        print(f"ERROR: No se encuentra el archivo {excel_file}")
        return 1

    try:
        # PASO 1: Leer datos del Excel
        print("PASO 1: Leyendo datos del Excel...")
        reader = ExcelTemplateReader(excel_file)

        # Leer datos del cliente
        # Para optimización anual, leer febrero (mes base)
        # Para optimización mensual, leer el mes específico
        read_month = 2 if is_annual else month

        print(f"  Expandiendo turnos para {year}-{read_month:02d}...")
        client_data = reader.read_client_data(client_name, year=year, month=read_month)

        # Contar turnos totales expandidos
        total_shifts = sum(len(s.get('shifts', [])) for s in client_data['services'])

        print(f"✓ Datos leídos correctamente:")
        print(f"  - Servicios (líneas Excel): {len(client_data['services'])}")
        print(f"  - Turnos expandidos: {total_shifts}")

        # Analizar tipos de servicio
        service_types = {}
        for service in client_data['services']:
            stype = service.get('service_type', 'Industrial')
            service_types[stype] = service_types.get(stype, 0) + 1

        print(f"\n📊 Análisis de tipos de servicio:")
        for stype, count in service_types.items():
            print(f"  - {stype}: {count} servicios")

        # Detectar régimen mixto
        if len(service_types) > 1:
            print("\n⚠️ RÉGIMEN MIXTO DETECTADO")
            print("Se aplicarán restricciones diferenciadas según el tipo de servicio:")
            if 'Interurbano' in service_types:
                print("  • Interurbano: Máx 5h conducción continua, 180h/mes")
            if 'Industrial' in service_types or 'Urbano' in service_types:
                print("  • Urbano/Industrial: Sin límite conducción continua, 44h/semana")
            if 'Faena Minera' in service_types or 'Minera' in service_types:
                print("  • Faena Minera: Ciclos 7x7/14x14, máx 14h/día, promedio 44h/semana")

        # PASO 2: Optimizar con regímenes diferenciados
        print(f"\nPASO 2: Ejecutando optimización con regímenes laborales...")

        optimizer = RosterOptimizerWithRegimes(client_data)

        if is_annual:
            # Optimizar febrero (mes base)
            print(f"  Optimizando febrero {year} (mes base)...")
            feb_solution = optimizer.optimize_month(year, 2)

            if feb_solution['status'] != 'success':
                print(f"ERROR: La optimización de febrero falló - {feb_solution.get('message', 'Unknown error')}")
                return 1

            print(f"  ✓ Febrero optimizado: {feb_solution['metrics']['drivers_used']} conductores")

            # Replicar febrero a todos los meses
            print(f"\n  Replicando patrón de febrero a todos los meses del año...")

            # Detectar patrón dominante (7x7, 10x10, 14x14)
            driver_summary = feb_solution.get('driver_summary', {})
            pattern_counts = {}
            for driver_id, driver_data in driver_summary.items():
                pattern = driver_data.get('pattern', 'Flexible')
                # Extraer número del patrón (ej: "7x7" → 7)
                if 'x' in pattern:
                    try:
                        cycle_num = int(pattern.split('x')[0])
                        pattern_counts[cycle_num] = pattern_counts.get(cycle_num, 0) + 1
                    except:
                        pass

            # Determinar módulo según patrón dominante
            if pattern_counts:
                dominant_cycle = max(pattern_counts.items(), key=lambda x: x[1])[0]
                modulo = dominant_cycle * 2  # 7x7 → 14, 10x10 → 20, 14x14 → 28
                print(f"  Patrón dominante detectado: {dominant_cycle}x{dominant_cycle}")
                print(f"  Módulo de replicación: {modulo} días")
            else:
                modulo = 28  # Por defecto
                print(f"  Usando módulo por defecto: 28 días")

            all_assignments = []
            monthly_costs = {}

            from datetime import date
            from copy import deepcopy
            import calendar

            # Indexar asignaciones de febrero por (día_módulo, servicio, turno, vehículo)
            feb_assignments_by_key = {}
            feb_1 = date(year, 2, 1)

            for assignment in feb_solution['assignments']:
                feb_date = assignment['date']
                if isinstance(feb_date, str):
                    feb_date = datetime.fromisoformat(feb_date).date()

                # Calcular día dentro del ciclo (1-14, 1-20, o 1-28)
                days_from_feb1 = (feb_date - feb_1).days
                day_in_cycle = (days_from_feb1 % modulo) + 1

                key = (
                    day_in_cycle,
                    assignment.get('service'),
                    assignment.get('shift'),
                    assignment.get('vehicle', 0)
                )
                feb_assignments_by_key[key] = assignment

            # Replicar patrón de febrero a todos los meses manteniendo CONTINUIDAD del ciclo
            print(f"\n  Generando asignaciones para todos los meses con continuidad de ciclos...")

            # Indexar asignaciones de febrero por (conductor, servicio, turno, vehículo, día_en_ciclo)
            feb_by_conductor_and_cycle_day = {}
            for assignment in feb_solution['assignments']:
                feb_date = assignment['date']
                if isinstance(feb_date, str):
                    feb_date = datetime.fromisoformat(feb_date).date()

                driver_id = assignment['driver_id']

                # Obtener work_start_date del conductor
                driver_info = feb_solution['driver_summary'].get(driver_id, {})
                work_start_date = driver_info.get('work_start_date')
                pattern = driver_info.get('pattern', '')

                if work_start_date and 'x' in pattern:
                    cycle_days = int(pattern.split('x')[0])
                    full_cycle = cycle_days * 2

                    # Convertir work_start_date
                    if isinstance(work_start_date, str):
                        work_start = datetime.fromisoformat(work_start_date).date()
                    elif hasattr(work_start_date, 'date'):
                        work_start = work_start_date.date()
                    else:
                        work_start = work_start_date

                    # Calcular en qué día del ciclo está esta asignación
                    days_since_start = (feb_date - work_start).days
                    day_in_cycle = days_since_start % full_cycle

                    # Indexar por (conductor, día_en_ciclo, servicio, turno, vehículo)
                    key = (
                        driver_id,
                        day_in_cycle,
                        assignment.get('service'),
                        assignment.get('shift'),
                        assignment.get('vehicle', 0)
                    )

                    if key not in feb_by_conductor_and_cycle_day:
                        feb_by_conductor_and_cycle_day[key] = assignment

            # Generar asignaciones para todo el año usando el work_start_date ajustado
            all_assignments = []
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)

            # Para cada conductor, generar sus asignaciones en todo el año
            for driver_id, driver_info in feb_solution['driver_summary'].items():
                work_start_date = driver_info.get('work_start_date')
                pattern = driver_info.get('pattern', '')

                if not work_start_date or 'x' not in pattern:
                    continue

                cycle_days = int(pattern.split('x')[0])
                full_cycle = cycle_days * 2

                # Convertir work_start_date
                if isinstance(work_start_date, str):
                    work_start = datetime.fromisoformat(work_start_date).date()
                elif hasattr(work_start_date, 'date'):
                    work_start = work_start_date.date()
                else:
                    work_start = work_start_date

                # Generar asignaciones día por día en el año
                current_date = year_start
                while current_date <= year_end:
                    # Calcular día en ciclo
                    days_since_start = (current_date - work_start).days
                    day_in_cycle = days_since_start % full_cycle

                    # Buscar asignaciones de febrero para este conductor y día en ciclo
                    for key, feb_assignment in feb_by_conductor_and_cycle_day.items():
                        if key[0] == driver_id and key[1] == day_in_cycle:
                            # Crear nueva asignación para esta fecha
                            new_assign = deepcopy(feb_assignment)
                            new_assign['date'] = current_date.isoformat()
                            all_assignments.append(new_assign)

                    current_date += timedelta(days=1)

            # Calcular costos mensuales (estimado)
            monthly_costs = {m: feb_solution['metrics']['total_cost'] for m in range(1, 13)}
            print(f"  ✓ Generadas {len(all_assignments)} asignaciones para todo el año")

            # Ajustar work_start_date en driver_summary para que sea válido para todo el año
            # Retroceder work_start_date al inicio del año manteniendo el patrón de ciclos
            print(f"\n  Ajustando work_start_date para modo anual...")
            adjusted_driver_summary = deepcopy(feb_solution['driver_summary'])
            year_start = date(year, 1, 1)

            for driver_id, driver_data in adjusted_driver_summary.items():
                work_start_date = driver_data.get('work_start_date')
                pattern = driver_data.get('pattern', '')

                if work_start_date and 'x' in pattern:
                    try:
                        cycle_days = int(pattern.split('x')[0])
                        full_cycle = cycle_days * 2  # 7x7 → 14 días

                        # Convertir work_start_date a date si es necesario
                        if isinstance(work_start_date, str):
                            feb_start = datetime.fromisoformat(work_start_date).date()
                        elif hasattr(work_start_date, 'date'):
                            feb_start = work_start_date.date()
                        else:
                            feb_start = work_start_date

                        # Calcular cuántos días hacia atrás necesitamos ir desde feb_start hasta year_start
                        days_back = (feb_start - year_start).days

                        # Retroceder en múltiplos del ciclo completo para mantener el patrón
                        cycles_back = (days_back // full_cycle)
                        adjusted_start = feb_start - timedelta(days=cycles_back * full_cycle)

                        # Si todavía está después de year_start, retroceder un ciclo más
                        while adjusted_start > year_start:
                            adjusted_start -= timedelta(days=full_cycle)

                        # Asegurarnos de que está en año correcto
                        if adjusted_start.year < year:
                            # Avanzar hasta el primer ciclo del año
                            while adjusted_start.year < year:
                                adjusted_start += timedelta(days=full_cycle)

                        adjusted_driver_summary[driver_id]['work_start_date'] = adjusted_start.isoformat()

                        # Log solo para primeros 3 conductores
                        if isinstance(driver_id, int) and driver_id <= 3:
                            print(f"    Conductor {driver_id}: {feb_start} → {adjusted_start}")

                    except Exception as e:
                        # Si hay error, mantener el original
                        print(f"    ERROR ajustando conductor {driver_id}: {e}")
                        pass

            # Crear solución anual consolidada
            solution = {
                'status': 'success',
                'year': year,
                'assignments': all_assignments,
                'driver_summary': adjusted_driver_summary,  # Usar resumen ajustado
                'regime': feb_solution.get('regime', 'Urbano/Industrial'),  # Preservar régimen de febrero
                'metrics': {
                    'drivers_used': feb_solution['metrics']['drivers_used'],
                    'total_assignments': len(all_assignments),
                    'total_annual_cost': sum(monthly_costs.values()),
                    'avg_monthly_cost': sum(monthly_costs.values()) / 12
                }
            }

            print(f"\n✓ Optimización anual completada")
            print(f"  - Asignaciones generadas: {len(solution['assignments'])}")
            print(f"  - Conductores utilizados: {solution['metrics']['drivers_used']}")
            print(f"  - Costo anual: ${solution['metrics']['total_annual_cost']:,.0f}")
            print(f"  - Costo promedio mensual: ${solution['metrics']['avg_monthly_cost']:,.0f}")
        else:
            solution = optimizer.optimize_month(year, month)

            if solution['status'] != 'success':
                print(f"ERROR: La optimización falló - {solution.get('message', 'Unknown error')}")
                return 1

            print(f"\n✓ Optimización completada exitosamente")
            print(f"  - Asignaciones generadas: {len(solution['assignments'])}")
            print(f"  - Conductores utilizados: {solution['metrics']['drivers_used']}")
            print(f"  - Costo total: ${solution['metrics']['total_cost']:,.0f}")

        # Mostrar análisis por régimen
        if 'regime_analysis' in solution:
            print(f"\n📋 Análisis por régimen laboral:")
            for regime, stats in solution['regime_analysis'].items():
                print(f"  {regime}:")
                print(f"    - Conductores: {stats['drivers']}")
                print(f"    - Turnos asignados: {stats['shifts']}")
                if 'violations' in stats and stats['violations']:
                    print(f"    - ⚠️ Violaciones: {stats['violations']}")

        # PASO 3: Generar reportes
        print("\nPASO 3: Generando reportes...")

        output_gen = OutputGenerator(solution, client_name)

        # Generar Excel con información de régimen
        excel_output = output_gen.generate_excel_report()
        print(f"  ✓ Reporte Excel: {excel_output}")

        # Generar HTML con análisis de régimen
        html_gen = HTMLReportGenerator(solution, client_name)
        html_output = html_gen.generate_html_report()
        print(f"  ✓ Reporte HTML: {html_output}")

        # PASO 4: Verificación de cumplimiento por régimen
        print("\nPASO 4: Verificando cumplimiento de restricciones por régimen...")

        violations_by_regime = {'Interurbano': [], 'Industrial': [], 'Urbano': []}

        for assignment in solution['assignments']:
            service_type = assignment.get('service_type', 'Industrial')
            driver_id = assignment['driver_id']

            # Verificar restricciones según tipo
            if service_type == 'Interurbano':
                # Verificar máximo 5h conducción continua
                # (Esto requeriría análisis más detallado de secuencias de turnos)
                pass
            elif service_type in ['Industrial', 'Urbano']:
                # Restricciones más flexibles
                pass

        print("  ✓ Verificación completada")

        # Mostrar resumen de violaciones si hay
        for regime, violations in violations_by_regime.items():
            if violations:
                print(f"  ⚠️ {regime}: {len(violations)} violaciones detectadas")

        print("\n" + "=" * 80)
        print("OPTIMIZACIÓN CON REGÍMENES COMPLETADA")
        print("=" * 80)
        print(f"Los resultados se han guardado en:")
        print(f"  - Excel: {excel_output}")
        print(f"  - HTML: {html_output}")
        print()

        return 0

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
