"""Clean the IT leads file into ONE tidy Excel workbook.

Usage (in the VS Code terminal, same folder as run_it.py):
    python clean_leads.py                          # reads output_it/IT_leads.xlsx (or .csv)
    python clean_leads.py path/to/some_file.csv    # or give a file

Output: output_it/IT_leads_CLEAN.xlsx  with sheets
    Clean Leads   - companies with a valid phone and/or email (ready to use)
    Needs Review  - probably not IT companies (schools, govt offices, IT parks...)
    Names Only    - companies with no usable contact yet
    Summary       - counts per state

TIP: always open the .xlsx. If you open the .csv in Excel and save it, Excel damages
phone numbers (turns them into things like 9.14813E+11 or -4712317916).
"""
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT_DIR = Path("output_it")

METRO2 = {"11", "20", "22", "33", "40", "44", "79", "80"}          # 2-digit area codes
STD3_7XX = {"712", "721", "731", "741", "751", "755", "761", "771"}  # 3-digit codes starting 7
METRO_STATE = {"80": "Karnataka", "79": "Gujarat"}
# Area codes (after the 0) that start with 6 in the eastern states
STD6 = {"Bihar": r"6(1\d|2\d|3\d|41|45|46|47)", "Jharkhand": r"6(43|5\d)", "Odisha": r"6[678]\d"}

EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}$")
SCI_RE = re.compile(r"^-?\d(\.\d+)?E[+-]?\d+$", re.I)

REVIEW_RE = re.compile(
    r"district medical|ghss|school|college|panchayat|panchayath|akshaya|\bcsc\b|digital seva|"
    r"meeseva|cable|directorate|information technology mission|startup mission|cyber ?park|"
    r"infopark|tech park|\bpark\b|institute|study cent|training|aptech|academy|library|"
    r"foundation|law center|feminist|gardens|boderland|medical office|government|\bgovt\b",
    re.I)


# ------------------------------------------------------------------ PHONES
def format_phone(part, state):
    """Returns (formatted, type) | ('DAMAGED', None) | None (junk/invalid)."""
    p = str(part).strip()
    if not p:
        return None
    if SCI_RE.match(p) or re.fullmatch(r"-\d+", p):
        return ("DAMAGED", None)
    if p.startswith("+") and not p.startswith("+91"):
        digits = re.sub(r"\D", "", p)
        return (re.sub(r"\s+", " ", p), "International") if len(digits) >= 8 else None
    digits = re.sub(r"\D", "", p)
    if len(digits) < 6:                       # fragments like "02"
        return None
    if re.fullmatch(r"(\d)\1+", digits):      # 1111111111
        return None
    if digits.startswith("1800") and len(digits) in (10, 11, 12):
        return (f"{digits[:4]} {digits[4:7]} {digits[7:]}", "Toll-free")
    if digits.startswith("91") and len(digits) in (12, 13):
        digits = digits[2:]
    leading_zero = digits.startswith("0")
    if leading_zero:
        digits = digits[1:]
    if len(digits) in (7, 8):                 # local number without area code
        return (f"(local) {digits}", "Landline (no area code)")
    if len(digits) != 10 or digits[0] == "0":
        return None

    if digits[0] in "12345":
        landline = True
    elif leading_zero:
        landline = (digits[:2] in {"79", "80"} or digits[:3] in STD3_7XX or
                    bool(state in STD6 and re.fullmatch(STD6[state], digits[:3])))
    elif digits[0] in "6789":
        landline = METRO_STATE.get(digits[:2]) == state
    else:
        landline = False

    if not landline:
        return (f"+91 {digits[:5]} {digits[5:]}", "Mobile")
    if digits[:2] in METRO2:
        return (f"+91 {digits[:2]} {digits[2:6]} {digits[6:]}", "Landline")
    return (f"+91 {digits[:3]} {digits[3:]}", "Landline")


def parse_phones(raw, state):
    """-> (list of (number, type), damaged_flag)"""
    out, damaged = [], False
    for part in re.split(r"\s*[;,]\s*|\s+/\s+", str(raw or "")):
        r = format_phone(part, state)
        if r is None:
            continue
        if r[0] == "DAMAGED":
            damaged = True
            continue
        if r[0] not in [x[0] for x in out]:
            out.append(r)
    return out, damaged


# ------------------------------------------------------------------ EMAIL / WEB
def clean_email(raw):
    e = str(raw or "").strip().lower().rstrip(".,;")
    return e if EMAIL_RE.match(e) else ""


def clean_website(raw):
    w = str(raw or "").strip().replace(" ", "").replace(",", ".")
    if not w or "@" in w:
        return ""
    if not w.startswith(("http://", "https://")):
        w = "https://" + w
    host = re.sub(r"^https?://(www\.)?", "", w).split("/")[0]
    return w if re.fullmatch(r"[a-z0-9\-]+(\.[a-z0-9\-]+)+", host, re.I) else ""


def domain(w):
    return re.sub(r"^https?://(www\.)?", "", w).split("/")[0].lower() if w else ""


# ------------------------------------------------------------------ MAIN
def load(path):
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, dtype=str).fillna("")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def find_input():
    for name in ("IT_leads.xlsx", "IT_leads.csv"):
        if (OUT_DIR / name).exists():
            return OUT_DIR / name
    raise SystemExit("Could not find output_it/IT_leads.xlsx. Pass a file: python clean_leads.py file.csv")


def build(df):
    rows, seen = [], set()
    for _, r in df.iterrows():
        name = re.sub(r"\s+", " ", str(r.get("name", "")).strip())
        if not name:
            continue
        state = str(r.get("state", "")).strip()
        phones, damaged = parse_phones(r.get("phone", ""), state)
        more, damaged2 = parse_phones(r.get("other_phones", ""), state)
        for m in more:
            if m[0] not in [x[0] for x in phones]:
                phones.append(m)
        damaged = damaged or damaged2

        email = clean_email(r.get("email", "")) or clean_email(r.get("website", ""))
        site = clean_website(r.get("website", ""))
        extra_emails = [e for e in (clean_email(x) for x in re.split(r"[;,\s]+", str(r.get("other_emails", "")))) if e and e != email]

        p1 = phones[0][0] if phones else ""
        key_a = (name.lower(), p1 or domain(site) or email, state)
        key_b = (p1, email) if p1 and email else None
        if key_a in seen or (key_b and key_b in seen):
            continue
        seen.add(key_a)
        if key_b:
            seen.add(key_b)

        note = []
        if damaged:
            note.append("Phone was damaged (e.g. by Excel) - re-run run_it.py to restore")
        if str(r.get("match", "")) == "name_match":
            note.append("Name looks like IT (not tagged) - verify")
        lat, lon = str(r.get("lat", "")), str(r.get("lon", ""))
        rows.append({
            "Company Name": name,
            "State": state,
            "City": str(r.get("city", "")).strip(),
            "Phone 1": p1,
            "Phone 1 Type": phones[0][1] if phones else "",
            "Phone 2": phones[1][0] if len(phones) > 1 else "",
            "Other Phones": ", ".join(p[0] for p in phones[2:]),
            "Email": email,
            "Other Emails": ", ".join(extra_emails),
            "Website": site,
            "Address": str(r.get("address", "")).strip(),
            "Confidence": "High (tagged IT)" if str(r.get("match", "")) == "tagged_IT" else "Medium (name match)",
            "Map": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}" if lat and lon else "",
            "Note": "; ".join(note),
            "_review": bool(REVIEW_RE.search(name)),
        })
    return pd.DataFrame(rows)


def style(ws, widths):
    head = PatternFill("solid", start_color="1F4E78")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.number_format = "@"          # keep phone numbers as text


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else find_input()
    print("Reading", src)
    df = build(load(src))
    OUT_DIR.mkdir(exist_ok=True)

    has_contact = (df["Phone 1"] != "") | (df["Email"] != "")
    review = df["_review"]
    clean = df[has_contact & ~review].drop(columns="_review")
    check = df[review].drop(columns="_review")
    names = df[~has_contact & ~review].drop(columns="_review")[
        ["Company Name", "State", "City", "Website", "Address", "Confidence", "Map", "Note"]]

    # tagged-IT first, then by state / name
    order = {"High (tagged IT)": 0, "Medium (name match)": 1}
    clean = clean.assign(_o=clean.Confidence.map(order)).sort_values(
        ["State", "_o", "Company Name"]).drop(columns="_o").reset_index(drop=True)
    clean.insert(0, "No.", range(1, len(clean) + 1))

    summary = (df[~review].groupby("State").agg(
        Companies=("Company Name", "count"),
        With_Phone=("Phone 1", lambda s: (s != "").sum()),
        With_Email=("Email", lambda s: (s != "").sum()),
        With_Website=("Website", lambda s: (s != "").sum()),
    ).sort_values("Companies", ascending=False).reset_index())
    summary.columns = ["State", "Companies", "With Phone", "With Email", "With Website"]
    total = pd.DataFrame([["TOTAL", *summary.iloc[:, 1:].sum().tolist()]], columns=summary.columns)
    summary = pd.concat([summary, total], ignore_index=True)

    out = OUT_DIR / "IT_leads_CLEAN.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        clean.to_excel(xw, sheet_name="Clean Leads", index=False)
        check.to_excel(xw, sheet_name="Needs Review", index=False)
        names.to_excel(xw, sheet_name="Names Only", index=False)
        summary.to_excel(xw, sheet_name="Summary", index=False)
        style(xw.sheets["Clean Leads"], [6, 38, 16, 16, 18, 15, 18, 22, 30, 28, 34, 45, 20, 18, 45])
        style(xw.sheets["Needs Review"], [38, 16, 16, 18, 15, 18, 22, 30, 28, 34, 45, 20, 18, 45])
        style(xw.sheets["Names Only"], [38, 16, 16, 34, 45, 20, 18, 45])
        style(xw.sheets["Summary"], [20, 12, 12, 12, 14])

    print(f"\nSaved {out}")
    print(f"  Clean Leads : {len(clean)}  (valid phone/email)")
    print(f"  Needs Review: {len(check)}  (probably not IT companies)")
    print(f"  Names Only  : {len(names)}  (no usable contact)")
    print(f"  With valid phone: {(clean['Phone 1'] != '').sum()} | with email: {(clean['Email'] != '').sum()}")
    dmg = df["Note"].str.contains("damaged").sum()
    if dmg:
        print(f"\n!! {dmg} rows had damaged phone numbers (Excel CSV problem). "
              f"Re-run:  python run_it.py --group all --no-enrich   then run this cleaner again.")


if __name__ == "__main__":
    main()
