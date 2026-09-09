# Power BI Semantic Model

Build the semantic model from `data/clean/*.csv`. The clean layer is validated
before loading, so the report model can focus on relationships and measures
rather than repairing source-system inconsistencies at query time.

## Model layout

```text
                         dim_date
                       (date table)
                             |
          +------------------+------------------+
          |                  |                  |
     fact_order      fact_support_ticket   fact_subscription
          |                  |                  |
          +----------- dim_restaurant ----------+
                             |
               fact_campaign_assignment
                             |
                       dim_campaign

                    dim_plan ── fact_subscription
```

## Relationships

| From | To | Cardinality | Filter direction | Active |
|---|---|---|---|---|
| `fact_order[restaurant_id]` | `dim_restaurant[restaurant_id]` | Many to one | Single | Yes |
| `fact_order[order_date]` | `dim_date[date]` | Many to one | Single | Yes |
| `fact_subscription[restaurant_id]` | `dim_restaurant[restaurant_id]` | Many to one | Single | Yes |
| `fact_subscription[plan_id]` | `dim_plan[plan_id]` | Many to one | Single | Yes |
| `fact_subscription[end_date]` | `dim_date[date]` | Many to one | Single | **No** |
| `fact_support_ticket[restaurant_id]` | `dim_restaurant[restaurant_id]` | Many to one | Single | Yes |
| `fact_support_ticket[ticket_date]` | `dim_date[date]` | Many to one | Single | Yes |
| `fact_campaign_assignment[restaurant_id]` | `dim_restaurant[restaurant_id]` | Many to one | Single | Yes |
| `fact_campaign_assignment[campaign_id]` | `dim_campaign[campaign_id]` | Many to one | Single | Yes |

Use one-way filtering from dimensions to facts. Bidirectional relationships are
not required here and would make filter propagation harder to reason about.

## Why subscriptions do not use an active date relationship

A subscription has a start and an end date, but analytically it occupies an
interval rather than a single day. If `start_date` were actively related to the
date dimension, filtering August 2026 would return subscriptions that started in
August—not all subscriptions active during August.

This model therefore uses two deliberate patterns:

1. No active relationship between `fact_subscription` and `dim_date`. MRR and
   active-customer measures apply the selected month-end to the subscription
   interval inside DAX.
2. An inactive relationship from `fact_subscription[end_date]` to
   `dim_date[date]`, activated with `USERELATIONSHIP` only for churn measures.

This requires more explicit measures, but it produces correct results when a
user changes the reporting month.

## Required model settings

- Mark `dim_date` as the official date table using `dim_date[date]`.
- Sort `dim_date[month_name]` by `dim_date[month_number]`.
- Hide technical keys and fact-table date fields from report consumers.
- Hide raw `fact_order[order_value_eur]` and expose the validated `GMV` measure;
  summing the column directly would include cancelled and refunded orders.
- Create an empty `_Measures` table to organise all measures.
- Use fixed decimal numbers for currency, date—not date/time—for calendar fields,
  and text for business keys.
- Keep “Auto date/time” disabled to avoid hidden date tables and ambiguous time
  intelligence.

## Storage mode

Import mode is appropriate for roughly 250,000 orders: it is fast, compact, and
supports the complete DAX surface. DirectQuery would become relevant only with
substantially larger or near-real-time data, and would add latency and modelling
constraints without benefit in this case.

## Validation checklist

After building the model, reconcile these figures with
`outputs/sql_results/04_saas_metrics__*.csv`:

- Active customers and MRR at every month-end.
- GMV and completed-order count by month.
- Customer churn and NRR.
- August 2026 results by plan.

Test the same measures under market and plan filters. A grand total that matches
SQL is not sufficient if the measure ignores dimensional filter context.
