# Table Design

Database design of the Azure SQL Database `ecommerce-analytics-db`
(server `ecommerce-analytics-sql-2026.database.windows.net`).

How the data gets into the `raw` schema is described in [`pipeline_guide.md`](pipeline_guide.md);
decisions and their reasons are recorded in [`project_log.md`](project_log.md).

---

## 1. Purpose

The database brings sales, website traffic and Google search together in one model for Power BI.
It should answer questions like these (from the README):

- Which products and categories sell?
- Through which channels do visitors come to the shop?
- Which search terms bring the shop up in Google?

The detailed questions, and the facts and dimensions that answer them, are defined with the mart (section 5).

---

## 2. Layers

The database has three layers, one schema each:

```
raw (tables)  ──►  staging (views)  ──►  mart (tables)  ──►  Power BI
 as delivered       cleaned               dimensions + facts
```

| | **raw** | **staging** | **mart** |
|---|---|---|---|
| **Purpose** | Source data as delivered | Cleaned source data | Model for Power BI (dimensions and facts) |
| **One object per** | source object | raw table (1:1) | business object or process |
| **Naming** | `raw.<source>_<object>` | `staging.<source>_<object>` | `mart.dim_<name>`, `mart.fact_<name>` |
| **Built as** | tables | views | tables |
| **Filled by** | Data Factory Copy activities (full refresh) | – (a view is calculated when it is read) | stored procedures (full refresh), started by Data Factory |
| **Keys** | source ID where one exists | source ID | source ID where one exists, otherwise surrogate keys; dates as `date_key` (INT, `YYYYMMDD`) |
| **Foreign keys** | none | none | yes |
| **SQL file** | `sql/02_create_raw_tables.sql` | `sql/03_create_staging_views.sql` | `sql/04_create_mart_tables.sql`, `sql/05_create_mart_procedures.sql` |

**Load flow:** Python → Data Lake → Data Factory Copy (`raw`) → Data Factory runs the mart procedures
(reading `staging`) → Power BI reads `mart`.

### What happens where

| Layer | Allowed | Not allowed |
|---|---|---|
| **raw** | loading only | any cleaning |
| **staging** | **technical transformations:** convert types (text → number/date), `''` → `NULL`, trim, HTML unescape (`&amp;` → `&`), `product_id = 0` → `NULL`, merge technical duplicates, URL → path, rename columns | joins between sources, business rules |
| **mart** | **business transformations:** derive customers from billing data, map country codes, choose a main category, join sources, surrogate keys, foreign keys | – |

**Test for the boundary:** would two people interpret the rule the same way?
`'19.90'` → `19.90` has only one sensible result → staging.
"Two orders with the same e-mail address belong to the same customer" is a decision → mart.

### Why staging is a view and the mart a table

- **Staging as views** – a thin 1:1 cleaning layer: no extra load step, always current, easy to change while the rules
  are still evolving, fast enough at ≤ ~20k rows per table.
- **Mart as tables** – Power BI reads it, so it should be stable; foreign keys check the model.
- This is the common pattern in SQL warehouses (e.g. dbt's default). Staging can be turned into tables later without
  changing the mart.

---

## 3. Raw layer

11 tables, defined in [`sql/02_create_raw_tables.sql`](../sql/02_create_raw_tables.sql).

Rules: column names follow the source fields; values are stored as delivered (amounts and GA4/GSC dates as text);
no surrogate or foreign keys; `loaded_at` records when a row was loaded.

| Table | Grain (one row = …) | Key | Lake file (container `raw`) | Pipeline |
|---|---|---|---|---|
| `woocommerce_orders` | one order (incl. billing data) | `order_id` | `woocommerce/orders/` | `pl_copy_woocommerce_to_raw` |
| `woocommerce_order_items` | one product line of an order | `item_id` | `woocommerce/orders/` (`line_items`) | `pl_copy_woocommerce_to_raw` |
| `woocommerce_products` | one product | `product_id` | `woocommerce/products/` | `pl_copy_woocommerce_to_raw` |
| `woocommerce_categories` | one category (main and subcategories) | `category_id` | `woocommerce/categories/` | `pl_copy_woocommerce_to_raw` |
| `woocommerce_product_categories` | one product × category assignment | `product_id, category_id` | `woocommerce/products/` (`categories`) | `pl_copy_woocommerce_to_raw` |
| `ga4_daily_traffic` | day × channel × source × medium × campaign | all five columns | `ga4/daily_traffic/` | `pl_copy_ga4_to_raw` |
| `ga4_daily_events` | day × event name | `report_date, event_name` | `ga4/daily_events/` | `pl_copy_ga4_to_raw` |
| `ga4_landing_pages` | day × landing page | `report_date, landing_page` | `ga4/landing_pages/` | `pl_copy_ga4_to_raw` |
| `ga4_page_events` | day × page × event name | `report_date, page_path, event_name` | `ga4/page_events/` | `pl_copy_ga4_to_raw` |
| `ga4_audience` | day × device category × country | `report_date, device_category, country` | `ga4/audience/` | `pl_copy_ga4_to_raw` |
| `gsc_search_performance` | day × query × page × country × device × search type | none (see below) | `gsc/search_performance/` | `pl_copy_gsc_to_raw` |

Special cases:

- **Stored as text, converted in staging:** WooCommerce prices and amounts (`''` for empty values), GA4 `report_date`
  (`20260315`), GSC `report_date` (`2026-03-15`).
- **`gsc_search_performance` has no unique key** – Google delivers some queries in two Unicode forms (`é` as one
  character and as `e` + combining accent), which Data Factory normalizes to the same text. Staging merges these rows
  (section 4).
- **GA4 data is aggregated** (Data API daily reports) – there are no single users, sessions or events.

---

## 4. Staging layer

11 views, defined in [`sql/03_create_staging_views.sql`](../sql/03_create_staging_views.sql), all built and checked
on 2026-10-04.

Rules: one view per raw table with the same name in schema `staging`; column names stay as in raw (plus one new
column, `gsc_search_performance.page_path`); `loaded_at` is dropped; views are created with `CREATE OR ALTER VIEW`, so
the file can be run again at any time.

### Cleaning per view

| View | Rows | Cleaning |
|---|---|---|
| `woocommerce_categories` | 29 | `name`: `&amp;` → `&` (the only HTML entity found) and trimmed · `parent_id`: `0` → `NULL` (= main category) · new `category_level`: `main` / `sub` |
| `woocommerce_product_categories` | 142 | none (pass-through, so the mart reads only from staging) |
| `woocommerce_products` | 55 | `price`, `regular_price`, `sale_price`: text → `DECIMAL(10,2)`, `''` → `NULL` · `sku`, `brand`: `''` → `NULL` |
| `woocommerce_orders` | 17 | `customer_id`: `0` → `NULL` (= guest order) · amounts: text → `DECIMAL(10,2)` · billing fields: trimmed, `''` → `NULL` · `billing_email` in lower case |
| `woocommerce_order_items` | 29 | `product_id`: `0` → `NULL` (= product deleted) · `variation_id`: `0` → `NULL` (= no variation) · `sku`: `''` → `NULL` · amounts: text → `DECIMAL(10,2)` · `price`: text → `DECIMAL(18,8)` (up to 7 decimals as delivered) |
| `ga4_daily_traffic` | 353 | `report_date`: text `YYYYMMDD` → `DATE` |
| `ga4_daily_events` | 1,336 | `report_date` → `DATE` |
| `ga4_landing_pages` | 759 | `report_date` → `DATE` |
| `ga4_page_events` | 4,591 | `report_date` → `DATE` |
| `ga4_audience` | 456 | `report_date` → `DATE` |
| `gsc_search_performance` | 20,358 (raw 20,362) | `report_date`: text `YYYY-MM-DD` → `DATE` · Unicode duplicates merged (see below) · new `page_path` (see below) |

Row counts as of 2026-10-04; every view has the same number of rows as its raw table, except
`gsc_search_performance`.

### Decisions

- **Empty values:** `''` → `NULL` and `0` as "no ID" → `NULL`, so a missing value is always `NULL` (shown as
  "(Blank)" in Power BI).
- **Amounts are cast with `CAST`, not `TRY_CAST`** – an unexpected value (e.g. `12,50`) stops the view with an error
  instead of silently becoming `NULL`.
- **Values are not rounded** (`ctr`, `position`, `price`) – the mart aggregates them again; rounding is formatting
  and belongs in Power BI.
- **GA4 `(not set)` is kept** – it is GA4's label for "could not be measured", not an empty value; `NULL` would also
  break joins and grouping in the mart. `(direct)` / `(none)` are real values anyway.
- **`gsc_search_performance` – merging duplicates:** `GROUP BY` over all six dimensions (date, query, page, country,
  device, search type) merges the 4 Unicode pairs; the view has a unique key again.
  - `clicks`, `impressions`: `SUM`
  - `ctr`: recalculated as `SUM(clicks) / SUM(impressions)` – CTRs cannot be added or averaged
  - `position`: weighted by impressions, `SUM(position × impressions) / SUM(impressions)` – the average position over
    all impressions, as Google calculates it
  - For a group of one row (all rows except the 4 pairs) the formulas return Google's values unchanged.
- **`gsc_search_performance.page_path`:** `page` (full URL, kept) → path in the same format as GA4: domain removed
  (all URLs start with `https://luandla.de/`), query string cut off (117 rows with `?orderby=…`, WooCommerce's sort
  parameter), trailing `/` removed (the home page stays `/`).

---

## 5. Mart layer

*To be designed: business questions, dimensions and facts with grain, keys and relationships.*

### Notes collected so far

**`dim_category`** (from `staging.woocommerce_categories`, checked 2026-10-04):

- The category tree has exactly **two levels** – every subcategory's parent is a main category, so one step up through
  `parent_id` always reaches the main category.
- Flatten the tree into `main_category` / `subcategory` with a self-join on `parent_id` (for a drill-down in Power BI).
- Products are assigned inconsistently: some only to subcategories, some to main and subcategories, many to several
  trees at once.
- Not every main category is a product type: **Geschenke** (gift ideas), **Neuheiten** (new arrivals) and
  **Uncategorized** (WooCommerce default) are labels. Choosing a product's main category should skip them.

**`dim_customer`** (from `staging.woocommerce_orders`, checked 2026-10-04):

- 14 of 17 orders are guest orders (`customer_id` is `NULL` in staging), so `customer_id` cannot be the customer key.
- **One rule for everyone: customer = normalized e-mail** (`billing_email`, lower case and trimmed in staging; never
  empty as of 2026-10-04). Using `customer_id` with an e-mail fallback would count a guest who later opens an account
  as two customers.
- **Key = hash of the e-mail** (`HASHBYTES('SHA2_256', billing_email)`) – stable across full refreshes (unlike
  `ROW_NUMBER()`/`IDENTITY`) and pseudonymized, so no e-mail address reaches Power BI or GitHub.
- `customer_id` stays as an attribute (has an account: yes/no).

---

## 6. How the sources connect

*To be designed: e.g. product slug ↔ GA4 landing page ↔ GSC page, dates through `dim_date`.*

### Notes collected so far

**GA4 page paths** (`staging.ga4_landing_pages`, checked 2026-10-04): paths are clean – no query strings, no trailing
slash except the home page `/`.

- **Product pages** are `/lifestyle-geschenke-shop/<slug>` – the last part of the path is the WooCommerce `slug`, which
  links GA4 to products.
- **Translated pages** (`/en/…`, `/es/tienda-de-regalos-de-estilo-de-vida/…`) have translated slugs that do not match
  the German `slug`; they need their own mapping or stay unlinked.
- **`/wp-login.php`** (69 sessions) is admin and bot traffic – filter it out in the mart (dropping rows is a business
  rule, not staging).
- Other page types: home page `/`, `/shop`, brand pages `/brand/<brand>`, blog articles (e.g.
  `/reis-wie-in-japan-…`), legal pages (`/impressum`).
- **`(not set)`** (GA4's label for "could not be measured", e.g. a session that started without a page view) is kept
  as a value: 51 landing-page rows, a few sources, mediums and campaigns, 1 country.

**GSC ↔ GA4** (checked 2026-10-04): `staging.gsc_search_performance.page_path` matches
`staging.ga4_landing_pages.landing_page` – for German and translated pages, because both sources use the same
translated paths. Only the link to WooCommerce products (German `slug`) is limited to German pages.
The pages with the most search rows are blog articles (`/reis-wie-in-japan-…`, `/japanischer-donabe-topf-…`), ahead of
product pages.

---

## 7. Known limitations

- **GA4 is aggregated** – the Data API returns daily totals, so GA4 cannot be joined to single orders or customers.
- **GA4 purchases have no transaction ID or revenue** – revenue comes from WooCommerce.
- **GA4 counts fewer purchases than WooCommerce** (10 vs. 17 as of 2026-09-25), because visitors who decline cookies
  or use ad blockers are not tracked.
- **No `view_item` events** are tracked, so product-level events start with `add_to_cart`.
- **Search Console hides rare search queries** for privacy – rows grouped by query add up to fewer clicks and
  impressions than the site totals in Search Console.
- **Search Console delivers some queries twice in different Unicode forms** (see section 3).
- **Country codes differ between sources** – Search Console `deu`, WooCommerce `DE`, GA4 `Germany`; comparing countries
  needs a mapping.
- **Customers have no ID of their own** – 14 of 17 orders are guest orders; customers are derived from the billing data.
- **No purchase price** – WooCommerce stores no cost price, so margins cannot be calculated yet; planned: a CSV with
  purchase prices per `product_id` as an additional raw source.
- **Some products have no SKU** (14 products with an empty SKU or brand) – not needed for the analysis, the key is
  `product_id`.
