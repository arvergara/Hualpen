#!/usr/bin/env python
"""
Analiza la capacidad disponible (holgura) de los conductores
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.excel_reader import ExcelTemplateReader
from app.services.roster_optimizer_traditional import TraditionalRosterOptimizer
from app.services.capacity_analyzer import CapacityAnalyzer

def analyze_client_capacity(client_name: str, year: int, month: int):
    """Analiza la capacidad disponible de un cliente"""
    
    # Leer datos
    excel_file = '/Users/alfil/Mi unidad/Prototipo_Hualpen/nueva_info/Template TURNOS  Hualpén 08-09-2025.xlsx'
    reader = ExcelTemplateReader(excel_file)
    client_data = reader.read_client_data(client_name)
    
    # Optimizar con patrones tradicionales
    print(f"Optimizando {client_name} para {month}/{year}...")
    optimizer = TraditionalRosterOptimizer(client_data)
    solution = optimizer.optimize_month(year, month)
    
    # Analizar capacidad
    print("\nAnalizando capacidad disponible...")
    analyzer = CapacityAnalyzer(solution, year, month)
    
    # Generar y mostrar reporte
    report = analyzer.generate_capacity_report()
    print(report)
    
    # Análisis adicional
    analysis = analyzer.analyze_capacity()
    
    print("\n" + "=" * 80)
    print("💡 OPORTUNIDADES DE REASIGNACIÓN")
    print("=" * 80)
    
    # Identificar mejores candidatos para reasignación
    candidates = []
    for driver_name, info in analysis['drivers'].items():
        if info['availability_score'] in ['ALTA', 'MEDIA']:
            candidates.append({
                'name': driver_name,
                'pattern': info['pattern'],
                'days_available': info['available']['days'],
                'hours_available': info['available']['hours'],
                'score': info['availability_score']
            })
    
    if candidates:
        candidates.sort(key=lambda x: x['days_available'], reverse=True)
        print("\n🎯 Mejores candidatos para tareas adicionales:")
        for i, candidate in enumerate(candidates[:5], 1):
            print(f"\n{i}. {candidate['name']} ({candidate['pattern']})")
            print(f"   • {candidate['days_available']} días disponibles")
            print(f"   • {candidate['hours_available']:.0f} horas disponibles")
            print(f"   • Disponibilidad: {candidate['score']}")
    
    # Calcular capacidad para otro cliente
    print("\n" + "=" * 80)
    print("📊 CAPACIDAD PARA ASIGNACIÓN ADICIONAL")
    print("=" * 80)
    
    total_available_hours = analysis['total_available_hours']
    total_available_days = analysis['total_available_days']
    
    print(f"\n📈 Capacidad total del equipo:")
    print(f"   • Horas disponibles: {total_available_hours:.0f}")
    print(f"   • Días disponibles: {total_available_days}")
    
    # Estimar qué servicios adicionales podrían cubrir
    print("\n🚌 Servicios adicionales que podrían cubrir:")
    
    # Turno corto (4 horas)
    short_shifts = int(total_available_hours / 4)
    print(f"   • Turnos cortos (4h): hasta {short_shifts} turnos")
    
    # Turno normal (8 horas)
    normal_shifts = int(total_available_hours / 8)
    print(f"   • Turnos normales (8h): hasta {normal_shifts} turnos")
    
    # Turno largo (12 horas)
    long_shifts = int(total_available_hours / 12)
    print(f"   • Turnos largos (12h): hasta {long_shifts} turnos")
    
    return analysis

if __name__ == "__main__":
    # Analizar Komatsu Car
    print("=" * 80)
    print("ANÁLISIS DE CAPACIDAD - KOMATSU CAR")
    print("=" * 80)
    
    analyze_client_capacity("Komatsu Car", 2025, 2)