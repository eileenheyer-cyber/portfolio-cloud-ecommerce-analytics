# Pipeline Guide

How the data gets from WooCommerce, GA4 and Google Search Console into Azure SQL (`raw` schema),
step by step.

## Overview

```
WooCommerce API ─┐
GA4 Data API ────┼─► Python (extract_*.py) ─► Azure Data Lake (JSON) ─► Data Factory ─► Azure SQL (raw)
GSC API ─────────┘
```

**Python extracts, the lake stores, Data Factory loads.** Each tool has one job.

---

## Step 1: One-time setup in Azure

| Resource | Name | Purpose |
|---|---|---|
| Azure SQL Database (serverless) | `ecommerce-analytics-db` | Target, with schemas `raw`, `staging`, `mart` |
| Storage account (ADLS Gen2) | `stecommercelake26`, container `raw` | Landing zone for the JSON files |
| Data Factory | `adf-ecommerce-analytics-26` | Loads the files into SQL |

**Security:** no passwords, no storage keys.
- Locally, the scripts use the Azure CLI login (`az login`) via `DefaultAzureCredential`.
- Data Factory uses its **managed identity**, an Azure identity that belongs to the service itself:
  - role *Storage Blob Data Contributor* on the lake
  - database user `FROM EXTERNAL PROVIDER` with `db_datareader`, `db_datawriter`, `db_ddladmin`
- SQL firewall: "Allow Azure services and resources to access this server", because Data Factory has no fixed IP.

## Step 2: Create the raw tables

`sql/01_create_schemas.sql` → `sql/02_create_raw_tables.sql`: 11 tables, named `<source>_<object>`,
storing values **as delivered** (e.g. prices and dates as text, converted in staging).

## Step 3: API access

| Source | Access | Where it's stored |
|---|---|---|
| WooCommerce | Consumer key + secret (REST API) | `.env` (not in Git) |
| GA4 | Google Cloud service account, added as a user on the GA4 property `518947113` | path to the key file in `.env` |
| Search Console | **Same** service account, added as a user on the property `https://luandla.de/` | same |

## Step 4: Python extracts and writes to the lake

Every script follows the same pattern: **call the API page by page → build JSON → upload it to the lake.**

| Script | What it fetches | Lake path (container `raw`) |
|---|---|---|
| `extract_categories.py` | Categories (`_fields`: only the needed fields) | `woocommerce/categories/categories_<date>.json` |
| `extract_products.py` | Products incl. categories and brand | `woocommerce/products/products_<date>.json` |
| `extract_orders.py` | Orders incl. billing data and `line_items` | `woocommerce/orders/orders_<date>.json` |
| `extract_ga4.py` | 5 daily reports (traffic, events, landing pages, page events, audience) | `ga4/<report>/<report>_<date>.json` |
| `extract_gsc.py` | Search performance (date × query × page × country × device × search type) | `gsc/search_performance/search_performance_<date>.json` |

- **WooCommerce:** the API response is saved **unchanged**; renaming happens in the Data Factory mapping.
- **GA4 / GSC:** Python builds rows with the **raw column names** and cuts long texts to the column length
  (Data Factory does not cut them and would fail).
- The file name contains the **load date**; a second run on the same day overwrites that day's file.

## Step 5: Data Factory building blocks

**Linked services** (connections, both via managed identity):
- `ls_adls_datalake` → Data Lake
- `ls_azure_sql` → database

**Generic datasets** (one each, reused everywhere):
- `ds_json_lake` – parameters `folder_path`, `file_name`
- `ds_sql_table` – parameters `schema_name`, `table_name`
- No stored schema, so they work for every file and table. If *Schemas importieren* ever saves a schema on
  `ds_json_lake`, clear it on the dataset's *Schema* tab.

**Git connection:** Data Factory is connected to this repository (collaboration branch `main`, root folder `/adf`,
publish branch `adf_publish`).
- *Speichern* commits the change to `main` (with your own commit message); run `git pull` locally afterwards.
- *Veröffentlichen* deploys to the live factory and writes deployment templates to `adf_publish`.
- Debug runs use the version from Git.
- Files: `adf/pipeline/`, `adf/dataset/`, `adf/linkedService/`, `adf/factory/` – no secrets, all connections use
  the managed identity.

## Step 6: Build a pipeline (example: Search Console)

1. **New pipeline** `pl_copy_gsc_to_raw` with parameter `load_date` (String).
2. **Copy activity** `copy_gsc_search_performance_json_to_sql`:
   - **Source:** `ds_json_lake`
     - `folder_path` = `gsc/search_performance`
     - `file_name` = `@concat('search_performance_', pipeline().parameters.load_date, '.json')`
   - **Sink:** `ds_sql_table` → `raw` / `gsc_search_performance`
     - pre-copy script `DELETE FROM raw.gsc_search_performance` (full refresh)
   - **Mapping:** *Schemas importieren* → JSON field → SQL column; `loaded_at` stays unmapped
     (filled by the database default).
3. **Debug run** – type the date by hand – then compare the row count in SQL.
4. **Speichern** (Git commit), then **Veröffentlichen** (live factory).

**One pipeline per source, one Copy activity per table:**

| Pipeline | Copy activities |
|---|---|
| `pl_copy_woocommerce_to_raw` | 5 – categories → products → product_categories, orders → order_items |
| `pl_copy_ga4_to_raw` | 5 – one per report |
| `pl_copy_gsc_to_raw` | 1 |

**Special cases in the mapping:**
- Renames: `id → product_id`
- Nested values: `$['brands'][0]['name'] → brand`
- Lists to rows: **collection reference** on `categories` or `line_items` – one order with 3 items becomes
  3 rows in `order_items`, so two tables come from one file. Use relative paths (`['id']`) inside the
  collection; `$['line_items'][0][…]` loads only the first item.

## Step 7: Run a load (currently by hand)

1. `python data/extract_<source>.py` → file lands in the lake
2. Start the matching pipeline with today's `load_date`
3. Check: `SELECT COUNT(*), MAX(loaded_at) FROM raw.<table>;`

## Pitfalls

- **Count rows after every load** – that's how the mapping that loaded only 17 of 29 order items was found.
- **Read the error message literally** – `search_performance_2026-10-03 .json` showed the trailing space from
  the start. Popups (*Debuggen*, *Schemas importieren*, *Datenvorschau*) remember the last value, and that value
  is not in the pipeline code. Type parameter values by hand instead of pasting them.
- **Schema import with a parameter fails** → temporarily set `file_name` to the plain file name, import,
  then restore the expression (the mapping stores only column names).
- **Raw keeps what the source delivered** – `raw.gsc_search_performance` has no unique key because Google sends
  some queries in two Unicode forms (`é` vs. `e` + accent), which Data Factory normalizes to the same text.
- **Data Factory rolls back the whole copy on an error** – after a failed run the table is empty
  (the pre-copy `DELETE` has already run).

## Still open

- **Automation:** an Azure Function runs the scripts; a trigger starts the pipelines **afterwards** and passes
  today's date as `load_date` (the default value is fixed at the moment).
- **Staging → mart → Power BI.**
