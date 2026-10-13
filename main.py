"""Lead scraper for Kolkata / West Bengal.

Examples:
  python main.py --region kolkata --categories restaurant,hotel,gym --enrich
  python main.py --region kolkata --radius 5000 --categories clinic,dentist --enrich
  python main.py --region west_bengal --categories school,hotel --enrich
  python main.py --source google --region kolkata --categories restaurant --enrich
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
from tqdm import tqdm

import config
import enricher
import google_source
import osm_source

COLUMNS = ["name", "category", "address", "phone", "email", "website",
           "other_phones", "other_emails", "maps_url", "lat", "lon", "source"]


def collect(args):
    region = config.REGIONS[args.region]
    cats = list(config.CATEGORIES) if args.categories == "all" else args.categories.split(",")
    rows = []
    for c in cats:
        if c not in config.CATEGORIES:
            print(f"Unknown category '{c}'. Options: {', '.join(config.CATEGORIES)}")
            continue
        osm_tag, phrase = config.CATEGORIES[c]
        if args.source in ("osm", "both"):
            got = osm_source.fetch(c, osm_tag, region, args.radius, region["center"])
            print(f"[osm] {c}: {len(got)}")
            rows += got
        if args.source in ("google", "both"):
            for area in region["areas"]:
                got = google_source.fetch(c, phrase, area, region["center"], args.radius or 25000)
                print(f"[google] {c} / {area}: {len(got)}")
                rows += got
    return rows


def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        key = (r["name"].lower().strip(), "".join(ch for ch in r["phone"] if ch.isdigit())[-10:] or r["website"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def enrich_all(rows, workers):
    targets = [r for r in rows if r["website"]]
    print(f"Visiting {len(targets)} websites for emails/phones...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(enricher.enrich_site, r["website"]): r for r in targets}
        for f in tqdm(as_completed(futures), total=len(futures)):
            r = futures[f]
            emails, phones = f.result()
            if emails:
                r["email"] = r["email"] or emails[0]
                r["other_emails"] = ", ".join(e for e in emails if e != r["email"])
            if phones:
                known = "".join(ch for ch in r["phone"] if ch.isdigit())[-10:]
                extra = [p for p in phones if p[-10:] != known]
                if not r["phone"]:
                    r["phone"], extra = phones[0], phones[1:]
                r["other_phones"] = ", ".join(extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", choices=config.REGIONS, default="kolkata")
    ap.add_argument("--categories", default="restaurant", help="comma list or 'all'")
    ap.add_argument("--source", choices=["osm", "google", "both"], default="osm")
    ap.add_argument("--radius", type=int, default=None, help="metres around region centre (optional)")
    ap.add_argument("--enrich", action="store_true", help="crawl business websites for emails/phones")
    ap.add_argument("--workers", type=int, default=config.WORKERS)
    ap.add_argument("--out", default=None, help="output file name without extension")
    args = ap.parse_args()

    rows = dedupe(collect(args))
    for r in rows:
        r.setdefault("other_phones", "")
        r.setdefault("other_emails", "")
    if args.enrich:
        enrich_all(rows, args.workers)

    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    out = args.out or f"leads_{args.region}_{datetime.now():%Y%m%d_%H%M}"
    df.to_csv(out + ".csv", index=False, encoding="utf-8-sig")
    df.to_excel(out + ".xlsx", index=False)
    print(f"\nSaved {len(df)} leads -> {out}.csv / {out}.xlsx")
    print(f"With phone: {(df.phone != '').sum()} | With email: {(df.email != '').sum()} | With website: {(df.website != '').sum()}")


if __name__ == "__main__":
    main()
