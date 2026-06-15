import sys, os
sys.path.insert(0, os.path.dirname(__file__))

ok = 0
err = 0

def check(nombre, fn):
    global ok, err
    try:
        fn()
        print(f"[OK] {nombre}")
        ok += 1
    except Exception as e:
        print(f"[ERROR] {nombre}: {e}")
        err += 1

check("Carga_SQL_to_Render", lambda: __import__("Carga_SQL_to_Render"))
check("playwright", lambda: __import__("playwright.sync_api"))
check("shapely", lambda: __import__("shapely.geometry"))
check("reportlab", lambda: __import__("reportlab.lib.pagesizes"))
check("pandas + openpyxl", lambda: [__import__("pandas"), __import__("openpyxl")])
check("sqlalchemy", lambda: __import__("sqlalchemy"))
check("pyodbc", lambda: __import__("pyodbc"))

# Test conexion SQL
def test_sql():
    from Carga_SQL_to_Render import get_engine
    import sqlalchemy as sa
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(sa.text("SELECT COUNT(*) FROM dbo.winforce_lima")).scalar()
        print(f"       winforce_lima: {n:,} registros")
        n2 = conn.execute(sa.text("SELECT COUNT(*) FROM dbo.ventas_aliv")).scalar()
        print(f"       ventas_aliv:   {n2:,} registros")
check("Conexion SQL + tablas", test_sql)

# Test KML
def test_kml():
    kml = os.path.join(os.path.dirname(__file__), "Parametros_ventas.kml")
    assert os.path.exists(kml), f"No encontrado: {kml}"
    import xml.etree.ElementTree as ET
    ET.parse(kml)
check("Parametros_ventas.kml", test_kml)

# Test ReporteDiario imports
def test_reportlab():
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
    from reportlab.lib.styles import ParagraphStyle
check("reportlab completo (PDF)", test_reportlab)

print(f"\n{'='*40}")
print(f"  Resultado: {ok} OK  |  {err} ERROR(S)")
print(f"{'='*40}")
