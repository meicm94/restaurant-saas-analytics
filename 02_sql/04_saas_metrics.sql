-- =====================================================================
-- 04_saas_metrics.sql - SaaS metrics: MRR, ARPU, GMV, churn, and NRR
-- These queries make every business definition explicit and reproducible.
-- =====================================================================

-- >>> monthly_mrr_and_customers
-- Month-end snapshot of active customers, MRR, and GMV.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
),
active_subscriptions AS (
    SELECT m.month, s.restaurant_id, s.plan_id, s.mrr_eur
    FROM months AS m
    JOIN fact_subscription AS s
      ON s.start_date <= m.month_ends
     AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
),
gmv AS (
    SELECT strftime('%Y-%m-01', order_date) AS month,
           COUNT(*)                         AS orders,
           SUM(order_value_eur)             AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY month
)
SELECT a.month,
       COUNT(*)                                        AS active_customers,
       ROUND(SUM(a.mrr_eur), 2)                        AS mrr_eur,
       ROUND(SUM(a.mrr_eur) * 12, 2)                   AS arr_eur,
       ROUND(SUM(a.mrr_eur) / COUNT(*), 2)             AS arpu_eur,
       IFNULL(g.orders, 0)                            AS orders,
       ROUND(IFNULL(g.gmv_eur, 0), 2)                  AS gmv_eur,
       ROUND(IFNULL(g.gmv_eur, 0) / COUNT(*), 2)       AS gmv_per_customer_eur,
       ROUND(100.0 * (SUM(a.mrr_eur) - LAG(SUM(a.mrr_eur)) OVER (ORDER BY a.month))
             / LAG(SUM(a.mrr_eur)) OVER (ORDER BY a.month), 2) AS mrr_growth_pct
FROM active_subscriptions AS a
LEFT JOIN gmv AS g ON g.month = a.month
GROUP BY a.month, g.orders, g.gmv_eur
ORDER BY a.month;

-- >>> mrr_movement
-- MRR bridge: new, reactivated, expansion, contraction, and churned MRR.
-- A restaurant-month panel and LAG explain why MRR changes each month.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
),
panel AS (
    SELECT m.month,
           r.restaurant_id,
           IFNULL(SUM(s.mrr_eur), 0) AS mrr
    FROM months AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.month_ends
          AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
    GROUP BY m.month, r.restaurant_id
),
comparison AS (
    SELECT month,
           restaurant_id,
           mrr,
           IFNULL(LAG(mrr) OVER (PARTITION BY restaurant_id ORDER BY month), 0) AS mrr_prev,
           IFNULL(MAX(mrr) OVER (PARTITION BY restaurant_id ORDER BY month
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prior_max_mrr
    FROM panel
)
SELECT month,
       ROUND(SUM(CASE WHEN mrr_prev = 0 AND mrr > 0 AND prior_max_mrr = 0
                      THEN mrr ELSE 0 END), 2)                      AS new_mrr,
       ROUND(SUM(CASE WHEN mrr_prev = 0 AND mrr > 0 AND prior_max_mrr > 0
                      THEN mrr ELSE 0 END), 2)                      AS reactivated_mrr,
       ROUND(SUM(CASE WHEN mrr_prev > 0 AND mrr > mrr_prev
                      THEN mrr - mrr_prev ELSE 0 END), 2)           AS expansion_mrr,
       ROUND(SUM(CASE WHEN mrr_prev > 0 AND mrr > 0 AND mrr < mrr_prev
                      THEN mrr - mrr_prev ELSE 0 END), 2)           AS contraction_mrr,
       ROUND(SUM(CASE WHEN mrr_prev > 0 AND mrr = 0
                      THEN -mrr_prev ELSE 0 END), 2)                AS churned_mrr,
       ROUND(SUM(mrr - mrr_prev), 2)                                AS net_mrr_change,
       ROUND(SUM(mrr), 2)                                           AS closing_mrr
FROM comparison
GROUP BY month
HAVING SUM(mrr) > 0
ORDER BY month;

-- >>> churn_and_nrr
-- Customer churn, revenue churn, and Net Revenue Retention.
-- The denominator is the active base at the previous month-end.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
),
panel AS (
    SELECT m.month, r.restaurant_id, IFNULL(SUM(s.mrr_eur), 0) AS mrr
    FROM months AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.month_ends
          AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
    GROUP BY m.month, r.restaurant_id
),
comparison AS (
    SELECT month, restaurant_id, mrr,
           IFNULL(LAG(mrr) OVER (PARTITION BY restaurant_id ORDER BY month), 0) AS mrr_prev
    FROM panel
)
SELECT month,
       SUM(CASE WHEN mrr_prev > 0 THEN 1 ELSE 0 END)                       AS opening_customers,
       SUM(CASE WHEN mrr_prev > 0 AND mrr = 0 THEN 1 ELSE 0 END)           AS churned_customers,
       ROUND(100.0 * SUM(CASE WHEN mrr_prev > 0 AND mrr = 0 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN mrr_prev > 0 THEN 1 ELSE 0 END), 0), 2) AS customer_churn_pct,
       ROUND(100.0 * SUM(CASE WHEN mrr_prev > 0 AND mrr = 0 THEN mrr_prev ELSE 0 END)
             / NULLIF(SUM(CASE WHEN mrr_prev > 0 THEN mrr_prev ELSE 0 END), 0), 2) AS revenue_churn_pct,
       ROUND(100.0 * SUM(CASE WHEN mrr_prev > 0 THEN mrr ELSE 0 END)
             / NULLIF(SUM(CASE WHEN mrr_prev > 0 THEN mrr_prev ELSE 0 END), 0), 1) AS nrr_pct
FROM comparison
GROUP BY month
HAVING SUM(CASE WHEN mrr_prev > 0 THEN 1 ELSE 0 END) > 0
ORDER BY month;

-- >>> total_revenue
-- Total revenue combines subscription MRR and plan-specific GMV commission.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
),
active_subscriptions AS (
    SELECT m.month, s.restaurant_id, s.plan_id, s.mrr_eur
    FROM months AS m
    JOIN fact_subscription AS s
      ON s.start_date <= m.month_ends
     AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
),
gmv_rm AS (
    SELECT restaurant_id,
           strftime('%Y-%m-01', order_date) AS month,
           SUM(order_value_eur)             AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id, month
)
SELECT a.month,
       ROUND(SUM(a.mrr_eur), 2)                                     AS mrr_eur,
       ROUND(SUM(IFNULL(g.gmv_eur, 0)), 2)                          AS gmv_eur,
       ROUND(SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate), 2)      AS commission_revenue_eur,
       ROUND(SUM(a.mrr_eur) + SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate), 2) AS total_revenue_eur,
       ROUND(100.0 * SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate)
             / (SUM(a.mrr_eur) + SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate)), 1) AS commission_revenue_pct
FROM active_subscriptions AS a
JOIN dim_plan AS p USING (plan_id)
LEFT JOIN gmv_rm AS g ON g.restaurant_id = a.restaurant_id AND g.month = a.month
GROUP BY a.month
ORDER BY a.month;

-- >>> metrics_by_plan
-- Latest available snapshot (August 2026), split by plan.
WITH latest AS (SELECT '2026-08-31' AS month_ends, '2026-08-01' AS month),
active_subscriptions AS (
    SELECT u.month, s.restaurant_id, s.plan_id, s.mrr_eur
    FROM latest AS u
    JOIN fact_subscription AS s
      ON s.start_date <= u.month_ends
     AND (s.end_date IS NULL OR s.end_date >= u.month_ends)
),
gmv AS (
    SELECT restaurant_id, SUM(order_value_eur) AS gmv_eur, COUNT(*) AS orders
    FROM fact_order
    WHERE order_status = 'completed'
      AND order_date >= '2026-08-01'
    GROUP BY restaurant_id
),
churned_customers AS (
    SELECT plan_id, COUNT(*) AS historical_churns
    FROM fact_subscription
    WHERE end_type = 'churn'
    GROUP BY plan_id
)
SELECT p.plan_name,
       p.monthly_price_eur                                  AS list_price_eur,
       COUNT(*)                                             AS customers,
       ROUND(SUM(a.mrr_eur), 2)                             AS mrr_eur,
       ROUND(AVG(a.mrr_eur), 2)                             AS arpu_eur,
       ROUND(100.0 * (1 - AVG(a.mrr_eur) / p.monthly_price_eur), 1) AS average_discount_pct,
       ROUND(SUM(IFNULL(g.gmv_eur, 0)), 2)                  AS monthly_gmv_eur,
       ROUND(AVG(IFNULL(g.orders, 0)), 1)                  AS average_orders,
       IFNULL(b.historical_churns, 0)                        AS historical_churns
FROM active_subscriptions AS a
JOIN dim_plan AS p USING (plan_id)
LEFT JOIN gmv AS g ON g.restaurant_id = a.restaurant_id
LEFT JOIN churned_customers AS b ON b.plan_id = a.plan_id
GROUP BY p.plan_name, p.monthly_price_eur, b.historical_churns
ORDER BY p.monthly_price_eur;

-- >>> executive_summary
-- Executive KPIs for the first dashboard page.
WITH active_subscriptions AS (
    SELECT s.restaurant_id, s.mrr_eur
    FROM fact_subscription AS s
    WHERE s.start_date <= '2026-08-31'
      AND (s.end_date IS NULL OR s.end_date >= '2026-08-31')
),
month AS (
    SELECT COUNT(*) AS orders, SUM(order_value_eur) AS gmv
    FROM fact_order
    WHERE order_status = 'completed' AND order_date >= '2026-08-01'
),
churned_customers_12m AS (
    SELECT COUNT(*) AS n FROM fact_subscription
    WHERE end_type = 'churn' AND end_date >= '2025-09-01'
),
average_base AS (
    SELECT AVG(c) AS average_customers FROM (
        SELECT strftime('%Y-%m', d.month_start) AS m, COUNT(*) AS c
        FROM (SELECT DISTINCT month_start FROM dim_date
              WHERE month_start >= '2025-09-01') AS d
        JOIN fact_subscription AS s
          ON s.start_date <= date(d.month_start, '+1 month', '-1 day')
         AND (s.end_date IS NULL OR s.end_date >= date(d.month_start, '+1 month', '-1 day'))
        GROUP BY m)
)
SELECT (SELECT COUNT(*) FROM active_subscriptions)                                   AS active_customers,
       ROUND((SELECT SUM(mrr_eur) FROM active_subscriptions), 2)                     AS mrr_eur,
       ROUND((SELECT SUM(mrr_eur) FROM active_subscriptions) * 12, 2)                AS arr_eur,
       ROUND((SELECT SUM(mrr_eur) FROM active_subscriptions) / (SELECT COUNT(*) FROM active_subscriptions), 2) AS arpu_eur,
       (SELECT orders FROM month)                                        AS orders_latest_month,
       ROUND((SELECT gmv FROM month), 2)                                  AS gmv_latest_month_eur,
       ROUND(100.0 * (SELECT n FROM churned_customers_12m) / (SELECT average_customers FROM average_base), 1) AS annual_churn_pct;
