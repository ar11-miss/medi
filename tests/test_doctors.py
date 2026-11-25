"""Doctor finder tests with fake HTTP responses (no internet needed)."""
import pytest
import requests

from app import config, doctors

USER = (18.6770, 73.8970)


class FakeResp:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status
        self.text = str(data)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.data


def feature(name, lat, lng, phone=None, **props):
    p = {"name": name, "lat": lat, "lon": lng, "address_line2": "Alandi, Pune", **props}
    if phone:
        p["contact"] = {"phone": phone}
    return {"properties": p}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", None)
    monkeypatch.setattr(config, "GEOAPIFY_API_KEY", "test-key")
    monkeypatch.setattr(doctors.time, "sleep", lambda s: None)

    def offline(*a, **kw):
        raise requests.ConnectionError("offline in tests")

    monkeypatch.setattr(requests, "get", offline)
    monkeypatch.setattr(requests, "post", offline)


def test_geoapify_specialty_results_sorted(monkeypatch):
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(params)
        return FakeResp({"features": [feature("Far Skin Clinic", 18.70, 73.90, phone="+91 20 1234 5678"),
                                      feature("Near Skin Clinic", 18.678, 73.898)]})

    monkeypatch.setattr(requests, "get", fake_get)
    r = doctors.find_doctors("yellow", "Dermatologist", *USER)
    assert r["source"] == "geoapify"
    assert [c["name"] for c in r["clinics"]] == ["Near Skin Clinic", "Far Skin Clinic"]
    assert r["clinics"][1]["call_link"] == "tel:+912012345678"
    assert calls[0]["categories"] == "healthcare.clinic_or_praxis.dermatology"
    assert calls[0]["filter"] == "circle:73.897,18.677,5000"
    assert "output=embed" in r["maps_embed"]


def test_falls_back_to_any_clinic(monkeypatch):
    def fake_get(url, params=None, **kw):
        if params["categories"] != doctors.GENERAL_CATEGORIES:
            return FakeResp({"features": []})
        return FakeResp({"features": [feature("Family Clinic", 18.68, 73.90)]})

    monkeypatch.setattr(requests, "get", fake_get)
    r = doctors.find_doctors("orange", "Urologist", *USER)
    assert r["clinics"][0]["name"] == "Family Clinic"
    assert "nearest clinics and hospitals" in r["note"]


def test_unknown_category_400_is_handled(monkeypatch):
    def fake_get(url, params=None, **kw):
        if params["categories"] != doctors.GENERAL_CATEGORIES:
            return FakeResp("bad category", status=400)
        return FakeResp({"features": [feature("City Clinic", 18.68, 73.90)]})

    monkeypatch.setattr(requests, "get", fake_get)
    assert doctors.find_doctors("yellow", "Cardiologist", *USER)["clinics"][0]["name"] == "City Clinic"


def test_red_means_hospitals(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, params=None, **kw: (
        calls.append(params) or FakeResp({"features": [feature("City Hospital", 18.68, 73.90)]})))
    r = doctors.find_doctors("red", "Cardiologist", *USER)
    assert r["emergency"] and r["emergency_numbers"] == ["108", "112"]
    assert calls[0]["categories"] == "healthcare.hospital"


def test_bad_key_message(monkeypatch):
    def fake_get(url, params=None, **kw):
        if "geoapify" in url:
            return FakeResp({"message": "Invalid apiKey"}, status=401)
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", fake_get)
    r = doctors.find_doctors("yellow", "Dentist", *USER)
    assert r["clinics"] == [] and "GEOAPIFY_API_KEY" in r["note"]
    assert r["maps_embed"].startswith("https://maps.google.com/maps?q=dentist")


def test_no_key_uses_nominatim(monkeypatch):
    monkeypatch.setattr(config, "GEOAPIFY_API_KEY", None)
    monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResp([
        {"name": "Alandi Rural Hospital", "lat": "18.680", "lon": "73.899",
         "display_name": "Alandi Rural Hospital, Alandi, Khed, Pune", "extratags": {"phone": "020 2711 1111"}}]))
    r = doctors.find_doctors("yellow", "General Physician", *USER)
    assert r["source"] == "openstreetmap" and r["clinics"][0]["phone"] == "020 2711 1111"


def test_everything_down_still_gives_map(monkeypatch):
    monkeypatch.setattr(config, "GEOAPIFY_API_KEY", None)
    r = doctors.find_doctors("yellow", "Dentist", *USER)
    assert r["clinics"] == [] and "map below" in r["note"] and "GEOAPIFY_API_KEY" in r["note"]


def test_google_used_first_when_key_set(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", "g-key")
    monkeypatch.setattr(requests, "post", lambda url, **kw: FakeResp({"places": [{
        "displayName": {"text": "Dr Patil ENT Clinic"}, "formattedAddress": "Alandi, Pune",
        "nationalPhoneNumber": "020 1234 5678", "location": {"latitude": 18.68, "longitude": 73.90},
        "rating": 4.6, "currentOpeningHours": {"openNow": True}, "googleMapsUri": "https://maps.google.com/x"}]}))
    r = doctors.find_doctors("orange", "ENT Specialist", *USER)
    assert r["source"] == "google" and r["clinics"][0]["rating"] == 4.6
