# ============================================================
# GOOGLE SEARCH CONSOLE INGESTION
# Extract search performance from the Search Console API
# and load it into raw.gsc_search_performance
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
import os
from datetime import date, timedelta
from urllib.parse import quote

import pandas as pd
import mssql_python
from dotenv import load_dotenv
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession


# ------------------------------------------------------------
# 2. SEARCH CONSOLE API CONFIGURATION
# ------------------------------------------------------------

# URL-prefix property of the online shop
site_url = "https://luandla.de/"

# Service account key file (same one as for GA4)
load_dotenv()
key_file = os.getenv("GOOGLE_KEY_FILE")

# Search Console keeps 16 months of data
end_date = date.today()
start_date = end_date - timedelta(days=486)

# Search types to load (Discover and Google News do not support the query dimension)
search_types = ["web", "image", "video", "news"]

credentials = service_account.Credentials.from_service_account_file(
    key_file,
    scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
)
session = AuthorizedSession(credentials)

api_url = (
    "https://searchconsole.googleapis.com/webmasters/v3/sites/"
    f"{quote(site_url, safe='')}/searchAnalytics/query"
)


def get_rows(search_type):
    # Read all rows of one search type.
    # The API returns at most 25,000 rows per request, so read page by page.
    rows = []
    start_row = 0

    while True:
        response = session.post(api_url, json={
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["date", "query", "page", "country", "device"],
            "type": search_type,
            "rowLimit": 25000,
            "startRow": start_row
        })
        response.raise_for_status()

        page_rows = response.json().get("rows", [])
        rows.extend(page_rows)

        if len(page_rows) < 25000:
            break

        start_row += 25000

    return rows


# ------------------------------------------------------------
# 3. EXTRACT AND TRANSFORM
# (keep the values as delivered)
# ------------------------------------------------------------

# Create an empty list to store all rows
search_records = []

for search_type in search_types:
    rows = get_rows(search_type)
    print(f"Search type {search_type}: {len(rows)} rows extracted")

    for row in rows:
        report_date, query, page, country, device = row["keys"]

        search_records.append({
            "report_date": date.fromisoformat(report_date),
            # Cut very long values to the column length
            "query": query[:300],
            "page": page[:500],
            "country": country,
            "device": device,
            "search_type": search_type,
            "clicks": int(row["clicks"]),
            "impressions": int(row["impressions"]),
            # The API sends whole numbers (e.g. 1) and decimals (e.g. 0.25) mixed,
            # so always convert to float; the database driver needs one type per column
            "ctr": float(row["ctr"]),
            "position": float(row["position"])
        })

# Create the DataFrame
search_df = pd.DataFrame(search_records)

print(f"Number of rows: {len(search_df)}")
print(search_df.head())


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

# Full refresh: remove the old rows, then load all rows again.
# Both steps are saved together with commit(), so the table is never half empty.
cursor.execute("DELETE FROM raw.gsc_search_performance")

columns = list(search_records[0].keys())

cursor.executemany(
    f"""
    INSERT INTO raw.gsc_search_performance ({", ".join(columns)})
    VALUES ({", ".join("?" for _ in columns)})
    """,
    [[record[column] for column in columns] for record in search_records]
)

# Save the changes
connection.commit()

print(f"{len(search_records)} rows successfully loaded into raw.gsc_search_performance.")
