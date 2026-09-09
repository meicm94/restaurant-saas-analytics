#!/usr/bin/env python3
"""
Paso 2: limpieza y normalizacion de los CSV crudos.

Este script hace en pandas EXACTAMENTE lo mismo que los pasos de Power Query
documentados en 05_powerbi/power_query_steps.md. Sirve para dos cosas:
  1. dejar una capa limpia lista para SQL, Python y Power BI
  2. poder comparar la version "codigo" con la version "M" de la misma limpieza

Entrada : data/raw/**
Salida  : data/clean/*.csv
Ejecutar: python 01_data/clean_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

MARKET_MAP = {
    "dk": "DK", "denmark": "DK", "uk": "UK", "united kingdom": "UK",
    "de": "DE", "germany": "DE", "no": "NO", "norway": "NO",
    "se": "SE", "sweden": "SE",
}
MARKET_NAME = {"DK": "Dinamarca", "UK": "Reino Unido", "DE": "Alemania",
               "NO": "Noruega", "SE": "Suecia"}

log = []


def step(msg: str) -> None:
    log.append(msg)
    print(f"  - {msg}")


# ----------------------------------------------------------------------
# dim_restaurant
# ----------------------------------------------------------------------
print("dim_restaurant")
r = pd.read_csv(RAW / "restaurants_raw.csv", dtype=str)
n0 = len(r)
r = r.drop_duplicates(subset="restaurant_id", keep="first")
step(f"eliminadas {n0 - len(r)} filas duplicadas por restaurant_id")

r["market"] = r["market"].str.strip().str.lower().map(MARKET_MAP)
assert r["market"].notna().all(), "codigo de mercado sin mapear"
r["market_name"] = r["market"].map(MARKET_NAME)
step("mercado normalizado a codigo ISO de 2 letras")

r["city"] = r["city"].str.strip().str.title()
step("ciudad: espacios recortados y capitalizacion homogenea")

# dos formatos de fecha conviven en el origen: dd/mm/yyyy e yyyy-mm-dd
d1 = pd.to_datetime(r["signup_date"], format="%d/%m/%Y", errors="coerce")
d2 = pd.to_datetime(r["signup_date"], format="%Y-%m-%d", errors="coerce")
r["signup_date"] = d1.fillna(d2)
assert r["signup_date"].notna().all(), "fecha de alta sin parsear"
step("signup_date parseada desde dos formatos distintos")

r["cuisine_type"] = (
    r["cuisine_type"].fillna("").str.strip()
    .replace({"": "Unknown", "N/A": "Unknown", "unknown": "Unknown"})
)
step("cuisine_type: vacios, 'N/A' y 'unknown' unificados en 'Unknown'")

r["is_chain"] = r["is_chain"].astype(int)
r["signup_month"] = r["signup_date"].values.astype("datetime64[M]")
r["signup_cohort"] = r["signup_date"].dt.strftime("%Y-%m")
restaurants = r[["restaurant_id", "restaurant_name", "market", "market_name", "city",
                 "city_size", "cuisine_type", "is_chain", "acquisition_channel",
                 "signup_date", "signup_month", "signup_cohort"]]

# ----------------------------------------------------------------------
# dim_plan
# ----------------------------------------------------------------------
print("dim_plan")
plans = pd.read_csv(RAW / "plans_raw.csv")
plans["monthly_price_eur"] = plans["monthly_price_eur"].astype(float)
step(f"{len(plans)} planes cargados")

# ----------------------------------------------------------------------
# fact_subscription
# ----------------------------------------------------------------------
print("fact_subscription")
s = pd.read_csv(RAW / "subscriptions_raw.csv", dtype=str)
s["plan_id"] = s["plan_id"].str.strip()
step("plan_id: espacios recortados (clave de relacion)")

s["mrr_eur"] = (
    s["mrr_eur"].str.replace(" EUR", "", regex=False)
    .str.replace(",", ".", regex=False).astype(float)
)
step("mrr_eur: sufijo de divisa retirado y coma decimal convertida a punto")

s["end_date"] = s["end_date"].replace({"": None, "NULL": None})
s["start_date"] = pd.to_datetime(s["start_date"])
s["end_date"] = pd.to_datetime(s["end_date"])
step("end_date: '' y 'NULL' convertidos en nulo real")

s["discount_pct"] = s["discount_pct"].astype(float)
s["is_active"] = s["end_date"].isna().astype(int)
s["churn_reason"] = s["churn_reason"].replace({"": None})
s["is_churn"] = (s["end_type"] == "churn").astype(int)
CUTOFF = pd.Timestamp("2026-08-31")
s["end_month"] = s["end_date"].values.astype("datetime64[M]")
s["start_month"] = s["start_date"].values.astype("datetime64[M]")
s["tenure_days"] = (s["end_date"].fillna(CUTOFF) - s["start_date"]).dt.days
subscriptions = s

# ----------------------------------------------------------------------
# fact_order  (combinar los ficheros mensuales de la carpeta)
# ----------------------------------------------------------------------
print("fact_order")
files = sorted((RAW / "orders").glob("orders_*.csv"))
parts = [pd.read_csv(f, dtype=str) for f in files]
o = pd.concat(parts, ignore_index=True)
step(f"{len(files)} ficheros mensuales combinados -> {len(o):,} filas")

n0 = len(o)
o = o.drop_duplicates(subset="order_id", keep="first")
step(f"eliminadas {n0 - len(o)} filas duplicadas por order_id")

o["order_value_eur"] = o["order_value_eur"].str.replace(",", ".", regex=False).astype(float)
step("order_value_eur: coma decimal de algunos meses convertida a punto")

o["order_status"] = o["order_status"].str.strip().str.lower()
step(f"order_status homogeneizado a minusculas: {sorted(o['order_status'].unique())}")

o["order_date"] = pd.to_datetime(o["order_date"])
o["order_month"] = o["order_date"].values.astype("datetime64[M]")
o["is_completed"] = (o["order_status"] == "completed").astype(int)
o["net_order_value_eur"] = np.where(o["is_completed"] == 1, o["order_value_eur"], 0.0)
orders = o.sort_values("order_date").reset_index(drop=True)
step(f"{orders['is_completed'].sum():,} pedidos completados de {len(orders):,} "
     f"({orders['is_completed'].mean():.1%})")

# ----------------------------------------------------------------------
# Resto de tablas
# ----------------------------------------------------------------------
print("otras tablas")
tickets = pd.read_csv(RAW / "support_tickets_raw.csv", parse_dates=["ticket_date"])
tickets["ticket_month"] = tickets["ticket_date"].values.astype("datetime64[M]")
campaigns = pd.read_csv(RAW / "campaigns_raw.csv", parse_dates=["start_date", "end_date"])
assignments = pd.read_csv(RAW / "campaign_assignments_raw.csv", parse_dates=["assigned_date"])
step(f"tickets={len(tickets):,}  campanas={len(campaigns)}  asignaciones={len(assignments):,}")

# ----------------------------------------------------------------------
# dim_date
# ----------------------------------------------------------------------
dates = pd.date_range("2025-01-01", "2026-08-31", freq="D")
ES_MONTH = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
            "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
dim_date = pd.DataFrame({"date": dates})
dim_date["year"] = dim_date["date"].dt.year
dim_date["quarter"] = "Q" + dim_date["date"].dt.quarter.astype(str)
dim_date["month_number"] = dim_date["date"].dt.month
dim_date["month_name"] = [ES_MONTH[m - 1] for m in dim_date["month_number"]]
dim_date["year_month"] = dim_date["date"].dt.strftime("%Y-%m")
dim_date["month_start"] = dim_date["date"].values.astype("datetime64[M]")
dim_date["day_of_week"] = dim_date["date"].dt.dayofweek + 1
dim_date["is_weekend"] = dim_date["date"].dt.dayofweek.isin([4, 5, 6]).astype(int)

# ----------------------------------------------------------------------
# Escritura
# ----------------------------------------------------------------------
out = {
    "dim_restaurant.csv": restaurants,
    "dim_plan.csv": plans,
    "dim_date.csv": dim_date,
    "fact_subscription.csv": subscriptions,
    "fact_order.csv": orders,
    "fact_support_ticket.csv": tickets,
    "dim_campaign.csv": campaigns,
    "fact_campaign_assignment.csv": assignments,
}
for name, df in out.items():
    df.to_csv(CLEAN / name, index=False)
print(f"\n{len(out)} tablas limpias escritas en {CLEAN}")
for name, df in out.items():
    print(f"  {name:<32} {len(df):>8,} filas x {df.shape[1]:>2} columnas")
