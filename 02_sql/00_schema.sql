-- =====================================================================
-- 00_schema.sql - modelo de datos y convenciones
-- Base: db/restaurant_saas.db (SQLite 3.45)
-- =====================================================================
--
-- MODELO EN ESTRELLA
--
--   dim_restaurant (600)          dim_plan (4)         dim_date (608 dias)
--        |                            |                      |
--        +--------+-------------------+----------+-----------+
--                 |                              |
--          fact_subscription (701)         fact_order (249.957)
--          fact_support_ticket (2.127)     fact_campaign_assignment (683)
--                                          dim_campaign (3)
--
-- GRANULARIDAD
--   fact_order              1 fila = 1 pedido
--   fact_subscription       1 fila = 1 "spell": tramo continuo de un
--                           restaurante en un mismo plan. Un cambio de plan
--                           cierra el tramo a fin de mes y abre otro el dia 1
--                           del mes siguiente, por lo que un restaurante nunca
--                           tiene dos tramos vivos en el mismo mes.
--   fact_support_ticket     1 fila = 1 ticket
--
-- CONVENCIONES DE NEGOCIO (importantes: definen todas las metricas)
--   * Activo en el mes M  = tramo con start_date <= fin de M
--                           y (end_date IS NULL O end_date >= fin de M).
--                           Es decir, foto a ultimo dia de mes.
--   * Baja en el mes M    = tramo con end_type = 'churn' y end_date dentro
--                           de M. Cuenta como activo en M y desaparece en M+1.
--   * Churn rate de M     = bajas en M / activos a cierre de M-1.
--   * GMV                 = suma de order_value_eur SOLO de pedidos
--                           'completed'. Los 'cancelled' y 'refunded' se
--                           excluyen de ingresos pero se conservan en la tabla.
--   * MRR                 = suma de mrr_eur de los tramos activos. Ojo: el
--                           precio de lista del plan NO es el MRR, porque hay
--                           descuentos (discount_pct).
--   * Ingresos totales    = MRR + comision sobre GMV (commission_rate del plan).
--   * Permanencia minima  = el contrato obliga a dos meses. Por eso ninguna
--                           cohorte pierde clientes en M0 ni en M1, y la primera
--                           baja posible aparece en M2.
--
-- PORTABILIDAD A T-SQL / MICROSOFT FABRIC
--   Las consultas usan solo ANSI SQL + funciones de ventana. Al llevarlas a
--   T-SQL hay que cambiar:
--     SQLite                                  T-SQL / Fabric
--     ------------------------------------    -----------------------------
--     strftime('%Y-%m', d)                    FORMAT(d,'yyyy-MM')
--     date(d,'start of month')                DATEFROMPARTS(YEAR(d),MONTH(d),1)
--     date(d,'+1 month','-1 day')             EOMONTH(d)
--     julianday(a) - julianday(b)             DATEDIFF(day, b, a)
--     CAST(x AS REAL)                         CAST(x AS FLOAT)
--     IFNULL(a,b)                             ISNULL(a,b) / COALESCE(a,b)
--     LIMIT 10                                TOP (10)
--   Las fechas se guardan como TEXT 'YYYY-MM-DD' porque SQLite no tiene tipo
--   DATE; en T-SQL serian DATE nativas.
--
-- COMO EJECUTAR
--   python 02_sql/run_sql.py            (ejecuta todo y exporta a outputs/sql_results)
--   sqlite3 db/restaurant_saas.db < 02_sql/04_saas_metrics.sql
-- =====================================================================

-- >>> tablas
SELECT name AS tabla,
       (SELECT COUNT(*) FROM pragma_table_info(m.name)) AS n_columnas
FROM sqlite_master AS m
WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
ORDER BY name;

-- >>> control_un_tramo_activo_por_mes
-- Comprobacion de la convencion: ningun restaurante puede tener dos tramos
-- vivos en la misma foto de fin de mes.
WITH meses AS (
    SELECT DISTINCT month_start AS mes,
           date(month_start, '+1 month', '-1 day') AS fin_mes
    FROM dim_date
)
SELECT COUNT(*) AS meses_con_solape
FROM (
    SELECT m.mes, s.restaurant_id, COUNT(*) AS tramos
    FROM meses AS m
    JOIN fact_subscription AS s
      ON s.start_date <= m.fin_mes
     AND (s.end_date IS NULL OR s.end_date >= m.fin_mes)
    GROUP BY m.mes, s.restaurant_id
    HAVING COUNT(*) > 1
);
