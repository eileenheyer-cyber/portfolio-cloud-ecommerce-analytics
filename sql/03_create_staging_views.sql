-- ============================================================
-- STAGING VIEWS
-- Cleaned source data, one view per raw table (1:1).
--
-- Rules for the staging layer:
--   * view name = name of the raw table, in schema staging
--   * only technical transformations: types (text → number/date),
--     '' → NULL, trimming, HTML unescape, merging technical duplicates,
--     URL → path, column names
--   * no joins between sources and no business rules (these belong to the mart)
--   * views are calculated when they are read, nothing is stored
-- ============================================================


-- ############################################################
-- WOOCOMMERCE
-- ############################################################


-- ============================================================
-- STAGING.WOOCOMMERCE_CATEGORIES
-- One row represents one product category
-- (two levels: main categories and their subcategories)
-- ============================================================

CREATE OR ALTER VIEW staging.woocommerce_categories AS
SELECT

    -- WooCommerce category ID
    category_id,

    -- Category name, HTML unescaped ("Küche &amp; Tisch" → "Küche & Tisch")
    TRIM(REPLACE(name, '&amp;', '&')) AS name,

    -- Part of the category URL
    slug,

    -- Parent category (NULL = main category; raw delivers 0)
    NULLIF(parent_id, 0) AS parent_id,

    -- Level in the category tree
    CASE WHEN parent_id = 0 THEN 'main' ELSE 'sub' END AS category_level

FROM raw.woocommerce_categories;
GO


-- ============================================================
-- STAGING.WOOCOMMERCE_PRODUCT_CATEGORIES
-- One row represents one assignment of a product to a category
-- (a product can belong to several categories)
-- ============================================================

CREATE OR ALTER VIEW staging.woocommerce_product_categories AS
SELECT

    product_id,
    category_id

FROM raw.woocommerce_product_categories;
GO


-- ============================================================
-- STAGING.WOOCOMMERCE_PRODUCTS
-- One row represents one WooCommerce product
-- ============================================================

CREATE OR ALTER VIEW staging.woocommerce_products AS
SELECT

    -- WooCommerce product ID
    product_id,

    -- Product information
    name,
    slug,                          -- part of the product URL, links to GA4 and Search Console
    type,
    status,
    NULLIF(sku, '')   AS sku,      -- '' → NULL (not every product has a SKU)
    NULLIF(brand, '') AS brand,    -- '' → NULL

    -- Pricing information (text → number, '' → NULL)
    CAST(NULLIF(price, '') AS DECIMAL(10,2))         AS price,           -- current price
    CAST(NULLIF(regular_price, '') AS DECIMAL(10,2)) AS regular_price,
    CAST(NULLIF(sale_price, '') AS DECIMAL(10,2))    AS sale_price,

    -- Inventory information
    stock_quantity,

    -- Product dates
    date_created,
    date_modified

FROM raw.woocommerce_products;
GO


-- ============================================================
-- STAGING.WOOCOMMERCE_ORDERS
-- One row represents one WooCommerce order,
-- including the billing data of the customer
-- ============================================================

CREATE OR ALTER VIEW staging.woocommerce_orders AS
SELECT

    -- WooCommerce order ID
    order_id,

    -- Order status and currency
    status,
    currency,

    -- Order dates
    date_created,
    date_modified,
    date_paid,
    date_completed,

    -- WooCommerce customer account ID (NULL = guest order; raw delivers 0)
    NULLIF(customer_id, 0) AS customer_id,

    -- Payment information
    payment_method,
    payment_method_title,

    -- Financial information (text → number, '' → NULL; total includes tax)
    CAST(NULLIF(discount_total, '') AS DECIMAL(10,2)) AS discount_total,
    CAST(NULLIF(shipping_total, '') AS DECIMAL(10,2)) AS shipping_total,
    CAST(NULLIF(total_tax, '') AS DECIMAL(10,2))      AS total_tax,
    CAST(NULLIF(total, '') AS DECIMAL(10,2))          AS total,

    -- Billing data ('' → NULL; e-mail in lower case, the mart derives customers from it)
    NULLIF(TRIM(billing_first_name), '')     AS billing_first_name,
    NULLIF(TRIM(billing_last_name), '')      AS billing_last_name,
    NULLIF(LOWER(TRIM(billing_email)), '')   AS billing_email,
    NULLIF(TRIM(billing_address_1), '')      AS billing_address_1,
    NULLIF(TRIM(billing_postcode), '')       AS billing_postcode,
    NULLIF(TRIM(billing_city), '')           AS billing_city,
    NULLIF(TRIM(billing_country), '')        AS billing_country

FROM raw.woocommerce_orders;
GO


-- ============================================================
-- STAGING.WOOCOMMERCE_ORDER_ITEMS
-- One row represents one product line of an order
-- ============================================================

CREATE OR ALTER VIEW staging.woocommerce_order_items AS
SELECT

    -- WooCommerce line item ID
    item_id,

    -- Order containing this item
    order_id,

    -- Product that was purchased (NULL = product was deleted; raw delivers 0)
    NULLIF(product_id, 0)   AS product_id,
    NULLIF(variation_id, 0) AS variation_id,   -- NULL = no variation

    -- Product information at the time of purchase
    name,
    NULLIF(sku, '') AS sku,

    -- Number of units purchased
    quantity,

    -- Financial information, net (text → number, '' → NULL)
    -- subtotal = before discount, total = after discount
    CAST(NULLIF(subtotal, '') AS DECIMAL(10,2))     AS subtotal,
    CAST(NULLIF(subtotal_tax, '') AS DECIMAL(10,2)) AS subtotal_tax,
    CAST(NULLIF(total, '') AS DECIMAL(10,2))        AS total,
    CAST(NULLIF(total_tax, '') AS DECIMAL(10,2))    AS total_tax,

    -- Net price per unit, full precision (up to 7 decimals as delivered)
    CAST(NULLIF(price, '') AS DECIMAL(18,8)) AS price

FROM raw.woocommerce_order_items;
GO




-- ############################################################
-- GOOGLE ANALYTICS 4
-- report_date: text YYYYMMDD → DATE (style 112).
-- "(not set)" is kept: GA4's label for "could not be measured",
-- not an empty value.
-- ############################################################


-- ============================================================
-- STAGING.GA4_DAILY_TRAFFIC
-- One row represents one day per channel, source, medium
-- and campaign
-- ============================================================

CREATE OR ALTER VIEW staging.ga4_daily_traffic AS
SELECT

    -- Day of the traffic
    CONVERT(date, report_date, 112) AS report_date,

    -- Traffic origin
    session_default_channel_group,
    session_source,
    session_medium,
    session_campaign_name,

    -- Traffic metrics
    sessions,
    total_users,
    new_users,
    engaged_sessions,
    screen_page_views

FROM raw.ga4_daily_traffic;
GO


-- ============================================================
-- STAGING.GA4_DAILY_EVENTS
-- One row represents one day per event name
-- ============================================================

CREATE OR ALTER VIEW staging.ga4_daily_events AS
SELECT

    -- Day of the events
    CONVERT(date, report_date, 112) AS report_date,

    -- GA4 event name and how often it happened
    event_name,
    event_count

FROM raw.ga4_daily_events;
GO


-- ============================================================
-- STAGING.GA4_LANDING_PAGES
-- One row represents one day per landing page
-- ============================================================

CREATE OR ALTER VIEW staging.ga4_landing_pages AS
SELECT

    -- Day of the sessions
    CONVERT(date, report_date, 112) AS report_date,

    -- First page of a session (path only)
    landing_page,

    -- Session metrics
    sessions,
    engaged_sessions

FROM raw.ga4_landing_pages;
GO


-- ============================================================
-- STAGING.GA4_PAGE_EVENTS
-- One row represents one day per page and event name
-- ============================================================

CREATE OR ALTER VIEW staging.ga4_page_events AS
SELECT

    -- Day of the events
    CONVERT(date, report_date, 112) AS report_date,

    -- Page on which the event happened (path only)
    page_path,

    -- GA4 event name and how often it happened
    event_name,
    event_count

FROM raw.ga4_page_events;
GO


-- ============================================================
-- STAGING.GA4_AUDIENCE
-- One row represents one day per device category and country
-- ============================================================

CREATE OR ALTER VIEW staging.ga4_audience AS
SELECT

    -- Day of the sessions
    CONVERT(date, report_date, 112) AS report_date,

    -- Visitor characteristics
    device_category,
    country,

    -- Audience metrics
    sessions,
    total_users,
    engaged_sessions

FROM raw.ga4_audience;
GO



-- ############################################################
-- GOOGLE SEARCH CONSOLE
-- ############################################################


-- ============================================================
-- STAGING.GSC_SEARCH_PERFORMANCE
-- One row represents one day per search query, page, country,
-- device and search type
--
-- Raw has no unique key: Google delivers some queries twice in
-- different Unicode forms, which Data Factory already normalized
-- to the same text. GROUP BY merges these rows (4 pairs as of
-- 2026-10-04), so this view has a unique key again.
-- ============================================================

CREATE OR ALTER VIEW staging.gsc_search_performance AS
SELECT

    -- Day of the searches (text YYYY-MM-DD → DATE, style 23)
    CONVERT(date, g.report_date, 23) AS report_date,

    -- What was searched and which page was shown
    g.query,
    g.page,                        -- full URL as delivered
    p.page_path,                   -- path only, comparable to GA4 paths

    -- Who searched
    g.country,
    g.device,
    g.search_type,

    -- Search metrics, merged
    SUM(g.clicks)      AS clicks,
    SUM(g.impressions) AS impressions,

    -- CTR recalculated from the sums (CTRs cannot be added up)
    CAST(SUM(g.clicks) AS FLOAT) / NULLIF(SUM(g.impressions), 0) AS ctr,

    -- Average position weighted by impressions (as Google calculates it)
    SUM(g.position * g.impressions) / NULLIF(SUM(g.impressions), 0) AS position

FROM raw.gsc_search_performance AS g

    -- URL → path: remove the domain (https://luandla.de/... → /...)
    CROSS APPLY (SELECT SUBSTRING(g.page, CHARINDEX('/', g.page, 9), 500) AS path_and_query) AS a

    -- Cut off the query string (?orderby=... sorts the same page)
    CROSS APPLY (SELECT CASE WHEN CHARINDEX('?', a.path_and_query) > 0
                             THEN LEFT(a.path_and_query, CHARINDEX('?', a.path_and_query) - 1)
                             ELSE a.path_and_query
                        END AS path) AS b

    -- Remove the trailing slash like GA4 (the home page stays /)
    CROSS APPLY (SELECT CASE WHEN LEN(b.path) > 1 AND RIGHT(b.path, 1) = '/'
                             THEN LEFT(b.path, LEN(b.path) - 1)
                             ELSE b.path
                        END AS page_path) AS p

GROUP BY
    g.report_date,
    g.query,
    g.page,
    p.page_path,
    g.country,
    g.device,
    g.search_type;
GO
