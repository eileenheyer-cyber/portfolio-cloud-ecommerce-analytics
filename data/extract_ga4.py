# ============================================================
# GOOGLE ANALYTICS 4 INGESTION
# Extract daily reports from the GA4 Data API,
# and save them as JSON to the Data Lake (raw/ga4/<report>, one file per report).
# Data Factory (pl_copy_ga4_to_raw) loads them into
#   raw.ga4_daily_traffic   raw.ga4_daily_events   raw.ga4_landing_pages
#   raw.ga4_page_events     raw.ga4_audience
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
import json
import os
from datetime import date

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
import pandas as pd
from dotenv import load_dotenv
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest
)


# ------------------------------------------------------------
# 2. GA4 API CONFIGURATION
# ------------------------------------------------------------

# GA4 property of the online shop
property_id = "518947113"

# Service account key file (keep it outside the project folder)
load_dotenv()
key_file = os.getenv("GOOGLE_KEY_FILE")

# Period to load: GA4 data starts in January 2026
start_date = "2025-11-01"
end_date = "yesterday"          # only complete days

client = BetaAnalyticsDataClient.from_service_account_file(key_file)


def run_report(dimensions, metrics):
    # Run one GA4 report and return all rows as a list of dictionaries.
    # GA4 returns at most 100,000 rows per request, so read page by page.
    rows = []
    offset = 0

    while True:
        response = client.run_report(RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimensions=[Dimension(name=name) for name in dimensions],
            metrics=[Metric(name=name) for name in metrics],
            limit=100000,
            offset=offset
        ))

        for row in response.rows:
            record = {}
            for name, value in zip(dimensions, row.dimension_values):
                record[name] = value.value
            for name, value in zip(metrics, row.metric_values):
                record[name] = int(value.value)
            rows.append(record)

        offset += len(response.rows)

        if offset >= response.row_count or not response.rows:
            break

    return rows


# ------------------------------------------------------------
# 3. EXTRACT AND TRANSFORM THE REPORTS
# (keep the values as delivered: dates stay text like "20260315" and are
# converted in staging, admin pages are filtered in staging;
# only long texts are cut to the column length, because Data Factory does not cut them)
# ------------------------------------------------------------

# Daily traffic per channel, source, medium and campaign
traffic_records = [
    {
        "report_date": row["date"],
        "session_default_channel_group": row["sessionDefaultChannelGroup"],
        "session_source": row["sessionSource"][:100],
        "session_medium": row["sessionMedium"][:100],
        "session_campaign_name": row["sessionCampaignName"][:100],
        "sessions": row["sessions"],
        "total_users": row["totalUsers"],
        "new_users": row["newUsers"],
        "engaged_sessions": row["engagedSessions"],
        "screen_page_views": row["screenPageViews"]
    }
    for row in run_report(
        ["date", "sessionDefaultChannelGroup", "sessionSource",
         "sessionMedium", "sessionCampaignName"],
        ["sessions", "totalUsers", "newUsers", "engagedSessions", "screenPageViews"]
    )
]

# Daily count of every event (page_view, add_to_cart, purchase, ...)
event_records = [
    {
        "report_date": row["date"],
        "event_name": row["eventName"],
        "event_count": row["eventCount"]
    }
    for row in run_report(["date", "eventName"], ["eventCount"])
]

# Daily sessions per landing page
landing_page_records = [
    {
        "report_date": row["date"],
        # Cut very long URLs to the column length
        "landing_page": row["landingPage"][:400],
        "sessions": row["sessions"],
        "engaged_sessions": row["engagedSessions"]
    }
    for row in run_report(["date", "landingPage"], ["sessions", "engagedSessions"])
]

# Daily count of every event per page (e.g. page views and add-to-cart per product page)
page_event_records = [
    {
        "report_date": row["date"],
        # Cut very long URLs to the column length
        "page_path": row["pagePath"][:300],
        "event_name": row["eventName"],
        "event_count": row["eventCount"]
    }
    for row in run_report(["date", "pagePath", "eventName"], ["eventCount"])
]

# Daily sessions per device category and country
audience_records = [
    {
        "report_date": row["date"],
        "device_category": row["deviceCategory"],
        "country": row["country"],
        "sessions": row["sessions"],
        "total_users": row["totalUsers"],
        "engaged_sessions": row["engagedSessions"]
    }
    for row in run_report(
        ["date", "deviceCategory", "country"],
        ["sessions", "totalUsers", "engagedSessions"]
    )
]

# Report name = folder in the lake and table name raw.ga4_<report>
reports = {
    "daily_traffic": traffic_records,
    "daily_events": event_records,
    "landing_pages": landing_page_records,
    "page_events": page_event_records,
    "audience": audience_records
}

for report, records in reports.items():
    print(f"{report}: {len(records)} rows extracted")

print(pd.DataFrame(traffic_records).head())


# ------------------------------------------------------------
# 4. SAVE RAW DATA TO THE DATA LAKE
# (one JSON file per report, field names = column names of the raw tables)
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

for report, records in reports.items():
    # Path inside the raw container; folders are created automatically
    file_path = f"ga4/{report}/{report}_{load_date}.json"

    # ensure_ascii=False keeps umlauts (ä, ö, ü) readable, indent=2 makes it readable in the portal
    json_text = json.dumps(records, ensure_ascii=False, indent=2)

    # Upload the file (overwrite=True: a second run on the same day replaces that day's file)
    file_client = file_system_client.get_file_client(file_path)
    file_client.upload_data(json_text.encode("utf-8"), overwrite=True)

    print(f"Saved to Data Lake: raw/{file_path}")
