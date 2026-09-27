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

## 2026-09-27 – Transformation tool: Azure Data Factory instead of dbt

**Decisions**
- **Azure Data Factory for the transformations** (`raw` → `staging` → `mart`) instead of dbt – this is a cloud portfolio
  project (IU Cloud Programming), so it should show Azure services and cloud concepts; dbt is not an Azure service.
  This also follows the architecture concept (`docs/architecture.png`).
- **Cost is acceptable because Data Factory is only used short-term** – the expensive part are Data Flows
  (Spark cluster, roughly €10–15/month when run daily); copy activities and orchestration cost about €1–3/month.
- Alternatives considered: dbt Core (free, SQL in git, built-in tests) – rejected because it runs outside Azure
  and would not demonstrate the cloud services of the concept.
- **Separate storage account for the Data Lake** (`stecommercelake26`) – the existing account `rgecommerceanalyticb0b6`
  belongs to the Function App (internal files, no hierarchical namespace) and stays untouched.
- **Data Lake settings:** hierarchical namespace on (ADLS Gen2), Standard performance, LRS redundancy (cheapest),
  access tier Hot, region Germany West Central (same as the database).
- **Anonymous access disabled; access only through Microsoft Entra ID (role-based)** – the lake stores order data
  with customer names, e-mail and billing addresses (personal data under GDPR), and no part of the pipeline needs
  public access: scripts, Data Factory and Power BI sign in with an Azure identity.
- **WooCommerce data is loaded every 2 weeks, not daily** – the shop has few changes (17 orders so far; categories
  and products rarely change), so fewer runs are enough and save cost. Only the schedule (trigger) is affected;
  the extract scripts stay the same. The schedule for GA4 and Search Console is decided later
  (Search Console keeps only 16 months of data).
- **Categories are still extracted from their own API endpoint** – the products API lists a product's categories
  without `parent`, so the main/subcategory hierarchy (needed for drill-down in Power BI) only comes from the
  categories endpoint; also 6 of 29 categories have no products and would be missing.
- **Only the needed fields are requested from the API (`_fields`)** – e.g. categories: `id,name,slug,parent`.
  Descriptions, images and SEO data (Yoast) are not needed (file size 346 KB → 3 KB). Raw now means
  "requested fields, unchanged" – data minimization, which matters most later for orders (personal data).
- **Storage account keys disabled, Entra ID as default in the portal** – no shared master keys that give full access
  without a person attached; every access goes through a role assignment (e.g. *Storage Blob Data Contributor*).

**Open / next steps**
- [x] Create the Data Lake storage account `stecommercelake26` (settings verified with Azure CLI)
- [x] Create the `raw` container
- [x] Create Data Factory `adf-ecommerce-analytics-26` (Germany West Central, V2, Git configured later, no managed VNet, public endpoint)
- [x] Set a budget alert `budget-ecommerce-analytics` (€10/month on `rg-ecommerce-analytics`; e-mail at 80 % and 100 % actual cost and at 100 % forecasted cost)
- [x] Give the Data Factory managed identity the role *Storage Blob Data Contributor* on the Data Lake (no keys)
- [x] Give the Data Factory managed identity access to the SQL database (Entra user `FROM EXTERNAL PROVIDER`,
      roles `db_datareader`, `db_datawriter`, `db_ddladmin`)
- [x] `extract_categories.py` saves the unchanged API response as JSON to the Data Lake
      (`raw/woocommerce/categories/categories_YYYY-MM-DD.json`, login via `DefaultAzureCredential`); SQL load kept until the pipeline works
- [x] Assign myself the role *Storage Blob Data Contributor* on the Data Lake (needed to write files with `az login`)
- [ ] Set cost rules when Data Factory is created: turn off Data Flow debug after use, no daily trigger while building,
      budget alert in Azure Cost Management, delete Data Factory after grading
- [x] Update README (`dbt/` replaced by Azure Data Factory)
- [x] Data Lake and Data Factory are created by hand in the Azure portal first (Terraform later)

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
