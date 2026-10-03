# ============================================================
# GOOGLE SEARCH CONSOLE INGESTION
# Extract search performance from the Search Console API,
# and save it as JSON to the Data Lake (raw/gsc/search_performance).
# Data Factory (pl_copy_gsc_to_raw) loads it into raw.gsc_search_performance.
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
import json
import os
from datetime import date, timedelta
from urllib.parse import quote

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
import pandas as pd
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
# (keep the values as delivered: dates stay text like "2026-03-15" and are
# converted in staging; only long texts are cut to the column length,
# because Data Factory does not cut them)
# ------------------------------------------------------------

# Create an empty list to store all rows
search_records = []

for search_type in search_types:
    rows = get_rows(search_type)
    print(f"Search type {search_type}: {len(rows)} rows extracted")

    for row in rows:
        report_date, query, page, country, device = row["keys"]

        search_records.append({
            "report_date": report_date,
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
# 4. SAVE RAW DATA TO THE DATA LAKE
# (field names = column names of the raw table)
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

# Today's date as text, e.g. "2026-10-01" (one file per load)
load_date = date.today().isoformat()

# Path inside the raw container; folders are created automatically
file_path = f"gsc/search_performance/search_performance_{load_date}.json"

# ensure_ascii=False keeps umlauts (ä, ö, ü) readable, indent=2 makes it readable in the portal
json_text = json.dumps(search_records, ensure_ascii=False, indent=2)

# Upload the file (overwrite=True: a second run on the same day replaces that day's file)
file_client = file_system_client.get_file_client(file_path)
file_client.upload_data(json_text.encode("utf-8"), overwrite=True)

print(f"Saved to Data Lake: raw/{file_path}")
