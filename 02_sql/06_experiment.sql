-- =====================================================================
-- 06_experiment.sql - lectura del experimento A/B en SQL
-- Campana CMP-003 "New onboarding flow": los restaurantes dados de alta
-- entre 2026-02-01 y 2026-06-30 se reparten al azar entre control y
-- tratamiento. Metrica principal: pedidos completados en los 30 primeros
-- dias de vida del restaurante.
--
-- El analisis estadistico completo (intervalos, OLS) esta en
-- 04_experiment/ab_test_onboarding.py. Aqui se calculan los agregados,
-- que es lo que normalmente se pide en una prueba tecnica.
-- =====================================================================

-- >>> equilibrio_de_grupos
-- Antes de mirar el resultado: comprobar que la aleatorizacion dejo grupos
-- comparables. Si aqui hay diferencias grandes, el resultado no vale.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS grupo, r.market, r.city_size,
           r.cuisine_type, r.is_chain, r.acquisition_channel, r.signup_date
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
)
SELECT grupo,
       COUNT(*)                                                          AS restaurantes,
       ROUND(100.0 * SUM(CASE WHEN market = 'DK' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_dk,
       ROUND(100.0 * SUM(CASE WHEN city_size = 'Metro' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_metro,
       ROUND(100.0 * SUM(is_chain) / COUNT(*), 1)                        AS pct_cadena,
       ROUND(100.0 * SUM(CASE WHEN acquisition_channel = 'Direct sales' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                              AS pct_venta_directa,
       MIN(signup_date)                                                  AS primera_alta,
       MAX(signup_date)                                                  AS ultima_alta
FROM exp
GROUP BY grupo
ORDER BY grupo;

-- >>> resultado_principal
-- Pedidos completados en los primeros 30 dias, por grupo.
-- Se excluyen los restaurantes que no han cumplido 30 dias dentro del
-- periodo de datos, para no comparar ventanas de distinta longitud.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS grupo, r.signup_date,
           date(r.signup_date, '+29 days') AS fin_ventana
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
      AND date(r.signup_date, '+29 days') <= '2026-08-31'
),
por_restaurante AS (
    SELECT e.restaurant_id,
           e.grupo,
           COUNT(o.order_id)                    AS pedidos_30d,
           IFNULL(SUM(o.order_value_eur), 0)    AS gmv_30d,
           MAX(CASE WHEN o.order_date <= date(e.signup_date, '+6 days') THEN 1 ELSE 0 END) AS activado_7d
    FROM exp AS e
    LEFT JOIN fact_order AS o
           ON o.restaurant_id = e.restaurant_id
          AND o.order_status = 'completed'
          AND o.order_date BETWEEN e.signup_date AND e.fin_ventana
    GROUP BY e.restaurant_id, e.grupo
)
SELECT grupo,
       COUNT(*)                                     AS restaurantes,
       ROUND(AVG(pedidos_30d), 2)                   AS pedidos_30d_medios,
       ROUND(AVG(gmv_30d), 2)                       AS gmv_30d_medio_eur,
       ROUND(100.0 * AVG(activado_7d), 1)           AS activacion_7d_pct,
       -- desviacion tipica muestral, necesaria para el intervalo de confianza
       ROUND(SQRT(SUM((pedidos_30d - (SELECT AVG(p2.pedidos_30d) FROM por_restaurante AS p2
                                      WHERE p2.grupo = por_restaurante.grupo))
                      * (pedidos_30d - (SELECT AVG(p2.pedidos_30d) FROM por_restaurante AS p2
                                        WHERE p2.grupo = por_restaurante.grupo)))
                  / (COUNT(*) - 1)), 2)             AS desv_tipica_pedidos
FROM por_restaurante
GROUP BY grupo
ORDER BY grupo;

-- >>> diferencia_y_uplift
-- La diferencia entre grupos en una sola fila, que es lo que acaba en el
-- resumen para negocio.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS grupo, r.signup_date,
           date(r.signup_date, '+29 days') AS fin_ventana
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
      AND date(r.signup_date, '+29 days') <= '2026-08-31'
),
por_restaurante AS (
    SELECT e.restaurant_id, e.grupo,
           COUNT(o.order_id)                 AS pedidos_30d,
           IFNULL(SUM(o.order_value_eur), 0) AS gmv_30d
    FROM exp AS e
    LEFT JOIN fact_order AS o
           ON o.restaurant_id = e.restaurant_id
          AND o.order_status = 'completed'
          AND o.order_date BETWEEN e.signup_date AND e.fin_ventana
    GROUP BY e.restaurant_id, e.grupo
),
medias AS (
    SELECT AVG(CASE WHEN grupo = 'treatment' THEN pedidos_30d END) AS trat_pedidos,
           AVG(CASE WHEN grupo = 'control'   THEN pedidos_30d END) AS ctrl_pedidos,
           AVG(CASE WHEN grupo = 'treatment' THEN gmv_30d END)     AS trat_gmv,
           AVG(CASE WHEN grupo = 'control'   THEN gmv_30d END)     AS ctrl_gmv
    FROM por_restaurante
)
SELECT ROUND(ctrl_pedidos, 2)                                          AS control_pedidos_30d,
       ROUND(trat_pedidos, 2)                                          AS tratamiento_pedidos_30d,
       ROUND(trat_pedidos - ctrl_pedidos, 2)                           AS diferencia_pedidos,
       ROUND(100.0 * (trat_pedidos - ctrl_pedidos) / ctrl_pedidos, 1)  AS uplift_pedidos_pct,
       ROUND(ctrl_gmv, 2)                                              AS control_gmv_30d,
       ROUND(trat_gmv, 2)                                              AS tratamiento_gmv_30d,
       ROUND(100.0 * (trat_gmv - ctrl_gmv) / ctrl_gmv, 1)              AS uplift_gmv_pct
FROM medias;

-- >>> retencion_a_90_dias
-- Metrica secundaria: seguian activos 90 dias despues del alta?
-- Solo se incluyen los que ya han tenido tiempo de cumplirlos.
WITH exp AS (
    SELECT a.restaurant_id, a.assignment_group AS grupo, r.signup_date,
           date(r.signup_date, '+90 days') AS corte
    FROM fact_campaign_assignment AS a
    JOIN dim_restaurant AS r USING (restaurant_id)
    WHERE a.campaign_id = 'CMP-003'
      AND date(r.signup_date, '+90 days') <= '2026-08-31'
)
SELECT e.grupo,
       COUNT(*)                                                   AS restaurantes,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM fact_subscription AS s
                             WHERE s.restaurant_id = e.restaurant_id
                               AND s.start_date <= e.corte
                               AND (s.end_date IS NULL OR s.end_date >= e.corte))
                THEN 1 ELSE 0 END)                                AS activos_a_90d,
       ROUND(100.0 * SUM(CASE WHEN EXISTS (SELECT 1 FROM fact_subscription AS s
                                           WHERE s.restaurant_id = e.restaurant_id
                                             AND s.start_date <= e.corte
                                             AND (s.end_date IS NULL OR s.end_date >= e.corte))
                              THEN 1 ELSE 0 END) / COUNT(*), 1)   AS retencion_90d_pct
FROM exp AS e
GROUP BY e.grupo
ORDER BY e.grupo;
