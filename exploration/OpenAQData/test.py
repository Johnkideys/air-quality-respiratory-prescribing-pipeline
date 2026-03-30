"""
OpenAQ v3 - Monthly PM2.5 from a single UK sensor (last 3 months)
"""

import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

API_KEY = os.environ.get("OPENAQ_API_KEY")
BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY, "Accept": "application/json"}

PM25_PARAM_ID = 2
date_from = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT00:00:00Z")
date_to = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")


def get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, headers=HEADERS, params=params)

    request_left = resp.headers.get("x-ratelimit-limit")
    print(f"Number of requests left within the free tier limit: {request_left}")

    resp.raise_for_status()
    return resp.json()


# --- 1. Grab a UK PM2.5 location near Leeds ---
result = get("/locations", {
    "coordinates": "53.8008,-1.5491",  # Leeds
    "radius": 15000,
    "parameters_id": PM25_PARAM_ID,
    "limit": 2,
})

loc = result["results"][0]
#print(loc)
print(f"Location: {loc['name']} (ID: {loc['id']})")
print(f"Coords:   {loc['coordinates']['latitude']}, {loc['coordinates']['longitude']}")

# --- 2. Find the PM2.5 sensor ---
sensor = next(s for s in loc["sensors"] if s["parameter"]["id"] == PM25_PARAM_ID)
print(f"Sensor:   {sensor['id']} ({sensor['name']})")

# --- 2. Get daily averages (this endpoint is reliable) ---
data = get(f"/sensors/{sensor['id']}/days", {
    "date_from": date_from,
    "date_to": date_to,
    "limit": 100,
})

# Show raw response first so we can see what's coming back
print(f"\nResults found: {data['meta']['found']}")

pprint(data)

# # --- 4. Peek at the raw response if you want to see the full shape ---
# # pprint(data["results"][0])