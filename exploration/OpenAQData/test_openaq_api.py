"""
OpenAQ API v3 - Simple exploration script
Set your API key: export OPENAQ_API_KEY="your-key-here"
"""

import os
import json
import requests
from dotenv import load_dotenv

from pprint import pprint

load_dotenv() 

API_KEY = os.environ.get("OPENAQ_API_KEY")

BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY, "Accept": "application/json"}

LEEDS = {"lat": 53.8008, "lon": -1.5491}


def get(endpoint, params=None):
    """Simple wrapper - prints the raw JSON so you can inspect it."""
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()

    request_left = response.headers.get("x-ratelimit-limit")
    print(f"Number of requests left within the free tier limit: {request_left}")

    return response.json()

### What gasses are measured in the UK, below prints the list
#print("\n=== ALL UK STATIONS ===")
# United Kingdom variables
gb_id = 79
code = 'GB'
name = 'United Kingdom'
result = get("/countries/79")
pprint(result['results'][0]['parameters'])

### How many stations are there (or sensors)
# result = get("/locations", {"bbox": "-8.2,49.9,1.8,60.9", "limit": 1})
# total_stations = result["meta"]["found"]
# print(f"Total UK stations: {total_stations}")
# pprint(result)

# # --- 1. Find monitoring stations near Leeds ---
# print("\n=== LOCATIONS near Leeds ===")
# locations = get("/locations", {
#     "coordinates": f"{LEEDS['lat']},{LEEDS['lon']}",
#     "radius": 20000,   # 20km
#     "limit": 5,
# })
# print(json.dumps(locations, indent=2))

# # --- 2. Inspect sensors at the first location ---
# if locations.get("results"):
#     first_location = locations["results"][0]
#     loc_id = first_location["id"]
#     loc_name = first_location.get("name", "?")

#     print(f"\n=== SENSORS at location {loc_id} ({loc_name}) ===")
#     sensors = get(f"/locations/{loc_id}/sensors")
#     print(json.dumps(sensors, indent=2))

#     # --- 3. Get daily data for the first sensor ---
#     if sensors.get("results"):
#         first_sensor_id = sensors["results"][0]["id"]

#         print(f"\n=== DAILY MEASUREMENTS for sensor {first_sensor_id} ===")
#         measurements = get(f"/sensors/{first_sensor_id}/days", {
#             "date_from": "2024-01-01",
#             "date_to": "2024-01-07",  # just one week so it's not huge
#             "limit": 10,
#         })
#         print(json.dumps(measurements, indent=2))



