"""
Discover all UK air quality monitoring locations in OpenAQ.
Saves a CSV of location IDs, names, coordinates, and sensor details
that you can use to drive your S3 bulk download.

Usage:
    export OPENAQ_API_KEY="your-key-here"
    python discover_uk_locations.py
"""

import os
import csv
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPENAQ_API_KEY")
BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY, "Accept": "application/json"}

# OpenAQ uses ISO 3166-1 alpha-2 codes. The UK country ID in OpenAQ
# needs to be looked up first - we'll do that automatically.
# Parameter IDs: 2 = PM2.5, 1 = PM10, 5 = NO2
PARAMS_OF_INTEREST = {2: "pm25", 1: "pm10", 5: "no2"}

OUTPUT_DIR = "openaq_data"


def get(endpoint, params=None):
    """Make an API request with rate-limit awareness."""
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, headers=HEADERS, params=params)

    remaining = resp.headers.get("x-ratelimit-remaining", "?")
    limit = resp.headers.get("x-ratelimit-limit", "?")
    print(f"  [rate limit: {remaining}/{limit} remaining]")

    # If we're getting close to the limit, slow down
    if remaining != "?" and int(remaining) <= 2:
        reset = int(resp.headers.get("x-ratelimit-reset", 60))
        print(f"  ⏳ Rate limit nearly hit. Waiting {reset + 1}s...")
        time.sleep(reset + 1)

    resp.raise_for_status()
    return resp.json()


def find_uk_country_id():
    """Look up the OpenAQ country ID for the United Kingdom."""
    print("🔍 Looking up UK country ID...")
    data = get("/countries", {"limit": 200})

    for country in data["results"]:
        code = country.get("code", "")
        name = country.get("name", "")
        if code == "GB" or "United Kingdom" in name:
            print(f"   Found: {name} (code={code}, id={country['id']})")
            return country["id"]
    return None


def fetch_all_uk_locations(country_id):
    """
    Fetch all UK locations that measure any of our target parameters.
    Handles pagination automatically.
    """
    all_locations = {}  # keyed by location ID to deduplicate

    for param_id, param_name in PARAMS_OF_INTEREST.items():
        print(f"\n📡 Fetching UK locations with {param_name} (param_id={param_id})...")
        page = 1

        while True:
            params = {
                "countries_id": country_id,
                "parameters_id": param_id,
                "limit": 1000,
                "page": page,
            }
            data = get("/locations", params)
            results = data.get("results", [])

            if not results:
                break

            for loc in results:
                loc_id = loc["id"]
                if loc_id not in all_locations:
                    all_locations[loc_id] = {
                        "location_id": loc_id,
                        "name": loc.get("name", ""),
                        "latitude": loc.get("coordinates", {}).get("latitude"),
                        "longitude": loc.get("coordinates", {}).get("longitude"),
                        "is_monitor": loc.get("isMonitor", False),
                        "is_mobile": loc.get("isMobile", False),
                        "sensors": {},
                    }

                # Record which sensors this location has for our parameters
                for sensor in loc.get("sensors", []):
                    s_param = sensor.get("parameter", {})
                    s_param_id = s_param.get("id")
                    if s_param_id in PARAMS_OF_INTEREST:
                        all_locations[loc_id]["sensors"][s_param_id] = {
                            "sensor_id": sensor["id"],
                            "parameter": PARAMS_OF_INTEREST[s_param_id],
                            "units": s_param.get("units", ""),
                        }

            found = data.get("meta", {}).get("found", 0)
            fetched_so_far = page * 1000
            print(f"   Page {page}: got {len(results)} locations (total found: {found})")

            if fetched_so_far >= found or len(results) < 1000:
                break
            page += 1
            time.sleep(0.5)

    return all_locations


def save_results(locations):
    """Save to both CSV (for pipeline use) and JSON (for full metadata)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- CSV: one row per location, flat format for easy use ---
    csv_path = f"{OUTPUT_DIR}/uk_locations.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "location_id", "name", "latitude", "longitude",
            "is_monitor", "is_mobile",
            "has_pm25", "pm25_sensor_id",
            "has_pm10", "pm10_sensor_id",
            "has_no2", "no2_sensor_id",
        ])

        for loc in locations.values():
            sensors = loc["sensors"]
            writer.writerow([
                loc["location_id"],
                loc["name"],
                loc["latitude"],
                loc["longitude"],
                loc["is_monitor"],
                loc["is_mobile"],
                2 in sensors,
                sensors.get(2, {}).get("sensor_id", ""),
                1 in sensors,
                sensors.get(1, {}).get("sensor_id", ""),
                5 in sensors,
                sensors.get(5, {}).get("sensor_id", ""),
            ])

    print(f"\n💾 CSV saved to: {csv_path}")

    # --- JSON: full metadata for reference ---
    json_path = f"{OUTPUT_DIR}/uk_locations.json"
    with open(json_path, "w") as f:
        json.dump(list(locations.values()), f, indent=2, default=str)
    print(f"💾 JSON saved to: {json_path}")

    return csv_path


def print_summary(locations):
    """Print a summary of what we found."""
    total = len(locations)
    monitors = sum(1 for l in locations.values() if l["is_monitor"])
    has_pm25 = sum(1 for l in locations.values() if 2 in l["sensors"])
    has_pm10 = sum(1 for l in locations.values() if 1 in l["sensors"])
    has_no2 = sum(1 for l in locations.values() if 5 in l["sensors"])

    print(f"\n{'='*60}")
    print(f"UK OPENAQ LOCATIONS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total locations found:     {total}")
    print(f"  Reference-grade monitors:  {monitors}")
    print(f"  With PM2.5 sensor:         {has_pm25}")
    print(f"  With PM10 sensor:          {has_pm10}")
    print(f"  With NO2 sensor:           {has_no2}")
    print()

    # Show a sample
    print("Sample locations (first 10):")
    print(f"  {'ID':<8} {'Name':<40} {'PM2.5':>5} {'PM10':>5} {'NO2':>5}")
    print(f"  {'-'*65}")
    for loc in list(locations.values())[:10]:
        s = loc["sensors"]
        print(
            f"  {loc['location_id']:<8} "
            f"{loc['name'][:39]:<40} "
            f"{'✓' if 2 in s else '':>5} "
            f"{'✓' if 1 in s else '':>5} "
            f"{'✓' if 5 in s else '':>5}"
        )

    print(f"\n  Use the location_id column from uk_locations.csv")
    print(f"  to download bulk data from the S3 bucket:")
    print(f"  s3://openaq-data-archive/records/csv.gz/locationid={{id}}/year={{yyyy}}/")


def main():
    if not API_KEY:
        print("❌ Set OPENAQ_API_KEY environment variable first")
        print("   export OPENAQ_API_KEY='your-key'")
        return

    # Step 1: Find UK country ID
    country_id = find_uk_country_id()
    if not country_id:
        print("❌ Could not find UK in OpenAQ countries list")
        return

    # Step 2: Fetch all UK locations with our target parameters
    locations = fetch_all_uk_locations(country_id)

    if not locations:
        print("❌ No locations found")
        return

    # Step 3: Save and summarise
    save_results(locations)
    print_summary(locations)


if __name__ == "__main__":
    main()