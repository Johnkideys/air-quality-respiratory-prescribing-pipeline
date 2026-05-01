"""
Generate a GCS Transfer Service URL manifest for OpenAQ UK stations.

Lists all daily files for UK stations in a given year from the public
OpenAQ S3 bucket, writes a TSV manifest in TsvHttpData-1.0 format,
and uploads it to GCS so you can use it in a Transfer Service job.

Usage:
    uv run generate_openaq_transfer_manifest.py

Then in GCP Console:
    Storage Transfer > Create Transfer Job
    Source: URL list
    URL list location: gs://air-quality-and-respiratory-openaq-lake/manifests/openaq_2025_manifest.tsv
    Destination: air-quality-and-respiratory-openaq-lake
"""

import csv
import io

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from google.cloud import storage as gcs

S3_BUCKET = "openaq-data-archive"
S3_PREFIX = "records/csv.gz"

LOCATIONS_CSV = "../exploration/OpenAQData/openaq_data/uk_locations.csv"

GCS_BUCKET = "air-quality-and-respiratory-openaq-lake"
MANIFEST_GCS_PATH = "manifests/openaq_2025_manifest.tsv"

YEAR = 2025
MONTHS = range(1, 13)


def get_s3_client():
    return boto3.client("s3", config=Config(signature_version=UNSIGNED))


def read_location_ids(csv_path):
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        return [int(row["location_id"]) for row in reader]


def list_s3_urls(s3_client, location_ids):
    """List all S3 object URLs for the given locations and year."""
    urls = []
    total = len(location_ids)

    for i, location_id in enumerate(location_ids, 1):
        print(f"[{i}/{total}] Listing location {location_id}...", end=" ", flush=True)
        location_urls = 0

        for month in MONTHS:
            prefix = f"{S3_PREFIX}/locationid={location_id}/year={YEAR}/month={month:02d}/"
            try:
                response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
            except Exception as e:
                print(f"\n  Warning: could not list {prefix}: {e}")
                continue

            for obj in response.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".csv.gz"):
                    url = f"https://s3.amazonaws.com/{S3_BUCKET}/{key}"
                    urls.append(url)
                    location_urls += 1

        print(f"{location_urls} files")

    return urls


def write_and_upload_manifest(urls):
    """Write TSV manifest and upload to GCS."""
    print(f"\nBuilding manifest with {len(urls)} files...")

    buf = io.StringIO()
    buf.write("TsvHttpData-1.0\n")
    for url in urls:
        buf.write(url + "\n")

    content = buf.getvalue().encode("utf-8")

    client = gcs.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(MANIFEST_GCS_PATH)
    blob.upload_from_string(content, content_type="text/plain")

    print(f"Manifest uploaded to gs://{GCS_BUCKET}/{MANIFEST_GCS_PATH}")
    print(f"\nNext step — GCP Console:")
    print(f"  Storage Transfer > Create Transfer Job")
    print(f"  Source type:      URL list")
    print(f"  URL list file:    gs://{GCS_BUCKET}/{MANIFEST_GCS_PATH}")
    print(f"  Destination:      gs://{GCS_BUCKET}/raw/openaq/")


def main():
    print(f"Reading UK locations from {LOCATIONS_CSV}...")
    location_ids = read_location_ids(LOCATIONS_CSV)
    print(f"Found {len(location_ids)} locations\n")

    s3 = get_s3_client()
    urls = list_s3_urls(s3, location_ids)

    if not urls:
        print("No files found — check location IDs and year.")
        return

    print(f"\nTotal files to transfer: {len(urls)}")
    write_and_upload_manifest(urls)


if __name__ == "__main__":
    main()
