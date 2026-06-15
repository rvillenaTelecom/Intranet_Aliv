from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, redirect, url_for, session, request, jsonify, Response, stream_with_context, flash
from functools import wraps
from werkzeug.security import check_password_hash
import subprocess
import os
import sys
import threading
import queue
import time
import json
from datetime import datetime
try:
    import db_helper
except ImportError:
    from . import db_helper

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'AlivIntranet2026!')

# --- PIPELINE: paths y estado global ---
_INTRANET_DIR  = os.path.dirname(os.path.abspath(__file__))
_PIPELINE_DIR  = os.path.join(os.path.dirname(_INTRANET_DIR), 'Descargas_Rápidas')
_PIPELINE_SCRIPT = os.path.join(_PIPELINE_DIR, 'run_pipeline.py')
_FASES_VALIDAS = {'bd', 'daily', 'consolidar', 'subida_aliv', 'reporte_diario'}

_pipeline_running = False
_pipeline_proc    = None
_pipeline_log     = []   # [(tipo, dato), ...] del run actual

# --- VERIFICACIÓN DE PLAYWRIGHT PARA RENDER ---
def check_playwright():
    if os.environ.get('RENDER'):
        print("Entorno Render detectado. Asegurando que Playwright esté listo...")
        try:
            subprocess.run(['python', '-m', 'playwright', 'install', 'chromium'], check=True)
        except Exception as e:
            print(f"Aviso: Error instalando playwright en arranque: {e}")

check_playwright()

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
    area = request.args.get('area', '')
    _dia = request.args.get('dia', 0, type=int)
    dia  = _dia if _dia and 1 <= _dia <= 31 else None

    meses = [
        {'id': 1, 'nombre': 'Enero'},    {'id': 2, 'nombre': 'Febrero'},
        {'id': 3, 'nombre': 'Marzo'},    {'id': 4, 'nombre': 'Abril'},
        {'id': 5, 'nombre': 'Mayo'},     {'id': 6, 'nombre': 'Junio'},
        {'id': 7, 'nombre': 'Julio'},    {'id': 8, 'nombre': 'Agosto'},
        {'id': 9, 'nombre': 'Septiembre'}, {'id': 10, 'nombre': 'Octubre'},
        {'id': 11, 'nombre': 'Noviembre'}, {'id': 12, 'nombre': 'Diciembre'},
    ]
    mes_nombre = next((m['nombre'] for m in meses if m['id'] == mes), '')

    kpi_lima   = db_helper.get_kpi_lima(mes, anio, area=area, dia=dia)
    kpi_prov   = db_helper.get_kpi_provincia(mes, anio)
    trend_lima = db_helper.get_daily_trend_lima(mes, anio, area=area)
    trend_prov = db_helper.get_daily_trend_provincia(mes, anio)
    top_dist   = db_helper.get_top_distritos_lima(mes, anio, area=area, dia=dia)
    tipo_vivienda = db_helper.get_tipo_vivienda_lima(mes, anio, area=area, dia=dia)
    dist_estados = db_helper.get_distribucion_estados_lima(mes, anio, area=area, dia=dia)
    pivot_planes  = db_helper.get_pivot_planes_agencia(mes, anio, area=area, dia=dia)
    vel_planes    = db_helper.get_velocidad_planes_lima(mes, anio, area=area, dia=dia)
    tabla_prov = db_helper.get_tabla_provincia(mes, anio)
    loc_lima    = db_helper.get_localizacion_lima(mes, anio, area=area)
    puntos_mapa = db_helper.get_puntos_mapa_lima(mes, anio, area=area)

    anios = list(range(2024, datetime.now().year + 2))

    return render_template('dashboard_ventas.html',
                           user=session['name'], role=session['role'],
                           mes_actual=mes, anio_actual=anio,
                           mes_nombre=mes_nombre, meses=meses, anios=anios,
                           area=area, dia_actual=dia or 0,
                           kpi_lima=kpi_lima, kpi_prov=kpi_prov,
                           trend_lima=trend_lima,
                           trend_prov=trend_prov,
                           top_dist=top_dist,
                           tipo_vivienda=tipo_vivienda,
                           dist_estados=dist_estados,
                           pivot_planes=pivot_planes,
                           vel_planes=vel_planes,
                           tabla_prov=tabla_prov,
                           loc_lima=loc_lima,
                           loc_zonas=loc_lima['zonas'] if loc_lima else [],
                           puntos_mapa=puntos_mapa)

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
        'nombre_completo': request.form.get('nombre_completo', '').strip(),
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
                           corriendo=_pipeline_running,
                           is_render=bool(os.environ.get('RENDER')))


@app.route('/pipeline/ejecutar', methods=['POST'])
@login_required
def pipeline_ejecutar():
    global _pipeline_running, _pipeline_proc, _pipeline_log

    if session.get('role') != 'admin':
        return jsonify({'ok': False, 'error': 'Sin permisos de administrador'}), 403
    if _pipeline_running:
        return jsonify({'ok': False, 'error': 'Ya hay un proceso en ejecución'}), 409

    fase = request.form.get('fase', '').strip()
    if fase not in _FASES_VALIDAS:
        return jsonify({'ok': False, 'error': 'Fase inválida'}), 400

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
                entry = ('line', line.rstrip())
                _pipeline_log.append(entry)
            proc.wait()
            _pipeline_log.append(('done', proc.returncode))
        except Exception as exc:
            _pipeline_log.append(('error', str(exc)))
            _pipeline_log.append(('done', 1))
        finally:
            _pipeline_running = False
            _pipeline_proc = None

    threading.Thread(target=_run, daemon=True).start()
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

    now = datetime.now()
    mes = now.month
    anio = now.year

    try:
        # 1. Obtener KPIs
        kpi_v = db_helper.get_kpi_lima(mes, anio, area='Vertical')
        kpi_h = db_helper.get_kpi_lima(mes, anio, area='Horizontal')

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

        # 2. Formateador de velocidades
        def format_speed(vel):
            return f"{vel} Mbps" if vel.isdigit() else vel

        def format_planes(planes_list):
            if not planes_list:
                return "Sin datos de planes"
            medals = ["🥇", "🥈", "🥉"]
            top_3 = planes_list[:3]
            others = planes_list[3:]
            total_altas = sum(item['altas'] for item in planes_list)
            
            lines = []
            for idx, item in enumerate(top_3):
                medal = medals[idx] if idx < len(medals) else "•"
                vel = format_speed(item['velocidad'])
                lines.append(f"{medal} {vel} → 📦 {item['altas']} ({item['pct']:.2f}%)")
            
            if others:
                others_count = sum(item['altas'] for item in others)
                others_pct = (others_count / total_altas * 100) if total_altas > 0 else 0
                lines.append(f"Otros → 📦 {others_count} ({others_pct:.2f}%)")
            return "\n".join(lines)

        # Build message depending on time
        if tiempo == 'manana':
            titulo = "Mensaje de la Mañana (Inicio)"
            mensaje = (
                f"🌅 *WIN · REPORTE MATUTINO*\n"
                f"📅 _Día {dias_trans} de {dias_tot}_\n\n"
                f"🔵 *Altas registradas (al cierre de ayer):*\n"
                f"- Vertical: {altas_v}\n"
                f"- Horizontal: {altas_h}\n\n"
                f"📈 *Proyección al cierre del mes:*\n"
                f"- Vertical: {proy_v} ({pct_proy_v}%)\n"
                f"- Horizontal: {proy_h} ({pct_proy_h}%)\n\n"
                f"🎯 *Faltan para la meta:*\n"
                f"- Vertical: {faltan_v} altas (Cuota: {cuota_v})\n"
                f"- Horizontal: {faltan_h} altas (Cuota: {cuota_h})\n\n"
                f"¡Que tengan un excelente y productivo día! 💪🔥"
            )
        elif tiempo == 'tarde':
            titulo = "Mensaje de la Tarde (Ritmo)"
            mensaje = (
                f"☀️ *WIN · AVANCE DE LA TARDE*\n"
                f"📅 _Avance al mediodía_\n\n"
                f"🔵 *Altas registradas:*\n"
                f"- Vertical: {altas_v} (Cuota: {cuota_v})\n"
                f"- Horizontal: {altas_h} (Cuota: {cuota_h})\n\n"
                f"📈 *Proyección actual:*\n"
                f"- Vertical: {proy_v} ({pct_proy_v}%)\n"
                f"- Horizontal: {proy_h} ({pct_proy_h}%)\n\n"
                f"⚡ *Ritmo de instalación diario:*\n"
                f"- Vertical: {ritmo_v} altas/día (Requerido: {ritmo_req_v}/día)\n"
                f"- Horizontal: {ritmo_h} altas/día (Requerido: {ritmo_req_h}/día)\n\n"
                f"¡A seguir empujando! 🚀"
            )
        else: # noche
            titulo = "Mensaje de la Noche (Cierre)"
            
            planes_v_list = db_helper.get_velocidad_planes_lima(mes, anio, area='Vertical')
            planes_h_list = db_helper.get_velocidad_planes_lima(mes, anio, area='Horizontal')
            
            planes_v = format_planes(planes_v_list)
            planes_h = format_planes(planes_h_list)

            mensaje = (
                f"🌙 *WIN · CIERRE DE JORNADA*\n"
                f"📅 _Balance final del día_\n\n"
                f"🔵 *Altas registradas:*\n"
                f"- Vertical: {altas_v}\n"
                f"- Horizontal: {altas_h}\n\n"
                f"📈 *Proyección al cierre del mes:*\n"
                f"- Vertical: {proy_v} ({pct_proy_v}%)\n"
                f"- Horizontal: {proy_h} ({pct_proy_h}%)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 *PLANES MÁS VENDIDOS (Top 3)*\n\n"
                f"*Vertical:*\n"
                f"{planes_v}\n\n"
                f"*Horizontal:*\n"
                f"{planes_h}\n\n"
                f"¡Gracias por el esfuerzo de hoy! A descansar. 💤🙌"
            )

        return jsonify({'ok': True, 'titulo': titulo, 'mensaje': mensaje})

    except Exception as e:
        import traceback
        print(f"[api_whatsapp_mensaje] Error: {e}")
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


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


if __name__ == '__main__':
    # Usar el puerto que asigna Render o el 5001 por defecto
    port = int(os.environ.get("PORT", 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1']
    if os.environ.get('RENDER'):
        debug_mode = False
    app.run(debug=debug_mode, host='0.0.0.0', port=port)