from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from functools import wraps
import subprocess
import os
import threading
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'AlivIntranet2026!'

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



if __name__ == '__main__':
    # Usar el puerto que asigna Render o el 5001 por defecto
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host='0.0.0.0', port=port)