"""Find doctors near you for your latest case (or any specialty).

  python try_doctors.py                                   uses your latest case
  python try_doctors.py --specialty Dermatologist --level yellow
  python try_doctors.py --lat 18.6770 --lng 73.8970       your location (default: Alandi, Pune)

Find your latitude/longitude: open Google Maps, right-click your location, click the numbers.
"""
import argparse

from app.db import DB
from app.doctors import SPECIALTY_SEARCH, find_doctors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specialty", choices=list(SPECIALTY_SEARCH))
    ap.add_argument("--level", choices=["green", "yellow", "orange", "red"])
    ap.add_argument("--lat", type=float, default=18.6770)
    ap.add_argument("--lng", type=float, default=73.8970)
    ap.add_argument("--radius", type=int, default=5000, help="metres")
    args = ap.parse_args()

    level, specialty = args.level, args.specialty
    if not (level and specialty):
        case = DB().latest_case()
        if case:
            level = level or case["level"]
            specialty = specialty or case["specialty"]
    level = level or "yellow"
    specialty = specialty or "General Physician"

    r = find_doctors(level, specialty, args.lat, args.lng, args.radius)
    if r["emergency"]:
        print("🚑 EMERGENCY: call 108 (ambulance) or 112 now. Nearest hospitals:")
    else:
        print(f"Nearby {r['specialty']} ({r['source']}):")
    if r["note"]:
        print(f"Note: {r['note']}")
    if not r["clinics"]:
        print("No clinics found. Try a bigger --radius.")
    for i, c in enumerate(r["clinics"], 1):
        extra = f"  ⭐ {c['rating']}" if c.get("rating") else ""
        print(f"\n{i}. {c['name']}  ({c['distance_km']} km){extra}")
        if c["address"]:
            print(f"   📍 {c['address']}")
        print(f"   📞 {c['phone'] or 'no phone listed'}")
        print(f"   🗺️  {c['maps_link']}")


if __name__ == "__main__":
    main()
