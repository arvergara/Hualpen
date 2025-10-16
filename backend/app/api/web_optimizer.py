"""
API Web para el optimizador de turnos
Permite ejecutar optimize_plus.py desde una interfaz web
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
import asyncio
from typing import Optional, Dict
import uuid
import json

# Agregar el directorio backend al path
backend_dir = Path(__file__).parent.parent.parent
sys.path.append(str(backend_dir))

from app.services.excel_reader import ExcelTemplateReader
from app.services.output_generator import OutputGenerator
from app.services.html_report_generator import HTMLReportGenerator
from app.services.roster_optimizer_with_regimes import RosterOptimizerWithRegimes

app = FastAPI(title="Optimizador de Turnos Web", version="1.0.0")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorio para almacenar archivos temporales
UPLOAD_DIR = Path(tempfile.gettempdir()) / "optimizer_uploads"
RESULTS_DIR = Path(tempfile.gettempdir()) / "optimizer_results"
UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# Estado de las tareas en proceso
optimization_tasks: Dict[str, Dict] = {}


@app.get("/", response_class=HTMLResponse)
async def home():
    """Página principal con formulario de carga"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Optimizador de Turnos Hualpén</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container {
                background: white;
                border-radius: 10px;
                padding: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 30px;
            }
            .upload-form {
                border: 2px dashed #667eea;
                border-radius: 10px;
                padding: 40px;
                text-align: center;
                background: #f8f9fa;
            }
            input[type="file"] {
                display: none;
            }
            .file-label {
                display: inline-block;
                padding: 12px 30px;
                background: #667eea;
                color: white;
                border-radius: 5px;
                cursor: pointer;
                transition: all 0.3s;
            }
            .file-label:hover {
                background: #5a67d8;
                transform: translateY(-2px);
            }
            .file-name {
                margin-top: 20px;
                color: #666;
            }
            .form-group {
                margin: 20px 0;
                text-align: left;
            }
            label {
                display: block;
                margin-bottom: 5px;
                color: #555;
                font-weight: 500;
            }
            select, input[type="number"] {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 16px;
            }
            button {
                background: #48bb78;
                color: white;
                border: none;
                padding: 15px 40px;
                border-radius: 5px;
                font-size: 18px;
                cursor: pointer;
                margin-top: 20px;
                transition: all 0.3s;
            }
            button:hover {
                background: #38a169;
                transform: translateY(-2px);
            }
            button:disabled {
                background: #cbd5e0;
                cursor: not-allowed;
                transform: none;
            }
            .status {
                margin-top: 30px;
                padding: 20px;
                border-radius: 5px;
                display: none;
            }
            .status.processing {
                background: #bee3f8;
                color: #2c5282;
                display: block;
            }
            .status.success {
                background: #c6f6d5;
                color: #22543d;
                display: block;
            }
            .status.error {
                background: #fed7d7;
                color: #742a2a;
                display: block;
            }
            .progress-bar {
                width: 100%;
                height: 30px;
                background: #e2e8f0;
                border-radius: 15px;
                overflow: hidden;
                margin-top: 20px;
                display: none;
            }
            .progress-bar.active {
                display: block;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #667eea, #764ba2);
                width: 0%;
                transition: width 0.5s;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
            }
            .results {
                margin-top: 30px;
                display: none;
            }
            .results.show {
                display: block;
            }
            .result-link {
                display: inline-block;
                margin: 10px;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: all 0.3s;
            }
            .result-link:hover {
                background: #5a67d8;
                transform: translateY(-2px);
            }
            .info-box {
                background: #edf2f7;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .info-box h3 {
                margin-top: 0;
                color: #2d3748;
            }
            .info-box ul {
                margin: 10px 0;
                padding-left: 20px;
            }
            .info-box li {
                margin: 5px 0;
                color: #4a5568;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚌 Optimizador de Turnos Hualpén</h1>
            
            <div class="info-box">
                <h3>📋 Instrucciones</h3>
                <ul>
                    <li>Sube el archivo Excel con el template de turnos</li>
                    <li>Selecciona el cliente y período a optimizar</li>
                    <li>El sistema aplicará automáticamente las restricciones laborales según el tipo de servicio</li>
                    <li>Recibirás los resultados en formato Excel y HTML</li>
                </ul>
            </div>
            
            <form id="optimizerForm" enctype="multipart/form-data">
                <div class="upload-form">
                    <label for="file" class="file-label">
                        📁 Seleccionar archivo Excel
                    </label>
                    <input type="file" id="file" name="file" accept=".xlsx,.xls" required>
                    <div class="file-name" id="fileName">No se ha seleccionado archivo</div>
                </div>
                
                <div class="form-group">
                    <label for="client">Cliente:</label>
                    <select id="client" name="client" required disabled>
                        <option value="">Primero sube un archivo</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="year">Año:</label>
                    <input type="number" id="year" name="year" min="2024" max="2030" value="2025" required>
                </div>
                
                <div class="form-group">
                    <label for="month">Mes:</label>
                    <select id="month" name="month" required>
                        <option value="1">Enero</option>
                        <option value="2">Febrero</option>
                        <option value="3">Marzo</option>
                        <option value="4">Abril</option>
                        <option value="5">Mayo</option>
                        <option value="6">Junio</option>
                        <option value="7">Julio</option>
                        <option value="8">Agosto</option>
                        <option value="9" selected>Septiembre</option>
                        <option value="10">Octubre</option>
                        <option value="11">Noviembre</option>
                        <option value="12">Diciembre</option>
                    </select>
                </div>
                
                <button type="submit" id="submitBtn">🚀 Optimizar Turnos</button>
            </form>
            
            <div class="progress-bar" id="progressBar">
                <div class="progress-fill" id="progressFill">0%</div>
            </div>
            
            <div class="status" id="status"></div>
            
            <div class="results" id="results">
                <h2>📊 Resultados</h2>
                <div id="resultLinks"></div>
            </div>
        </div>
        
        <script>
            const form = document.getElementById('optimizerForm');
            const fileInput = document.getElementById('file');
            const fileName = document.getElementById('fileName');
            const clientSelect = document.getElementById('client');
            const submitBtn = document.getElementById('submitBtn');
            const status = document.getElementById('status');
            const progressBar = document.getElementById('progressBar');
            const progressFill = document.getElementById('progressFill');
            const results = document.getElementById('results');
            const resultLinks = document.getElementById('resultLinks');
            
            fileInput.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (file) {
                    fileName.textContent = `📄 ${file.name}`;
                    
                    // Cargar clientes disponibles
                    const formData = new FormData();
                    formData.append('file', file);
                    
                    try {
                        const response = await fetch('/api/get-clients', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (response.ok) {
                            const data = await response.json();
                            clientSelect.innerHTML = '<option value="">Selecciona un cliente</option>';
                            data.clients.forEach(client => {
                                const option = document.createElement('option');
                                option.value = client;
                                option.textContent = client;
                                clientSelect.appendChild(option);
                            });
                            clientSelect.disabled = false;
                        }
                    } catch (error) {
                        console.error('Error loading clients:', error);
                    }
                }
            });
            
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                // Validar que se haya seleccionado un archivo
                if (!fileInput.files[0]) {
                    alert('Por favor selecciona un archivo Excel');
                    return;
                }
                
                // Validar que se haya seleccionado un cliente
                if (!clientSelect.value) {
                    alert('Por favor selecciona un cliente');
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                formData.append('client', clientSelect.value);
                formData.append('year', document.getElementById('year').value);
                formData.append('month', document.getElementById('month').value);
                
                submitBtn.disabled = true;
                status.className = 'status processing';
                status.textContent = '⏳ Iniciando optimización...';
                progressBar.className = 'progress-bar active';
                results.className = 'results';
                
                try {
                    // Iniciar optimización
                    const response = await fetch('/api/optimize', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (!response.ok) {
                        throw new Error('Error en la optimización');
                    }
                    
                    const data = await response.json();
                    const taskId = data.task_id;
                    
                    // Monitorear progreso
                    let progress = 0;
                    const interval = setInterval(async () => {
                        try {
                            const statusResponse = await fetch(`/api/task-status/${taskId}`);
                            const statusData = await statusResponse.json();
                            
                            progress = statusData.progress || progress + 10;
                            progressFill.style.width = `${Math.min(progress, 100)}%`;
                            progressFill.textContent = `${Math.min(progress, 100)}%`;
                            
                            // Mostrar mensaje de estado si existe
                            if (statusData.message) {
                                status.innerHTML = `⏳ ${statusData.message}`;
                            }
                            
                            if (statusData.status === 'completed') {
                                clearInterval(interval);
                                progressFill.style.width = '100%';
                                progressFill.textContent = '100%';
                                
                                status.className = 'status success';
                                status.innerHTML = `
                                    <h3>✅ Optimización completada</h3>
                                    <p>Conductores utilizados: ${statusData.result.drivers_used}</p>
                                    <p>Costo total: $${statusData.result.total_cost.toLocaleString()}</p>
                                    <p>Tiempo de procesamiento: ${statusData.result.processing_time}s</p>
                                `;
                                
                                resultLinks.innerHTML = `
                                    <a href="/api/download/excel/${taskId}" class="result-link">
                                        📊 Descargar Excel
                                    </a>
                                    <a href="/api/download/html/${taskId}" class="result-link" target="_blank">
                                        📈 Ver Reporte HTML
                                    </a>
                                `;
                                results.className = 'results show';
                                
                            } else if (statusData.status === 'failed') {
                                clearInterval(interval);
                                throw new Error(statusData.error || 'Error en la optimización');
                            }
                        } catch (error) {
                            clearInterval(interval);
                            throw error;
                        }
                    }, 2000);
                    
                } catch (error) {
                    status.className = 'status error';
                    status.textContent = `❌ Error: ${error.message}`;
                    progressBar.className = 'progress-bar';
                } finally {
                    submitBtn.disabled = false;
                }
            });
        </script>
    </body>
    </html>
    """


@app.post("/api/get-clients")
async def get_clients(file: UploadFile = File(...)):
    """Obtiene la lista de clientes del archivo Excel"""
    try:
        # Guardar archivo temporal
        temp_path = UPLOAD_DIR / f"temp_{uuid.uuid4()}.xlsx"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Leer clientes
        reader = ExcelTemplateReader(str(temp_path))
        clients = reader.get_available_clients()
        
        # Limpiar archivo temporal
        os.remove(temp_path)
        
        return {"clients": clients}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/optimize")
async def optimize(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    client: str = Form(...),  # Hacer el cliente requerido
    year: int = Form(2025),
    month: int = Form(9)
):
    """Inicia el proceso de optimización"""
    try:
        # Generar ID único para la tarea
        task_id = str(uuid.uuid4())
        
        # Guardar archivo
        file_path = UPLOAD_DIR / f"{task_id}.xlsx"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Inicializar estado de la tarea
        optimization_tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "file_path": str(file_path),
            "client": client,
            "year": year,
            "month": month,
            "start_time": datetime.now().isoformat()
        }
        
        # Ejecutar optimización en background
        background_tasks.add_task(run_optimization, task_id)
        
        return {"task_id": task_id, "message": "Optimización iniciada"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def run_optimization(task_id: str):
    """Ejecuta el proceso de optimización"""
    try:
        print(f"[DEBUG] Iniciando optimización task_id={task_id}")
        task = optimization_tasks[task_id]
        print(f"[DEBUG] Task data: client={task.get('client')}, year={task.get('year')}, month={task.get('month')}")
        
        # Leer datos del Excel
        optimization_tasks[task_id]["progress"] = 10
        optimization_tasks[task_id]["message"] = "Leyendo archivo Excel..."
        print(f"[DEBUG] Progreso actualizado a 10%")
        
        # Validar que el cliente no sea None
        if not task["client"]:
            raise Exception("No se especificó un cliente")
        
        print(f"[DEBUG] Leyendo archivo: {task['file_path']}")
        reader = ExcelTemplateReader(task["file_path"])
        print(f"[DEBUG] ExcelTemplateReader creado")
        
        optimization_tasks[task_id]["progress"] = 15
        optimization_tasks[task_id]["message"] = f"Cargando datos del cliente {task['client']}..."
        
        client_data = reader.read_client_data(task["client"])
        
        if not client_data or not client_data.get('services'):
            raise Exception(f"No se encontraron datos para el cliente {task['client']}")
        
        # Detectar tipo de servicio
        optimization_tasks[task_id]["progress"] = 20
        optimization_tasks[task_id]["message"] = "Analizando tipos de servicio..."
        service_types = {}
        for service in client_data['services']:
            stype = service.get('service_type', 'Industrial')
            service_types[stype] = service_types.get(stype, 0) + 1
        
        # Ejecutar optimización
        optimization_tasks[task_id]["progress"] = 30
        optimization_tasks[task_id]["message"] = f"Optimizando {len(client_data['services'])} servicios..."
        
        # Crear optimizador con callback para actualizar progreso
        optimizer = RosterOptimizerWithRegimes(client_data)
        
        # Ejecutar optimización de forma más simple
        try:
            # Usar asyncio para no bloquear pero sin threads complicados
            solution = await asyncio.get_event_loop().run_in_executor(
                None, 
                optimizer.optimize_month, 
                task["year"], 
                task["month"]
            )
            
            # Actualizar progreso después de completar
            optimization_tasks[task_id]["progress"] = 75
            optimization_tasks[task_id]["message"] = "Optimización completada, generando reportes..."
            
        except Exception as opt_error:
            raise Exception(f"Error en optimización: {str(opt_error)}")
        
        optimization_tasks[task_id]["progress"] = 80
        
        if solution['status'] != 'success':
            raise Exception(f"Optimización fallida: {solution.get('message', 'Unknown error')}")
        
        # Generar reportes
        optimization_tasks[task_id]["progress"] = 90
        
        # Generar Excel
        output_gen = OutputGenerator(solution, task["client"])
        excel_path = RESULTS_DIR / f"{task_id}_result.xlsx"
        excel_output = output_gen.generate_excel_report(str(excel_path))
        
        # Generar HTML
        html_gen = HTMLReportGenerator(solution, task["client"])
        html_path = RESULTS_DIR / f"{task_id}_result.html"
        html_output = html_gen.generate_html_report(str(html_path))
        
        # Actualizar estado final
        optimization_tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "excel_path": str(excel_path),
            "html_path": str(html_path),
            "result": {
                "drivers_used": solution['metrics']['drivers_used'],
                "total_cost": solution['metrics']['total_cost'],
                "processing_time": round(
                    (datetime.now() - datetime.fromisoformat(task["start_time"])).total_seconds(), 
                    2
                )
            },
            "end_time": datetime.now().isoformat()
        })
        
    except Exception as e:
        optimization_tasks[task_id].update({
            "status": "failed",
            "error": str(e),
            "end_time": datetime.now().isoformat()
        })


@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    """Obtiene el estado de una tarea de optimización"""
    if task_id not in optimization_tasks:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    return optimization_tasks[task_id]


@app.get("/api/download/excel/{task_id}")
async def download_excel(task_id: str):
    """Descarga el resultado en Excel"""
    if task_id not in optimization_tasks:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task = optimization_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="La tarea no ha completado")
    
    if not os.path.exists(task["excel_path"]):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    return FileResponse(
        task["excel_path"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"roster_{task['client']}_{task['year']}_{task['month']}.xlsx"
    )


@app.get("/api/download/html/{task_id}")
async def download_html(task_id: str):
    """Descarga/muestra el resultado en HTML"""
    if task_id not in optimization_tasks:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task = optimization_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="La tarea no ha completado")
    
    if not os.path.exists(task["html_path"]):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    return FileResponse(
        task["html_path"],
        media_type="text/html",
        filename=f"roster_{task['client']}_{task['year']}_{task['month']}.html"
    )


@app.on_event("startup")
async def startup_event():
    """Limpia archivos temporales antiguos al iniciar"""
    # Limpiar archivos de más de 24 horas
    import time
    current_time = time.time()
    
    for dir_path in [UPLOAD_DIR, RESULTS_DIR]:
        for file_path in dir_path.glob("*"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > 86400:  # 24 horas
                    try:
                        file_path.unlink()
                    except:
                        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)