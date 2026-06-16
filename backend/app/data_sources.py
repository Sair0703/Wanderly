"""Listing data sources.

Default provider pulls **real accommodations from OpenStreetMap** via the
Overpass API (no API key required) — real property names, coordinates, and
websites. OSM has no nightly prices, so we attach a clearly-labelled *estimated*
price for ranking/budget filtering; the real price lives on the partner site the
"Book" button links to.

Falls back to the curated catalog (``seed.CURATED_LISTINGS``) if the live fetch
returns nothing or errors, so startup never breaks.
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
import urllib.request

from .booking_links import build_booking_url
from .config import settings

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# (city, country, lat, lng, base_price, vibe_tags) — anchors for the live query.
CITIES = [
    ("Lisbon", "Portugal", 38.7223, -9.1393, 130, ["city", "beach", "food", "history"]),
    ("Barcelona", "Spain", 41.3851, 2.1734, 150, ["beach", "city", "nightlife", "food"]),
    ("Paris", "France", 48.8566, 2.3522, 190, ["city", "art", "food", "history"]),
    ("Rome", "Italy", 41.9028, 12.4964, 160, ["history", "city", "food", "art"]),
    ("Amsterdam", "Netherlands", 52.3676, 4.9041, 185, ["city", "art", "history", "food"]),
    ("London", "United Kingdom", 51.5072, -0.1276, 210, ["city", "history", "art", "nightlife"]),
    ("New York", "USA", 40.7128, -74.0060, 240, ["city", "nightlife", "shopping", "art"]),
    ("Tokyo", "Japan", 35.6762, 139.6503, 165, ["city", "food", "nightlife", "shopping"]),
    ("Kyoto", "Japan", 35.0116, 135.7681, 150, ["history", "art", "nature", "relax"]),
    ("Bangkok", "Thailand", 13.7563, 100.5018, 90, ["city", "food", "nightlife", "tropical"]),
    ("Istanbul", "Turkey", 41.0082, 28.9784, 110, ["history", "city", "food"]),
    ("Marrakech", "Morocco", 31.6295, -7.9811, 95, ["history", "desert", "food", "art"]),
    ("Cape Town", "South Africa", -33.9249, 18.4241, 140, ["beach", "adventure", "nature", "wine"]),
    ("Sydney", "Australia", -33.8688, 151.2093, 200, ["beach", "city", "nature"]),
    ("Bali", "Indonesia", -8.4095, 115.1889, 120, ["tropical", "beach", "nature", "relax"]),
    ("Reykjavik", "Iceland", 64.1466, -21.9426, 200, ["nature", "cold", "adventure", "snow"]),
]

_AMENITY_MAP = {
    "internet_access": "wifi",
    "wifi": "wifi",
    "swimming_pool": "pool",
    "air_conditioning": "ac",
    "restaurant": "restaurant",
    "bar": "bar",
    "spa": "spa",
    "parking": "parking",
    "laundry_service": "washer",
    "fitness_centre": "gym",
}


def _det(seed: str) -> float:
    """Deterministic 0..1 value from a string (stable across runs)."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _haversine(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlmb = math.radians(b_lng - a_lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _nearest_city(lat: float, lng: float):
    return min(CITIES, key=lambda c: _haversine(lat, lng, c[2], c[3]))


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")[:40] or "stay"


def _overpass_query(radius: int = 6000) -> str:
    parts = [
        f'node["tourism"~"^(hotel|guest_house|hostel|apartment|resort)$"]["name"]'
        f"(around:{radius},{lat},{lng});"
        for _, _, lat, lng, _, _ in CITIES
    ]
    return f"[out:json][timeout:30];({''.join(parts)});out body 600;"


def fetch_osm_listings(per_city: int = 8) -> list[dict]:
    """Query Overpass and shape OSM accommodations into listing dicts."""
    body = urllib.parse.urlencode({"data": _overpass_query()}).encode()
    req = urllib.request.Request(
        OVERPASS_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "wanderly/1.0 (travel recommendation demo)",
        },
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        payload = json.loads(resp.read().decode())

    buckets: dict[str, list[dict]] = {c[0]: [] for c in CITIES}
    seen: set[tuple] = set()

    for el in payload.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        lat, lng = el.get("lat"), el.get("lon")
        if not name or lat is None or lng is None:
            continue
        city, country, c_lat, c_lng, base, vibe = _nearest_city(lat, lng)
        key = (name.lower(), city)
        if key in seen:
            continue
        seen.add(key)

        d = _det(name + city)
        stars = tags.get("stars")
        try:
            rating = round(3.9 + (float(stars) - 3) * 0.25, 2) if stars else round(4.0 + d * 0.9, 2)
        except ValueError:
            rating = round(4.0 + d * 0.9, 2)
        rating = max(3.6, min(rating, 5.0))

        amenities = sorted({
            v for k, v in _AMENITY_MAP.items()
            if tags.get(k) and tags.get(k) != "no"
        } | {"wifi"})

        kind = "stay"
        tourism = tags.get("tourism", "hotel")
        star_factor = 1.0
        if stars and stars.replace(".", "", 1).isdigit():
            star_factor = 1 + (float(stars) - 3) * 0.12
        price = round(base * (0.7 + d * 0.8) * star_factor, 0)
        website = tags.get("website") or tags.get("contact:website") or ""

        buckets[city].append({
            "title": name,
            "kind": kind,
            "city": city,
            "country": country,
            "lat": lat,
            "lng": lng,
            "price_per_night": float(max(45, price)),
            "price_is_estimate": True,
            "rating": rating,
            "review_count": int(60 + d * 540),
            "max_guests": 2 + int(d * 4),
            "tags": vibe,
            "amenities": amenities,
            "description": f"{tourism.replace('_', ' ').title()} in {city}, {country}."
                           + (f" {tags.get('addr:street')}." if tags.get("addr:street") else ""),
            "image_url": f"https://picsum.photos/seed/{_slug(name + city)}/640/420",
            "website": website,
            "booking_url": build_booking_url(name, city, country),
            "source": "openstreetmap",
            "popularity": int(d * 200),
            # rank within city: prefer entries with stars + website
            "_score": (1 if stars else 0) + (1 if website else 0) + d,
        })

    listings: list[dict] = []
    for city, items in buckets.items():
        items.sort(key=lambda x: x["_score"], reverse=True)
        for it in items[:per_city]:
            it.pop("_score", None)
            listings.append(it)
    return listings


def get_listings() -> list[dict]:
    """Resolve listings for the active provider, with safe fallback to curated."""
    from .seed import curated_listing_dicts  # local import avoids a cycle

    provider = settings.data_provider.lower()
    if provider == "seed":
        return curated_listing_dicts()

    if provider == "osm":
        try:
            live = fetch_osm_listings()
            if len(live) >= 12:
                print(f"[data] Loaded {len(live)} real listings from OpenStreetMap.")
                return live
            print("[data] Overpass returned too few results; using curated catalog.")
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[data] OSM fetch failed ({exc}); using curated catalog.")
        return curated_listing_dicts()

    # Unknown / amadeus-not-configured -> curated.
    return curated_listing_dicts()
