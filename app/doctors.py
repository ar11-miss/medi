"""Doctor finder: the triage result (level + specialty) + the user's location
-> nearby clinics with phone numbers, sorted by distance.

Order of sources:
  1. Google Places API (New)  - if GOOGLE_PLACES_API_KEY is set (needs a billing account)
  2. Geoapify Places API      - if GEOAPIFY_API_KEY is set (free, no card, 3000 requests/day)
  3. OpenStreetMap Nominatim  - free, no key, slower and less complete
The page also always shows an embedded Google map of the same search as a backup.
"""
import math
import time
import urllib.parse

import requests

from app import config

# specialty -> (search words for Google, Geoapify category)
SPECIALTY_SEARCH = {
    "General Physician": ("general physician clinic", "healthcare.clinic_or_praxis.general"),
    "Dermatologist": ("dermatologist", "healthcare.clinic_or_praxis.dermatology"),
    "ENT Specialist": ("ENT specialist", "healthcare.clinic_or_praxis.otolaryngology"),
    "Gastroenterologist": ("gastroenterologist", "healthcare.clinic_or_praxis.gastroenterology"),
    "Pulmonologist": ("pulmonologist chest physician", "healthcare.clinic_or_praxis.pulmonology"),
    "Cardiologist": ("cardiologist", "healthcare.clinic_or_praxis.cardiology"),
    "Neurologist": ("neurologist", None),
    "Orthopedic": ("orthopedic doctor", "healthcare.clinic_or_praxis.orthopaedics"),
    "Ophthalmologist": ("eye hospital ophthalmologist", "healthcare.clinic_or_praxis.ophthalmology"),
    "Dentist": ("dentist", "healthcare.dentist"),
    "Gynecologist": ("gynecologist", "healthcare.clinic_or_praxis.gynaecology"),
    "Pediatrician": ("pediatrician child specialist", "healthcare.clinic_or_praxis.paediatrics"),
    "Urologist": ("urologist", "healthcare.clinic_or_praxis.urology"),
    "Psychiatrist": ("psychiatrist", "healthcare.clinic_or_praxis.psychiatry"),
    "Endocrinologist": ("endocrinologist diabetologist", "healthcare.clinic_or_praxis.endocrinology"),
    "Emergency Department": ("hospital emergency 24 hours", "healthcare.hospital"),
}
GENERAL_CATEGORIES = "healthcare.clinic_or_praxis,healthcare.hospital"
HEADERS = {"User-Agent": "MediAid-student-project/1.0"}


class MapServiceError(Exception):
    pass


def distance_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


def maps_link(lat, lng, name: str = "") -> str:
    q = urllib.parse.quote(f"{name} {lat},{lng}".strip())
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def maps_query(specialty: str) -> str:
    return SPECIALTY_SEARCH.get(specialty, (specialty, None))[0]


def google_maps_search_link(specialty: str, lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/{urllib.parse.quote(maps_query(specialty))}/@{lat},{lng},14z"


def google_maps_embed(specialty: str, lat: float, lng: float) -> str:
    """A Google map of the same search, shown inside the page. Needs no key."""
    q = urllib.parse.quote(f"{maps_query(specialty)} near {lat},{lng}")
    return f"https://maps.google.com/maps?q={q}&z=14&output=embed"


def _clinic(name, specialty, address, phone, lat, lng, user_lat, user_lng, source, **extra) -> dict:
    phone = (phone or "").split(";")[0].strip()
    return {
        "name": name or "Unnamed clinic", "specialty": specialty, "address": address or "",
        "phone": phone, "call_link": f"tel:{phone.replace(' ', '')}" if phone else "",
        "lat": lat, "lng": lng,
        "distance_km": distance_km(user_lat, user_lng, lat, lng) if lat is not None else None,
        "maps_link": extra.pop("maps_link", None) or (maps_link(lat, lng, name) if lat is not None else ""),
        "source": source, **extra,
    }


# --- 1. Google Places (New) Text Search ----------------------------------------
def search_google(specialty: str, lat: float, lng: float, radius_m: int, limit: int) -> list[dict]:
    resp = requests.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": config.GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
                                "places.location,places.rating,places.currentOpeningHours.openNow,"
                                "places.googleMapsUri",
        },
        json={
            "textQuery": maps_query(specialty),
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng},
                                        "radius": float(radius_m)}},
            "rankPreference": "DISTANCE",
            "pageSize": limit,
        },
        timeout=(6, 15),
    )
    resp.raise_for_status()
    out = []
    for p in resp.json().get("places", []):
        loc = p.get("location", {})
        out.append(_clinic(
            p.get("displayName", {}).get("text"), specialty, p.get("formattedAddress"),
            p.get("nationalPhoneNumber"), loc.get("latitude"), loc.get("longitude"), lat, lng, "google",
            rating=p.get("rating"), open_now=p.get("currentOpeningHours", {}).get("openNow"),
            maps_link=p.get("googleMapsUri")))
    return out


# --- 2. Geoapify Places ----------------------------------------------------------
GEOAPIFY_URL = "https://api.geoapify.com/v2/places"


def _geoapify(categories: str, lat: float, lng: float, radius_m: int, limit: int) -> list[dict]:
    resp = requests.get(GEOAPIFY_URL, headers=HEADERS, timeout=(6, 15), params={
        "categories": categories,
        "filter": f"circle:{lng},{lat},{radius_m}",
        "bias": f"proximity:{lng},{lat}",
        "limit": limit,
        "apiKey": config.GEOAPIFY_API_KEY,
    })
    if resp.status_code == 401:
        raise MapServiceError("Geoapify rejected the API key (401). Check GEOAPIFY_API_KEY in .env")
    if resp.status_code == 400:
        raise ValueError(resp.text[:200])  # usually an unknown category
    resp.raise_for_status()
    return resp.json().get("features", [])


def search_geoapify(specialty: str, lat: float, lng: float, radius_m: int, limit: int) -> tuple[list[dict], str | None]:
    """Returns (clinics, note). Tries the specialty first, then any clinic/hospital."""
    note = None
    category = SPECIALTY_SEARCH.get(specialty, (None, None))[1]
    features = []
    if category:
        try:
            features = _geoapify(category, lat, lng, radius_m, limit)
        except ValueError:
            features = []
    if not features and specialty not in ("General Physician", "Emergency Department"):
        features = _geoapify(GENERAL_CATEGORIES, lat, lng, radius_m, limit)
        if features:
            note = f"No clinics listed as {specialty} nearby, so these are the nearest clinics and hospitals."
    elif not features:
        features = _geoapify(GENERAL_CATEGORIES, lat, lng, radius_m, limit)

    out, seen = [], set()
    for f in features:
        p = f.get("properties", {})
        name = p.get("name") or p.get("address_line1")
        if not name or name in seen or p.get("lat") is None:
            continue
        seen.add(name)
        raw = (p.get("datasource") or {}).get("raw") or {}
        phone = (p.get("contact") or {}).get("phone") or raw.get("phone") or raw.get("contact:phone")
        address = p.get("address_line2") or p.get("formatted") or ""
        out.append(_clinic(name, specialty, address, phone, p["lat"], p["lon"], lat, lng, "geoapify",
                           opening_hours=p.get("opening_hours")))
    out.sort(key=lambda c: c["distance_km"])
    return out[:limit], note


# --- 3. Nominatim (OpenStreetMap's own search), no key -----------------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def search_nominatim(specialty: str, lat: float, lng: float, radius_m: int, limit: int) -> list[dict]:
    if specialty == "Emergency Department":
        terms = ["hospital"]
    elif specialty == "Dentist":
        terms = ["dentist"]
    else:
        terms = ["clinic", "hospital"]
    d = radius_m / 111_000
    out, seen, errors = [], set(), []
    for i, term in enumerate(terms):
        if i:
            time.sleep(1.1)  # Nominatim allows 1 request per second
        try:
            resp = requests.get(NOMINATIM_URL, headers=HEADERS, timeout=(6, 15), params={
                "q": term, "format": "jsonv2", "limit": 25, "bounded": 1, "extratags": 1,
                "viewbox": f"{lng - d},{lat + d},{lng + d},{lat - d}"})
            resp.raise_for_status()
            rows = resp.json()
        except (requests.RequestException, ValueError) as e:
            errors.append(e.__class__.__name__)
            continue
        for r in rows:
            name = r.get("name") or (r.get("display_name") or "").split(",")[0]
            if not name or name in seen:
                continue
            seen.add(name)
            tags = r.get("extratags") or {}
            addr = ", ".join(x.strip() for x in (r.get("display_name") or "").split(",")[1:4])
            out.append(_clinic(name, specialty, addr, tags.get("phone") or tags.get("contact:phone"),
                               float(r["lat"]), float(r["lon"]), lat, lng, "openstreetmap"))
    if not out and errors:
        raise MapServiceError("OpenStreetMap search failed: " + ", ".join(errors))
    out.sort(key=lambda c: c["distance_km"])
    return out[:limit]


# --- Main entry point ----------------------------------------------------------------
def find_doctors(level: str, specialty: str | None, lat: float, lng: float,
                 radius_m: int = 5000, limit: int = 10) -> dict:
    """Clinics for a triage result. Red always means nearest hospitals."""
    if level == "red":
        specialty = "Emergency Department"
    specialty = specialty if specialty in SPECIALTY_SEARCH else "General Physician"
    clinics: list[dict] = []
    source, note, problems = None, None, []

    if config.GOOGLE_PLACES_API_KEY:
        try:
            clinics, source = search_google(specialty, lat, lng, radius_m, limit), "google"
        except requests.RequestException as e:
            problems.append(f"Google Places: {e.__class__.__name__}")

    if not clinics and config.GEOAPIFY_API_KEY:
        try:
            clinics, note = search_geoapify(specialty, lat, lng, radius_m, limit)
            source = "geoapify"
            if not clinics:  # nothing within the radius: look 3x wider
                clinics, note = search_geoapify(specialty, lat, lng, radius_m * 3, limit)
                if clinics:
                    note = f"Nothing within {radius_m // 1000} km, so this shows up to {radius_m * 3 // 1000} km away."
        except MapServiceError as e:
            problems.append(str(e))
        except requests.RequestException as e:
            problems.append(f"Geoapify: {e.__class__.__name__}")

    if not clinics:
        try:
            clinics = search_nominatim(specialty, lat, lng, radius_m * 2, limit)
            source = "openstreetmap"
            if clinics and specialty not in ("General Physician", "Emergency Department", "Dentist"):
                note = f"Showing the nearest clinics and hospitals (not filtered for {specialty})."
        except MapServiceError as e:
            problems.append(str(e))

    if not clinics:
        tip = "" if config.GEOAPIFY_API_KEY else " Add a free GEOAPIFY_API_KEY to .env for reliable results."
        note = ("Couldn't load the clinic list right now"
                + (f" ({'; '.join(problems)})" if problems else "")
                + f". The map below still shows doctors near you.{tip}")

    return {
        "level": level, "specialty": specialty, "emergency": level == "red",
        "emergency_numbers": ["108", "112"] if level == "red" else [],
        "source": source, "note": note, "clinics": clinics,
        "maps_search_link": google_maps_search_link(specialty, lat, lng),
        "maps_embed": google_maps_embed(specialty, lat, lng),
    }
