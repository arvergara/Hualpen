"""
Lector de archivos Excel para extraer servicios, turnos y parámetros de optimización
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
from datetime import datetime, time, timedelta
import re


class ExcelTemplateReader:
    """
    Lee el template de turnos Excel y extrae toda la información necesaria
    para la optimización
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.xl_file = pd.ExcelFile(file_path)
        
    def get_available_clients(self) -> List[str]:
        """Obtiene lista de clientes disponibles (hojas del Excel)"""
        # Filtrar hojas que no son clientes
        exclude = ['Criticidad Jornadas', 'Ejemplo']
        return [sheet for sheet in self.xl_file.sheet_names if sheet not in exclude]
    
    def read_client_data(self, sheet_name: str, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        Lee datos completos de un cliente específico

        Args:
            sheet_name: Nombre de la hoja (cliente)
            year: Año para expandir turnos (opcional)
            month: Mes para expandir turnos (opcional)

        Returns:
            Dict con:
            - parameters: Parámetros generales
            - optimization_criteria: Criterios de optimización
            - costs: Estructura de costos
            - services: Lista de servicios con sus turnos
        """
        df = pd.read_excel(self.file_path, sheet_name=sheet_name)

        # Encontrar las secciones principales
        parameters = self._extract_parameters(df)
        criteria = self._extract_optimization_criteria(df)
        costs = self._extract_costs(df)
        services = self._extract_services(df, sheet_name)

        # Extraer tipo de servicio (Industrial/Interurbano) de columna D
        service_type = self._extract_service_type(df)

        # Si se especifica año y mes, expandir turnos a días específicos
        if year is not None and month is not None:
            services = self._expand_shifts_to_month(services, year, month)

        return {
            'client_name': sheet_name,
            'service_type': service_type,  # Nuevo campo
            'parameters': parameters,
            'optimization_criteria': criteria,
            'costs': costs,
            'services': services
        }
    
    def _extract_parameters(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extrae parámetros generales del servicio"""
        params = {}
        
        # Buscar tiempos de preparación y cierre
        for idx, row in df.iterrows():
            row_str = str(row.values)
            if 'Tiempo de preparación' in row_str:
                # Extraer valor numérico
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)):
                        params['preparation_time_min'] = int(val)
                        break
            elif 'Tiempo de Cierre' in row_str:
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)):
                        params['closing_time_min'] = int(val)
                        break
            elif 'Permite multas' in row_str:
                params['allows_penalties'] = True
            elif 'Permite Horas Extra' in row_str:
                params['allows_overtime'] = True
            elif '% Conductores Respaldo' in row_str:
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)):
                        params['backup_drivers_percent'] = float(val)
                        break
        
        # Valores por defecto si no se encuentran
        params.setdefault('preparation_time_min', 30)
        params.setdefault('closing_time_min', 30)
        params.setdefault('allows_penalties', False)
        params.setdefault('allows_overtime', True)
        params.setdefault('backup_drivers_percent', 10)
        
        return params
    
    def _extract_optimization_criteria(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extrae criterios de optimización"""
        criteria = {
            'primary_objective': 'minimize_cost',
            'secondary_objectives': [],
            'constraints_priority': 'high'
        }
        
        for idx, row in df.iterrows():
            row_str = str(row.values)
            if 'Objetivo Primario' in row_str:
                if 'Minimizar Costo Total' in row_str:
                    criteria['primary_objective'] = 'minimize_cost'
                elif 'Minimizar Cantidad de Conductores' in row_str:
                    criteria['primary_objective'] = 'minimize_drivers'
                elif 'Cumplimiento Legal' in row_str:
                    criteria['primary_objective'] = 'legal_compliance'
        
        return criteria
    
    def _extract_costs(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extrae estructura de costos"""
        costs = {
            'full_time': {},
            'part_time_20h': {},
            'part_time_30h': {},
            'overtime_normal': 0,
            'overtime_holiday': 0
        }
        
        for idx, row in df.iterrows():
            row_str = str(row.values)
            
            # Buscar costos Full Time
            if 'Full Time' in row_str:
                # Extraer valores numéricos de la fila
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)) and val > 1000:
                        costs['full_time']['base_salary'] = float(val)
                        break
            
            # Buscar costos Part Time
            elif 'Par-Time (20h)' in row_str or 'Part-Time (20h)' in row_str:
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)) and val > 1000:
                        costs['part_time_20h']['base_salary'] = float(val)
                        break
            
            elif 'Par-Time (30h)' in row_str or 'Part-Time (30h)' in row_str:
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)) and val > 1000:
                        costs['part_time_30h']['base_salary'] = float(val)
                        break
            
            # Horas extra
            elif 'Hora Extra normal' in row_str:
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)) and val > 100:
                        costs['overtime_normal'] = float(val)
                        break
            
            elif 'Hora Extra festivo' in row_str:
                for val in row.values:
                    if pd.notna(val) and isinstance(val, (int, float)) and val > 100:
                        costs['overtime_holiday'] = float(val)
                        break
        
        # Valores por defecto si no se encuentran
        if not costs['full_time']:
            costs['full_time']['base_salary'] = 850000
        if not costs['part_time_20h']:
            costs['part_time_20h']['base_salary'] = 425000
        if not costs['part_time_30h']:
            costs['part_time_30h']['base_salary'] = 637500
        if costs['overtime_normal'] == 0:
            costs['overtime_normal'] = 15000
        if costs['overtime_holiday'] == 0:
            costs['overtime_holiday'] = 20000
            
        return costs
    
    def _extract_services(self, df: pd.DataFrame, sheet_name: str) -> List[Dict[str, Any]]:
        """Extrae lista de servicios con sus turnos"""
        
        # Ya no necesitamos manejo especial - toda la planilla tiene la misma estructura
        # if sheet_name in ['Andina', 'Watts']:
        #     return self._extract_services_andina_watts(df, sheet_name)
        
        services = []
        
        # Encontrar la fila que contiene "Nombre de Servicio"
        header_row = None
        for idx, row in df.iterrows():
            if 'Nombre de Servicio' in str(row.values):
                header_row = idx
                break
        
        if header_row is None:
            print(f"No se encontró sección de servicios en {sheet_name}")
            return services
        
        # Leer desde la fila de encabezados (leer hasta 200 filas para soportar clientes grandes)
        df_services = pd.read_excel(self.file_path, sheet_name=sheet_name,
                                   skiprows=header_row, nrows=200)
        
        # Procesar cada servicio
        for idx in range(1, len(df_services)):
            row = df_services.iloc[idx]
            
            # Verificar si hay datos en la fila
            if pd.isna(row.iloc[1]) or row.iloc[1] == 'Nombre de Servicio':
                continue
            
            group_value = row.iloc[0] if len(row) > 0 else None
            service_group = str(group_value).strip() if pd.notna(group_value) else None
            if not service_group:
                service_group = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else f"{sheet_name}_default_group"

            service = {
                'id': f"{sheet_name}_{idx}",
                'name': str(row.iloc[1]) if pd.notna(row.iloc[1]) else f"Servicio_{idx}",
                'vehicles': self._parse_vehicles(row.iloc[2]),
                'service_type': str(row.iloc[3]) if pd.notna(row.iloc[3]) else 'Industrial',
                'frequency': self._parse_frequency(row.iloc[4]),
                'shifts': self._extract_shifts(row),
                'client': sheet_name,
                'service_group': service_group
            }
            
            if service['shifts']:  # Solo agregar si tiene turnos válidos
                services.append(service)
        
        return services
    
    # MÉTODO ELIMINADO - Ya no necesario con estructura estandarizada
    # def _extract_services_andina_watts - REMOVIDO
    
    def _parse_vehicles(self, value) -> Dict[str, int]:
        """Parsea la información de vehículos requeridos"""
        if pd.isna(value):
            return {'quantity': 1, 'type': 'bus'}
        
        value_str = str(value).lower()
        
        # Extraer número de buses
        match = re.search(r'(\d+)\s*bus', value_str)
        if match:
            num_buses = int(match.group(1))
        else:
            num_buses = 1
        
        # Determinar tipo
        if 'minibus' in value_str:
            vehicle_type = 'minibus'
        elif 'van' in value_str:
            vehicle_type = 'van'
        else:
            vehicle_type = 'bus'
        
        return {
            'quantity': num_buses,
            'type': vehicle_type
        }
    
    def _parse_frequency(self, value) -> Dict[str, Any]:
        """Parsea la frecuencia del servicio"""
        if pd.isna(value):
            return {
                'type': 'daily',
                'days': [0, 1, 2, 3, 4, 5, 6],  # Todos los días
                'description': 'Todos los días'
            }
        
        value_str = str(value).lower().strip()
        
        # Mapeo de días
        day_map = {
            'lunes': 0, 'lun': 0, 'l': 0,
            'martes': 1, 'mar': 1, 'ma': 1,
            'miércoles': 2, 'miercoles': 2, 'mié': 2, 'mie': 2, 'mi': 2, 'x': 2,
            'jueves': 3, 'jue': 3, 'ju': 3, 'j': 3,
            'viernes': 4, 'vie': 4, 'vi': 4, 'v': 4,
            'sábado': 5, 'sabado': 5, 'sáb': 5, 'sab': 5, 'sa': 5, 's': 5,
            'domingo': 6, 'dom': 6, 'do': 6, 'd': 6
        }
        
        # Casos comunes
        if 'lunes a domingo' in value_str or 'l-d' in value_str or 'todos' in value_str:
            return {
                'type': 'daily',
                'days': [0, 1, 2, 3, 4, 5, 6],
                'description': 'Lunes a Domingo'
            }
        elif 'lunes a viernes' in value_str or 'l-v' in value_str:
            return {
                'type': 'weekdays',
                'days': [0, 1, 2, 3, 4],
                'description': 'Lunes a Viernes'
            }
        elif 'lunes a sábado' in value_str or 'lunes a sabado' in value_str or 'l-s' in value_str:
            return {
                'type': 'weekdays_saturday',
                'days': [0, 1, 2, 3, 4, 5],
                'description': 'Lunes a Sábado'
            }
        elif 'fin de semana' in value_str or 'fds' in value_str:
            return {
                'type': 'weekend',
                'days': [5, 6],  # Sábado y domingo
                'description': 'Fin de semana'
            }
        # Días específicos (ej: "martes a jueves", "lunes a martes")
        elif ' a ' in value_str or ' al ' in value_str or '-' in value_str:
            # Intentar parsear rango
            import re
            # Buscar patrón "día a día" o "día-día"
            pattern = r'(\w+)\s*(?:a|al|-)\s*(\w+)'
            match = re.search(pattern, value_str)
            if match:
                start_day = match.group(1).strip()
                end_day = match.group(2).strip()
                
                if start_day in day_map and end_day in day_map:
                    start_idx = day_map[start_day]
                    end_idx = day_map[end_day]
                    
                    # Generar lista de días
                    if end_idx >= start_idx:
                        days = list(range(start_idx, end_idx + 1))
                    else:
                        # Caso que cruza la semana (ej: viernes a lunes)
                        days = list(range(start_idx, 7)) + list(range(0, end_idx + 1))
                    
                    return {
                        'type': 'custom',
                        'days': days,
                        'description': value_str.title()
                    }
        # Día único (ej: "jueves", "martes")
        elif value_str in day_map:
            day_idx = day_map[value_str]
            return {
                'type': 'single_day',
                'days': [day_idx],
                'description': value_str.title()
            }
        
        # Si no se reconoce el patrón, asumir todos los días
        return {
            'type': 'daily',
            'days': [0, 1, 2, 3, 4, 5, 6],
            'description': value_str
        }
    
    def _extract_service_type(self, df: pd.DataFrame) -> str:
        """Extrae el tipo de servicio (Industrial/Interurbano) de la columna D"""
        # Buscar en columna D (índice 3) o columnas con palabras clave
        for idx, row in df.iterrows():
            if len(row) > 3:
                col_d_value = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ""
                if 'Industrial' in col_d_value:
                    return 'Industrial'
                elif 'Interurbano' in col_d_value:
                    return 'Interurbano'
        
        # Buscar en cualquier columna
        for col in df.columns:
            col_values = df[col].astype(str)
            if any('Industrial' in str(v) for v in col_values if pd.notna(v)):
                return 'Industrial'
            elif any('Interurbano' in str(v) for v in col_values if pd.notna(v)):
                return 'Interurbano'
        
        # Default
        return 'Industrial'  # Por defecto asumimos Industrial/Urbano
    
    def _extract_shifts(self, row) -> List[Dict[str, Any]]:
        """Extrae los turnos de un servicio (puede tener múltiples turnos)"""
        shifts = []
        
        # Los turnos empiezan en la columna 6 (índice 5) y van de a pares (inicio, fin)
        for i in range(5, len(row), 2):
            if i+1 < len(row):
                start_time = row.iloc[i]
                end_time = row.iloc[i+1]
                
                if pd.notna(start_time) and pd.notna(end_time):
                    shift = self._parse_shift_times(start_time, end_time, len(shifts) + 1)
                    if shift:
                        shifts.append(shift)
        
        return shifts
    
    def _parse_shift_times(self, start_time, end_time, shift_number: int) -> Dict[str, Any]:
        """Parsea los tiempos de un turno"""
        try:
            # Manejar diferentes tipos de datos que Excel puede devolver
            if pd.isna(start_time) or pd.isna(end_time):
                return None
            
            # Si es timedelta (Excel a veces interpreta horas como timedelta)
            if hasattr(start_time, 'total_seconds'):
                # Convertir timedelta a time
                total_seconds = int(start_time.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                start = datetime.strptime(f"{hours:02d}:{minutes:02d}", '%H:%M').time()
            elif isinstance(start_time, str):
                # Si es string, parsear normalmente
                if ':' in start_time:
                    parts = start_time.split(':')
                    if len(parts) == 3:
                        start = datetime.strptime(start_time, '%H:%M:%S').time()
                    else:
                        start = datetime.strptime(start_time, '%H:%M').time()
                else:
                    return None
            elif hasattr(start_time, 'hour'):
                # Si ya es un objeto time
                start = start_time
            else:
                return None
            
            # Mismo proceso para end_time
            if hasattr(end_time, 'total_seconds'):
                total_seconds = int(end_time.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                end = datetime.strptime(f"{hours:02d}:{minutes:02d}", '%H:%M').time()
            elif isinstance(end_time, str):
                if ':' in end_time:
                    parts = end_time.split(':')
                    if len(parts) == 3:
                        end = datetime.strptime(end_time, '%H:%M:%S').time()
                    else:
                        end = datetime.strptime(end_time, '%H:%M').time()
                else:
                    return None
            elif hasattr(end_time, 'hour'):
                end = end_time
            else:
                return None
            
            # Calcular duración
            start_dt = datetime.combine(datetime.today(), start)
            end_dt = datetime.combine(datetime.today(), end)
            
            # Si el turno cruza medianoche
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
            
            duration_hours = (end_dt - start_dt).total_seconds() / 3600
            
            # Determinar tipo de turno
            if start.hour < 6 or start.hour >= 22:
                shift_type = 'night'
            elif start.hour < 14:
                shift_type = 'morning'
            elif start.hour < 22:
                shift_type = 'afternoon'
            else:
                shift_type = 'night'
            
            return {
                'shift_number': shift_number,
                'start_time': start.strftime('%H:%M'),
                'end_time': end.strftime('%H:%M'),
                'duration_hours': round(duration_hours, 2),
                'shift_type': shift_type,
                'crosses_midnight': end_dt.day != start_dt.day
            }
            
        except Exception as e:
            print(f"Error parseando turno: {e}")
            return None

    def _expand_shifts_to_month(self, services: List[Dict], year: int, month: int) -> List[Dict]:
        """
        Expande los turnos plantilla a todos los días del mes según la frecuencia

        Args:
            services: Lista de servicios con turnos plantilla
            year: Año
            month: Mes (1-12)

        Returns:
            Lista de servicios con turnos expandidos por día
        """
        import calendar
        from datetime import date

        # Obtener días del mes
        num_days = calendar.monthrange(year, month)[1]

        # Procesar cada servicio
        expanded_services = []

        for service in services:
            frequency = service.get('frequency', {})
            days_of_week = frequency.get('days', [])  # [0, 1, 2, 3, 4] para Lunes-Viernes
            shift_templates = service.get('shifts', [])

            if not shift_templates:
                continue

            # Crear turnos expandidos
            expanded_shifts = []

            for day in range(1, num_days + 1):
                current_date = date(year, month, day)
                weekday = current_date.weekday()  # 0=Lunes, 6=Domingo

                # Verificar si este día aplica según frecuencia
                if weekday in days_of_week:
                    # Para cada plantilla de turno, crear un turno real para este día
                    for shift_template in shift_templates:
                        # Calcular start_minutes y end_minutes
                        start_time_str = shift_template['start_time']
                        end_time_str = shift_template['end_time']

                        start_parts = start_time_str.split(':')
                        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])

                        end_parts = end_time_str.split(':')
                        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])

                        # Si cruza medianoche, ajustar
                        if shift_template.get('crosses_midnight', False):
                            end_minutes += 1440  # Agregar 24 horas

                        expanded_shift = {
                            'date': current_date,
                            'start_time': shift_template['start_time'],
                            'end_time': shift_template['end_time'],
                            'start_minutes': start_minutes,
                            'end_minutes': end_minutes,
                            'duration_hours': shift_template['duration_hours'],
                            'shift_number': shift_template['shift_number'],
                            'shift_type': shift_template['shift_type'],
                            'service_id': service.get('id'),
                            'service_name': service.get('name'),
                            'service_type': service.get('service_type'),
                            'vehicle_type': service.get('vehicles', {}).get('type', 'bus'),
                            'crosses_midnight': shift_template.get('crosses_midnight', False)
                        }

                        expanded_shifts.append(expanded_shift)

            # Actualizar servicio con turnos expandidos
            if expanded_shifts:
                expanded_service = service.copy()
                expanded_service['shifts'] = expanded_shifts
                expanded_services.append(expanded_service)

        return expanded_services

    def generate_summary_report(self, client_data: Dict[str, Any]) -> str:
        """Genera un reporte resumen de los datos leídos"""
        report = []
        report.append(f"=== RESUMEN CLIENTE: {client_data['client_name']} ===\n")
        
        # Parámetros
        report.append("PARÁMETROS:")
        params = client_data['parameters']
        report.append(f"  - Tiempo preparación: {params.get('preparation_time_min', 0)} min")
        report.append(f"  - Tiempo cierre: {params.get('closing_time_min', 0)} min")
        report.append(f"  - Permite horas extra: {params.get('allows_overtime', False)}")
        report.append(f"  - % Conductores respaldo: {params.get('backup_drivers_percent', 0)}%\n")
        
        # Criterios de optimización
        report.append("CRITERIOS DE OPTIMIZACIÓN:")
        criteria = client_data['optimization_criteria']
        report.append(f"  - Objetivo primario: {criteria['primary_objective']}\n")
        
        # Costos
        report.append("ESTRUCTURA DE COSTOS:")
        costs = client_data['costs']
        if 'base_salary' in costs.get('full_time', {}):
            report.append(f"  - Full Time: ${costs['full_time']['base_salary']:,.0f}")
        report.append(f"  - Hora extra normal: ${costs['overtime_normal']:,.0f}")
        report.append(f"  - Hora extra festivo: ${costs['overtime_holiday']:,.0f}\n")
        
        # Servicios
        report.append(f"SERVICIOS ({len(client_data['services'])} total):")
        
        for service in client_data['services'][:5]:  # Mostrar primeros 5
            report.append(f"\n  {service['name']}:")
            report.append(f"    - Vehículos: {service['vehicles']['quantity']} {service['vehicles']['type']}")
            report.append(f"    - Frecuencia: {service['frequency']['description']}")
            report.append(f"    - Turnos: {len(service['shifts'])}")
            
            for shift in service['shifts']:
                report.append(f"      * Turno {shift['shift_number']}: {shift['start_time']} - {shift['end_time']} ({shift['duration_hours']}h)")
        
        if len(client_data['services']) > 5:
            report.append(f"\n  ... y {len(client_data['services']) - 5} servicios más")
        
        return '\n'.join(report)


# Función auxiliar para testing
def test_reader():
    """Función de prueba del lector"""
    file_path = '/Users/alfil/Mi unidad/Prototipo_Hualpen/nueva_info/Template TURNOS  Hualpén 08-09-2025.xlsx'
    
    reader = ExcelTemplateReader(file_path)
    
    # Obtener clientes disponibles
    clients = reader.get_available_clients()
    print(f"Clientes disponibles: {clients}\n")
    
    # Leer datos de Watts
    if 'Watts' in clients:
        watts_data = reader.read_client_data('Watts')
        report = reader.generate_summary_report(watts_data)
        print(report)
        
        return watts_data
    
    return None


if __name__ == "__main__":
    test_reader()
