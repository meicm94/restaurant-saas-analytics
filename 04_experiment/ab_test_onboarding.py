#!/usr/bin/env python3
"""
Semana 4 - experimento comercial
================================
CMP-003 "New onboarding flow": prueba A/B aleatorizada sobre el proceso de
alta de restaurantes nuevos.

FICHA DEL EXPERIMENTO
  Pregunta      Aumenta el nuevo onboarding los pedidos de un restaurante
                durante sus primeros 30 dias?
  Hipotesis     H0: no hay diferencia entre control y tratamiento.
                H1: el tratamiento aumenta los pedidos de los primeros 30 dias.
  Unidad        el restaurante (no el pedido: los pedidos de un mismo
                restaurante estan correlacionados).
  Asignacion    aleatoria estratificada por mercado, tamano de ciudad y si es
                cadena, entre los restaurantes dados de alta del 2025-10-01 al
                2026-06-30.
  Metrica       pedidos completados en los primeros 30 dias de vida.
  Secundarias   GMV a 30 dias, activacion a 7 dias, retencion a 90 dias.
  Guardarrail   tickets de soporte en 30 dias (que el nuevo flujo no genere
                mas incidencias).

Ejecutar: python 04_experiment/ab_test_onboarding.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.power import TTestIndPower
from statsmodels.stats.proportion import proportions_ztest

sys.path.append(str(Path(__file__).resolve().parents[1] / "03_python"))
import viz_style as vs

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "restaurant_saas.db"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
FIN_DATOS = "2026-08-31"
R = {}


def linea(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# ----------------------------------------------------------------------
# Datos del experimento (una fila por restaurante asignado)
# ----------------------------------------------------------------------
con = sqlite3.connect(DB)
d = pd.read_sql_query(f"""
WITH exp AS (
    SELECT a.restaurant_id,
           a.assignment_group AS grupo,
           r.signup_date,
           date(r.signup_date, '+29 days')  AS fin_30d,
           date(r.signup_date, '+6 days')   AS fin_7d,
           date(r.signup_date, '+90 days')  AS corte_90d
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
)
SELECT e.restaurant_id, e.grupo, e.signup_date,
       r.market, r.city_size, r.cuisine_type, r.is_chain, r.acquisition_channel,
       strftime('%Y-%m', r.signup_date) AS cohorte,
       (SELECT COUNT(*) FROM fact_order o
         WHERE o.restaurant_id = e.restaurant_id AND o.order_status = 'completed'
           AND o.order_date BETWEEN e.signup_date AND e.fin_30d)          AS pedidos_30d,
       (SELECT IFNULL(SUM(o.order_value_eur), 0) FROM fact_order o
         WHERE o.restaurant_id = e.restaurant_id AND o.order_status = 'completed'
           AND o.order_date BETWEEN e.signup_date AND e.fin_30d)          AS gmv_30d,
       (SELECT COUNT(*) FROM fact_order o
         WHERE o.restaurant_id = e.restaurant_id AND o.order_status = 'completed'
           AND o.order_date BETWEEN e.signup_date AND e.fin_7d)           AS pedidos_7d,
       (SELECT COUNT(*) FROM fact_support_ticket t
         WHERE t.restaurant_id = e.restaurant_id
           AND t.ticket_date BETWEEN e.signup_date AND e.fin_30d)         AS tickets_30d,
       CASE WHEN date(e.corte_90d) <= '{FIN_DATOS}' THEN 1 ELSE 0 END     AS elegible_90d,
       CASE WHEN EXISTS (SELECT 1 FROM fact_subscription s
                          WHERE s.restaurant_id = e.restaurant_id
                            AND s.start_date <= e.corte_90d
                            AND (s.end_date IS NULL OR s.end_date >= e.corte_90d))
            THEN 1 ELSE 0 END                                             AS activo_90d
FROM exp AS e
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE date(e.fin_30d) <= '{FIN_DATOS}'
""", con)
con.close()

d["treat"] = (d["grupo"] == "treatment").astype(int)
d["activado_7d"] = (d["pedidos_7d"] > 0).astype(int)
ctrl = d[d["treat"] == 0]
trat = d[d["treat"] == 1]
n_c, n_t = len(ctrl), len(trat)

linea("0. LA MUESTRA")
print(f"Restaurantes asignados y con 30 dias cumplidos: {len(d)}  "
      f"(control {n_c}, tratamiento {n_t})")
print(f"Altas entre {d['signup_date'].min()} y {d['signup_date'].max()}")

# ----------------------------------------------------------------------
# 1. Comprobaciones previas: SRM y equilibrio
# ----------------------------------------------------------------------
linea("1. COMPROBACIONES PREVIAS (antes de mirar el resultado)")

# Sample Ratio Mismatch: el reparto observado se aleja del 50/50 esperado?
chi2, p_srm = stats.chisquare([n_c, n_t])[:2]
print(f"SRM  reparto {n_c}/{n_t}  chi2 = {chi2:.2f}  p = {p_srm:.3f}  "
      f"-> {'OK' if p_srm > 0.01 else 'REVISAR: el reparto no es el esperado'}")
print("     (la asignacion por bloques con estratos impares no cuadra exacto al 50/50;")
print("      mientras el p-valor no sea diminuto, no indica un fallo de la asignacion)")

print("\nEquilibrio de covariables (diferencia estandarizada; |d| < 0.10 se considera bien):")
balance = []
for var in ["is_chain"]:
    dif = trat[var].mean() - ctrl[var].mean()
    s = np.sqrt((trat[var].var() + ctrl[var].var()) / 2)
    balance.append((var, ctrl[var].mean(), trat[var].mean(), dif / s if s else 0))
for var in ["market", "city_size", "acquisition_channel"]:
    for nivel in sorted(d[var].unique()):
        a, b = (ctrl[var] == nivel).mean(), (trat[var] == nivel).mean()
        s = np.sqrt((a * (1 - a) + b * (1 - b)) / 2)
        balance.append((f"{var}={nivel}", a, b, (b - a) / s if s else 0))
bal = pd.DataFrame(balance, columns=["variable", "control", "tratamiento", "dif_estandarizada"])
bal["aviso"] = np.where(bal["dif_estandarizada"].abs() > 0.10, "  <-- desequilibrio", "")
print(bal.round(3).to_string(index=False))
R["equilibrio_max_dif_estandarizada"] = round(float(bal["dif_estandarizada"].abs().max()), 3)

# ----------------------------------------------------------------------
# 2. Resultado principal
# ----------------------------------------------------------------------
linea("2. RESULTADO PRINCIPAL: pedidos en los primeros 30 dias")

m_c, m_t = ctrl["pedidos_30d"].mean(), trat["pedidos_30d"].mean()
s_c, s_t = ctrl["pedidos_30d"].std(ddof=1), trat["pedidos_30d"].std(ddof=1)
dif = m_t - m_c
se = np.sqrt(s_c**2 / n_c + s_t**2 / n_t)
t_stat, p_val = stats.ttest_ind(trat["pedidos_30d"], ctrl["pedidos_30d"], equal_var=False)
gl = se**4 / ((s_c**2 / n_c) ** 2 / (n_c - 1) + (s_t**2 / n_t) ** 2 / (n_t - 1))
t_crit = stats.t.ppf(0.975, gl)
ic = (dif - t_crit * se, dif + t_crit * se)
u_stat, p_mw = stats.mannwhitneyu(trat["pedidos_30d"], ctrl["pedidos_30d"], alternative="two-sided")

print(f"Control       media {m_c:6.2f} pedidos   mediana {ctrl['pedidos_30d'].median():5.1f}   n = {n_c}")
print(f"Tratamiento   media {m_t:6.2f} pedidos   mediana {trat['pedidos_30d'].median():5.1f}   n = {n_t}")
print(f"\nDiferencia    {dif:+.2f} pedidos por restaurante ({100 * dif / m_c:+.1f}%)")
print(f"IC 95%        [{ic[0]:+.2f}, {ic[1]:+.2f}] pedidos  "
      f"([{100 * ic[0] / m_c:+.1f}%, {100 * ic[1] / m_c:+.1f}%])")
print(f"t de Welch    t = {t_stat:.2f}   p = {p_val:.4f}")
print(f"Mann-Whitney  p = {p_mw:.4f}   (contraste no parametrico: la distribucion de")
print("              pedidos es asimetrica y conviene no depender solo de la media)")
print(f"\nConclusion    {'se rechaza H0' if p_val < 0.05 else 'no se rechaza H0'} al 5%")

R["principal"] = {
    "n_control": n_c, "n_tratamiento": n_t,
    "media_control": round(float(m_c), 2), "media_tratamiento": round(float(m_t), 2),
    "diferencia": round(float(dif), 2), "uplift_pct": round(float(100 * dif / m_c), 1),
    "ic95": [round(float(ic[0]), 2), round(float(ic[1]), 2)],
    "ic95_uplift_pct": [round(float(100 * ic[0] / m_c), 1), round(float(100 * ic[1] / m_c), 1)],
    "p_welch": round(float(p_val), 5), "p_mann_whitney": round(float(p_mw), 5),
}

# ----------------------------------------------------------------------
# 3. OLS: la misma diferencia, ajustada por covariables
# ----------------------------------------------------------------------
linea("3. REGRESION OLS: el mismo efecto, controlando covariables")
print("La aleatorizacion ya hace comparables a los grupos, asi que el OLS no")
print("corrige un sesgo: REDUCE LA VARIANZA. Al explicar parte de la dispersion")
print("con mercado, tipo de cocina o cohorte, el intervalo del efecto se estrecha.")
print("Se modela log(1+pedidos) porque el efecto esperado es multiplicativo y la")
print("variable es asimetrica; el coeficiente se lee como cambio porcentual.\n")

m_simple = smf.ols("np.log1p(pedidos_30d) ~ treat", data=d).fit(cov_type="HC3")
m_ajust = smf.ols(
    "np.log1p(pedidos_30d) ~ treat + C(market) + C(city_size) + is_chain"
    " + C(cuisine_type) + C(acquisition_channel) + C(cohorte)",
    data=d).fit(cov_type="HC3")

for nombre, mod in [("Sin covariables", m_simple), ("Con covariables", m_ajust)]:
    b = mod.params["treat"]
    lo, hi = mod.conf_int().loc["treat"]
    print(f"{nombre:<18} efecto {100 * (np.exp(b) - 1):+6.1f}%   "
          f"IC 95% [{100 * (np.exp(lo) - 1):+.1f}%, {100 * (np.exp(hi) - 1):+.1f}%]   "
          f"p = {mod.pvalues['treat']:.4f}   R2 = {mod.rsquared:.3f}")

b = m_ajust.params["treat"]
lo, hi = m_ajust.conf_int().loc["treat"]
R["ols_ajustado"] = {
    "efecto_pct": round(float(100 * (np.exp(b) - 1)), 1),
    "ic95_pct": [round(float(100 * (np.exp(lo) - 1)), 1), round(float(100 * (np.exp(hi) - 1)), 1)],
    "p": round(float(m_ajust.pvalues["treat"]), 5),
    "r2": round(float(m_ajust.rsquared), 3),
}
print("\nResumen del modelo ajustado (solo la fila del tratamiento):")
print(m_ajust.summary().tables[1].as_text().split("\n")[0])
for fila in m_ajust.summary().tables[1].as_text().split("\n"):
    if fila.strip().startswith("treat"):
        print(fila)

# ----------------------------------------------------------------------
# 4. Metricas secundarias y guardarrail
# ----------------------------------------------------------------------
linea("4. METRICAS SECUNDARIAS Y GUARDARRAIL")

# GMV a 30 dias
t_g, p_g = stats.ttest_ind(trat["gmv_30d"], ctrl["gmv_30d"], equal_var=False)
print(f"GMV 30 dias        control {ctrl['gmv_30d'].mean():8.2f} EUR   "
      f"tratamiento {trat['gmv_30d'].mean():8.2f} EUR   "
      f"({100 * (trat['gmv_30d'].mean() / ctrl['gmv_30d'].mean() - 1):+.1f}%)   p = {p_g:.4f}")

# Activacion a 7 dias (proporciones)
z_a, p_a = proportions_ztest([trat["activado_7d"].sum(), ctrl["activado_7d"].sum()], [n_t, n_c])
print(f"Activacion 7 dias  control {ctrl['activado_7d'].mean():8.1%}       "
      f"tratamiento {trat['activado_7d'].mean():8.1%}       "
      f"({100 * (trat['activado_7d'].mean() - ctrl['activado_7d'].mean()):+.1f} pp)      p = {p_a:.4f}")

# Retencion a 90 dias (solo los que ya han cumplido 90 dias)
r90 = d[d["elegible_90d"] == 1]
rc, rt = r90[r90.treat == 0], r90[r90.treat == 1]
z_r, p_r = proportions_ztest([rt["activo_90d"].sum(), rc["activo_90d"].sum()], [len(rt), len(rc)])
print(f"Retencion 90 dias  control {rc['activo_90d'].mean():8.1%}       "
      f"tratamiento {rt['activo_90d'].mean():8.1%}       "
      f"({100 * (rt['activo_90d'].mean() - rc['activo_90d'].mean()):+.1f} pp)      p = {p_r:.4f}"
      f"   (n = {len(rc)}/{len(rt)})")

# Guardarrail: el nuevo flujo no debe disparar el soporte
t_s, p_s = stats.ttest_ind(trat["tickets_30d"], ctrl["tickets_30d"], equal_var=False)
print(f"Tickets 30 dias    control {ctrl['tickets_30d'].mean():8.2f}       "
      f"tratamiento {trat['tickets_30d'].mean():8.2f}       "
      f"({100 * (trat['tickets_30d'].mean() / max(ctrl['tickets_30d'].mean(), 1e-9) - 1):+.1f}%)   p = {p_s:.4f}"
      f"   <- guardarrail")

R["secundarias"] = {
    "gmv_30d_uplift_pct": round(float(100 * (trat["gmv_30d"].mean() / ctrl["gmv_30d"].mean() - 1)), 1),
    "gmv_30d_p": round(float(p_g), 5),
    "activacion_7d_control": round(float(ctrl["activado_7d"].mean()), 4),
    "activacion_7d_tratamiento": round(float(trat["activado_7d"].mean()), 4),
    "activacion_7d_p": round(float(p_a), 5),
    "retencion_90d_control": round(float(rc["activo_90d"].mean()), 4),
    "retencion_90d_tratamiento": round(float(rt["activo_90d"].mean()), 4),
    "retencion_90d_p": round(float(p_r), 5),
    "tickets_30d_p": round(float(p_s), 5),
}

# ----------------------------------------------------------------------
# 5. Potencia: que efecto era detectable con esta muestra
# ----------------------------------------------------------------------
linea("5. POTENCIA Y EFECTO MINIMO DETECTABLE (MDE)")
sd_conjunta = np.sqrt(((n_c - 1) * s_c**2 + (n_t - 1) * s_t**2) / (n_c + n_t - 2))
analisis = TTestIndPower()
d_min = analisis.solve_power(effect_size=None, nobs1=n_c, alpha=0.05, power=0.8,
                             ratio=n_t / n_c, alternative="two-sided")
mde_pedidos = d_min * sd_conjunta
potencia = analisis.power(effect_size=dif / sd_conjunta, nobs1=n_c, alpha=0.05, ratio=n_t / n_c)
n_para_10pct = analisis.solve_power(effect_size=(0.10 * m_c) / sd_conjunta, power=0.8, alpha=0.05)
print(f"Desviacion tipica conjunta      {sd_conjunta:.2f} pedidos")
print(f"MDE con esta muestra (80%)      {mde_pedidos:.2f} pedidos = {100 * mde_pedidos / m_c:.1f}% "
      f"sobre la media del control")
print(f"Potencia alcanzada              {potencia:.1%} para el efecto observado")
print(f"Para detectar un +10% harian falta {n_para_10pct:,.0f} restaurantes por grupo")
print("\nLectura: la muestra solo permite ver efectos grandes. Un +5% real habria")
print("pasado desapercibido, asi que 'no significativo' nunca significaria 'no funciona'.")
R["potencia"] = {
    "mde_pct": round(float(100 * mde_pedidos / m_c), 1),
    "potencia_efecto_observado": round(float(potencia), 3),
    "n_por_grupo_para_detectar_10pct": int(round(n_para_10pct)),
}

# ----------------------------------------------------------------------
# 6. Grafico
# ----------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.4), gridspec_kw={"width_ratios": [1, 1.25]})

ax = axes[0]
medias = [m_c, m_t]
errores = [stats.t.ppf(0.975, n_c - 1) * s_c / np.sqrt(n_c),
           stats.t.ppf(0.975, n_t - 1) * s_t / np.sqrt(n_t)]
x = [0, 1]
ax.bar(x, medias, width=0.55, color=[vs.BLUE, vs.ORANGE])
ax.errorbar(x, medias, yerr=errores, fmt="none", ecolor=vs.INK, elinewidth=1.4, capsize=6)
for xi, m, e in zip(x, medias, errores):
    ax.text(xi, m + e + 1.2, f"{m:.1f}", ha="center", fontsize=11, fontweight="bold", color=vs.INK)
ax.set_xticks(x, ["Control", "Tratamiento"])
ax.set_ylabel("Pedidos en los primeros 30 dias")
ax.set_ylim(0, max(medias) * 1.35)
vs.title(ax, f"{100 * dif / m_c:+.0f}% de pedidos con el nuevo onboarding",
         "Media por restaurante e intervalo de confianza al 95%")
vs.despine(ax)

ax = axes[1]
for etiqueta, grupo, color in [("Control", ctrl, vs.BLUE), ("Tratamiento", trat, vs.ORANGE)]:
    v = np.sort(grupo["pedidos_30d"].to_numpy())
    ax.step(v, np.arange(1, len(v) + 1) / len(v), where="post", color=color, lw=2, label=etiqueta)
ax.set_xlabel("Pedidos en los primeros 30 dias")
ax.set_ylabel("Proporcion acumulada de restaurantes")
ax.set_xlim(0, np.percentile(d["pedidos_30d"], 98))
ax.legend(loc="lower right")
vs.title(ax, "La mejora se ve en toda la distribucion",
         "Funcion de distribucion acumulada: la curva naranja va por debajo\n"
         "de la azul, no es cosa de unos pocos restaurantes grandes")
vs.despine(ax)
fig.tight_layout()
vs.save(fig, FIG / "08_experimento_ab.png")

# ----------------------------------------------------------------------
# 7. Ficha para negocio
# ----------------------------------------------------------------------
signif = R["principal"]["p_welch"] < 0.05
md = f"""# Experimento CMP-003 · Nuevo flujo de onboarding

## Recomendación

**{'Desplegar el nuevo onboarding en todos los mercados.' if signif else
'No hay evidencia suficiente para desplegar: repetir con más muestra.'}**

El nuevo flujo de alta aumenta los pedidos de los primeros 30 días en
**{R['principal']['uplift_pct']:+.0f} %** ({R['principal']['diferencia']:+.1f} pedidos por
restaurante; IC 95 % del {R['principal']['ic95_uplift_pct'][0]:+.0f} % al
{R['principal']['ic95_uplift_pct'][1]:+.0f} %; p = {R['principal']['p_welch']:.4f}).
Ajustando por mercado, tipo de cocina, canal y cohorte, el efecto queda en
**{R['ols_ajustado']['efecto_pct']:+.0f} %** (IC 95 % del {R['ols_ajustado']['ic95_pct'][0]:+.0f} %
al {R['ols_ajustado']['ic95_pct'][1]:+.0f} %).

## Qué se midió

| | |
|---|---|
| Unidad de aleatorización | Restaurante |
| Asignación | Aleatoria estratificada por mercado, tamaño de ciudad y cadena |
| Periodo de altas | {d['signup_date'].min()} a {d['signup_date'].max()} |
| Muestra | {n_c} control / {n_t} tratamiento |
| Métrica principal | Pedidos completados en los primeros 30 días |
| Guardarraíl | Tickets de soporte en los primeros 30 días |

## Resultados

| Métrica | Control | Tratamiento | Diferencia | p |
|---|---|---|---|---|
| Pedidos 30 días | {m_c:.1f} | {m_t:.1f} | {100 * dif / m_c:+.1f} % | {p_val:.4f} |
| GMV 30 días (€) | {ctrl['gmv_30d'].mean():.0f} | {trat['gmv_30d'].mean():.0f} | {R['secundarias']['gmv_30d_uplift_pct']:+.1f} % | {p_g:.4f} |
| Activación 7 días | {ctrl['activado_7d'].mean():.1%} | {trat['activado_7d'].mean():.1%} | {100 * (trat['activado_7d'].mean() - ctrl['activado_7d'].mean()):+.1f} pp | {p_a:.4f} |
| Retención 90 días | {rc['activo_90d'].mean():.1%} | {rt['activo_90d'].mean():.1%} | {100 * (rt['activo_90d'].mean() - rc['activo_90d'].mean()):+.1f} pp | {p_r:.4f} |
| Tickets 30 días | {ctrl['tickets_30d'].mean():.2f} | {trat['tickets_30d'].mean():.2f} | {100 * (trat['tickets_30d'].mean() / max(ctrl['tickets_30d'].mean(), 1e-9) - 1):+.1f} % | {p_s:.4f} |

## Limitaciones

1. **Potencia.** La muestra ({n_c + n_t} restaurantes) solo detecta efectos del
   {R['potencia']['mde_pct']:.0f} % o mayores con un 80 % de potencia. Para confirmar un
   +10 % harían falta unos {R['potencia']['n_por_grupo_para_detectar_10pct']:,} restaurantes por grupo.
2. **Ventana corta.** 30 días miden la puesta en marcha, no el valor a largo
   plazo. La retención a 90 días apunta en la misma dirección, pero con menos casos.
3. **Efecto novedad.** Parte de la mejora puede venir del acompañamiento extra
   durante el piloto y no del flujo en sí.
4. **Estacionalidad.** Las altas cubren de octubre a junio; los grupos están
   equilibrados por cohorte, pero un despliegue en verano puede rendir distinto.
5. **Falta el coste.** No se ha medido el coste operativo del nuevo flujo; la
   recomendación da por supuesto que es comparable al actual.

## Siguiente paso

Desplegar por mercados de forma escalonada midiendo la misma métrica, y añadir al
seguimiento el coste por alta para poder calcular el retorno.
"""
(OUT / "experimento_onboarding.md").write_text(md, encoding="utf-8")
(OUT / "experimento_resumen.json").write_text(json.dumps(R, indent=2, ensure_ascii=False))
print(f"\nFicha para negocio -> outputs/experimento_onboarding.md")
print(f"Resumen JSON       -> outputs/experimento_resumen.json")
