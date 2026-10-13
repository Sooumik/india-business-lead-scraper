"""Visit each business's OWN website and pull public contact emails/phones."""
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,}")
# Indian mobiles (6-9xxxxxxxxx) and Kolkata/WB landlines (033 xxxx xxxx etc.)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?(?:0?33[\s\-]?\d{4}[\s\-]?\d{4}|[6-9]\d{4}[\s\-]?\d{5})(?!\d)")
BAD_EMAIL_PARTS = ("example.", "sentry", "wixpress", "domain.com", "yourname", "email@",
                   ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
CONTACT_HINTS = ("contact", "about", "reach", "enquir", "inquir", "connect", "support")

_robots_cache = {}


def normalize_url(url):
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def allowed_by_robots(session, url):
    if not config.RESPECT_ROBOTS_TXT:
        return True
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        from urllib.robotparser import RobotFileParser
        rp = RobotFileParser()
        try:
            r = session.get(base + "/robots.txt", timeout=config.REQUEST_TIMEOUT)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        _robots_cache[base] = rp
    return _robots_cache[base].can_fetch(config.USER_AGENT, url)


def clean_phone(raw):
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    digits = digits.lstrip("0") if len(digits) > 10 and digits.startswith("0") else digits
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    if digits.startswith("33") and len(digits) == 10:
        return "033-" + digits[2:]
    return None


def extract_contacts(html):
    soup = BeautifulSoup(html, "html.parser")
    emails, phones = set(), set()
    for a in soup.select('a[href^="mailto:"]'):
        emails.add(a["href"][7:].split("?")[0].strip().lower())
    for a in soup.select('a[href^="tel:"]'):
        p = clean_phone(a["href"][4:])
        if p:
            phones.add(p)
    text = soup.get_text(" ", strip=True)
    emails.update(e.lower() for e in EMAIL_RE.findall(text))
    for m in PHONE_RE.findall(text):
        p = clean_phone(m)
        if p:
            phones.add(p)
    emails = {e for e in emails if not any(b in e for b in BAD_EMAIL_PARTS)}
    return emails, phones, soup


def enrich_site(website):
    """Returns (emails, phones). Never raises."""
    url = normalize_url(website)
    if not url:
        return [], []
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    emails, phones, seen = set(), set(), set()
    queue = [url]
    while queue and len(seen) < config.MAX_PAGES_PER_SITE:
        page = queue.pop(0)
        if page in seen or not allowed_by_robots(session, page):
            continue
        seen.add(page)
        try:
            r = session.get(page, timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                continue
        except requests.RequestException:
            continue
        e, p, soup = extract_contacts(r.text)
        emails |= e
        phones |= p
        if len(seen) == 1:  # from homepage, queue contact-like pages on same domain
            host = urlparse(page).netloc
            for a in soup.find_all("a", href=True):
                link = urljoin(page, a["href"]).split("#")[0]
                if urlparse(link).netloc == host and any(h in link.lower() for h in CONTACT_HINTS):
                    queue.append(link)
        time.sleep(config.DELAY_BETWEEN_REQUESTS)
    return sorted(emails), sorted(phones)
