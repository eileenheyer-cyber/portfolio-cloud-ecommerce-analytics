# ============================================================
# ORDER ITEMS INGESTION
# Extract order items (line items) from WooCommerce REST API
# and load them into raw.woocommerce_order_items
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
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
            "page": page
        }
    )

    orders = response.json()

    if not orders:
         break

    all_orders.extend(orders)

    page += 1

print(f"Number of orders extracted: {len(all_orders)}")


# ------------------------------------------------------------
# 3. TRANSFORM ORDER ITEMS
# (keep the values as delivered, only convert text amounts to numbers)
# ------------------------------------------------------------


def to_number(value):
    # WooCommerce delivers amounts as text; empty text means no value
    return float(value) if value not in (None, "") else None


# Create an empty list to store all order items
order_item_records = []

# Loop through all WooCommerce orders
for order in all_orders:
    # Every order contains a list of purchased products (line items)
    for item in order.get("line_items", []):

        order_item_records.append({
            "item_id": item["id"],
            "order_id": order["id"],
            # 0 = deleted product / no variation (cleaned in staging)
            "product_id": item.get("product_id"),
            "variation_id": item.get("variation_id"),
            "name": item.get("name"),
            "sku": item.get("sku"),
            "quantity": item.get("quantity"),
            "subtotal": to_number(item.get("subtotal")),
            "subtotal_tax": to_number(item.get("subtotal_tax")),
            "total": to_number(item.get("total")),
            "total_tax": to_number(item.get("total_tax")),
            "price": to_number(item.get("price"))
        })

# Create the DataFrame
order_items_df = pd.DataFrame(order_item_records)

print(f"Number of order items: {len(order_items_df)}")
print(order_items_df)


# ------------------------------------------------------------
# 4. LOAD INTO AZURE SQL
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

# Full refresh: remove the old rows, then load all order items again.
# Both steps are saved together with commit(), so the table is never half empty.
cursor.execute("DELETE FROM raw.woocommerce_order_items")

columns = list(order_item_records[0].keys())

cursor.executemany(
    f"""
    INSERT INTO raw.woocommerce_order_items ({", ".join(columns)})
    VALUES ({", ".join("?" for _ in columns)})
    """,
    [[item[column] for column in columns] for item in order_item_records]
)

# Save the changes
connection.commit()

print(f"{len(order_item_records)} order items successfully loaded into raw.woocommerce_order_items.")
