"""
Download NHS English Prescribing Dataset (EPD) from NHSBSA Open Data Portal,
filter to respiratory (salbutamol) BNF codes using PySpark, save as parquet.

Processes ONE MONTH at a time to keep disk usage low (~500MB temp per month).

Prerequisites:
    pip install pyspark requests

Usage:
    # Single month test
    python download_epd_spark_filter.py --year 2024 --month 1

    # Backfill a full year
    python download_epd_spark_filter.py --year 2024 --month 1 --months 12
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import requests
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# NHSBSA CKAN API base
CKAN_API = "https://opendata.nhsbsa.net/api/3/action"

# EPD dataset ID on CKAN
DATASET_ID = "english-prescribing-data-epd"

# BNF codes to keep — salbutamol (all presentations)
# 0301011R0 = Salbutamol — the first 9 chars of BNF_CODE identify the chemical
# You could expand this to all of BNF section 0301 (bronchodilators) if desired
BNF_FILTER_PREFIXES = [
    "0301011R0",  # Salbutamol
    # "0301",     # Uncomment to keep ALL bronchodilators
]

TEMP_DIR = Path("temp_epd")
OUTPUT_DIR = Path("output_epd")


# ---------------------------------------------------------------------------
# Step 1: Discover download URLs from CKAN API
# ---------------------------------------------------------------------------

def get_resource_url(year: int, month: int) -> str:
    """
    Query the CKAN API to find the download URL for a given EPD month.
    The resources are named like 'EPD_202401'.
    """
    resource_name = f"EPD_{year}{month:02d}"

    print(f"  Looking up resource: {resource_name}")
    resp = requests.get(
        f"{CKAN_API}/package_show",
        params={"id": DATASET_ID},
        timeout=30,
    )
    resp.raise_for_status()
    package = resp.json()["result"]

    for resource in package["resources"]:
        # Match on the resource name — CKAN stores it in 'name' or 'description'
        if resource.get("name", "").strip() == resource_name:
            return resource["url"]

    # Fallback: try matching on the URL itself
    for resource in package["resources"]:
        if resource_name.lower() in resource.get("url", "").lower():
            return resource["url"]

    raise ValueError(
        f"Could not find resource '{resource_name}' in dataset. "
        f"Data may not be published yet (2-month lag)."
    )


# ---------------------------------------------------------------------------
# Step 2: Download the CSV
# ---------------------------------------------------------------------------

def download_csv(url: str, dest: Path) -> Path:
    """Stream-download a large CSV file."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"  Downloading: {url}")
    print(f"  Saving to:   {dest}")

    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):  # 8MB chunks
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                print(f"\r  Progress: {downloaded / 1e6:.0f} MB / {total / 1e6:.0f} MB ({pct:.0f}%)", end="")

    print()  # newline after progress
    return dest


# ---------------------------------------------------------------------------
# Step 3: PySpark filter to respiratory BNF codes
# ---------------------------------------------------------------------------

def spark_filter(csv_path: Path, year: int, month: int) -> Path:
    """
    Read the raw EPD CSV with Spark, filter to salbutamol rows,
    write out as parquet.
    """
    output_path = OUTPUT_DIR / f"year={year}" / f"month={month:02d}"
    output_path.mkdir(parents=True, exist_ok=True)

    parquet_path = output_path / f"epd_{year}{month:02d}_respiratory.parquet"

    print(f"  Starting Spark filter...")

    spark = SparkSession.builder \
        .appName("EPD_Filter") \
        .master("local[*]") \
        .config("spark.driver.memory", "4g") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    try:
        # Read raw CSV — EPD uses comma separator
        df = spark.read.csv(
            str(csv_path),
            header=True,
            inferSchema=True,
        )

        row_count_raw = df.count()
        print(f"  Raw rows:      {row_count_raw:,}")
        print(f"  Columns:       {df.columns}")

        # Build filter condition for BNF code prefixes
        # The BNF_CODE column contains 15-char presentation codes
        # First 9 chars = chemical substance
        filter_cond = None
        for prefix in BNF_FILTER_PREFIXES:
            cond = F.col("BNF_CODE").startswith(prefix)
            filter_cond = cond if filter_cond is None else (filter_cond | cond)

        df_filtered = df.filter(filter_cond)
        row_count_filtered = df_filtered.count()

        print(f"  Filtered rows: {row_count_filtered:,}")
        print(f"  Reduction:     {(1 - row_count_filtered / row_count_raw) * 100:.1f}%")

        # Write as single parquet file (coalesce to 1 for simplicity)
        df_filtered.coalesce(1).write.mode("overwrite").parquet(str(parquet_path))

        print(f"  Parquet saved: {parquet_path}")

        # Show a sample
        print(f"\n  Sample (first 5 rows):")
        df_filtered.show(5, truncate=False)

    finally:
        spark.stop()

    return parquet_path


# ---------------------------------------------------------------------------
# Step 4: Cleanup temp files
# ---------------------------------------------------------------------------

def cleanup_temp(csv_path: Path):
    """Remove the large raw CSV to free disk space."""
    if csv_path.exists():
        size_mb = csv_path.stat().st_size / 1e6
        csv_path.unlink()
        print(f"  Cleaned up temp file ({size_mb:.0f} MB freed)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_month(year: int, month: int):
    """Full pipeline for one month: discover → download → filter → cleanup."""
    print(f"\n{'='*60}")
    print(f"Processing EPD {year}-{month:02d}")
    print(f"{'='*60}")

    # 1. Find download URL
    url = get_resource_url(year, month)

    # 2. Download raw CSV
    csv_path = TEMP_DIR / f"EPD_{year}{month:02d}.csv"
    download_csv(url, csv_path)

    # 3. Spark filter
    parquet_path = spark_filter(csv_path, year, month)

    # 4. Cleanup
    cleanup_temp(csv_path)

    print(f"\n  ✅ Done: {year}-{month:02d} → {parquet_path}")


def main():
    parser = argparse.ArgumentParser(description="Download and filter EPD data")
    parser.add_argument("--year", type=int, required=True, help="Start year (e.g. 2024)")
    parser.add_argument("--month", type=int, required=True, help="Start month (1-12)")
    parser.add_argument("--months", type=int, default=1, help="Number of months to process (default: 1)")
    args = parser.parse_args()

    TEMP_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    year, month = args.year, args.month

    for i in range(args.months):
        try:
            process_month(year, month)
        except Exception as e:
            print(f"\n  ❌ Error processing {year}-{month:02d}: {e}")
            print(f"     Skipping and continuing...")

        # Advance to next month
        month += 1
        if month > 12:
            month = 1
            year += 1

    print(f"\n{'='*60}")
    print(f"All done! Filtered parquet files are in: {OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()