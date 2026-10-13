"""Optional, richer source: official Google Places API (New). Needs an API key.
Set it with:  export GOOGLE_API_KEY="..."   (Windows: set GOOGLE_API_KEY=...)
Enable 'Places API (New)' in Google Cloud. Google gives a monthly free credit; check pricing.
"""
import os
import time
import requests

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ("places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
          "places.internationalPhoneNumber,places.websiteUri,places.googleMapsUri,"
          "places.location,nextPageToken")


def fetch(category, phrase, area, center=None, radius_m=None):
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("Set GOOGLE_API_KEY environment variable to use --source google")
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"}
    body = {"textQuery": f"{phrase} in {area}, West Bengal, India", "pageSize": 20}
    if center and radius_m:
        body["locationBias"] = {"circle": {
            "center": {"latitude": center[0], "longitude": center[1]},
            "radius": float(min(radius_m, 50000))}}
    rows = []
    for _ in range(3):  # API returns max ~60 results per query (3 pages)
        r = requests.post(URL, json=body, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"[google] {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        for p in data.get("places", []):
            loc = p.get("location", {})
            rows.append({
                "name": p.get("displayName", {}).get("text", ""),
                "category": category,
                "address": p.get("formattedAddress", ""),
                "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber", ""),
                "email": "",
                "website": p.get("websiteUri", ""),
                "lat": loc.get("latitude"), "lon": loc.get("longitude"),
                "maps_url": p.get("googleMapsUri", ""),
                "source": "google_places",
            })
        token = data.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
        time.sleep(2)
    return rows
