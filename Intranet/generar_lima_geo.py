"""
Descarga los límites distritales de Lima y Callao desde GADM 4.1 y los guarda
como Intranet/static/lima_distritos.geojson para el mapa interactivo.

Uso (desde la raíz del proyecto o desde Intranet/):
    python Intranet/generar_lima_geo.py

Solo necesitas ejecutarlo UNA vez. Luego reinicia Flask.
"""
import json
import os
import sys
import urllib.request

URL = 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PER_3.json'

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT   = os.path.join(_HERE, 'static', 'lima_distritos.geojson')


def _simplify_ring(ring, max_pts=300):
    """Reduce número de coordenadas sin alterar la forma general."""
    if len(ring) <= max_pts:
        return ring
    step = max(1, len(ring) // max_pts)
    out  = ring[::step]
    if out[-1] != ring[-1]:
        out = list(out) + [ring[-1]]
    return out


def _simplify_geometry(geom):
    """Aplica simplificación a Polygon y MultiPolygon."""
    if geom['type'] == 'Polygon':
        geom['coordinates'] = [_simplify_ring(r) for r in geom['coordinates']]
    elif geom['type'] == 'MultiPolygon':
        geom['coordinates'] = [
            [_simplify_ring(r) for r in poly]
            for poly in geom['coordinates']
        ]
    return geom


def main():
    if os.path.exists(OUT):
        size_kb = os.path.getsize(OUT) // 1024
        print(f"El archivo ya existe ({size_kb} KB): {OUT}")
        resp = input("¿Volver a generarlo? [s/N] ").strip().lower()
        if resp != 's':
            print("Nada que hacer.")
            return

    print(f"Descargando GADM 4.1 Perú nivel 3 (archivo completo ~20 MB)...")
    print(f"URL: {URL}\n")

    try:
        req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"ERROR descargando: {e}")
        sys.exit(1)

    print(f"Descargado: {len(raw) // 1024} KB")

    data = json.loads(raw.decode('utf-8'))
    all_features = data.get('features', [])
    print(f"Total distritos Perú: {len(all_features)}")

    # NAME_1='LimaProvince' = Lima Metropolitana (43 distritos)
    # NAME_1='Callao' = Callao (Callao + Ventanilla en GADM 4.1)
    lima_callao = [
        f for f in all_features
        if f.get('properties', {}).get('NAME_1', '') in ('LimaProvince', 'Callao')
    ]
    print(f"Distritos Lima Metro + Callao: {len(lima_callao)}")

    # Simplificar polígonos para web
    for feat in lima_callao:
        feat['geometry'] = _simplify_geometry(feat['geometry'])

    out_data = {'type': 'FeatureCollection', 'features': lima_callao}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out_data, f, ensure_ascii=False, separators=(',', ':'))

    size_kb = os.path.getsize(OUT) // 1024
    print(f"\nGuardado: {OUT} ({size_kb} KB)")
    print("Listo. Reinicia Flask para que el mapa cargue los límites distritales.")


if __name__ == '__main__':
    main()
