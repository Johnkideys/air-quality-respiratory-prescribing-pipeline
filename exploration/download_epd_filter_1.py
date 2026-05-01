"""
Download NHS English Prescribing Dataset (EPD) from NHSBSA Open Data Portal.
Pulls all respiratory + oral steroid BNF sections via CKAN API, saves as parquet.
Precise filtering to individual chemicals happens downstream in dbt.

Prerequisites:
    pip install duckdb requests pandas

Usage:
    uv run download_epd_filter_1.py --year 2024 --month 1
    uv run download_epd_filter_1.py --year 2024 --month 1 --months 12
"""

import argparse
import json
import time
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CKAN_BASE = "https://opendata.nhsbsa.net/api/3/action/datastore_search"

# Broad BNF sections — pull everything, filter to specific chemicals in dbt
BNF_PREFIXES = {
    "0301":   "Bronchodilators (SABA, ipratropium, etc)",
    "0302":   "Corticosteroid inhalers (ICS)",
    "0303":   "Cromoglicate and related",
    "060302": "Systemic corticosteroids (prednisolone)",
}

PAGE_SIZE = 32000

KEEP_FIELDS = ",".join([
    "YEAR_MONTH", "REGIONAL_OFFICE_NAME", "REGIONAL_OFFICE_CODE",
    "ICB_NAME", "ICB_CODE", "PCO_NAME", "PCO_CODE",
    "PRACTICE_NAME", "PRACTICE_CODE", "POSTCODE",
    "BNF_CHEMICAL_SUBSTANCE", "CHEMICAL_SUBSTANCE_BNF_DESCR",
    "BNF_CODE", "BNF_DESCRIPTION", "BNF_CHAPTER_PLUS_CODE",
    "QUANTITY", "ITEMS", "TOTAL_QUANTITY", "ADQUSAGE",
    "NIC", "ACTUAL_COST",
])

OUTPUT_DIR = Path("output_epd")


# ---------------------------------------------------------------------------
# API helper
# ---------------------------------------------------------------------------

def ckan_search(resource_id: str, q_dict: dict, offset: int = 0) -> dict:
    q_json = json.dumps(q_dict)
    url = (
        f"{CKAN_BASE}"
        f"?resource_id={resource_id}"
        f"&limit={PAGE_SIZE}"
        f"&offset={offset}"
        f"&fields={KEEP_FIELDS}"
        f"&q={urllib.request.quote(q_json)}"
    )
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError(f"CKAN API error: {data}")
    return data["result"]


# ---------------------------------------------------------------------------
# Query by BNF_CODE prefix with pagination
# ---------------------------------------------------------------------------

def query_by_prefix(resource_id: str, prefix: str) -> list[dict]:
    all_records = []
    offset = 0

    while True:
        result = ckan_search(resource_id, {"BNF_CODE": prefix}, offset)
        records = result.get("records", [])

        # q is full-text search so verify prefix match
        verified = [r for r in records if r.get("BNF_CODE", "").startswith(prefix)]
        all_records.extend(verified)

        if len(records) < PAGE_SIZE:
            break

        offset += PAGE_SIZE
        print(f"    Paginating... {len(all_records):,} rows so far")
        time.sleep(0.5)

    return all_records


# ---------------------------------------------------------------------------
# Fetch, save as parquet
# ---------------------------------------------------------------------------

def fetch_and_save(year: int, month: int):
    resource_id = f"EPD_{year}{month:02d}"
    print(f"  Resource: {resource_id}")

    all_records = []

    for prefix, label in BNF_PREFIXES.items():
        print(f"\n  Querying: {label} (BNF_CODE LIKE {prefix}%)")
        records = query_by_prefix(resource_id, prefix)
        print(f"    Rows: {len(records):,}")
        all_records.extend(records)

    if not all_records:
        print(f"\n  ⚠️  No records found for {year}-{month:02d}")
        return None

    # Save as parquet
    output_path = OUTPUT_DIR / f"year={year}" / f"month={month:02d}"
    output_path.mkdir(parents=True, exist_ok=True)
    parquet_path = output_path / f"epd_{year}{month:02d}_respiratory.parquet"

    df = pd.DataFrame(all_records)
    for col in ["_id", "_full_text", "rank"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE epd AS SELECT * FROM df")
        con.execute(f"COPY epd TO '{parquet_path}' (FORMAT PARQUET)")

        row_count = con.execute("SELECT COUNT(*) FROM epd").fetchone()[0]
        print(f"\n  Parquet saved: {parquet_path}")
        print(f"  Rows:          {row_count:,}")

        # Breakdown
        print(f"\n  Rows by medication:")
        breakdown = con.execute("""
            SELECT
                "CHEMICAL_SUBSTANCE_BNF_DESCR" AS medication,
                COUNT(*) AS practices,
                SUM(CAST("ITEMS" AS INTEGER)) AS total_items
            FROM epd
            GROUP BY 1
            ORDER BY total_items DESC
            LIMIT 15
        """).fetchdf()
        print(breakdown.to_string(index=False))

    finally:
        con.close()

    return parquet_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Download EPD respiratory data")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--months", type=int, default=1)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    year, month = args.year, args.month

    for i in range(args.months):
        print(f"\n{'='*60}")
        print(f"Processing EPD {year}-{month:02d}")
        print(f"{'='*60}")

        try:
            fetch_and_save(year, month)
            print(f"\n  ✅ Done: {year}-{month:02d}")
        except Exception as e:
            print(f"\n  ❌ Error: {e}")

        month += 1
        if month > 12:
            month = 1
            year += 1
        if i < args.months - 1:
            time.sleep(2)

    print(f"\n{'='*60}")
    print(f"All done! Files in: {OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()