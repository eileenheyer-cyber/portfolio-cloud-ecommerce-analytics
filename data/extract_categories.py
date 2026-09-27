# ============================================================
# CATEGORIES INGESTION
# Extract product categories from WooCommerce REST API
# and load them into raw.woocommerce_categories
# (main categories and subcategories in one table)
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

#get all product categories
all_categories = []

page = 1

while True:
    # get the categories
    response = requests.get(
        f"{shop_url}/wp-json/wc/v3/products/categories",
        auth=(consumer_key, consumer_secret),
        params={
            "per_page": 100,
            "page": page
        }
    )

    categories = response.json()

    if not categories:
         break

    all_categories.extend(categories)

    page += 1

print(f"Number of categories extracted: {len(all_categories)}")


# ------------------------------------------------------------
# 3. TRANSFORM CATEGORIES
# (keep the values as delivered; names are decoded in staging)
# ------------------------------------------------------------

# Create an empty list to store all categories
category_records = []

for category in all_categories:
    category_records.append({
        "category_id": category["id"],
        "name": category.get("name"),
        "slug": category.get("slug"),
        # 0 = main category, otherwise the ID of the main category
        "parent_id": category.get("parent")
    })

# Create the DataFrame
categories_df = pd.DataFrame(category_records)

print(f"Number of categories: {len(categories_df)}")
print(categories_df)


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

# Full refresh: remove the old rows, then load all categories again.
# Both steps are saved together with commit(), so the table is never half empty.
cursor.execute("DELETE FROM raw.woocommerce_categories")

columns = list(category_records[0].keys())

cursor.executemany(
    f"""
    INSERT INTO raw.woocommerce_categories ({", ".join(columns)})
    VALUES ({", ".join("?" for _ in columns)})
    """,
    [[category[column] for column in columns] for category in category_records]
)

# Save the changes
connection.commit()

print(f"{len(category_records)} categories successfully loaded into raw.woocommerce_categories.")
