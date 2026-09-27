# ============================================================
# GOOGLE ANALYTICS 4 INGESTION
# Extract daily reports from the GA4 Data API and load them into
#   raw.ga4_daily_traffic   raw.ga4_daily_events   raw.ga4_landing_pages
#   raw.ga4_page_events     raw.ga4_audience
# ============================================================


# ------------------------------------------------------------
# 1. IMPORT LIBRARIES
# ------------------------------------------------------------
import os
from datetime import datetime

import pandas as pd
import mssql_python
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


def to_date(value):
    # GA4 delivers dates as text "20260315"
    return datetime.strptime(value, "%Y%m%d").date()


# ------------------------------------------------------------
# 3. EXTRACT AND TRANSFORM THE REPORTS
# (keep the values as delivered; admin pages are filtered in staging)
# ------------------------------------------------------------

# Daily traffic per channel, source, medium and campaign
traffic_records = [
    {
        "report_date": to_date(row["date"]),
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
        "report_date": to_date(row["date"]),
        "event_name": row["eventName"],
        "event_count": row["eventCount"]
    }
    for row in run_report(["date", "eventName"], ["eventCount"])
]

# Daily sessions per landing page
landing_page_records = [
    {
        "report_date": to_date(row["date"]),
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
        "report_date": to_date(row["date"]),
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
        "report_date": to_date(row["date"]),
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

reports = {
    "raw.ga4_daily_traffic": traffic_records,
    "raw.ga4_daily_events": event_records,
    "raw.ga4_landing_pages": landing_page_records,
    "raw.ga4_page_events": page_event_records,
    "raw.ga4_audience": audience_records
}

for table, records in reports.items():
    print(f"{table}: {len(records)} rows extracted")

print(pd.DataFrame(traffic_records).head())


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


def full_refresh(table, records):
    # Remove the old rows, then insert all records again
    cursor.execute(f"DELETE FROM {table}")

    if not records:
        print(f"No rows for {table}.")
        return

    columns = list(records[0].keys())

    cursor.executemany(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        """,
        [[record[column] for column in columns] for record in records]
    )

    print(f"{len(records)} rows loaded into {table}.")


for table, records in reports.items():
    full_refresh(table, records)

# Save all five tables together
connection.commit()

print("GA4 data successfully loaded into Azure SQL.")
