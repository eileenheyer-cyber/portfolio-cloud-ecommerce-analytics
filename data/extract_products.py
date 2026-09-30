# ============================================================
# PRODUCTS INGESTION
# Extract products from WooCommerce REST API and load them into
#   raw.woocommerce_products            (one row per product)
#   raw.woocommerce_product_categories  (one row per product and category)
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
import json
from datetime import date
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient



import os
import requests
import pandas as pd
import mssql_python
from dotenv import load_dotenv


# ------------------------------------------------------------
# 2. WOOCOMMERCE API CONFIGURATION
# ------------------------------------------------------------


# API keys come from the .env file (not stored in the code)
load_dotenv()
consumer_key = os.getenv("WC_CONSUMER_KEY")
consumer_secret = os.getenv("WC_CONSUMER_SECRET")
shop_url = "https://luandla.de/"

#get all products
all_products = []

page = 1

while True:
    # get the products
    response = requests.get(
        f"{shop_url}/wp-json/wc/v3/products",
        auth=(consumer_key, consumer_secret),
        params={
            "per_page": 100,
            "page": page,
            "_fields": "id,name,slug,type,status,sku,brands,price,regular_price,sale_price,stock_quantity,date_created,date_modified,categories"
        }
    )

    products = response.json()

    if not products:
         break

    all_products.extend(products)

    page += 1

print(f"Number of products extracted: {len(all_products)}")


# ------------------------------------------------------------
# 3. SAVE RAW DATA TO THE DATA LAKE
# (the API response unchanged, as a JSON file)
# ------------------------------------------------------------

# Address of the Data Lake (dfs = Data Lake endpoint)
account_url = "https://stecommercelake26.dfs.core.windows.net"

# Log in with the Azure CLI login (az login), no storage key
credential = DefaultAzureCredential()

# Connection to the storage account
service_client = DataLakeServiceClient(
    account_url=account_url,
    credential=credential
)

# Connection to the raw container
file_system_client = service_client.get_file_system_client("raw")

# Today's date as text, e.g. "2026-09-27" (one file per load)
load_date = date.today().isoformat()

# Path inside the raw container; folders are created automatically
file_path = f"woocommerce/products/products_{load_date}.json"

# Convert the API response to JSON text
# ensure_ascii=False keeps umlauts (ä, ö, ü) readable, indent=2 makes it readable in the portal
json_text = json.dumps(all_products, ensure_ascii=False, indent=2)

# Upload the file (overwrite=True: a second run on the same day replaces that day's file)
file_client = file_system_client.get_file_client(file_path)
file_client.upload_data(json_text.encode("utf-8"), overwrite=True)

print(f"Saved to Data Lake: raw/{file_path}")


# ------------------------------------------------------------
# 4. TRANSFORM PRODUCTS
# (keep the values as delivered, only convert text prices to numbers)
# ------------------------------------------------------------


def to_number(value):
    # WooCommerce delivers prices as text; empty text means no price
    return float(value) if value not in (None, "") else None


# Create empty lists for products and their category assignments
product_records = []
product_category_records = []

for product in all_products:
    # Brand comes from the WooCommerce "brands" field
    brands = product.get("brands") or []

    product_records.append({
        "product_id": product["id"],
        "name": product.get("name"),
        "slug": product.get("slug"),
        "type": product.get("type"),
        "status": product.get("status"),
        "sku": product.get("sku"),
        "brand": brands[0]["name"] if brands else None,
        "price": to_number(product.get("price")),
        "regular_price": to_number(product.get("regular_price")),
        "sale_price": to_number(product.get("sale_price")),
        "stock_quantity": product.get("stock_quantity"),
        "date_created": product.get("date_created"),
        "date_modified": product.get("date_modified")
    })

    # A product can belong to several categories: keep all of them
    for category in product.get("categories", []):
        product_category_records.append({
            "product_id": product["id"],
            "category_id": category["id"]
        })

# Create the DataFrames
products_df = pd.DataFrame(product_records)
product_categories_df = pd.DataFrame(product_category_records)

print(f"Number of products: {len(products_df)}")
print(products_df)
print(f"Number of product-category assignments: {len(product_categories_df)}")


# ------------------------------------------------------------
# 5. LOAD INTO AZURE SQL
# ------------------------------------------------------------

# Azure SQL connection details
server = "ecommerce-analytics-sql-2026.database.windows.net"
database = "ecommerce-analytics-db"

# Create a connection to Azure SQL
connection = mssql_python.connect(
    f"SERVER={server};"
    f"DATABASE={database};"
    "Authentication=ActiveDirectoryDefault;"      # uses the Azure CLI login (az login)
    "Encrypt=yes;"
)

cursor = connection.cursor()
# Test the Azure SQL connection
cursor.execute("SELECT DB_NAME()")
database_name = cursor.fetchone()[0]

print(f"Connected to database: {database_name}")


def full_refresh(table, records):
    # Remove the old rows, then insert all records again
    cursor.execute(f"DELETE FROM {table}")

    columns = list(records[0].keys())

    cursor.executemany(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        """,
        [[record[column] for column in columns] for record in records]
    )

    print(f"{len(records)} rows loaded into {table}.")


full_refresh("raw.woocommerce_products", product_records)
full_refresh("raw.woocommerce_product_categories", product_category_records)

# Save both tables together
connection.commit()

print("Products successfully loaded into Azure SQL.")
