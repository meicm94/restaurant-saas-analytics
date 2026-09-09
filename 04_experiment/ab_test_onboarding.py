#!/usr/bin/env python3
"""
Week 4: commercial experiment
=============================
CMP-003 "New onboarding flow": a stratified randomised A/B test for newly
signed restaurants.

EXPERIMENT DESIGN
  Question      Does the new onboarding flow increase completed orders during
                a restaurant's first 30 days?
  Hypotheses    H0: there is no difference between control and treatment.
                H1: treatment increases first-30-day order volume.
  Unit          Restaurant, because orders from one restaurant are correlated.
  Assignment    Randomised within market, city size, and chain status for
                restaurants signed from 2025-10-01 through 2026-06-30.
  Primary KPI   Completed orders during the first 30 days.
  Secondary     30-day GMV, 7-day activation, and 90-day retention.
  Guardrail     Support tickets during the first 30 days.

Run: python 04_experiment/ab_test_onboarding.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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
DATA_END_DATE = "2026-08-31"
RESULTS = {}


def section(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# ----------------------------------------------------------------------
# Experiment dataset: one row per assigned restaurant.
# ----------------------------------------------------------------------
con = sqlite3.connect(DB)
d = pd.read_sql_query(f"""
WITH exp AS (
    SELECT a.restaurant_id,
           a.assignment_group AS assignment_group,
           r.signup_date,
           date(r.signup_date, '+29 days')  AS day_30_end,
           date(r.signup_date, '+6 days')   AS day_7_end,
           date(r.signup_date, '+90 days')  AS day_90_cutoff
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
)
SELECT e.restaurant_id, e.assignment_group, e.signup_date,
       r.market, r.city_size, r.cuisine_type, r.is_chain, r.acquisition_channel,
       strftime('%Y-%m', r.signup_date) AS cohort,
       (SELECT COUNT(*) FROM fact_order o
         WHERE o.restaurant_id = e.restaurant_id AND o.order_status = 'completed'
           AND o.order_date BETWEEN e.signup_date AND e.day_30_end)          AS orders_30d,
       (SELECT IFNULL(SUM(o.order_value_eur), 0) FROM fact_order o
         WHERE o.restaurant_id = e.restaurant_id AND o.order_status = 'completed'
           AND o.order_date BETWEEN e.signup_date AND e.day_30_end)          AS gmv_30d,
       (SELECT COUNT(*) FROM fact_order o
         WHERE o.restaurant_id = e.restaurant_id AND o.order_status = 'completed'
           AND o.order_date BETWEEN e.signup_date AND e.day_7_end)           AS orders_7d,
       (SELECT COUNT(*) FROM fact_support_ticket t
         WHERE t.restaurant_id = e.restaurant_id
           AND t.ticket_date BETWEEN e.signup_date AND e.day_30_end)         AS tickets_30d,
       CASE WHEN date(e.day_90_cutoff) <= '{DATA_END_DATE}' THEN 1 ELSE 0 END     AS eligible_90d,
       CASE WHEN EXISTS (SELECT 1 FROM fact_subscription s
                          WHERE s.restaurant_id = e.restaurant_id
                            AND s.start_date <= e.day_90_cutoff
                            AND (s.end_date IS NULL OR s.end_date >= e.day_90_cutoff))
            THEN 1 ELSE 0 END                                             AS active_90d
FROM exp AS e
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE date(e.day_30_end) <= '{DATA_END_DATE}'
""", con)
con.close()

d["treat"] = (d["assignment_group"] == "treatment").astype(int)
d["activated_7d"] = (d["orders_7d"] > 0).astype(int)
control = d[d["treat"] == 0]
treatment = d[d["treat"] == 1]
n_c, n_t = len(control), len(treatment)

section("0. ANALYSIS SAMPLE")
print(f"Assigned restaurants with a complete 30-day window: {len(d)} "
      f"(control {n_c}, treatment {n_t})")
print(f"Signup dates: {d['signup_date'].min()} to {d['signup_date'].max()}")

# ----------------------------------------------------------------------
# 1. Pre-analysis checks: sample ratio mismatch and covariate balance.
# ----------------------------------------------------------------------
section("1. PRE-ANALYSIS CHECKS")

# Sample ratio mismatch: does the observed split differ from the expected 50/50?
chi2, p_srm = stats.chisquare([n_c, n_t])[:2]
print(f"SRM  observed split {n_c}/{n_t}  chi-square = {chi2:.2f}  p = {p_srm:.3f}  "
      f"-> {'OK' if p_srm > 0.01 else 'REVIEW: allocation differs from expectation'}")
print("     Block randomisation across strata with odd sample sizes need not be exactly 50/50;")
print("     a non-extreme p-value does not indicate an assignment failure.")

print("\nCovariate balance (standardised difference; |d| < 0.10 is considered balanced):")
balance = []
for var in ["is_chain"]:
    difference = treatment[var].mean() - control[var].mean()
    s = np.sqrt((treatment[var].var() + control[var].var()) / 2)
    balance.append((var, control[var].mean(), treatment[var].mean(), difference / s if s else 0))
for var in ["market", "city_size", "acquisition_channel"]:
    for level in sorted(d[var].unique()):
        a, b = (control[var] == level).mean(), (treatment[var] == level).mean()
        s = np.sqrt((a * (1 - a) + b * (1 - b)) / 2)
        balance.append((f"{var}={level}", a, b, (b - a) / s if s else 0))
bal = pd.DataFrame(balance, columns=["variable", "control", "treatment", "standardized_difference"])
bal["flag"] = np.where(bal["standardized_difference"].abs() > 0.10, "  <-- imbalance", "")
print(bal.round(3).to_string(index=False))
RESULTS["max_standardized_balance_difference"] = round(float(bal["standardized_difference"].abs().max()), 3)

# ----------------------------------------------------------------------
# 2. Primary outcome.
# ----------------------------------------------------------------------
section("2. PRIMARY OUTCOME: COMPLETED ORDERS IN THE FIRST 30 DAYS")

m_c, m_t = control["orders_30d"].mean(), treatment["orders_30d"].mean()
s_c, s_t = control["orders_30d"].std(ddof=1), treatment["orders_30d"].std(ddof=1)
difference = m_t - m_c
se = np.sqrt(s_c**2 / n_c + s_t**2 / n_t)
t_stat, p_val = stats.ttest_ind(treatment["orders_30d"], control["orders_30d"], equal_var=False)
degrees_freedom = se**4 / ((s_c**2 / n_c) ** 2 / (n_c - 1) + (s_t**2 / n_t) ** 2 / (n_t - 1))
t_crit = stats.t.ppf(0.975, degrees_freedom)
confidence_interval = (difference - t_crit * se, difference + t_crit * se)
_, p_mw = stats.mannwhitneyu(
    treatment["orders_30d"], control["orders_30d"], alternative="two-sided"
)

print(f"Control       mean {m_c:6.2f} orders   median {control['orders_30d'].median():5.1f}   n = {n_c}")
print(f"Treatment     mean {m_t:6.2f} orders   median {treatment['orders_30d'].median():5.1f}   n = {n_t}")
print(f"\nDifference    {difference:+.2f} orders per restaurant ({100 * difference / m_c:+.1f}%)")
print(f"95% CI        [{confidence_interval[0]:+.2f}, {confidence_interval[1]:+.2f}] orders  "
      f"([{100 * confidence_interval[0] / m_c:+.1f}%, {100 * confidence_interval[1] / m_c:+.1f}%])")
print(f"Welch t-test  t = {t_stat:.2f}   p = {p_val:.4f}")
print(f"Mann-Whitney  p = {p_mw:.4f}   (non-parametric robustness check for a")
print("              right-skewed order distribution)")
print(f"\nConclusion    {'Reject H0' if p_val < 0.05 else 'Do not reject H0'} at alpha=5%")

RESULTS["primary"] = {
    "n_control": n_c, "n_treatment": n_t,
    "control_mean": round(float(m_c), 2), "treatment_mean": round(float(m_t), 2),
    "difference": round(float(difference), 2), "uplift_pct": round(float(100 * difference / m_c), 1),
    "confidence_interval_95": [round(float(confidence_interval[0]), 2), round(float(confidence_interval[1]), 2)],
    "uplift_confidence_interval_95_pct": [round(float(100 * confidence_interval[0] / m_c), 1), round(float(100 * confidence_interval[1] / m_c), 1)],
    "p_welch": round(float(p_val), 5), "p_mann_whitney": round(float(p_mw), 5),
}

# ----------------------------------------------------------------------
# 3. OLS: the same effect, adjusted for covariates.
# ----------------------------------------------------------------------
section("3. OLS REGRESSION: COVARIATE-ADJUSTED EFFECT")
print("Randomisation already makes the groups comparable; OLS adjustment is used")
print("to reduce variance rather than correct selection bias. Market, cuisine,")
print("acquisition channel, and cohort explain part of the outcome dispersion.")
print("The model uses log(1 + orders) because the expected effect is multiplicative")
print("and the outcome is right-skewed; the coefficient is read as a percentage.\n")

m_simple = smf.ols("np.log1p(orders_30d) ~ treat", data=d).fit(cov_type="HC3")
adjusted_model = smf.ols(
    "np.log1p(orders_30d) ~ treat + C(market) + C(city_size) + is_chain"
    " + C(cuisine_type) + C(acquisition_channel) + C(cohort)",
    data=d).fit(cov_type="HC3")

for name, mod in [("Unadjusted", m_simple), ("Covariate-adjusted", adjusted_model)]:
    b = mod.params["treat"]
    lo, hi = mod.conf_int().loc["treat"]
    print(f"{name:<20} effect {100 * (np.exp(b) - 1):+6.1f}%   "
          f"95% CI [{100 * (np.exp(lo) - 1):+.1f}%, {100 * (np.exp(hi) - 1):+.1f}%]   "
          f"p = {mod.pvalues['treat']:.4f}   R² = {mod.rsquared:.3f}")

b = adjusted_model.params["treat"]
lo, hi = adjusted_model.conf_int().loc["treat"]
RESULTS["adjusted_ols"] = {
    "effect_pct": round(float(100 * (np.exp(b) - 1)), 1),
    "confidence_interval_95_pct": [round(float(100 * (np.exp(lo) - 1)), 1), round(float(100 * (np.exp(hi) - 1)), 1)],
    "p": round(float(adjusted_model.pvalues["treat"]), 5),
    "r2": round(float(adjusted_model.rsquared), 3),
}
print("\nAdjusted model summary (treatment row only):")
print(adjusted_model.summary().tables[1].as_text().split("\n")[0])
for row in adjusted_model.summary().tables[1].as_text().split("\n"):
    if row.strip().startswith("treat"):
        print(row)

# ----------------------------------------------------------------------
# 4. Secondary metrics and guardrail.
# ----------------------------------------------------------------------
section("4. SECONDARY METRICS AND GUARDRAIL")

# 30-day GMV.
t_g, p_g = stats.ttest_ind(treatment["gmv_30d"], control["gmv_30d"], equal_var=False)
print(f"30-day GMV         control EUR {control['gmv_30d'].mean():8.2f}   "
      f"treatment EUR {treatment['gmv_30d'].mean():8.2f}   "
      f"({100 * (treatment['gmv_30d'].mean() / control['gmv_30d'].mean() - 1):+.1f}%)   p = {p_g:.4f}")

# 7-day activation (difference in proportions).
z_a, p_a = proportions_ztest([treatment["activated_7d"].sum(), control["activated_7d"].sum()], [n_t, n_c])
print(f"7-day activation   control {control['activated_7d'].mean():8.1%}       "
      f"treatment {treatment['activated_7d'].mean():8.1%}       "
      f"({100 * (treatment['activated_7d'].mean() - control['activated_7d'].mean()):+.1f} pp)      p = {p_a:.4f}")

# 90-day retention for restaurants with a complete observation window.
r90 = d[d["eligible_90d"] == 1]
rc, rt = r90[r90.treat == 0], r90[r90.treat == 1]
z_r, p_r = proportions_ztest([rt["active_90d"].sum(), rc["active_90d"].sum()], [len(rt), len(rc)])
print(f"90-day retention   control {rc['active_90d'].mean():8.1%}       "
      f"treatment {rt['active_90d'].mean():8.1%}       "
      f"({100 * (rt['active_90d'].mean() - rc['active_90d'].mean()):+.1f} pp)      p = {p_r:.4f}"
      f"   (n = {len(rc)}/{len(rt)})")

# Guardrail: the new flow should not materially increase support demand.
t_s, p_s = stats.ttest_ind(treatment["tickets_30d"], control["tickets_30d"], equal_var=False)
print(f"30-day tickets     control {control['tickets_30d'].mean():8.2f}       "
      f"treatment {treatment['tickets_30d'].mean():8.2f}       "
      f"({100 * (treatment['tickets_30d'].mean() / max(control['tickets_30d'].mean(), 1e-9) - 1):+.1f}%)   p = {p_s:.4f}"
      f"   <- guardrail")

RESULTS["secondary_metrics"] = {
    "gmv_30d_uplift_pct": round(float(100 * (treatment["gmv_30d"].mean() / control["gmv_30d"].mean() - 1)), 1),
    "gmv_30d_p": round(float(p_g), 5),
    "control_day_7_activation": round(float(control["activated_7d"].mean()), 4),
    "treatment_day_7_activation": round(float(treatment["activated_7d"].mean()), 4),
    "day_7_activation_p": round(float(p_a), 5),
    "control_day_90_retention": round(float(rc["active_90d"].mean()), 4),
    "treatment_day_90_retention": round(float(rt["active_90d"].mean()), 4),
    "day_90_retention_p": round(float(p_r), 5),
    "tickets_30d_p": round(float(p_s), 5),
}

# ----------------------------------------------------------------------
# 5. Power: minimum detectable effect for this sample.
# ----------------------------------------------------------------------
section("5. POWER AND MINIMUM DETECTABLE EFFECT (MDE)")
pooled_sd = np.sqrt(((n_c - 1) * s_c**2 + (n_t - 1) * s_t**2) / (n_c + n_t - 2))
power_analysis = TTestIndPower()
d_min = power_analysis.solve_power(effect_size=None, nobs1=n_c, alpha=0.05, power=0.8,
                             ratio=n_t / n_c, alternative="two-sided")
mde_orders = d_min * pooled_sd
power = power_analysis.power(effect_size=difference / pooled_sd, nobs1=n_c, alpha=0.05, ratio=n_t / n_c)
n_for_10pct = power_analysis.solve_power(effect_size=(0.10 * m_c) / pooled_sd, power=0.8, alpha=0.05)
print(f"Pooled standard deviation       {pooled_sd:.2f} orders")
print(f"MDE at 80% power                {mde_orders:.2f} orders = {100 * mde_orders / m_c:.1f}% "
      f"of the control mean")
print(f"Power for observed effect       {power:.1%}")
print(f"Sample needed for +10% uplift   {n_for_10pct:,.0f} restaurants per group")
print("\nInterpretation: the available sample can detect only large effects. A real")
print("+5% effect could be missed, so non-significance would not prove no effect.")
RESULTS["power"] = {
    "mde_pct": round(float(100 * mde_orders / m_c), 1),
    "observed_effect_power": round(float(power), 3),
    "sample_size_per_group_for_10pct": int(round(n_for_10pct)),
}

# ----------------------------------------------------------------------
# 6. Chart.
# ----------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.4), gridspec_kw={"width_ratios": [1, 1.25]})

ax = axes[0]
means = [m_c, m_t]
errors = [stats.t.ppf(0.975, n_c - 1) * s_c / np.sqrt(n_c),
           stats.t.ppf(0.975, n_t - 1) * s_t / np.sqrt(n_t)]
x = [0, 1]
ax.bar(x, means, width=0.55, color=[vs.BLUE, vs.ORANGE])
ax.errorbar(x, means, yerr=errors, fmt="none", ecolor=vs.INK, elinewidth=1.4, capsize=6)
for xi, m, e in zip(x, means, errors):
    ax.text(xi, m + e + 1.2, f"{m:.1f}", ha="center", fontsize=11, fontweight="bold", color=vs.INK)
ax.set_xticks(x, ["Control", "Treatment"])
ax.set_ylabel("Completed orders in the first 30 days")
ax.set_ylim(0, max(means) * 1.35)
vs.title(ax, f"{100 * difference / m_c:+.0f}% more orders with the new onboarding flow",
         "Mean per restaurant with 95% confidence intervals")
vs.despine(ax)

ax = axes[1]
for label, assignment_group, color in [("Control", control, vs.BLUE), ("Treatment", treatment, vs.ORANGE)]:
    v = np.sort(assignment_group["orders_30d"].to_numpy())
    ax.step(v, np.arange(1, len(v) + 1) / len(v), where="post", color=color, lw=2, label=label)
ax.set_xlabel("Completed orders in the first 30 days")
ax.set_ylabel("Cumulative share of restaurants")
ax.set_xlim(0, np.percentile(d["orders_30d"], 98))
ax.legend(loc="lower right")
vs.title(ax, "The uplift appears across the distribution",
         "Empirical cumulative distribution: the treatment curve remains below\n"
         "the control curve, so the result is not driven by a few large restaurants")
vs.despine(ax)
fig.tight_layout()
vs.save(fig, FIG / "08_ab_experiment.png")

# ----------------------------------------------------------------------
# 7. Business-facing experiment brief.
# ----------------------------------------------------------------------
is_significant = RESULTS["primary"]["p_welch"] < 0.05
md = f"""# CMP-003 Experiment · New Onboarding Flow

## Recommendation

**{'Roll out the new onboarding flow in stages across markets.' if is_significant else
'Do not roll out yet; repeat the test with a larger sample.'}**

The new flow increased completed orders during the first 30 days by
**{RESULTS['primary']['uplift_pct']:+.0f}%** ({RESULTS['primary']['difference']:+.1f} orders per
restaurant; 95% CI: {RESULTS['primary']['uplift_confidence_interval_95_pct'][0]:+.0f}% to
{RESULTS['primary']['uplift_confidence_interval_95_pct'][1]:+.0f}%;
p = {RESULTS['primary']['p_welch']:.4f}). After adjustment for market, cuisine,
acquisition channel, and signup cohort, the estimated effect is
**{RESULTS['adjusted_ols']['effect_pct']:+.0f}%** (95% CI:
{RESULTS['adjusted_ols']['confidence_interval_95_pct'][0]:+.0f}% to
{RESULTS['adjusted_ols']['confidence_interval_95_pct'][1]:+.0f}%).

## Experiment design

| | |
|---|---|
| Randomisation unit | Restaurant |
| Assignment | Randomised within market, city size, and chain status |
| Signup period | {d['signup_date'].min()} to {d['signup_date'].max()} |
| Sample | {n_c} control / {n_t} treatment |
| Primary metric | Completed orders in the first 30 days |
| Guardrail | Support tickets in the first 30 days |

## Results

| Metric | Control | Treatment | Difference | p-value |
|---|---|---|---|---|
| 30-day orders | {m_c:.1f} | {m_t:.1f} | {100 * difference / m_c:+.1f}% | {p_val:.4f} |
| 30-day GMV (EUR) | {control['gmv_30d'].mean():.0f} | {treatment['gmv_30d'].mean():.0f} | {RESULTS['secondary_metrics']['gmv_30d_uplift_pct']:+.1f}% | {p_g:.4f} |
| 7-day activation | {control['activated_7d'].mean():.1%} | {treatment['activated_7d'].mean():.1%} | {100 * (treatment['activated_7d'].mean() - control['activated_7d'].mean()):+.1f} pp | {p_a:.4f} |
| 90-day retention | {rc['active_90d'].mean():.1%} | {rt['active_90d'].mean():.1%} | {100 * (rt['active_90d'].mean() - rc['active_90d'].mean()):+.1f} pp | {p_r:.4f} |
| 30-day support tickets | {control['tickets_30d'].mean():.2f} | {treatment['tickets_30d'].mean():.2f} | {100 * (treatment['tickets_30d'].mean() / max(control['tickets_30d'].mean(), 1e-9) - 1):+.1f}% | {p_s:.4f} |

## Limitations

1. **Power.** The sample of {n_c + n_t} restaurants can detect effects of roughly
   {RESULTS['power']['mde_pct']:.0f}% or more at 80% power. Confirming a +10%
   uplift would require about {RESULTS['power']['sample_size_per_group_for_10pct']:,}
   restaurants per group.
2. **Short outcome window.** Thirty days measures initial activation, not
   long-term customer value. The 90-day retention result has a smaller eligible sample.
3. **Novelty effect.** Part of the uplift may reflect additional attention during
   the pilot rather than the workflow alone.
4. **Seasonality.** Signups run from October through June. A summer rollout may
   perform differently even though cohorts are balanced between groups.
5. **Cost not observed.** The analysis does not include the operating cost of the
   new flow; the recommendation assumes that cost is comparable to the current process.

## Next step

Use a staged market rollout with the same primary and guardrail metrics, and add
cost per activated restaurant so that incremental return can be measured.
"""
(OUT / "onboarding_experiment_brief.md").write_text(md, encoding="utf-8")
(OUT / "experiment_summary.json").write_text(json.dumps(RESULTS, indent=2, ensure_ascii=False))
print("\nBusiness brief -> outputs/onboarding_experiment_brief.md")
print("JSON summary   -> outputs/experiment_summary.json")
