-- =====================================================================
-- 06_experiment.sql - A/B experiment analysis in SQL
-- CMP-003 "New onboarding flow": eligible restaurants are randomised between
-- control and treatment. The primary outcome is completed orders during each
-- restaurant's first 30 days.
--
-- Confidence intervals, power, and adjusted OLS analysis are implemented in
-- 04_experiment/ab_test_onboarding.py. This file provides the SQL aggregates.
-- =====================================================================

-- >>> group_balance
-- Validate group balance before reviewing outcomes.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS assignment_group, r.market, r.city_size,
           r.cuisine_type, r.is_chain, r.acquisition_channel, r.signup_date
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
)
SELECT assignment_group,
       COUNT(*)                                                          AS restaurants,
       ROUND(100.0 * SUM(CASE WHEN market = 'DK' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_dk,
       ROUND(100.0 * SUM(CASE WHEN city_size = 'Metro' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_metro,
       ROUND(100.0 * SUM(is_chain) / COUNT(*), 1)                        AS pct_chain,
       ROUND(100.0 * SUM(CASE WHEN acquisition_channel = 'Direct sales' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                              AS pct_direct_sales,
       MIN(signup_date)                                                  AS earliest_signup,
       MAX(signup_date)                                                  AS latest_signup
FROM exp
GROUP BY assignment_group
ORDER BY assignment_group;

-- >>> primary_result
-- Completed orders during the first 30 days by assignment group. Restaurants
-- without a complete 30-day observation window are excluded.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS assignment_group, r.signup_date,
           date(r.signup_date, '+29 days') AS window_end
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
      AND date(r.signup_date, '+29 days') <= '2026-08-31'
),
by_restaurant AS (
    SELECT e.restaurant_id,
           e.assignment_group,
           COUNT(o.order_id)                    AS orders_30d,
           IFNULL(SUM(o.order_value_eur), 0)    AS gmv_30d,
           MAX(CASE WHEN o.order_date <= date(e.signup_date, '+6 days') THEN 1 ELSE 0 END) AS activated_7d
    FROM exp AS e
    LEFT JOIN fact_order AS o
           ON o.restaurant_id = e.restaurant_id
          AND o.order_status = 'completed'
          AND o.order_date BETWEEN e.signup_date AND e.window_end
    GROUP BY e.restaurant_id, e.assignment_group
)
SELECT assignment_group,
       COUNT(*)                                     AS restaurants,
       ROUND(AVG(orders_30d), 2)                    AS average_orders_30d,
       ROUND(AVG(gmv_30d), 2)                       AS average_gmv_30d_eur,
       ROUND(100.0 * AVG(activated_7d), 1)          AS activation_7d_pct,
       -- Sample standard deviation, required for the confidence interval.
       ROUND(SQRT(SUM((orders_30d - (SELECT AVG(p2.orders_30d) FROM by_restaurant AS p2
                                      WHERE p2.assignment_group = by_restaurant.assignment_group))
                      * (orders_30d - (SELECT AVG(p2.orders_30d) FROM by_restaurant AS p2
                                        WHERE p2.assignment_group = by_restaurant.assignment_group)))
                  / (COUNT(*) - 1)), 2)             AS orders_30d_stddev
FROM by_restaurant
GROUP BY assignment_group
ORDER BY assignment_group;

-- >>> difference_and_uplift
-- Treatment-control difference and uplift in one business-facing row.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS assignment_group, r.signup_date,
           date(r.signup_date, '+29 days') AS window_end
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
      AND date(r.signup_date, '+29 days') <= '2026-08-31'
),
by_restaurant AS (
    SELECT e.restaurant_id, e.assignment_group,
           COUNT(o.order_id)                 AS orders_30d,
           IFNULL(SUM(o.order_value_eur), 0) AS gmv_30d
    FROM exp AS e
    LEFT JOIN fact_order AS o
           ON o.restaurant_id = e.restaurant_id
          AND o.order_status = 'completed'
          AND o.order_date BETWEEN e.signup_date AND e.window_end
    GROUP BY e.restaurant_id, e.assignment_group
),
means AS (
    SELECT AVG(CASE WHEN assignment_group = 'treatment' THEN orders_30d END) AS trat_orders,
           AVG(CASE WHEN assignment_group = 'control'   THEN orders_30d END) AS ctrl_orders,
           AVG(CASE WHEN assignment_group = 'treatment' THEN gmv_30d END)     AS trat_gmv,
           AVG(CASE WHEN assignment_group = 'control'   THEN gmv_30d END)     AS ctrl_gmv
    FROM by_restaurant
)
SELECT ROUND(ctrl_orders, 2)                                          AS control_orders_30d,
       ROUND(trat_orders, 2)                                          AS treatment_orders_30d,
       ROUND(trat_orders - ctrl_orders, 2)                           AS difference_orders,
       ROUND(100.0 * (trat_orders - ctrl_orders) / ctrl_orders, 1)  AS uplift_orders_pct,
       ROUND(ctrl_gmv, 2)                                              AS control_gmv_30d,
       ROUND(trat_gmv, 2)                                              AS treatment_gmv_30d,
       ROUND(100.0 * (trat_gmv - ctrl_gmv) / ctrl_gmv, 1)              AS uplift_gmv_pct
FROM means;

-- >>> day_90_retention
-- Secondary outcome: active subscription 90 days after signup. Include only
-- restaurants with a complete observation window.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS assignment_group, r.signup_date,
           date(r.signup_date, '+90 days') AS day_90
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
      AND date(r.signup_date, '+90 days') <= '2026-08-31'
)
SELECT e.assignment_group,
       COUNT(*)                                                   AS restaurants,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM fact_subscription AS s
                             WHERE s.restaurant_id = e.restaurant_id
                               AND s.start_date <= e.day_90
                               AND (s.end_date IS NULL OR s.end_date >= e.day_90))
                THEN 1 ELSE 0 END)                                AS active_at_90d,
       ROUND(100.0 * SUM(CASE WHEN EXISTS (SELECT 1 FROM fact_subscription AS s
                                           WHERE s.restaurant_id = e.restaurant_id
                                             AND s.start_date <= e.day_90
                                             AND (s.end_date IS NULL OR s.end_date >= e.day_90))
                              THEN 1 ELSE 0 END) / COUNT(*), 1)   AS retention_90d_pct
FROM exp AS e
GROUP BY e.assignment_group
ORDER BY e.assignment_group;
