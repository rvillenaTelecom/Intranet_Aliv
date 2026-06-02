from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from functools import wraps
from werkzeug.security import check_password_hash
import subprocess
import os
import threading
import json
from datetime import datetime
try:
    import db_helper
except ImportError:
    from . import db_helper

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'AlivIntranet2026!')

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
    'admin': {
        'password_hash': 'scrypt:32768:8:1$laF1BDiVFlAPU7zZ$89fe55fc045e07cfa6b74ccee313cc6d3b5985c14e2969d7adcec3bc248facdbd9dab19d2b3cc955596cabd3c5d3b86146d6921068f864198de09bfb9d44dbcd',
        'role': 'admin',
        'name': 'Administrador'
    },
    'ventas': {
        'password_hash': 'scrypt:32768:8:1$l5kbEX1xYfm34mhG$3bff098e81d691e6e6445245eb1fcb4cf8a091497d2979ce4ac8014b4a9336c73db2c01fb43427a9bd72b63763e9ca1aec3fa5af0bd03d8b7534046e13da9db3',
        'role': 'ventas',
        'name': 'Equipo Ventas'
    },
    'operaciones': {
        'password_hash': 'scrypt:32768:8:1$DHNA7UTUjCJnC2nQ$97a877a4115a866d8e04f4798f8fb4ba391569a456fda5be0b71b6208baa5aa4452703318b34211ddc9b71b8af364fdd69e16ec9eb44a9285a56dba267653885',
        'role': 'operaciones',
        'name': 'Equipo Operaciones'
    },
    'tecnologia': {
        'password_hash': 'scrypt:32768:8:1$hITPuKEv1ptrDKaS$2e4f5789b8ec172397d9ce326b2ac9ebbe55ca2400a20ffe9dfb5d32ce7fa03d1359816d57cb9c72628a9c9c681946a2ba44612cd146743e49dd64f1bf9edb87',
        'role': 'tecnologia',
        'name': 'Equipo Tecnología'
    },
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
        if username in USERS and check_password_hash(USERS[username]['password_hash'], password):
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

@app.route('/dashboard-ventas')
@login_required
def dashboard_ventas():
    mes  = request.args.get('mes',  datetime.now().month, type=int)
    anio = request.args.get('anio', datetime.now().year,  type=int)

    meses = [
        {'id': 1, 'nombre': 'Enero'},    {'id': 2, 'nombre': 'Febrero'},
        {'id': 3, 'nombre': 'Marzo'},    {'id': 4, 'nombre': 'Abril'},
        {'id': 5, 'nombre': 'Mayo'},     {'id': 6, 'nombre': 'Junio'},
        {'id': 7, 'nombre': 'Julio'},    {'id': 8, 'nombre': 'Agosto'},
        {'id': 9, 'nombre': 'Septiembre'}, {'id': 10, 'nombre': 'Octubre'},
        {'id': 11, 'nombre': 'Noviembre'}, {'id': 12, 'nombre': 'Diciembre'},
    ]
    mes_nombre = next((m['nombre'] for m in meses if m['id'] == mes), '')

    kpi_lima   = db_helper.get_kpi_lima(mes, anio)
    kpi_prov   = db_helper.get_kpi_provincia(mes, anio)
    trend_lima = db_helper.get_daily_trend_lima(mes, anio)
    trend_prov = db_helper.get_daily_trend_provincia(mes, anio)
    top_dist   = db_helper.get_top_distritos_lima(mes, anio)
    tipo_vivienda = db_helper.get_tipo_vivienda_lima(mes, anio)
    dist_estados = db_helper.get_distribucion_estados_lima(mes, anio)
    pivot_planes = db_helper.get_pivot_planes_agencia(mes, anio)
    tabla_prov = db_helper.get_tabla_provincia(mes, anio)
    loc_lima   = db_helper.get_localizacion_lima(mes, anio)

    anios = list(range(2024, datetime.now().year + 2))

    return render_template('dashboard_ventas.html',
                           user=session['name'], role=session['role'],
                           mes_actual=mes, anio_actual=anio,
                           mes_nombre=mes_nombre, meses=meses, anios=anios,
                           kpi_lima=kpi_lima, kpi_prov=kpi_prov,
                           trend_lima=trend_lima,
                           trend_prov=trend_prov,
                           top_dist=top_dist,
                           tipo_vivienda=tipo_vivienda,
                           dist_estados=dist_estados,
                           pivot_planes=pivot_planes,
                           tabla_prov=tabla_prov,
                           loc_lima=loc_lima,
                           loc_zonas=loc_lima['zonas'] if loc_lima else [])

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



if __name__ == '__main__':
    # Usar el puerto que asigna Render o el 5001 por defecto
    port = int(os.environ.get("PORT", 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1']
    if os.environ.get('RENDER'):
        debug_mode = False
    app.run(debug=debug_mode, host='0.0.0.0', port=port)