# Project Log

Daily documentation of the work on the cloud e-commerce analytics pipeline
(WooCommerce + GA4 + Search Console → Azure SQL → dbt → Power BI).

**How to use:** add a new entry at the top for every working day. Copy the template below
and fill in only the sections that apply. Keep it short: what was done, what was decided
and why, what went wrong and how it was solved.

---

<!--
## YYYY-MM-DD – Short title

**Done**
-

**Decisions**
- Decision – reason

**Problems & solutions**
- Problem → solution

**Open / next steps**
- [ ]
-->

## 2026-09-25 – Raw layer for all three data sources

**Done**
- Connected Python to Azure SQL: replaced `pyodbc` with `mssql-python`, which brings its own SQL Server driver.
- Loaded the first WooCommerce tables (customers, categories, products, orders, order items) into `dbo`.
- Connected the **GA4 Data API** and the **Search Console API** with a Google Cloud service account
  (GA4 property `518947113`, Search Console property `https://luandla.de/`).
- Designed a GA4 star schema and a Search Console fact table, then moved them to the planned dbt mart layer.
- Created the layered database structure: schemas `raw`, `staging`, `mart`
  (`sql/00_drop_old_tables.sql`, `sql/01_create_schemas.sql`, `sql/02_create_raw_tables.sql`).
- Created 11 raw tables and rewrote the six load scripts in `data/` for them.
- Loaded all raw tables: 17 orders, 29 order items, 55 products, 29 categories, 142 product-category links,
  GA4 reports (344–4,420 rows each), 19,997 Search Console rows.
- Installed the Azure CLI; the load scripts now log in with `az login` instead of a browser window.
- Created `docs/table_design.md`.

**Decisions**
- **Layers as schemas** (`raw.…`, `staging.…`, `mart.…`) instead of name prefixes – standard in dbt, clearer in the database explorer.
- **Raw stores data as delivered** – cleaning (HTML entities, `product_id = 0`, customer deduplication,
  admin-page filter, country codes) happens in dbt staging, so raw always shows what the source sent.
- **Customers are derived from order billing data** – 14 of 17 orders are guest orders without a customer account.
- **GA4 via Data API** (aggregated daily reports) instead of the BigQuery export – available now with history since January 2026;
  the BigQuery export would only collect data from the day it is enabled.
- **`dim_date` and all `dim_`/`fact_` tables belong to the mart** and will be built with dbt.
- **Load scripts do a full refresh** (delete + insert in one transaction) – safe to rerun at any time.
- **Started the database fresh** instead of migrating the old `dbo` tables – all data can be reloaded from the APIs.
- **All keys stay `BIGINT`** – consistent with the source systems.
- **Database auto-pause set to 15 minutes** (was 60) to save student credit.

**Problems & solutions**
- `ODBC Driver 18 for SQL Server` not found; Homebrew does not support Intel Macs → switched to `mssql-python`.
- `mssql-python` could not find OpenSSL → linked Anaconda's OpenSSL into `/usr/local/opt/openssl/lib`.
- `ModuleNotFoundError: mssql_python` → the script ran in a different Python environment; installed the package in `python_course`.
- Live `customers` table had only 4 columns → added the missing columns; later replaced by the raw design.
- Foreign-key error when loading order items → orders and products must be loaded first (no longer relevant in raw).
- GA4 purchases have no transaction ID or revenue, and no `view_item` events are tracked → GA4 cannot be joined to single orders.
- Search Console load failed (`Unable to cast … float`) → the API mixes whole numbers and decimals; values are now always converted to `float`.
- Azure SQL free offer cannot be applied to an existing paid database → kept the paid database with 15-minute auto-pause.

**Open / next steps**
- [ ] Rewrite `docs/table_design.md` for the raw layer
- [ ] Move WooCommerce API keys into a `.env` file, then `git init` and first commit
- [ ] Add `timeout=` to the WooCommerce API requests
- [ ] Set up dbt: staging models, then mart (`dim_date`, dimensions, facts)
- [ ] Later: Terraform for the Azure resources, Azure Functions for daily loads
