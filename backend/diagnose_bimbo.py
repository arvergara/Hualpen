#!/usr/bin/env python
"""
Script de diagnóstico para identificar por qué se pierden servicios en Bimbo Faena
"""
import sys
import os
from datetime import datetime, date
from collections import defaultdict

# Agregar el directorio app al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.excel_reader import ExcelTemplateReader

def diagnose():
    """Diagnóstico completo de Bimbo Faena"""

    excel_file = '/Users/alfil/Library/CloudStorage/GoogleDrive-andres.vergara@maindset.cl/Mi unidad/Prototipo_Hualpen/nueva_info/Template TURNOS  Hualpén 08-09-2025.xlsx'
    client_name = 'Bimbo Faena'

    print("=" * 80)
    print("DIAGNÓSTICO BIMBO FAENA - Pérdida de Servicios")
    print("=" * 80)

    # Leer datos
    print("\n1. Leyendo datos del Excel...")
    reader = ExcelTemplateReader(excel_file)
    client_data = reader.read_client_data(client_name)

    print(f"   Total servicios leídos: {len(client_data['services'])}")

    # Analizar servicios
    print("\n2. Análisis detallado de servicios:")
    print("-" * 80)

    for idx, service in enumerate(client_data['services'], 1):
        print(f"\n   Servicio {idx}: {service['name']}")
        print(f"     - ID: {service['id']}")
        print(f"     - Grupo: {service.get('service_group', 'N/A')}")
        print(f"     - Tipo: {service.get('service_type', 'N/A')}")
        print(f"     - Vehículos: {service['vehicles']['quantity']} x {service['vehicles']['type']}")
        print(f"     - Frecuencia: {service['frequency']['description']}")
        print(f"     - Días: {service['frequency']['days']}")
        print(f"     - Turnos: {len(service['shifts'])}")

        for shift in service['shifts']:
            print(f"       * Turno {shift['shift_number']}: {shift['start_time']} - {shift['end_time']} ({shift['duration_hours']}h)")

    # Simular generación de turnos para Enero 13 (Lunes)
    print("\n" + "=" * 80)
    print("3. Simulación de generación de turnos para Lunes 13 Enero 2025")
    print("=" * 80)

    target_date = date(2025, 1, 13)  # Lunes
    weekday = target_date.weekday()  # 0 = Lunes

    print(f"\n   Fecha objetivo: {target_date} (día de semana: {weekday} = Lunes)")
    print(f"\n   Servicios que operan este día:")

    operating_count = 0
    total_shifts_generated = 0

    for service in client_data['services']:
        if weekday in service['frequency']['days']:
            operating_count += 1
            vehicles = service['vehicles']['quantity']
            shifts_per_vehicle = len(service['shifts'])
            total_for_service = vehicles * shifts_per_vehicle
            total_shifts_generated += total_for_service

            print(f"\n   ✓ {service['name']}")
            print(f"     - Vehículos: {vehicles}")
            print(f"     - Turnos por vehículo: {shifts_per_vehicle}")
            print(f"     - Total turnos generados: {total_for_service}")

            for shift in service['shifts']:
                print(f"       * {shift['start_time']} - {shift['end_time']} ({shift['duration_hours']}h)")

    print(f"\n" + "=" * 80)
    print(f"RESUMEN:")
    print(f"  - Total servicios leídos: {len(client_data['services'])}")
    print(f"  - Servicios que operan el lunes: {operating_count}")
    print(f"  - Total turnos que deberían generarse: {total_shifts_generated}")
    print("=" * 80)

    # Análisis por tipo de servicio
    print("\n4. Análisis por tipo de servicio:")
    service_types = defaultdict(int)
    vehicle_types = defaultdict(int)

    for service in client_data['services']:
        stype = service.get('service_type', 'Unknown')
        service_types[stype] += 1

        vtype = service['vehicles']['type']
        vehicle_types[vtype] += service['vehicles']['quantity']

    print("\n   Por tipo de servicio:")
    for stype, count in service_types.items():
        print(f"     - {stype}: {count} servicios")

    print("\n   Por tipo de vehículo:")
    for vtype, count in vehicle_types.items():
        print(f"     - {vtype}: {count} vehículos")

    # Revisar si hay servicios con jornada excepcional incorrecta
    print("\n5. Verificación de tipos de servicio vs jornadas:")
    print("-" * 80)

    for service in client_data['services']:
        stype = service.get('service_type', 'Unknown')

        # Verificar si es Faena Minera
        is_faena = 'faena' in stype.lower() or 'minera' in stype.lower()

        # Verificar duración de turnos
        for shift in service['shifts']:
            duration = shift['duration_hours']

            # Si no es Faena pero tiene turnos muy largos, podría ser problema
            if not is_faena and duration > 12:
                print(f"\n   ⚠️ POSIBLE PROBLEMA: {service['name']}")
                print(f"      - Tipo servicio: {stype} (NO ES FAENA)")
                print(f"      - Turno: {shift['start_time']} - {shift['end_time']} ({duration}h)")
                print(f"      - Problema: Turno muy largo para servicio no-faena")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    diagnose()
