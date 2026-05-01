"""
Download all GP practice locations from OpenPrescribing.net API.
Saves as parquet — one row per practice with lat, lon, name, code.

Prerequisites:
    pip install duckdb curl_cffi pandas

Usage:
    python download_practice_locations.py
"""

from pathlib import Path

import duckdb
import pandas as pd
from curl_cffi import requests


BASE_URL = "https://openprescribing.net/api/1.0"
OUTPUT_DIR = Path("output_prescribing")


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Step 1: Get all practice codes and names
    print("Fetching all practice codes...")
    resp = requests.get(
        f"{BASE_URL}/org_code/",
        params={"org_type": "practice", "format": "json"},
        impersonate="chrome",
        timeout=120,
    )
    resp.raise_for_status()
    practices = resp.json()
    print(f"  Practices found: {len(practices):,}")

    # Step 2: Get locations for all practices (batch query)
    # The org_location endpoint accepts comma-separated codes
    # Process in batches to avoid URL length limits
    print("Fetching practice locations...")
    codes = [p["code"] for p in practices]

    all_locations = []
    batch_size = 200

    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        batch_str = ",".join(batch)

        resp = requests.get(
            f"{BASE_URL}/org_location/",
            params={"q": batch_str, "format": "json"},
            impersonate="chrome",
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # Response is GeoJSON FeatureCollection
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geometry = feature.get("geometry")
            if geometry and geometry.get("coordinates"):
                coords = geometry["coordinates"]
                lon, lat = coords[0], coords[1]
            else:
                lon, lat = None, None
            all_locations.append({
                "practice_code": props.get("code"),
                "practice_name": props.get("name"),
                "setting": props.get("setting"),
                "lon": lon,
                "lat": lat,
            })

        print(f"  Fetched {min(i + batch_size, len(codes)):,} / {len(codes):,}")

    print(f"\n  Practices with locations: {len(all_locations):,}")

    # Save as parquet
    df = pd.DataFrame(all_locations)
    parquet_path = OUTPUT_DIR / "practice_locations.parquet"

    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE practices AS SELECT * FROM df")
        con.execute(f"COPY practices TO '{parquet_path}' (FORMAT PARQUET)")

        row_count = con.execute("SELECT COUNT(*) FROM practices").fetchone()[0]
        print(f"\n  Parquet saved: {parquet_path}")
        print(f"  Total rows:    {row_count:,}")

        # Sample
        print(f"\n  Sample:")
        sample = con.execute("SELECT * FROM practices LIMIT 5").fetchdf()
        print(sample.to_string(index=False))

        # Quick stats
        stats = con.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(lat) AS with_location,
                COUNT(*) - COUNT(lat) AS missing_location
            FROM practices
        """).fetchdf()
        print(f"\n  {stats.to_string(index=False)}")

    finally:
        con.close()

    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()