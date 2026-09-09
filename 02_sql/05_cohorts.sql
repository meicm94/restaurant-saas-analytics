-- =====================================================================
-- 05_cohorts.sql - retention cohorts
-- Cohort = signup month; index = months elapsed since signup.
-- This view separates customer acquisition from customer retention.
-- =====================================================================

-- >>> long_term_retention
-- Long format: one row per cohort and lifecycle month, ready for Power BI.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
),
panel AS (
    SELECT m.month,
           r.restaurant_id,
           r.signup_cohort AS cohort,
           r.signup_month,
           CASE WHEN s.restaurant_id IS NULL THEN 0 ELSE 1 END AS is_active,
           IFNULL(s.mrr_eur, 0) AS mrr
    FROM months AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.month_ends
          AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
    WHERE m.month >= r.signup_month
),
indexed AS (
    SELECT cohort,
           month,
           restaurant_id,
           is_active,
           mrr,
           (CAST(strftime('%Y', month) AS INTEGER) * 12 + CAST(strftime('%m', month) AS INTEGER))
         - (CAST(strftime('%Y', signup_month) AS INTEGER) * 12 + CAST(strftime('%m', signup_month) AS INTEGER))
             AS lifecycle_month
    FROM panel
),
cohort_size AS (
    SELECT cohort, COUNT(DISTINCT restaurant_id) AS cohort_size
    FROM indexed WHERE lifecycle_month = 0 GROUP BY cohort
)
SELECT i.cohort,
       t.cohort_size,
       i.lifecycle_month,
       SUM(i.is_active)                                                   AS active_subscriptions,
       ROUND(100.0 * SUM(i.is_active) / t.cohort_size, 1)               AS retention_pct,
       ROUND(SUM(i.mrr), 2)                                            AS mrr_eur,
       ROUND(SUM(i.mrr) / NULLIF(SUM(i.is_active), 0), 2)                 AS arpu_eur
FROM indexed AS i
JOIN cohort_size AS t USING (cohort)
GROUP BY i.cohort, t.cohort_size, i.lifecycle_month
ORDER BY i.cohort, i.lifecycle_month;

-- >>> retention_matrix
-- The same information pivoted to lifecycle months for quick inspection.
-- Empty cells represent cohorts that have not yet reached that age.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
),
panel AS (
    SELECT m.month, r.restaurant_id, r.signup_cohort AS cohort, r.signup_month,
           CASE WHEN s.restaurant_id IS NULL THEN 0 ELSE 1 END AS is_active
    FROM months AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.month_ends
          AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
    WHERE m.month >= r.signup_month
),
indexed AS (
    SELECT cohort, restaurant_id, is_active,
           (CAST(strftime('%Y', month) AS INTEGER) * 12 + CAST(strftime('%m', month) AS INTEGER))
         - (CAST(strftime('%Y', signup_month) AS INTEGER) * 12 + CAST(strftime('%m', signup_month) AS INTEGER))
             AS lifecycle_month
    FROM panel
),
base AS (
    SELECT cohort, lifecycle_month, SUM(is_active) AS active_subscriptions
    FROM indexed GROUP BY cohort, lifecycle_month
),
cohort_size AS (
    SELECT cohort, active_subscriptions AS n FROM base WHERE lifecycle_month = 0
)
SELECT b.cohort,
       t.n AS signups,
       MAX(CASE WHEN b.lifecycle_month = 1 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M1,
       MAX(CASE WHEN b.lifecycle_month = 2 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M2,
       MAX(CASE WHEN b.lifecycle_month = 3 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M3,
       MAX(CASE WHEN b.lifecycle_month = 4 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M4,
       MAX(CASE WHEN b.lifecycle_month = 5 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M5,
       MAX(CASE WHEN b.lifecycle_month = 6 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M6,
       MAX(CASE WHEN b.lifecycle_month = 9 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M9,
       MAX(CASE WHEN b.lifecycle_month = 12 THEN ROUND(100.0 * b.active_subscriptions / t.n, 0) END) AS M12
FROM base AS b
JOIN cohort_size AS t USING (cohort)
GROUP BY b.cohort, t.n
ORDER BY b.cohort;

-- >>> survival_by_market
-- Three-, six-, and twelve-month retention by market, restricted to customers
-- with sufficient observation time at each horizon.
WITH customer_age AS (
    SELECT r.restaurant_id,
           r.market,
           r.signup_date,
           CAST((julianday('2026-08-31') - julianday(r.signup_date)) / 30.44 AS INTEGER) AS observable_months,
           CAST((julianday(IFNULL((SELECT MAX(s.end_date) FROM fact_subscription AS s
                                   WHERE s.restaurant_id = r.restaurant_id AND s.end_type = 'churn'),
                                  '2026-08-31'))
                 - julianday(r.signup_date)) / 30.44 AS INTEGER) AS months_survived
    FROM dim_restaurant AS r
)
SELECT market,
       COUNT(*)                                                                AS restaurants,
       ROUND(100.0 * SUM(CASE WHEN observable_months >= 3 AND months_survived >= 3 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN observable_months >= 3 THEN 1 ELSE 0 END), 0), 1)   AS retention_3m_pct,
       ROUND(100.0 * SUM(CASE WHEN observable_months >= 6 AND months_survived >= 6 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN observable_months >= 6 THEN 1 ELSE 0 END), 0), 1)   AS retention_6m_pct,
       ROUND(100.0 * SUM(CASE WHEN observable_months >= 12 AND months_survived >= 12 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN observable_months >= 12 THEN 1 ELSE 0 END), 0), 1)  AS retention_12m_pct
FROM customer_age
GROUP BY market
ORDER BY retention_6m_pct DESC;
