"""
OpenPrescribing API - Explore salbutamol prescribing for Yorkshire region.

Steps:
  1. Find all Sub-ICB codes within Yorkshire ICBs
  2. Peek at salbutamol data for one Sub-ICB (Leeds) to see the structure
"""

import json
from curl_cffi import requests

BASE_URL = "https://openprescribing.net/api/1.0"

# BNF code for salbutamol (all inhaler presentations)
SALBUTAMOL_CODE = "0301011R0"


def get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    r = requests.get(url, params=params, impersonate="chrome")
    r.raise_for_status()
    return r.json()


# --- Step 1: Find all Sub-ICB codes for Yorkshire ---
# Search by name terms — the `org` param doesn't filter by parent ICB on this endpoint
print("=== Yorkshire Sub-ICB codes ===")
yorkshire_sub_icbs = []
seen_ids = set()

for term in ["West Yorkshire", "South Yorkshire", "North Yorkshire", "Humber"]:
    results = get("/org_code/", {"q": term, "org_type": "CCG", "format": "json"})
    for org in results:
        if org["id"] not in seen_ids:
            seen_ids.add(org["id"])
            yorkshire_sub_icbs.append(org)
            print(f"  {org['id']:>5}  {org['name']}")

print(f"\nTotal Yorkshire Sub-ICBs found: {len(yorkshire_sub_icbs)}")


# --- Step 2: Peek at salbutamol data for Leeds Sub-ICB (15F) ---
# Using one Sub-ICB to check the structure before querying all of Yorkshire
print("\n=== Salbutamol data peek: Leeds Sub-ICB (15F), 2024 ===")

all_data = get("/spending_by_org/", {
    "org_type": "practice",
    "code": SALBUTAMOL_CODE,
    "org": "15F",       # Leeds Sub-ICB — one area as a sample
    "format": "json",
})

data_2024 = [row for row in all_data if row["date"].startswith("2024")]

print(f"Total rows returned (all years): {len(all_data)}")
print(f"Filtered to 2024:                {len(data_2024)}")
print(f"\nColumns available: {list(data_2024[0].keys()) if data_2024 else 'no data'}")
print(f"\nSample (first 3 rows):")
print(json.dumps(data_2024[:3], indent=2))
