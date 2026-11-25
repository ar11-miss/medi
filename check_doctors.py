"""Diagnose the doctor finder:  python check_doctors.py"""
from app import config
from app.doctors import find_doctors

LAT, LNG = 18.6770, 73.8970  # Alandi, Pune

print("Geoapify key in .env:", "yes" if config.GEOAPIFY_API_KEY else "NO - get a free one at https://myprojects.geoapify.com")
print("Google Places key in .env:", "yes" if config.GOOGLE_PLACES_API_KEY else "no (optional)")
for specialty in ("General Physician", "Dermatologist", "Emergency Department"):
    res = find_doctors("yellow", specialty, LAT, LNG)
    print(f"\n{specialty}: {len(res['clinics'])} found via {res['source']}")
    if res["note"]:
        print("  note:", res["note"])
    for c in res["clinics"][:3]:
        print(f"  - {c['name']} ({c['distance_km']} km) {c['phone']}")
print("\nGoogle Maps backup link:", res["maps_search_link"])
