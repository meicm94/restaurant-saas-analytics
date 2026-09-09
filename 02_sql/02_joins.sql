-- =====================================================================
-- 02_joins.sql - INNER, LEFT, and anti-joins across customers,
-- subscriptions, plans, orders, and campaigns.
-- =====================================================================

-- >>> customer_profile
-- Customer 360 view: three INNER JOINs plus a LEFT JOIN to order aggregates.
WITH orders AS (
    SELECT restaurant_id,
           COUNT(*)               AS orders,
           SUM(order_value_eur)   AS gmv_eur,
           MAX(order_date)        AS latest_order_date
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id
)
SELECT r.restaurant_id,
       r.restaurant_name,
       r.market,
       r.city,
       r.cuisine_type,
       p.plan_name,
       s.mrr_eur,
       s.start_date                       AS subscription_start_date,
       IFNULL(px.orders, 0)              AS orders,
       ROUND(IFNULL(px.gmv_eur, 0), 2)    AS gmv_eur,
       px.latest_order_date
FROM fact_subscription AS s
JOIN dim_restaurant    AS r USING (restaurant_id)
JOIN dim_plan          AS p USING (plan_id)
LEFT JOIN orders      AS px ON px.restaurant_id = r.restaurant_id
WHERE s.end_date IS NULL          -- Current subscription period only.
ORDER BY gmv_eur DESC
LIMIT 20;

-- >>> inactive_customers
-- Anti-join: active customers with no completed order in the last 60 days.
-- This produces a practical retention-risk outreach list.
SELECT r.restaurant_id,
       r.restaurant_name,
       r.market,
       p.plan_name,
       s.mrr_eur,
       MAX(o.order_date)                                        AS latest_order_date,
       CAST(julianday('2026-08-31') - julianday(MAX(o.order_date)) AS INTEGER) AS days_since_last_order
FROM fact_subscription AS s
JOIN dim_restaurant    AS r USING (restaurant_id)
JOIN dim_plan          AS p USING (plan_id)
LEFT JOIN fact_order   AS o
       ON o.restaurant_id = r.restaurant_id AND o.order_status = 'completed'
WHERE s.end_date IS NULL
GROUP BY r.restaurant_id, r.restaurant_name, r.market, p.plan_name, s.mrr_eur
HAVING MAX(o.order_date) IS NULL
    OR julianday('2026-08-31') - julianday(MAX(o.order_date)) > 60
ORDER BY s.mrr_eur DESC, days_since_last_order DESC;

-- >>> churn_reasons
-- Churn volume, lost MRR, and tenure by reason.
SELECT s.churn_reason                       AS churn_reason,
       COUNT(*)                             AS churned_customers,
       ROUND(SUM(s.mrr_eur), 2)             AS lost_mrr_eur,
       ROUND(AVG(s.tenure_days) / 30.4, 1)  AS average_tenure_months,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_churned_customers
FROM fact_subscription AS s
WHERE s.end_type = 'churn'
GROUP BY s.churn_reason
ORDER BY churned_customers DESC;

-- >>> support_and_churn
-- Relationship between support intensity and churn incidence.
WITH tickets AS (
    SELECT restaurant_id,
           COUNT(*)                 AS n_tickets,
           AVG(satisfaction_score)  AS average_csat
    FROM fact_support_ticket
    GROUP BY restaurant_id
),
churn_status AS (
    SELECT restaurant_id,
           MAX(CASE WHEN end_type = 'churn' THEN 1 ELSE 0 END) AS has_churned
    FROM fact_subscription
    GROUP BY restaurant_id
)
SELECT CASE WHEN IFNULL(t.n_tickets, 0) = 0 THEN '0 tickets'
            WHEN t.n_tickets <= 2          THEN '1-2 tickets'
            WHEN t.n_tickets <= 5          THEN '3-5 tickets'
            ELSE                                '6 or more tickets' END AS ticket_band,
       COUNT(*)                                                       AS restaurants,
       SUM(e.has_churned)                                         AS churned_customers,
       ROUND(100.0 * SUM(e.has_churned) / COUNT(*), 1)            AS churn_pct,
       ROUND(AVG(t.average_csat), 2)                                  AS average_csat
FROM dim_restaurant AS r
JOIN churn_status         AS e USING (restaurant_id)
LEFT JOIN tickets   AS t USING (restaurant_id)
GROUP BY ticket_band
ORDER BY ticket_band;

-- >>> campaign_coverage
-- Start from the campaign dimension to retain campaigns with no assignments
-- and distinguish experiments from targeted campaigns.
SELECT c.campaign_id,
       c.campaign_name,
       c.campaign_type,
       c.budget_eur,
       CASE WHEN c.is_experiment = 1 THEN 'A/B experiment' ELSE 'Targeted campaign' END AS campaign_class,
       COUNT(a.restaurant_id)                                   AS assigned_restaurants,
       COUNT(DISTINCT a.assignment_group)                       AS assignment_groups
FROM dim_campaign AS c
LEFT JOIN fact_campaign_assignment AS a USING (campaign_id)
GROUP BY c.campaign_id, c.campaign_name, c.campaign_type, c.budget_eur, c.is_experiment
ORDER BY c.campaign_id;
