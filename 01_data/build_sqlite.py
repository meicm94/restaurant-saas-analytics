#!/usr/bin/env python3
"""
Paso 3: carga la capa limpia en una base SQLite consultable.

SQLite se usa porque no necesita servidor y permite practicar el 95% de lo
que se pide en una vacante de analista: JOIN, CASE, CTE, funciones de ventana
y agregaciones. Las diferencias con T-SQL / Fabric estan anotadas en
02_sql/00_schema.sql.

Salida  : db/restaurant_saas.db
Ejecutar: python 01_data/build_sqlite.py
"""
from pathlib import Path
import sqlite3

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
DB = ROOT / "db" / "restaurant_saas.db"
DB.parent.mkdir(parents=True, exist_ok=True)
if DB.exists():
    DB.unlink()

TABLES = [
    "dim_restaurant", "dim_plan", "dim_date", "dim_campaign",
    "fact_subscription", "fact_order", "fact_support_ticket",
    "fact_campaign_assignment",
]
DATE_COLS = {
    "dim_restaurant": ["signup_date", "signup_month"],
    "dim_date": ["date", "month_start"],
    "dim_campaign": ["start_date", "end_date"],
    "fact_subscription": ["start_date", "end_date", "start_month", "end_month"],
    "fact_order": ["order_date", "order_month"],
    "fact_support_ticket": ["ticket_date", "ticket_month"],
    "fact_campaign_assignment": ["assigned_date"],
}
INDEXES = [
    "CREATE INDEX ix_order_rest  ON fact_order(restaurant_id)",
    "CREATE INDEX ix_order_date  ON fact_order(order_date)",
    "CREATE INDEX ix_order_month ON fact_order(order_month)",
    "CREATE INDEX ix_sub_rest    ON fact_subscription(restaurant_id)",
    "CREATE INDEX ix_sub_dates   ON fact_subscription(start_date, end_date)",
    "CREATE INDEX ix_ticket_rest ON fact_support_ticket(restaurant_id)",
    "CREATE INDEX ix_assign_camp ON fact_campaign_assignment(campaign_id)",
]

con = sqlite3.connect(DB)
for t in TABLES:
    df = pd.read_csv(CLEAN / f"{t}.csv")
    for c in DATE_COLS.get(t, []):
        # las fechas se guardan como TEXT ISO 'YYYY-MM-DD': es lo que entienden
        # las funciones date() y strftime() de SQLite
        df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d")
    df.to_sql(t, con, index=False)
    print(f"{t:<28} {len(df):>8,} filas")

for stmt in INDEXES:
    con.execute(stmt)
con.commit()

# comprobaciones de integridad
checks = {
    "pedidos sin restaurante":
        "SELECT COUNT(*) FROM fact_order o LEFT JOIN dim_restaurant r "
        "USING(restaurant_id) WHERE r.restaurant_id IS NULL",
    "suscripciones sin plan":
        "SELECT COUNT(*) FROM fact_subscription s LEFT JOIN dim_plan p "
        "USING(plan_id) WHERE p.plan_id IS NULL",
    "pedidos anteriores al alta":
        "SELECT COUNT(*) FROM fact_order o JOIN dim_restaurant r USING(restaurant_id) "
        "WHERE o.order_date < r.signup_date",
    "restaurantes con >1 suscripcion activa":
        "SELECT COUNT(*) FROM (SELECT restaurant_id FROM fact_subscription "
        "WHERE end_date IS NULL GROUP BY restaurant_id HAVING COUNT(*) > 1)",
}
print("\nIntegridad referencial")
for label, q in checks.items():
    n = con.execute(q).fetchone()[0]
    print(f"  {label:<40} {n}")
con.close()
print(f"\nBase creada: {DB}  ({DB.stat().st_size / 1e6:.1f} MB)")
