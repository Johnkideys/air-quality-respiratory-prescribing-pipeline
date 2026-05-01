import io
import os
import time
import pandas as pd
from curl_cffi import requests
from google.cloud import storage as gcs

GCS_BUCKET = "air-quality-and-respiratory-openaq-lake"
OPENPRESCRIBING_BASE_URL = "https://openprescribing.net/api/1.0"
BNF_SECTIONS = {
    "0301": "Bronchodilators",
    "0302": "Corticosteroid inhalers (ICS)",
    "0303": "Cromoglicate and related",
    "060302": "Systemic corticosteroids",
}

def fetch_prescribing(year, month):
    date_str = f"{year}-{month:02d}-01"
    print(f"\nFetching {date_str}...")
    all_records = []

    for bnf_code, label in BNF_SECTIONS.items():
        resp = requests.get(
            f"{OPENPRESCRIBING_BASE_URL}/spending_by_org/",
            params={"org_type": "practice", "code": bnf_code, "date": date_str, "format": "json"},
            impersonate="chrome",
            timeout=120,
        )
        resp.raise_for_status()
        records = resp.json()
        for rec in records:
            rec["bnf_section"] = bnf_code
            rec["bnf_label"] = label
        all_records.extend(records)
        print(f"  {label}: {len(records)} rows")
        time.sleep(0.5)

    if not all_records:
        print(f"  No data for {date_str}")
        return

    df = pd.DataFrame(all_records)
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)

    gcs_client = gcs.Client()
    bucket = gcs_client.bucket(GCS_BUCKET)
    gcs_path = f"raw/prescribing/year={year}/month={month:02d}/prescribing.parquet"
    bucket.blob(gcs_path).upload_from_file(buf, content_type="application/octet-stream")
    print(f"  Uploaded {len(df)} rows to {gcs_path}")

# Run for all months
months = [
    (2025, 1), (2025, 2), (2025, 3), (2025, 4), (2025, 5), (2025, 6),
    (2025, 7), (2025, 8), (2025, 9), (2025, 10), (2025, 11), (2025, 12),
    (2026, 1), (2026, 2),
]

for year, month in months:
    fetch_prescribing(year, month)

print("\nDone")