"""Settings: regions, business categories, and scraping behaviour."""

REGIONS = {
    # Kolkata city (bounding box = south, west, north, east)
    "kolkata": {
        "bbox": (22.45, 88.22, 22.70, 88.50),
        "center": (22.5726, 88.3639),
        "areas": [
            "Salt Lake", "New Town", "Park Street", "Howrah", "Dum Dum",
            "Behala", "Garia", "Jadavpur", "Ballygunge", "Tollygunge",
            "Shyambazar", "Barasat", "Rajarhat", "Baranagar", "Kasba",
            "Gariahat", "Esplanade", "Bidhannagar", "Sodepur", "Barrackpore",
        ],
    },
    # Whole of West Bengal
    "west_bengal": {
        "iso": "IN-WB",
        "center": (22.9868, 87.8550),
        "areas": [
            "Kolkata", "Howrah", "Durgapur", "Asansol", "Siliguri", "Darjeeling",
            "Kharagpur", "Haldia", "Bardhaman", "Malda", "Berhampore", "Krishnanagar",
            "Bankura", "Purulia", "Jalpaiguri", "Cooch Behar", "Raiganj", "Midnapore",
            "Bally", "Barasat", "Kalyani", "Serampore", "Chandannagar", "Digha",
        ],
    },
}

# friendly name -> (OpenStreetMap tag, Google search phrase)
CATEGORIES = {
    "restaurant": ("amenity=restaurant", "restaurants"),
    "cafe": ("amenity=cafe", "cafes"),
    "hotel": ("tourism=hotel", "hotels"),
    "school": ("amenity=school", "schools"),
    "college": ("amenity=college", "colleges"),
    "hospital": ("amenity=hospital", "hospitals"),
    "clinic": ("amenity=clinic", "clinics"),
    "dentist": ("amenity=dentist", "dentists"),
    "pharmacy": ("amenity=pharmacy", "pharmacies"),
    "gym": ("leisure=fitness_centre", "gyms"),
    "bank": ("amenity=bank", "banks"),
    "salon": ("shop=hairdresser", "salons"),
    "clothes": ("shop=clothes", "clothing stores"),
    "electronics": ("shop=electronics", "electronics shops"),
    "jewellery": ("shop=jewelry", "jewellery shops"),
    "car_dealer": ("shop=car", "car dealers"),
    "real_estate": ("office=estate_agent", "real estate agents"),
    "lawyer": ("office=lawyer", "lawyers"),
    "accountant": ("office=accountant", "accountants"),
    "it_company": ("office=it", "IT companies"),
    "any_office": ("office=*", "offices"),
    "digital_marketing": ("office=advertising_agency", "digital marketing agencies"),
    "software_company": ("office=it", "software companies"),
    "consulting": ("office=consulting", "consulting firms"),
}

# Politeness / crawling
USER_AGENT = "LeadResearchBot/1.0 (+contact: soumik.santra25-27@bibs.co.in)"  # <- put YOUR email
REQUEST_TIMEOUT = 12
DELAY_BETWEEN_REQUESTS = 1.0     # seconds, per website
MAX_PAGES_PER_SITE = 4           # homepage + up to 3 contact/about pages
WORKERS = 8                      # parallel websites
RESPECT_ROBOTS_TXT = True
