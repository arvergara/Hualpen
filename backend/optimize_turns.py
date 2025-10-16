#!/usr/bin/env python
"""
Interfaz interactiva amigable para optimización de turnos
"""

import sys
import os
from datetime import datetime
import calendar
from typing import Dict, List

# Agregar el directorio app al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.excel_reader import ExcelTemplateReader
# from app.services.roster_optimizer_adaptive import AdaptiveRosterOptimizer as RosterOptimizer
# from app.services.roster_optimizer_improved import ImprovedRosterOptimizer as RosterOptimizer
# from app.services.roster_optimizer_fixed import RobustRosterOptimizer as RosterOptimizer
# from app.services.roster_optimizer_simple import SimpleRosterOptimizer as RosterOptimizer
from app.services.roster_optimizer_grouped import GroupedRosterOptimizer
from app.services.roster_optimizer_traditional import TraditionalRosterOptimizer
from app.services.output_generator import OutputGenerator
from app.services.output_generator_enhanced import EnhancedOutputGenerator
from app.services.html_report_generator import HTMLReportGenerator


def clear_screen():
    """Limpia la pantalla"""
    os.system('clear' if os.name == 'posix' else 'cls')


def print_header():
    """Imprime el encabezado del sistema"""
    print("=" * 80)
    print("🚌 SISTEMA DE OPTIMIZACIÓN DE TURNOS - HUALPÉN 🚌".center(80))
    print("=" * 80)
    print()


def select_excel_file() -> str:
    """Permite seleccionar el archivo Excel"""
    default_file = '/Users/alfil/Mi unidad/Prototipo_Hualpen/nueva_info/Template TURNOS  Hualpén 08-09-2025.xlsx'
    
    print("📁 SELECCIÓN DE ARCHIVO EXCEL")
    print("-" * 40)
    print(f"Archivo por defecto:")
    print(f"  {default_file}")
    print()
    
    choice = input("¿Usar archivo por defecto? (S/n): ").strip().lower()
    
    if choice == 'n':
        file_path = input("Ingrese la ruta del archivo Excel: ").strip()
        if not os.path.exists(file_path):
            print("❌ Error: El archivo no existe.")
            return select_excel_file()
        return file_path
    
    return default_file


def select_client(reader: ExcelTemplateReader) -> str:
    """Permite seleccionar un cliente de la lista disponible"""
    clients = reader.get_available_clients()
    
    print("\n👥 SELECCIÓN DE CLIENTE")
    print("-" * 40)
    print("Clientes disponibles:")
    print()
    
    # Mostrar clientes en columnas
    for i, client in enumerate(clients, 1):
        print(f"  {i:2d}. {client}")
    
    print()
    
    while True:
        try:
            choice = input(f"Seleccione el cliente (1-{len(clients)}): ").strip()
            index = int(choice) - 1
            
            if 0 <= index < len(clients):
                selected = clients[index]
                print(f"\n✓ Cliente seleccionado: {selected}")
                return selected
            else:
                print("❌ Opción inválida. Intente nuevamente.")
        except ValueError:
            print("❌ Por favor ingrese un número válido.")



def select_month() -> tuple:
    """Permite seleccionar el mes a optimizar"""
    year = 2025
    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    
    print("\n📅 SELECCIÓN DE PERÍODO")
    print("-" * 40)
    print(f"Año: {year}")
    print("\nMeses disponibles:")
    print()
    
    # Mostrar meses en 3 columnas
    for i in range(0, 12, 3):
        row = ""
        for j in range(3):
            if i + j < 12:
                row += f"  {i+j+1:2d}. {months[i+j]:12s}"
        print(row)
    
    print()
    
    while True:
        try:
            choice = input("Seleccione el mes (1-12): ").strip()
            month = int(choice)
            
            if 1 <= month <= 12:
                month_name = months[month-1]
                num_days = calendar.monthrange(year, month)[1]
                
                # Contar domingos
                sundays = sum(1 for day in range(1, num_days + 1)
                            if datetime(year, month, day).weekday() == 6)
                
                print(f"\n✓ Período seleccionado: {month_name} {year}")
                print(f"  • {num_days} días en total")
                print(f"  • {sundays} domingos")
                
                return year, month
            else:
                print("❌ Mes inválido. Intente nuevamente.")
        except ValueError:
            print("❌ Por favor ingrese un número válido.")


def show_summary(client_data: Dict, client_name: str, year: int, month: int):
    """Muestra un resumen de los datos antes de optimizar"""
    print("\n📊 RESUMEN DE LA OPTIMIZACIÓN")
    print("=" * 80)
    
    print(f"\n🏢 Cliente: {client_name}")
    print(f"📅 Período: {calendar.month_name[month]} {year}")
    print(f"🚌 Servicios: {len(client_data['services'])}")
    
    # Calcular estadísticas
    total_shifts = sum(len(s['shifts']) for s in client_data['services'])
    total_vehicles = sum(s['vehicles']['quantity'] for s in client_data['services'])
    
    print(f"🔄 Turnos totales: {total_shifts}")
    print(f"🚐 Vehículos requeridos: {total_vehicles}")
    
    # Calcular horas totales aproximadas
    total_hours = 0
    for service in client_data['services']:
        days_in_month = len([d for d in range(7) if d in service['frequency']['days']]) * 4
        for shift in service['shifts']:
            total_hours += shift['duration_hours'] * service['vehicles']['quantity'] * days_in_month
    
    print(f"⏱️  Horas estimadas: {total_hours:.0f} horas/mes")
    print(f"👷 Conductores mínimos teóricos: {int(total_hours/160)}")
    
    print("\n" + "=" * 80)


def confirm_optimization() -> bool:
    """Ya no pedimos confirmación - siempre procede"""
    return True  # Siempre continuar


def show_progress_animation():
    """Muestra una animación de progreso"""
    import time
    import threading
    
    def animate():
        chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        i = 0
        while not stop_animation:
            print(f'\r{chars[i % len(chars)]} Optimizando...', end='', flush=True)
            time.sleep(0.1)
            i += 1
    
    stop_animation = False
    t = threading.Thread(target=animate)
    t.start()
    
    return lambda: stop_animation


def main():
    """Función principal interactiva"""
    try:
        clear_screen()
        print_header()
        
        # Paso 1: Seleccionar archivo Excel
        excel_file = select_excel_file()
        
        if not os.path.exists(excel_file):
            print(f"❌ Error: No se encuentra el archivo {excel_file}")
            return 1
        
        # Leer el archivo Excel
        print("\n⏳ Leyendo archivo Excel...")
        reader = ExcelTemplateReader(excel_file)
        
        # Paso 2: Seleccionar cliente
        client_name = select_client(reader)
        
        # Leer datos del cliente
        print("\n⏳ Cargando datos del cliente...")
        client_data = reader.read_client_data(client_name)
        
        # Paso 3: Seleccionar tipo de optimización
        print("\n📋 TIPO DE OPTIMIZACIÓN")
        print("-" * 40)
        print("\n1. Optimización flexible (busca mínimo de conductores)")
        print("2. Patrones tradicionales (5x2, 6x1, 4x3, etc.)")
        print("\nLa opción 2 respeta las mallas de trabajo tradicionales")
        print("y es más compatible con las prácticas del sector.\n")
        
        while True:
            opt_type = input("Seleccione tipo de optimización (1-2) [1]: ").strip()
            if opt_type == "" or opt_type == "1":
                use_traditional = False
                break
            elif opt_type == "2":
                use_traditional = True
                break
            else:
                print("❌ Opción inválida. Intente nuevamente.")
        
        # Paso 4: Directamente ir a optimización mensual (eliminada la opción anual)
        year, month = select_month()
        
        # Mostrar resumen
        show_summary(client_data, client_name, year, month)
        
        # No pedimos confirmación - directo a optimizar
        # Paso 4: Ejecutar optimización
        print("\n🚀 INICIANDO OPTIMIZACIÓN")
        print("=" * 80)
        print()
        
        if use_traditional:
            print("Usando PATRONES TRADICIONALES de trabajo (5x2, 6x1, 4x3).")
            print("El sistema respetará las mallas de trabajo habituales del sector.")
        else:
            print("Usando optimización FLEXIBLE.")
            print("El sistema buscará el mínimo número de conductores necesarios.")
        
        print("\nEl sistema agregará conductores automáticamente hasta encontrar")
        print("una solución factible que cumpla todas las restricciones laborales.")
        print()
        
        # Crear optimizador según tipo seleccionado
        if use_traditional:
            optimizer = TraditionalRosterOptimizer(client_data)
        else:
            optimizer = GroupedRosterOptimizer(client_data)
        
        solution = optimizer.optimize_month(year, month)
        
        if solution['status'] != 'success':
            # Si el optimizador agrupado falla, intentar con el simple
            print(f"\n⚠️  El optimizador agrupado no pudo resolver. Intentando con optimizador simple...")
            from app.services.roster_optimizer_simple import SimpleRosterOptimizer
            optimizer = SimpleRosterOptimizer(client_data)
            solution = optimizer.optimize_month(year, month)
            
            if solution['status'] != 'success':
                print(f"\n❌ Error: La optimización falló")
                print(f"   {solution.get('message', 'Error desconocido')}")
                return 1
            else:
                print(f"\n✓ Optimización completada con el método simple")
        
        # Mostrar resultados
        print("\n" + "=" * 80)
        print("✅ OPTIMIZACIÓN COMPLETADA EXITOSAMENTE")
        print("=" * 80)
        
        print(f"\n📊 RESULTADOS:")
        print(f"  • Asignaciones generadas: {len(solution['assignments'])}")
        print(f"  • Conductores utilizados: {solution['metrics']['drivers_used']}")
        
        # total_cost puede estar en metrics o en el nivel superior
        total_cost = solution.get('total_cost', solution['metrics'].get('total_cost', 0))
        print(f"  • Costo total: ${total_cost:,.0f}")
        
        if 'quality_metrics' in solution:
            qm = solution['quality_metrics']
            print(f"\n🎯 CALIDAD DE LA SOLUCIÓN:")
            
            # Determinar calidad basada en ratio o score
            if 'quality' in qm:
                print(f"  • {qm['quality']}")
            elif 'optimality_ratio' in qm:
                ratio = qm['optimality_ratio']
                quality = "EXCELENTE" if ratio > 0.8 else "BUENA" if ratio > 0.6 else "ACEPTABLE"
                print(f"  • Solución {quality}")
                print(f"  • Ratio de optimalidad: {ratio:.2f}")
            elif solution.get('quality_score'):
                score = solution['quality_score']
                quality = "EXCELENTE" if score > 0.8 else "BUENA" if score > 0.6 else "ACEPTABLE"
                print(f"  • Solución {quality} (score: {score:.2f})")
            
            if qm.get('efficiency_metrics'):
                em = qm['efficiency_metrics']
                print(f"  • Utilización promedio: {em['avg_utilization']:.1f}%")
        
        # Mostrar análisis de capacidad (holgura) si está disponible
        if 'capacity_analysis' in solution:
            capacity = solution['capacity_analysis']
            print(f"\n💼 ANÁLISIS DE CAPACIDAD (HOLGURA):")
            print(f"  • Horas disponibles totales: {capacity['total_available_hours']:.0f}")
            print(f"  • Días disponibles totales: {capacity['total_available_days']}")
            
            if capacity.get('potential_additional_shifts'):
                shifts = capacity['potential_additional_shifts']
                print(f"  • Capacidad para turnos adicionales de 8h: {shifts['normal_shifts_8h']}")
            
            if capacity.get('drivers_with_high_availability'):
                high_avail = capacity['drivers_with_high_availability']
                if len(high_avail) > 0:
                    print(f"  • Conductores con alta disponibilidad: {len(high_avail)}")
        
        # Generar reportes
        print("\n📄 GENERANDO REPORTES...")
        # Generar reporte Excel estándar
        output_gen = OutputGenerator(solution, client_name)
        excel_output = output_gen.generate_excel_report()
        
        # Generar reporte Excel mejorado con vista detallada por conductor
        enhanced_gen = EnhancedOutputGenerator(solution, client_name)
        enhanced_excel = enhanced_gen.generate_excel_with_driver_details()
        
        # Generar reporte HTML
        html_gen = HTMLReportGenerator(solution, client_name)
        html_output = html_gen.generate_html_report()
        
        print(f"\n✅ Archivos generados:")
        print(f"  • Excel: {excel_output}")
        print(f"  • Excel Detallado: {enhanced_excel}")
        print(f"  • HTML: {html_output}")
        
        # Preguntar si desea optimizar otro cliente
        print("\n" + "=" * 80)
        choice = input("\n¿Desea optimizar otro cliente? (s/N): ").strip().lower()
        
        if choice == 's':
            return main()
        
        print("\n👋 ¡Gracias por usar el Sistema de Optimización de Turnos!")
        print()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Optimización interrumpida por el usuario.")
        return 1
    except Exception as e:
        print(f"\n❌ Error inesperado: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())