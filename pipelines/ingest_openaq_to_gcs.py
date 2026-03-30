# Script will be slow, but good for exploration stage still, 
# later for bulk uploading Ill use a different approach using the amazon cli method thats optimised for this.

"""
Ingest OpenAQ data: stream from S3 public bucket → GCS data lake.
No local disk storage - files go straight from S3 into your GCS bucket.

Prerequisites:
    pip install boto3 google-cloud-storage
    gcloud auth application-default login   (for GCS auth)
Usage:
    # Backfill last 12 months for all UK stations
    python ingest_openaq_to_gcs.py

    # Specific date range
    python ingest_openaq_to_gcs.py --start 2025-04 --end 2025-12

    # Single station (for testing)
    python ingest_openaq_to_gcs.py --location-id 1396 --start 2025-03 --end 2025-03
"""

import argparse
import csv
import io
from datetime import datetime
from calendar import monthrange

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from google.cloud import storage as gcs


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
S3_BUCKET = "openaq-data-archive"
S3_PREFIX = "records/csv.gz"

LOCATIONS_CSV = "openaq_data/uk_locations.csv"

GCS_BUCKET = "air-quality-and-respiratory-openaq-lake"
GCS_PREFIX = "raw/openaq"


def get_s3_client():
    """Create an anonymous S3 client (public bucket, no credentials needed)."""
    return boto3.client("s3", config=Config(signature_version=UNSIGNED))


def get_gcs_bucket(bucket_name):
    """Get a GCS bucket handle."""
    client = gcs.Client()
    return client.bucket(bucket_name)


def read_location_ids(csv_path):
    """Read location IDs from the uk_locations.csv file."""
    location_ids = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            location_ids.append(int(row["location_id"]))
    return location_ids


def generate_months(start_str, end_str):
    """Generate (year, month) tuples from 'YYYY-MM' start/end strings."""
    start = datetime.strptime(start_str, "%Y-%m")
    end = datetime.strptime(end_str, "%Y-%m")

    months = []
    current = start
    while current <= end:
        months.append((current.year, current.month))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def stream_month(s3_client, gcs_bucket, location_id, year, month):
    """
    Stream all daily files for one location/month from S3 to GCS.
    Returns the number of files transferred.
    """
    s3_folder = f"{S3_PREFIX}/locationid={location_id}/year={year}/month={month:02d}/"
    gcs_folder = f"{GCS_PREFIX}/locationid={location_id}/year={year}/month={month:02d}/"

    # List all objects in the S3 folder
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=s3_folder,
        )
    except Exception as e:
        print(f"    ⚠️  Error listing S3: {e}")
        return 0

    if "Contents" not in response:
        return 0

    files_transferred = 0
    for obj in response["Contents"]:
        s3_key = obj["Key"]
        filename = s3_key.split("/")[-1]

        if not filename.endswith(".csv.gz"):
            continue

        # Download from S3 into memory
        s3_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        data = s3_obj["Body"].read()

        # Upload to GCS
        gcs_path = f"{gcs_folder}{filename}"
        blob = gcs_bucket.blob(gcs_path)
        blob.upload_from_string(data, content_type="application/gzip")

        files_transferred += 1

    return files_transferred


def main():
    parser = argparse.ArgumentParser(description="Stream OpenAQ S3 data to GCS")
    parser.add_argument("--start", default="2025-04",
                        help="Start month YYYY-MM (default: 2025-04)")
    parser.add_argument("--end", default="2026-03",
                        help="End month YYYY-MM (default: 2026-03)")
    parser.add_argument("--location-id", type=int, default=None,
                        help="Single location ID (default: all from CSV)")
    parser.add_argument("--gcs-bucket", default=GCS_BUCKET,
                        help="GCS bucket name")
    parser.add_argument("--locations-csv", default=LOCATIONS_CSV,
                        help="Path to uk_locations.csv")
    args = parser.parse_args()

    if not args.gcs_bucket:
        print("❌ Set --gcs-bucket or edit GCS_BUCKET in the script")
        print("   e.g. python ingest_openaq_to_gcs.py --gcs-bucket my-project-air-quality-lake")
        return

    # Get location IDs
    if args.location_id:
        location_ids = [args.location_id]
        print(f"📍 Single location: {args.location_id}")
    else:
        location_ids = read_location_ids(args.locations_csv)
        print(f"📍 Loaded {len(location_ids)} locations from {args.locations_csv}")

    months = generate_months(args.start, args.end)
    print(f"📅 Date range: {args.start} to {args.end} ({len(months)} months)")
    print(f"☁️  GCS bucket: {args.gcs_bucket}")
    print(f"📦 Total downloads: {len(location_ids)} stations × {len(months)} months")
    print()

    # Set up clients
    s3 = get_s3_client()
    gcs_bucket = get_gcs_bucket(args.gcs_bucket)

    # Process
    total_files = 0
    empty_months = 0

    for i, location_id in enumerate(location_ids, 1):
        print(f"[{i}/{len(location_ids)}] Location {location_id}")

        for year, month in months:
            files = stream_month(s3, gcs_bucket, location_id, year, month)
            total_files += files

            if files > 0:
                print(f"  {year}-{month:02d}: {files} files ✅")
            else:
                print(f"  {year}-{month:02d}: no data")
                empty_months += 1

    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"{'='*50}")
    print(f"  Files transferred:  {total_files}")
    print(f"  Empty months:       {empty_months}")
    print(f"  GCS path:           gs://{args.gcs_bucket}/{GCS_PREFIX}/")


if __name__ == "__main__":
    main()
