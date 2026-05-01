"""
Practice Locations DAG: Fetch GP practice locations from OpenPrescribing and upload to GCS.

Manual trigger only (schedule=None). GP practice locations change slowly, so this
is run ad-hoc when the reference data needs refreshing (roughly quarterly or when
OpenPrescribing publishes an updated list).

Writes to: gs://air-quality-and-respiratory-openaq-lake/raw/practice_locations/practice_locations.parquet
"""

from datetime import datetime

from airflow.decorators import dag, task

GCS_BUCKET = "air-quality-and-respiratory-openaq-lake"
OPENPRESCRIBING_BASE_URL = "https://openprescribing.net/api/1.0"


@dag(
    schedule=None,
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["ingest", "manual", "reference-data"],
    doc_md=__doc__,
)
def practice_locations_dag():

    @task
    def ingest_practice_locations_to_gcs():
        """Fetch all GP practice locations from OpenPrescribing API, save as parquet to GCS."""
        import io

        import pandas as pd
        from curl_cffi import requests
        from google.cloud import storage as gcs

        # Get all practice codes
        print("Fetching practice codes...")
        resp = requests.get(
            f"{OPENPRESCRIBING_BASE_URL}/org_code/",
            params={"org_type": "practice", "format": "json"},
            impersonate="chrome",
            timeout=120,
        )
        resp.raise_for_status()
        practices = resp.json()
        codes = [p["code"] for p in practices]
        print(f"  Found {len(codes)} practices")

        # Get locations in batches
        all_locations = []
        batch_size = 200
        for i in range(0, len(codes), batch_size):
            batch = codes[i : i + batch_size]
            resp = requests.get(
                f"{OPENPRESCRIBING_BASE_URL}/org_location/",
                params={"q": ",".join(batch), "format": "json"},
                impersonate="chrome",
                timeout=120,
            )
            resp.raise_for_status()
            for feature in resp.json().get("features", []):
                props = feature.get("properties", {})
                geometry = feature.get("geometry")
                coords = (
                    geometry["coordinates"]
                    if geometry and geometry.get("coordinates")
                    else [None, None]
                )
                all_locations.append(
                    {
                        "practice_code": props.get("code"),
                        "practice_name": props.get("name"),
                        "setting": props.get("setting"),
                        "lon": coords[0],
                        "lat": coords[1],
                    }
                )

            if (i // batch_size) % 10 == 0:
                print(f"  Fetched {min(i + batch_size, len(codes))}/{len(codes)}")

        df = pd.DataFrame(all_locations)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)

        gcs_client = gcs.Client()
        bucket = gcs_client.bucket(GCS_BUCKET)
        blob = bucket.blob("raw/practice_locations/practice_locations.parquet")
        blob.upload_from_file(buf, content_type="application/octet-stream")

        print(f"Uploaded {len(df)} practice locations")
        return len(df)

    ingest_practice_locations_to_gcs()


practice_locations_dag()
