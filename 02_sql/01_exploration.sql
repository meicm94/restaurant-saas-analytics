-- =====================================================================
-- 01_exploration.sql - SELECT, WHERE, GROUP BY, CASE, HAVING
-- Bloque de la semana 1: fundamentos de consulta.
-- =====================================================================

-- >>> volumen_por_mes
-- Pedidos, GMV y ticket medio por mes. Solo pedidos completados: los
-- cancelados y reembolsados no son ingreso.
SELECT strftime('%Y-%m', order_date)               AS mes,
       COUNT(*)                                    AS pedidos,
       ROUND(SUM(order_value_eur), 2)              AS gmv_eur,
       ROUND(AVG(order_value_eur), 2)              AS ticket_medio_eur,
       COUNT(DISTINCT restaurant_id)               AS restaurantes_con_pedidos
FROM fact_order
WHERE order_status = 'completed'
GROUP BY mes
ORDER BY mes;

-- >>> calidad_de_pedidos
-- Reparto de estados y su peso economico. CASE para agrupar categorias.
SELECT order_status,
       CASE WHEN order_status = 'completed' THEN 'Cuenta como ingreso'
            ELSE 'No cuenta como ingreso' END      AS tratamiento,
       COUNT(*)                                    AS pedidos,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_pedidos,
       ROUND(SUM(order_value_eur), 2)              AS valor_eur
FROM fact_order
GROUP BY order_status
ORDER BY pedidos DESC;

-- >>> segmentacion_por_ticket
-- CASE para crear tramos de ticket medio (banding), tipico en analisis comercial.
SELECT CASE
           WHEN order_value_eur <  15 THEN 'A. Menos de 15 EUR'
           WHEN order_value_eur <  30 THEN 'B. 15-30 EUR'
           WHEN order_value_eur <  50 THEN 'C. 30-50 EUR'
           WHEN order_value_eur < 100 THEN 'D. 50-100 EUR'
           ELSE                            'E. 100 EUR o mas'
       END                                         AS tramo_ticket,
       COUNT(*)                                    AS pedidos,
       ROUND(SUM(order_value_eur), 2)              AS gmv_eur,
       ROUND(100.0 * SUM(order_value_eur) / SUM(SUM(order_value_eur)) OVER (), 2) AS pct_gmv
FROM fact_order
WHERE order_status = 'completed'
GROUP BY tramo_ticket
ORDER BY tramo_ticket;

-- >>> mercado_y_canal
-- Doble agrupacion y porcentaje de pedidos por app.
SELECT r.market,
       r.market_name,
       COUNT(*)                                                        AS pedidos,
       ROUND(SUM(o.order_value_eur), 2)                                AS gmv_eur,
       ROUND(AVG(o.order_value_eur), 2)                                AS ticket_medio_eur,
       ROUND(100.0 * SUM(CASE WHEN o.order_channel = 'app' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                            AS pct_app,
       ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'delivery' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                            AS pct_delivery
FROM fact_order AS o
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE o.order_status = 'completed'
GROUP BY r.market, r.market_name
ORDER BY gmv_eur DESC;

-- >>> top_restaurantes
-- HAVING para filtrar despues de agregar: solo restaurantes con volumen real.
SELECT o.restaurant_id,
       r.restaurant_name,
       r.market,
       r.cuisine_type,
       COUNT(*)                          AS pedidos,
       ROUND(SUM(o.order_value_eur), 2)  AS gmv_eur,
       ROUND(AVG(o.order_value_eur), 2)  AS ticket_medio_eur
FROM fact_order AS o
JOIN dim_restaurant AS r USING (restaurant_id)
WHERE o.order_status = 'completed'
GROUP BY o.restaurant_id, r.restaurant_name, r.market, r.cuisine_type
HAVING COUNT(*) >= 200
ORDER BY gmv_eur DESC
LIMIT 15;

-- >>> efecto_fin_de_semana
-- Patron semanal: insumo directo para decidir cuando lanzar promociones.
SELECT CASE CAST(strftime('%w', order_date) AS INTEGER)
           WHEN 0 THEN '7 Domingo' WHEN 1 THEN '1 Lunes'   WHEN 2 THEN '2 Martes'
           WHEN 3 THEN '3 Miercoles' WHEN 4 THEN '4 Jueves' WHEN 5 THEN '5 Viernes'
           ELSE '6 Sabado' END                    AS dia_semana,
       COUNT(*)                                   AS pedidos,
       ROUND(AVG(order_value_eur), 2)             AS ticket_medio_eur
FROM fact_order
WHERE order_status = 'completed'
GROUP BY dia_semana
ORDER BY dia_semana;
