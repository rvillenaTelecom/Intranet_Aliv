from flask import Flask, render_template, redirect, url_for, session, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time, timedelta
import os
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'AlivMarkingSecret2026!')

# Configuración de SQLite local
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'marking.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS DE BASE DE DATOS ---

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='worker') # 'worker' o 'hr'
    schedule_start = db.Column(db.String(5), nullable=False, default='08:00') # Formato "HH:MM"
    schedule_end = db.Column(db.String(5), nullable=False, default='17:00') # Formato "HH:MM"
    markings = db.relationship('Marking', backref='user', lazy=True, cascade="all, delete-orphan")

class Marking(db.Model):
    __tablename__ = 'markings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    clock_in = db.Column(db.DateTime, nullable=True)
    break_start = db.Column(db.DateTime, nullable=True)
    break_end = db.Column(db.DateTime, nullable=True)
    clock_out = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Incompleto') # 'A tiempo', 'Tarde', 'Incompleto'
    mode = db.Column(db.String(20), nullable=False, default='presencial')   # 'presencial' | 'remoto'
    total_hours = db.Column(db.Float, nullable=False, default=0.0)
    break_hours = db.Column(db.Float, nullable=False, default=0.0)

# --- DECORADORES DE ACCESO ---

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, inicie sesión primero.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def hr_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'hr':
            flash('Acceso denegado. Se requiere cuenta de Recursos Humanos.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# --- RUTAS DE LA APLICACIÓN ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('user_role') == 'hr':
        return redirect(url_for('hr_dashboard'))
    return redirect(url_for('worker_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_username'] = user.username
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash(f'¡Bienvenido de vuelta, {user.name}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login'))

# --- TRABAJADOR ---

@app.route('/worker')
@login_required
def worker_dashboard():
    if session.get('user_role') == 'hr':
        return redirect(url_for('index'))
        
    user = db.session.get(User, session['user_id'])
    today = date.today()
    today_marking = Marking.query.filter_by(user_id=user.id, date=today).first()
    
    # Historial del mes actual
    start_of_month = date(today.year, today.month, 1)
    history = Marking.query.filter(
        Marking.user_id == user.id, 
        Marking.date >= start_of_month,
        Marking.date <= today
    ).order_by(Marking.date.desc()).all()
    
    return render_template('worker.html', user=user, today_marking=today_marking, history=history)

@app.route('/mark/<action>', methods=['POST'])
@login_required
def mark_action(action):
    user = db.session.get(User, session['user_id'])
    today = date.today()
    now = datetime.now()
    
    marking = Marking.query.filter_by(user_id=user.id, date=today).first()
    
    if action == 'clock_in':
        if marking:
            flash('Ya has registrado tu entrada de hoy.', 'error')
        else:
            try:
                hour, minute = map(int, user.schedule_start.split(':'))
                sched_time = time(hour, minute)
            except:
                sched_time = time(8, 0)

            current_time = now.time()
            if current_time > (datetime.combine(today, sched_time) + timedelta(minutes=5)).time():
                status = 'Tarde'
            else:
                status = 'A tiempo'

            mode = request.form.get('mode', 'presencial')

            new_marking = Marking(
                user_id=user.id,
                date=today,
                clock_in=now,
                status=status,
                mode=mode
            )
            db.session.add(new_marking)
            db.session.commit()
            flash(f'Entrada registrada — Modalidad: {mode.capitalize()}.', 'success')
            
    elif action == 'break_start':
        if not marking or not marking.clock_in:
            flash('Primero debes marcar tu entrada.', 'error')
        elif marking.break_start:
            flash('Ya iniciaste tu break anteriormente.', 'error')
        elif marking.clock_out:
            flash('Ya has marcado tu salida de hoy.', 'error')
        else:
            marking.break_start = now
            db.session.commit()
            flash('Inicio de break registrado.', 'warning')
            
    elif action == 'break_end':
        if not marking or not marking.break_start:
            flash('No has iniciado ningún break hoy.', 'error')
        elif marking.break_end:
            flash('Ya terminaste tu break anteriormente.', 'error')
        elif marking.clock_out:
            flash('Ya has marcado tu salida de hoy.', 'error')
        else:
            marking.break_end = now
            # Calcular duración del break en horas
            dur = (now - marking.break_start).total_seconds() / 3600.0
            marking.break_hours = round(dur, 2)
            db.session.commit()
            flash('Fin de break registrado. ¡A trabajar!', 'success')
            
    elif action == 'clock_out':
        if not marking or not marking.clock_in:
            flash('Primero debes marcar tu entrada.', 'error')
        elif marking.clock_out:
            flash('Ya has registrado tu salida de hoy.', 'error')
        elif marking.break_start and not marking.break_end:
            flash('Debes marcar el fin de tu break antes de salir.', 'error')
        else:
            marking.clock_out = now
            
            # Calcular horas trabajadas totales
            tot_dur = (now - marking.clock_in).total_seconds() / 3600.0
            if marking.break_hours:
                net_dur = tot_dur - marking.break_hours
            else:
                net_dur = tot_dur
                
            marking.total_hours = round(max(net_dur, 0.0), 2)
            db.session.commit()
            flash('Salida registrada. ¡Buen descanso!', 'success')
            
    return redirect(url_for('worker_dashboard'))

# --- RECURSOS HUMANOS ---

@app.route('/hr')
@hr_required
def hr_dashboard():
    # Obtener filtros
    selected_user = request.args.get('user_id', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    
    today = date.today()
    
    # Rango de fechas por defecto: Mes actual
    if not start_date_str:
        start_date = date(today.year, today.month, 1)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        
    if not end_date_str:
        end_date = today
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
    # Query de trabajadores para el filtro
    workers = User.query.filter_by(role='worker').order_by(User.name).all()
    
    # Query principal
    query = db.session.query(
        Marking.id,
        User.name.label('user_name'),
        Marking.date,
        Marking.clock_in,
        Marking.break_start,
        Marking.break_end,
        Marking.clock_out,
        Marking.break_hours,
        Marking.total_hours,
        Marking.status,
        Marking.mode
    ).join(User, Marking.user_id == User.id)
    
    query = query.filter(Marking.date >= start_date, Marking.date <= end_date)
    
    if selected_user:
        query = query.filter(Marking.user_id == int(selected_user))
        
    markings_raw = query.order_by(Marking.date.desc(), User.name.asc()).all()
    
    # Formatear resultados para el template
    markings = []
    for m in markings_raw:
        markings.append({
            'user_name': m.user_name,
            'date': m.date.strftime('%d/%m/%Y'),
            'clock_in': m.clock_in.strftime('%H:%M:%S') if m.clock_in else '--:--',
            'break_start': m.break_start.strftime('%H:%M') if m.break_start else '--:--',
            'break_end': m.break_end.strftime('%H:%M') if m.break_end else '--:--',
            'clock_out': m.clock_out.strftime('%H:%M:%S') if m.clock_out else '--:--',
            'break_hours': m.break_hours,
            'total_hours': m.total_hours,
            'status': m.status,
            'mode': m.mode if m.mode else 'presencial',
        })
        
    # Estadísticas del día de hoy
    active_today = Marking.query.filter_by(date=today).count()
    in_break = Marking.query.filter(
        Marking.date == today,
        Marking.break_start.isnot(None),
        Marking.break_end.is_(None),
        Marking.clock_out.is_(None)
    ).count()
    
    late_today = Marking.query.filter_by(date=today, status='Tarde').count()
    total_workers = User.query.filter_by(role='worker').count()
    
    stats = {
        'active_today': active_today,
        'in_break': in_break,
        'late_today': late_today,
        'total_workers': total_workers
    }
    
    return render_template(
        'hr.html', 
        workers=workers, 
        markings=markings, 
        stats=stats,
        selected_user=selected_user,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )

@app.route('/hr/register', methods=['POST'])
@hr_required
def register_worker():
    name = request.form.get('name', '').strip()
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    schedule_start = request.form.get('schedule_start', '08:00')
    schedule_end = request.form.get('schedule_end', '17:00')
    
    if not name or not username or not password:
        flash('Todos los campos son obligatorios.', 'error')
        return redirect(url_for('hr_dashboard'))
        
    existing = User.query.filter_by(username=username).first()
    if existing:
        flash('El nombre de usuario ya está registrado.', 'error')
        return redirect(url_for('hr_dashboard'))
        
    new_user = User(
        name=name,
        username=username,
        password_hash=generate_password_hash(password),
        role='worker',
        schedule_start=schedule_start,
        schedule_end=schedule_end
    )
    db.session.add(new_user)
    db.session.commit()
    flash(f'Colaborador {name} registrado exitosamente.', 'success')
    return redirect(url_for('hr_dashboard'))

@app.route('/hr/export')
@hr_required
def export_excel():
    selected_user = request.args.get('user_id', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    
    today = date.today()
    if not start_date_str:
        start_date = date(today.year, today.month, 1)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        
    if not end_date_str:
        end_date = today
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
    query = Marking.query.join(User, Marking.user_id == User.id)
    query = query.filter(Marking.date >= start_date, Marking.date <= end_date)
    if selected_user:
        query = query.filter(Marking.user_id == int(selected_user))

    data = query.order_by(Marking.date.desc()).all()

    rows = []
    for m in data:
        u = db.session.get(User, m.user_id)
        rows.append({
            'Empleado':      u.name,
            'Usuario':       u.username,
            'Horario':       f"{u.schedule_start} - {u.schedule_end}",
            'Fecha':         m.date.strftime('%d/%m/%Y'),
            'Entrada':       m.clock_in.strftime('%H:%M:%S')    if m.clock_in    else 'N/A',
            'Inicio Break':  m.break_start.strftime('%H:%M')    if m.break_start else 'N/A',
            'Fin Break':     m.break_end.strftime('%H:%M')      if m.break_end   else 'N/A',
            'Salida':        m.clock_out.strftime('%H:%M:%S')   if m.clock_out   else 'N/A',
            'Modalidad':     m.mode if m.mode else 'presencial',
            'Horas Break':   m.break_hours,
            'Horas Trabajo': m.total_hours,
            'Estado':        m.status,
        })
    
    df = pd.DataFrame(rows)
    
    if df.empty:
        # DataFrame vacío estructurado para evitar errores
        df = pd.DataFrame(columns=[
            'Empleado', 'Fecha', 'Entrada', 'Inicio Break', 'Fin Break', 'Salida', 'Horas Break', 'Horas Trabajo', 'Estado'
        ])
        
    # Crear excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte Asistencia')
        
    output.seek(0)
    
    filename = f"Reporte_Asistencia_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- INICIALIZACIÓN DE SEMILLAS DE BASE DE DATOS ---

with app.app_context():
    db.create_all()
    
    # Crear administrador si no existe
    admin = User.query.filter_by(username='rrhh').first()
    if not admin:
        new_admin = User(
            name='Jefa de Recursos Humanos',
            username='rrhh',
            password_hash=generate_password_hash('AlivRRHH2026!'),
            role='hr'
        )
        db.session.add(new_admin)
        
    # Crear un trabajador de prueba si no existe
    worker = User.query.filter_by(username='trabajador').first()
    if not worker:
        new_worker = User(
            name='Juan Pérez (Pruebas)',
            username='trabajador',
            password_hash=generate_password_hash('Worker2026!'),
            role='worker',
            schedule_start='08:00',
            schedule_end='17:00'
        )
        db.session.add(new_worker)
        
    db.session.commit()

if __name__ == '__main__':
    # Habilitar modo desarrollo local en puerto 5002 para no interferir con la Intranet principal
    port = int(os.environ.get("PORT", 5002))
    app.run(debug=True, host='0.0.0.0', port=port)
