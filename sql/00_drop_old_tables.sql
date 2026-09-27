-- ============================================================
-- DROP OLD TABLES
-- Removes the first version of the database design (schema dbo)
-- before the raw / staging / mart layers are created.
-- Run this file ONCE. All data is reloaded from the sources later.
-- ============================================================

-- Tables are dropped child tables first,
-- so no foreign key blocks the drop

-- Old WooCommerce tables
DROP TABLE IF EXISTS
    dbo.order_items,
    dbo.orders,
    dbo.products,
    dbo.subcategories,
    dbo.categories,
    dbo.customers;

-- Old GA4 tables (first aggregated design)
DROP TABLE IF EXISTS
    dbo.ga4_daily_traffic,
    dbo.ga4_daily_funnel,
    dbo.ga4_landing_pages,
    dbo.ga4_product_interest,
    dbo.ga4_audience;

-- Old star-schema tables (now built later in the mart layer by dbt)
DROP TABLE IF EXISTS
    dbo.fact_ga4_events,
    dbo.fact_search_performance,
    dbo.dim_sessions,
    dbo.dim_users,
    dbo.dim_traffic_source,
    dbo.dim_device,
    dbo.dim_products,
    dbo.dim_date;

-- Check: no user tables should be left in dbo
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_TYPE = 'BASE TABLE';
