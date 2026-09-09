-- =====================================================================
-- 03_cte_windows.sql - CTE y funciones de ventana
-- ROW_NUMBER, LAG, RANK, NTILE, SUM() OVER, medias moviles.
-- =====================================================================

-- >>> crecimiento_mensual
-- LAG para variacion mes a mes y media movil de 3 meses del GMV.
WITH mensual AS (
    SELECT strftime('%Y-%m', order_date) AS mes,
           COUNT(*)                      AS pedidos,
           SUM(order_value_eur)          AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY mes
)
SELECT mes,
       pedidos,
       ROUND(gmv_eur, 2)                                          AS gmv_eur,
       ROUND(LAG(gmv_eur) OVER (ORDER BY mes), 2)                 AS gmv_mes_anterior,
       ROUND(100.0 * (gmv_eur - LAG(gmv_eur) OVER (ORDER BY mes))
             / LAG(gmv_eur) OVER (ORDER BY mes), 2)               AS crecimiento_mom_pct,
       ROUND(AVG(gmv_eur) OVER (ORDER BY mes
                                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS media_movil_3m,
       ROUND(SUM(gmv_eur) OVER (ORDER BY mes), 2)                 AS gmv_acumulado
FROM mensual
ORDER BY mes;

-- >>> primer_y_ultimo_pedido
-- ROW_NUMBER para quedarse con el primer pedido de cada restaurante y medir
-- el "time to first order" desde el alta: KPI clasico de onboarding.
WITH ordenados AS (
    SELECT o.restaurant_id,
           o.order_id,
           o.order_date,
           o.order_value_eur,
           ROW_NUMBER() OVER (PARTITION BY o.restaurant_id ORDER BY o.order_date, o.order_id) AS rn
    FROM fact_order AS o
    WHERE o.order_status = 'completed'
)
SELECT r.market,
       COUNT(*)                                                                AS restaurantes,
       ROUND(AVG(julianday(x.order_date) - julianday(r.signup_date)), 2)       AS dias_hasta_1er_pedido,
       ROUND(AVG(x.order_value_eur), 2)                                        AS ticket_1er_pedido
FROM ordenados AS x
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE x.rn = 1
GROUP BY r.market
ORDER BY dias_hasta_1er_pedido;

-- >>> ranking_por_mercado
-- RANK dentro de cada mercado + peso sobre el GMV de su propio mercado.
-- El filtro por posicion va en una CTE aparte porque no se puede filtrar por
-- una funcion de ventana en el WHERE del mismo SELECT (en T-SQL/Fabric
-- tampoco: hace falta subconsulta o CTE).
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
           RANK() OVER (PARTITION BY market ORDER BY gmv_eur DESC)         AS posicion,
           100.0 * gmv_eur / SUM(gmv_eur) OVER (PARTITION BY market)       AS pct_gmv_mercado
    FROM gmv
)
SELECT market, posicion, restaurant_id, restaurant_name,
       ROUND(gmv_eur, 2)         AS gmv_eur,
       ROUND(pct_gmv_mercado, 2) AS pct_gmv_mercado
FROM ranking
WHERE posicion <= 5
ORDER BY market, posicion;

-- >>> concentracion_pareto
-- NTILE para dividir la cartera en deciles y ver que parte del GMV aporta
-- el 10% de clientes mas grande.
WITH gmv AS (
    SELECT restaurant_id, SUM(order_value_eur) AS gmv_eur
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id
),
deciles AS (
    SELECT restaurant_id, gmv_eur,
           NTILE(10) OVER (ORDER BY gmv_eur DESC) AS decil
    FROM gmv
)
SELECT decil,
       COUNT(*)                                             AS restaurantes,
       ROUND(SUM(gmv_eur), 2)                               AS gmv_eur,
       ROUND(100.0 * SUM(gmv_eur) / SUM(SUM(gmv_eur)) OVER (), 2)         AS pct_gmv,
       ROUND(SUM(SUM(gmv_eur)) OVER (ORDER BY decil) * 100.0
             / SUM(SUM(gmv_eur)) OVER (), 2)                AS pct_gmv_acumulado
FROM deciles
GROUP BY decil
ORDER BY decil;

-- >>> tendencia_por_restaurante
-- Ventana por restaurante: pedidos del mes frente a la media de los 3 meses
-- anteriores. Sirve como alerta temprana de caida de actividad.
WITH rm AS (
    SELECT restaurant_id,
           strftime('%Y-%m', order_date) AS mes,
           COUNT(*)                      AS pedidos
    FROM fact_order
    WHERE order_status = 'completed'
    GROUP BY restaurant_id, mes
),
con_media AS (
    SELECT restaurant_id, mes, pedidos,
           AVG(pedidos) OVER (PARTITION BY restaurant_id ORDER BY mes
                              ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS media_3m_previa,
           ROW_NUMBER() OVER (PARTITION BY restaurant_id ORDER BY mes DESC) AS rn_desc
    FROM rm
)
SELECT c.restaurant_id,
       r.restaurant_name,
       r.market,
       c.mes                                            AS ultimo_mes,
       c.pedidos,
       ROUND(c.media_3m_previa, 1)                      AS media_3m_previa,
       ROUND(100.0 * (c.pedidos - c.media_3m_previa) / c.media_3m_previa, 1) AS variacion_pct
FROM con_media AS c
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE c.rn_desc = 1
  AND c.media_3m_previa IS NOT NULL
  AND c.pedidos < 0.6 * c.media_3m_previa
ORDER BY variacion_pct
LIMIT 20;
