# ============================================================
# ORDERS INGESTION
# Extract orders from WooCommerce REST API,
# and save them as JSON to the Data Lake (raw/woocommerce/orders).
# Data Factory (pl_copy_woocommerce_to_raw) loads them into
#   raw.woocommerce_orders       (including the billing data, customers are derived from it in staging)
#   raw.woocommerce_order_items  (from the line_items of each order)
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
