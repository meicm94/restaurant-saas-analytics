#!/usr/bin/env python3
"""
Restaurant SaaS Revenue, Retention & Experimentation Analytics
--------------------------------------------------------------
Paso 1: generacion del dataset ficticio (datos "crudos", con suciedad
intencionada para practicar limpieza en Power Query / pandas).

Simula una plataforma SaaS que vende a restaurantes un sistema de pedidos
online de marca propia:
  - los restaurantes pagan una suscripcion mensual (MRR)
  - procesan pedidos a traves de la plataforma (GMV) y pagan comision
  - abren tickets de soporte
  - algunos cancelan (churn)
  - una campana de onboarding se lanza como experimento A/B aleatorizado

Salida: data/raw/**  (CSV crudos)
Ejecutar:  python 01_data/generate_raw_data.py
"""
from __future__ import annotations

import calendar
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
(RAW / "orders").mkdir(parents=True, exist_ok=True)

N_RESTAURANTS = 600
PERIOD_START = pd.Timestamp("2025-01-01")
PERIOD_END = pd.Timestamp("2026-08-31")

# ----------------------------------------------------------------------
# Catalogos
# ----------------------------------------------------------------------
MARKETS = {
    #        peso   multiplicador de demanda  multiplicador de churn
    "DK": (0.42, 1.00, 1.00),
    "UK": (0.24, 1.15, 1.20),
    "DE": (0.16, 0.95, 1.10),
    "NO": (0.10, 0.90, 0.85),
    "SE": (0.08, 0.92, 0.95),
}
CITIES = {
    "DK": ["Copenhagen", "Aarhus", "Odense", "Aalborg", "Esbjerg"],
    "UK": ["London", "Manchester", "Birmingham", "Leeds", "Bristol"],
    "DE": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt"],
    "NO": ["Oslo", "Bergen", "Trondheim", "Stavanger"],
    "SE": ["Stockholm", "Gothenburg", "Malmo", "Uppsala"],
}
CUISINES = {
    #               peso  demanda  ticket medio (EUR)
    "Pizza":       (0.22, 1.20, 26.0),
    "Sushi":       (0.12, 0.85, 42.0),
    "Burger":      (0.15, 1.10, 24.0),
    "Kebab":       (0.14, 1.25, 19.0),
    "Thai":        (0.10, 0.90, 33.0),
    "Indian":      (0.09, 0.95, 31.0),
    "Chinese":     (0.08, 1.00, 28.0),
    "Nordic":      (0.05, 0.65, 55.0),
    "Vegetarian":  (0.05, 0.70, 29.0),
}
PLANS = {
    # plan_id, nombre, precio mensual EUR, comision sobre GMV, multiplicador demanda
    "PL-01": ("Starter", 49.0, 0.030, 0.90),
    "PL-02": ("Growth", 99.0, 0.020, 1.00),
    "PL-03": ("Pro", 199.0, 0.012, 1.15),
    "PL-04": ("Enterprise", 349.0, 0.006, 1.35),
}
PLAN_ORDER = ["PL-01", "PL-02", "PL-03", "PL-04"]
CHANNELS = ["Direct sales", "Inbound", "Partner", "Referral", "Paid search"]
CHURN_REASONS = [
    ("Precio", 0.24),
    ("Poco volumen de pedidos", 0.28),
    ("Se pasa a la competencia", 0.16),
    ("Cierra el negocio", 0.14),
    ("Insatisfaccion con el servicio", 0.11),
    ("Impago", 0.07),
]
SEASONALITY = {1: 0.92, 2: 0.95, 3: 1.00, 4: 1.02, 5: 1.05, 6: 0.98,
               7: 0.88, 8: 0.90, 9: 1.04, 10: 1.08, 11: 1.10, 12: 1.20}
WEEKDAY_W = np.array([0.11, 0.10, 0.11, 0.13, 0.19, 0.21, 0.15])  # lun..dom
RAMP = np.array([0.55, 0.78, 0.92, 1.00, 1.03, 1.05])             # curva de arranque

# Experimento A/B de onboarding
EXP_ID = "CMP-003"
EXP_FROM = pd.Timestamp("2025-10-01")
EXP_TO = pd.Timestamp("2026-06-30")
TRUE_UPLIFT = 0.35          # efecto real sobre pedidos en los primeros 30 dias
TRUE_UPLIFT_RETENTION = 0.70  # multiplicador de churn en los 3 primeros meses


def month_start(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.replace(day=1)


def month_end(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.replace(day=calendar.monthrange(ts.year, ts.month)[1])


def add_month(ts: pd.Timestamp) -> pd.Timestamp:
    return month_start(ts) + pd.offsets.MonthBegin(1)


# ----------------------------------------------------------------------
# 1. Restaurantes
# ----------------------------------------------------------------------
market_keys = list(MARKETS)
market_p = np.array([MARKETS[m][0] for m in market_keys])
market_p = market_p / market_p.sum()

cuisine_keys = list(CUISINES)
cuisine_p = np.array([CUISINES[c][0] for c in cuisine_keys])
cuisine_p = cuisine_p / cuisine_p.sum()

# meses de alta: de 2025-01 a 2026-07 con tendencia creciente de captacion
signup_months = pd.date_range("2025-01-01", "2026-08-01", freq="MS")
signup_w = np.linspace(1.0, 2.1, len(signup_months))
signup_w = signup_w / signup_w.sum()

restaurants = []
for i in range(N_RESTAURANTS):
    rid = f"R-{i + 1:04d}"
    market = rng.choice(market_keys, p=market_p)
    city = rng.choice(CITIES[market])
    cuisine = rng.choice(cuisine_keys, p=cuisine_p)
    city_size = rng.choice(["Metro", "Mid", "Small"], p=[0.45, 0.35, 0.20])
    size_mult = {"Metro": 1.25, "Mid": 1.0, "Small": 0.78}[city_size]
    is_chain = int(rng.random() < 0.18)

    m0 = rng.choice(len(signup_months), p=signup_w)
    base_month = pd.Timestamp(signup_months[m0])
    day = int(rng.integers(1, calendar.monthrange(base_month.year, base_month.month)[1] + 1))
    signup = base_month.replace(day=day)

    demand = (
        rng.lognormal(mean=np.log(32), sigma=0.55)   # pedidos/mes en regimen
        * MARKETS[market][1]
        * CUISINES[cuisine][1]
        * size_mult
        * (1.45 if is_chain else 1.0)
    )
    aov_mu = np.log(CUISINES[cuisine][2] * rng.normal(1.0, 0.10))
    # plan inicial correlacionado con el tamano esperado
    if demand > 72:
        p_plan = [0.02, 0.20, 0.48, 0.30]
    elif demand > 42:
        p_plan = [0.10, 0.46, 0.36, 0.08]
    elif demand > 23:
        p_plan = [0.32, 0.50, 0.17, 0.01]
    else:
        p_plan = [0.62, 0.33, 0.05, 0.00]

    restaurants.append(
        dict(
            restaurant_id=rid,
            restaurant_name=f"{cuisine} {city} {i + 1:04d}",
            market=market,
            city=city,
            city_size=city_size,
            cuisine_type=cuisine,
            is_chain=is_chain,
            acquisition_channel=rng.choice(CHANNELS, p=[0.34, 0.22, 0.14, 0.16, 0.14]),
            signup_date=signup,
            base_demand=demand,
            aov_mu=aov_mu,
            aov_sigma=float(rng.uniform(0.28, 0.45)),
            app_share=float(np.clip(rng.normal(0.55, 0.15), 0.15, 0.9)),
            delivery_share=float(np.clip(rng.normal(0.62, 0.18), 0.1, 0.95)),
            ticket_prone=float(rng.gamma(2.0, 0.18)),
            initial_plan=rng.choice(PLAN_ORDER, p=p_plan),
            frailty=float(rng.normal(0, 0.55)),  # heterogeneidad no observada en churn
        )
    )

rest = pd.DataFrame(restaurants)

# Asignacion del experimento de onboarding
# Aleatorizacion ESTRATIFICADA (block randomization) por mercado, tamano de
# ciudad y si es cadena: dentro de cada estrato se alterna control/tratamiento
# sobre un orden aleatorio. Es lo que se hace en la practica cuando la muestra
# es pequena y las covariables pesan mucho, y evita que el azar deje un grupo
# con muchos mas restaurantes grandes que el otro.
eligible = rest["signup_date"].between(EXP_FROM, EXP_TO).to_numpy()
strata = (rest["market"] + "|" + rest["city_size"] + "|" + rest["is_chain"].astype(str)).to_numpy()
groups = np.array([None] * len(rest), dtype=object)
elig_idx = np.where(eligible)[0]
for s in np.unique(strata[elig_idx]):
    idx = rng.permutation(elig_idx[strata[elig_idx] == s])
    labels = np.resize(np.array(["control", "treatment"]), len(idx))
    if rng.random() < 0.5:      # alterna el arranque del bloque para no
        labels = labels[::-1]   # sesgar sistematicamente el tamano de los grupos
    groups[idx] = labels
rest["exp_group"] = [g if isinstance(g, str) else None for g in groups]

# ----------------------------------------------------------------------
# 2. Bucle mensual: suscripciones, pedidos, tickets, churn
# ----------------------------------------------------------------------
sub_rows, order_rows, ticket_rows = [], [], []
order_seq = 0
sub_seq = 0
ticket_seq = 0

for r in rest.itertuples(index=False):
    plan = r.initial_plan
    discount = float(rng.choice([0.0, 0.0, 0.0, 0.0, 0.10, 0.15, 0.20]))
    spell_start = r.signup_date
    sub_seq += 1
    sub_id = f"S-{sub_seq:05d}"

    cur = month_start(r.signup_date)
    m = 0
    # "salud" latente del restaurante: paseo aleatorio que hace que el negocio
    # gane o pierda tiron con el tiempo. Es lo que produce trayectorias de
    # caida sostenida antes de una baja, en lugar de bajas puramente aleatorias.
    health = 0.0
    churned = False
    churn_date = None
    last_orders = None

    while cur <= PERIOD_END and not churned:
        m_start = max(cur, r.signup_date)
        m_end = min(month_end(cur), PERIOD_END)
        if m_start > m_end:
            break
        days_active = (m_end - m_start).days + 1
        days_in_month = calendar.monthrange(cur.year, cur.month)[1]

        health = float(np.clip(health + rng.normal(0, 0.16), -1.6, 0.7))
        ramp = RAMP[min(m, len(RAMP) - 1)]
        trend = 1.0 + 0.008 * ((cur.year - 2025) * 12 + cur.month - 1)
        lam = (
            r.base_demand
            * ramp
            * SEASONALITY[cur.month]
            * trend
            * PLANS[plan][3]
            * np.exp(health)
            * (days_active / days_in_month)
        )

        # efecto real del nuevo onboarding: solo los primeros 30 dias de vida
        if isinstance(r.exp_group, str) and r.exp_group == "treatment":
            win_end = r.signup_date + timedelta(days=30)
            overlap = (min(m_end, win_end) - m_start).days + 1
            frac = max(0.0, overlap) / max(days_active, 1)
            lam *= 1.0 + TRUE_UPLIFT * min(frac, 1.0)

        n_orders = int(rng.poisson(max(lam, 0.5)))

        if n_orders > 0:
            offsets = np.arange(days_active)
            dows = np.array([(m_start + timedelta(days=int(o))).weekday() for o in offsets])
            w = WEEKDAY_W[dows]
            w = w / w.sum()
            chosen = rng.choice(offsets, size=n_orders, p=w)
            dates = [m_start + timedelta(days=int(o)) for o in chosen]
            weekend = np.isin([d.weekday() for d in dates], [4, 5, 6])
            values = rng.lognormal(r.aov_mu, r.aov_sigma, n_orders) * np.where(weekend, 1.08, 1.0)
            values = np.round(np.clip(values, 6.0, 400.0), 2)
            status = rng.choice(
                ["completed", "cancelled", "refunded"], size=n_orders, p=[0.955, 0.033, 0.012]
            )
            is_app = rng.random(n_orders) < r.app_share
            is_del = rng.random(n_orders) < r.delivery_share
            for k in range(n_orders):
                order_seq += 1
                order_rows.append(
                    (
                        f"ORD-{order_seq:07d}",
                        r.restaurant_id,
                        dates[k].date().isoformat(),
                        float(values[k]),
                        "app" if is_app[k] else "web",
                        "delivery" if is_del[k] else "pickup",
                        status[k],
                    )
                )

        # tickets de soporte
        n_tickets = int(rng.poisson(r.ticket_prone * (1.9 if m == 0 else 1.0)))
        for _ in range(n_tickets):
            ticket_seq += 1
            d = m_start + timedelta(days=int(rng.integers(0, days_active)))
            ticket_rows.append(
                (
                    f"T-{ticket_seq:06d}",
                    r.restaurant_id,
                    d.date().isoformat(),
                    rng.choice(
                        ["Tecnico", "Facturacion", "Onboarding", "Menu", "Pagos"],
                        p=[0.34, 0.20, 0.18, 0.17, 0.11],
                    ),
                    round(float(rng.gamma(2.0, 6.0)), 1),
                    int(rng.choice([1, 2, 3, 4, 5], p=[0.05, 0.09, 0.18, 0.36, 0.32])),
                )
            )

        # --- decision de churn al cierre de mes ---
        expected = r.base_demand * ramp * SEASONALITY[cur.month] * (days_active / days_in_month)
        activity_ratio = n_orders / max(expected, 1.0)
        z = (
            -3.60
            + 0.50 * r.frailty
            - 4.20 * health
            + 2.60 * max(0.0, 0.80 - activity_ratio)
            + 0.50 * (plan == "PL-01")
            - 0.35 * (plan in ("PL-03", "PL-04"))
            - 0.090 * m
            + 0.42 * n_tickets
            - 0.40 * r.is_chain
            + np.log(MARKETS[r.market][2])
        )
        p_churn = 1 / (1 + np.exp(-z))
        if isinstance(r.exp_group, str) and r.exp_group == "treatment" and m <= 2:
            p_churn *= TRUE_UPLIFT_RETENTION

        end_of_month = month_end(cur)
        # m >= 1: el contrato tiene una permanencia minima de dos meses, asi que
        # la primera baja posible se materializa al cierre del segundo mes.
        if m >= 1 and rng.random() < p_churn and end_of_month <= PERIOD_END:
            churned = True
            churn_date = end_of_month
            reason = rng.choice(
                [c[0] for c in CHURN_REASONS], p=[c[1] for c in CHURN_REASONS]
            )
            sub_rows.append(
                dict(
                    subscription_id=sub_id,
                    restaurant_id=r.restaurant_id,
                    plan_id=plan,
                    start_date=spell_start,
                    end_date=churn_date,
                    discount_pct=discount,
                    mrr_eur=round(PLANS[plan][1] * (1 - discount), 2),
                    end_type="churn",
                    churn_reason=reason,
                )
            )
            break

        # --- cambio de plan (upgrade / downgrade) ---
        idx = PLAN_ORDER.index(plan)
        p_up = 0.020 + 0.05 * max(0.0, activity_ratio - 1.15)
        p_down = 0.010 + 0.05 * max(0.0, 0.70 - activity_ratio)
        roll = rng.random()
        new_plan = plan
        if m >= 2 and roll < p_up and idx < 3:
            new_plan = PLAN_ORDER[idx + 1]
        elif m >= 2 and roll > 1 - p_down and idx > 0:
            new_plan = PLAN_ORDER[idx - 1]

        if new_plan != plan and end_of_month < PERIOD_END:
            sub_rows.append(
                dict(
                    subscription_id=sub_id,
                    restaurant_id=r.restaurant_id,
                    plan_id=plan,
                    start_date=spell_start,
                    end_date=end_of_month,
                    discount_pct=discount,
                    mrr_eur=round(PLANS[plan][1] * (1 - discount), 2),
                    end_type="upgrade" if PLAN_ORDER.index(new_plan) > idx else "downgrade",
                    churn_reason=None,
                )
            )
            plan = new_plan
            spell_start = end_of_month + timedelta(days=1)
            sub_seq += 1
            sub_id = f"S-{sub_seq:05d}"

        last_orders = n_orders
        cur = add_month(cur)
        m += 1

    if not churned:
        sub_rows.append(
            dict(
                subscription_id=sub_id,
                restaurant_id=r.restaurant_id,
                plan_id=plan,
                start_date=spell_start,
                end_date=pd.NaT,
                discount_pct=discount,
                mrr_eur=round(PLANS[plan][1] * (1 - discount), 2),
                end_type="active",
                churn_reason=None,
            )
        )

subs = pd.DataFrame(sub_rows).sort_values(["restaurant_id", "start_date"]).reset_index(drop=True)
orders = pd.DataFrame(
    order_rows,
    columns=["order_id", "restaurant_id", "order_date", "order_value_eur",
             "order_channel", "fulfilment_type", "order_status"],
)
tickets = pd.DataFrame(
    ticket_rows,
    columns=["ticket_id", "restaurant_id", "ticket_date", "category",
             "resolution_hours", "satisfaction_score"],
)

# ----------------------------------------------------------------------
# 3. Campanas
# ----------------------------------------------------------------------
campaigns = pd.DataFrame(
    [
        dict(campaign_id="CMP-001", campaign_name="Referral push Q3 2025",
             campaign_type="referral", start_date="2025-07-01", end_date="2025-09-30",
             budget_eur=45000, is_experiment=0),
        dict(campaign_id="CMP-002", campaign_name="Winback DK 2026",
             campaign_type="winback", start_date="2026-01-15", end_date="2026-03-15",
             budget_eur=28000, is_experiment=0),
        dict(campaign_id=EXP_ID, campaign_name="New onboarding flow (A/B test)",
             campaign_type="onboarding", start_date=EXP_FROM.date().isoformat(),
             end_date=EXP_TO.date().isoformat(), budget_eur=60000, is_experiment=1),
    ]
)

assign_rows = []
for r in rest.itertuples(index=False):
    if isinstance(r.exp_group, str):   # pandas convierte None en NA, no en None
        assign_rows.append(
            dict(campaign_id=EXP_ID, restaurant_id=r.restaurant_id,
                 assignment_group=r.exp_group, assigned_date=r.signup_date.date().isoformat())
        )
    if pd.Timestamp("2025-07-01") <= r.signup_date <= pd.Timestamp("2025-09-30") and rng.random() < 0.45:
        assign_rows.append(
            dict(campaign_id="CMP-001", restaurant_id=r.restaurant_id,
                 assignment_group="targeted", assigned_date=r.signup_date.date().isoformat()))
churned_dk = subs.query("end_type == 'churn'").merge(
    rest[["restaurant_id", "market"]], on="restaurant_id"
).query("market == 'DK'")["restaurant_id"].unique()
for rid in churned_dk:
    if rng.random() < 0.5:
        assign_rows.append(dict(campaign_id="CMP-002", restaurant_id=rid,
                                assignment_group="targeted", assigned_date="2026-01-15"))
assignments = pd.DataFrame(assign_rows)

plans_df = pd.DataFrame(
    [dict(plan_id=k, plan_name=v[0], monthly_price_eur=v[1], commission_rate=v[2])
     for k, v in PLANS.items()]
)

# ----------------------------------------------------------------------
# 4. Ensuciar y escribir los CSV crudos
# ----------------------------------------------------------------------
def dirty_restaurants(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["restaurant_id", "restaurant_name", "market", "city", "city_size",
              "cuisine_type", "is_chain", "acquisition_channel", "signup_date"]].copy()
    long_market = {"DK": "Denmark", "UK": "United Kingdom", "DE": "Germany",
                   "NO": "Norway", "SE": "Sweden"}
    mk = out["market"].to_numpy(copy=True)
    roll = rng.random(len(out))
    mk = np.where(roll < 0.12, [long_market[m] for m in out["market"]], mk)
    mk = np.where((roll >= 0.12) & (roll < 0.22), [m.lower() for m in out["market"]], mk)
    out["market"] = mk
    pad = rng.random(len(out))
    out["city"] = [f"  {c} " if p < 0.15 else (c.upper() if p > 0.93 else c)
                   for c, p in zip(out["city"], pad)]
    d = pd.to_datetime(out["signup_date"])
    fmt = rng.random(len(out))
    out["signup_date"] = [
        dt.strftime("%d/%m/%Y") if f < 0.25 else dt.strftime("%Y-%m-%d")
        for dt, f in zip(d, fmt)
    ]
    miss = rng.random(len(out)) < 0.04
    out.loc[miss, "cuisine_type"] = rng.choice(["", "N/A", "unknown"], size=int(miss.sum()))
    dupes = out.sample(6, random_state=SEED)
    return pd.concat([out, dupes], ignore_index=True)


def dirty_subscriptions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["start_date"] = pd.to_datetime(out["start_date"]).dt.strftime("%Y-%m-%d")
    end = pd.to_datetime(out["end_date"])
    fill = rng.random(len(out))
    out["end_date"] = [
        "" if pd.isna(e) and f < 0.5 else ("NULL" if pd.isna(e) else e.strftime("%Y-%m-%d"))
        for e, f in zip(end, fill)
    ]
    price_fmt = rng.random(len(out))
    out["mrr_eur"] = [
        f"{v:.2f}".replace(".", ",") + " EUR" if p < 0.3 else f"{v:.2f}"
        for v, p in zip(out["mrr_eur"], price_fmt)
    ]
    out["plan_id"] = [f" {p}" if rng.random() < 0.1 else p for p in out["plan_id"]]
    out["churn_reason"] = out["churn_reason"].fillna("")
    return out


rest_raw = dirty_restaurants(rest)
subs_raw = dirty_subscriptions(subs)

RAW.mkdir(parents=True, exist_ok=True)
rest_raw.to_csv(RAW / "restaurants_raw.csv", index=False)
subs_raw.to_csv(RAW / "subscriptions_raw.csv", index=False)
tickets.to_csv(RAW / "support_tickets_raw.csv", index=False)
campaigns.to_csv(RAW / "campaigns_raw.csv", index=False)
assignments.to_csv(RAW / "campaign_assignments_raw.csv", index=False)
plans_df.to_csv(RAW / "plans_raw.csv", index=False)

# pedidos: un fichero por mes (patron "combinar archivos de una carpeta" en Power Query)
orders["_month"] = orders["order_date"].str.slice(0, 7)
comma_months = {"2025-03", "2025-04", "2025-11", "2026-02"}   # decimales con coma
dupe_months = {"2025-06", "2026-05"}                           # filas duplicadas
for month, g in orders.groupby("_month", sort=True):
    g = g.drop(columns="_month").copy()
    if month in comma_months:
        g["order_value_eur"] = g["order_value_eur"].map(lambda v: f"{v:.2f}".replace(".", ","))
    else:
        g["order_value_eur"] = g["order_value_eur"].map(lambda v: f"{v:.2f}")
    case = rng.random(len(g))
    g["order_status"] = [
        s.upper() if c < 0.08 else (s.capitalize() if c > 0.94 else s)
        for s, c in zip(g["order_status"], case)
    ]
    if month in dupe_months and len(g) > 20:
        g = pd.concat([g, g.sample(max(3, int(len(g) * 0.004)), random_state=SEED)],
                      ignore_index=True)
    g.to_csv(RAW / "orders" / f"orders_{month}.csv", index=False)

n_files = len(list((RAW / 'orders').glob('*.csv')))
print(f"Restaurantes .......... {len(rest):>7,}")
print(f"Suscripciones ......... {len(subs):>7,}  (activas: {(subs.end_type == 'active').sum():,})")
print(f"Pedidos ............... {len(orders):>7,}  en {n_files} ficheros mensuales")
print(f"Tickets de soporte .... {len(tickets):>7,}")
print(f"Asignaciones campana .. {len(assignments):>7,}")
print(f"Grupo experimento ..... {rest['exp_group'].value_counts().to_dict()}")
print(f"CSV crudos escritos en: {RAW}")
