#!/usr/bin/env python3
"""
Ejecuta el proyecto completo de principio a fin, en orden.

    python run_all.py

Cada paso es independiente y se puede lanzar por separado; este script solo
garantiza el orden correcto (los datos antes que el SQL, el SQL antes que el
contraste de pandas, y los modelos al final).
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PASOS = [
    ("Generar datos crudos", "01_data/generate_raw_data.py"),
    ("Limpiar y normalizar", "01_data/clean_data.py"),
    ("Cargar en SQLite", "01_data/build_sqlite.py"),
    ("Ejecutar la biblioteca SQL", "02_sql/run_sql.py"),
    ("Panel y metricas (pandas)", "03_python/01_panel_y_metricas.py"),
    ("Modelos (scikit-learn)", "03_python/02_modelos.py"),
    ("Experimento A/B (statsmodels)", "04_experiment/ab_test_onboarding.py"),
]

fallos = 0
for i, (titulo, script) in enumerate(PASOS, 1):
    print(f"\n{'#' * 78}\n# {i}/{len(PASOS)}  {titulo}\n{'#' * 78}")
    t0 = time.time()
    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0:
        print(f"!! FALLO en {script}")
        fallos += 1
        break
    print(f"-- {titulo}: OK ({time.time() - t0:.1f}s)")

print("\n" + "=" * 78)
print("Proyecto completo." if not fallos else "Ejecucion interrumpida por un error.")
print("Resultados en outputs/ (figuras, CSV de consultas, JSON de metricas).")
sys.exit(1 if fallos else 0)
