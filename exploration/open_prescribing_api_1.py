"""
Download respiratory prescribing data from OpenPrescribing.net API.
Practice-level, monthly, all of England.

Loops through months one at a time (API requires a date parameter).
Precise filtering to individual chemicals happens downstream in dbt.

Prerequisites:
    pip install duckdb curl_cffi pandas

Usage:
    # Last 2 year
    uv run open_prescribing_api_1.py --from 2024-01 --to 2026-01

    # Last 5 years
    uv run open_prescribing_api_1.py --from 2020-01 --to 2025-01

    # Single month test
    uv run open_prescribing_api_1.py --from 2024-01 --to 2024-01
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
from curl_cffi import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://openprescribing.net/api/1.0"

BNF_SECTIONS = {
    "0301":   "Bronchodilators (salbutamol, ipratropium, terbutaline)",
    "0302":   "Corticosteroid inhalers (ICS)",
    "0303":   "Cromoglicate and related",
    "060302": "Systemic corticosteroids (prednisolone)",
}

OUTPUT_DIR = Path("output_prescribing")


# ---------------------------------------------------------------------------
# Generate list of month dates between from and to
# ---------------------------------------------------------------------------

def generate_months(from_str: str, to_str: str) -> list[str]:
    """
    Generate list of first-of-month dates from 'YYYY-MM' to 'YYYY-MM' inclusive.
    Returns dates as 'YYYY-MM-01' strings (API format).
    """
    start = datetime.strptime(from_str, "%Y-%m")
    end = datetime.strptime(to_str, "%Y-%m")

    months = []
    current = start
    while current <= end:
        months.append(current.strftime("%Y-%m-01"))
        # Advance to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months


# ---------------------------------------------------------------------------
# Fetch one BNF section for one month
# ---------------------------------------------------------------------------

def fetch_section_month(bnf_code: str, date: str) -> list[dict]:
    """
    Fetch spending by practice for a BNF section on a single date.
    Returns list of dicts with: row_id, row_name, date, actual_cost, items, quantity
    """
    url = f"{BASE_URL}/spending_by_org/"
    params = {
        "org_type": "practice",
        "code": bnf_code,
        "date": date,
        "format": "json",
    }

    resp = requests.get(url, params=params, timeout=120, impersonate="chrome")
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Download OpenPrescribing respiratory data")
    parser.add_argument("--from", dest="from_date", required=True,
                        help="Start month YYYY-MM (e.g. 2024-01)")
    parser.add_argument("--to", dest="to_date", required=True,
                        help="End month YYYY-MM inclusive (e.g. 2025-01)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    months = generate_months(args.from_date, args.to_date)
    print(f"Months to fetch: {len(months)} ({months[0]} to {months[-1]})")

    all_records = []

    for month in months:
        print(f"\n  === {month} ===")

        for bnf_code, label in BNF_SECTIONS.items():
            print(f"    {label} ({bnf_code})...", end=" ")

            try:
                records = fetch_section_month(bnf_code, month)
                # Tag each record with the BNF section
                for rec in records:
                    rec["bnf_section"] = bnf_code
                    rec["bnf_label"] = label
                all_records.extend(records)
                print(f"{len(records):,} rows")
            except Exception as e:
                print(f"ERROR: {e}")

            time.sleep(0.5)  # Be polite

    if not all_records:
        print("\nNo data returned.")
        return

    # Convert to DataFrame
    combined = pd.DataFrame(all_records)
    print(f"\n{'='*60}")
    print(f"Combined rows: {combined.shape[0]:,}")
    print(f"Columns: {list(combined.columns)}")
    print(f"Date range: {combined['date'].min()} to {combined['date'].max()}")

    # Build filename from the dates requested
    from_tag = args.from_date.replace("-", "")   # "2024-01" → "202401"
    to_tag = args.to_date.replace("-", "")
    parquet_path = OUTPUT_DIR / f"prescribing_respiratory_{from_tag}_{to_tag}.parquet"

    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE rx AS SELECT * FROM combined")
        con.execute(f"COPY rx TO '{parquet_path}' (FORMAT PARQUET)")

        row_count = con.execute("SELECT COUNT(*) FROM rx").fetchone()[0]
        print(f"\nParquet saved: {parquet_path}")
        print(f"Total rows:    {row_count:,}")

        # Summary
        print(f"\nRows by BNF section:")
        breakdown = con.execute("""
            SELECT
                bnf_label,
                COUNT(*) AS rows,
                COUNT(DISTINCT row_id) AS practices,
                COUNT(DISTINCT date) AS months,
                SUM(items) AS total_items,
                ROUND(SUM(actual_cost), 2) AS total_cost
            FROM rx
            GROUP BY 1
            ORDER BY total_items DESC
        """).fetchdf()
        print(breakdown.to_string(index=False))

        # Sample
        print(f"\nSample (first 5 rows):")
        sample = con.execute("SELECT * FROM rx LIMIT 5").fetchdf()
        print(sample.to_string(index=False))

    finally:
        con.close()

    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()