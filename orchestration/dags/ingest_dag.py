"""
Ingest DAG: Fetch new monthly data from sources and upload to GCS.

Runs monthly. Also manually triggerable for backfills.
Refreshes UK station list, then runs three parallel ingestion tasks,
then triggers the transform DAG.
"""

from datetime import datetime

from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

GCS_BUCKET = "air-quality-and-respiratory-openaq-lake"
S3_BUCKET = "openaq-data-archive"
S3_PREFIX = "records/csv.gz"
UK_LOCATIONS_GCS_PATH = "config/uk_locations.csv"

OPENAQ_API_BASE = "https://api.openaq.org/v3"
OPENAQ_PARAMS = {2: "pm25", 1: "pm10", 5: "no2"}

OPENPRESCRIBING_BASE_URL = "https://openprescribing.net/api/1.0"
BNF_SECTIONS = {
    "0301": "Bronchodilators",
    "0302": "Corticosteroid inhalers (ICS)",
    "0303": "Cromoglicate and related",
    "060302": "Systemic corticosteroids",
}


@dag(
    schedule="@monthly",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["ingest"],
    doc_md=__doc__,
)
def ingest_dag():

    @task
    def refresh_uk_stations():
        """Fetch current UK air quality station IDs from OpenAQ API and upload to GCS."""
        import csv
        import io
        import os
        import time

        import requests
        from google.cloud import storage as gcs

        api_key = os.environ["OPENAQ_API_KEY"]
        headers = {"X-API-Key": api_key, "Accept": "application/json"}

        # Find UK country ID
        resp = requests.get(f"{OPENAQ_API_BASE}/countries", headers=headers, params={"limit": 200})
        resp.raise_for_status()
        country_id = None
        for country in resp.json()["results"]:
            if country.get("code") == "GB": # GB for Great Britain
                country_id = country["id"]
                break
        if not country_id:
            raise ValueError("Could not find UK in OpenAQ countries")

        # Fetch all UK locations (location_id is the station in OpenAQ) with PM2.5, PM10, or NO2
        all_locations = {}
        for param_id, param_name in OPENAQ_PARAMS.items():
            print(f"  Fetching UK stations with {param_name}...")
            page = 1
            while True:
                resp = requests.get(
                    f"{OPENAQ_API_BASE}/locations",
                    headers=headers,
                    params={"countries_id": country_id, "parameters_id": param_id, "limit": 1000, "page": page},
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if not results:
                    break
                for loc in results:
                    loc_id = loc["id"]
                    if loc_id not in all_locations:
                        entry = {
                            "location_id": loc_id,
                            "name": loc.get("name", ""),
                            "latitude": loc.get("coordinates", {}).get("latitude"),
                            "longitude": loc.get("coordinates", {}).get("longitude"),
                            "is_monitor": loc.get("isMonitor"),
                            "is_mobile": loc.get("isMobile"),
                            "has_pm25": False, 
                            "pm25_sensor_id": None,
                            "has_pm10": False, 
                            "pm10_sensor_id": None,
                            "has_no2": False,  
                            "no2_sensor_id": None
                        }
                        for sensor in loc.get("sensors", []):
                            pid = sensor.get("parameter", {}).get("id")
                            if pid == 2:
                                entry["has_pm25"], entry["pm25_sensor_id"] = True, sensor["id"]
                            elif pid == 1:
                                entry["has_pm10"], entry["pm10_sensor_id"] = True, sensor["id"]
                            elif pid == 5:
                                entry["has_no2"], entry["no2_sensor_id"] = True, sensor["id"]
                        all_locations[loc_id] = entry
                found = resp.json().get("meta", {}).get("found", 0)
                if page * 1000 >= found or len(results) < 1000:
                    break
                page += 1
                time.sleep(0.5)

        print(f"  Found {len(all_locations)} UK stations total")

        # Write CSV to GCS
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "location_id", "name", "latitude", "longitude",
            "is_monitor", "is_mobile",
            "has_pm25", "pm25_sensor_id",
            "has_pm10", "pm10_sensor_id",
            "has_no2",  "no2_sensor_id",
        ])
        writer.writeheader()
        for loc in all_locations.values():
            writer.writerow(loc)

        gcs_client = gcs.Client()
        bucket = gcs_client.bucket(GCS_BUCKET)
        blob = bucket.blob(UK_LOCATIONS_GCS_PATH)
        blob.upload_from_string(buf.getvalue(), content_type="text/csv")

        print(f"  Uploaded {len(all_locations)} stations to gs://{GCS_BUCKET}/{UK_LOCATIONS_GCS_PATH}")
        return len(all_locations)

    @task
    def ingest_openaq_to_gcs(**context):
        """Stream one month of OpenAQ data from S3 to GCS for all UK stations."""
        import csv
        import io

        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        from google.cloud import storage as gcs
        from google.cloud.storage.retry import DEFAULT_RETRY

        execution_date = context["logical_date"]
        year = execution_date.year
        month = execution_date.month

        # Read UK station IDs from GCS (refreshed by upstream task)
        gcs_client = gcs.Client()
        bucket = gcs_client.bucket(GCS_BUCKET)
        blob = bucket.blob(UK_LOCATIONS_GCS_PATH)
        csv_content = blob.download_as_text()
        reader = csv.DictReader(io.StringIO(csv_content))
        location_ids = [int(row["location_id"]) for row in reader]

        # For testing purposes:
        #location_ids = location_ids[:2]

        # Anonymous S3 client (public bucket) with aggressive retries for transient network errors
        s3 = boto3.client(
            "s3",
            config=Config(
                signature_version=UNSIGNED,
                retries={"max_attempts": 10, "mode": "adaptive"},
            ),
        )

        # Retry policy for GCS uploads — handles RemoteDisconnected and other transient errors
        upload_retry = DEFAULT_RETRY.with_deadline(300)

        total_files = 0
        failed_stations = []
        for i, location_id in enumerate(location_ids, 1):
            prefix = f"{S3_PREFIX}/locationid={location_id}/year={year}/month={month:02d}/"

            try:
                response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)

                for obj in response.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".csv.gz"):
                        continue

                    filename = key.split("/")[-1]
                    s3_obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
                    data = s3_obj["Body"].read()

                    gcs_path = f"raw/openaq/year={year}/month={month:02d}/locationid={location_id}/{filename}"
                    dest_blob = bucket.blob(gcs_path)
                    dest_blob.upload_from_string(
                        data,
                        content_type="application/gzip",
                        retry=upload_retry,
                    )
                    total_files += 1

            except Exception as e:
                print(f"  FAILED station {location_id}: {e}")
                failed_stations.append(location_id)
                continue

            if i % 50 == 0:
                print(f"  Progress: {i}/{len(location_ids)} stations, {total_files} files")

        print(f"Transferred {total_files} files for {year}-{month:02d}")
        if failed_stations:
            print(f"  {len(failed_stations)} stations failed: {failed_stations}")
        return total_files

    @task
    def ingest_prescribing_to_gcs(**context):
        """Fetch one month of prescribing data from OpenPrescribing API, save as parquet to GCS."""
        import io
        import time

        import pandas as pd
        from curl_cffi import requests
        from google.cloud import storage as gcs

        execution_date = context["logical_date"]
        year = execution_date.year
        month = execution_date.month
        date_str = f"{year}-{month:02d}-01" # prescription data is aggregated as monthly from api, so always 1st of the month

        all_records = []

        for bnf_code, label in BNF_SECTIONS.items():
            print(f"  Fetching {label} ({bnf_code}) for {date_str}...")
            resp = requests.get(
                f"{OPENPRESCRIBING_BASE_URL}/spending_by_org/",
                params={
                    "org_type": "practice",
                    "code": bnf_code,
                    "date": date_str,
                    "format": "json",
                },
                impersonate="chrome",
                timeout=120,
            )
            resp.raise_for_status()
            records = resp.json()
            for rec in records:
                rec["bnf_section"] = bnf_code
                rec["bnf_label"] = label
            all_records.extend(records)
            print(f"    {len(records)} rows")
            time.sleep(0.5)

        if not all_records:
            print(f"No prescribing data for {date_str}")
            return 0

        df = pd.DataFrame(all_records)
        df["period_date"] = f"{year}-{month:02d}-01"
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)

        gcs_client = gcs.Client()
        bucket = gcs_client.bucket(GCS_BUCKET)
        gcs_path = f"raw/prescribing/year={year}/month={month:02d}/prescribing.parquet"
        blob = bucket.blob(gcs_path)
        blob.upload_from_file(buf, content_type="application/octet-stream")

        print(f"Uploaded {len(df)} prescribing rows for {date_str}")
        return len(df)

    trigger_transform = TriggerDagRunOperator(
        task_id="trigger_transform_dag",
        trigger_dag_id="transform_dag",
        wait_for_completion=False,
    ) 

    # Refresh stations first, then ingest tasks in parallel, then trigger transform.
    # Practice locations live in a separate manual-trigger DAG (practice_locations_dag).
    stations = refresh_uk_stations()
    openaq = ingest_openaq_to_gcs()
    prescribing = ingest_prescribing_to_gcs()

    stations >> openaq
    [openaq, prescribing] >> trigger_transform


ingest_dag()