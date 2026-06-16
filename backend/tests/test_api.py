"""End-to-end API tests covering the full personalization + booking flow.

Run:  cd backend && python -m pytest -q
Uses an isolated temp SQLite DB so it never touches your dev data.
"""
import os
import tempfile

import pytest

# Point the app at a throwaway DB before importing it.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["AUTO_SEED"] = "true"
os.environ["DATA_PROVIDER"] = "seed"  # deterministic curated catalog for tests

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "demo@traveler.io", "password": "demo1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_seeded_listings(client):
    listings = client.get("/api/listings").json()
    assert len(listings) == 20


def test_listings_have_outbound_booking_links(client):
    listings = client.get("/api/listings").json()
    assert all(l["booking_url"].startswith("https://") for l in listings)
    assert any("booking.com" in l["booking_url"] for l in listings)


def test_register_and_login(client):
    r = client.post("/api/auth/register", json={
        "email": "t@example.com", "name": "T", "password": "secret12",
        "preferences": {"budget": 150, "trip_styles": ["beach"], "interests": ["food"], "climate": "warm"},
    })
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "t@example.com"
    assert r.json()["user"]["is_admin"] is False


def test_register_rejects_short_password(client):
    r = client.post("/api/auth/register", json={
        "email": "short@example.com", "name": "S", "password": "short",
    })
    assert r.status_code == 422


def test_personalized_search_ranks_by_preference(client, auth):
    r = client.post("/api/search", json={"tags": ["beach"], "personalize": True}, headers=auth)
    assert r.status_code == 200
    results = r.json()["results"]
    assert results and results[0]["score"] > 0
    assert "beach" in (results[0]["reason"].lower() + " ".join(results[0]["tags"]))


def test_recommendations_require_auth(client):
    assert client.get("/api/recommendations").status_code == 401


def test_recommendations(client, auth):
    recs = client.get("/api/recommendations?limit=5", headers=auth).json()
    assert len(recs) == 5
    assert recs[0]["score"] >= recs[-1]["score"]  # sorted by score desc


def test_itinerary_generation(client, auth):
    r = client.post("/api/trips", json={"destination": "Kyoto", "days": 4}, headers=auth)
    assert r.status_code == 201
    trip = r.json()
    assert len(trip["days"]) == 4
    assert all("activities" in d for d in trip["days"])


def test_booking_flow_and_pricing(client, auth):
    r = client.post("/api/bookings", json={
        "listing_id": 1, "check_in": "2026-08-01", "check_out": "2026-08-04", "guests": 2,
    }, headers=auth)
    assert r.status_code == 201
    assert r.json()["total_price"] > 0
    assert r.json()["status"] == "confirmed"


def test_booking_rejects_overcapacity(client, auth):
    # Listing 3 (Santorini suite) max 2 guests.
    r = client.post("/api/bookings", json={
        "listing_id": 3, "check_in": "2026-08-01", "check_out": "2026-08-03", "guests": 9,
    }, headers=auth)
    assert r.status_code == 400


def test_dashboard_requires_admin(client):
    # No auth -> 401; the demo account is admin in dev -> 200.
    assert client.get("/api/analytics/dashboard").status_code == 401


def test_dashboard_as_admin(client, auth):
    d = client.get("/api/analytics/dashboard", headers=auth).json()
    assert d["totals"]["listings"] == 20
    assert "acceptance_rate" in d["recommendation_quality"]


def test_demo_account_is_admin_in_dev(client):
    r = client.post("/api/auth/login", json={"email": "demo@traveler.io", "password": "demo1234"})
    assert r.json()["user"]["is_admin"] is True
