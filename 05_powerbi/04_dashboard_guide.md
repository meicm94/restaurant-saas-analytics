# Power BI Dashboard Specification

The report uses three pages, each built around one management question. Every
visual should either answer that question or support an action; decorative
charts are intentionally excluded.

## Page 1 · Business performance

**Question:** How is the business performing, and what is driving the change?

| Area | Content |
|---|---|
| KPI cards | MRR, ARR, active customers, ARPU, latest-month GMV, customer churn |
| Main visual | Monthly MRR with three-month trend or prior-period comparison |
| Driver visual | MRR bridge: new, reactivated, expansion, contraction, and churn |
| Market view | GMV and completed orders by market, sorted by GMV |
| Filters | Date range, market, and plan |

Add a short commentary box that distinguishes acquisition-led growth from
expansion-led growth. The latest value should never appear without a comparison
period or target.

## Page 2 · Retention and intervention

**Question:** Where is retention deteriorating, and which customers require action?

| Area | Content |
|---|---|
| KPI cards | Churned customers, customer churn, revenue churn, and NRR |
| Main visual | Retention-cohort matrix with a single sequential colour scale |
| Diagnostic view | Churn reasons and churn by plan |
| Action table | At-risk active customers with MRR, last order, days inactive, and model risk |
| Filters | Cohort, market, plan, cuisine, and segment |

The action table is the operational endpoint of the page. Sort it first by model
risk and then by MRR so that outreach capacity is directed toward accounts with
both high probability and meaningful commercial value.

## Page 3 · Onboarding experiment

**Question:** Did the new onboarding flow improve adoption without damaging support?

| Area | Content |
|---|---|
| Context | Hypothesis, randomisation unit, sample, and observation window |
| KPI cards | 30-day orders by group, uplift, 95% confidence interval, and p-value |
| Main visual | Treatment and control means with 95% confidence intervals |
| Distribution | Empirical cumulative distribution of first-30-day orders |
| Supporting table | GMV, 7-day activation, 90-day retention, and support-ticket guardrail |
| Decision | Staged rollout recommendation and next measurement step |

Report the uncertainty beside the point estimate. A difference between bars is
not evidence of a reliable effect unless the experimental design and interval
are visible.

## Visual standards

- Use separate panels instead of dual vertical axes.
- Prefer sorted bars to pie charts with more than three categories.
- Assign colours consistently to treatment groups and business entities.
- Use one sequential palette for magnitude and a small categorical palette for
  genuinely distinct series.
- Display material comparisons: `4.1% vs 3.4% last quarter` is more useful than
  `4.1%` alone.
- Use business-level precision. A card should show `EUR 61.8K`, not
  `EUR 61,803.45`.
- Include definitions in report tooltips for MRR, active customer, churn, and NRR.
- Check colour contrast and ensure that meaning does not depend on colour alone.

## Acceptance checks

Before publishing, confirm that:

1. SQL, pandas, and Power BI return the same MRR and active-customer totals.
2. Market and plan filters change every relevant subscription measure.
3. Cancelled and refunded orders are excluded from GMV.
4. Retention denominators exclude cohorts that have not reached the selected age.
5. The experiment page uses only restaurants with complete outcome windows.
6. Each page has a clear decision or next action, not merely a collection of KPIs.
