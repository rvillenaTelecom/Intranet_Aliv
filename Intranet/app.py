from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from functools import wraps
import subprocess
import os
import threading
import json
from datetime import datetime

from flask_apscheduler import APScheduler
import sqlalchemy as sa
import urllib

app = Flask(__name__)
app.secret_key = 'AlivIntranet2026!'

# --- CONFIGURACIÓN DEL PLANIFICADOR ---
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# --- VERIFICACIÓN DE PLAYWRIGHT PARA RENDER ---
def check_playwright():
    if os.environ.get('RENDER'):
        print("Entorno Render detectado. Asegurando que Playwright esté listo...")
        try:
            subprocess.run(['python', '-m', 'playwright', 'install', 'chromium'], check=True)
        except Exception as e:
            print(f"Aviso: Error instalando playwright en arranque: {e}")

check_playwright()

USERS = {
    'admin': {'password': 'Aliv2026', 'role': 'admin', 'name': 'Administrador'},
    'ventas': {'password': 'Ventas2026', 'role': 'ventas', 'name': 'Equipo Ventas'},
    'operaciones': {'password': 'Ops2026', 'role': 'operaciones', 'name': 'Equipo Operaciones'},
    'tecnologia': {'password': 'Tech2026', 'role': 'tecnologia', 'name': 'Equipo Tecnología'},
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def root():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').lower()
        password = request.form.get('password', '')
        if username in USERS and USERS[username]['password'] == password:
            session['user'] = username
            session['role'] = USERS[username]['role']
            session['name'] = USERS[username]['name']
            return redirect(url_for('home'))
        error = 'Usuario o contraseña incorrectos'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    return render_template('home.html', user=session['name'], role=session['role'])

@app.route('/herramientas')
@login_required
def herramientas():
    return render_template('herramientas.html', user=session['name'], role=session['role'])

@app.route('/dashboards')
@login_required
def dashboards():
    return render_template('dashboards.html', user=session['name'], role=session['role'])

@app.route('/ventas')
@login_required
def ventas():
    return render_template('ventas.html', user=session['name'], role=session['role'])

@app.route('/operaciones')
@login_required
def operaciones():
    return render_template('operaciones.html', user=session['name'], role=session['role'])

@app.route('/tecnologia')
@login_required
def tecnologia():
    return render_template('tecnologia.html', user=session['name'], role=session['role'])

# --- SECCIÓN DE AUTOMATIZACIÓN ---

# Ruta dinámica: funciona tanto en Windows como en Render (Linux)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_PATH = os.path.join(BASE_DIR, "Descargas_Rápidas")

@app.route('/automatizacion')
@login_required
def automatizacion():
    # Buscamos los últimos logs para mostrar el estado
    log_dir = os.path.join(BASE_PATH, "logs")
    recent_logs = []
    if os.path.exists(log_dir):
        files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True)
        recent_logs = files[:5]
        
    return render_template('automatizacion.html', 
                           user=session['name'], 
                           role=session['role'],
                           recent_logs=recent_logs)

@app.route('/api/run-task', methods=['POST'])
@login_required
def run_task():
    task_type = request.json.get('task')
    
    script_map = {
        'daily': ['python', 'run_pipeline.py', 'daily'],
        'full': ['python', 'run_pipeline.py', 'fase1'],
        'maestros': ['python', 'Cargar_Maestros_SQL.py']
    }
    
    if task_type not in script_map:
        return jsonify({'status': 'error', 'message': 'Tarea no reconocida'}), 400
        
    # Ejecutar en segundo plano para no bloquear la web
    def execute():
        try:
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            subprocess.run(script_map[task_type], cwd=BASE_PATH, env=env)
        except Exception as e:
            print(f"Error ejecutando {task_type}: {e}")

    thread = threading.Thread(target=execute)
    thread.start()
    
    return jsonify({'status': 'success', 'message': f'Tarea {task_type} iniciada correctamente'})

@app.route('/api/log-stream')
@login_required
def log_stream():
    # Ruta al último log generado
    log_dir = os.path.join(BASE_PATH, "logs")
    if not os.path.exists(log_dir):
        return jsonify({'content': 'No hay logs disponibles.'})
        
    files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
    if not files:
        return jsonify({'content': 'Esperando inicio de proceso...'})
        
    files.sort(key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True)
    latest_log = os.path.join(log_dir, files[0])
    
    try:
        with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Devolver las últimas 50 líneas para no saturar
            lines = content.splitlines()
            return jsonify({'content': '\n'.join(lines[-50:]), 'filename': files[0]})
    except Exception as e:
        return jsonify({'content': f'Error leyendo log: {e}'})

# --- FUNCIONES DEL PLANIFICADOR ---

def job_daily_update():
    """Función que ejecuta el scheduler."""
    print(f"[{datetime.now()}] Iniciando actualización programada...")
    try:
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        subprocess.run(['python', 'run_pipeline.py', 'daily'], cwd=BASE_PATH, env=env)
    except Exception as e:
        print(f"Error en tarea programada: {e}")

@app.route('/api/scheduler/status')
@login_required
def get_scheduler_status():
    jobs = scheduler.get_jobs()
    active = any(job.id == 'daily_update_job' for job in jobs)
    
    next_run = "N/A"
    if active:
        job = scheduler.get_job('daily_update_job')
        next_run = job.next_run_time.strftime('%H:%M:%S') if job.next_run_time else "N/A"
        
    return jsonify({
        'active': active,
        'next_run': next_run
    })

@app.route('/api/scheduler/toggle', methods=['POST'])
@login_required
def toggle_scheduler():
    active = request.json.get('active')
    
    if active:
        # Si no existe el trabajo, lo creamos (Exactamente al minuto 45 de cada hora)
        if not scheduler.get_job('daily_update_job'):
            scheduler.add_job(id='daily_update_job', func=job_daily_update, trigger='cron', minute=45)
            return jsonify({'status': 'success', 'message': 'Programación activada (Minuto 45 de cada hora)'})
    else:
        # Si existe, lo removemos
        if scheduler.get_job('daily_update_job'):
            scheduler.remove_job('daily_update_job')
            return jsonify({'status': 'success', 'message': 'Programación desactivada'})
            
    return jsonify({'status': 'no_change'})

if __name__ == '__main__':
    # Usar el puerto que asigna Render o el 5001 por defecto
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host='0.0.0.0', port=port)