# Lead Scraper – Kolkata & West Bengal

## Setup
    python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
    pip install -r requirements.txt
Edit `config.py` -> set USER_AGENT to include your real email.

## Run
    python main.py --region kolkata --categories restaurant,hotel,gym --enrich
    python main.py --region kolkata --radius 5000 --categories clinic --enrich     # 5 km around centre
    python main.py --region west_bengal --categories school,hotel --enrich
    python main.py --source google --region kolkata --categories restaurant --enrich   # needs GOOGLE_API_KEY

Output: `leads_<region>_<timestamp>.csv` and `.xlsx`.

## How it works
1. OpenStreetMap (free) and/or Google Places API (official, paid-after-free-credit) give business name, address, phone, website.
2. The enricher visits each business's own website (homepage + contact/about pages), respects robots.txt, rate-limits, and extracts public emails/phones.
3. Results are de-duplicated and saved.

## Use responsibly
- Collect only business contact details, not private individuals' data (India's DPDP Act 2023 applies to personal data).
- Don't scrape Google Maps / JustDial / IndiaMART pages directly - against their Terms. Use the official API instead.
- When emailing leads, identify yourself, be relevant, and honour opt-outs.
