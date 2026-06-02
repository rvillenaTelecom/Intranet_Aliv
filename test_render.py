from flask import Flask, render_template_string
import json

app = Flask(__name__)

@app.route('/')
def test():
    data = [{"dia": 1, "ventas": 28, "altas": 61}]
    trend_lima = json.dumps(data)
    
    # 1. Sin comillas con | safe
    template1 = """<script>const trendLima1 = {{ trend_lima | safe }};</script>"""
    print("Test 1:", render_template_string(template1, trend_lima=trend_lima))
    
    # 2. Con JSON.parse y comillas simples
    template2 = """<script>const trendLima2 = JSON.parse('{{ trend_lima | safe }}');</script>"""
    print("Test 2:", render_template_string(template2, trend_lima=trend_lima))
    
    return "OK"

with app.app_context():
    test()
