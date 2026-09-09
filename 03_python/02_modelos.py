#!/usr/bin/env python3
"""
Semana 3 - parte 2: scikit-learn
================================
Tres modelos sobre el panel restaurante-mes, cada uno respondiendo a una
pregunta de negocio distinta:

  1. REGRESION LINEAL   -> cuanto GMV hara este restaurante el mes que viene?
                           (prevision de ingresos por comision)
  2. REGRESION LOGISTICA-> que probabilidad tiene de darse de baja el mes que
                           viene? (lista de trabajo para el equipo de retencion)
  3. CLUSTERING K-MEANS -> que tipos de restaurante hay en la cartera?
                           (segmentacion para precios y account management)

Decisiones metodologicas que hay que poder defender en una entrevista:
  * Particion TEMPORAL, no aleatoria: se entrena con el pasado y se valida con
    los ultimos meses. Con datos de panel, una particion aleatoria filtra
    informacion del futuro y el resultado sale mejor de lo que es.
  * Ninguna variable del mes siguiente entra como predictor (fuga de datos).
  * Todo el preprocesado va DENTRO del Pipeline, para que la validacion
    cruzada escale y codifique dentro de cada pliegue y no antes.
  * Se compara siempre contra una linea base tonta. Un modelo que no gana a la
    linea base no aporta nada, por bueno que parezca su R2.

Salidas: outputs/modelos_resumen.json, outputs/segmentos_perfil.csv y figuras 04-07.
Ejecutar: python 03_python/02_modelos.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                             mean_absolute_error, precision_score, r2_score,
                             recall_score, roc_auc_score, root_mean_squared_error)
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import silhouette_score

sys.path.append(str(Path(__file__).parent))
import viz_style as vs

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
RESUMEN = {}

panel = pd.read_csv(CLEAN / "panel_restaurante_mes.csv", parse_dates=["mes", "signup_date", "signup_month"])
# El mes del ano entra como categoria: el negocio es estacional (diciembre alto,
# julio-agosto bajo) y sin esta variable el modelo no puede batir a la
# prediccion ingenua de "el mes que viene sera como este".
panel["mes_del_ano"] = panel["mes"].dt.month.astype(str)
orders = pd.read_csv(CLEAN / "fact_order.csv", parse_dates=["order_date"])
CORTE = pd.Timestamp("2026-05-01")   # entrenamiento hasta abril, prueba de mayo en adelante

NUM = ["pedidos", "gmv_eur", "ticket_medio_eur", "tickets", "tickets_acumulados",
       "antiguedad_meses", "media_pedidos_3m", "variacion_actividad",
       "tasa_cancelacion", "mrr_eur", "ratio_vs_pico", "tendencia_3m",
       "meses_bajo_media"]
CAT = ["market", "city_size", "cuisine_type", "acquisition_channel", "plan_id"]
# El mes del ano solo entra en la regresion de GMV: alli la estacionalidad es
# real y necesaria. En el modelo de baja anade doce variables ficticias que no
# aportan senal y empeoran la ordenacion por riesgo, que es lo que se usa.
CAT_REG = CAT + ["mes_del_ano"]
BIN = ["is_chain"]


def preprocesador(cat=None):
    cat = CAT if cat is None else cat
    return ColumnTransformer([
        ("num", StandardScaler(), NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False), cat),
        ("bin", "passthrough", BIN),
    ])


def nombres_variables(pre, cat=None):
    cat = CAT if cat is None else cat
    salida = list(NUM)
    salida += list(pre.named_transformers_["cat"].get_feature_names_out(cat))
    salida += BIN
    return salida


# ======================================================================
# 1. REGRESION LINEAL - GMV del mes siguiente
# ======================================================================
print("=" * 78)
print("1. REGRESION LINEAL  -  GMV del mes siguiente")
print("=" * 78)

reg = panel[(panel["activo"] == 1) &
            (panel["activo_mes_siguiente"] == 1) &
            panel["gmv_mes_siguiente"].notna()].copy()
for c in ["variacion_actividad", "ratio_vs_pico", "tendencia_3m"]:
    reg[c] = reg[c].fillna(1.0)
reg = reg.dropna(subset=["media_pedidos_3m"])

tr = reg[reg["mes"] < CORTE]
te = reg[reg["mes"] >= CORTE]
X_tr, y_tr = tr[NUM + CAT_REG + BIN], tr["gmv_mes_siguiente"]
X_te, y_te = te[NUM + CAT_REG + BIN], te["gmv_mes_siguiente"]
print(f"Entrenamiento: {len(tr):,} filas (hasta {tr['mes'].max():%Y-%m}) | "
      f"Prueba: {len(te):,} filas (desde {te['mes'].min():%Y-%m})")

modelo_reg = Pipeline([("pre", preprocesador(CAT_REG)), ("lm", LinearRegression())])
modelo_reg.fit(X_tr, y_tr)
pred = modelo_reg.predict(X_te)

# linea base: "el mes que viene sera igual que este"
base = te["gmv_eur"].to_numpy()
cv = cross_val_score(modelo_reg, X_tr, y_tr, cv=TimeSeriesSplit(n_splits=5), scoring="r2")

met_reg = {
    "r2_prueba": round(float(r2_score(y_te, pred)), 3),
    "mae_prueba_eur": round(float(mean_absolute_error(y_te, pred)), 2),
    "rmse_prueba_eur": round(float(root_mean_squared_error(y_te, pred)), 2),
    "r2_linea_base": round(float(r2_score(y_te, base)), 3),
    "mae_linea_base_eur": round(float(mean_absolute_error(y_te, base)), 2),
    "r2_validacion_cruzada_media": round(float(cv.mean()), 3),
    "r2_validacion_cruzada_desv": round(float(cv.std()), 3),
    "n_entrenamiento": int(len(tr)), "n_prueba": int(len(te)),
}
RESUMEN["regresion_gmv"] = met_reg
for k, v in met_reg.items():
    print(f"  {k:<32} {v}")
print(f"  mejora del MAE sobre la linea base: "
      f"{100 * (1 - met_reg['mae_prueba_eur'] / met_reg['mae_linea_base_eur']):.1f}%")

fig, ax = plt.subplots(figsize=(6.4, 5.6))
lim = float(np.percentile(np.concatenate([y_te, pred]), 99.5))
ax.scatter(y_te, pred, s=14, color=vs.BLUE, alpha=0.45, linewidths=0)
ax.plot([0, lim], [0, lim], color=vs.INK_SOFT, lw=1.2, ls="--")
ax.set_xlim(0, lim); ax.set_ylim(0, lim)
ax.set_xlabel("GMV real del mes siguiente (EUR)")
ax.set_ylabel("GMV predicho (EUR)")
ax.annotate(f"R2 = {met_reg['r2_prueba']:.2f}\nMAE = {met_reg['mae_prueba_eur']:,.0f} EUR",
            (0.04, 0.92), xycoords="axes fraction", va="top", fontsize=9.5,
            fontweight="bold", color=vs.INK)
vs.title(ax, "El modelo explica el GMV del mes siguiente",
         f"Meses de prueba ({te['mes'].min():%Y-%m} a {te['mes'].max():%Y-%m}); "
         "la diagonal es la prediccion perfecta")
vs.despine(ax)
ax.grid(axis="x", visible=True)
vs.save(fig, FIG / "04_regresion_gmv.png")

# ======================================================================
# 2. REGRESION LOGISTICA - baja el mes siguiente
# ======================================================================
print("\n" + "=" * 78)
print("2. REGRESION LOGISTICA  -  probabilidad de baja el mes siguiente")
print("=" * 78)

clf_df = panel[(panel["activo"] == 1) & panel["baja_mes_siguiente"].notna()].copy()
for c in ["variacion_actividad", "ratio_vs_pico", "tendencia_3m"]:
    clf_df[c] = clf_df[c].fillna(1.0)
clf_df = clf_df.dropna(subset=["media_pedidos_3m"])
clf_df["y"] = clf_df["baja_mes_siguiente"].astype(int)

tr = clf_df[clf_df["mes"] < CORTE]
te = clf_df[clf_df["mes"] >= CORTE]
X_tr, y_tr = tr[NUM + CAT + BIN], tr["y"]
X_te, y_te = te[NUM + CAT + BIN], te["y"]
print(f"Entrenamiento: {len(tr):,} filas, {y_tr.sum()} bajas ({y_tr.mean():.1%}) | "
      f"Prueba: {len(te):,} filas, {y_te.sum()} bajas ({y_te.mean():.1%})")
print("  Clases muy desbalanceadas: se usa class_weight='balanced' y se mira")
print("  AUC / precision-recall, no la exactitud (predecir 'nadie se va' ya acierta el 97%).")

modelo_clf = Pipeline([
    ("pre", preprocesador()),
    ("lr", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
])
cv_auc = cross_val_score(modelo_clf, X_tr, y_tr, cv=StratifiedKFold(5, shuffle=True, random_state=42),
                         scoring="roc_auc")
modelo_clf.fit(X_tr, y_tr)
proba = modelo_clf.predict_proba(X_te)[:, 1]
UMBRAL = 0.5
pred_clf = (proba >= UMBRAL).astype(int)
cm = confusion_matrix(y_te, pred_clf)

met_clf = {
    "auc_validacion_cruzada_media": round(float(cv_auc.mean()), 3),
    "auc_validacion_cruzada_desv": round(float(cv_auc.std()), 3),
    "auc_prueba": round(float(roc_auc_score(y_te, proba)), 3),
    "average_precision_prueba": round(float(average_precision_score(y_te, proba)), 3),
    "tasa_base_bajas_prueba": round(float(y_te.mean()), 4),
    "precision": round(float(precision_score(y_te, pred_clf, zero_division=0)), 3),
    "recall": round(float(recall_score(y_te, pred_clf)), 3),
    "exactitud": round(float(accuracy_score(y_te, pred_clf)), 3),
    "umbral": UMBRAL,
}
RESUMEN["clasificacion_churn"] = met_clf
for k, v in met_clf.items():
    print(f"  {k:<32} {v}")

# valor de negocio: si el equipo de retencion solo puede llamar al 10% de la
# cartera, a cuantas bajas llega usando el modelo?
orden = np.argsort(-proba)
top10 = orden[: max(1, int(0.10 * len(orden)))]
captura = y_te.to_numpy()[top10].sum() / max(y_te.sum(), 1)
lift = captura / 0.10
RESUMEN["clasificacion_churn"]["captura_en_top10pct"] = round(float(captura), 3)
RESUMEN["clasificacion_churn"]["lift_top10pct"] = round(float(lift), 2)
print(f"  captura_en_top10pct              {captura:.1%}  (lift x{lift:.1f} sobre llamar al azar)")

# --- figura 05: matriz de confusion
fig, ax = plt.subplots(figsize=(5.4, 4.6))
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("azul", vs.SEQ)
ax.imshow(cm / cm.sum(axis=1, keepdims=True), cmap=cmap, vmin=0, vmax=1)
etiquetas = ["Sigue", "Se da de baja"]
ax.set_xticks([0, 1], [f"Predicho:\n{e.lower()}" for e in etiquetas])
ax.set_yticks([0, 1], [f"Real:\n{e.lower()}" for e in etiquetas])
for i in range(2):
    for j in range(2):
        pct = cm[i, j] / cm[i].sum()
        ax.text(j, i, f"{cm[i, j]:,}\n{pct:.0%} de la fila", ha="center", va="center",
                fontsize=10, fontweight="bold", color="white" if pct > 0.55 else vs.INK)
ax.set_xticks(np.arange(-.5, 2, 1), minor=True)
ax.set_yticks(np.arange(-.5, 2, 1), minor=True)
ax.grid(which="minor", color=vs.SURFACE, linewidth=3)
ax.grid(which="major", visible=False)
ax.tick_params(which="both", length=0)
for s in ax.spines.values():
    s.set_visible(False)
vs.title(ax, f"El modelo encuentra {met_clf['recall']:.0%} de las bajas",
         f"Matriz de confusion en los meses de prueba, umbral {UMBRAL}")
vs.save(fig, FIG / "05_churn_matriz_confusion.png")

# --- figura 06: coeficientes como odds ratio
pre = modelo_clf.named_steps["pre"]
coef = pd.DataFrame({"variable": nombres_variables(pre),
                     "coef": modelo_clf.named_steps["lr"].coef_[0]})
coef["odds_ratio"] = np.exp(coef["coef"])
# Se grafican SOLO las variables numericas estandarizadas: sus coeficientes son
# comparables entre si (efecto de una desviacion tipica). Los coeficientes de
# las variables categoricas van al CSV, porque un "x2,7 si es sushi" no se lee
# en la misma escala y confunde mas que ayuda.
TRAD = {"pedidos": "Pedidos del mes", "gmv_eur": "GMV del mes",
        "ticket_medio_eur": "Ticket medio", "tickets": "Tickets de soporte del mes",
        "ratio_vs_pico": "Pedidos vs su maximo", "tendencia_3m": "Tendencia a 3 meses",
        "meses_bajo_media": "Meses seguidos por debajo de su media",
        "tickets_acumulados": "Tickets acumulados", "antiguedad_meses": "Antiguedad (meses)",
        "media_pedidos_3m": "Media de pedidos 3m", "variacion_actividad": "Actividad vs su media",
        "tasa_cancelacion": "Tasa de cancelacion", "mrr_eur": "MRR"}
top = coef[coef["variable"].isin(NUM)].copy().sort_values("coef")
top["etiqueta"] = top["variable"].map(TRAD)

fig, ax = plt.subplots(figsize=(7.8, 5.2))
colores = [vs.RED if c > 0 else vs.BLUE for c in top["coef"]]
ax.barh(top["etiqueta"], top["coef"], color=colores, height=0.68)
ax.axvline(0, color=vs.INK_SOFT, lw=0.9)
margen = 0.16 * max(top["coef"].abs().max(), 0.1)
for y, (c, orr) in enumerate(zip(top["coef"], top["odds_ratio"])):
    ax.text(c + (margen * 0.18 if c > 0 else -margen * 0.18), y, f"x{orr:.2f}",
            va="center", ha="left" if c > 0 else "right", fontsize=8, color=vs.INK_SOFT)
ax.set_xlim(top["coef"].min() - margen, top["coef"].max() + margen)
ax.set_xlabel("Coeficiente (log-odds). A la derecha: mas riesgo de baja")
# Lectura conjunta: "pedidos del mes" protege y "media de pedidos 3m" agrava.
# No se contradicen: manteniendo fija la media de los ultimos meses, un mes
# flojo dispara el riesgo. Los dos juntos describen una TRAYECTORIA a la baja,
# no un nivel. Es el efecto tipico de dos variables muy correlacionadas y hay
# que explicarlo, no esconderlo.
or_mes = float(coef.loc[coef["variable"] == "pedidos", "odds_ratio"].iloc[0])
or_media = float(coef.loc[coef["variable"] == "media_pedidos_3m", "odds_ratio"].iloc[0])
vs.title(ax, "Lo que anticipa una baja es la caida, no el tamano",
         f"Un mes con mas pedidos protege (x{or_mes:.2f} por desviacion tipica) y una media "
         f"previa alta con un mes flojo agrava (x{or_media:.2f}):\njuntos describen una "
         "trayectoria descendente. Etiquetas en odds ratio")
vs.despine(ax, left=True)
ax.grid(axis="x", visible=True)
ax.grid(axis="y", visible=False)
vs.save(fig, FIG / "06_churn_coeficientes.png")
coef.sort_values("coef", ascending=False).to_csv(OUT / "churn_coeficientes.csv", index=False)

# ======================================================================
# 3. CLUSTERING - segmentacion de la cartera
# ======================================================================
print("\n" + "=" * 78)
print("3. K-MEANS  -  segmentacion de restaurantes")
print("=" * 78)

comp = orders[orders["order_status"] == "completed"]
perfil_pedidos = comp.groupby("restaurant_id").agg(
    pct_app=("order_channel", lambda s: (s == "app").mean()),
    pct_delivery=("fulfilment_type", lambda s: (s == "delivery").mean()),
).reset_index()

act = panel[panel["activo"] == 1]
seg = act.groupby("restaurant_id").agg(
    pedidos_mes=("pedidos", "mean"),
    ticket_medio=("ticket_medio_eur", "mean"),
    meses_activo=("mes", "count"),
    tickets_mes=("tickets", "mean"),
    volatilidad=("pedidos", lambda s: s.std() / max(s.mean(), 1)),
).reset_index().merge(perfil_pedidos, on="restaurant_id", how="left").fillna(0)

# Solo variables de COMPORTAMIENTO. La antiguedad se deja fuera a proposito:
# si entra, K-Means separa "clientes nuevos" de "clientes veteranos", que ya
# sabemos, en vez de encontrar tipos de negocio distintos.
seg = seg[(seg["meses_activo"] >= 3) & (seg["pedidos_mes"] > 0)].reset_index(drop=True)
VARS = ["pedidos_mes", "ticket_medio", "tickets_mes", "volatilidad",
        "pct_app", "pct_delivery"]
Xs = seg[VARS].copy()
Xs["pedidos_mes"] = np.log1p(Xs["pedidos_mes"])      # muy asimetrica
Xs["ticket_medio"] = np.log1p(Xs["ticket_medio"])
Xs = StandardScaler().fit_transform(Xs)

print("  k   silueta")
siluetas = {}
for k in range(2, 7):
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xs)
    siluetas[k] = silhouette_score(Xs, km.labels_)
    print(f"  {k}   {siluetas[k]:.3f}")

# La silueta es plana (~0.15) para todo k: no hay grupos naturalmente separados,
# la cartera es un continuo. Eso NO invalida segmentar, pero cambia el criterio:
# como los datos no eligen k, lo elige el uso de negocio. Se fija k = 4 porque
# es lo que el equipo comercial puede gestionar con playbooks distintos.
# Decirlo asi es mas honesto que presentar 5 grupos como si fueran naturales.
K = 4
print(f"  -> silueta plana entre k=2 y k=6 (max {max(siluetas.values()):.3f}): no hay")
print(f"     estructura de grupos separados. Se fija k = {K} por criterio de negocio.")

km = KMeans(n_clusters=K, n_init=10, random_state=42).fit(Xs)
mejor_k, mejor_s = K, siluetas[K]
seg["segmento"] = km.labels_

estado = (panel.groupby("restaurant_id")["baja_mes_siguiente"].max()
          .rename("ha_causado_baja").reset_index())
mrr_actual = (panel[panel["activo"] == 1].sort_values("mes")
              .groupby("restaurant_id")["mrr_eur"].last().rename("mrr_ultimo").reset_index())
seg = seg.merge(estado, on="restaurant_id", how="left").merge(mrr_actual, on="restaurant_id", how="left")

perfil = seg.groupby("segmento").agg(
    restaurantes=("restaurant_id", "count"),
    pedidos_mes=("pedidos_mes", "mean"),
    ticket_medio=("ticket_medio", "mean"),
    meses_activo=("meses_activo", "mean"),
    tickets_mes=("tickets_mes", "mean"),
    volatilidad=("volatilidad", "mean"),
    pct_app=("pct_app", "mean"),
    pct_delivery=("pct_delivery", "mean"),
    mrr_medio=("mrr_ultimo", "mean"),
    pct_baja=("ha_causado_baja", "mean"),
).round(3)
perfil["gmv_mes_estimado"] = (perfil["pedidos_mes"] * perfil["ticket_medio"]).round(0)

# Nombres deterministas a partir del perfil, no a ojo: mayor GMV -> motor de
# volumen; del resto, mayor ticket medio -> ticket alto; del resto, mas tickets
# de soporte por mes -> alta carga de soporte; el que queda -> larga cola.
libres = list(perfil.index)
finales = {}
motor = perfil.loc[libres, "gmv_mes_estimado"].idxmax(); finales[motor] = "Motor de volumen"
libres.remove(motor)
alto = perfil.loc[libres, "ticket_medio"].idxmax(); finales[alto] = "Ticket alto"
libres.remove(alto)
soporte = perfil.loc[libres, "tickets_mes"].idxmax(); finales[soporte] = "Alta carga de soporte"
libres.remove(soporte)
finales[libres[0]] = "Larga cola"

perfil["nombre"] = [finales[s_] for s_ in perfil.index]
seg["nombre_segmento"] = seg["segmento"].map(finales)
print("\n" + perfil.to_string())
perfil.to_csv(OUT / "segmentos_perfil.csv")
seg[["restaurant_id", "segmento", "nombre_segmento"]].to_csv(OUT / "segmentos_restaurantes.csv", index=False)
RESUMEN["segmentacion"] = {
    "k_elegido": int(K),
    "silueta": round(float(mejor_s), 3),
    "criterio_k": "silueta plana; k fijado por criterio de negocio",
    "segmentos": {finales[s_]: int(perfil.loc[s_, "restaurantes"]) for s_ in perfil.index},
    "pct_baja_por_segmento": {finales[s_]: round(float(perfil.loc[s_, "pct_baja"]), 3)
                              for s_ in perfil.index},
}

# --- figura 07: pequenos multiplos, un panel por segmento
fig, axes = plt.subplots(1, mejor_k, figsize=(3.0 * mejor_k, 3.6), sharex=True, sharey=True)
axes = np.atleast_1d(axes)
for i, ax in enumerate(axes):
    ax.scatter(seg["pedidos_mes"], seg["ticket_medio"], s=9, color="#d8d7d3", linewidths=0)
    d = seg[seg["segmento"] == i]
    ax.scatter(d["pedidos_mes"], d["ticket_medio"], s=11, color=vs.BLUE, linewidths=0)
    ax.set_xscale("log")
    ax.set_title(f"{finales[i]}\n{len(d)} restaurantes", fontsize=9.5, color=vs.INK)
    ax.set_xlabel("Pedidos/mes (escala log)")
    if i == 0:
        ax.set_ylabel("Ticket medio (EUR)")
    vs.despine(ax)
    ax.grid(axis="x", visible=True)
fig.suptitle(f"{K} perfiles de restaurante en la cartera",
             x=0.02, y=0.995, ha="left", fontsize=11, fontweight="bold", color=vs.INK)
fig.text(0.02, 0.925, "En gris, toda la cartera. Los grupos se solapan en estos dos ejes "
         "porque la separacion usa seis variables de comportamiento",
         ha="left", fontsize=8.5, color=vs.INK_SOFT)
fig.tight_layout(rect=(0, 0, 1, 0.90))
vs.save(fig, FIG / "07_segmentos.png")

(OUT / "modelos_resumen.json").write_text(json.dumps(RESUMEN, indent=2, ensure_ascii=False))
print(f"\nResumen de modelos -> outputs/modelos_resumen.json")
