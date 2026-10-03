-- ============================================================
-- RAW TABLES
-- Data as it comes from the sources, loaded by the Python scripts.
--
-- Rules for the raw layer:
--   * table name = <source>_<object>
--   * column names follow the source fields
--   * values are stored as delivered (no cleaning, no filtering)
--   * no surrogate keys and no foreign keys (these belong to the mart)
--   * the source ID is the primary key where one exists
--   * loaded_at records when a row was loaded
-- ============================================================


-- ############################################################
-- WOOCOMMERCE
-- ############################################################


-- ============================================================
-- RAW.WOOCOMMERCE_ORDERS
-- One row represents one WooCommerce order,
-- including the billing data of the customer
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.woocommerce_orders', 'U') IS NULL
BEGIN

    CREATE TABLE raw.woocommerce_orders (

        -- WooCommerce order ID
        order_id BIGINT PRIMARY KEY,

        -- Order status, e.g. completed, processing, cancelled
        status NVARCHAR(50),
        currency NVARCHAR(10),

        -- Order dates
        date_created DATETIME2,
        date_modified DATETIME2,
        date_paid DATETIME2,
        date_completed DATETIME2,

        -- WooCommerce customer account ID (0 = guest order)
        customer_id BIGINT,

        -- Payment information
        payment_method NVARCHAR(100),
        payment_method_title NVARCHAR(255),

        -- Financial information (text as delivered by the API, converted in staging)
        discount_total NVARCHAR(20),
        shipping_total NVARCHAR(20),
        total_tax NVARCHAR(20),
        total NVARCHAR(20),

        -- Billing data (customers are derived from it in staging)
        billing_first_name NVARCHAR(100),
        billing_last_name NVARCHAR(100),
        billing_email NVARCHAR(255),
        billing_address_1 NVARCHAR(255),
        billing_postcode NVARCHAR(20),
        billing_city NVARCHAR(100),
        billing_country NVARCHAR(10),

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()

    );

END;


-- ============================================================
-- RAW.WOOCOMMERCE_ORDER_ITEMS
-- One row represents one product line of an order
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.woocommerce_order_items', 'U') IS NULL
BEGIN

    CREATE TABLE raw.woocommerce_order_items (

        -- WooCommerce line item ID
        item_id BIGINT PRIMARY KEY,

        -- Order containing this item
        order_id BIGINT NOT NULL,

        -- Product that was purchased (0 = product was deleted)
        product_id BIGINT,
        variation_id BIGINT,

        -- Product information at the time of purchase
        name NVARCHAR(255),
        sku NVARCHAR(100),

        -- Number of units purchased
        quantity INT,

        -- Financial information (text as delivered by the API, converted in staging)
        subtotal NVARCHAR(20),
        subtotal_tax NVARCHAR(20),
        total NVARCHAR(20),
        total_tax NVARCHAR(20),

        -- Net price per unit, with full precision as delivered (text, converted in staging)
        price NVARCHAR(20),

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()

    );

END;


-- ============================================================
-- RAW.WOOCOMMERCE_PRODUCTS
-- One row represents one WooCommerce product
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.woocommerce_products', 'U') IS NULL
BEGIN

    CREATE TABLE raw.woocommerce_products (

        -- WooCommerce product ID
        product_id BIGINT PRIMARY KEY,

        -- Product information
        name NVARCHAR(255),
        slug NVARCHAR(255),            -- part of the product URL, links to GA4 and Search Console
        type NVARCHAR(50),             -- simple, variable, ...
        status NVARCHAR(50),           -- publish, draft, ...
        sku NVARCHAR(100),
        brand NVARCHAR(100),

        -- Pricing information (text as delivered by the API, converted in staging)
        price NVARCHAR(20),            -- current price
        regular_price NVARCHAR(20),
        sale_price NVARCHAR(20),

        -- Inventory information
        stock_quantity INT,

        -- Product dates
        date_created DATETIME2,
        date_modified DATETIME2,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()

    );

END;


-- ============================================================
-- RAW.WOOCOMMERCE_CATEGORIES
-- One row represents one product category
-- (main categories and subcategories in one table)
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.woocommerce_categories', 'U') IS NULL
BEGIN

    CREATE TABLE raw.woocommerce_categories (

        -- WooCommerce category ID
        category_id BIGINT PRIMARY KEY,

        -- Category information (name as delivered, e.g. "Küche &amp; Tisch")
        name NVARCHAR(255),
        slug NVARCHAR(255),

        -- Parent category (0 = main category)
        parent_id BIGINT,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()

    );

END;


-- ============================================================
-- RAW.WOOCOMMERCE_PRODUCT_CATEGORIES
-- One row represents one assignment of a product to a category
-- (a product can belong to several categories)
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.woocommerce_product_categories', 'U') IS NULL
BEGIN

    CREATE TABLE raw.woocommerce_product_categories (

        product_id BIGINT NOT NULL,
        category_id BIGINT NOT NULL,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        -- Every assignment may exist only once
        CONSTRAINT PK_woocommerce_product_categories
            PRIMARY KEY (product_id, category_id)

    );

END;


-- ############################################################
-- GOOGLE ANALYTICS 4 (Data API, aggregated reports)
-- Text dimensions contain "(not set)" instead of empty values.
-- ############################################################


-- ============================================================
-- RAW.GA4_DAILY_TRAFFIC
-- One row represents one day per channel, source, medium
-- and campaign
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.ga4_daily_traffic', 'U') IS NULL
BEGIN

    CREATE TABLE raw.ga4_daily_traffic (

        -- Day of the traffic (text as delivered, e.g. 20260315, converted in staging)
        report_date NVARCHAR(8) NOT NULL,

        -- Traffic origin (GA4 dimensions)
        session_default_channel_group NVARCHAR(100) NOT NULL,
        session_source NVARCHAR(100) NOT NULL,
        session_medium NVARCHAR(100) NOT NULL,
        session_campaign_name NVARCHAR(100) NOT NULL,

        -- Traffic metrics (GA4 metrics)
        sessions INT,
        total_users INT,
        new_users INT,
        engaged_sessions INT,
        screen_page_views INT,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        -- One row per day, channel, source, medium and campaign
        CONSTRAINT PK_ga4_daily_traffic
            PRIMARY KEY (report_date, session_default_channel_group,
                         session_source, session_medium, session_campaign_name)

    );

END;


-- ============================================================
-- RAW.GA4_DAILY_EVENTS
-- One row represents one day per event name
-- (e.g. page_view, add_to_cart, begin_checkout, purchase)
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.ga4_daily_events', 'U') IS NULL
BEGIN

    CREATE TABLE raw.ga4_daily_events (

        -- Day of the events (text as delivered, e.g. 20260315, converted in staging)
        report_date NVARCHAR(8) NOT NULL,

        -- GA4 event name
        event_name NVARCHAR(100) NOT NULL,

        -- How often the event happened
        event_count INT,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        -- One row per day and event
        CONSTRAINT PK_ga4_daily_events
            PRIMARY KEY (report_date, event_name)

    );

END;


-- ============================================================
-- RAW.GA4_LANDING_PAGES
-- One row represents one day per landing page
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.ga4_landing_pages', 'U') IS NULL
BEGIN

    CREATE TABLE raw.ga4_landing_pages (

        -- Day of the sessions (text as delivered, e.g. 20260315, converted in staging)
        report_date NVARCHAR(8) NOT NULL,

        -- First page of a session (path only, e.g. /japanischer-donabe-topf-...)
        landing_page NVARCHAR(400) NOT NULL,

        -- Session metrics
        sessions INT,
        engaged_sessions INT,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        -- One row per day and landing page
        CONSTRAINT PK_ga4_landing_pages
            PRIMARY KEY (report_date, landing_page)

    );

END;


-- ============================================================
-- RAW.GA4_PAGE_EVENTS
-- One row represents one day per page and event name
-- (e.g. page views and add-to-cart clicks per product page)
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.ga4_page_events', 'U') IS NULL
BEGIN

    CREATE TABLE raw.ga4_page_events (

        -- Day of the events (text as delivered, e.g. 20260315, converted in staging)
        report_date NVARCHAR(8) NOT NULL,

        -- Page on which the event happened (path only)
        page_path NVARCHAR(300) NOT NULL,

        -- GA4 event name
        event_name NVARCHAR(100) NOT NULL,

        -- How often the event happened
        event_count INT,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        -- One row per day, page and event
        CONSTRAINT PK_ga4_page_events
            PRIMARY KEY (report_date, page_path, event_name)

    );

END;


-- ============================================================
-- RAW.GA4_AUDIENCE
-- One row represents one day per device category and country
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.ga4_audience', 'U') IS NULL
BEGIN

    CREATE TABLE raw.ga4_audience (

        -- Day of the sessions (text as delivered, e.g. 20260315, converted in staging)
        report_date NVARCHAR(8) NOT NULL,

        -- Visitor characteristics
        device_category NVARCHAR(50) NOT NULL,     -- desktop, mobile, tablet
        country NVARCHAR(100) NOT NULL,            -- country name, e.g. Germany

        -- Audience metrics
        sessions INT,
        total_users INT,
        engaged_sessions INT,

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        -- One row per day, device and country
        CONSTRAINT PK_ga4_audience
            PRIMARY KEY (report_date, device_category, country)

    );

END;


-- ############################################################
-- GOOGLE SEARCH CONSOLE
-- ############################################################


-- ============================================================
-- RAW.GSC_SEARCH_PERFORMANCE
-- One row represents one day per search query, page, country,
-- device and search type
-- ============================================================

-- Create the table only if it does not already exist
IF OBJECT_ID('raw.gsc_search_performance', 'U') IS NULL
BEGIN

    CREATE TABLE raw.gsc_search_performance (

        -- Day of the searches (text as delivered, e.g. 2026-03-15, converted in staging)
        report_date NVARCHAR(10) NOT NULL,

        -- What was searched and which page was shown
        query NVARCHAR(300) NOT NULL,
        page NVARCHAR(500) NOT NULL,           -- full URL as delivered, e.g. https://luandla.de/...

        -- Who searched
        country NVARCHAR(3) NOT NULL,          -- ISO 3166-1 alpha-3 in lower case, e.g. deu
        device NVARCHAR(20) NOT NULL,          -- DESKTOP, MOBILE, TABLET

        -- Google search type, e.g. web, image, video
        search_type NVARCHAR(20) NOT NULL,

        -- Search metrics, as delivered by the API
        clicks INT,
        impressions INT,
        ctr FLOAT,                             -- clicks / impressions
        position FLOAT,                        -- average position, 1 = top

        -- When the row was loaded
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()

        -- No unique key: Google delivers some queries twice in different Unicode
        -- forms (e.g. "é" as one character and as "e" + accent). Data Factory
        -- normalizes them to the same text, so they would collide.
        -- Staging normalizes the queries and merges these rows.

    );

END;


-- ============================================================
-- CHECK
-- All raw tables with their number of columns
-- ============================================================

SELECT
    t.name AS table_name,
    COUNT(c.column_id) AS number_of_columns
FROM sys.tables AS t
JOIN sys.columns AS c
    ON c.object_id = t.object_id
WHERE SCHEMA_NAME(t.schema_id) = 'raw'
GROUP BY t.name
ORDER BY t.name;
