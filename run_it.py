"""IT-sector lead scraper: Eastern India, North-East and (optionally) big IT-hub states.

Source : OpenStreetMap (Overpass API) - free and legal to use.
Enrich : visits each company's OWN website for public email/phone (respects robots.txt).

Needs only these files in the same folder:  run_it.py, enricher.py, config.py, requirements.txt

STATE GROUPS
  east       West Bengal, Odisha, Bihar, Jharkhand (incl. Jamshedpur / Tatanagar)
  northeast  Assam, Sikkim, Tripura, Meghalaya, Manipur, Nagaland, Arunachal Pradesh, Mizoram
  central    Chhattisgarh
  hubs       Delhi, Haryana, Uttar Pradesh, Karnataka, Telangana, Maharashtra, Tamil Nadu,
             Gujarat, Kerala, Andhra Pradesh, Rajasthan, Madhya Pradesh, Uttarakhand
  all        every group above

EXAMPLES
  python run_it.py                                  # east + northeast + central (default)
  python run_it.py --states Jharkhand --no-enrich   # quick test, one state
  python run_it.py --group all                      # everything (aim for 680+)
  python run_it.py --group east,hubs --wide         # wider name search = more results
  python run_it.py --group all --no-enrich          # fastest (no email/phone crawl)
"""
import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

import config
import enricher

# ------------------------------------------------------------------ SETTINGS
TARGET = 690                   # goal; the script tells you at the end if you reached it
OUT_DIR = Path("output_it")
WORKERS = 8                    # parallel website visits (keep 8-10 or lower)

# "iso" = official state code used by OpenStreetMap, "name" = fallback name match.
STATES = {
    # ---- east
    "West Bengal":       {"iso": "IN-WB", "name": "West Bengal"},
    "Odisha":            {"iso": "IN-OD", "name": "Odisha|Orissa"},
    "Bihar":             {"iso": "IN-BR", "name": "Bihar"},
    "Jharkhand":         {"iso": "IN-JH", "name": "Jharkhand"},
    # ---- north-east
    "Assam":             {"iso": "IN-AS", "name": "Assam"},
    "Sikkim":            {"iso": "IN-SK", "name": "Sikkim"},
    "Tripura":           {"iso": "IN-TR", "name": "Tripura"},
    "Meghalaya":         {"iso": "IN-ML", "name": "Meghalaya"},
    "Manipur":           {"iso": "IN-MN", "name": "Manipur"},
    "Nagaland":          {"iso": "IN-NL", "name": "Nagaland"},
    "Arunachal Pradesh": {"iso": "IN-AR", "name": "Arunachal Pradesh"},
    "Mizoram":           {"iso": "IN-MZ", "name": "Mizoram"},
    # ---- central
    "Chhattisgarh":      {"iso": "IN-CT", "name": "Chhattisgarh|Chattisgarh"},
    # ---- big IT hubs
    "Delhi":             {"iso": "IN-DL", "name": "Delhi|National Capital Territory of Delhi"},
    "Haryana":           {"iso": "IN-HR", "name": "Haryana"},
    "Uttar Pradesh":     {"iso": "IN-UP", "name": "Uttar Pradesh"},
    "Karnataka":         {"iso": "IN-KA", "name": "Karnataka"},
    "Telangana":         {"iso": "IN-TG", "name": "Telangana"},
    "Maharashtra":       {"iso": "IN-MH", "name": "Maharashtra"},
    "Tamil Nadu":        {"iso": "IN-TN", "name": "Tamil Nadu"},
    "Gujarat":           {"iso": "IN-GJ", "name": "Gujarat"},
    "Kerala":            {"iso": "IN-KL", "name": "Kerala"},
    "Andhra Pradesh":    {"iso": "IN-AP", "name": "Andhra Pradesh"},
    "Rajasthan":         {"iso": "IN-RJ", "name": "Rajasthan"},
    "Madhya Pradesh":    {"iso": "IN-MP", "name": "Madhya Pradesh"},
    "Uttarakhand":       {"iso": "IN-UT", "name": "Uttarakhand|Uttaranchal"},
}

GROUPS = {
    "east": ["West Bengal", "Odisha", "Bihar", "Jharkhand"],
    "northeast": ["Assam", "Sikkim", "Tripura", "Meghalaya", "Manipur", "Nagaland",
                  "Arunachal Pradesh", "Mizoram"],
    "central": ["Chhattisgarh"],
    "hubs": ["Delhi", "Haryana", "Uttar Pradesh", "Karnataka", "Telangana", "Maharashtra",
             "Tamil Nadu", "Gujarat", "Kerala", "Andhra Pradesh", "Rajasthan",
             "Madhya Pradesh", "Uttarakhand"],
}
DEFAULT_GROUPS = "east,northeast,central"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Words that suggest an IT company in the business name (used with office/building tags)
IT_WORDS = (r"software|infotech|info ?tech|infosystem|infosoft|softech|technolog|technosoft|"
            r"it solution|it service|cyber|web ?(design|solution|tech|develop)|digital|cloud|"
            r"data ?(system|solution|centre|center)|computer|systems|networks|analytics|"
            r"app ?develop|\bit\b|\btech\b")

# Stricter words used by --wide (searches ALL named places, so keep it specific)
WIDE_WORDS = (r"software|infotech|info ?tech|infosystem|infosoft|softech|technosoft|"
              r"it solution|it service|cyber ?(tech|soft|solution)|web ?(design|solution|tech|develop)|"
              r"app ?develop|technologies")

# Names containing these are NOT software companies (schools, shops, banks, IT parks...)
EXCLUDE_RE = re.compile(
    r"institute|college|school|university|polytechnic|academy|coaching|training|classes|"
    r"hospital|clinic|bank|hotel|restaurant|pharma|studio|printing|photo|repair|showroom|"
    r"\bpark\b|market|complex|tower|mall|cinema|court|police|municipal|panchayat|post office",
    re.I)
# Place types that are clearly not IT offices (skipped unless tagged office=it)
NON_OFFICE_TAGS = ("amenity", "shop", "healthcare", "tourism", "leisure", "craft")

COLUMNS = ["name", "state", "city", "match", "address", "phone", "email", "website",
           "other_phones", "other_emails", "lat", "lon", "source"]


# ------------------------------------------------------------------ OVERPASS
def build_query(state_cfg, use_name_area, wide):
    if use_name_area:
        head = ('area["boundary"="administrative"]["admin_level"="4"]'
                f'["name"~"^({state_cfg["name"]})$"]->.a;')
    else:
        head = f'area["ISO3166-2"="{state_cfg["iso"]}"]->.a;'
    parts = [
        'nwr["office"="it"](area.a);',
        f'nwr["office"]["name"~"{IT_WORDS}",i](area.a);',
        f'nwr["building"~"office|commercial|industrial"]["name"~"{IT_WORDS}",i](area.a);',
    ]
    if wide:
        parts.append(f'nwr["name"~"{WIDE_WORDS}",i](area.a);')
    return "[out:json][timeout:300];" + head + "(" + "".join(parts) + ");out center tags;"


def overpass(query):
    """Returns list of elements, or None if every attempt failed."""
    for attempt in range(3):
        for url in OVERPASS_URLS:
            host = url.split("/")[2]
            try:
                r = requests.post(url, data={"data": query}, timeout=330,
                                  headers={"User-Agent": config.USER_AGENT})
                if r.status_code == 200:
                    return r.json().get("elements", [])
                print(f"   {host}: status {r.status_code} (busy), trying next...")
            except (requests.RequestException, ValueError) as e:
                print(f"   {host}: {type(e).__name__}, trying next...")
        wait = 10 * (attempt + 1)
        print(f"   waiting {wait}s before retry {attempt + 2}/3...")
        time.sleep(wait)
    return None


# ------------------------------------------------------------------ PARSING
def first(tags, *keys):
    for k in keys:
        if tags.get(k):
            return tags[k].strip()
    return ""


def build_address(t):
    parts = [t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:suburb"),
             t.get("addr:city"), t.get("addr:state"), t.get("addr:postcode")]
    return ", ".join(p for p in parts if p)


def tidy_phone(raw):
    """'03326478988;26698989' -> '033-26478988, 26698989'; mobiles -> '+91 98300 12345'."""
    out = []
    for part in re.split(r"[;,/]", raw or ""):
        digits = re.sub(r"\D", "", part)
        if not digits:
            continue
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if len(digits) == 10 and digits[0] in "6789":
            out.append(f"+91 {digits[:5]} {digits[5:]}")
        elif len(digits) == 11 and digits.startswith("0"):
            out.append(f"{digits[:3]}-{digits[3:]}")
        else:
            out.append(part.strip())
    return ", ".join(out)


def parse(elements, state):
    rows = []
    for el in elements:
        t = el.get("tags", {})
        name = (t.get("name") or "").strip()
        if not name:
            continue
        tagged_it = t.get("office") == "it"
        if not tagged_it:
            if EXCLUDE_RE.search(name):
                continue
            if any(t.get(k) for k in NON_OFFICE_TAGS):
                continue
        if tagged_it:
            match = "tagged_IT"
        elif t.get("office") or t.get("building"):
            match = "name_match"
        else:
            match = "wide_name"
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        rows.append({
            "name": name,
            "state": state,
            "city": t.get("addr:city", ""),
            "match": match,
            "address": build_address(t),
            "phone": tidy_phone(first(t, "phone", "contact:phone", "mobile", "contact:mobile")),
            "email": first(t, "email", "contact:email").lower(),
            "website": first(t, "website", "contact:website", "url"),
            "other_phones": "", "other_emails": "",
            "lat": lat, "lon": lon,
            "source": "openstreetmap",
        })
    return rows


def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        lat = round(float(r["lat"]), 3) if r["lat"] not in (None, "") else None
        lon = round(float(r["lon"]), 3) if r["lon"] not in (None, "") else None
        key = (str(r["name"]).lower().strip(), lat, lon)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ------------------------------------------------------------------ ENRICH
def enrich_rows(rows, workers):
    targets = [r for r in rows if r["website"]]
    print(f"\nVisiting {len(targets)} company websites for emails/phones "
          f"(polite crawl, can take a while)...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(enricher.enrich_site, r["website"]): r for r in targets}
        for f in tqdm(as_completed(futures), total=len(futures)):
            r = futures[f]
            try:
                emails, phones = f.result()
            except Exception:
                continue
            if emails:
                r["email"] = r["email"] or emails[0]
                r["other_emails"] = ", ".join(e for e in emails if e != r["email"])
            if phones:
                known = re.sub(r"\D", "", r["phone"])[-10:]
                extra = [p for p in phones if p[-10:] != known]
                if not r["phone"]:
                    r["phone"], extra = phones[0], phones[1:]
                r["other_phones"] = ", ".join(extra)


# ------------------------------------------------------------------ MAIN
def resolve_states(args):
    if args.states:
        wanted = [s.strip() for s in args.states.split(",") if s.strip()]
    else:
        names = [g.strip().lower() for g in args.group.split(",") if g.strip()]
        if "all" in names:
            names = list(GROUPS)
        wanted = []
        for g in names:
            if g not in GROUPS:
                raise SystemExit(f"Unknown group '{g}'. Options: {list(GROUPS)} or 'all'")
            wanted += [s for s in GROUPS[g] if s not in wanted]
    bad = [s for s in wanted if s not in STATES]
    if bad:
        raise SystemExit(f"Unknown state(s): {bad}. Options: {list(STATES)}")
    return wanted


def main():
    ap = argparse.ArgumentParser(description="IT-sector lead scraper (India)")
    ap.add_argument("--group", default=DEFAULT_GROUPS,
                    help="east, northeast, central, hubs, all (comma list). Default: "
                         + DEFAULT_GROUPS)
    ap.add_argument("--states", default="",
                    help='exact state names, e.g. --states "Odisha,Bihar" (overrides --group)')
    ap.add_argument("--wide", action="store_true",
                    help="also search ALL named places for IT words (more results, slower)")
    ap.add_argument("--no-enrich", action="store_true", help="skip website visits (faster)")
    args = ap.parse_args()

    wanted = resolve_states(args)
    mode = "wide" if args.wide else "std"
    print(f"States to scrape ({len(wanted)}): {', '.join(wanted)}  [mode: {mode}]")

    OUT_DIR.mkdir(exist_ok=True)
    frames = []

    for state in wanted:
        tag = "_wide" if args.wide else ""
        raw_file = OUT_DIR / f"raw_{state.replace(' ', '_')}{tag}.csv"
        if raw_file.exists():
            print(f"[{state}] already saved, skipping download ({raw_file.name})")
            frames.append(pd.read_csv(raw_file, keep_default_na=False))
            continue

        print(f"\n=== {state} ===")
        cfg = STATES[state]
        elements = overpass(build_query(cfg, False, args.wide))
        if not elements:                      # state code not found or server problem
            print("   no result with state code, trying by state name...")
            elements = overpass(build_query(cfg, True, args.wide))
        if elements is None:
            print(f"!! {state}: server busy. Run the same command again in 10 minutes.")
            continue

        rows = dedupe(parse(elements, state))
        print(f"   found {len(rows)} IT companies in {state}")
        if rows:
            part = pd.DataFrame(rows).reindex(columns=COLUMNS).fillna("")
            part.to_csv(raw_file, index=False, encoding="utf-8-sig")
            frames.append(part)
        time.sleep(10)                        # be polite to the free server

    if not frames:
        raise SystemExit("\nNo data collected. Check internet / run again later.")

    df = pd.concat(frames, ignore_index=True)
    rows = dedupe(df.to_dict("records"))

    if not args.no_enrich:
        enrich_rows(rows, WORKERS)

    final = pd.DataFrame(rows).reindex(columns=COLUMNS).fillna("")
    for col in ("phone", "other_phones"):
        final[col] = final[col].astype(str).map(tidy_phone)
    final = final.sort_values(["state", "match", "name"]).reset_index(drop=True)

    final.to_csv(OUT_DIR / "IT_leads.csv", index=False, encoding="utf-8-sig")
    final.to_excel(OUT_DIR / "IT_leads.xlsx", index=False)
    useful = final[(final.phone != "") | (final.email != "")]
    useful.to_excel(OUT_DIR / "IT_with_contacts.xlsx", index=False)

    print("\n" + "=" * 54)
    print(f"TOTAL IT companies : {len(final)}   (target {TARGET})")
    print(final.state.value_counts().to_string())
    print(f"With phone   : {(final.phone != '').sum()}")
    print(f"With email   : {(final.email != '').sum()}")
    print(f"With website : {(final.website != '').sum()}")
    print(f"With phone or email: {len(useful)}  -> {OUT_DIR}/IT_with_contacts.xlsx")
    print(f"\nFiles saved in the '{OUT_DIR}' folder (IT_leads.xlsx = everything).")
    if len(final) < TARGET:
        print(f"\nBelow {TARGET}. To get more: add '--wide', or add '--group all' "
              f"to include the big IT-hub states.")
    else:
        print(f"\nTarget of {TARGET}+ reached.")


if __name__ == "__main__":
    main()
