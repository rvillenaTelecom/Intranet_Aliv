"""
cuotas_config.py
========================
Fuente única de cuotas mensuales (metas de altas asignadas por WIN a Aliv).

Este es el ÚNICO archivo que se debe editar cada mes para actualizar cuotas.
Lo importan tanto Intranet/db_helper.py (dashboard web) como todos los
scripts de reportes PDF en Pipeline/scripts/ — así se evita que un reporte
quede con una cuota vieja mientras otro ya se actualizó.

Uso desde otro archivo (Intranet/ o Pipeline/scripts/):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cuotas_config import CUOTA_LIMA, cuota_lima
"""

# ──────────────────────────────────────────────
# LIMA
# Clave: (mes_num, area). area='' = total Lima, 'Vertical' = Condominio/Edificio,
# 'Horizontal' = resto de Lima.
# ──────────────────────────────────────────────
CUOTA_LIMA = {
    (1, ''): 2010, (1, 'Vertical'): 230, (1, 'Horizontal'): 1780,
    (2, ''): 2210, (2, 'Vertical'): 260, (2, 'Horizontal'): 1950,
    (3, ''): 1920, (3, 'Vertical'): 231, (3, 'Horizontal'): 1689,
    (4, ''): 1838, (4, 'Vertical'): 310, (4, 'Horizontal'): 1528,
    (5, ''): 2332, (5, 'Vertical'): 320, (5, 'Horizontal'): 2012,
    (6, ''): 2500, (6, 'Vertical'): 314, (6, 'Horizontal'): 2186,
    (7, ''): 2250, (7, 'Vertical'): 270, (7, 'Horizontal'): 1980,
    (8, ''): 2599, (8, 'Vertical'): 304, (8, 'Horizontal'): 2295,
    (9, ''): 0, (9, 'Vertical'): 0, (9, 'Horizontal'): 0,
    # 10-12: agregar cuando WIN las asigne.
}


def cuota_lima(mes, area=''):
    return CUOTA_LIMA.get((mes, area), 0)
