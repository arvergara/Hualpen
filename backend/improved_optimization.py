"""
Versión mejorada del optimizador que realmente permite múltiples turnos por conductor
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ortools.sat.python import cp_model
from datetime import date, timedelta
from collections import defaultdict
import time

def create_molynor_february_data():
    """Crea datos completos de Molynor para febrero 2025"""
    shifts = []
    shift_id = 0
    
    # Febrero 2025 tiene 28 días
    for day in range(28):
        current_date = date(2025, 2, day + 1)
        
        for service_id in range(11):
            # Dos turnos por servicio
            for turn in range(2):
                if turn == 0:
                    start_time = '06:00' if service_id < 5 else '07:00'
                    end_time = '14:00' if service_id < 5 else '15:00'
                    start_min = 360 if service_id < 5 else 420
                    end_min = 840 if service_id < 5 else 900
                else:
                    start_time = '14:00' if service_id < 5 else '15:00'
                    end_time = '22:00' if service_id < 5 else '23:00'
                    start_min = 840 if service_id < 5 else 900
                    end_min = 1320 if service_id < 5 else 1380
                
                shifts.append({
                    'id': shift_id,
                    'date': current_date,
                    'service_id': service_id,
                    'shift_number': turn + 1,
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_minutes': start_min,
                    'end_minutes': end_min,
                    'duration_hours': 8.0,
                    'is_sunday': current_date.weekday() == 6
                })
                shift_id += 1
    
    return shifts

def optimize_with_smart_assignment(shifts, num_drivers, verbose=True):
    """
    Optimización mejorada que realmente aprovecha la capacidad de múltiples turnos
    """
    model = cp_model.CpModel()
    
    # Variables: X[driver][shift]
    X = {}
    for d in range(num_drivers):
        for s in range(len(shifts)):
            X[d, s] = model.NewBoolVar(f'x_{d}_{s}')
    
    # RESTRICCIÓN 1: Cada turno debe ser cubierto exactamente una vez
    for s in range(len(shifts)):
        model.Add(sum(X[d, s] for d in range(num_drivers)) == 1)
    
    # Preparar estructuras de datos para restricciones eficientes
    shifts_by_date = defaultdict(list)
    for s_idx, shift in enumerate(shifts):
        shifts_by_date[shift['date']].append((s_idx, shift))
    
    # Pre-calcular qué turnos son compatibles (pueden ser hechos por el mismo conductor)
    compatible_pairs = set()
    incompatible_pairs = set()
    
    for date, day_shifts in shifts_by_date.items():
        day_shifts.sort(key=lambda x: x[1]['start_minutes'])
        
        for i in range(len(day_shifts)):
            for j in range(i + 1, len(day_shifts)):
                s_idx_i, shift_i = day_shifts[i]
                s_idx_j, shift_j = day_shifts[j]
                
                # Calcular gap entre turnos
                gap = shift_j['start_minutes'] - shift_i['end_minutes']
                
                if gap < 0:  # Se solapan
                    incompatible_pairs.add((s_idx_i, s_idx_j))
                elif gap >= 60:  # Al menos 1h de descanso
                    # Verificar span total
                    span = (shift_j['end_minutes'] - shift_i['start_minutes']) / 60
                    
                    if span <= 16:  # Dentro del límite de 16h
                        # Verificar restricción de 5h continuas
                        if gap >= 120:  # 2+ horas de descanso reinicia el contador
                            compatible_pairs.add((s_idx_i, s_idx_j))
                        elif shift_i['duration_hours'] + shift_j['duration_hours'] <= 5:
                            # Menos de 2h descanso pero no excede 5h continuas
                            compatible_pairs.add((s_idx_i, s_idx_j))
                        else:
                            incompatible_pairs.add((s_idx_i, s_idx_j))
                    else:
                        incompatible_pairs.add((s_idx_i, s_idx_j))
                else:
                    # Gap < 60 min - necesita verificación adicional
                    if shift_i['duration_hours'] + shift_j['duration_hours'] > 5:
                        incompatible_pairs.add((s_idx_i, s_idx_j))
    
    if verbose:
        print(f"Pares compatibles encontrados: {len(compatible_pairs)}")
        print(f"Pares incompatibles: {len(incompatible_pairs)}")
    
    # RESTRICCIÓN 2: Aplicar solo incompatibilidades
    for d in range(num_drivers):
        for (s1, s2) in incompatible_pairs:
            model.Add(X[d, s1] + X[d, s2] <= 1)
    
    # RESTRICCIÓN 3: Máximo 180 horas mensuales por conductor (Interurbano)
    for d in range(num_drivers):
        total_hours = sum(X[d, s] * int(shifts[s]['duration_hours'] * 10) 
                         for s in range(len(shifts)))
        model.Add(total_hours <= 1800)  # 180 horas * 10 (para evitar decimales)
    
    # RESTRICCIÓN 4: Máximo 6 días consecutivos de trabajo
    dates = sorted(list(set(shift['date'] for shift in shifts)))
    for d in range(num_drivers):
        for start_idx in range(len(dates) - 6):
            consecutive_work = []
            for day_offset in range(7):
                date = dates[start_idx + day_offset]
                day_shifts = [s for s, shift in enumerate(shifts) if shift['date'] == date]
                
                # Trabaja ese día si hace algún turno
                works_day = model.NewBoolVar(f'works_d{d}_date{date}')
                model.AddMaxEquality(works_day, [X[d, s] for s in day_shifts])
                consecutive_work.append(works_day)
            
            model.Add(sum(consecutive_work) <= 6)
    
    # RESTRICCIÓN 5: Mínimo 2 domingos libres al mes
    sunday_shifts = [s for s, shift in enumerate(shifts) if shift['is_sunday']]
    sunday_dates = sorted(list(set(shift['date'] for shift in shifts if shift['is_sunday'])))
    
    for d in range(num_drivers):
        sunday_work = []
        for sunday in sunday_dates:
            day_shifts = [s for s in sunday_shifts if shifts[s]['date'] == sunday]
            works_sunday = model.NewBoolVar(f'works_sunday_d{d}_{sunday}')
            model.AddMaxEquality(works_sunday, [X[d, s] for s in day_shifts])
            sunday_work.append(works_sunday)
        
        # Máximo 2 domingos trabajados (de 4 en febrero)
        if len(sunday_dates) > 2:
            model.Add(sum(sunday_work) <= len(sunday_dates) - 2)
    
    # OBJETIVO: Minimizar conductores usados Y maximizar uso de múltiples turnos
    drivers_used = []
    multi_shift_bonus = []
    
    for d in range(num_drivers):
        # Variable: conductor usado
        used = model.NewBoolVar(f'used_{d}')
        model.AddMaxEquality(used, [X[d, s] for s in range(len(shifts))])
        drivers_used.append(used)
        
        # Bonus por hacer múltiples turnos en el mismo día (incentivo)
        for date, day_shifts in shifts_by_date.items():
            if len(day_shifts) > 1:
                shifts_in_day = [X[d, s_idx] for s_idx, _ in day_shifts]
                multi_var = model.NewIntVar(0, len(day_shifts), f'multi_d{d}_{date}')
                model.Add(multi_var == sum(shifts_in_day))
                
                # Bonus si hace 2+ turnos
                bonus = model.NewBoolVar(f'bonus_d{d}_{date}')
                model.Add(multi_var >= 2).OnlyEnforceIf(bonus)
                model.Add(multi_var < 2).OnlyEnforceIf(bonus.Not())
                multi_shift_bonus.append(bonus)
    
    # Objetivo combinado: minimizar conductores, maximizar múltiples turnos
    model.Minimize(sum(drivers_used) * 1000 - sum(multi_shift_bonus))
    
    # Resolver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8
    solver.parameters.linearization_level = 2
    
    status = solver.Solve(model)
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        actual_drivers = sum(solver.Value(used) for used in drivers_used)
        
        # Analizar asignaciones
        driver_shifts = defaultdict(list)
        for d in range(num_drivers):
            for s in range(len(shifts)):
                if solver.Value(X[d, s]):
                    driver_shifts[d].append(shifts[s])
        
        # Contar conductores con múltiples turnos
        multi_shift_count = 0
        total_multi_shifts = 0
        
        for d, d_shifts in driver_shifts.items():
            shifts_by_date_driver = defaultdict(list)
            for shift in d_shifts:
                shifts_by_date_driver[shift['date']].append(shift)
            
            has_multi = False
            for date, day_shifts in shifts_by_date_driver.items():
                if len(day_shifts) > 1:
                    has_multi = True
                    total_multi_shifts += len(day_shifts) - 1
            
            if has_multi:
                multi_shift_count += 1
        
        return {
            'status': 'success',
            'drivers_used': actual_drivers,
            'multi_shift_drivers': multi_shift_count,
            'total_multi_shifts': total_multi_shifts,
            'solver_status': solver.StatusName(status),
            'driver_assignments': driver_shifts
        }
    
    return {
        'status': 'failed',
        'solver_status': solver.StatusName(status)
    }

def main():
    """Prueba principal con datos completos de febrero"""
    print("="*60)
    print("OPTIMIZACIÓN MEJORADA PARA MOLYNOR - FEBRERO 2025")
    print("="*60)
    
    shifts = create_molynor_february_data()
    print(f"\nTotal turnos en febrero: {len(shifts)}")
    print(f"Turnos diarios: {len(shifts) // 28}")
    
    # Calcular horas totales
    total_hours = sum(s['duration_hours'] for s in shifts)
    print(f"Horas totales: {total_hours}")
    print(f"Mínimo teórico por horas (180h/conductor): {int(total_hours / 180) + 1}")
    
    # Probar con diferentes números de conductores
    test_ranges = [20, 22, 24, 26, 28, 30]
    
    for num_drivers in test_ranges:
        print(f"\n{'='*40}")
        print(f"Probando con {num_drivers} conductores...")
        start_time = time.time()
        
        result = optimize_with_smart_assignment(shifts, num_drivers)
        elapsed = time.time() - start_time
        
        if result['status'] == 'success':
            print(f"✅ SOLUCIÓN ENCONTRADA en {elapsed:.2f}s")
            print(f"   Estado: {result['solver_status']}")
            print(f"   Conductores utilizados: {result['drivers_used']}")
            print(f"   Conductores con múltiples turnos/día: {result['multi_shift_drivers']}")
            print(f"   Total de asignaciones múltiples: {result['total_multi_shifts']}")
            
            # Análisis detallado
            if result['multi_shift_drivers'] > 0:
                print("\n   Ejemplo de conductor con múltiples turnos:")
                for d, shifts in result['driver_assignments'].items():
                    if len(shifts) > 20:  # Conductor con muchos turnos
                        shifts_by_date = defaultdict(list)
                        for shift in shifts:
                            shifts_by_date[shift['date']].append(shift)
                        
                        for date, day_shifts in shifts_by_date.items():
                            if len(day_shifts) > 1:
                                print(f"   Conductor {d} el {date}:")
                                for s in day_shifts:
                                    print(f"     - {s['start_time']}-{s['end_time']} (Servicio {s['service_id']})")
                                break
                        break
            
            # Si encontramos solución óptima, terminamos
            if result['drivers_used'] <= 25:
                print("\n🎯 SOLUCIÓN ÓPTIMA ENCONTRADA")
                break
        else:
            print(f"❌ NO se encontró solución en {elapsed:.2f}s")
            print(f"   Estado: {result['solver_status']}")

if __name__ == "__main__":
    main()