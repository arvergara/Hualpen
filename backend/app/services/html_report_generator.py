"""
Generador de reportes HTML atractivos para los resultados de optimización
"""

from typing import Dict, Any
from datetime import datetime, timedelta
import calendar
import json
import os


class HTMLReportGenerator:
    """Genera reportes HTML interactivos y visualmente atractivos"""
    
    def __init__(self, solution: Dict[str, Any], client_name: str):
        self.solution = solution
        self.client_name = client_name
        self.assignments = solution.get('assignments', [])
        self.driver_summary = solution.get('driver_summary', {})
        self.metrics = solution.get('metrics', {})
        self.quality_metrics = solution.get('quality_metrics', {})
        self.timestamp = datetime.now()
    
    def generate_html_report(self, filename: str = None) -> str:
        """Genera el reporte HTML completo"""
        if filename is None:
            filename = f"roster_{self.client_name.replace(' ', '_')}_{self.timestamp.strftime('%Y%m%d_%H%M%S')}.html"
        
        html_content = self._generate_html()
        
        # Guardar archivo
        output_path = os.path.join(os.getcwd(), filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def _generate_html(self) -> str:
        """Genera el contenido HTML completo"""
        
        # Obtener datos del calendario
        if self.assignments:
            first_date = datetime.fromisoformat(min(a['date'] for a in self.assignments))
            year = first_date.year
            month = first_date.month
        else:
            year = datetime.now().year
            month = datetime.now().month
        
        month_name = calendar.month_name[month]
        
        # Preparar datos para gráficos
        driver_data = self._prepare_driver_chart_data()
        calendar_data = self._prepare_calendar_data(year, month)
        timeline_data = self._prepare_timeline_data()
        
        html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Optimización - {self.client_name}</title>
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <!-- Custom Styles -->
    <style>
        :root {{
            --primary-color: #2c3e50;
            --secondary-color: #3498db;
            --success-color: #27ae60;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
            --light-bg: #ecf0f1;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px 0;
        }}
        
        .main-container {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            margin: 0 auto;
            max-width: 1400px;
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            margin: 0;
            font-size: 2.5rem;
            font-weight: 300;
        }}
        
        .header .subtitle {{
            opacity: 0.9;
            margin-top: 10px;
        }}
        
        .metric-card {{
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
            margin-bottom: 20px;
        }}
        
        .metric-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }}
        
        .metric-value {{
            font-size: 2.5rem;
            font-weight: bold;
            color: var(--primary-color);
        }}
        
        .metric-label {{
            color: #7f8c8d;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .quality-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
        }}
        
        .quality-excellent {{
            background: var(--success-color);
            color: white;
        }}
        
        .quality-good {{
            background: #3498db;
            color: white;
        }}
        
        .quality-acceptable {{
            background: var(--warning-color);
            color: white;
        }}
        
        .quality-improvable {{
            background: var(--danger-color);
            color: white;
        }}
        
        .calendar-container {{
            overflow-x: auto;
        }}
        
        .calendar-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 2px;
        }}
        
        .calendar-table th {{
            background: var(--primary-color);
            color: white;
            padding: 10px;
            text-align: center;
            font-size: 0.9rem;
        }}
        
        .calendar-table td {{
            padding: 8px;
            text-align: center;
            background: #f8f9fa;
            border-radius: 5px;
            font-size: 0.85rem;
        }}
        
        .calendar-table .driver-name {{
            text-align: left;
            font-weight: bold;
            background: var(--light-bg);
        }}
        
        .work-day {{
            background: var(--success-color) !important;
            color: white;
            font-weight: bold;
        }}
        
        .sunday {{
            background: #ffe6e6 !important;
        }}
        
        .sunday.work-day {{
            background: #ff4444 !important;
            color: white !important;
            font-weight: bold;
        }}
        
        .saturday {{
            background: #e6f3ff !important;
        }}
        
        .saturday.work-day {{
            background: #4a90e2 !important;
            color: white !important;
            font-weight: bold;
        }}
        
        .chart-container {{
            position: relative;
            height: 400px;
            margin: 20px 0;
        }}
        
        .timeline-container {{
            overflow-x: auto;
            padding: 20px 0;
        }}
        
        .nav-tabs .nav-link {{
            color: var(--primary-color);
            border-radius: 10px 10px 0 0;
        }}
        
        .nav-tabs .nav-link.active {{
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
        }}
        
        .table-responsive {{
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .footer {{
            background: var(--light-bg);
            padding: 20px;
            text-align: center;
            color: #7f8c8d;
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            .main-container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="main-container">
        <!-- Header -->
        <div class="header">
            <h1><i class="fas fa-bus"></i> Reporte de Optimización de Turnos</h1>
            <div class="subtitle">
                <strong>{self.client_name}</strong> | {month_name} {year}
            </div>
            <div class="mt-3">
                <small>Generado: {self.timestamp.strftime('%d/%m/%Y %H:%M:%S')}</small>
            </div>
        </div>
        
        <!-- Content -->
        <div class="container-fluid p-4">
            
            <!-- Métricas Principales -->
            <div class="row mb-4">
                <div class="col-md-3">
                    <div class="metric-card text-center">
                        <i class="fas fa-users fa-2x mb-3" style="color: var(--secondary-color);"></i>
                        <div class="metric-value">{self.metrics.get('drivers_used', 0)}</div>
                        <div class="metric-label">Conductores</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="metric-card text-center">
                        <i class="fas fa-clock fa-2x mb-3" style="color: var(--warning-color);"></i>
                        <div class="metric-value">{self.metrics.get('total_hours', 0):.0f}</div>
                        <div class="metric-label">Horas Totales</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="metric-card text-center">
                        <i class="fas fa-dollar-sign fa-2x mb-3" style="color: var(--success-color);"></i>
                        <div class="metric-value">${self.metrics.get('total_cost', 0)/1000000:.1f}M</div>
                        <div class="metric-label">Costo Total</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="metric-card text-center">
                        <i class="fas fa-chart-line fa-2x mb-3" style="color: var(--danger-color);"></i>
                        <div class="metric-value">{self.quality_metrics.get('efficiency_metrics', {}).get('avg_utilization', 0):.1f}%</div>
                        <div class="metric-label">Utilización Promedio</div>
                    </div>
                </div>
            </div>
            
            <!-- Calidad de la Solución -->
            {self._generate_quality_section()}
            
            <!-- Tabs de Contenido -->
            <ul class="nav nav-tabs mb-4" id="reportTabs" role="tablist">
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="overview-tab" data-bs-toggle="tab" data-bs-target="#overview" type="button">
                        <i class="fas fa-chart-bar"></i> Resumen
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="calendar-tab" data-bs-toggle="tab" data-bs-target="#calendar" type="button">
                        <i class="fas fa-calendar-alt"></i> Calendario
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="drivers-tab" data-bs-toggle="tab" data-bs-target="#drivers" type="button">
                        <i class="fas fa-id-card"></i> Conductores
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="assignments-tab" data-bs-toggle="tab" data-bs-target="#assignments" type="button">
                        <i class="fas fa-list"></i> Asignaciones
                    </button>
                </li>
            </ul>
            
            <div class="tab-content" id="reportTabContent">
                <!-- Tab Resumen -->
                <div class="tab-pane fade show active" id="overview" role="tabpanel">
                    {self._generate_overview_tab(driver_data)}
                </div>
                
                <!-- Tab Calendario -->
                <div class="tab-pane fade" id="calendar" role="tabpanel">
                    {self._generate_calendar_tab(calendar_data, year, month)}
                </div>
                
                <!-- Tab Conductores -->
                <div class="tab-pane fade" id="drivers" role="tabpanel">
                    {self._generate_drivers_tab()}
                </div>
                
                <!-- Tab Asignaciones -->
                <div class="tab-pane fade" id="assignments" role="tabpanel">
                    {self._generate_assignments_tab()}
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p class="mb-0">
                <i class="fas fa-info-circle"></i> 
                Sistema de Optimización de Turnos - Hualpén
            </p>
            <small>Desarrollado con Python + OR-Tools</small>
        </div>
    </div>
    
    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    
    <!-- Charts -->
    <script>
        {self._generate_chart_scripts(driver_data)}
    </script>
</body>
</html>
"""
        return html
    
    def _generate_quality_section(self) -> str:
        """Genera la sección de calidad de la solución"""
        if not self.quality_metrics:
            return ""
        
        quality = self.quality_metrics.get('quality', 'DESCONOCIDA')
        ratio = self.quality_metrics.get('optimality_ratio', 0)
        
        # Determinar el color del badge
        if 'EXCELENTE' in quality:
            badge_class = 'quality-excellent'
        elif 'BUENA' in quality:
            badge_class = 'quality-good'
        elif 'ACEPTABLE' in quality:
            badge_class = 'quality-acceptable'
        else:
            badge_class = 'quality-improvable'
        
        return f"""
        <div class="row mb-4">
            <div class="col-12">
                <div class="metric-card">
                    <h5><i class="fas fa-medal"></i> Calidad de la Solución</h5>
                    <div class="mt-3">
                        <span class="quality-badge {badge_class}">{quality}</span>
                        <span class="ms-3">Ratio de Optimalidad: <strong>{ratio:.2f}</strong></span>
                        <span class="ms-3">Límite Teórico: <strong>{self.quality_metrics.get('theoretical_min_drivers', 0)} conductores</strong></span>
                    </div>
                </div>
            </div>
        </div>
        """
    
    def _generate_overview_tab(self, driver_data: Dict) -> str:
        """Genera el tab de resumen con gráficos"""
        return f"""
        <div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-chart-bar"></i> Distribución de Horas por Conductor</h5>
                        <div class="chart-container">
                            <canvas id="hoursChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-chart-pie"></i> Tipos de Contrato</h5>
                        <div class="chart-container">
                            <canvas id="contractChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-chart-line"></i> Utilización por Conductor</h5>
                        <div class="chart-container">
                            <canvas id="utilizationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
    
    def _generate_calendar_tab(self, calendar_data: Dict, year: int, month: int) -> str:
        """Genera el tab del calendario"""
        num_days = calendar.monthrange(year, month)[1]
        
        # Leyenda de colores
        html = """
        <div style="margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px;">
            <strong>Leyenda:</strong>
            <span style="display: inline-block; margin-left: 15px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #28a745; border-radius: 3px; vertical-align: middle;"></span> Día trabajado
            </span>
            <span style="display: inline-block; margin-left: 15px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #ff4444; border-radius: 3px; vertical-align: middle;"></span> Domingo trabajado
            </span>
            <span style="display: inline-block; margin-left: 15px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #4a90e2; border-radius: 3px; vertical-align: middle;"></span> Sábado trabajado
            </span>
            <span style="display: inline-block; margin-left: 15px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 3px; vertical-align: middle;"></span> Día libre
            </span>
        </div>
        <div class="calendar-container">
            <table class="calendar-table">
                <thead>
                    <tr>
                        <th>Conductor</th>
        """
        
        # Encabezados de días
        for day in range(1, num_days + 1):
            date = datetime(year, month, day)
            day_name = ['L', 'M', 'X', 'J', 'V', 'S', 'D'][date.weekday()]
            day_class = 'sunday' if date.weekday() == 6 else 'saturday' if date.weekday() == 5 else ''
            html += f'<th class="{day_class}">{day}<br><small>{day_name}</small></th>'
        
        html += '<th>Total</th></tr></thead><tbody>'
        
        # Filas de conductores - ordenar por ID numérico
        sorted_calendar = sorted(
            calendar_data.items(),
            key=lambda x: int(''.join(filter(str.isdigit, str(x[0]))) or '0')
        )
        for driver_id, driver_days in sorted_calendar:
            # Extraer solo el número del conductor
            driver_num = ''.join(filter(str.isdigit, str(driver_id))) or driver_id

            # Obtener patrón del conductor si existe
            pattern_text = ''
            if driver_id in self.driver_summary:
                pattern = self.driver_summary[driver_id].get('pattern', '')
                if pattern:
                    pattern_text = f' <span style="color: #0066cc; font-size: 0.85em;">({pattern})</span>'

            html += f'<tr><td class="driver-name">{driver_num}{pattern_text}</td>'
            
            total_days = 0
            for day in range(1, num_days + 1):
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                date_obj = datetime(year, month, day)
                
                cell_class = ''
                if date_obj.weekday() == 6:
                    cell_class = 'sunday'
                elif date_obj.weekday() == 5:
                    cell_class = 'saturday'
                
                if date_str in driver_days:
                    cell_class += ' work-day'
                    cell_content = '✓'
                    total_days += 1
                else:
                    cell_content = ''
                
                html += f'<td class="{cell_class}">{cell_content}</td>'
            
            html += f'<td><strong>{total_days}</strong></td></tr>'
        
        # Fila de totales
        html += '<tr><td class="driver-name">Total Conductores</td>'
        
        for day in range(1, num_days + 1):
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            count = sum(1 for driver_days in calendar_data.values() if date_str in driver_days)
            html += f'<td><strong>{count if count > 0 else ""}</strong></td>'
        
        html += '<td></td></tr></tbody></table></div>'
        
        return html
    
    def _generate_drivers_tab(self) -> str:
        """Genera el tab de conductores"""
        html = """
        <div class="table-responsive">
            <table class="table table-hover">
                <thead class="table-dark">
                    <tr>
                        <th>Conductor</th>
                        <th>Patrón</th>
                        <th>Tipo Contrato</th>
                        <th>Horas Trabajadas</th>
                        <th>Utilización</th>
                        <th>Días Trabajados</th>
                        <th>Domingos</th>
                        <th>Salario</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Ordenar por ID de conductor (numérico)
        sorted_drivers = sorted(
            self.driver_summary.items(),
            key=lambda x: int(''.join(filter(str.isdigit, str(x[0]))) or '0')
        )
        
        for driver_id, data in sorted_drivers:
            contract_badge = 'badge bg-primary' if data.get('contract_type') == 'full_time' else 'badge bg-secondary'
            utilization = data.get('utilization', 0)
            utilization_color = 'text-success' if utilization > 70 else 'text-warning' if utilization > 50 else 'text-danger'
            
            # Obtener el patrón del conductor
            pattern = data.get('pattern', 'Flexible')
            pattern_badge = 'badge bg-info' if 'FIJO' in pattern else 'badge bg-warning' if 'ROTATIVO' in pattern else ''
            
            html += f"""
                <tr>
                    <td><strong>{data.get('name', data.get('driver_name', driver_id))}</strong></td>
                    <td><span class="{pattern_badge}">{pattern}</span></td>
                    <td><span class="{contract_badge}">{data.get('contract_type', 'N/A')}</span></td>
                    <td>{data.get('total_hours', 0):.1f}h</td>
                    <td class="{utilization_color}">{utilization:.1f}%</td>
                    <td>{data.get('days_worked', 0)}</td>
                    <td>{data.get('sundays_worked', 0)}</td>
                    <td>${data.get('salary', 0):,.0f}</td>
                </tr>
            """
        
        html += """
                </tbody>
            </table>
        </div>
        """
        
        return html
    
    def _generate_assignments_tab(self) -> str:
        """Genera el tab de asignaciones detalladas"""
        html = """
        <div class="table-responsive">
            <table class="table table-sm table-striped">
                <thead class="table-dark">
                    <tr>
                        <th>Fecha</th>
                        <th>Día</th>
                        <th>Servicio</th>
                        <th>Turno</th>
                        <th>Vehículo / Tipo</th>
                        <th>Conductor</th>
                        <th>Patrón</th>
                        <th>Horario</th>
                        <th>Horas</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Ordenar asignaciones por fecha y hora
        sorted_assignments = sorted(
            self.assignments,
            key=lambda x: (x['date'], x.get('start_time', ''))
        )
        
        for assignment in sorted_assignments[:100]:  # Limitar a 100 para no sobrecargar
            date_obj = datetime.fromisoformat(assignment['date'])
            day_name = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][date_obj.weekday()]
            
            row_class = 'table-danger' if date_obj.weekday() == 6 else ''
            
            # Calcular horas si no están presentes
            duration = assignment.get('duration_hours', 0)
            if duration == 0 and assignment.get('start_time') and assignment.get('end_time'):
                try:
                    start = datetime.strptime(assignment['start_time'], '%H:%M')
                    end = datetime.strptime(assignment['end_time'], '%H:%M')
                    # Si el turno cruza la medianoche
                    if end < start:
                        delta = (end.hour + 24 - start.hour) + (end.minute - start.minute) / 60
                    else:
                        delta = (end.hour - start.hour) + (end.minute - start.minute) / 60
                    duration = round(delta, 1)
                except:
                    duration = 0
            
            # Obtener patrón del conductor
            driver_id = assignment.get('driver_id', '')
            pattern = ''
            if driver_id in self.driver_summary:
                pattern = self.driver_summary[driver_id].get('pattern', '')

            html += f"""
                <tr class="{row_class}">
                    <td>{date_obj.strftime('%d/%m/%Y')}</td>
                    <td>{day_name}</td>
                    <td>{assignment.get('service_name') or assignment.get('service', 'N/A')}</td>
                    <td>Turno {assignment.get('shift', assignment.get('shift_number', 'N/A'))}</td>
                    <td>{self._format_vehicle_label(assignment)}</td>
                    <td>{assignment.get('driver_name', 'N/A')}</td>
                    <td><span class="badge bg-info">{pattern or 'N/A'}</span></td>
                    <td>{assignment.get('start_time', '')} - {assignment.get('end_time', '')}</td>
                    <td>{duration:.1f}h</td>
                </tr>
            """
        
        if len(self.assignments) > 100:
            html += f"""
                <tr>
                    <td colspan="9" class="text-center text-muted">
                        ... y {len(self.assignments) - 100} asignaciones más
                    </td>
                </tr>
            """
        
        html += """
                </tbody>
            </table>
        </div>
        """
        
        return html

    def _format_vehicle_label(self, assignment: Dict[str, Any]) -> str:
        """Crea una etiqueta amigable con el tipo de vehículo"""
        vehicle_type = assignment.get('vehicle_type') or assignment.get('vehicle_category') or ''
        vehicle_value = assignment.get('vehicle')

        type_label = str(vehicle_type).strip()
        if type_label.lower() in {'', 'unknown', 'industrial', 'urbano', 'interurbano'}:
            type_label = ''
        else:
            type_label = type_label.replace('_', ' ').title()

        idx_label = ''
        if isinstance(vehicle_value, (int, float)):
            try:
                idx_label = f"#{int(vehicle_value) + 1}"
            except (TypeError, ValueError):
                idx_label = f"{vehicle_value}"
        elif vehicle_value:
            idx_label = str(vehicle_value).strip()

        parts = [part for part in [type_label, idx_label] if part]
        if parts:
            return ' '.join(parts)
        return 'Vehículo'
    
    def _prepare_driver_chart_data(self) -> Dict:
        """Prepara datos para los gráficos de conductores"""
        labels = []
        hours_data = []
        utilization_data = []
        colors = []
        
        # Ordenar por ID de conductor (numérico)
        sorted_drivers = sorted(
            self.driver_summary.items(),
            key=lambda x: int(''.join(filter(str.isdigit, str(x[0]))) or '0')
        )[:10]  # Top 10
        
        for driver_id, data in sorted_drivers:
            labels.append(data.get('name', driver_id))
            hours_data.append(data.get('total_hours', 0))
            utilization_data.append(data.get('utilization', 0))
            
            # Color según utilización
            util = data.get('utilization', 0)
            if util > 80:
                colors.append('rgba(39, 174, 96, 0.8)')  # Verde
            elif util > 60:
                colors.append('rgba(52, 152, 219, 0.8)')  # Azul
            elif util > 40:
                colors.append('rgba(243, 156, 18, 0.8)')  # Naranja
            else:
                colors.append('rgba(231, 76, 60, 0.8)')  # Rojo
        
        return {
            'labels': labels,
            'hours': hours_data,
            'utilization': utilization_data,
            'colors': colors
        }
    
    def _prepare_calendar_data(self, year: int, month: int) -> Dict:
        """Prepara datos del calendario"""
        calendar_data = {}
        
        for assignment in self.assignments:
            driver_id = assignment.get('driver_id')
            date = assignment.get('date')
            
            if driver_id not in calendar_data:
                calendar_data[driver_id] = set()
            
            calendar_data[driver_id].add(date)
        
        return calendar_data
    
    def _prepare_timeline_data(self) -> Dict:
        """Prepara datos para el timeline"""
        timeline = {}
        
        for assignment in self.assignments:
            date = assignment.get('date')
            if date not in timeline:
                timeline[date] = []
            
            timeline[date].append({
                'driver': assignment.get('driver_name'),
                'service': assignment.get('service_name') or assignment.get('service'),
                'start': assignment.get('start_time'),
                'end': assignment.get('end_time')
            })
        
        return timeline
    
    def _generate_chart_scripts(self, driver_data: Dict) -> str:
        """Genera los scripts para los gráficos"""
        
        # Contar tipos de contrato
        contract_counts = {'full_time': 0, 'part_time': 0}
        for data in self.driver_summary.values():
            if data.get('contract_type') == 'full_time':
                contract_counts['full_time'] += 1
            else:
                contract_counts['part_time'] += 1
        
        return f"""
        // Gráfico de Horas por Conductor
        const hoursCtx = document.getElementById('hoursChart');
        if (hoursCtx) {{
            new Chart(hoursCtx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(driver_data['labels'])},
                    datasets: [{{
                        label: 'Horas Trabajadas',
                        data: {json.dumps(driver_data['hours'])},
                        backgroundColor: {json.dumps(driver_data['colors'])},
                        borderColor: {json.dumps(driver_data['colors'])},
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            title: {{
                                display: true,
                                text: 'Horas'
                            }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            display: false
                        }}
                    }}
                }}
            }});
        }}
        
        // Gráfico de Tipos de Contrato
        const contractCtx = document.getElementById('contractChart');
        if (contractCtx) {{
            new Chart(contractCtx, {{
                type: 'doughnut',
                data: {{
                    labels: ['Full Time', 'Part Time'],
                    datasets: [{{
                        data: [{contract_counts['full_time']}, {contract_counts['part_time']}],
                        backgroundColor: [
                            'rgba(52, 152, 219, 0.8)',
                            'rgba(155, 89, 182, 0.8)'
                        ],
                        borderWidth: 2,
                        borderColor: '#fff'
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'bottom'
                        }}
                    }}
                }}
            }});
        }}
        
        // Gráfico de Utilización
        const utilizationCtx = document.getElementById('utilizationChart');
        if (utilizationCtx) {{
            new Chart(utilizationCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(driver_data['labels'])},
                    datasets: [{{
                        label: 'Utilización (%)',
                        data: {json.dumps(driver_data['utilization'])},
                        borderColor: 'rgba(52, 152, 219, 1)',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                        tension: 0.4,
                        fill: true
                    }}, {{
                        label: 'Objetivo (80%)',
                        data: Array({len(driver_data['labels'])}).fill(80),
                        borderColor: 'rgba(39, 174, 96, 0.5)',
                        borderDash: [5, 5],
                        fill: false
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            max: 100,
                            title: {{
                                display: true,
                                text: 'Utilización (%)'
                            }}
                        }}
                    }}
                }}
            }});
        }}
        """
