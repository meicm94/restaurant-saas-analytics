#!/usr/bin/env python3
"""
Week 3, Part 1: pandas
======================
Build the restaurant-month modelling panel, recalculate the core SaaS metrics
in pandas, and reconcile them with the independently generated SQL results.
Agreement between both implementations is an important metric-quality check.

Outputs:
  data/clean/restaurant_month_panel.csv
  outputs/key_metrics.json
  outputs/figures/01_mrr_and_customers.png
  outputs/figures/02_mrr_movement.png
  outputs/figures/03_retention_cohorts.png

Run: python 03_python/01_panel_and_metrics.py
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

# ----------------------------------------------------------------------
# 1. Load clean data
# ----------------------------------------------------------------------
rest = pd.read_csv(CLEAN / "dim_restaurant.csv", parse_dates=["signup_date", "signup_month"])
subs = pd.read_csv(CLEAN / "fact_subscription.csv", parse_dates=["start_date", "end_date"])
orders = pd.read_csv(CLEAN / "fact_order.csv", parse_dates=["order_date", "order_month"])
tickets = pd.read_csv(CLEAN / "fact_support_ticket.csv", parse_dates=["ticket_date", "ticket_month"])
print(
    f"Loaded: {len(rest)} restaurants, {len(orders):,} orders, "
    f"{len(subs)} subscription periods"
)

# ----------------------------------------------------------------------
# 2. Restaurant-month panel
# ----------------------------------------------------------------------
months = pd.date_range("2025-01-01", "2026-08-01", freq="MS")
month_ends = months + pd.offsets.MonthEnd(0)

# Month-end subscription snapshot, using the same convention as the SQL model.
active_subscriptions = []
for ms, me in zip(months, month_ends):
    a = subs[(subs["start_date"] <= me) &
             (subs["end_date"].isna() | (subs["end_date"] >= me))]
    a = a[["restaurant_id", "plan_id", "mrr_eur"]].copy()
    a["month"] = ms
    active_subscriptions.append(a)
active_subscriptions = pd.concat(active_subscriptions, ignore_index=True)
assert not active_subscriptions.duplicated(["restaurant_id", "month"]).any(), (
    "A restaurant has more than one active subscription in the same month"
)

panel = (
    rest[["restaurant_id", "market", "city_size", "cuisine_type", "is_chain",
          "acquisition_channel", "signup_date", "signup_month", "signup_cohort"]]
    .merge(pd.DataFrame({"month": months}), how="cross")
)
panel = panel[panel["month"] >= panel["signup_month"]].copy()
panel = panel.merge(active_subscriptions, on=["restaurant_id", "month"], how="left")
panel["is_active"] = panel["mrr_eur"].notna().astype(int)
panel["mrr_eur"] = panel["mrr_eur"].fillna(0.0)

# Monthly product activity.
completed_orders = orders[orders["order_status"] == "completed"]
monthly_activity = (
    completed_orders.groupby(["restaurant_id", "order_month"])
    .agg(
        orders=("order_id", "count"),
        gmv_eur=("order_value_eur", "sum"),
        average_order_value_eur=("order_value_eur", "mean"),
    )
    .reset_index()
    .rename(columns={"order_month": "month"})
)
monthly_cancellations = (
    orders.assign(is_cancelled=(orders["order_status"] != "completed").astype(int))
    .groupby(["restaurant_id", "order_month"])["is_cancelled"]
    .mean()
    .reset_index()
    .rename(columns={"order_month": "month", "is_cancelled": "cancellation_rate"})
)
monthly_tickets = (
    tickets.groupby(["restaurant_id", "ticket_month"])
    .agg(tickets=("ticket_id", "count"), csat=("satisfaction_score", "mean"))
    .reset_index()
    .rename(columns={"ticket_month": "month"})
)

panel = (panel.merge(monthly_activity, on=["restaurant_id", "month"], how="left")
              .merge(monthly_cancellations, on=["restaurant_id", "month"], how="left")
              .merge(monthly_tickets, on=["restaurant_id", "month"], how="left"))
for c in ["orders", "gmv_eur", "tickets"]:
    panel[c] = panel[c].fillna(0)
panel["average_order_value_eur"] = panel["average_order_value_eur"].fillna(0)
panel["cancellation_rate"] = panel["cancellation_rate"].fillna(0)
panel["csat"] = panel["csat"].fillna(np.nan)

panel["tenure_months"] = ((panel["month"].dt.year * 12 + panel["month"].dt.month)
                             - (panel["signup_month"].dt.year * 12 + panel["signup_month"].dt.month))
panel = panel.sort_values(["restaurant_id", "month"]).reset_index(drop=True)

g = panel.groupby("restaurant_id", sort=False)
panel["previous_month_orders"] = g["orders"].shift(1)
panel["rolling_3m_orders"] = g["orders"].transform(
    lambda s: s.shift(1).rolling(3, min_periods=1).mean())
panel["activity_ratio"] = panel["orders"] / panel["rolling_3m_orders"].replace(0, np.nan)
panel["cumulative_tickets"] = g["tickets"].cumsum()
# Trajectory signals: current activity relative to each restaurant's historical
# peak and recent direction of travel. These features help the churn model detect
# declining product engagement before cancellation.
panel["peak_orders"] = g["orders"].transform(lambda s: s.expanding().max())
panel["peak_order_ratio"] = panel["orders"] / panel["peak_orders"].replace(0, np.nan)
panel["trend_3m"] = (panel["rolling_3m_orders"]
                         / g["rolling_3m_orders"].shift(3).replace(0, np.nan))
panel["months_below_average"] = g["activity_ratio"].transform(
    lambda s: (s.fillna(1) < 0.85).rolling(4, min_periods=1).sum())
panel["next_month_mrr"] = g["mrr_eur"].shift(-1)
panel["next_month_active"] = g["is_active"].shift(-1)
panel["next_month_gmv"] = g["gmv_eur"].shift(-1)

# Churn label: active this month and inactive next month. The latest month is NaN.
panel["next_month_churn"] = np.where(
    panel["next_month_active"].isna(), np.nan,
    ((panel["is_active"] == 1) & (panel["next_month_active"] == 0)).astype(float))

panel.to_csv(CLEAN / "restaurant_month_panel.csv", index=False)
print(f"Restaurant-month panel: {len(panel):,} rows x {panel.shape[1]} columns "
      f"-> data/clean/restaurant_month_panel.csv")

# ----------------------------------------------------------------------
# 3. Monthly metrics in pandas and reconciliation with SQL
# ----------------------------------------------------------------------
active_panel = panel[panel["is_active"] == 1]
monthly = (active_panel.groupby("month")
           .agg(active_customers=("restaurant_id", "count"),
                mrr_eur=("mrr_eur", "sum"),
                orders=("orders", "sum"),
                gmv_eur=("gmv_eur", "sum"))
           .reset_index())
monthly["arpu_eur"] = monthly["mrr_eur"] / monthly["active_customers"]
monthly["mrr_growth_pct"] = monthly["mrr_eur"].pct_change() * 100

sql_path = OUT / "sql_results" / "04_saas_metrics__monthly_mrr_and_customers.csv"
if sql_path.exists():
    sql = pd.read_csv(sql_path, parse_dates=["month"])
    comparison = monthly.merge(sql, on="month", suffixes=("_py", "_sql"))
    mrr_diff = (comparison["mrr_eur_py"] - comparison["mrr_eur_sql"]).abs().max()
    customer_diff = (
        comparison["active_customers_py"] - comparison["active_customers_sql"]
    ).abs().max()
    print(
        f"\nPandas vs SQL reconciliation -> max MRR difference: {mrr_diff:.4f} EUR | "
        f"max customer difference: {customer_diff:.0f}"
    )
    assert mrr_diff < 0.01 and customer_diff == 0, (
        "Pandas and SQL results do not match; review metric definitions"
    )
else:
    print("\n(Run 02_sql/run_sql.py first to enable the SQL reconciliation check.)")

# MRR movement.
panel["previous_month_mrr"] = g["mrr_eur"].shift(1).fillna(0)
mrr_movement = panel.assign(
    new_mrr=np.where((panel["previous_month_mrr"] == 0) & (panel["mrr_eur"] > 0), panel["mrr_eur"], 0),
    expansion_mrr=np.where((panel["previous_month_mrr"] > 0) & (panel["mrr_eur"] > panel["previous_month_mrr"]),
                       panel["mrr_eur"] - panel["previous_month_mrr"], 0),
    contraction_mrr=np.where((panel["previous_month_mrr"] > 0) & (panel["mrr_eur"] > 0)
                         & (panel["mrr_eur"] < panel["previous_month_mrr"]),
                         panel["mrr_eur"] - panel["previous_month_mrr"], 0),
    churned_mrr=np.where((panel["previous_month_mrr"] > 0) & (panel["mrr_eur"] == 0),
                         -panel["previous_month_mrr"], 0),
).groupby("month")[["new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr"]].sum().reset_index()
mrr_movement["net_mrr"] = mrr_movement[
    ["new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr"]
].sum(axis=1)

# Monthly churn and NRR.
churn = (panel[panel["previous_month_mrr"] > 0]
      .groupby("month")
      .apply(lambda d: pd.Series({
          "opening_customers": len(d),
          "churned_customers": int((d["mrr_eur"] == 0).sum()),
          "customer_churn_pct": 100 * (d["mrr_eur"] == 0).mean(),
          "nrr_pct": 100 * d["mrr_eur"].sum() / d["previous_month_mrr"].sum(),
      }), include_groups=False)
      .reset_index())

# Retention cohorts.
cohort_panel = panel.copy()
cohort_panel["lifecycle_month"] = cohort_panel["tenure_months"]
cohort_size = cohort_panel[cohort_panel["lifecycle_month"] == 0].groupby("signup_cohort")["restaurant_id"].nunique()
retention = (cohort_panel.groupby(["signup_cohort", "lifecycle_month"])["is_active"].sum().unstack()
       .div(cohort_size, axis=0) * 100)

# ----------------------------------------------------------------------
# 4. Charts
# ----------------------------------------------------------------------
print("\nCharts")

# --- 01: MRR and active customers in separate panels.
fig, axes = plt.subplots(2, 1, figsize=(8.2, 6.2), sharex=True,
                         gridspec_kw={"hspace": 0.45})
ax = axes[0]
ax.plot(monthly["month"], monthly["mrr_eur"], color=vs.BLUE, lw=2)
ax.fill_between(monthly["month"], monthly["mrr_eur"], color=vs.BLUE, alpha=0.10)
latest_point = monthly.iloc[-1]
ax.scatter([latest_point["month"]], [latest_point["mrr_eur"]], color=vs.BLUE, s=28, zorder=3)
ax.annotate(f"EUR {latest_point['mrr_eur']:,.0f}", (latest_point["month"], latest_point["mrr_eur"]),
            textcoords="offset points", xytext=(-6, 8), ha="right",
            fontsize=9, fontweight="bold", color=vs.INK)
ax.yaxis.set_major_formatter(lambda v, p: f"{v/1000:,.0f}k")
vs.title(ax, "MRR grows steadily",
         "Monthly recurring revenue, EUR")
vs.despine(ax)

ax = axes[1]
ax.plot(monthly["month"], monthly["active_customers"], color=vs.BLUE, lw=2)
ax.scatter([latest_point["month"]], [latest_point["active_customers"]], color=vs.BLUE, s=28, zorder=3)
ax.annotate(f"{latest_point['active_customers']:,.0f}", (latest_point["month"], latest_point["active_customers"]),
            textcoords="offset points", xytext=(-6, 8), ha="right",
            fontsize=9, fontweight="bold", color=vs.INK)
vs.title(ax, "The active customer base is expanding as well",
         "Restaurants with an active subscription at month-end")
vs.despine(ax)
fig.autofmt_xdate(rotation=0, ha="center")
vs.save(fig, FIG / "01_mrr_and_customers.png")

# --- 02: MRR movement.
fig, ax = plt.subplots(figsize=(8.6, 4.6))
x = np.arange(len(mrr_movement))
w = 0.72
ax.bar(x, mrr_movement["new_mrr"], w, color=vs.BLUE, label="New")
ax.bar(x, mrr_movement["expansion_mrr"], w, bottom=mrr_movement["new_mrr"], color=vs.AQUA, label="Expansion",
       linewidth=1.6, edgecolor=vs.SURFACE)
ax.bar(x, mrr_movement["contraction_mrr"], w, color=vs.YELLOW, label="Contraction",
       linewidth=1.6, edgecolor=vs.SURFACE)
ax.bar(x, mrr_movement["churned_mrr"], w, bottom=mrr_movement["contraction_mrr"], color=vs.RED, label="Churn",
       linewidth=1.6, edgecolor=vs.SURFACE)
ax.plot(x, mrr_movement["net_mrr"], color=vs.INK, lw=1.6, marker="o", ms=3.5, label="Net")
ax.axhline(0, color=vs.INK_SOFT, lw=0.9)
ax.set_xticks(x[::2])
ax.set_xticklabels([d.strftime("%Y-%m") for d in mrr_movement["month"]][::2])
ax.yaxis.set_major_formatter(lambda v, p: f"{v/1000:,.0f}k")
vs.title(ax, "New customers are the primary source of MRR growth",
         "Monthly MRR movement, EUR; the black line shows net change")
ax.legend(ncol=5, loc="upper left", bbox_to_anchor=(0, -0.12))
vs.despine(ax)
vs.save(fig, FIG / "02_mrr_movement.png")

# --- 03: Retention cohorts.
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("blue", vs.SEQ)
m = retention.loc[:, [c for c in retention.columns if c <= 12]]
fig, ax = plt.subplots(figsize=(9.4, 6.0))
im = ax.imshow(m.values, cmap=cmap, vmin=40, vmax=100, aspect="auto")
ax.set_xticks(range(m.shape[1]), [f"M{c}" for c in m.columns])
ax.set_yticks(range(m.shape[0]), [f"{i}  (n={cohort_size[i]})" for i in m.index])
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
vs.title(ax, "Retention declines most sharply between months 2 and 6",
         "Share of restaurants still active by signup cohort and lifecycle month. "
         "M0 and M1 remain at 100% because contracts have a two-month minimum term")
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cb.outline.set_visible(False)
cb.set_label("Retention (%)", color=vs.INK_SOFT, fontsize=8)
vs.save(fig, FIG / "03_retention_cohorts.png")

# ----------------------------------------------------------------------
# 5. Key metrics for the README
# ----------------------------------------------------------------------
latest = monthly.iloc[-1]
last_12m_churn = churn[churn["month"] >= "2025-09-01"]
key_metrics = {
    "period": "2025-01 to 2026-08",
    "restaurants": int(len(rest)),
    "total_orders": int(len(orders)),
    "total_gmv_eur": round(float(completed_orders["order_value_eur"].sum()), 2),
    "latest_month_active_customers": int(latest["active_customers"]),
    "latest_month_mrr_eur": round(float(latest["mrr_eur"]), 2),
    "latest_month_arr_eur": round(float(latest["mrr_eur"] * 12), 2),
    "latest_month_arpu_eur": round(float(latest["arpu_eur"]), 2),
    "average_order_value_eur": round(float(completed_orders["order_value_eur"].mean()), 2),
    "average_monthly_churn_12m_pct": round(float(last_12m_churn["customer_churn_pct"].mean()), 2),
    "average_nrr_12m_pct": round(float(last_12m_churn["nrr_pct"].mean()), 1),
    "average_month_3_retention_pct": round(float(retention[3].dropna().mean()), 1),
    "average_month_6_retention_pct": round(float(retention[6].dropna().mean()), 1),
    "average_mrr_growth_6m_pct": round(float(monthly["mrr_growth_pct"].tail(6).mean()), 2),
}
(OUT / "key_metrics.json").write_text(json.dumps(key_metrics, indent=2, ensure_ascii=False))
print("\nKey metrics")
for k, v in key_metrics.items():
    print(f"  {k:<32} {v}")
