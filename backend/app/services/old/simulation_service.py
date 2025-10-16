from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import random


class SimulationService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def run_scenario(self, scenario: dict) -> dict:
        """Run a simulation scenario"""
        # Simulate processing
        start_time = datetime.utcnow()
        
        # Extract parameters
        parameters = scenario.get("parameters", {})
        constraints_override = scenario.get("constraints_override", {})
        
        # Simulate metrics based on parameters
        driver_count = parameters.get("driver_count", 100)
        service_count = parameters.get("service_count", 50)
        
        # Calculate simulated metrics
        base_cost = driver_count * 850000  # Base salary
        overtime_factor = 1.0 + random.uniform(0.1, 0.3)
        total_cost = base_cost * overtime_factor
        
        compliance_score = random.uniform(85, 98)
        if constraints_override:
            # Looser constraints might reduce compliance
            compliance_score *= 0.95
        
        violations = int(random.uniform(0, 10))
        if compliance_score > 95:
            violations = max(0, violations - 5)
        
        return {
            "scenario_id": f"sim_{int(datetime.utcnow().timestamp())}",
            "scenario_name": scenario["name"],
            "metrics": {
                "total_cost": total_cost,
                "cost_per_service": total_cost / service_count,
                "driver_utilization": random.uniform(70, 90),
                "service_coverage": random.uniform(95, 100),
                "compliance_score": compliance_score,
                "dead_kilometers": random.uniform(200, 500),
                "average_shift_duration": random.uniform(7, 9)
            },
            "cost_breakdown": {
                "labor_cost": base_cost,
                "overtime_cost": total_cost - base_cost,
                "fuel_cost": random.uniform(50000, 100000),
                "maintenance_cost": random.uniform(20000, 40000)
            },
            "violations_summary": {
                "total": violations,
                "critical": max(0, violations // 3),
                "major": max(0, violations // 3),
                "minor": violations - (violations // 3) * 2
            },
            "recommendations": self._generate_recommendations(parameters, compliance_score)
        }
    
    async def compare_scenarios(self, scenarios: List[dict]) -> dict:
        """Compare multiple simulation scenarios"""
        results = []
        
        for scenario in scenarios:
            result = await self.run_scenario(scenario)
            results.append(result)
        
        # Find best scenario
        best_scenario = min(results, key=lambda r: r["metrics"]["total_cost"])
        
        # Build comparison
        comparison = {
            "baseline_scenario": results[0],
            "alternative_scenarios": results[1:],
            "best_scenario": best_scenario["scenario_id"],
            "comparison_summary": {
                "cost_savings": {
                    scenario["scenario_name"]: 
                    results[0]["metrics"]["total_cost"] - scenario["metrics"]["total_cost"]
                    for scenario in results[1:]
                },
                "compliance_impact": {
                    scenario["scenario_name"]: 
                    scenario["metrics"]["compliance_score"] - results[0]["metrics"]["compliance_score"]
                    for scenario in results[1:]
                },
                "recommendations": [
                    f"Scenario '{best_scenario['scenario_name']}' offers the best cost-effectiveness",
                    "Consider gradual implementation to minimize disruption",
                    "Monitor compliance metrics closely during transition"
                ]
            }
        }
        
        return comparison
    
    async def evaluate_tender(self, tender_requirements: Dict[str, Any]) -> dict:
        """Evaluate if a tender can be serviced"""
        # Extract requirements
        services_required = tender_requirements.get("services_required", 10)
        coverage_hours = tender_requirements.get("coverage_hours", 16)
        sla_requirements = tender_requirements.get("sla_requirements", {})
        
        # Calculate resources needed
        drivers_needed = services_required * coverage_hours / 8
        buses_needed = services_required
        
        # Simulate availability check
        can_service = random.random() > 0.3  # 70% chance we can service it
        
        proposal = {
            "tender_id": tender_requirements.get("tender_id", "NEW"),
            "can_service": can_service,
            "resources_required": {
                "drivers": int(drivers_needed),
                "buses": int(buses_needed),
                "additional_drivers_needed": max(0, int(drivers_needed) - 100),
                "additional_buses_needed": max(0, int(buses_needed) - 50)
            },
            "estimated_costs": {
                "monthly_operational": drivers_needed * 850000,
                "setup_cost": random.uniform(1000000, 5000000),
                "monthly_profit_margin": random.uniform(10, 25)
            },
            "risks": self._evaluate_tender_risks(tender_requirements),
            "recommendations": [
                "Hire additional drivers 2 months before start" if drivers_needed > 100 else None,
                "Negotiate flexible SLA terms for first 3 months",
                "Consider phased rollout to minimize risk"
            ]
        }
        
        return proposal
    
    async def what_if_analysis(
        self, 
        parameter: str, 
        min_value: float, 
        max_value: float, 
        steps: int
    ) -> dict:
        """Perform what-if analysis on a parameter"""
        step_size = (max_value - min_value) / (steps - 1)
        results = []
        
        for i in range(steps):
            value = min_value + (i * step_size)
            
            # Simulate impact
            if parameter == "driver_count":
                cost = value * 850000 * random.uniform(1.1, 1.3)
                utilization = min(95, 8000 / value)  # Assuming 8000 hours needed
            elif parameter == "overtime_rate":
                cost = 100 * 850000 + (value * 1000 * random.uniform(50, 100))
                utilization = random.uniform(70, 85)
            else:
                cost = random.uniform(80000000, 120000000)
                utilization = random.uniform(70, 90)
            
            results.append({
                "parameter_value": value,
                "metrics": {
                    "total_cost": cost,
                    "driver_utilization": utilization,
                    "service_coverage": random.uniform(95, 100),
                    "compliance_score": random.uniform(90, 98)
                }
            })
        
        # Find optimal value
        optimal = min(results, key=lambda r: r["metrics"]["total_cost"])
        
        return {
            "parameter": parameter,
            "range": {"min": min_value, "max": max_value},
            "results": results,
            "optimal_value": optimal["parameter_value"],
            "insights": [
                f"Optimal {parameter} is around {optimal['parameter_value']:.0f}",
                f"Cost varies by {((max(r['metrics']['total_cost'] for r in results) / min(r['metrics']['total_cost'] for r in results)) - 1) * 100:.1f}% across the range",
                "Consider operational constraints when implementing changes"
            ]
        }
    
    def _generate_recommendations(self, parameters: dict, compliance_score: float) -> List[str]:
        """Generate recommendations based on simulation results"""
        recommendations = []
        
        if parameters.get("driver_count", 100) < 90:
            recommendations.append("Consider hiring additional drivers to improve coverage")
        
        if compliance_score < 95:
            recommendations.append("Review and adjust labor constraints to improve compliance")
        
        if parameters.get("overtime_rate", 15000) > 20000:
            recommendations.append("High overtime costs detected - optimize shift distribution")
        
        recommendations.append("Implement continuous monitoring of key metrics")
        
        return recommendations
    
    def _evaluate_tender_risks(self, requirements: dict) -> List[dict]:
        """Evaluate risks for a tender"""
        risks = []
        
        if requirements.get("services_required", 0) > 50:
            risks.append({
                "type": "capacity",
                "level": "high",
                "description": "Large scale operation may strain resources"
            })
        
        if requirements.get("sla_requirements", {}).get("on_time_performance", 0) > 95:
            risks.append({
                "type": "performance",
                "level": "medium",
                "description": "Strict SLA requirements may result in penalties"
            })
        
        risks.append({
            "type": "market",
            "level": "low",
            "description": "Fuel price fluctuations may impact profitability"
        })
        
        return risks