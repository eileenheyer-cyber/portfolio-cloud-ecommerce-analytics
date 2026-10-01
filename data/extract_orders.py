# ============================================================
# ORDERS INGESTION
# Extract orders from WooCommerce REST API,
# save them as JSON to the Data Lake (raw/woocommerce/orders)
# and load them into raw.woocommerce_orders
# (including the billing data, customers are derived from it in staging)
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
import json
import os
from datetime import date

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
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

#get all orders
all_orders = []

page = 1

while True:
    # get the orders
    response = requests.get(
        f"{shop_url}/wp-json/wc/v3/orders",
        auth=(consumer_key, consumer_secret),
        params={
            "per_page": 100,
            "page": page,
            "_fields": "id,status,currency,date_created,date_modified,date_paid,date_completed,customer_id,payment_method,payment_method_title,discount_total,shipping_total,total_tax,total,billing,line_items"
        }
    )

    orders = response.json()

    if not orders:
         break

    all_orders.extend(orders)

    page += 1

print(f"Number of orders extracted: {len(all_orders)}")


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
file_path = f"woocommerce/orders/orders_{load_date}.json"

# Convert the API response to JSON text
# ensure_ascii=False keeps umlauts (ä, ö, ü) readable, indent=2 makes it readable in the portal
json_text = json.dumps(all_orders, ensure_ascii=False, indent=2)

# Upload the file (overwrite=True: a second run on the same day replaces that day's file)
file_client = file_system_client.get_file_client(file_path)
file_client.upload_data(json_text.encode("utf-8"), overwrite=True)

print(f"Saved to Data Lake: raw/{file_path}")


# ------------------------------------------------------------
# 4. TRANSFORM ORDERS
# (keep the values as delivered; amounts stay text and are converted in staging)
# ------------------------------------------------------------

# Create an empty list to store all orders
order_records = []

for order in all_orders:
    billing = order.get("billing") or {}

    order_records.append({
        "order_id": order["id"],
        "status": order.get("status"),
        "currency": order.get("currency"),
        "date_created": order.get("date_created"),
        "date_modified": order.get("date_modified"),
        "date_paid": order.get("date_paid"),
        "date_completed": order.get("date_completed"),
        "customer_id": order.get("customer_id"),
        "payment_method": order.get("payment_method"),
        "payment_method_title": order.get("payment_method_title"),
        "discount_total": order.get("discount_total"),
        "shipping_total": order.get("shipping_total"),
        "total_tax": order.get("total_tax"),
        "total": order.get("total"),
        "billing_first_name": billing.get("first_name"),
        "billing_last_name": billing.get("last_name"),
        "billing_email": billing.get("email"),
        "billing_address_1": billing.get("address_1"),
        "billing_postcode": billing.get("postcode"),
        "billing_city": billing.get("city"),
        "billing_country": billing.get("country")
    })

# Create the DataFrame
orders_df = pd.DataFrame(order_records)

print(f"Number of orders: {len(orders_df)}")
print(orders_df)


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

# Full refresh: remove the old rows, then load all orders again.
# Both steps are saved together with commit(), so the table is never half empty.
cursor.execute("DELETE FROM raw.woocommerce_orders")

columns = list(order_records[0].keys())

cursor.executemany(
    f"""
    INSERT INTO raw.woocommerce_orders ({", ".join(columns)})
    VALUES ({", ".join("?" for _ in columns)})
    """,
    [[order[column] for column in columns] for order in order_records]
)

# Save the changes
connection.commit()

print(f"{len(order_records)} orders successfully loaded into raw.woocommerce_orders.")
