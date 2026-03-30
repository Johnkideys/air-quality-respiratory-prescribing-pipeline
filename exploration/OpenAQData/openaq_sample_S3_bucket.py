"""
Download a sample day of OpenAQ data from the public S3 bucket.
"""

import urllib.request
import gzip
import csv
import io
import os
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Leeds Headingley Kerbside - already know this ID from API exploration
LOCATION_ID = 1396

OUTPUT_DIR = "openaq_sample"

# The S3 bucket is publicly accessible via plain HTTPS - no auth needed
BASE_URL = "https://openaq-data-archive.s3.amazonaws.com"


def download_sensor_data(location_id, sample_date):
    """Download one day's CSV from the public S3 bucket and print what's inside."""
    # Construct the URL following the Hive partition structure:
    # /records/csv.gz/locationid={id}/year={yyyy}/month={mm}/location-{id}-{yyyymmdd}.csv.gz
    year = sample_date[0:4]
    month = sample_date[4:6]
    day = sample_date[6:8]

    url = (
        f"{BASE_URL}/records/csv.gz/"
        f"locationid={location_id}/"
        f"year={year}/"
        f"month={month}/"
        f"location-{location_id}-{sample_date}.csv.gz"
    )

    print(f"Downloading: {url}")
    print(f"(Location: {location_id}, Date: {year}-{month}-{day})")
    print()

    try:
        # Download the gzipped CSV
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            compressed = response.read()
            #print(f"Downloaded {len(compressed):,} bytes (compressed)")

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"File not found (404). This date might not have data yet.")
        else:
            print(f"HTTP Error {e.code}: {e.reason}")
        return
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}")
        print("Check your internet connection.")
        return

    # Decompress
    decompressed = gzip.decompress(compressed)
    text = decompressed.decode("utf-8")

    # Save raw CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = f"{OUTPUT_DIR}/location-{LOCATION_ID}-{sample_date}.csv"
    with open(csv_path, "w") as f:
        f.write(text)
    print(f"Saved to: {csv_path}")

    # Parse and display
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    print(f"\n✅ Full CSV saved to: {csv_path}")

if __name__ == "__main__":
    # Create a 2 month period for downloading the csv files 
    for days_ago in range(5, 8):
        date_str = (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d")
        download_sensor_data(LOCATION_ID, date_str)