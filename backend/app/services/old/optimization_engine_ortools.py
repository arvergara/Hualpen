"""
Motor de Optimización Real con Google OR-Tools

Este módulo implementa la optimización real de asignación de conductores
a servicios usando Google OR-Tools, respetando las restricciones laborales
chilenas.
"""

import time
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from ortools.sat.python import cp_model
import numpy as np


class RealOptimizationEngine:
    """
    Motor de optimización real usando OR-Tools.
    
    Implementa:
    - Asignación óptima de conductores a servicios
    - Respeto de restricciones laborales chilenas
    - Minimización de costos y kilómetros muertos
    - Maximización del cumplimiento normativo
    """
    
    def __init__(self):
        pass
        
    def optimize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecuta la optimización real usando OR-Tools
        """
        start_time = time.time()
        
        drivers = data["drivers"]
        services = data["services"]
        constraints = data["constraints"]
        date_range = data["date_range"]
        
        # Ejecutar optimización por día
        all_assignments = []
        all_violations = []
        
        start_date = datetime.strptime(date_range["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(date_range["end_date"], "%Y-%m-%d")
        
        current_date = start_date
        while current_date <= end_date:
            # Optimizar asignaciones para este día
            daily_assignments, daily_violations = self._optimize_daily_assignments(
                drivers, services, constraints, current_date
            )
            
            all_assignments.extend(daily_assignments)
            all_violations.extend(daily_violations)
            
            # Actualizar horas trabajadas de los conductores
            self._update_driver_hours(drivers, daily_assignments)
            
            current_date += timedelta(days=1)
        
        # Calcular métricas reales
        metrics = self._calculate_real_metrics(all_assignments, drivers, services)
        
        # Generar advertencias basadas en datos reales
        warnings = self._generate_real_warnings(all_assignments, metrics, drivers)
        
        # Generar recomendaciones basadas en el análisis
        recommendations = self._generate_real_recommendations(metrics, all_violations)
        
        compute_time = time.time() - start_time
        
        return {
            "status": "success" if len(all_violations) == 0 else "partial",
            "assignments": all_assignments,
            "metrics": metrics,
            "violations": all_violations,
            "warnings": warnings,
            "recommendations": recommendations,
            "compute_time": compute_time,
            "solution_quality": self._calculate_solution_quality(metrics, all_violations)
        }
    
    def _optimize_daily_assignments(
        self, 
        drivers: List[Dict], 
        services: List[Dict], 
        constraints: Dict,
        date: datetime
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Optimiza las asignaciones para un día específico usando CP-SAT solver
        """
        assignments = []
        violations = []
        
        # Verificar si es domingo
        is_sunday = date.weekday() == 6
        
        # Crear nuevo modelo para esta optimización
        model = cp_model.CpModel()
        solver = cp_model.CpSolver()
        
        # Crear variables de decisión
        assignment_vars = {}
        
        # Variable binaria: x[d,s] = 1 si conductor d es asignado a servicio s
        for d_idx, driver in enumerate(drivers):
            for s_idx, service in enumerate(services):
                var_name = f"x_{d_idx}_{s_idx}"
                assignment_vars[(d_idx, s_idx)] = model.NewBoolVar(var_name)
        
        # Restricción 1: Cada servicio debe tener exactamente un conductor
        for s_idx, service in enumerate(services):
            model.Add(
                sum(assignment_vars[(d_idx, s_idx)] for d_idx in range(len(drivers))) == 1
            )
        
        # Restricción 2: Un conductor no puede estar en dos servicios al mismo tiempo
        for d_idx, driver in enumerate(drivers):
            overlapping_services = self._find_overlapping_services(services)
            for service_pair in overlapping_services:
                model.Add(
                    assignment_vars[(d_idx, service_pair[0])] + 
                    assignment_vars[(d_idx, service_pair[1])] <= 1
                )
        
        # Restricción 3: Respetar horas máximas de conducción continua
        for d_idx, driver in enumerate(drivers):
            daily_hours = []
            for s_idx, service in enumerate(services):
                service_hours = self._calculate_service_hours(service)
                daily_hours.append(assignment_vars[(d_idx, s_idx)] * int(service_hours * 10))
            
            # Máximo de horas diarias
            max_daily_hours = int(constraints["maxDailyDrivingHours"] * 10)
            model.Add(sum(daily_hours) <= max_daily_hours)
        
        # Restricción 4: Domingos libres (min_sundays_off_per_month)
        if is_sunday:
            # Obtener el contador de domingos trabajados este mes para cada conductor
            for d_idx, driver in enumerate(drivers):
                sundays_worked = driver.get("sundays_worked_this_month", 0)
                max_sundays_work = 4 - constraints.get("min_sundays_off_per_month", 2)
                
                # Si ya trabajó el máximo de domingos permitidos, no puede trabajar este domingo
                if sundays_worked >= max_sundays_work:
                    for s_idx in range(len(services)):
                        model.Add(assignment_vars[(d_idx, s_idx)] == 0)
        
        # Función objetivo: Minimizar costos y kilómetros muertos
        objective = []
        
        for d_idx, driver in enumerate(drivers):
            for s_idx, service in enumerate(services):
                # Costo del conductor
                service_hours = self._calculate_service_hours(service)
                hourly_rate = driver.get("hourlyRate", 15000)
                labor_cost = int(service_hours * hourly_rate)
                
                # Kilómetros muertos (distancia desde ubicación base del conductor)
                dead_km = self._calculate_dead_kilometers(driver, service)
                dead_km_cost = int(dead_km * 500)  # 500 pesos por km
                
                total_cost = labor_cost + dead_km_cost
                objective.append(assignment_vars[(d_idx, s_idx)] * total_cost)
        
        model.Minimize(sum(objective))
        
        # Resolver el modelo
        solver.parameters.max_time_in_seconds = 30.0
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Extraer asignaciones
            for d_idx, driver in enumerate(drivers):
                for s_idx, service in enumerate(services):
                    if solver.Value(assignment_vars[(d_idx, s_idx)]) == 1:
                        assignment = self._create_assignment(
                            driver, service, date, constraints
                        )
                        assignments.append(assignment)
                        
                        # Verificar violaciones
                        driver_violations = self._check_driver_violations(
                            driver, assignment, constraints
                        )
                        violations.extend(driver_violations)
        
        return assignments, violations
    
    def _calculate_service_hours(self, service: Dict) -> float:
        """Calcula las horas de un servicio"""
        start_time = datetime.strptime(service["schedule"]["startTime"], "%H:%M")
        end_time = datetime.strptime(service["schedule"]["endTime"], "%H:%M")
        duration = (end_time - start_time).total_seconds() / 3600
        return max(duration, 0)
    
    def _calculate_dead_kilometers(self, driver: Dict, service: Dict) -> float:
        """Calcula los kilómetros muertos entre la ubicación del conductor y el servicio"""
        # Simplificación: usar distancia euclidiana
        driver_loc = driver.get("baseLocation", {"lat": -36.8201, "lng": -73.0444})
        service_origin = {"lat": -36.8201, "lng": -73.0444}  # Ubicación por defecto
        
        lat_diff = abs(driver_loc["lat"] - service_origin["lat"])
        lng_diff = abs(driver_loc["lng"] - service_origin["lng"])
        
        # Aproximación simple: 111 km por grado
        distance = np.sqrt(lat_diff**2 + lng_diff**2) * 111
        return distance
    
    def _find_overlapping_services(self, services: List[Dict]) -> List[Tuple[int, int]]:
        """Encuentra pares de servicios que se superponen en tiempo"""
        overlapping = []
        
        for i in range(len(services)):
            for j in range(i + 1, len(services)):
                if self._services_overlap(services[i], services[j]):
                    overlapping.append((i, j))
        
        return overlapping
    
    def _services_overlap(self, service1: Dict, service2: Dict) -> bool:
        """Verifica si dos servicios se superponen en tiempo"""
        start1 = datetime.strptime(service1["schedule"]["startTime"], "%H:%M")
        end1 = datetime.strptime(service1["schedule"]["endTime"], "%H:%M")
        start2 = datetime.strptime(service2["schedule"]["startTime"], "%H:%M")
        end2 = datetime.strptime(service2["schedule"]["endTime"], "%H:%M")
        
        return not (end1 <= start2 or end2 <= start1)
    
    def _create_assignment(
        self, 
        driver: Dict, 
        service: Dict, 
        date: datetime,
        constraints: Dict
    ) -> Dict:
        """Crea un registro de asignación"""
        service_hours = self._calculate_service_hours(service)
        
        # Calcular descansos requeridos
        breaks = []
        if service_hours > constraints["maxContinuousDrivingHours"]:
            num_breaks = int(service_hours / constraints["maxContinuousDrivingHours"])
            for i in range(num_breaks):
                break_time = datetime.strptime(service["schedule"]["startTime"], "%H:%M")
                break_time += timedelta(hours=constraints["maxContinuousDrivingHours"] * (i + 1))
                breaks.append({
                    "start_time": break_time.strftime("%H:%M"),
                    "end_time": (break_time + timedelta(minutes=constraints["requiredBreakMinutes"])).strftime("%H:%M"),
                    "duration": constraints["requiredBreakMinutes"],
                    "type": "mandatory"
                })
        
        return {
            "driver_id": driver["id"],
            "service_id": service["id"],
            "position": "primary",
            "date": date.strftime("%Y-%m-%d"),
            "shift_start": service["schedule"]["startTime"],
            "shift_end": service["schedule"]["endTime"],
            "actual_driving_hours": service_hours,
            "breaks_taken": breaks,
            "status": "scheduled",
            "driver_name": driver["name"],
            "service_name": service["name"],
            "route": f"{service['route']['origin']} - {service['route']['destination']}",
            "dead_kilometers": self._calculate_dead_kilometers(driver, service)
        }
    
    def _check_driver_violations(
        self, 
        driver: Dict, 
        assignment: Dict,
        constraints: Dict
    ) -> List[Dict]:
        """Verifica violaciones de restricciones laborales"""
        violations = []
        
        # Verificar horas continuas de conducción
        if assignment["actual_driving_hours"] > constraints["maxContinuousDrivingHours"]:
            if len(assignment["breaks_taken"]) == 0:
                violations.append({
                    "driver_id": driver["id"],
                    "driver_name": driver["name"],
                    "date": assignment["date"],
                    "type": "continuous_driving",
                    "constraint": "Conducción continua máxima",
                    "expected": f"{constraints['maxContinuousDrivingHours']} horas",
                    "actual": f"{assignment['actual_driving_hours']:.1f} horas",
                    "severity": "critical",
                    "description": f"El conductor {driver['name']} excede las horas continuas permitidas"
                })
        
        # Verificar horas semanales
        current_week_hours = driver.get("availability", {}).get("currentWeekHours", 0)
        total_week_hours = current_week_hours + assignment["actual_driving_hours"]
        
        if total_week_hours > constraints["maxWeeklyDrivingHours"]:
            violations.append({
                "driver_id": driver["id"],
                "driver_name": driver["name"],
                "date": assignment["date"],
                "type": "weekly_hours",
                "constraint": "Horas semanales máximas",
                "expected": f"{constraints['maxWeeklyDrivingHours']} horas",
                "actual": f"{total_week_hours:.1f} horas",
                "severity": "major",
                "description": f"El conductor {driver['name']} excede las horas semanales permitidas"
            })
        
        # Verificar restricción de domingos libres
        assignment_date = datetime.strptime(assignment["date"], "%Y-%m-%d")
        if assignment_date.weekday() == 6:  # Es domingo
            sundays_worked = driver.get("sundays_worked_this_month", 0)
            min_sundays_off = constraints.get("min_sundays_off_per_month", 2)
            max_sundays_work = 4 - min_sundays_off  # Asumiendo 4 domingos por mes
            
            if sundays_worked > max_sundays_work:
                violations.append({
                    "driver_id": driver["id"],
                    "driver_name": driver["name"],
                    "date": assignment["date"],
                    "type": "sunday_restriction",
                    "constraint": "Domingos libres mínimos",
                    "expected": f"Mínimo {min_sundays_off} domingos libres al mes",
                    "actual": f"Ya trabajó {sundays_worked} domingos este mes",
                    "severity": "major",
                    "description": f"El conductor {driver['name']} excede el límite de domingos trabajados (debe tener {min_sundays_off} domingos libres al mes)"
                })
        
        return violations
    
    def _update_driver_hours(self, drivers: List[Dict], assignments: List[Dict]):
        """Actualiza las horas trabajadas de los conductores y rastrea domingos trabajados"""
        for assignment in assignments:
            driver = next((d for d in drivers if d["id"] == assignment["driver_id"]), None)
            if driver:
                availability = driver.get("availability", {})
                availability["currentWeekHours"] = availability.get("currentWeekHours", 0) + assignment["actual_driving_hours"]
                availability["currentMonthHours"] = availability.get("currentMonthHours", 0) + assignment["actual_driving_hours"]
                
                # Rastrear domingos trabajados en el mes
                assignment_date = datetime.strptime(assignment["date"], "%Y-%m-%d")
                if assignment_date.weekday() == 6:  # Es domingo
                    driver["sundays_worked_this_month"] = driver.get("sundays_worked_this_month", 0) + 1
    
    def _calculate_real_metrics(
        self, 
        assignments: List[Dict], 
        drivers: List[Dict],
        services: List[Dict]
    ) -> Dict:
        """Calcula métricas reales basadas en las asignaciones"""
        total_labor_cost = 0
        total_overtime_cost = 0
        total_dead_km = 0
        total_driving_hours = 0
        
        # Calcular costos por conductor
        driver_hours = {}
        for assignment in assignments:
            driver_id = assignment["driver_id"]
            if driver_id not in driver_hours:
                driver_hours[driver_id] = 0
            driver_hours[driver_id] += assignment["actual_driving_hours"]
            
            # Encontrar datos del conductor
            driver = next((d for d in drivers if d["id"] == driver_id), None)
            if driver:
                hourly_rate = driver.get("hourlyRate", 15000)
                hours = assignment["actual_driving_hours"]
                
                # Calcular costo regular y overtime
                if driver_hours[driver_id] <= 45:  # Horas normales semanales
                    total_labor_cost += hours * hourly_rate
                else:
                    # Horas extra
                    overtime_rate = driver.get("overtimeRate", 1.5)
                    overtime_hours = driver_hours[driver_id] - 45
                    regular_hours = hours - overtime_hours
                    
                    total_labor_cost += regular_hours * hourly_rate
                    total_overtime_cost += overtime_hours * hourly_rate * overtime_rate
            
            total_dead_km += assignment.get("dead_kilometers", 0)
            total_driving_hours += assignment["actual_driving_hours"]
        
        # Calcular utilización
        total_available_hours = len(drivers) * 45  # 45 horas semanales por conductor
        driver_utilization = (total_driving_hours / total_available_hours) * 100 if total_available_hours > 0 else 0
        
        # Calcular cobertura de servicios
        services_covered = len(set(a["service_id"] for a in assignments))
        total_services = len(services) * 7  # Servicios por semana
        service_coverage = (services_covered / total_services) * 100 if total_services > 0 else 0
        
        # Calcular cumplimiento
        compliance_score = 100  # Empezar con 100 y restar por violaciones
        for assignment in assignments:
            if "violation" in assignment:
                compliance_score -= 5
        compliance_score = max(compliance_score, 0)
        
        # Calcular equidad (distribución de horas entre conductores)
        if driver_hours:
            hours_values = list(driver_hours.values())
            hours_std = np.std(hours_values) if len(hours_values) > 1 else 0
            hours_mean = np.mean(hours_values) if hours_values else 0
            equity_score = max(0, 100 - (hours_std / hours_mean * 100)) if hours_mean > 0 else 100
        else:
            equity_score = 100
        
        # Calcular eficiencia
        efficiency_score = 100 - (total_dead_km / (total_driving_hours * 20) * 100) if total_driving_hours > 0 else 100
        efficiency_score = max(0, min(100, efficiency_score))
        
        return {
            "totalCost": total_labor_cost + total_overtime_cost + (total_dead_km * 500),
            "laborCost": total_labor_cost,
            "overtimeCost": total_overtime_cost,
            "deadKilometers": total_dead_km,
            "driverUtilization": driver_utilization,
            "servicesCovered": service_coverage,
            "complianceScore": compliance_score,
            "equityScore": equity_score,
            "efficiencyScore": efficiency_score
        }
    
    def _generate_real_warnings(
        self, 
        assignments: List[Dict], 
        metrics: Dict,
        drivers: List[Dict]
    ) -> List[Dict]:
        """Genera advertencias basadas en el análisis real"""
        warnings = []
        
        # Advertencia por baja utilización
        if metrics["driverUtilization"] < 70:
            warnings.append({
                "type": "low_utilization",
                "message": f"Utilización de conductores baja: {metrics['driverUtilization']:.1f}%",
                "severity": "medium",
                "recommendation": "Considere reducir el número de conductores disponibles"
            })
        
        # Advertencia por altos kilómetros muertos
        if metrics["deadKilometers"] > 1000:
            warnings.append({
                "type": "high_dead_km",
                "message": f"Alto número de kilómetros muertos: {metrics['deadKilometers']:.0f} km",
                "severity": "medium",
                "recommendation": "Revise la asignación de zonas base de los conductores"
            })
        
        # Advertencia por distribución desigual
        if metrics["equityScore"] < 80:
            warnings.append({
                "type": "unequal_distribution",
                "message": f"Distribución desigual de horas: equidad al {metrics['equityScore']:.1f}%",
                "severity": "low",
                "recommendation": "Considere rotar las asignaciones entre conductores"
            })
        
        return warnings
    
    def _generate_real_recommendations(
        self, 
        metrics: Dict, 
        violations: List[Dict]
    ) -> List[str]:
        """Genera recomendaciones basadas en el análisis"""
        recommendations = []
        
        if violations:
            recommendations.append(
                f"Se detectaron {len(violations)} violaciones. Revise las restricciones laborales."
            )
        
        if metrics["deadKilometers"] > 500:
            recommendations.append(
                "Considere reasignar conductores a zonas más cercanas a sus rutas habituales."
            )
        
        if metrics["overtimeCost"] > metrics["laborCost"] * 0.2:
            recommendations.append(
                "El costo de horas extra es alto. Considere contratar conductores adicionales."
            )
        
        if metrics["servicesCovered"] < 95:
            recommendations.append(
                f"Cobertura de servicios al {metrics['servicesCovered']:.1f}%. Revise la disponibilidad de conductores."
            )
        
        if not recommendations:
            recommendations.append(
                "La optimización se completó exitosamente. Los resultados cumplen con todos los objetivos."
            )
        
        return recommendations
    
    def _calculate_solution_quality(self, metrics: Dict, violations: List[Dict]) -> float:
        """Calcula la calidad general de la solución"""
        # Peso de cada componente
        weights = {
            "compliance": 0.4,
            "efficiency": 0.2,
            "equity": 0.2,
            "coverage": 0.2
        }
        
        # Penalización por violaciones
        violation_penalty = min(len(violations) * 5, 50)
        
        quality = (
            metrics["complianceScore"] * weights["compliance"] +
            metrics["efficiencyScore"] * weights["efficiency"] +
            metrics["equityScore"] * weights["equity"] +
            metrics["servicesCovered"] * weights["coverage"]
        ) - violation_penalty
        
        return max(0, min(100, quality))