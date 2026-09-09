# DAX Measure Library

Create these measures in a dedicated `_Measures` table. Their definitions match
the business conventions in `02_sql/00_schema.sql`; validate them against the
CSV outputs produced by `02_sql/04_saas_metrics.sql`.

## 1. Core commercial metrics

```dax
Completed Orders =
CALCULATE (
    COUNTROWS ( fact_order ),
    fact_order[order_status] = "completed"
)

GMV =
CALCULATE (
    SUM ( fact_order[order_value_eur] ),
    fact_order[order_status] = "completed"
)

Average Order Value = DIVIDE ( [GMV], [Completed Orders] )

Non-Completed Orders =
CALCULATE (
    COUNTROWS ( fact_order ),
    fact_order[order_status] <> "completed"
)

Cancellation Rate % =
DIVIDE ( [Non-Completed Orders], COUNTROWS ( fact_order ) )
```

`DIVIDE` returns blank when the denominator is zero, which is safer than `/`
when report filters create an empty slice.

## 2. Active customers and MRR at month-end

`fact_subscription` has no active date relationship because each row represents
an interval. These measures evaluate whether that interval overlaps the selected
period end.

```dax
Active Customers =
VAR PeriodEnd = MAX ( dim_date[date] )
RETURN
    CALCULATE (
        DISTINCTCOUNT ( fact_subscription[restaurant_id] ),
        FILTER (
            ALL (
                fact_subscription[start_date],
                fact_subscription[end_date]
            ),
            fact_subscription[start_date] <= PeriodEnd
                && (
                    ISBLANK ( fact_subscription[end_date] )
                    || fact_subscription[end_date] >= PeriodEnd
                )
        )
    )

MRR =
VAR PeriodEnd = MAX ( dim_date[date] )
RETURN
    CALCULATE (
        SUM ( fact_subscription[mrr_eur] ),
        FILTER (
            ALL (
                fact_subscription[start_date],
                fact_subscription[end_date]
            ),
            fact_subscription[start_date] <= PeriodEnd
                && (
                    ISBLANK ( fact_subscription[end_date] )
                    || fact_subscription[end_date] >= PeriodEnd
                )
        )
    )

ARR = [MRR] * 12

ARPU = DIVIDE ( [MRR], [Active Customers] )
```

Only the interval columns are cleared. Market, plan, cuisine, and other
dimension filters remain in context and continue to affect the result.

## 3. Time intelligence

```dax
Previous Month MRR =
CALCULATE ( [MRR], DATEADD ( dim_date[date], -1, MONTH ) )

MRR Growth % =
VAR PreviousMRR = [Previous Month MRR]
RETURN
    DIVIDE ( [MRR] - PreviousMRR, PreviousMRR )

GMV YTD = TOTALYTD ( [GMV], dim_date[date] )

GMV Previous Year =
CALCULATE ( [GMV], SAMEPERIODLASTYEAR ( dim_date[date] ) )

GMV Rolling 3M =
AVERAGEX (
    DATESINPERIOD (
        dim_date[date],
        MAX ( dim_date[date] ),
        -3,
        MONTH
    ),
    [GMV]
)
```

Mark `dim_date` as the official date table and ensure that it covers complete
calendar years before relying on time-intelligence functions.

## 4. Churn measures

The inactive `end_date` relationship is activated only for measures that count
subscription endings.

```dax
Churned Customers =
CALCULATE (
    COUNTROWS ( fact_subscription ),
    fact_subscription[end_type] = "churn",
    USERELATIONSHIP (
        fact_subscription[end_date],
        dim_date[date]
    )
)

Churned MRR =
CALCULATE (
    SUM ( fact_subscription[mrr_eur] ),
    fact_subscription[end_type] = "churn",
    USERELATIONSHIP (
        fact_subscription[end_date],
        dim_date[date]
    )
)

Previous Month Active Customers =
CALCULATE (
    [Active Customers],
    DATEADD ( dim_date[date], -1, MONTH )
)

Customer Churn % =
DIVIDE ( [Churned Customers], [Previous Month Active Customers] )

Revenue Churn % =
DIVIDE ( [Churned MRR], [Previous Month MRR] )

Annualised Customer Churn % =
1 - POWER ( 1 - [Customer Churn %], 12 )
```

The denominator is the active base at the previous month-end. This is a stated
business convention rather than a universal definition; an average monthly base
would produce a different result.

## 5. Net Revenue Retention

For exact NRR, compare current MRR from the previous month's customer base with
that cohort's opening MRR. New customers must be excluded.

```dax
NRR % =
VAR CurrentPeriodEnd = MAX ( dim_date[date] )
VAR PreviousPeriodEnd = EOMONTH ( CurrentPeriodEnd, -1 )
VAR OpeningCustomers =
    CALCULATETABLE (
        VALUES ( fact_subscription[restaurant_id] ),
        FILTER (
            ALL (
                fact_subscription[start_date],
                fact_subscription[end_date]
            ),
            fact_subscription[start_date] <= PreviousPeriodEnd
                && (
                    ISBLANK ( fact_subscription[end_date] )
                    || fact_subscription[end_date] >= PreviousPeriodEnd
                )
        )
    )
VAR OpeningMRR =
    CALCULATE (
        SUM ( fact_subscription[mrr_eur] ),
        OpeningCustomers,
        FILTER (
            ALL (
                fact_subscription[start_date],
                fact_subscription[end_date]
            ),
            fact_subscription[start_date] <= PreviousPeriodEnd
                && (
                    ISBLANK ( fact_subscription[end_date] )
                    || fact_subscription[end_date] >= PreviousPeriodEnd
                )
        )
    )
VAR ClosingMRRFromOpeningBase =
    CALCULATE (
        SUM ( fact_subscription[mrr_eur] ),
        OpeningCustomers,
        FILTER (
            ALL (
                fact_subscription[start_date],
                fact_subscription[end_date]
            ),
            fact_subscription[start_date] <= CurrentPeriodEnd
                && (
                    ISBLANK ( fact_subscription[end_date] )
                    || fact_subscription[end_date] >= CurrentPeriodEnd
                )
        )
    )
RETURN
    DIVIDE ( ClosingMRRFromOpeningBase, OpeningMRR )
```

Validate this measure carefully under market and plan filters. For production,
an account-month snapshot table often makes NRR simpler and more efficient.

## 6. MRR movement

MRR movement requires comparing every customer with the previous month and
classifying the change as new, reactivated, expansion, contraction, or churn.
The precise implementation is materialised by the `mrr_movement` query in
`02_sql/04_saas_metrics.sql`.

Load that output as a monthly bridge table and expose simple additive measures:

```dax
New MRR = SUM ( mrr_movement[new_mrr] )

Reactivated MRR = SUM ( mrr_movement[reactivated_mrr] )

Expansion MRR = SUM ( mrr_movement[expansion_mrr] )

Contraction MRR = SUM ( mrr_movement[contraction_mrr] )

Churned MRR Movement = SUM ( mrr_movement[churned_mrr] )

Net MRR Change = SUM ( mrr_movement[net_mrr_change] )
```

Materialising the bridge is preferable to recalculating a long interval-based
measure in every report cell. Choosing the correct data layer is part of model
design, not a failure to write more DAX.

## 7. Retention cohorts

Load `data/clean/restaurant_month_panel.csv` as `panel`.

```dax
Retention % =
VAR CohortSize =
    CALCULATE (
        DISTINCTCOUNT ( panel[restaurant_id] ),
        ALLEXCEPT ( panel, panel[signup_cohort] ),
        panel[tenure_months] = 0
    )
VAR ActiveCustomers =
    CALCULATE (
        DISTINCTCOUNT ( panel[restaurant_id] ),
        panel[is_active] = 1
    )
RETURN
    DIVIDE ( ActiveCustomers, CohortSize )
```

Use `signup_cohort` on rows, `tenure_months` on columns, and `Retention %` as the
value in a matrix with a sequential colour scale.

## 8. Experiment reporting

```dax
Experiment Restaurants =
CALCULATE (
    DISTINCTCOUNT ( fact_campaign_assignment[restaurant_id] ),
    fact_campaign_assignment[campaign_id] = "CMP-003"
)

Orders in First 30 Days =
SUMX (
    VALUES ( dim_restaurant[restaurant_id] ),
    VAR SignupDate = CALCULATE ( MAX ( dim_restaurant[signup_date] ) )
    RETURN
        CALCULATE (
            [Completed Orders],
            DATESBETWEEN (
                dim_date[date],
                SignupDate,
                SignupDate + 29
            )
        )
)

Orders per Experiment Restaurant =
DIVIDE ( [Orders in First 30 Days], [Experiment Restaurants] )
```

Place `assignment_group` on the visual axis. Confidence intervals and p-values
come from `outputs/experiment_summary.json`; do not imply statistical certainty
with a bar chart that omits uncertainty.

## Formatting and documentation

- Currency: `EUR #,##0` for KPI cards and `EUR #,##0.0` where precision matters.
- Percentages: `0.0%`.
- Counts: whole numbers with thousands separators.
- Add a description to every measure in the model properties.
- Keep technical measures hidden if they exist only to support another measure.
