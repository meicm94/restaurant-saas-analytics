-- =====================================================================
-- 04_saas_metrics.sql - metricas SaaS: MRR, ARPU, GMV, churn, NRR
-- Este es el bloque que hay que saber defender en una entrevista:
-- no basta con calcularlo, hay que poder explicar la definicion.
-- =====================================================================

-- >>> mrr_y_clientes_por_mes
-- Foto a fin de mes: cuantos clientes activos, cuanto MRR y cuanto GMV.
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
),
activos AS (
    SELECT m.mes, s.restaurant_id, s.plan_id, s.mrr_eur
    FROM meses AS m
    JOIN fact_subscription AS s
      ON s.start_date <= m.fin_mes
     AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
),
gmv AS (
    SELECT strftime('%Y-%m-01', order_date) AS mes,
           COUNT(*)                         AS pedidos,
           SUM(order_value_eur)             AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY mes
)
SELECT a.mes,
       COUNT(*)                                        AS clientes_activos,
       ROUND(SUM(a.mrr_eur), 2)                        AS mrr_eur,
       ROUND(SUM(a.mrr_eur) * 12, 2)                   AS arr_eur,
       ROUND(SUM(a.mrr_eur) / COUNT(*), 2)             AS arpu_eur,
       IFNULL(g.pedidos, 0)                            AS pedidos,
       ROUND(IFNULL(g.gmv_eur, 0), 2)                  AS gmv_eur,
       ROUND(IFNULL(g.gmv_eur, 0) / COUNT(*), 2)       AS gmv_por_cliente_eur,
       ROUND(100.0 * (SUM(a.mrr_eur) - LAG(SUM(a.mrr_eur)) OVER (ORDER BY a.mes))
             / LAG(SUM(a.mrr_eur)) OVER (ORDER BY a.mes), 2) AS crecimiento_mrr_pct
FROM activos AS a
LEFT JOIN gmv AS g ON g.mes = a.mes
GROUP BY a.mes, g.pedidos, g.gmv_eur
ORDER BY a.mes;

-- >>> movimiento_de_mrr
-- Descomposicion del MRR: nuevo, expansion, contraccion, baja y reactivacion.
-- Se construye un panel restaurante-mes y se compara con el mes anterior
-- mediante LAG. Es la consulta que explica POR QUE sube o baja el MRR.
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
),
panel AS (
    SELECT m.mes,
           r.restaurant_id,
           IFNULL(SUM(s.mrr_eur), 0) AS mrr
    FROM meses AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.fin_mes
          AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
    GROUP BY m.mes, r.restaurant_id
),
comparado AS (
    SELECT mes,
           restaurant_id,
           mrr,
           IFNULL(LAG(mrr) OVER (PARTITION BY restaurant_id ORDER BY mes), 0) AS mrr_prev,
           IFNULL(MAX(mrr) OVER (PARTITION BY restaurant_id ORDER BY mes
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS mrr_max_previo
    FROM panel
)
SELECT mes,
       ROUND(SUM(CASE WHEN mrr_prev = 0 AND mrr > 0 AND mrr_max_previo = 0
                      THEN mrr ELSE 0 END), 2)                      AS mrr_nuevo,
       ROUND(SUM(CASE WHEN mrr_prev = 0 AND mrr > 0 AND mrr_max_previo > 0
                      THEN mrr ELSE 0 END), 2)                      AS mrr_reactivado,
       ROUND(SUM(CASE WHEN mrr_prev > 0 AND mrr > mrr_prev
                      THEN mrr - mrr_prev ELSE 0 END), 2)           AS mrr_expansion,
       ROUND(SUM(CASE WHEN mrr_prev > 0 AND mrr > 0 AND mrr < mrr_prev
                      THEN mrr - mrr_prev ELSE 0 END), 2)           AS mrr_contraccion,
       ROUND(SUM(CASE WHEN mrr_prev > 0 AND mrr = 0
                      THEN -mrr_prev ELSE 0 END), 2)                AS mrr_baja,
       ROUND(SUM(mrr - mrr_prev), 2)                                AS mrr_neto,
       ROUND(SUM(mrr), 2)                                           AS mrr_cierre
FROM comparado
GROUP BY mes
HAVING SUM(mrr) > 0
ORDER BY mes;

-- >>> churn_y_nrr
-- Churn de clientes (logo churn), churn de ingresos y Net Revenue Retention.
-- Denominador: la base activa al cierre del mes anterior. Esa eleccion hay
-- que decirla siempre en voz alta, porque cambia el resultado.
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
),
panel AS (
    SELECT m.mes, r.restaurant_id, IFNULL(SUM(s.mrr_eur), 0) AS mrr
    FROM meses AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.fin_mes
          AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
    GROUP BY m.mes, r.restaurant_id
),
comparado AS (
    SELECT mes, restaurant_id, mrr,
           IFNULL(LAG(mrr) OVER (PARTITION BY restaurant_id ORDER BY mes), 0) AS mrr_prev
    FROM panel
)
SELECT mes,
       SUM(CASE WHEN mrr_prev > 0 THEN 1 ELSE 0 END)                       AS activos_inicio,
       SUM(CASE WHEN mrr_prev > 0 AND mrr = 0 THEN 1 ELSE 0 END)           AS bajas,
       ROUND(100.0 * SUM(CASE WHEN mrr_prev > 0 AND mrr = 0 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN mrr_prev > 0 THEN 1 ELSE 0 END), 0), 2) AS churn_clientes_pct,
       ROUND(100.0 * SUM(CASE WHEN mrr_prev > 0 AND mrr = 0 THEN mrr_prev ELSE 0 END)
             / NULLIF(SUM(CASE WHEN mrr_prev > 0 THEN mrr_prev ELSE 0 END), 0), 2) AS churn_ingresos_pct,
       ROUND(100.0 * SUM(CASE WHEN mrr_prev > 0 THEN mrr ELSE 0 END)
             / NULLIF(SUM(CASE WHEN mrr_prev > 0 THEN mrr_prev ELSE 0 END), 0), 1) AS nrr_pct
FROM comparado
GROUP BY mes
HAVING SUM(CASE WHEN mrr_prev > 0 THEN 1 ELSE 0 END) > 0
ORDER BY mes;

-- >>> ingresos_totales
-- El negocio no vive solo de la suscripcion: tambien cobra comision sobre el
-- GMV, y la comision depende del plan. MRR + comision = ingreso total.
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
),
activos AS (
    SELECT m.mes, s.restaurant_id, s.plan_id, s.mrr_eur
    FROM meses AS m
    JOIN fact_subscription AS s
      ON s.start_date <= m.fin_mes
     AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
),
gmv_rm AS (
    SELECT restaurant_id,
           strftime('%Y-%m-01', order_date) AS mes,
           SUM(order_value_eur)             AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id, mes
)
SELECT a.mes,
       ROUND(SUM(a.mrr_eur), 2)                                     AS mrr_eur,
       ROUND(SUM(IFNULL(g.gmv_eur, 0)), 2)                          AS gmv_eur,
       ROUND(SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate), 2)      AS comision_eur,
       ROUND(SUM(a.mrr_eur) + SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate), 2) AS ingreso_total_eur,
       ROUND(100.0 * SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate)
             / (SUM(a.mrr_eur) + SUM(IFNULL(g.gmv_eur, 0) * p.commission_rate)), 1) AS pct_ingreso_por_comision
FROM activos AS a
JOIN dim_plan AS p USING (plan_id)
LEFT JOIN gmv_rm AS g ON g.restaurant_id = a.restaurant_id AND g.mes = a.mes
GROUP BY a.mes
ORDER BY a.mes;

-- >>> metricas_por_plan
-- Ultima foto disponible (agosto 2026) abierta por plan.
WITH ultimo AS (SELECT '2026-08-31' AS fin_mes, '2026-08-01' AS mes),
activos AS (
    SELECT u.mes, s.restaurant_id, s.plan_id, s.mrr_eur
    FROM ultimo AS u
    JOIN fact_subscription AS s
      ON s.start_date <= u.fin_mes
     AND (s.end_date IS NULL OR s.end_date >= u.fin_mes)
),
gmv AS (
    SELECT restaurant_id, SUM(order_value_eur) AS gmv_eur, COUNT(*) AS pedidos
    FROM fact_order
    WHERE order_status = 'completed'
      AND order_date >= '2026-08-01'
    GROUP BY restaurant_id
),
bajas AS (
    SELECT plan_id, COUNT(*) AS bajas_historicas
    FROM fact_subscription
    WHERE end_type = 'churn'
    GROUP BY plan_id
)
SELECT p.plan_name,
       p.monthly_price_eur                                  AS precio_lista_eur,
       COUNT(*)                                             AS clientes,
       ROUND(SUM(a.mrr_eur), 2)                             AS mrr_eur,
       ROUND(AVG(a.mrr_eur), 2)                             AS arpu_eur,
       ROUND(100.0 * (1 - AVG(a.mrr_eur) / p.monthly_price_eur), 1) AS descuento_medio_pct,
       ROUND(SUM(IFNULL(g.gmv_eur, 0)), 2)                  AS gmv_mes_eur,
       ROUND(AVG(IFNULL(g.pedidos, 0)), 1)                  AS pedidos_medios,
       IFNULL(b.bajas_historicas, 0)                        AS bajas_historicas
FROM activos AS a
JOIN dim_plan AS p USING (plan_id)
LEFT JOIN gmv AS g ON g.restaurant_id = a.restaurant_id
LEFT JOIN bajas AS b ON b.plan_id = a.plan_id
GROUP BY p.plan_name, p.monthly_price_eur, b.bajas_historicas
ORDER BY p.monthly_price_eur;

-- >>> resumen_ejecutivo
-- Los seis numeros que irian en la primera pagina del dashboard.
WITH activos AS (
    SELECT s.restaurant_id, s.mrr_eur
    FROM fact_subscription AS s
    WHERE s.start_date <= '2026-08-31'
      AND (s.end_date IS NULL OR s.end_date >= '2026-08-31')
),
mes AS (
    SELECT COUNT(*) AS pedidos, SUM(order_value_eur) AS gmv
    FROM fact_order
    WHERE order_status = 'completed' AND order_date >= '2026-08-01'
),
bajas_12m AS (
    SELECT COUNT(*) AS n FROM fact_subscription
    WHERE end_type = 'churn' AND end_date >= '2025-09-01'
),
base_media AS (
    SELECT AVG(c) AS media FROM (
        SELECT strftime('%Y-%m', d.month_start) AS m, COUNT(*) AS c
        FROM (SELECT DISTINCT month_start FROM dim_date
              WHERE month_start >= '2025-09-01') AS d
        JOIN fact_subscription AS s
          ON s.start_date <= date(d.month_start, '+1 month', '-1 day')
         AND (s.end_date IS NULL OR s.end_date >= date(d.month_start, '+1 month', '-1 day'))
        GROUP BY m)
)
SELECT (SELECT COUNT(*) FROM activos)                                   AS clientes_activos,
       ROUND((SELECT SUM(mrr_eur) FROM activos), 2)                     AS mrr_eur,
       ROUND((SELECT SUM(mrr_eur) FROM activos) * 12, 2)                AS arr_eur,
       ROUND((SELECT SUM(mrr_eur) FROM activos) / (SELECT COUNT(*) FROM activos), 2) AS arpu_eur,
       (SELECT pedidos FROM mes)                                        AS pedidos_ultimo_mes,
       ROUND((SELECT gmv FROM mes), 2)                                  AS gmv_ultimo_mes_eur,
       ROUND(100.0 * (SELECT n FROM bajas_12m) / (SELECT media FROM base_media), 1) AS churn_anual_pct;
