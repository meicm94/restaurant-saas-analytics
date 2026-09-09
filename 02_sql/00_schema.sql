-- =====================================================================
-- 00_schema.sql - data model and analytical conventions
-- Database: db/restaurant_saas.db (SQLite)
-- =====================================================================
--
-- STAR SCHEMA
--
--   dim_restaurant (600)          dim_plan (4)         dim_date (608 days)
--        |                            |                      |
--        +--------+-------------------+----------+-----------+
--                 |                              |
--          fact_subscription (701)         fact_order (~250k)
--          fact_support_ticket (~2.1k)     fact_campaign_assignment (683)
--                                          dim_campaign (3)
--
-- GRAIN
--   fact_order              1 row = 1 order
--   fact_subscription       1 row = 1 continuous subscription period for one
--                           restaurant and plan. A plan change closes the current
--                           period at month-end and opens another on day one of
--                           the next month, preventing overlapping active periods.
--   fact_support_ticket     1 row = 1 support ticket
--
-- BUSINESS CONVENTIONS
--   * Active in month M    = start_date <= month-end and
--                           (end_date IS NULL OR end_date >= month-end).
--                           Metrics therefore use a month-end snapshot.
--   * Churn in month M     = end_type = 'churn' and end_date falls within M.
--                           The customer is active in M and absent from M+1.
--   * Customer churn rate = customers lost in M / active customers at M-1 close.
--   * GMV                 = order_value_eur for completed orders only. Cancelled
--                           and refunded orders remain in the fact table but are
--                           excluded from revenue metrics.
--   * MRR                 = mrr_eur for active subscription periods. List price
--                           is not MRR because discounts may apply.
--   * Total revenue       = MRR + GMV commission at the applicable plan rate.
--   * Minimum term        = two months, so cohorts retain 100% in M0 and M1;
--                           the earliest possible churn appears in M2.
--
-- PORTABILITY TO T-SQL / MICROSOFT FABRIC
--   The queries use ANSI SQL plus window functions. For T-SQL, replace:
--     SQLite                                  T-SQL / Fabric
--     ------------------------------------    -----------------------------
--     strftime('%Y-%m', d)                    FORMAT(d,'yyyy-MM')
--     date(d,'start of month')                DATEFROMPARTS(YEAR(d),MONTH(d),1)
--     date(d,'+1 month','-1 day')             EOMONTH(d)
--     julianday(a) - julianday(b)             DATEDIFF(day, b, a)
--     CAST(x AS REAL)                         CAST(x AS FLOAT)
--     IFNULL(a,b)                             ISNULL(a,b) / COALESCE(a,b)
--     LIMIT 10                                TOP (10)
--   Dates are stored as ISO TEXT ('YYYY-MM-DD') because SQLite has no native
--   DATE storage class. They would be native DATE values in T-SQL.
--
-- HOW TO RUN
--   python 02_sql/run_sql.py            (run all queries and export CSV results)
--   sqlite3 db/restaurant_saas.db < 02_sql/04_saas_metrics.sql
-- =====================================================================

-- >>> tables
SELECT name AS table_name,
       (SELECT COUNT(*) FROM pragma_table_info(m.name)) AS n_columns
FROM sqlite_master AS m
WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
ORDER BY name;

-- >>> one_active_subscription_per_month_check
-- Integrity check: a restaurant cannot have overlapping active subscriptions
-- in the same month-end snapshot.
WITH months AS (
    SELECT DISTINCT month_start AS month,
           date(month_start, '+1 month', '-1 day') AS month_ends
    FROM dim_date
)
SELECT COUNT(*) AS overlapping_restaurant_months
FROM (
    SELECT m.month, s.restaurant_id, COUNT(*) AS subscription_periods
    FROM months AS m
    JOIN fact_subscription AS s
      ON s.start_date <= m.month_ends
     AND (s.end_date IS NULL OR s.end_date >= m.month_ends)
    GROUP BY m.month, s.restaurant_id
    HAVING COUNT(*) > 1
);
