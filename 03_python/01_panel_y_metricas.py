#!/usr/bin/env python3
"""
Semana 3 - parte 1: pandas
==========================
Construye el panel restaurante-mes (la tabla sobre la que se modela despues),
recalcula las metricas SaaS en pandas y las CONTRASTA con los resultados que
devolvio SQL. Que dos caminos independientes den el mismo numero es la mejor
prueba de que la definicion de la metrica esta bien implementada.

Salidas:
  data/clean/panel_restaurante_mes.csv
  outputs/metricas_clave.json
  outputs/figures/01_mrr_y_clientes.png
  outputs/figures/02_movimiento_mrr.png
  outputs/figures/03_cohortes_retencion.png

Ejecutar: python 03_python/01_panel_y_metricas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent))
import viz_style as vs

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

PERIODO_FIN = pd.Timestamp("2026-08-31")

# ----------------------------------------------------------------------
# 1. Carga
# ----------------------------------------------------------------------
rest = pd.read_csv(CLEAN / "dim_restaurant.csv", parse_dates=["signup_date", "signup_month"])
subs = pd.read_csv(CLEAN / "fact_subscription.csv", parse_dates=["start_date", "end_date"])
orders = pd.read_csv(CLEAN / "fact_order.csv", parse_dates=["order_date", "order_month"])
tickets = pd.read_csv(CLEAN / "fact_support_ticket.csv", parse_dates=["ticket_date", "ticket_month"])
plans = pd.read_csv(CLEAN / "dim_plan.csv")
print(f"Cargado: {len(rest)} restaurantes, {len(orders):,} pedidos, {len(subs)} tramos de suscripcion")

# ----------------------------------------------------------------------
# 2. Panel restaurante-mes
# ----------------------------------------------------------------------
meses = pd.date_range("2025-01-01", "2026-08-01", freq="MS")
fin_mes = meses + pd.offsets.MonthEnd(0)

# foto de suscripciones activas a fin de cada mes (misma convencion que en SQL)
activos = []
for ms, me in zip(meses, fin_mes):
    a = subs[(subs["start_date"] <= me) &
             (subs["end_date"].isna() | (subs["end_date"] >= me))]
    a = a[["restaurant_id", "plan_id", "mrr_eur"]].copy()
    a["mes"] = ms
    activos.append(a)
activos = pd.concat(activos, ignore_index=True)
assert not activos.duplicated(["restaurant_id", "mes"]).any(), "dos tramos activos el mismo mes"

panel = (
    rest[["restaurant_id", "market", "city_size", "cuisine_type", "is_chain",
          "acquisition_channel", "signup_date", "signup_month", "signup_cohort"]]
    .merge(pd.DataFrame({"mes": meses}), how="cross")
)
panel = panel[panel["mes"] >= panel["signup_month"]].copy()
panel = panel.merge(activos, on=["restaurant_id", "mes"], how="left")
panel["activo"] = panel["mrr_eur"].notna().astype(int)
panel["mrr_eur"] = panel["mrr_eur"].fillna(0.0)

# actividad del mes
comp = orders[orders["order_status"] == "completed"]
act_mes = (comp.groupby(["restaurant_id", "order_month"])
           .agg(pedidos=("order_id", "count"),
                gmv_eur=("order_value_eur", "sum"),
                ticket_medio_eur=("order_value_eur", "mean"))
           .reset_index().rename(columns={"order_month": "mes"}))
cancel_mes = (orders.assign(cancelado=(orders["order_status"] != "completed").astype(int))
              .groupby(["restaurant_id", "order_month"])["cancelado"].mean()
              .reset_index().rename(columns={"order_month": "mes", "cancelado": "tasa_cancelacion"}))
tick_mes = (tickets.groupby(["restaurant_id", "ticket_month"])
            .agg(tickets=("ticket_id", "count"), csat=("satisfaction_score", "mean"))
            .reset_index().rename(columns={"ticket_month": "mes"}))

panel = (panel.merge(act_mes, on=["restaurant_id", "mes"], how="left")
              .merge(cancel_mes, on=["restaurant_id", "mes"], how="left")
              .merge(tick_mes, on=["restaurant_id", "mes"], how="left"))
for c in ["pedidos", "gmv_eur", "tickets"]:
    panel[c] = panel[c].fillna(0)
panel["ticket_medio_eur"] = panel["ticket_medio_eur"].fillna(0)
panel["tasa_cancelacion"] = panel["tasa_cancelacion"].fillna(0)
panel["csat"] = panel["csat"].fillna(np.nan)

panel["antiguedad_meses"] = ((panel["mes"].dt.year * 12 + panel["mes"].dt.month)
                             - (panel["signup_month"].dt.year * 12 + panel["signup_month"].dt.month))
panel = panel.sort_values(["restaurant_id", "mes"]).reset_index(drop=True)

g = panel.groupby("restaurant_id", sort=False)
panel["pedidos_mes_anterior"] = g["pedidos"].shift(1)
panel["media_pedidos_3m"] = g["pedidos"].transform(
    lambda s: s.shift(1).rolling(3, min_periods=1).mean())
panel["variacion_actividad"] = panel["pedidos"] / panel["media_pedidos_3m"].replace(0, np.nan)
panel["tickets_acumulados"] = g["tickets"].cumsum()
# senales de trayectoria: donde esta hoy el restaurante respecto a su propio
# maximo historico y hacia donde va. Son las variables que mas aportan al
# modelo de baja, porque un negocio que cancela suele apagarse antes.
panel["pico_pedidos"] = g["pedidos"].transform(lambda s: s.expanding().max())
panel["ratio_vs_pico"] = panel["pedidos"] / panel["pico_pedidos"].replace(0, np.nan)
panel["tendencia_3m"] = (panel["media_pedidos_3m"]
                         / g["media_pedidos_3m"].shift(3).replace(0, np.nan))
panel["meses_bajo_media"] = g["variacion_actividad"].transform(
    lambda s: (s.fillna(1) < 0.85).rolling(4, min_periods=1).sum())
panel["mrr_mes_siguiente"] = g["mrr_eur"].shift(-1)
panel["activo_mes_siguiente"] = g["activo"].shift(-1)
panel["gmv_mes_siguiente"] = g["gmv_eur"].shift(-1)

# etiqueta de baja: activo este mes y no activo el siguiente (ultimo mes = NaN)
panel["baja_mes_siguiente"] = np.where(
    panel["activo_mes_siguiente"].isna(), np.nan,
    ((panel["activo"] == 1) & (panel["activo_mes_siguiente"] == 0)).astype(float))

panel.to_csv(CLEAN / "panel_restaurante_mes.csv", index=False)
print(f"Panel restaurante-mes: {len(panel):,} filas x {panel.shape[1]} columnas "
      f"-> data/clean/panel_restaurante_mes.csv")

# ----------------------------------------------------------------------
# 3. Metricas mensuales en pandas + contraste con SQL
# ----------------------------------------------------------------------
act = panel[panel["activo"] == 1]
mensual = (act.groupby("mes")
           .agg(clientes_activos=("restaurant_id", "count"),
                mrr_eur=("mrr_eur", "sum"),
                pedidos=("pedidos", "sum"),
                gmv_eur=("gmv_eur", "sum"))
           .reset_index())
mensual["arpu_eur"] = mensual["mrr_eur"] / mensual["clientes_activos"]
mensual["crecimiento_mrr_pct"] = mensual["mrr_eur"].pct_change() * 100

sql_path = OUT / "sql_results" / "04_saas_metrics__mrr_y_clientes_por_mes.csv"
if sql_path.exists():
    sql = pd.read_csv(sql_path, parse_dates=["mes"])
    comparado = mensual.merge(sql, on="mes", suffixes=("_py", "_sql"))
    dif_mrr = (comparado["mrr_eur_py"] - comparado["mrr_eur_sql"]).abs().max()
    dif_cli = (comparado["clientes_activos_py"] - comparado["clientes_activos_sql"]).abs().max()
    print(f"\nContraste pandas vs SQL  ->  max diferencia MRR: {dif_mrr:.4f} EUR | "
          f"max diferencia clientes: {dif_cli:.0f}")
    assert dif_mrr < 0.01 and dif_cli == 0, "pandas y SQL no coinciden: revisar definiciones"
else:
    print("\n(ejecuta antes 02_sql/run_sql.py para contrastar con SQL)")

# movimiento de MRR
panel["mrr_mes_anterior"] = g["mrr_eur"].shift(1).fillna(0)
mov = panel.assign(
    nuevo=np.where((panel["mrr_mes_anterior"] == 0) & (panel["mrr_eur"] > 0), panel["mrr_eur"], 0),
    expansion=np.where((panel["mrr_mes_anterior"] > 0) & (panel["mrr_eur"] > panel["mrr_mes_anterior"]),
                       panel["mrr_eur"] - panel["mrr_mes_anterior"], 0),
    contraccion=np.where((panel["mrr_mes_anterior"] > 0) & (panel["mrr_eur"] > 0)
                         & (panel["mrr_eur"] < panel["mrr_mes_anterior"]),
                         panel["mrr_eur"] - panel["mrr_mes_anterior"], 0),
    baja=np.where((panel["mrr_mes_anterior"] > 0) & (panel["mrr_eur"] == 0),
                  -panel["mrr_mes_anterior"], 0),
).groupby("mes")[["nuevo", "expansion", "contraccion", "baja"]].sum().reset_index()
mov["neto"] = mov[["nuevo", "expansion", "contraccion", "baja"]].sum(axis=1)

# churn mensual
ch = (panel[panel["mrr_mes_anterior"] > 0]
      .groupby("mes")
      .apply(lambda d: pd.Series({
          "activos_inicio": len(d),
          "bajas": int((d["mrr_eur"] == 0).sum()),
          "churn_clientes_pct": 100 * (d["mrr_eur"] == 0).mean(),
          "nrr_pct": 100 * d["mrr_eur"].sum() / d["mrr_mes_anterior"].sum(),
      }), include_groups=False)
      .reset_index())

# cohortes
coh = panel.copy()
coh["mes_de_vida"] = coh["antiguedad_meses"]
tam = coh[coh["mes_de_vida"] == 0].groupby("signup_cohort")["restaurant_id"].nunique()
ret = (coh.groupby(["signup_cohort", "mes_de_vida"])["activo"].sum().unstack()
       .div(tam, axis=0) * 100)

# ----------------------------------------------------------------------
# 4. Graficos
# ----------------------------------------------------------------------
print("\nGraficos")

# --- 01: MRR y clientes activos (dos paneles; nunca dos ejes en el mismo grafico)
fig, axes = plt.subplots(2, 1, figsize=(8.2, 6.2), sharex=True,
                         gridspec_kw={"hspace": 0.45})
ax = axes[0]
ax.plot(mensual["mes"], mensual["mrr_eur"], color=vs.BLUE, lw=2)
ax.fill_between(mensual["mes"], mensual["mrr_eur"], color=vs.BLUE, alpha=0.10)
ult = mensual.iloc[-1]
ax.scatter([ult["mes"]], [ult["mrr_eur"]], color=vs.BLUE, s=28, zorder=3)
ax.annotate(f"{ult['mrr_eur']:,.0f}".replace(",", ".") + " EUR", (ult["mes"], ult["mrr_eur"]),
            textcoords="offset points", xytext=(-6, 8), ha="right",
            fontsize=9, fontweight="bold", color=vs.INK)
ax.yaxis.set_major_formatter(lambda v, p: f"{v/1000:,.0f}k")
vs.title(ax, "El MRR crece de forma sostenida",
         "Ingreso recurrente mensual, en euros")
vs.despine(ax)

ax = axes[1]
ax.plot(mensual["mes"], mensual["clientes_activos"], color=vs.BLUE, lw=2)
ax.scatter([ult["mes"]], [ult["clientes_activos"]], color=vs.BLUE, s=28, zorder=3)
ax.annotate(f"{ult['clientes_activos']:,.0f}", (ult["mes"], ult["clientes_activos"]),
            textcoords="offset points", xytext=(-6, 8), ha="right",
            fontsize=9, fontweight="bold", color=vs.INK)
vs.title(ax, "...y la base de clientes tambien",
         "Restaurantes con suscripcion activa a fin de mes")
vs.despine(ax)
fig.autofmt_xdate(rotation=0, ha="center")
vs.save(fig, FIG / "01_mrr_y_clientes.png")

# --- 02: movimiento de MRR
fig, ax = plt.subplots(figsize=(8.6, 4.6))
x = np.arange(len(mov))
w = 0.72
ax.bar(x, mov["nuevo"], w, color=vs.BLUE, label="Nuevo")
ax.bar(x, mov["expansion"], w, bottom=mov["nuevo"], color=vs.AQUA, label="Expansion",
       linewidth=1.6, edgecolor=vs.SURFACE)
ax.bar(x, mov["contraccion"], w, color=vs.YELLOW, label="Contraccion",
       linewidth=1.6, edgecolor=vs.SURFACE)
ax.bar(x, mov["baja"], w, bottom=mov["contraccion"], color=vs.RED, label="Baja",
       linewidth=1.6, edgecolor=vs.SURFACE)
ax.plot(x, mov["neto"], color=vs.INK, lw=1.6, marker="o", ms=3.5, label="Neto")
ax.axhline(0, color=vs.INK_SOFT, lw=0.9)
ax.set_xticks(x[::2])
ax.set_xticklabels([d.strftime("%Y-%m") for d in mov["mes"]][::2])
ax.yaxis.set_major_formatter(lambda v, p: f"{v/1000:,.0f}k")
vs.title(ax, "El crecimiento del MRR viene del cliente nuevo, no de la expansion",
         "Descomposicion mensual del MRR, en euros. El negro es el neto del mes")
ax.legend(ncol=5, loc="upper left", bbox_to_anchor=(0, -0.12))
vs.despine(ax)
vs.save(fig, FIG / "02_movimiento_mrr.png")

# --- 03: cohortes de retencion (mapa de calor, rampa secuencial de un solo tono)
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("azul", vs.SEQ)
m = ret.loc[:, [c for c in ret.columns if c <= 12]]
fig, ax = plt.subplots(figsize=(9.4, 6.0))
im = ax.imshow(m.values, cmap=cmap, vmin=40, vmax=100, aspect="auto")
ax.set_xticks(range(m.shape[1]), [f"M{c}" for c in m.columns])
ax.set_yticks(range(m.shape[0]), [f"{i}  (n={tam[i]})" for i in m.index])
for i in range(m.shape[0]):
    for j in range(m.shape[1]):
        v = m.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                    color="white" if v > 78 else vs.INK)
ax.set_xticks(np.arange(-.5, m.shape[1], 1), minor=True)
ax.set_yticks(np.arange(-.5, m.shape[0], 1), minor=True)
ax.grid(which="minor", color=vs.SURFACE, linewidth=2)
ax.grid(which="major", visible=False)
ax.tick_params(which="both", length=0)
for s in ax.spines.values():
    s.set_visible(False)
vs.title(ax, "La retencion se pierde entre el mes 2 y el mes 6",
         "% de restaurantes que siguen activos, por cohorte de alta y meses de vida. "
         "M0 y M1 son 100% por el compromiso minimo de dos meses")
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cb.outline.set_visible(False)
cb.set_label("% retenido", color=vs.INK_SOFT, fontsize=8)
vs.save(fig, FIG / "03_cohortes_retencion.png")

# ----------------------------------------------------------------------
# 5. Metricas clave para el README
# ----------------------------------------------------------------------
ultimo = mensual.iloc[-1]
churn_12m = ch[ch["mes"] >= "2025-09-01"]
clave = {
    "periodo": "2025-01 a 2026-08",
    "restaurantes": int(len(rest)),
    "pedidos_totales": int(len(orders)),
    "gmv_total_eur": round(float(comp["order_value_eur"].sum()), 2),
    "clientes_activos_ultimo_mes": int(ultimo["clientes_activos"]),
    "mrr_ultimo_mes_eur": round(float(ultimo["mrr_eur"]), 2),
    "arr_ultimo_mes_eur": round(float(ultimo["mrr_eur"] * 12), 2),
    "arpu_ultimo_mes_eur": round(float(ultimo["arpu_eur"]), 2),
    "ticket_medio_eur": round(float(comp["order_value_eur"].mean()), 2),
    "churn_mensual_medio_12m_pct": round(float(churn_12m["churn_clientes_pct"].mean()), 2),
    "nrr_medio_12m_pct": round(float(churn_12m["nrr_pct"].mean()), 1),
    "retencion_m3_media_pct": round(float(ret[3].dropna().mean()), 1),
    "retencion_m6_media_pct": round(float(ret[6].dropna().mean()), 1),
    "crecimiento_mrr_medio_6m_pct": round(float(mensual["crecimiento_mrr_pct"].tail(6).mean()), 2),
}
(OUT / "metricas_clave.json").write_text(json.dumps(clave, indent=2, ensure_ascii=False))
print("\nMetricas clave")
for k, v in clave.items():
    print(f"  {k:<32} {v}")
