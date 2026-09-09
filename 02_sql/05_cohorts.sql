-- =====================================================================
-- 05_cohorts.sql - cohortes de retencion
-- Cohorte = mes de alta. Indice = meses transcurridos desde el alta.
-- Es la vista que separa "estamos creciendo" de "estamos reteniendo".
-- =====================================================================

-- >>> retencion_larga
-- Formato largo: una fila por cohorte y mes de vida. Es el formato que hay
-- que llevar a Power BI (la matriz se pivota alli, no en SQL).
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
),
panel AS (
    SELECT m.mes,
           r.restaurant_id,
           r.signup_cohort AS cohorte,
           r.signup_month,
           CASE WHEN s.restaurant_id IS NULL THEN 0 ELSE 1 END AS activo,
           IFNULL(s.mrr_eur, 0) AS mrr
    FROM meses AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.fin_mes
          AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
    WHERE m.mes >= r.signup_month
),
indexado AS (
    SELECT cohorte,
           mes,
           restaurant_id,
           activo,
           mrr,
           (CAST(strftime('%Y', mes) AS INTEGER) * 12 + CAST(strftime('%m', mes) AS INTEGER))
         - (CAST(strftime('%Y', signup_month) AS INTEGER) * 12 + CAST(strftime('%m', signup_month) AS INTEGER))
             AS mes_de_vida
    FROM panel
),
tamano AS (
    SELECT cohorte, COUNT(DISTINCT restaurant_id) AS tamano_cohorte
    FROM indexado WHERE mes_de_vida = 0 GROUP BY cohorte
)
SELECT i.cohorte,
       t.tamano_cohorte,
       i.mes_de_vida,
       SUM(i.activo)                                                   AS activos,
       ROUND(100.0 * SUM(i.activo) / t.tamano_cohorte, 1)              AS retencion_pct,
       ROUND(SUM(i.mrr), 2)                                            AS mrr_eur,
       ROUND(SUM(i.mrr) / NULLIF(SUM(i.activo), 0), 2)                 AS arpu_eur
FROM indexado AS i
JOIN tamano AS t USING (cohorte)
GROUP BY i.cohorte, t.tamano_cohorte, i.mes_de_vida
ORDER BY i.cohorte, i.mes_de_vida;

-- >>> retencion_matriz
-- La misma informacion pivotada a M0..M9 para leerla de un vistazo.
-- Las celdas vacias son cohortes que todavia no han cumplido esa edad.
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
),
panel AS (
    SELECT m.mes, r.restaurant_id, r.signup_cohort AS cohorte, r.signup_month,
           CASE WHEN s.restaurant_id IS NULL THEN 0 ELSE 1 END AS activo
    FROM meses AS m
    CROSS JOIN dim_restaurant AS r
    LEFT JOIN fact_subscription AS s
           ON s.restaurant_id = r.restaurant_id
          AND s.start_date <= m.fin_mes
          AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
    WHERE m.mes >= r.signup_month
),
indexado AS (
    SELECT cohorte, restaurant_id, activo,
           (CAST(strftime('%Y', mes) AS INTEGER) * 12 + CAST(strftime('%m', mes) AS INTEGER))
         - (CAST(strftime('%Y', signup_month) AS INTEGER) * 12 + CAST(strftime('%m', signup_month) AS INTEGER))
             AS mes_de_vida
    FROM panel
),
base AS (
    SELECT cohorte, mes_de_vida, SUM(activo) AS activos
    FROM indexado GROUP BY cohorte, mes_de_vida
),
tamano AS (
    SELECT cohorte, activos AS n FROM base WHERE mes_de_vida = 0
)
SELECT b.cohorte,
       t.n AS altas,
       MAX(CASE WHEN b.mes_de_vida = 1 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M1,
       MAX(CASE WHEN b.mes_de_vida = 2 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M2,
       MAX(CASE WHEN b.mes_de_vida = 3 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M3,
       MAX(CASE WHEN b.mes_de_vida = 4 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M4,
       MAX(CASE WHEN b.mes_de_vida = 5 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M5,
       MAX(CASE WHEN b.mes_de_vida = 6 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M6,
       MAX(CASE WHEN b.mes_de_vida = 9 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M9,
       MAX(CASE WHEN b.mes_de_vida = 12 THEN ROUND(100.0 * b.activos / t.n, 0) END) AS M12
FROM base AS b
JOIN tamano AS t USING (cohorte)
GROUP BY b.cohorte, t.n
ORDER BY b.cohorte;

-- >>> supervivencia_por_mercado
-- Retencion a 3, 6 y 12 meses por mercado, contando solo los restaurantes
-- que han tenido tiempo de llegar a esa edad (si no, se infla el resultado).
WITH edad AS (
    SELECT r.restaurant_id,
           r.market,
           r.signup_date,
           CAST((julianday('2026-08-31') - julianday(r.signup_date)) / 30.44 AS INTEGER) AS meses_posibles,
           CAST((julianday(IFNULL((SELECT MAX(s.end_date) FROM fact_subscription AS s
                                   WHERE s.restaurant_id = r.restaurant_id AND s.end_type = 'churn'),
                                  '2026-08-31'))
                 - julianday(r.signup_date)) / 30.44 AS INTEGER) AS meses_vividos
    FROM dim_restaurant AS r
)
SELECT market,
       COUNT(*)                                                                AS restaurantes,
       ROUND(100.0 * SUM(CASE WHEN meses_posibles >= 3 AND meses_vividos >= 3 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN meses_posibles >= 3 THEN 1 ELSE 0 END), 0), 1)   AS retencion_3m_pct,
       ROUND(100.0 * SUM(CASE WHEN meses_posibles >= 6 AND meses_vividos >= 6 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN meses_posibles >= 6 THEN 1 ELSE 0 END), 0), 1)   AS retencion_6m_pct,
       ROUND(100.0 * SUM(CASE WHEN meses_posibles >= 12 AND meses_vividos >= 12 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN meses_posibles >= 12 THEN 1 ELSE 0 END), 0), 1)  AS retencion_12m_pct
FROM edad
GROUP BY market
ORDER BY retencion_6m_pct DESC;
