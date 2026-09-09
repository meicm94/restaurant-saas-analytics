#!/usr/bin/env python3
"""
Week 3, Part 2: scikit-learn
================================
Train three models on the restaurant-month panel, each answering a different
business question:

  1. LINEAR REGRESSION   -> How much GMV will a restaurant generate next month?
                            (commission-revenue planning)
  2. LOGISTIC REGRESSION -> How likely is a restaurant to churn next month?
                            (prioritised retention outreach)
  3. K-MEANS CLUSTERING  -> Which behavioural customer profiles exist?
                            (segmentation for pricing and account management)

Methodological choices:
  * Use a temporal holdout for regression: train on the past and test on the
    latest months. A random split on panel data can leak future information.
  * Exclude all next-month variables from the feature set.
  * Keep preprocessing inside each Pipeline so that scaling and encoding are
    learned independently within every validation fold.
  * Compare the forecast with a transparent naive baseline. A model that does
    not improve on the baseline does not create practical value.

Outputs: outputs/model_summary.json, outputs/segment_profiles.csv, and figures 04-07.
Run: python 03_python/02_models.py
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
SUMMARY = {}

panel = pd.read_csv(CLEAN / "restaurant_month_panel.csv", parse_dates=["month", "signup_date", "signup_month"])
# Calendar month captures seasonality: demand peaks in December and softens in
# July and August. Without it, the model cannot improve on a naive forecast.
panel["calendar_month"] = panel["month"].dt.month.astype(str)
orders = pd.read_csv(CLEAN / "fact_order.csv", parse_dates=["order_date"])
CUTOFF = pd.Timestamp("2026-05-01")  # Train through April; test from May onward.

NUM = ["orders", "gmv_eur", "average_order_value_eur", "tickets", "cumulative_tickets",
       "tenure_months", "rolling_3m_orders", "activity_ratio",
       "cancellation_rate", "mrr_eur", "peak_order_ratio", "trend_3m",
       "months_below_average"]
CAT = ["market", "city_size", "cuisine_type", "acquisition_channel", "plan_id"]
# Calendar month is used only for GMV regression, where seasonality is material.
# In the churn model it adds sparse dummy variables without improving risk ranking.
CAT_REG = CAT + ["calendar_month"]
BIN = ["is_chain"]


def build_preprocessor(cat=None):
    cat = CAT if cat is None else cat
    return ColumnTransformer([
        ("num", StandardScaler(), NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False), cat),
        ("bin", "passthrough", BIN),
    ])


def feature_names(pre, cat=None):
    cat = CAT if cat is None else cat
    output = list(NUM)
    output += list(pre.named_transformers_["cat"].get_feature_names_out(cat))
    output += BIN
    return output


# ======================================================================
# 1. LINEAR REGRESSION - next-month GMV
# ======================================================================
print("=" * 78)
print("1. LINEAR REGRESSION - next-month GMV")
print("=" * 78)

reg = panel[(panel["is_active"] == 1) &
            (panel["next_month_active"] == 1) &
            panel["next_month_gmv"].notna()].copy()
for c in ["activity_ratio", "peak_order_ratio", "trend_3m"]:
    reg[c] = reg[c].fillna(1.0)
reg = reg.dropna(subset=["rolling_3m_orders"])

tr = reg[reg["month"] < CUTOFF]
te = reg[reg["month"] >= CUTOFF]
X_tr, y_tr = tr[NUM + CAT_REG + BIN], tr["next_month_gmv"]
X_te, y_te = te[NUM + CAT_REG + BIN], te["next_month_gmv"]
print(f"Training: {len(tr):,} rows (through {tr['month'].max():%Y-%m}) | "
      f"Test: {len(te):,} rows (from {te['month'].min():%Y-%m})")

regression_model = Pipeline([("pre", build_preprocessor(CAT_REG)), ("lm", LinearRegression())])
regression_model.fit(X_tr, y_tr)
pred = regression_model.predict(X_te)

# Naive baseline: next month will equal the current month.
baseline = te["gmv_eur"].to_numpy()
cv = cross_val_score(regression_model, X_tr, y_tr, cv=TimeSeriesSplit(n_splits=5), scoring="r2")

regression_metrics = {
    "test_r2": round(float(r2_score(y_te, pred)), 3),
    "test_mae_eur": round(float(mean_absolute_error(y_te, pred)), 2),
    "test_rmse_eur": round(float(root_mean_squared_error(y_te, pred)), 2),
    "baseline_r2": round(float(r2_score(y_te, baseline)), 3),
    "baseline_mae_eur": round(float(mean_absolute_error(y_te, baseline)), 2),
    "mean_cross_validation_r2": round(float(cv.mean()), 3),
    "std_cross_validation_r2": round(float(cv.std()), 3),
    "train_rows": int(len(tr)),
    "test_rows": int(len(te)),
}
SUMMARY["gmv_regression"] = regression_metrics
for k, v in regression_metrics.items():
    print(f"  {k:<32} {v}")
print(f"  MAE improvement over baseline: "
      f"{100 * (1 - regression_metrics['test_mae_eur'] / regression_metrics['baseline_mae_eur']):.1f}%")

fig, ax = plt.subplots(figsize=(6.4, 5.6))
lim = float(np.percentile(np.concatenate([y_te, pred]), 99.5))
ax.scatter(y_te, pred, s=14, color=vs.BLUE, alpha=0.45, linewidths=0)
ax.plot([0, lim], [0, lim], color=vs.INK_SOFT, lw=1.2, ls="--")
ax.set_xlim(0, lim); ax.set_ylim(0, lim)
ax.set_xlabel("Actual next-month GMV (EUR)")
ax.set_ylabel("Predicted next-month GMV (EUR)")
ax.annotate(f"R² = {regression_metrics['test_r2']:.2f}\nMAE = EUR {regression_metrics['test_mae_eur']:,.0f}",
            (0.04, 0.92), xycoords="axes fraction", va="top", fontsize=9.5,
            fontweight="bold", color=vs.INK)
vs.title(ax, "The model explains next-month GMV",
         f"Test period: {te['month'].min():%Y-%m} to {te['month'].max():%Y-%m}; "
         "the diagonal represents a perfect prediction")
vs.despine(ax)
ax.grid(axis="x", visible=True)
vs.save(fig, FIG / "04_gmv_regression.png")

# ======================================================================
# 2. LOGISTIC REGRESSION - next-month churn
# ======================================================================
print("\n" + "=" * 78)
print("2. LOGISTIC REGRESSION - next-month churn probability")
print("=" * 78)

clf_df = panel[(panel["is_active"] == 1) & panel["next_month_churn"].notna()].copy()
for c in ["activity_ratio", "peak_order_ratio", "trend_3m"]:
    clf_df[c] = clf_df[c].fillna(1.0)
clf_df = clf_df.dropna(subset=["rolling_3m_orders"])
clf_df["y"] = clf_df["next_month_churn"].astype(int)

tr = clf_df[clf_df["month"] < CUTOFF]
te = clf_df[clf_df["month"] >= CUTOFF]
X_tr, y_tr = tr[NUM + CAT + BIN], tr["y"]
X_te, y_te = te[NUM + CAT + BIN], te["y"]
print(f"Training: {len(tr):,} rows, {y_tr.sum()} churn events ({y_tr.mean():.1%}) | "
      f"Test: {len(te):,} rows, {y_te.sum()} churn events ({y_te.mean():.1%})")
print("  The target is highly imbalanced: class_weight='balanced' is applied.")
print("  Evaluation prioritises AUC and precision-recall over raw accuracy.")

classification_model = Pipeline([
    ("pre", build_preprocessor()),
    ("lr", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
])
cv_auc = cross_val_score(classification_model, X_tr, y_tr, cv=StratifiedKFold(5, shuffle=True, random_state=42),
                         scoring="roc_auc")
classification_model.fit(X_tr, y_tr)
proba = classification_model.predict_proba(X_te)[:, 1]
THRESHOLD = 0.5
pred_clf = (proba >= THRESHOLD).astype(int)
cm = confusion_matrix(y_te, pred_clf)

classification_metrics = {
    "mean_cross_validation_auc": round(float(cv_auc.mean()), 3),
    "std_cross_validation_auc": round(float(cv_auc.std()), 3),
    "test_auc": round(float(roc_auc_score(y_te, proba)), 3),
    "test_average_precision": round(float(average_precision_score(y_te, proba)), 3),
    "test_churn_base_rate": round(float(y_te.mean()), 4),
    "precision": round(float(precision_score(y_te, pred_clf, zero_division=0)), 3),
    "recall": round(float(recall_score(y_te, pred_clf)), 3),
    "accuracy": round(float(accuracy_score(y_te, pred_clf)), 3),
    "threshold": THRESHOLD,
}
SUMMARY["churn_classification"] = classification_metrics
for k, v in classification_metrics.items():
    print(f"  {k:<32} {v}")

# Business value: measure how much churn the retention team can reach if it
# contacts only the highest-risk 10% of the portfolio.
ranking = np.argsort(-proba)
top10 = ranking[: max(1, int(0.10 * len(ranking)))]
capture = y_te.to_numpy()[top10].sum() / max(y_te.sum(), 1)
lift = capture / 0.10
SUMMARY["churn_classification"]["churn_capture_at_top_10pct"] = round(float(capture), 3)
SUMMARY["churn_classification"]["lift_at_top_10pct"] = round(float(lift), 2)
print(f"  churn_capture_at_top_10pct              {capture:.1%}  (lift x{lift:.1f} vs random selection)")

# --- Figure 05: confusion matrix.
fig, ax = plt.subplots(figsize=(5.4, 4.6))
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("blue", vs.SEQ)
ax.imshow(cm / cm.sum(axis=1, keepdims=True), cmap=cmap, vmin=0, vmax=1)
labels = ["Retained", "Churned"]
ax.set_xticks([0, 1], [f"Predicted:\n{label.lower()}" for label in labels])
ax.set_yticks([0, 1], [f"Actual:\n{label.lower()}" for label in labels])
for i in range(2):
    for j in range(2):
        pct = cm[i, j] / cm[i].sum()
        ax.text(j, i, f"{cm[i, j]:,}\n{pct:.0%} of row", ha="center", va="center",
                fontsize=10, fontweight="bold", color="white" if pct > 0.55 else vs.INK)
ax.set_xticks(np.arange(-.5, 2, 1), minor=True)
ax.set_yticks(np.arange(-.5, 2, 1), minor=True)
ax.grid(which="minor", color=vs.SURFACE, linewidth=3)
ax.grid(which="major", visible=False)
ax.tick_params(which="both", length=0)
for s in ax.spines.values():
    s.set_visible(False)
vs.title(ax, f"The model identifies {classification_metrics['recall']:.0%} of churn events",
         f"Confusion matrix for the test period at a {THRESHOLD:.1f} threshold")
vs.save(fig, FIG / "05_churn_confusion_matrix.png")

# --- Figure 06: standardised numerical coefficients and odds ratios.
pre = classification_model.named_steps["pre"]
coef = pd.DataFrame({"variable": feature_names(pre),
                     "coef": classification_model.named_steps["lr"].coef_[0]})
coef["odds_ratio"] = np.exp(coef["coef"])
# Plot only standardised numerical variables, whose coefficients are directly
# comparable as one-standard-deviation effects. All categorical coefficients
# remain available in the exported CSV.
DISPLAY_NAMES = {
    "orders": "Current-month orders",
    "gmv_eur": "Current-month GMV",
    "average_order_value_eur": "Average order value",
    "tickets": "Monthly support tickets",
    "peak_order_ratio": "Orders vs historical peak",
    "trend_3m": "Three-month trend",
    "months_below_average": "Months below recent average",
    "cumulative_tickets": "Cumulative support tickets",
    "tenure_months": "Tenure (months)",
    "rolling_3m_orders": "Three-month average orders",
    "activity_ratio": "Activity vs recent average",
    "cancellation_rate": "Cancellation rate",
    "mrr_eur": "MRR",
}
top = coef[coef["variable"].isin(NUM)].copy().sort_values("coef")
top["label"] = top["variable"].map(DISPLAY_NAMES)

fig, ax = plt.subplots(figsize=(7.8, 5.2))
colors = [vs.RED if c > 0 else vs.BLUE for c in top["coef"]]
ax.barh(top["label"], top["coef"], color=colors, height=0.68)
ax.axvline(0, color=vs.INK_SOFT, lw=0.9)
margin = 0.16 * max(top["coef"].abs().max(), 0.1)
for y, (c, orr) in enumerate(zip(top["coef"], top["odds_ratio"])):
    ax.text(c + (margin * 0.18 if c > 0 else -margin * 0.18), y, f"x{orr:.2f}",
            va="center", ha="left" if c > 0 else "right", fontsize=8, color=vs.INK_SOFT)
ax.set_xlim(top["coef"].min() - margin, top["coef"].max() + margin)
ax.set_xlabel("Coefficient (log-odds); values to the right indicate higher churn risk")
# Joint interpretation: current-month orders are protective while a high prior
# three-month average increases risk when current activity is weak. Together,
# these correlated variables describe a downward trajectory rather than size.
or_month = float(coef.loc[coef["variable"] == "orders", "odds_ratio"].iloc[0])
or_media = float(coef.loc[coef["variable"] == "rolling_3m_orders", "odds_ratio"].iloc[0])
vs.title(ax, "Declining engagement—not customer size—signals churn",
         f"Higher current activity is protective (x{or_month:.2f} per standard deviation), while a "
         f"strong prior average followed by a weak month raises risk (x{or_media:.2f}).\n"
         "Together they describe a downward trajectory; labels show odds ratios")
vs.despine(ax, left=True)
ax.grid(axis="x", visible=True)
ax.grid(axis="y", visible=False)
vs.save(fig, FIG / "06_churn_coefficients.png")
coef.sort_values("coef", ascending=False).to_csv(OUT / "churn_coefficients.csv", index=False)

# ======================================================================
# 3. K-MEANS CLUSTERING - portfolio segmentation
# ======================================================================
print("\n" + "=" * 78)
print("3. K-MEANS CLUSTERING - restaurant segmentation")
print("=" * 78)

completed_orders = orders[orders["order_status"] == "completed"]
order_profile = completed_orders.groupby("restaurant_id").agg(
    pct_app=("order_channel", lambda s: (s == "app").mean()),
    pct_delivery=("fulfilment_type", lambda s: (s == "delivery").mean()),
).reset_index()

active_panel = panel[panel["is_active"] == 1]
seg = active_panel.groupby("restaurant_id").agg(
    monthly_orders=("orders", "mean"),
    average_order_value=("average_order_value_eur", "mean"),
    active_months=("month", "count"),
    monthly_tickets=("tickets", "mean"),
    volatility=("orders", lambda s: s.std() / max(s.mean(), 1)),
).reset_index().merge(order_profile, on="restaurant_id", how="left").fillna(0)

# Use behavioural features only. Tenure is intentionally excluded; otherwise,
# K-Means mainly separates new from mature customers instead of uncovering
# commercially useful behaviour profiles.
seg = seg[(seg["active_months"] >= 3) & (seg["monthly_orders"] > 0)].reset_index(drop=True)
VARS = ["monthly_orders", "average_order_value", "monthly_tickets", "volatility",
        "pct_app", "pct_delivery"]
Xs = seg[VARS].copy()
Xs["monthly_orders"] = np.log1p(Xs["monthly_orders"])  # Strong right skew.
Xs["average_order_value"] = np.log1p(Xs["average_order_value"])
Xs = StandardScaler().fit_transform(Xs)

print("  k   silhouette")
silhouette_scores = {}
for k in range(2, 7):
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xs)
    silhouette_scores[k] = silhouette_score(Xs, km.labels_)
    print(f"  {k}   {silhouette_scores[k]:.3f}")

# Silhouette scores are broadly flat, which indicates overlapping customer
# behaviours rather than naturally isolated clusters. Four segments are used as
# a pragmatic balance between analytical resolution and commercial usability.
K = 4
print(f"  -> Silhouette is broadly flat for k=2 to k=6 (max {max(silhouette_scores.values()):.3f}).")
print(f"     Selected k={K} as a practical choice for distinct commercial playbooks.")

km = KMeans(n_clusters=K, n_init=10, random_state=42).fit(Xs)
best_k, best_silhouette = K, silhouette_scores[K]
seg["segment"] = km.labels_

churn_status = (panel.groupby("restaurant_id")["next_month_churn"].max()
          .rename("has_churned").reset_index())
current_mrr = (panel[panel["is_active"] == 1].sort_values("month")
              .groupby("restaurant_id")["mrr_eur"].last().rename("mrr_latest").reset_index())
seg = seg.merge(churn_status, on="restaurant_id", how="left").merge(current_mrr, on="restaurant_id", how="left")

segment_profile = seg.groupby("segment").agg(
    restaurants=("restaurant_id", "count"),
    monthly_orders=("monthly_orders", "mean"),
    average_order_value=("average_order_value", "mean"),
    active_months=("active_months", "mean"),
    monthly_tickets=("monthly_tickets", "mean"),
    volatility=("volatility", "mean"),
    pct_app=("pct_app", "mean"),
    pct_delivery=("pct_delivery", "mean"),
    average_mrr=("mrr_latest", "mean"),
    churn_pct=("has_churned", "mean"),
).round(3)
segment_profile["estimated_monthly_gmv"] = (segment_profile["monthly_orders"] * segment_profile["average_order_value"]).round(0)

# Assign deterministic business labels from the segment profiles: highest GMV,
# highest order value, highest support intensity, and the remaining long tail.
remaining = list(segment_profile.index)
segment_names = {}
volume_driver = segment_profile.loc[remaining, "estimated_monthly_gmv"].idxmax(); segment_names[volume_driver] = "Volume Engine"
remaining.remove(volume_driver)
high_value = segment_profile.loc[remaining, "average_order_value"].idxmax(); segment_names[high_value] = "High-Value Orders"
remaining.remove(high_value)
support_intensive = segment_profile.loc[remaining, "monthly_tickets"].idxmax(); segment_names[support_intensive] = "Support Intensive"
remaining.remove(support_intensive)
segment_names[remaining[0]] = "Long Tail"

segment_profile["name"] = [segment_names[s_] for s_ in segment_profile.index]
seg["segment_name"] = seg["segment"].map(segment_names)
print("\n" + segment_profile.to_string())
segment_profile.to_csv(OUT / "segment_profiles.csv")
seg[["restaurant_id", "segment", "segment_name"]].to_csv(OUT / "restaurant_segments.csv", index=False)
SUMMARY["segmentation"] = {
    "selected_k": int(K),
    "silhouette": round(float(best_silhouette), 3),
    "k_selection_rationale": "Silhouette scores were broadly flat; k=4 was selected for commercial usability.",
    "segments": {segment_names[s_]: int(segment_profile.loc[s_, "restaurants"]) for s_ in segment_profile.index},
    "churn_pct_by_segment": {segment_names[s_]: round(float(segment_profile.loc[s_, "churn_pct"]), 3)
                              for s_ in segment_profile.index},
}

# --- Figure 07: one small multiple per segment.
fig, axes = plt.subplots(1, best_k, figsize=(3.0 * best_k, 3.6), sharex=True, sharey=True)
axes = np.atleast_1d(axes)
for i, ax in enumerate(axes):
    ax.scatter(seg["monthly_orders"], seg["average_order_value"], s=9, color="#d8d7d3", linewidths=0)
    d = seg[seg["segment"] == i]
    ax.scatter(d["monthly_orders"], d["average_order_value"], s=11, color=vs.BLUE, linewidths=0)
    ax.set_xscale("log")
    ax.set_title(f"{segment_names[i]}\n{len(d)} restaurants", fontsize=9.5, color=vs.INK)
    ax.set_xlabel("Orders/month (log scale)")
    if i == 0:
        ax.set_ylabel("Average order value (EUR)")
    vs.despine(ax)
    ax.grid(axis="x", visible=True)
fig.suptitle(f"{K} behavioural profiles in the restaurant portfolio",
             x=0.02, y=0.995, ha="left", fontsize=11, fontweight="bold", color=vs.INK)
fig.text(0.02, 0.925, "Grey points show the full portfolio. Segments overlap on these two axes "
         "because clustering uses six behavioural variables.",
         ha="left", fontsize=8.5, color=vs.INK_SOFT)
fig.tight_layout(rect=(0, 0, 1, 0.90))
vs.save(fig, FIG / "07_segments.png")

(OUT / "model_summary.json").write_text(json.dumps(SUMMARY, indent=2, ensure_ascii=False))
print("\nModel summary -> outputs/model_summary.json")
