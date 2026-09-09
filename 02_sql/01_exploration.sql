-- =====================================================================
-- 01_exploration.sql - SELECT, WHERE, GROUP BY, CASE, HAVING
-- Week 1: core querying patterns.
-- =====================================================================

-- >>> monthly_volume
-- Monthly orders, GMV, and average order value. Revenue includes completed orders only.
SELECT strftime('%Y-%m', order_date)               AS month,
       COUNT(*)                                    AS orders,
       ROUND(SUM(order_value_eur), 2)              AS gmv_eur,
       ROUND(AVG(order_value_eur), 2)              AS average_order_value_eur,
       COUNT(DISTINCT restaurant_id)               AS restaurants_with_orders
FROM fact_order
WHERE order_status = 'completed'
GROUP BY month
ORDER BY month;

-- >>> order_quality
-- Order-status mix and economic value, using CASE for business grouping.
SELECT order_status,
       CASE WHEN order_status = 'completed' THEN 'Included in revenue'
            ELSE 'Excluded from revenue' END       AS revenue_treatment,
       COUNT(*)                                    AS orders,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_orders,
       ROUND(SUM(order_value_eur), 2)              AS order_value_eur
FROM fact_order
GROUP BY order_status
ORDER BY orders DESC;

-- >>> average_order_value_segments
-- Commercial average-order-value bands created with CASE.
SELECT CASE
           WHEN order_value_eur <  15 THEN 'A. Under EUR 15'
           WHEN order_value_eur <  30 THEN 'B. 15-30 EUR'
           WHEN order_value_eur <  50 THEN 'C. 30-50 EUR'
           WHEN order_value_eur < 100 THEN 'D. 50-100 EUR'
           ELSE                            'E. EUR 100 or more'
       END                                         AS order_value_band,
       COUNT(*)                                    AS orders,
       ROUND(SUM(order_value_eur), 2)              AS gmv_eur,
       ROUND(100.0 * SUM(order_value_eur) / SUM(SUM(order_value_eur)) OVER (), 2) AS pct_gmv
FROM fact_order
WHERE order_status = 'completed'
GROUP BY order_value_band
ORDER BY order_value_band;

-- >>> market_and_channel
-- Market aggregation with app and delivery shares.
SELECT r.market,
       r.market_name,
       COUNT(*)                                                        AS orders,
       ROUND(SUM(o.order_value_eur), 2)                                AS gmv_eur,
       ROUND(AVG(o.order_value_eur), 2)                                AS average_order_value_eur,
       ROUND(100.0 * SUM(CASE WHEN o.order_channel = 'app' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                            AS pct_app,
       ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'delivery' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                            AS pct_delivery
FROM fact_order AS o
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE o.order_status = 'completed'
GROUP BY r.market, r.market_name
ORDER BY gmv_eur DESC;

-- >>> top_restaurants
-- HAVING filters after aggregation to retain restaurants with material volume.
SELECT o.restaurant_id,
       r.restaurant_name,
       r.market,
       r.cuisine_type,
       COUNT(*)                          AS orders,
       ROUND(SUM(o.order_value_eur), 2)  AS gmv_eur,
       ROUND(AVG(o.order_value_eur), 2)  AS average_order_value_eur
FROM fact_order AS o
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE o.order_status = 'completed'
GROUP BY o.restaurant_id, r.restaurant_name, r.market, r.cuisine_type
HAVING COUNT(*) >= 200
ORDER BY gmv_eur DESC
LIMIT 15;

-- >>> weekend_effect
-- Weekly demand pattern to inform promotion timing.
SELECT CASE CAST(strftime('%w', order_date) AS INTEGER)
           WHEN 0 THEN '7 Sunday'   WHEN 1 THEN '1 Monday'   WHEN 2 THEN '2 Tuesday'
           WHEN 3 THEN '3 Wednesday' WHEN 4 THEN '4 Thursday' WHEN 5 THEN '5 Friday'
           ELSE '6 Saturday' END                  AS day_of_week,
       COUNT(*)                                   AS orders,
       ROUND(AVG(order_value_eur), 2)             AS average_order_value_eur
FROM fact_order
WHERE order_status = 'completed'
GROUP BY day_of_week
ORDER BY day_of_week;
