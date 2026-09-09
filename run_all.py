#!/usr/bin/env python3
"""
Run the complete project from raw-data generation to analytical outputs.

    python run_all.py

Each step can also run independently. This orchestrator preserves the required
dependency order: data before SQL, SQL before the pandas reconciliation, and
predictive models after the analytical panel is built.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("Generate raw data", "01_data/generate_raw_data.py"),
    ("Clean and standardize", "01_data/clean_data.py"),
    ("Load SQLite database", "01_data/build_sqlite.py"),
    ("Run SQL query library", "02_sql/run_sql.py"),
    ("Build panel and reconcile metrics (pandas)", "03_python/01_panel_and_metrics.py"),
    ("Train models (scikit-learn)", "03_python/02_models.py"),
    ("Evaluate A/B experiment (statsmodels)", "04_experiment/ab_test_onboarding.py"),
]

failures = 0
for i, (title, script) in enumerate(STEPS, 1):
    print(f"\n{'#' * 78}\n# {i}/{len(STEPS)}  {title}\n{'#' * 78}")
    t0 = time.time()
    r = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0:
        print(f"!! FAILED: {script}")
        failures += 1
        break
    print(f"-- {title}: OK ({time.time() - t0:.1f}s)")

print("\n" + "=" * 78)
print("Project completed successfully." if not failures else "Execution stopped after an error.")
print("Outputs are available in outputs/ (figures, SQL result CSVs, and metric JSON files).")
sys.exit(1 if failures else 0)
