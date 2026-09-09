-- =====================================================================
-- 02_joins.sql - INNER, LEFT y anti-joins entre restaurantes,
-- suscripciones, planes, pedidos y campanas.
-- =====================================================================

-- >>> ficha_cliente
-- INNER JOIN de tres tablas + LEFT JOIN a una agregacion: la ficha comercial
-- que pediria un account manager.
WITH pedidos AS (
    SELECT restaurant_id,
           COUNT(*)               AS pedidos,
           SUM(order_value_eur)   AS gmv_eur,
           MAX(order_date)        AS ultimo_pedido
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
       s.start_date                       AS alta_tramo,
       IFNULL(px.pedidos, 0)              AS pedidos,
       ROUND(IFNULL(px.gmv_eur, 0), 2)    AS gmv_eur,
       px.ultimo_pedido
FROM fact_subscription AS s
JOIN dim_restaurant    AS r USING (restaurant_id)
JOIN dim_plan          AS p USING (plan_id)
LEFT JOIN pedidos      AS px ON px.restaurant_id = r.restaurant_id
WHERE s.end_date IS NULL          -- solo el tramo vigente
ORDER BY gmv_eur DESC
LIMIT 20;

-- >>> clientes_sin_actividad
-- ANTI-JOIN: clientes activos que NO han pedido nada en los ultimos 60 dias
-- del periodo. Es la lista de riesgo que usaria el equipo de retencion.
SELECT r.restaurant_id,
       r.restaurant_name,
       r.market,
       p.plan_name,
       s.mrr_eur,
       MAX(o.order_date)                                        AS ultimo_pedido,
       CAST(julianday('2026-08-31') - julianday(MAX(o.order_date)) AS INTEGER) AS dias_sin_pedidos
FROM fact_subscription AS s
JOIN dim_restaurant    AS r USING (restaurant_id)
JOIN dim_plan          AS p USING (plan_id)
LEFT JOIN fact_order   AS o
       ON o.restaurant_id = r.restaurant_id AND o.order_status = 'completed'
WHERE s.end_date IS NULL
GROUP BY r.restaurant_id, r.restaurant_name, r.market, p.plan_name, s.mrr_eur
HAVING MAX(o.order_date) IS NULL
    OR julianday('2026-08-31') - julianday(MAX(o.order_date)) > 60
ORDER BY s.mrr_eur DESC, dias_sin_pedidos DESC;

-- >>> motivos_de_baja
-- Bajas por motivo y mercado, con el MRR que se perdio por cada motivo.
SELECT s.churn_reason                       AS motivo,
       COUNT(*)                             AS bajas,
       ROUND(SUM(s.mrr_eur), 2)             AS mrr_perdido_eur,
       ROUND(AVG(s.tenure_days) / 30.4, 1)  AS antiguedad_media_meses,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_bajas
FROM fact_subscription AS s
WHERE s.end_type = 'churn'
GROUP BY s.churn_reason
ORDER BY bajas DESC;

-- >>> soporte_y_baja
-- Cruce soporte <-> retencion: relacion entre tickets y probabilidad de baja.
WITH tickets AS (
    SELECT restaurant_id,
           COUNT(*)                 AS n_tickets,
           AVG(satisfaction_score)  AS csat_medio
    FROM fact_support_ticket
    GROUP BY restaurant_id
),
estado AS (
    SELECT restaurant_id,
           MAX(CASE WHEN end_type = 'churn' THEN 1 ELSE 0 END) AS ha_causado_baja
    FROM fact_subscription
    GROUP BY restaurant_id
)
SELECT CASE WHEN IFNULL(t.n_tickets, 0) = 0 THEN '0 tickets'
            WHEN t.n_tickets <= 2          THEN '1-2 tickets'
            WHEN t.n_tickets <= 5          THEN '3-5 tickets'
            ELSE                                '6 o mas tickets' END AS tramo_tickets,
       COUNT(*)                                                       AS restaurantes,
       SUM(e.ha_causado_baja)                                         AS bajas,
       ROUND(100.0 * SUM(e.ha_causado_baja) / COUNT(*), 1)            AS pct_baja,
       ROUND(AVG(t.csat_medio), 2)                                    AS csat_medio
FROM dim_restaurant AS r
JOIN estado         AS e USING (restaurant_id)
LEFT JOIN tickets   AS t USING (restaurant_id)
GROUP BY tramo_tickets
ORDER BY tramo_tickets;

-- >>> cobertura_campanas
-- LEFT JOIN desde la dimension de campanas para ver tambien las que no
-- tienen asignaciones, y separar el experimento del resto.
SELECT c.campaign_id,
       c.campaign_name,
       c.campaign_type,
       c.budget_eur,
       CASE WHEN c.is_experiment = 1 THEN 'Experimento A/B' ELSE 'Campana dirigida' END AS tipo,
       COUNT(a.restaurant_id)                                   AS restaurantes_asignados,
       COUNT(DISTINCT a.assignment_group)                       AS n_grupos
FROM dim_campaign AS c
LEFT JOIN fact_campaign_assignment AS a USING (campaign_id)
GROUP BY c.campaign_id, c.campaign_name, c.campaign_type, c.budget_eur, c.is_experiment
ORDER BY c.campaign_id;
