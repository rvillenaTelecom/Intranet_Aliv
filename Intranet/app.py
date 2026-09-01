from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, redirect, url_for, session, request, jsonify, Response, stream_with_context, flash
from functools import wraps
from werkzeug.security import check_password_hash
from flask_apscheduler import APScheduler
import subprocess
import os
import sys
import threading
import queue
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import db_helper
except ImportError:
    from . import db_helper

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'AlivIntranet2026!')

# --- PIPELINE: paths y estado global ---
_INTRANET_DIR  = os.path.dirname(os.path.abspath(__file__))
_PIPELINE_DIR  = os.path.join(os.path.dirname(_INTRANET_DIR), 'Pipeline')
_PIPELINE_SCRIPT = os.path.join(_PIPELINE_DIR, 'run_pipeline.py')
_FASES_VALIDAS = {'bd', 'daily', 'consolidar', 'actualizar_ventas', 'subida_aliv', 'subida_referidos', 'reporte_diario', 'reporte_gerente', 'reporte_nocturno', 'reporte_proyeccion'}
# Render no tiene Playwright/Chromium instalado (Intranet/requirements.txt no
# los incluye a propósito) -- el pipeline de scraping solo puede correr desde
# la PC local. Render define RENDER=true automáticamente en su entorno.
IS_RENDER = bool(os.environ.get('RENDER'))

_pipeline_running = False
_pipeline_proc    = None
_pipeline_log     = []   # [(tipo, dato), ...] del run actual


def _ejecutar_fase_bg(fase):
    """Lanza run_pipeline.py <fase> en background. Usado tanto por el boton
    'Ejecutar' de /pipeline como por los jobs programados de APScheduler,
    para que compartan el mismo candado (_pipeline_running) y no se pisen."""
    global _pipeline_running, _pipeline_proc, _pipeline_log

    if _pipeline_running:
        print(f"[Scheduler] Se omite '{fase}': ya hay un proceso de pipeline en ejecucion.")
        return False

    _pipeline_log = []
    _pipeline_running = True

    def _run():
        global _pipeline_running, _pipeline_proc
        try:
            args = [sys.executable, _PIPELINE_SCRIPT]
            if fase != 'bd':
                args.append(fase)
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=_PIPELINE_DIR,
            )
            _pipeline_proc = proc
            for line in proc.stdout:
                _pipeline_log.append(('line', line.rstrip()))
            proc.wait()
            _pipeline_log.append(('done', proc.returncode))
        except Exception as exc:
            _pipeline_log.append(('error', str(exc)))
            _pipeline_log.append(('done', 1))
        finally:
            _pipeline_running = False
            _pipeline_proc = None

    threading.Thread(target=_run, daemon=True).start()
    return True


# --- SCHEDULER INTERNO: reemplaza las tareas de Windows Task Scheduler ---
# (Aliv_SoloesMes, Aliv_ReporteDiario, Aliv_Todo2026 -- mismos horarios)
class _SchedulerConfig:
    SCHEDULER_API_ENABLED = False

app.config.from_object(_SchedulerConfig())
scheduler = APScheduler()
scheduler.init_app(app)


@scheduler.task('cron', id='job_solo_este_mes', hour='*', minute=0)
def _job_solo_este_mes():
    """Cada hora en punto -- sube directo a Azure SQL (aliv-server-2), la que lee Render.
    Antes era cada 15 min; se bajó a cada hora para no consumir tanto compute de Azure."""
    _ejecutar_fase_bg('daily')


@scheduler.task('cron', id='job_subida_aliv', hour=9, minute=0)
def _job_subida_aliv():
    """Ventas Win Activas del Sistema Aliv -- 9:00am diario."""
    _ejecutar_fase_bg('subida_aliv')


@scheduler.task('cron', id='job_subida_referidos', hour=9, minute=5)
def _job_subida_referidos():
    """Ventas Win Referidos del Sistema Aliv -- 9:05am diario (5 min después de Subida Aliv para no pisarse)."""
    _ejecutar_fase_bg('subida_referidos')


@scheduler.task('cron', id='job_reporte_diario', hour=10, minute=0)
def _job_reporte_diario():
    """Antes: tarea 'Aliv_ReporteDiario' -- 10:00am diario."""
    _ejecutar_fase_bg('reporte_diario')


@scheduler.task('cron', id='job_todo_2026', day=1, hour=2, minute=0)
def _job_todo_2026():
    """Antes: tarea 'Aliv_Todo2026' -- dia 1 de cada mes, 2:00am."""
    _ejecutar_fase_bg('bd')

_dashboard_cache = {}
_CACHE_TTL = 300  # 5 minutos


def _cache_get(key):
    entry = _dashboard_cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key, data):
    _dashboard_cache[key] = (time.time(), data)

try:
    db_helper.init_dim_usuarios_table()
except Exception as _e:
    print(f"init dim_usuarios: {_e}")


def _auto_download_lima_geo():
    """Descarga límites distritales Lima/Callao desde GADM en background al arrancar."""
    import json
    import urllib.request
    path = os.path.join(_INTRANET_DIR, 'static', 'lima_distritos.geojson')
    if os.path.exists(path):
        return
    try:
        print("[Lima Geo] Descargando límites distritales desde GADM (~20 MB)…")
        url = 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_3.json'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        # NAME_1='LimaProvince' = Lima Metropolitana (43 distritos)
        # NAME_1='Callao' = Callao (Callao + Ventanilla en GADM 4.1)
        features = [f for f in data.get('features', [])
                    if f.get('properties', {}).get('NAME_1', '') in ('LimaProvince', 'Callao')]

        def _simplify(ring, max_pts=300):
            if len(ring) <= max_pts:
                return ring
            step = max(1, len(ring) // max_pts)
            out = ring[::step]
            if out[-1] != ring[-1]:
                out = list(out) + [ring[-1]]
            return out

        for feat in features:
            g = feat['geometry']
            if g['type'] == 'Polygon':
                g['coordinates'] = [_simplify(r) for r in g['coordinates']]
            elif g['type'] == 'MultiPolygon':
                g['coordinates'] = [[_simplify(r) for r in p] for p in g['coordinates']]

        out = {'type': 'FeatureCollection', 'features': features}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
        print(f"[Lima Geo] Guardado ({os.path.getsize(path)//1024} KB) — recarga el mapa.")
    except Exception as e:
        print(f"[Lima Geo] Error: {e}")


threading.Thread(target=_auto_download_lima_geo, daemon=True).start()

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
    'vertical': {
        'password_hash': 'scrypt:32768:8:1$Vz8lDPriB3iglgsF$39624d66226d07973daa855cbf6d20e9ef2ca45e935f0f94f0c69e61f2b1aafc9c72739d6ced2110c1a7962b21500a72859ef1f9c197015b9f2272dc05dab2d0',
        'role': 'vertical',
        'name': 'Gerente Vertical'
    },
    'horizontal_sub': {
        'password_hash': 'scrypt:32768:8:1$kBeU1J3IK0tgZqDl$9947a8f448b3816e598dc8fde55e9cc11e4c47db990015fa96198ce2b46990d9f248562075f6a2cb2a9c107d52be8c6a3590d04c19d22e85d359a7c5f7a11adc',
        'role': 'horizontal_sub',
        'name': 'Gerente Horizontal Sub'
    },
    'horizontal_aliv': {
        'password_hash': 'scrypt:32768:8:1$GqSd3NHdzQYqt10a$99ab34c7f46a02f53115c1fab0c5e097a867b30dc156f01a836dfec039a9bb19c45f61156a698dc0a98b9400e1d23667523c6ae45f51715fb9f55ae8d2eca757',
        'role': 'horizontal_aliv',
        'name': 'Gerente Horizontal Aliv'
    },
    'ejecutivo': {
        'password_hash': 'scrypt:32768:8:1$I8oJX7olYzbQqfbN$274e1e7f8408a2365c26e9cda1d98f003d4f43b34655174e805870c6b14efce8421ed69495aad25da366b67fd067ffaaf8aed55657bc29b70475f55bfc268760',
        'role': 'ejecutivo',
        'name': 'Gerente Ejecutivo'
    },
}

# Roles con acceso restringido a un único dashboard/área — el filtro se fuerza
# en el servidor (no solo se oculta en el HTML) para que no puedan verse entre sí
# cambiando la URL a mano.
ROLE_SCOPE = {
    'vertical':        {'home': 'dashboard_ventas', 'area': 'Vertical',   'agencia': ''},
    'horizontal_sub':  {'home': 'dashboard_ventas', 'area': 'Horizontal', 'agencia': 'Sub'},
    'horizontal_aliv': {'home': 'dashboard_ventas', 'area': 'Horizontal', 'agencia': 'Aliv'},
    'ejecutivo':       {'home': 'reporte_gerente'},
}

_LOCKED_ROLE_ALLOWED_ENDPOINTS = {
    'static', 'login', 'logout', 'root',
    'dashboard_ventas', 'reporte_gerente',
    'lima_distritos_geo', 'api_chat',
}
# resumen-tabla/proyeccion-cierre devuelven el consolidado Vertical+Horizontal
# (para el toggle interno de Ejecutivo) — no deben quedar accesibles por URL
# directa para los roles bloqueados a una sola área.
_ROLE_EXTRA_ENDPOINTS = {
    'ejecutivo': {'api_resumen_tabla', 'api_proyeccion_cierre'},
}

@app.before_request
def _enforce_locked_role_scope():
    role = session.get('role')
    if role not in ROLE_SCOPE:
        return
    allowed = _LOCKED_ROLE_ALLOWED_ENDPOINTS | _ROLE_EXTRA_ENDPOINTS.get(role, set())
    if request.endpoint not in allowed:
        scope = ROLE_SCOPE[role]
        return redirect(url_for(scope['home'], **{k: v for k, v in scope.items() if k != 'home' and v}))


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
            scope = ROLE_SCOPE.get(session['role'])
            if scope:
                params = {k: v for k, v in scope.items() if k != 'home' and v}
                return redirect(url_for(scope['home'], **params))
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
    from datetime import timedelta
    mes       = request.args.get('mes',  datetime.now().month, type=int)
    anio      = request.args.get('anio', datetime.now().year,  type=int)
    _scope    = ROLE_SCOPE.get(session['role'])
    if _scope and _scope['home'] != 'dashboard_ventas':
        return redirect(url_for(_scope['home']))
    if _scope:
        area    = _scope['area']
        agencia = _scope['agencia']
    else:
        area      = request.args.get('area', '')
        _agencia  = request.args.get('agencia', '')
        agencia   = _agencia if _agencia in ('Aliv', 'Sub') else ''
    _dia      = request.args.get('dia', 0, type=int)
    dia       = _dia if _dia and 1 <= _dia <= 31 else None
    _base     = request.args.get('base', 30, type=int)
    base_dias = _base if _base in range(25, 32) else 30

    meses = [
        {'id': 1, 'nombre': 'Enero'},    {'id': 2, 'nombre': 'Febrero'},
        {'id': 3, 'nombre': 'Marzo'},    {'id': 4, 'nombre': 'Abril'},
        {'id': 5, 'nombre': 'Mayo'},     {'id': 6, 'nombre': 'Junio'},
        {'id': 7, 'nombre': 'Julio'},    {'id': 8, 'nombre': 'Agosto'},
        {'id': 9, 'nombre': 'Septiembre'}, {'id': 10, 'nombre': 'Octubre'},
        {'id': 11, 'nombre': 'Noviembre'}, {'id': 12, 'nombre': 'Diciembre'},
    ]
    mes_nombre = next((m['nombre'] for m in meses if m['id'] == mes), '')

    anios = list(range(2024, datetime.now().year + 2))

    cache_key = (mes, anio, area, agencia, dia, base_dias)
    db_data = _cache_get(cache_key)

    if db_data is None:
        _queries = {
            'kpi_lima':       lambda: db_helper.get_kpi_lima(mes, anio, area=area, dia=dia, cumul=True, base_dias=base_dias, agencia_grupo=agencia),
            'trend_lima':     lambda: db_helper.get_daily_trend_lima(mes, anio, area=area),
            'top_dist':       lambda: db_helper.get_top_distritos_lima(mes, anio, area=area, dia=dia),
            'dist_estados':   lambda: db_helper.get_distribucion_estados_lima(mes, anio, area=area, dia=dia),
            'vel_planes':     lambda: db_helper.get_velocidad_planes_lima(mes, anio, area=area, dia=dia),
            'loc_lima':       lambda: db_helper.get_localizacion_lima(mes, anio, area=area),
            'puntos_mapa':    lambda: db_helper.get_puntos_mapa_lima(mes, anio, area=area),
        }
        if area == 'Vertical':
            _queries['pivot_agencia'] = lambda: db_helper.get_pivot_subagencias_lima(mes, anio, dia=dia)
            _fecha_ayer = datetime.now() - timedelta(days=1)
            _queries['pivot_agencia_cierre'] = lambda: db_helper.get_pivot_subagencias_lima(
                _fecha_ayer.month, _fecha_ayer.year, dia=_fecha_ayer.day, cumul=False)
        db_data = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fn): name for name, fn in _queries.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    db_data[name] = future.result()
                except Exception as e:
                    print(f"[dashboard] {name}: {e}")
                    db_data[name] = None
        _cache_set(cache_key, db_data)

    loc_lima = db_data.get('loc_lima')
    fecha_cierre = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
    return render_template('dashboard_ventas.html',
                           user=session['name'], role=session['role'],
                           mes_actual=mes, anio_actual=anio,
                           mes_nombre=mes_nombre, meses=meses, anios=anios,
                           area=area, agencia=agencia, dia_actual=dia or 0, base_dias=base_dias,
                           fecha_cierre=fecha_cierre,
                           pivot_agencia_cierre=db_data.get('pivot_agencia_cierre'),
                           kpi_lima=db_data.get('kpi_lima'),
                           trend_lima=db_data.get('trend_lima'),
                           top_dist=db_data.get('top_dist'),
                           dist_estados=db_data.get('dist_estados'),
                           vel_planes=db_data.get('vel_planes'),
                           loc_lima=loc_lima,
                           loc_zonas=loc_lima['zonas'] if loc_lima else [],
                           puntos_mapa=db_data.get('puntos_mapa'),
                           pivot_agencia=db_data.get('pivot_agencia'))

@app.route('/ventas')
@login_required
def ventas():
    hoy = datetime.now()
    cache_key = ('equipo_ventas_kpis', hoy.month, hoy.year)
    kpis = _cache_get(cache_key)
    if kpis is None:
        try:
            kpis = db_helper.get_equipo_ventas_kpis(hoy.month, hoy.year)
        except Exception as e:
            print(f"[ventas] get_equipo_ventas_kpis: {e}")
            kpis = None
        _cache_set(cache_key, kpis)

    cuotas_key = ('cuotas_lima_historial', hoy.year)
    cuotas_historial = _cache_get(cuotas_key)
    if cuotas_historial is None:
        try:
            cuotas_historial = db_helper.get_cuotas_lima_historial(hoy.year)
        except Exception as e:
            print(f"[ventas] get_cuotas_lima_historial: {e}")
            cuotas_historial = []
        _cache_set(cuotas_key, cuotas_historial)

    return render_template('ventas.html', user=session['name'], role=session['role'],
                           kpis=kpis, cuotas_historial=cuotas_historial, anio_actual=hoy.year)


@app.route('/ventas/cuota', methods=['POST'])
@login_required
def ventas_cuota_guardar():
    if session.get('role') != 'admin':
        return jsonify({'ok': False, 'error': 'Solo el administrador puede modificar cuotas.'}), 403
    data = request.get_json(silent=True) or {}
    try:
        mes = int(data.get('mes'))
        vertical = int(data.get('vertical'))
        horizontal = int(data.get('horizontal'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Mes, vertical y horizontal deben ser números enteros.'}), 400
    if vertical < 0 or horizontal < 0:
        return jsonify({'ok': False, 'error': 'Los valores no pueden ser negativos.'}), 400
    try:
        resultado = db_helper.set_cuota_lima(mes, vertical, horizontal)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"[ventas_cuota_guardar] {e}")
        return jsonify({'ok': False, 'error': 'No se pudo guardar la cuota.'}), 500

    _dashboard_cache.clear()
    return jsonify({'ok': True, 'cuota': resultado})

@app.route('/operaciones')
@login_required
def operaciones():
    return render_template('operaciones.html', user=session['name'], role=session['role'])

@app.route('/tecnologia')
@login_required
def tecnologia():
    return render_template('tecnologia.html', user=session['name'], role=session['role'])


@app.route('/usuarios')
@login_required
def usuarios():
    filters = {
        'search':     request.args.get('search', ''),
        'agencia':    request.args.get('agencia', ''),
        'supervisor': request.args.get('supervisor', ''),
        'cargo':      request.args.get('cargo', ''),
        'estado':     request.args.get('estado', ''),
    }
    return render_template(
        'usuarios.html',
        user=session['name'], role=session['role'],
        usuarios=db_helper.get_usuarios(**filters),
        stats=db_helper.get_usuarios_stats(),
        agencias=db_helper.get_agencias_list(),
        supervisores=db_helper.get_supervisores_list(),
        cargos=['Vendedor', 'Supervisor', 'Jefe de Agencia', 'Coordinador', 'Admin'],
        filters=filters,
    )


@app.route('/usuarios/guardar', methods=['POST'])
@login_required
def guardar_usuario():
    if session.get('role') != 'admin':
        flash('Sin permisos para realizar esta acción.', 'error')
        return redirect(url_for('usuarios'))
    data = {
        'vendedor':        request.form.get('vendedor', '').strip(),
        'nombre_aliv':     request.form.get('nombre_aliv', '').strip(),
        'cargo':           request.form.get('cargo', 'Vendedor'),
        'agencia':         request.form.get('agencia', '').strip(),
        'supervisor':      request.form.get('supervisor', '').strip(),
        'canal':           request.form.get('canal', ''),
        'estado':          request.form.get('estado', 'Activo'),
    }
    uid = request.form.get('id', '').strip()
    if uid:
        ok = db_helper.update_usuario(int(uid), data)
        flash(f"Usuario «{data['vendedor']}» actualizado correctamente." if ok else 'Error al actualizar. Revisa la consola del servidor.', 'success' if ok else 'error')
    else:
        ok = db_helper.create_usuario(data)
        flash(f"Usuario «{data['vendedor']}» creado y guardado en la base de datos." if ok else 'Error al crear el usuario. Revisa la consola del servidor.', 'success' if ok else 'error')
    return redirect(url_for('usuarios'))


@app.route('/usuarios/eliminar/<int:uid>', methods=['POST'])
@login_required
def eliminar_usuario(uid):
    if session.get('role') != 'admin':
        flash('Sin permisos para realizar esta acción.', 'error')
        return redirect(url_for('usuarios'))
    ok = db_helper.delete_usuario(uid)
    flash('Usuario eliminado de la base de datos.' if ok else 'Error al eliminar. Revisa la consola del servidor.', 'success' if ok else 'error')
    return redirect(url_for('usuarios'))


@app.route('/pipeline')
@login_required
def pipeline():
    return render_template('pipeline.html',
                           user=session['name'], role=session['role'],
                           corriendo=_pipeline_running, is_render=IS_RENDER)


@app.route('/pipeline/ejecutar', methods=['POST'])
@login_required
def pipeline_ejecutar():
    if session.get('role') != 'admin':
        return jsonify({'ok': False, 'error': 'Sin permisos de administrador'}), 403
    if IS_RENDER:
        return jsonify({'ok': False, 'error': 'El pipeline no puede correr en Render (falta Playwright/Chromium) — ejecútalo desde tu PC local.'}), 400
    if _pipeline_running:
        return jsonify({'ok': False, 'error': 'Ya hay un proceso en ejecución'}), 409

    fase = request.form.get('fase', '').strip()
    if fase not in _FASES_VALIDAS:
        return jsonify({'ok': False, 'error': 'Fase inválida'}), 400

    _ejecutar_fase_bg(fase)
    return jsonify({'ok': True})


@app.route('/pipeline/stream')
@login_required
def pipeline_stream():
    def _generate():
        idx = 0
        last_ping = time.time()
        while True:
            while idx < len(_pipeline_log):
                tipo, dato = _pipeline_log[idx]
                idx += 1
                if tipo == 'line':
                    yield f'data: {json.dumps({"t":"l","v":dato})}\n\n'
                elif tipo == 'done':
                    yield f'data: {json.dumps({"t":"done","code":dato})}\n\n'
                    return
                elif tipo == 'error':
                    yield f'data: {json.dumps({"t":"err","v":dato})}\n\n'

            if not _pipeline_running and idx >= len(_pipeline_log):
                yield f'data: {json.dumps({"t":"idle"})}\n\n'
                return

            if time.time() - last_ping > 20:
                yield ': ping\n\n'
                last_ping = time.time()

            time.sleep(0.08)

    return Response(
        stream_with_context(_generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/pipeline/estado')
@login_required
def pipeline_estado():
    return jsonify({'corriendo': _pipeline_running, 'lineas': len(_pipeline_log)})


@app.route('/pipeline/cancelar', methods=['POST'])
@login_required
def pipeline_cancelar():
    if session.get('role') != 'admin':
        return jsonify({'ok': False}), 403
    if _pipeline_proc:
        _pipeline_proc.terminate()
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'No hay proceso activo'})


def _api_key_valida():
    clave = request.headers.get('X-API-Key', '')
    esperada = os.environ.get('PIPELINE_API_KEY', '')
    return bool(esperada) and clave == esperada


@app.route('/api/pipeline/trigger', methods=['POST'])
def api_pipeline_trigger():
    """Igual que /pipeline/ejecutar pero autenticado por API key (X-API-Key)
    en vez de sesion, para que herramientas externas (n8n, cron, etc.)
    puedan disparar una fase sin loguearse."""
    if not _api_key_valida():
        return jsonify({'ok': False, 'error': 'API key invalida o ausente'}), 401
    if IS_RENDER:
        return jsonify({'ok': False, 'error': 'El pipeline no puede correr en Render (falta Playwright/Chromium).'}), 400

    data = request.get_json(silent=True) or request.form
    fase = (data.get('fase') or '').strip()
    if fase not in _FASES_VALIDAS:
        return jsonify({'ok': False, 'error': 'Fase invalida'}), 400
    if _pipeline_running:
        return jsonify({'ok': False, 'error': 'Ya hay un proceso en ejecucion'}), 409

    _ejecutar_fase_bg(fase)
    return jsonify({'ok': True, 'fase': fase})


@app.route('/api/pipeline/status')
def api_pipeline_status():
    if not _api_key_valida():
        return jsonify({'ok': False, 'error': 'API key invalida o ausente'}), 401

    ultimo_ok = None
    if _pipeline_log and _pipeline_log[-1][0] == 'done':
        ultimo_ok = _pipeline_log[-1][1] == 0

    return jsonify({
        'ok': True,
        'corriendo': _pipeline_running,
        'terminado_ok': ultimo_ok,
    })


@app.route('/api/lima-distritos-geo')
@login_required
def lima_distritos_geo():
    path = os.path.join(_INTRANET_DIR, 'static', 'lima_distritos.geojson')
    if not os.path.exists(path):
        return Response(
            '{"type":"FeatureCollection","features":[]}',
            mimetype='application/json', status=200
        )
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return Response(content, mimetype='application/json',
                    headers={'Cache-Control': 'public, max-age=3600'})


@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data     = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    if not messages:
        return jsonify({'error': 'Sin mensajes'}), 400
    try:
        import ai_helper
        reply = ai_helper.generate_chat_response(
            messages=messages,
            user_role=session.get('role', ''),
            user_name=session.get('name', ''),
        )
        return jsonify({'reply': reply})
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(f"[api_chat] {type(e).__name__}: {e}")
        traceback.print_exc()
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@app.route('/api/whatsapp-mensaje')
@login_required
def api_whatsapp_mensaje():
    tiempo = request.args.get('tiempo', 'manana').lower()
    if tiempo not in ('manana', 'tarde', 'noche'):
        return jsonify({'ok': False, 'error': 'Tiempo inválido (debe ser manana, tarde o noche)'}), 400
    _base     = request.args.get('base', 30, type=int)
    base_dias = _base if _base in (25, 26, 28, 30) else 30

    import calendar as _cal
    now = datetime.now()
    mes = now.month
    anio = now.year
    hoy_dia = now.day

    # Calcular día/mes/año de ayer (puede cruzar mes)
    if hoy_dia == 1:
        mes_ayer = mes - 1 if mes > 1 else 12
        anio_ayer = anio if mes > 1 else anio - 1
        ayer_dia = _cal.monthrange(anio_ayer, mes_ayer)[1]
    else:
        mes_ayer, anio_ayer, ayer_dia = mes, anio, hoy_dia - 1

    try:
        # KPIs acumulados del mes
        kpi_v = db_helper.get_kpi_lima(mes, anio, area='Vertical',   base_dias=base_dias)
        kpi_h = db_helper.get_kpi_lima(mes, anio, area='Horizontal', base_dias=base_dias)

        if not kpi_v or not kpi_h:
            return jsonify({'ok': False, 'error': 'No se pudieron recuperar las métricas de la base de datos'}), 500

        altas_v = kpi_v['altas']
        proy_v = kpi_v['proyeccion']
        pct_proy_v = kpi_v['pct_proyeccion']
        cuota_v = kpi_v['cuota']
        faltan_v = kpi_v['faltantes']
        ritmo_v = kpi_v['ritmo_actual']
        ritmo_req_v = kpi_v['ritmo_necesario']
        dias_trans = kpi_v['dias_trans']
        dias_tot = kpi_v['dias_tot']

        altas_h = kpi_h['altas']
        proy_h = kpi_h['proyeccion']
        pct_proy_h = kpi_h['pct_proyeccion']
        cuota_h = kpi_h['cuota']
        faltan_h = kpi_h['faltantes']
        ritmo_h = kpi_h['ritmo_actual']
        ritmo_req_h = kpi_h['ritmo_necesario']

        # Helpers de formato — tablas monoespaciadas (WhatsApp renderiza ``` como bloque fijo)
        def _vel(v):
            return f"{v} Mbps" if str(v).isdigit() else str(v)

        def fmt_tabla_area(vv, av, vh, ah):
            tv, ta = vv + vh, av + ah
            s = "─" * 11 + " " + "─" * 6 + " " + "─" * 5
            return "\n".join([
                "```",
                f"{'ÁREA':<11} {'VENTAS':>6} {'ALTAS':>5}",
                s,
                f"{'Vertical':<11} {vv:>6} {av:>5}",
                f"{'Horizontal':<11} {vh:>6} {ah:>5}",
                s,
                f"{'TOTAL':<11} {tv:>6} {ta:>5}",
                "```",
            ])

        def fmt_agencias(ag_list, max_items=6):
            if not ag_list:
                return "Sin datos aún"
            rows = sorted(ag_list, key=lambda x: x.get('ventas', 0), reverse=True)[:max_items]
            s = "─" * 3 + " " + "─" * 11 + " " + "─" * 6
            lines = ["```", f"{'#':<3} {'AGENCIA':<11} {'VENTAS':>6}", s]
            for i, ag in enumerate(rows, 1):
                lines.append(f"{i:<3} {str(ag['agencia']):<11} {ag['ventas']:>6}")
            lines.append("```")
            return "\n".join(lines)

        def fmt_planes(planes_list):
            if not planes_list:
                return "Sin datos de planes"
            cnt_key = 'ventas' if 'ventas' in planes_list[0] else 'altas'
            total = sum(p[cnt_key] for p in planes_list) or 1
            top = planes_list[:4]
            others = planes_list[4:]
            s = "─" * 11 + " " + "─" * 5 + " " + "─" * 6
            lines = ["```", f"{'PLAN':<11} {'CNT':>5} {'%':>6}", s]
            for p in top:
                lines.append(f"{_vel(p['velocidad']):<11} {p[cnt_key]:>5} {p['pct']:>5.1f}%")
            if others:
                oc = sum(p[cnt_key] for p in others)
                lines.append(f"{'Otros':<11} {oc:>5} {oc/total*100:>5.1f}%")
            lines += [s, f"{'TOTAL':<11} {total:>5} {'100.0%':>6}", "```"]
            return "\n".join(lines)

        def fmt_acumulado(av, cv, pv, ppv, ah, ch, ph, pph):
            s = "─" * 11 + " " + "─" * 5 + " " + "─" * 5 + " " + "─" * 6 + " " + "─" * 5
            return "\n".join([
                "```",
                f"{'ÁREA':<11} {'ALTAS':>5} {'META':>5} {'PROY.':>6} {'AVZ':>5}",
                s,
                f"{'Vertical':<11} {str(av):>5} {str(cv):>5} {str(pv):>6} {str(ppv):>4}%",
                f"{'Horizontal':<11} {str(ah):>5} {str(ch):>5} {str(ph):>6} {str(pph):>4}%",
                "```",
            ])

        def fmt_ritmo(rv, rrv, rh, rrh):
            s = "─" * 11 + " " + "─" * 7 + " " + "─" * 8
            return "\n".join([
                "```",
                f"{'ÁREA':<11} {'ACTUAL':>7} {'REQUER.':>8}",
                s,
                f"{'Vertical':<11} {str(rv):>7} {str(rrv):>8}",
                f"{'Horizontal':<11} {str(rh):>7} {str(rrh):>8}",
                "```",
            ])

        # Build message depending on time
        if tiempo == 'manana':
            # Exacto del día de ayer (para tabla de cierre)
            kpi_v_ay = db_helper.get_kpi_lima(mes_ayer, anio_ayer, area='Vertical',   dia=ayer_dia, base_dias=base_dias) or {}
            kpi_h_ay = db_helper.get_kpi_lima(mes_ayer, anio_ayer, area='Horizontal', dia=ayer_dia, base_dias=base_dias) or {}
            # Acumulado hasta ayer (días 1–ayer_dia) para proyección: (altas/ayer_dia)*base_dias
            kpi_v_acum = db_helper.get_kpi_lima(mes_ayer, anio_ayer, area='Vertical',   dia=ayer_dia, cumul=True, base_dias=base_dias) or {}
            kpi_h_acum = db_helper.get_kpi_lima(mes_ayer, anio_ayer, area='Horizontal', dia=ayer_dia, cumul=True, base_dias=base_dias) or {}
            agencias_ay = db_helper.get_ranking_agencias_lima(mes_ayer, anio_ayer, dia=ayer_dia)

            ventas_v_ay = kpi_v_ay.get('ventas', 0)
            altas_v_ay  = kpi_v_ay.get('altas', 0)
            ventas_h_ay = kpi_h_ay.get('ventas', 0)
            altas_h_ay  = kpi_h_ay.get('altas', 0)

            # Valores acumulados para la tabla de proyección
            _av   = kpi_v_acum.get('altas', 0)
            _cv   = kpi_v_acum.get('cuota', cuota_v)
            _pv   = kpi_v_acum.get('proyeccion', 0)
            _ppv  = kpi_v_acum.get('pct_proyeccion', 0)
            _ah   = kpi_h_acum.get('altas', 0)
            _ch   = kpi_h_acum.get('cuota', cuota_h)
            _ph   = kpi_h_acum.get('proyeccion', 0)
            _pph  = kpi_h_acum.get('pct_proyeccion', 0)
            _dtr  = kpi_v_acum.get('dias_trans', ayer_dia)
            _dtot = kpi_v_acum.get('dias_tot', dias_tot)

            titulo = f"Mensaje de la Mañana · Base {base_dias}d"
            mensaje = (
                f"🌅 *WIN · REPORTE MATUTINO*\n"
                f"📅 _Día {_dtr} de {_dtot}_\n\n"
                f"📊 *Cierre de ayer (día {ayer_dia}):*\n"
                f"{fmt_tabla_area(ventas_v_ay, altas_v_ay, ventas_h_ay, altas_h_ay)}\n\n"
                f"🏆 *Top agencias de ayer:*\n"
                f"{fmt_agencias(agencias_ay)}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 *Acumulado hasta ayer (días 1–{ayer_dia}):*\n"
                f"{fmt_acumulado(_av, _cv, _pv, _ppv, _ah, _ch, _ph, _pph)}\n\n"
                f"¡Que tengan un excelente y productivo día! 💪🔥"
            )

        elif tiempo == 'tarde':
            kpi_v_hoy = db_helper.get_kpi_lima(mes, anio, area='Vertical',   dia=hoy_dia, base_dias=base_dias) or {}
            kpi_h_hoy = db_helper.get_kpi_lima(mes, anio, area='Horizontal', dia=hoy_dia, base_dias=base_dias) or {}
            agencias_hoy = db_helper.get_ranking_agencias_lima(mes, anio, dia=hoy_dia)

            ventas_v_hoy = kpi_v_hoy.get('ventas', 0)
            altas_v_hoy  = kpi_v_hoy.get('altas', 0)
            ventas_h_hoy = kpi_h_hoy.get('ventas', 0)
            altas_h_hoy  = kpi_h_hoy.get('altas', 0)

            titulo = f"Mensaje de la Tarde · Base {base_dias}d"
            mensaje = (
                f"☀️ *WIN · AVANCE DE LA TARDE*\n"
                f"📅 _Hoy día {hoy_dia} · Día {dias_trans} de {dias_tot}_\n\n"
                f"📊 *Lo que va del día de hoy:*\n"
                f"{fmt_tabla_area(ventas_v_hoy, altas_v_hoy, ventas_h_hoy, altas_h_hoy)}\n\n"
                f"🏆 *Top agencias de hoy:*\n"
                f"{fmt_agencias(agencias_hoy)}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ *Ritmo vs. Requerido (/día):*\n"
                f"{fmt_ritmo(ritmo_v, ritmo_req_v, ritmo_h, ritmo_req_h)}\n\n"
                f"📈 *Acumulado del mes:*\n"
                f"{fmt_acumulado(altas_v, cuota_v, proy_v, pct_proy_v, altas_h, cuota_h, proy_h, pct_proy_h)}\n\n"
                f"¡A seguir empujando! 🚀"
            )

        else:  # noche
            kpi_v_hoy = db_helper.get_kpi_lima(mes, anio, area='Vertical',   dia=hoy_dia, base_dias=base_dias) or {}
            kpi_h_hoy = db_helper.get_kpi_lima(mes, anio, area='Horizontal', dia=hoy_dia, base_dias=base_dias) or {}
            agencias_hoy_n = db_helper.get_ranking_agencias_lima(mes, anio, dia=hoy_dia)
            planes_v_list = db_helper.get_velocidad_planes_ventas_lima(mes, anio, area='Vertical')
            planes_h_list = db_helper.get_velocidad_planes_ventas_lima(mes, anio, area='Horizontal')

            ventas_v_hoy = kpi_v_hoy.get('ventas', 0)
            altas_v_hoy  = kpi_v_hoy.get('altas', 0)
            ventas_h_hoy = kpi_h_hoy.get('ventas', 0)
            altas_h_hoy  = kpi_h_hoy.get('altas', 0)

            titulo = f"Mensaje de la Noche · Base {base_dias}d"
            mensaje = (
                f"🌙 *WIN · CIERRE DE JORNADA*\n"
                f"📅 _Balance del día {hoy_dia} · Día {dias_trans} de {dias_tot}_\n\n"
                f"📊 *Ventas e instalaciones del día:*\n"
                f"{fmt_tabla_area(ventas_v_hoy, altas_v_hoy, ventas_h_hoy, altas_h_hoy)}\n\n"
                f"🏆 *Top agencias del día:*\n"
                f"{fmt_agencias(agencias_hoy_n)}\n\n"
                f"📡 *Planes más vendidos del mes:*\n"
                f"*Vertical:*\n{fmt_planes(planes_v_list)}\n"
                f"*Horizontal:*\n{fmt_planes(planes_h_list)}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 *Acumulado del mes:*\n"
                f"{fmt_acumulado(altas_v, cuota_v, proy_v, pct_proy_v, altas_h, cuota_h, proy_h, pct_proy_h)}\n\n"
                f"¡Gracias por el esfuerzo de hoy! A descansar. 💤🙌"
            )

        return jsonify({'ok': True, 'titulo': titulo, 'mensaje': mensaje})

    except Exception as e:
        import traceback
        print(f"[api_whatsapp_mensaje] Error: {e}")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/prediccion-dia')
@login_required
def api_prediccion_dia():
    result = db_helper.get_prediccion_dia()
    if result is None:
        return jsonify({'ok': False, 'error': 'No se pudo calcular la predicción'}), 500
    return jsonify({'ok': True, **result})


@app.route('/api/resumen-tabla')
@login_required
def api_resumen_tabla():
    from datetime import timedelta
    hoy  = datetime.now()
    _base = request.args.get('base', 25, type=int)
    base_dias = _base if _base in (25, 26, 28, 29, 30, 31) else 25
    ref = request.args.get('ref', 'hoy')  # 'hoy' o 'ayer'

    if ref == 'ayer':
        fecha_ref = hoy - timedelta(days=1)
        mes_q, anio_q, dia_q = fecha_ref.month, fecha_ref.year, fecha_ref.day
        dia_corte = dia_q
        def _kpi(area):
            return db_helper.get_kpi_lima(mes_q, anio_q, area=area, base_dias=base_dias, dia=dia_q, cumul=True) or {}
    else:
        mes_q, anio_q = request.args.get('mes', hoy.month, type=int), request.args.get('anio', hoy.year, type=int)
        dia_corte = hoy.day
        def _kpi(area):
            return db_helper.get_kpi_lima(mes_q, anio_q, area=area, base_dias=base_dias) or {}

    import calendar as _cal
    dias_mes = _cal.monthrange(anio_q, mes_q)[1]

    filas = []
    for area, label in [('Vertical', 'Vertical'), ('Horizontal', 'Horizontal'), ('', 'TOTAL')]:
        kpi = _kpi(area)
        bac_total = sum(db_helper.get_bac_lima(mes_q, anio_q, dia_corte, area=area).values())
        dias_trans = kpi.get('dias_trans', dia_corte)
        dias_rest = max(base_dias - dias_trans, 1)
        faltante_neto = max(kpi.get('faltantes', 0) - bac_total, 0)
        filas.append({
            'area':            label,
            'altas':           kpi.get('altas', 0),
            'meta':            kpi.get('cuota', 0),
            'proyeccion':      kpi.get('proyeccion', 0),
            'avz':             kpi.get('pct_proyeccion', 0.0),
            'alcance':         kpi.get('alcance', 0.0),
            'ritmo_actual':    kpi.get('ritmo_actual', 0.0),
            'ritmo_necesario': kpi.get('ritmo_necesario', 0.0),
            'faltantes':       kpi.get('faltantes', 0),
            'bac':             bac_total,
            'faltante_neto':   faltante_neto,
            'ritmo_necesario_neto': round(faltante_neto / dias_rest),
        })
    return jsonify({'ok': True, 'mes': mes_q, 'anio': anio_q, 'base': base_dias, 'ref': ref,
                     'dia_corte': dia_corte, 'dias_mes': dias_mes, 'filas': filas})


@app.route('/api/proyeccion-cierre')
@login_required
def api_proyeccion_cierre():
    from datetime import timedelta
    hoy = datetime.now()
    _base = request.args.get('base', 25, type=int)
    base_dias = _base if _base in (25, 26, 28, 29, 30, 31) else 25
    ref = request.args.get('ref', 'hoy')
    _area = request.args.get('area', '')
    area = _area if _area in ('Vertical', 'Horizontal') else ''

    if ref == 'ayer':
        fecha_ref = hoy - timedelta(days=1)
        mes_q, anio_q, dia_q = fecha_ref.month, fecha_ref.year, fecha_ref.day
    else:
        mes_q, anio_q = request.args.get('mes', hoy.month, type=int), request.args.get('anio', hoy.year, type=int)
        dia_q = None

    data = db_helper.get_proyeccion_cierre_lima(mes_q, anio_q, dia_ref=dia_q, base_dias=base_dias, area=area)
    if data is None:
        return jsonify({'ok': False, 'error': 'No se pudo calcular la proyección'}), 500
    return jsonify({'ok': True, 'mes': mes_q, 'anio': anio_q, **data})


@app.route('/api/avance-horario')
@login_required
def api_avance_horario():
    """Cuadro de avance del día: necesidad vs. ALTAS EJECUTADAS (instalaciones,
    no ventas registradas), repartidas por turno (Mañana/Mediodía/Tarde — el
    único corte horario real que trae la data, vía [Tramo Horario]; el sistema
    no guarda la hora exacta de ejecución).
    La 'necesidad' del día es el ritmo necesario BRUTO — el mismo campo que
    se ve en la columna 'RITMO NEC.' de Resumen Lima: (cuota 100% − altas) ÷
    días restantes, sin descontar BAC — repartido en partes iguales entre los
    3 turnos. ref=hoy usa datos en vivo; ref=ayer usa el corte de ayer, igual
    que el selector de Resumen Lima, para poder comparar 1 a 1."""
    from datetime import timedelta
    hoy = datetime.now()
    _base = request.args.get('base', 25, type=int)
    base_dias = _base if _base in (25, 26, 28, 29, 30, 31) else 25
    ref = request.args.get('ref', 'hoy')

    if ref == 'ayer':
        fecha_ref = hoy - timedelta(days=1)
        mes_q, anio_q, dia_q = fecha_ref.month, fecha_ref.year, fecha_ref.day
        fecha_objetivo = fecha_ref.date()
        def _kpi(area):
            return db_helper.get_kpi_lima(mes_q, anio_q, area=area, base_dias=base_dias, dia=dia_q, cumul=True) or {}
        turno_actual = None
    else:
        mes_q, anio_q, dia_q = hoy.month, hoy.year, hoy.day
        fecha_objetivo = hoy.date()
        def _kpi(area):
            return db_helper.get_kpi_lima(mes_q, anio_q, area=area, base_dias=base_dias) or {}
        turno_actual = 0 if hoy.hour < 12 else (1 if hoy.hour < 16 else 2)

    def _meta_dia(area):
        # Ritmo necesario BRUTO — el mismo campo que se ve en la columna
        # "RITMO NEC." de Resumen Lima: (cuota 100% − altas) ÷ días restantes,
        # sin descontar BAC.
        kpi = _kpi(area)
        return kpi.get('ritmo_necesario', 0)

    meta_ventas_hoy = _meta_dia('')
    meta_vertical = _meta_dia('Vertical')
    meta_horizontal = _meta_dia('Horizontal')

    activaciones = db_helper.get_activaciones_hoy(fecha=fecha_objetivo)
    turnos_data = activaciones.get('turnos', [])
    n_turnos = len(turnos_data) or 3

    filas = []
    acum = acum_v = acum_h = 0
    for i, t in enumerate(turnos_data):
        acum += t['ejecutadas']
        acum_v += t['ejecutadas_vertical']
        acum_h += t['ejecutadas_horizontal']
        frac = (i + 1) / n_turnos
        necesidad = round(meta_ventas_hoy * frac)
        necesidad_v = round(meta_vertical * frac)
        necesidad_h = round(meta_horizontal * frac)
        filas.append({
            'turno': t['turno'], 'indice': i,
            'necesidad_acum': necesidad, 'avance_acum': acum, 'diferencia': acum - necesidad,
            'necesidad_vertical': necesidad_v, 'avance_vertical': acum_v, 'diferencia_vertical': acum_v - necesidad_v,
            'necesidad_horizontal': necesidad_h, 'avance_horizontal': acum_h, 'diferencia_horizontal': acum_h - necesidad_h,
        })

    return jsonify({
        'ok': True, 'base': base_dias, 'ref': ref, 'meta_ventas_hoy': meta_ventas_hoy,
        'meta_vertical': meta_vertical, 'meta_horizontal': meta_horizontal,
        'avance_hoy_total': activaciones.get('ejecutadas', 0),
        'avance_hoy_vertical': activaciones.get('ejecutadas_vertical', 0),
        'avance_hoy_horizontal': activaciones.get('ejecutadas_horizontal', 0),
        'turno_actual': turno_actual, 'turnos': filas, 'activaciones': activaciones,
    })


@app.route('/reporte-gerente')
@login_required
def reporte_gerente():
    _scope = ROLE_SCOPE.get(session['role'])
    if _scope and _scope['home'] != 'reporte_gerente':
        return redirect(url_for(_scope['home'], **{k: v for k, v in _scope.items() if k != 'home' and v}))

    from datetime import timedelta
    hoy_real = datetime.now()
    _base     = request.args.get('base', 30, type=int)
    base_dias = _base if _base in range(25, 32) else 30
    _area     = request.args.get('area', '')
    area      = _area if _area in ('Vertical', 'Horizontal') else ''
    _ref      = request.args.get('ref', 'hoy')
    ref       = _ref if _ref in ('hoy', 'ayer') else 'hoy'
    _dia_pick = request.args.get('dia', 0, type=int)
    dia_pick  = _dia_pick if _dia_pick and 1 <= _dia_pick <= 31 else 0

    _mes_arg  = request.args.get('mes',  type=int)
    _anio_arg = request.args.get('anio', type=int)
    mes  = _mes_arg  if _mes_arg  else hoy_real.month
    anio = _anio_arg if _anio_arg else hoy_real.year

    if dia_pick:
        # Día específico: ventas/altas exactas de ese día (no acumulado), tiene
        # prioridad sobre el toggle Ayer/Hoy.
        dia, _cumul = dia_pick, False
    elif ref == 'ayer':
        fecha_ayer = hoy_real - timedelta(days=1)
        # El corte "ayer" solo tiene sentido cuando el mes/año elegido es el
        # mes en curso; un mes ya cerrado se ve igual con Hoy o Ayer.
        if mes == fecha_ayer.month and anio == fecha_ayer.year:
            dia, _cumul = fecha_ayer.day, True
        else:
            dia, _cumul = None, False
    else:
        dia, _cumul = None, False

    meses = [
        {'id': 1, 'nombre': 'Enero'},    {'id': 2, 'nombre': 'Febrero'},
        {'id': 3, 'nombre': 'Marzo'},    {'id': 4, 'nombre': 'Abril'},
        {'id': 5, 'nombre': 'Mayo'},     {'id': 6, 'nombre': 'Junio'},
        {'id': 7, 'nombre': 'Julio'},    {'id': 8, 'nombre': 'Agosto'},
        {'id': 9, 'nombre': 'Septiembre'}, {'id': 10, 'nombre': 'Octubre'},
        {'id': 11, 'nombre': 'Noviembre'}, {'id': 12, 'nombre': 'Diciembre'},
    ]
    mes_nombre = next((m['nombre'] for m in meses if m['id'] == mes), '')

    kpi_t = db_helper.get_kpi_lima(mes, anio, area='',           dia=dia, cumul=_cumul, base_dias=base_dias) or {}
    kpi_v = db_helper.get_kpi_lima(mes, anio, area='Vertical',   dia=dia, cumul=_cumul, base_dias=base_dias) or {}
    kpi_h = db_helper.get_kpi_lima(mes, anio, area='Horizontal', dia=dia, cumul=_cumul, base_dias=base_dias) or {}
    k = kpi_v if area == 'Vertical' else (kpi_h if area == 'Horizontal' else kpi_t)

    planes_v_raw = db_helper.get_velocidad_planes_lima(mes, anio, area='Vertical',   dia=dia, cumul=_cumul)
    planes_h_raw = db_helper.get_velocidad_planes_lima(mes, anio, area='Horizontal', dia=dia, cumul=_cumul)
    _pm = {}
    for p in planes_v_raw:
        _pm[p['velocidad']] = {'velocidad': p['velocidad'], 'v_altas': p['altas'], 'v_pct': p['pct'], 'h_altas': 0, 'h_pct': 0.0}
    for p in planes_h_raw:
        if p['velocidad'] in _pm:
            _pm[p['velocidad']]['h_altas'] = p['altas']
            _pm[p['velocidad']]['h_pct']   = p['pct']
        else:
            _pm[p['velocidad']] = {'velocidad': p['velocidad'], 'v_altas': 0, 'v_pct': 0.0, 'h_altas': p['altas'], 'h_pct': p['pct']}
    planes_merged = sorted(_pm.values(), key=lambda x: x['v_altas'] + x['h_altas'], reverse=True)
    for p in planes_merged:
        p['total'] = p['v_altas'] + p['h_altas']

    top_distritos = db_helper.get_top_distritos_lima(mes, anio, top=10, dia=dia, cumul=_cumul)
    pivot_sub = db_helper.get_pivot_subagencias_lima(mes, anio, dia=dia, cumul=_cumul)
    anios = list(range(2024, datetime.now().year + 2))

    # Instalaciones del día: si hay un Día específico elegido, la vista operativa
    # se mueve a ese día del mes/año filtrado; si no, sigue el corte Ayer/Hoy real.
    if dia_pick:
        import calendar
        _dias_en_mes = calendar.monthrange(anio, mes)[1]
        fecha_avance = datetime(anio, mes, min(dia_pick, _dias_en_mes)).date()
        avance_label = f'Día {dia_pick}'
    elif ref == 'ayer':
        fecha_avance = (hoy_real - timedelta(days=1)).date()
        avance_label = 'Ayer'
    else:
        fecha_avance = hoy_real.date()
        avance_label = 'Hoy'
    activaciones_hoy = db_helper.get_activaciones_hoy(fecha=fecha_avance)
    activaciones_hoy['agendadas_vertical']   = activaciones_hoy['ejecutadas_vertical']   + activaciones_hoy['pendientes_vertical']
    activaciones_hoy['agendadas_horizontal'] = activaciones_hoy['ejecutadas_horizontal'] + activaciones_hoy['pendientes_horizontal']

    return render_template(
        'reporte_gerente.html',
        user=session['name'], role=session['role'],
        mes_actual=mes, anio_actual=anio,
        mes_nombre=mes_nombre, meses=meses, anios=anios,
        dia_actual=dia or 0, dia_pick=dia_pick, base_dias=base_dias, area=area, ref=ref,
        kpi_t=kpi_t, kpi_v=kpi_v, kpi_h=kpi_h, k=k,
        planes_merged=planes_merged,
        top_distritos=top_distritos,
        pivot_sub=pivot_sub,
        activaciones_hoy=activaciones_hoy, fecha_avance=fecha_avance, avance_label=avance_label,
        generado=datetime.now().strftime('%d/%m/%Y %H:%M'),
    )


# ── MOROSIDAD / CLAWBACK ────────────────────────────────────────────────────


@app.route('/morosidad')
@login_required
def morosidad():
    return render_template('morosidad.html', user=session['name'], role=session['role'])


def _mora_kwargs():
    mes_str = request.args.get('mes', '')
    return {k: v for k, v in {
        'mes':          int(mes_str) if mes_str.isdigit() else None,
        'departamento': request.args.get('departamento', ''),
        'grupo':        request.args.get('grupo',        ''),
        'recibo':       request.args.get('recibo',       ''),
        'supervisor':   request.args.get('supervisor',   ''),
        'distrito':     request.args.get('distrito',     ''),
        'riesgo':       request.args.get('riesgo',       ''),
        'caso':         request.args.get('caso',         ''),
        'dni':          request.args.get('dni',          ''),
        'tramo':        request.args.get('tramo',        ''),
    }.items() if v}



@app.route('/api/departamentos')
@login_required
def api_departamentos():
    try:
        return jsonify(db_helper.get_departamentos())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/filtros')
@login_required
def api_mora_filtros():
    try:
        return jsonify(db_helper.get_mora_filtros())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/resumen')
@login_required
def api_mora_resumen():
    try:
        return jsonify(db_helper.get_mora_resumen(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/embudo')
@login_required
def api_mora_embudo():
    try:
        return jsonify(db_helper.get_mora_embudo(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/perdidas')
@login_required
def api_mora_perdidas():
    try:
        return jsonify(db_helper.get_mora_perdidas(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/supervisores')
@login_required
def api_mora_supervisores():
    try:
        return jsonify(db_helper.get_mora_supervisores(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/casos')
@login_required
def api_mora_casos():
    try:
        return jsonify(db_helper.get_mora_casos(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/distritos')
@login_required
def api_mora_distritos():
    try:
        return jsonify(db_helper.get_mora_distritos(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/paquetes')
@login_required
def api_mora_paquetes():
    try:
        return jsonify(db_helper.get_mora_paquetes(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/riesgos')
@login_required
def api_mora_riesgos():
    try:
        return jsonify(db_helper.get_mora_riesgos(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/detalle')
@login_required
def api_mora_detalle():
    try:
        return jsonify(db_helper.get_mora_detalle(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/detalle/excel')
@login_required
def api_mora_detalle_excel():
    try:
        import io
        import pandas as pd
        from datetime import datetime

        rows = db_helper.get_mora_detalle(**_mora_kwargs())
        if not rows:
            return jsonify({'error': 'Sin datos para exportar'}), 404

        col_names = {
            'dni': 'DNI / Carnet',
            'paquete': 'Paquete',
            'precio_paquete': 'Precio Paquete',
            'adicional': 'Adicional',
            'precio_adicional': 'Precio Adicional',
            'total_precio': 'Total S/.',
            'fecha_activacion': 'F. Activación',
            'fecha_pago': 'F. Pago',
            'fecha_venc_m1': 'Venc. M1', 'fecha_pago_1': 'Pago M1',
            'deuda_m1': 'Deuda M1', 'estado_m1': 'Estado M1',
            'fecha_venc_m2': 'Venc. M2', 'fecha_pago_2': 'Pago M2',
            'deuda_m2': 'Deuda M2', 'estado_m2': 'Estado M2',
            'fecha_venc_m3': 'Venc. M3', 'fecha_pago_3': 'Pago M3',
            'deuda_m3': 'Deuda M3', 'estado_m3': 'Estado M3',
            'recibo': 'Recibo',
            'ultimo_estado': 'Último Estado',
            'caso': 'Caso',
            'riesgo': 'Riesgo',
        }

        df = pd.DataFrame(rows).rename(columns=col_names)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Detalle Morosidad')
            ws = writer.sheets['Detalle Morosidad']
            # Ajusta ancho de columnas automáticamente
            for col in ws.columns:
                max_len = max((len(str(c.value or '')) for c in col), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

        buf.seek(0)
        fname = f"mora_detalle_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            buf.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{fname}"'}
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/pagos-dia')
@login_required
def api_mora_pagos_dia():
    try:
        data = db_helper.get_mora_pagos_dia(**_mora_kwargs())
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/mora/pagos-acumulado')
@login_required
def api_mora_pagos_acumulado():
    try:
        return jsonify(db_helper.get_mora_pagos_acumulado(**_mora_kwargs()))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- CONSULTAS SQL ---
_SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'SQL')

try:
    import db_config
except ImportError:
    from . import db_config

@app.route('/queries')
@login_required
def queries():
    sql_tree = {}
    if os.path.exists(_SQL_DIR):
        for root, dirs, files in os.walk(_SQL_DIR):
            rel_dir = os.path.relpath(root, _SQL_DIR)
            if rel_dir == '.':
                rel_dir = ''
            sql_files = [f for f in files if f.endswith('.sql')]
            if sql_files:
                folder_name = rel_dir.replace('\\', '/') if rel_dir else 'Raíz'
                sql_tree[folder_name] = []
                for f in sorted(sql_files):
                    rel_path = os.path.relpath(os.path.join(root, f), _SQL_DIR).replace('\\', '/')
                    sql_tree[folder_name].append({
                        'name': f,
                        'path': rel_path
                    })
    
    sorted_tree = dict(sorted(sql_tree.items()))
    return render_template('queries.html',
                           user=session['name'],
                           role=session['role'],
                           sql_tree=sorted_tree)


@app.route('/queries/get_content')
@login_required
def queries_get_content():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'No se especificó la ruta'}), 400
    
    # Prevenir path traversal
    safe_path = os.path.normpath(os.path.join(_SQL_DIR, file_path))
    if not safe_path.startswith(os.path.normpath(_SQL_DIR)):
        return jsonify({'error': 'Ruta de archivo no permitida'}), 403
        
    if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
        return jsonify({'error': 'El archivo no existe'}), 404
        
    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/queries/run', methods=['POST'])
@login_required
def queries_run():
    data = request.get_json() or {}
    sql = data.get('sql', '').strip()
    if not sql:
        return jsonify({'error': 'El script SQL está vacío'}), 400
        
    try:
        from decimal import Decimal
        from datetime import datetime, date
        
        engine = db_config.get_engine()

        conn = engine.raw_connection()
        tables = []
        try:
            cursor = conn.cursor()
            cursor.execute(sql)

            while True:
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()

                    formatted_rows = []
                    for row in rows:
                        formatted_row = []
                        for val in row:
                            if isinstance(val, (datetime, date)):
                                formatted_row.append(val.isoformat())
                            elif isinstance(val, Decimal):
                                formatted_row.append(float(val))
                            elif isinstance(val, bytes):
                                formatted_row.append(val.hex())
                            else:
                                formatted_row.append(val)
                        formatted_rows.append(formatted_row)

                    tables.append({
                        'columns': columns,
                        'rows': formatted_rows
                    })
                
                try:
                    if not cursor.nextset():
                        break
                except Exception:
                    break
        finally:
            conn.close()
            
        return jsonify({'ok': True, 'tables': tables})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/queries/run', methods=['POST'])
def api_queries_run():
    """Igual que /queries/run pero autenticado por API key, y devuelve las
    filas como lista de objetos (una fila = un item) para que herramientas
    externas (n8n -> Google Sheets, etc.) las consuman directo sin cabecera."""
    if not _api_key_valida():
        return jsonify({'ok': False, 'error': 'API key invalida o ausente'}), 401

    from decimal import Decimal
    from datetime import datetime, date

    data = request.get_json(silent=True) or {}
    sql = (data.get('sql') or '').strip()
    if not sql:
        return jsonify({'ok': False, 'error': 'El script SQL esta vacio'}), 400

    try:
        engine = db_config.get_engine()
        conn = engine.raw_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall() if cursor.description else []

            registros = []
            for row in rows:
                registro = {}
                for col, val in zip(columns, row):
                    if isinstance(val, (datetime, date)):
                        registro[col] = val.isoformat()
                    elif isinstance(val, Decimal):
                        registro[col] = float(val)
                    elif isinstance(val, bytes):
                        registro[col] = val.hex()
                    else:
                        registro[col] = val
                registros.append(registro)
        finally:
            conn.close()

        return jsonify({'ok': True, 'columnas': columns, 'filas': registros})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/queries/export', methods=['POST'])
@login_required
def queries_export():
    import io
    import pandas as pd
    from decimal import Decimal
    from datetime import datetime, date
    
    sql = request.form.get('sql', '').strip()
    filename = request.form.get('filename', 'consulta_sql').strip()
    
    filename = "".join([c for c in filename if c.isalnum() or c in (' ', '_', '-')]).rstrip()
    if not filename:
        filename = 'consulta_sql'
        
    if not sql:
        return "El script SQL está vacío", 400
        
    try:
        engine = db_config.get_engine()

        conn = engine.raw_connection()
        tables = []
        try:
            cursor = conn.cursor()
            cursor.execute(sql)

            while True:
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()

                    formatted_rows = []
                    for row in rows:
                        formatted_row = []
                        for val in row:
                            if isinstance(val, Decimal):
                                formatted_row.append(float(val))
                            else:
                                formatted_row.append(val)
                        formatted_rows.append(formatted_row)

                    df = pd.DataFrame(formatted_rows, columns=columns)
                    tables.append(df)
                
                try:
                    if not cursor.nextset():
                        break
                except Exception:
                    break
        finally:
            conn.close()
            
        if not tables:
            return "No se encontraron tablas de resultados en la consulta para exportar.", 400
            
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            for idx, df in enumerate(tables):
                sheet_name = f"Resultados {idx + 1}"
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                ws = writer.sheets[sheet_name]
                for col in ws.columns:
                    max_len = max((len(str(c.value or '')) for c in col), default=10)
                    ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)
                    
        buf.seek(0)
        fname = f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            buf.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{fname}"'}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error al generar el Excel: {str(e)}", 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1']

    # Con el reloader de debug, este modulo se importa 2 veces (proceso monitor
    # + proceso worker). Arrancamos el scheduler solo en el worker real para
    # no duplicar los jobs programados.
    if not debug_mode or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler.start()

    app.run(debug=debug_mode, host='0.0.0.0', port=port)