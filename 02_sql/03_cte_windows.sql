-- =====================================================================
-- 03_cte_windows.sql - CTEs and window functions
-- ROW_NUMBER, LAG, RANK, NTILE, SUM() OVER, and rolling averages.
-- =====================================================================

-- >>> monthly_growth
-- Month-over-month GMV change and a three-month rolling average using LAG.
WITH monthly AS (
    SELECT strftime('%Y-%m', order_date) AS month,
           COUNT(*)                      AS orders,
           SUM(order_value_eur)          AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY month
)
SELECT month,
       orders,
       ROUND(gmv_eur, 2)                                          AS gmv_eur,
       ROUND(LAG(gmv_eur) OVER (ORDER BY month), 2)                 AS previous_month_gmv,
       ROUND(100.0 * (gmv_eur - LAG(gmv_eur) OVER (ORDER BY month))
             / LAG(gmv_eur) OVER (ORDER BY month), 2)               AS month_over_month_growth_pct,
       ROUND(AVG(gmv_eur) OVER (ORDER BY month
                                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS rolling_3m_gmv,
       ROUND(SUM(gmv_eur) OVER (ORDER BY month), 2)                 AS cumulative_gmv
FROM monthly
ORDER BY month;

-- >>> first_and_last_order
-- Use ROW_NUMBER to isolate each restaurant's first completed order and measure
-- time to first order, a core onboarding KPI.
WITH ranked_orders AS (
    SELECT o.restaurant_id,
           o.order_id,
           o.order_date,
           o.order_value_eur,
           ROW_NUMBER() OVER (PARTITION BY o.restaurant_id ORDER BY o.order_date, o.order_id) AS rn
    FROM fact_order AS o
    WHERE o.order_status = 'completed'
)
SELECT r.market,
       COUNT(*)                                                                AS restaurants,
       ROUND(AVG(julianday(x.order_date) - julianday(r.signup_date)), 2)       AS days_to_first_order,
       ROUND(AVG(x.order_value_eur), 2)                                        AS first_order_value_eur
FROM ranked_orders AS x
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE x.rn = 1
GROUP BY r.market
ORDER BY days_to_first_order;

-- >>> market_ranking
-- Rank restaurants within each market and calculate their share of market GMV.
-- Window-function results are filtered in a separate CTE for portability.
WITH gmv AS (
    SELECT o.restaurant_id, r.market, r.restaurant_name,
           SUM(o.order_value_eur) AS gmv_eur
    FROM fact_order AS o
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE o.order_status = 'completed'
    GROUP BY o.restaurant_id, r.market, r.restaurant_name
),
ranking AS (
    SELECT market, restaurant_id, restaurant_name, gmv_eur,
           RANK() OVER (PARTITION BY market ORDER BY gmv_eur DESC)         AS market_rank,
           100.0 * gmv_eur / SUM(gmv_eur) OVER (PARTITION BY market)       AS market_gmv_share_pct
    FROM gmv
)
SELECT market, market_rank, restaurant_id, restaurant_name,
       ROUND(gmv_eur, 2)         AS gmv_eur,
       ROUND(market_gmv_share_pct, 2) AS market_gmv_share_pct
FROM ranking
WHERE market_rank <= 5
ORDER BY market, market_rank;

-- >>> pareto_concentration
-- Use NTILE to quantify GMV concentration by customer decile.
WITH gmv AS (
    SELECT restaurant_id, SUM(order_value_eur) AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id
),
deciles AS (
    SELECT restaurant_id, gmv_eur,
           NTILE(10) OVER (ORDER BY gmv_eur DESC) AS decile
    FROM gmv
)
SELECT decile,
       COUNT(*)                                             AS restaurants,
       ROUND(SUM(gmv_eur), 2)                               AS gmv_eur,
       ROUND(100.0 * SUM(gmv_eur) / SUM(SUM(gmv_eur)) OVER (), 2)         AS pct_gmv,
       ROUND(SUM(SUM(gmv_eur)) OVER (ORDER BY decile) * 100.0
             / SUM(SUM(gmv_eur)) OVER (), 2)                AS cumulative_gmv_pct
FROM deciles
GROUP BY decile
ORDER BY decile;

-- >>> restaurant_trend
-- Compare current orders with the preceding three-month average to surface
-- early warnings of declining engagement.
WITH rm AS (
    SELECT restaurant_id,
           strftime('%Y-%m', order_date) AS month,
           COUNT(*)                      AS orders
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id, month
),
with_prior_average AS (
    SELECT restaurant_id, month, orders,
           AVG(orders) OVER (PARTITION BY restaurant_id ORDER BY month
                              ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS prior_3m_average,
           ROW_NUMBER() OVER (PARTITION BY restaurant_id ORDER BY month DESC) AS rn_desc
    FROM rm
)
SELECT c.restaurant_id,
       r.restaurant_name,
       r.market,
       c.month                                            AS latest_month,
       c.orders,
       ROUND(c.prior_3m_average, 1)                      AS prior_3m_average,
       ROUND(100.0 * (c.orders - c.prior_3m_average) / c.prior_3m_average, 1) AS change_pct
FROM with_prior_average AS c
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE c.rn_desc = 1
  AND c.prior_3m_average IS NOT NULL
  AND c.orders < 0.6 * c.prior_3m_average
ORDER BY change_pct
LIMIT 20;
