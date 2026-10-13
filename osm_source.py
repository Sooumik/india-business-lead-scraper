"""Free source: OpenStreetMap via the Overpass API (legal, no key needed)."""
import time
import requests
from config import USER_AGENT

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def build_query(tag, region, radius_m=None, center=None):
    key, val = tag.split("=", 1)
    sel = f'["{key}"]' if val == "*" else f'["{key}"="{val}"]'
    head = ""
    if radius_m:
        c = center or region["center"]
        scope = f"(around:{int(radius_m)},{c[0]},{c[1]})"
    elif "iso" in region:
        head = f'area["ISO3166-2"="{region["iso"]}"]->.a;'
        scope = "(area.a)"
    else:
        s, w, n, e = region["bbox"]
        scope = f"({s},{w},{n},{e})"
    return f"[out:json][timeout:180];{head}nwr{sel}{scope};out center tags;"


def _first(tags, *keys):
    for k in keys:
        if tags.get(k):
            return tags[k].strip()
    return ""


def _address(t):
    parts = [t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:suburb"),
             t.get("addr:city"), t.get("addr:state"), t.get("addr:postcode")]
    return ", ".join(p for p in parts if p)


def fetch(category, tag, region, radius_m=None, center=None):
    query = build_query(tag, region, radius_m, center)
    for attempt in range(3):
        for url in OVERPASS_URLS:
            try:
                r = requests.post(url, data={"data": query}, timeout=240,
                                  headers={"User-Agent": USER_AGENT})
                if r.status_code == 200:
                    return _parse(r.json().get("elements", []), category)
            except requests.RequestException:
                pass
        time.sleep(10 * (attempt + 1))
    print(f"[osm] giving up on {category}")
    return []


def _parse(elements, category):
    rows = []
    for el in elements:
        t = el.get("tags", {})
        if not t.get("name"):
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        rows.append({
            "name": t["name"],
            "category": category,
            "address": _address(t),
            "phone": _first(t, "phone", "contact:phone", "mobile", "contact:mobile"),
            "email": _first(t, "email", "contact:email"),
            "website": _first(t, "website", "contact:website", "url"),
            "lat": lat, "lon": lon,
            "maps_url": "",
            "source": "openstreetmap",
        })
    return rows
