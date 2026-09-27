# ============================================================
# ORDERS INGESTION
# Extract orders from WooCommerce REST API
# and load them into raw.woocommerce_orders
# (including the billing data, customers are derived from it in staging)
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
# 3. TRANSFORM ORDERS
# (keep the values as delivered, only convert text amounts to numbers)
# ------------------------------------------------------------


def to_number(value):
    # WooCommerce delivers amounts as text; empty text means no value
    return float(value) if value not in (None, "") else None


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
        "discount_total": to_number(order.get("discount_total")),
        "shipping_total": to_number(order.get("shipping_total")),
        "total_tax": to_number(order.get("total_tax")),
        "total": to_number(order.get("total")),
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
