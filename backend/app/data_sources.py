"""Listing data sources — global coverage.

Providers (``DATA_PROVIDER``):
  * ``osm``     — real accommodations from OpenStreetMap / Overpass (no key).
                  Seeds a broad global spread, then grows on demand: any
                  destination a user searches is geocoded (Nominatim) and its
                  hotels are fetched live, cached, and persisted — so coverage
                  extends to anywhere on Earth without preloading everything.
  * ``seed``    — curated offline catalog (deterministic; used in tests).
  * ``amadeus`` — Amadeus Self-Service hotel offers (REAL nightly prices; needs
                  AMADEUS_API_KEY/SECRET). Falls back to OSM/curated if unset.

OSM carries no nightly price, so OSM listings show a clearly-labelled *estimate*;
Amadeus listings carry real prices (``price_is_estimate=False``). Every provider
attaches a real outbound booking link. All network paths degrade gracefully.
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .booking_links import build_booking_url
from .cache import cache
from .config import settings
from .models import Listing

# Multiple Overpass mirrors — we try each in turn so one being down/rate-limited
# doesn't break seeding.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_UA = "wanderly/1.0 (travel recommendation platform; contact: admin@wanderly.app)"

DEFAULT_VIBE = ["city", "food"]

# Broad global spread seeded at startup. On-demand search covers everywhere else.
# (city, country, lat, lng, base_price, vibe_tags)
CITIES = [
    # Europe
    ("Lisbon", "Portugal", 38.7223, -9.1393, 130, ["city", "beach", "food", "history"]),
    ("Barcelona", "Spain", 41.3851, 2.1734, 150, ["beach", "city", "nightlife", "food"]),
    ("Madrid", "Spain", 40.4168, -3.7038, 140, ["city", "art", "food", "nightlife"]),
    ("Paris", "France", 48.8566, 2.3522, 190, ["city", "art", "food", "history"]),
    ("Rome", "Italy", 41.9028, 12.4964, 160, ["history", "city", "food", "art"]),
    ("Venice", "Italy", 45.4408, 12.3155, 180, ["history", "art", "relax", "city"]),
    ("Amsterdam", "Netherlands", 52.3676, 4.9041, 185, ["city", "art", "history", "food"]),
    ("London", "United Kingdom", 51.5072, -0.1276, 210, ["city", "history", "art", "nightlife"]),
    ("Berlin", "Germany", 52.52, 13.405, 130, ["city", "nightlife", "art", "history"]),
    ("Prague", "Czechia", 50.0755, 14.4378, 110, ["history", "city", "art"]),
    ("Vienna", "Austria", 48.2082, 16.3738, 140, ["history", "art", "city", "relax"]),
    ("Athens", "Greece", 37.9838, 23.7275, 110, ["history", "city", "beach", "food"]),
    ("Istanbul", "Turkey", 41.0082, 28.9784, 110, ["history", "city", "food"]),
    ("Edinburgh", "United Kingdom", 55.9533, -3.1883, 150, ["history", "city", "nature"]),
    ("Reykjavik", "Iceland", 64.1466, -21.9426, 200, ["nature", "cold", "adventure", "snow"]),
    ("Zurich", "Switzerland", 47.3769, 8.5417, 230, ["city", "mountain", "nature", "relax"]),
    # Asia
    ("Tokyo", "Japan", 35.6762, 139.6503, 165, ["city", "food", "nightlife", "shopping"]),
    ("Kyoto", "Japan", 35.0116, 135.7681, 150, ["history", "art", "nature", "relax"]),
    ("Osaka", "Japan", 34.6937, 135.5023, 140, ["city", "food", "nightlife"]),
    ("Bangkok", "Thailand", 13.7563, 100.5018, 90, ["city", "food", "nightlife", "tropical"]),
    ("Singapore", "Singapore", 1.3521, 103.8198, 190, ["city", "food", "shopping", "tropical"]),
    ("Bali", "Indonesia", -8.4095, 115.1889, 120, ["tropical", "beach", "nature", "relax"]),
    ("Hong Kong", "China", 22.3193, 114.1694, 180, ["city", "food", "shopping", "nightlife"]),
    ("Seoul", "South Korea", 37.5665, 126.978, 130, ["city", "food", "shopping", "nightlife"]),
    ("Hanoi", "Vietnam", 21.0278, 105.8342, 70, ["history", "food", "city"]),
    ("Mumbai", "India", 19.076, 72.8777, 90, ["city", "food", "nightlife"]),
    ("New Delhi", "India", 28.6139, 77.209, 85, ["history", "city", "food"]),
    ("Dubai", "United Arab Emirates", 25.2048, 55.2708, 220, ["city", "desert", "shopping", "beach"]),
    # Africa
    ("Marrakech", "Morocco", 31.6295, -7.9811, 95, ["history", "desert", "food", "art"]),
    ("Cairo", "Egypt", 30.0444, 31.2357, 90, ["history", "desert", "city"]),
    ("Cape Town", "South Africa", -33.9249, 18.4241, 140, ["beach", "adventure", "nature", "wine"]),
    ("Nairobi", "Kenya", -1.2921, 36.8219, 120, ["nature", "adventure", "city"]),
    ("Zanzibar", "Tanzania", -6.1659, 39.2026, 130, ["beach", "tropical", "relax", "island"]),
    # Americas
    ("New York", "USA", 40.7128, -74.006, 240, ["city", "nightlife", "shopping", "art"]),
    ("Los Angeles", "USA", 34.0522, -118.2437, 220, ["city", "beach", "nightlife"]),
    ("San Francisco", "USA", 37.7749, -122.4194, 240, ["city", "food", "nature"]),
    ("Mexico City", "Mexico", 19.4326, -99.1332, 110, ["city", "history", "food", "art"]),
    ("Cancun", "Mexico", 21.1619, -86.8515, 160, ["beach", "tropical", "relax", "nightlife"]),
    ("Rio de Janeiro", "Brazil", -22.9068, -43.1729, 130, ["beach", "city", "nightlife", "nature"]),
    ("Buenos Aires", "Argentina", -34.6037, -58.3816, 100, ["city", "food", "nightlife", "art"]),
    ("Toronto", "Canada", 43.6532, -79.3832, 180, ["city", "art", "food"]),
    # Oceania
    ("Sydney", "Australia", -33.8688, 151.2093, 200, ["beach", "city", "nature"]),
    ("Melbourne", "Australia", -37.8136, 144.9631, 180, ["city", "art", "food", "nightlife"]),
    ("Auckland", "New Zealand", -36.8485, 174.7633, 170, ["nature", "city", "beach"]),
    ("Queenstown", "New Zealand", -45.0312, 168.6626, 210, ["adventure", "mountain", "nature", "lake"]),
]

_AMENITY_MAP = {
    "internet_access": "wifi", "wifi": "wifi", "swimming_pool": "pool",
    "air_conditioning": "ac", "restaurant": "restaurant", "bar": "bar",
    "spa": "spa", "parking": "parking", "laundry_service": "washer",
    "fitness_centre": "gym",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _det(seed: str) -> float:
    return int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _haversine(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi, dlmb = math.radians(b_lat - a_lat), math.radians(b_lng - a_lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _nearest_city(lat: float, lng: float):
    return min(CITIES, key=lambda c: _haversine(lat, lng, c[2], c[3]))


def _vibe_and_base(lat: float, lng: float):
    """Borrow vibe/base from the nearest seeded city within 80km, else defaults."""
    c = _nearest_city(lat, lng)
    if _haversine(lat, lng, c[2], c[3]) <= 80:
        return list(c[5]), c[4]
    return list(DEFAULT_VIBE), 120


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")[:40] or "stay"


def _http_get_json(url: str, timeout: int = 40):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# --------------------------------------------------------------------------- #
# Real photos (no API key): per-property OSM tags, else a Wikipedia city photo
# --------------------------------------------------------------------------- #
def city_photo(city: str) -> str | None:
    """A real representative photo of the destination from Wikipedia (cached)."""
    key = "cityphoto:" + city.lower()
    cached = cache.get_json(key)
    if cached is not None:
        return cached or None
    try:
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "titles": city, "prop": "pageimages",
            "pithumbsize": "800", "format": "json", "redirects": "1",
        })
        pages = _http_get_json(url, timeout=12).get("query", {}).get("pages", {})
        for p in pages.values():
            thumb = (p.get("thumbnail") or {}).get("source")
            if thumb:
                cache.set_json(key, thumb, ttl=30 * 86400)
                return thumb
    except Exception:  # pragma: no cover - network dependent
        pass
    cache.set_json(key, "", ttl=86400)
    return None


def _resolve_image(tags: dict, city: str, slug: str) -> str:
    # 1) Real photo of the actual property if OSM has one.
    img = tags.get("image")
    if img and img.startswith("http"):
        return img
    wc = tags.get("wikimedia_commons") or ""
    if wc.startswith("File:"):
        return ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                + urllib.parse.quote(wc[5:]) + "?width=800")
    # 2) Real photo of the destination from Wikipedia.
    cp = city_photo(city)
    if cp:
        return cp
    # 3) Deterministic placeholder as a last resort.
    return f"https://picsum.photos/seed/{slug}/640/420"


# --------------------------------------------------------------------------- #
# OpenStreetMap (Overpass) — names + locations, no prices
# --------------------------------------------------------------------------- #
def _shape_osm(el: dict, city: str, country: str, base: float, vibe: list) -> dict | None:
    tags = el.get("tags", {})
    name = tags.get("name")
    lat, lng = el.get("lat"), el.get("lon")
    if not name or lat is None or lng is None:
        return None

    # Independent deterministic seeds so rating / price / guests don't correlate
    # (otherwise every "good" hotel is also the most expensive and largest).
    dr, dp, dg, dv = (_det(name + city + s) for s in ("|r", "|p", "|g", "|v"))
    stars = tags.get("stars")
    try:
        rating = round(3.9 + (float(stars) - 3) * 0.25, 2) if stars else round(4.0 + dr * 0.9, 2)
    except ValueError:
        rating = round(4.0 + dr * 0.9, 2)
    rating = max(3.6, min(rating, 5.0))

    star_factor = 1.0
    if stars and stars.replace(".", "", 1).isdigit():
        star_factor = 1 + (float(stars) - 3) * 0.12
    price = round(base * (0.55 + dp * 0.95) * star_factor, 0)

    amenities = sorted({v for k, v in _AMENITY_MAP.items() if tags.get(k) and tags.get(k) != "no"} | {"wifi"})
    tourism = tags.get("tourism", "hotel")
    return {
        "title": name, "kind": "stay", "city": city, "country": country,
        "lat": lat, "lng": lng, "price_per_night": float(max(45, price)),
        "price_is_estimate": True, "rating": rating, "review_count": int(40 + dv * 560),
        "max_guests": 2 + int(dg * 5), "tags": vibe, "amenities": amenities,
        "description": f"{tourism.replace('_', ' ').title()} in {city}, {country}."
                       + (f" {tags.get('addr:street')}." if tags.get("addr:street") else ""),
        "image_url": _resolve_image(tags, city, _slug(name + city)),
        "website": tags.get("website") or tags.get("contact:website") or "",
        "booking_url": build_booking_url(name, city, country),
        "source": "openstreetmap", "popularity": int(dv * 200),
        "_score": (1 if stars else 0) + (1 if tags.get("website") else 0) + dr,
    }


def _overpass_post(query: str, timeout: int = 70) -> list[dict]:
    """POST an Overpass query, trying each mirror until one answers."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last_exc = None
    for mirror in OVERPASS_MIRRORS:
        req = urllib.request.Request(
            mirror, data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": _UA},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode()).get("elements", [])
        except Exception as exc:  # 429 / timeout / 5xx -> try next mirror
            last_exc = exc
            continue
    raise last_exc if last_exc else RuntimeError("no overpass mirror responded")


def _overpass_around(points: list[tuple], radius: int) -> list[dict]:
    clauses = "".join(
        f'node["tourism"~"^(hotel|guest_house|hostel|apartment|resort)$"]["name"]'
        f"(around:{radius},{lat},{lng});"
        for lat, lng in points
    )
    return _overpass_post(f"[out:json][timeout:50];({clauses});out body 2000;")


def fetch_osm_listings(per_city: int = 7, radius: int = 5000) -> list[dict]:
    """Seed-time global fetch across CITIES (chunked Overpass requests)."""
    buckets: dict[str, list[dict]] = {c[0]: [] for c in CITIES}
    seen: set[tuple] = set()
    chunk = 6
    for i in range(0, len(CITIES), chunk):
        group = CITIES[i:i + chunk]
        try:
            elements = _overpass_around([(c[2], c[3]) for c in group], radius)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[data] Overpass chunk {i // chunk} failed: {exc}")
            continue
        for el in elements:
            lat, lng = el.get("lat"), el.get("lon")
            if lat is None or lng is None:
                continue
            city, country, _, _, base, vibe = _nearest_city(lat, lng)
            shaped = _shape_osm(el, city, country, base, vibe)
            if not shaped:
                continue
            key = (shaped["title"].lower(), city)
            if key in seen:
                continue
            seen.add(key)
            buckets[city].append(shaped)

    listings: list[dict] = []
    for items in buckets.values():
        items.sort(key=lambda x: x["_score"], reverse=True)
        for it in items[:per_city]:
            it.pop("_score", None)
            listings.append(it)
    return listings


# --------------------------------------------------------------------------- #
# On-demand: geocode any place on Earth, then fetch its hotels
# --------------------------------------------------------------------------- #
def geocode(query: str) -> dict | None:
    key = "geo:" + query.lower().strip()
    cached = cache.get_json(key)
    if cached is not None:
        return cached or None
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
    )
    try:
        data = _http_get_json(url, timeout=15)
    except Exception as exc:  # pragma: no cover
        print(f"[data] geocode failed for {query!r}: {exc}")
        return None
    if not data:
        cache.set_json(key, {}, ttl=86400)
        return None
    item = data[0]
    addr = item.get("address", {})
    city = (
        addr.get("city") or addr.get("town") or addr.get("municipality")
        or addr.get("village") or item.get("display_name", query).split(",")[0].strip()
        or addr.get("county") or addr.get("state")
    )
    result = {
        "lat": float(item["lat"]), "lng": float(item["lon"]),
        "city": city, "country": addr.get("country", ""),
    }
    cache.set_json(key, result, ttl=7 * 86400)
    return result


def fetch_around(lat: float, lng: float, city: str, country: str,
                 radius: int = 8000, limit: int = 24) -> list[dict]:
    vibe, base = _vibe_and_base(lat, lng)
    try:
        elements = _overpass_around([(lat, lng)], radius)
    except Exception as exc:  # pragma: no cover
        print(f"[data] on-demand Overpass failed for {city}: {exc}")
        return []
    out, seen = [], set()
    for el in elements:
        shaped = _shape_osm(el, city, country, base, vibe)
        if not shaped:
            continue
        k = (shaped["title"].lower(), city)
        if k in seen:
            continue
        seen.add(k)
        shaped.pop("_score", None)
        out.append(shaped)
    out.sort(key=lambda x: x["rating"], reverse=True)
    return out[:limit]


def ensure_destination(db: Session, query: str) -> int:
    """Geocode `query` and ingest its hotels if we haven't recently. Idempotent.
    Only for live OSM self-hosting — the snapshot/seed demos stay fully offline
    (live geocode+Overpass fetches are too slow/unreliable on free hosting)."""
    if settings.data_provider.lower() != "osm":
        return 0
    q = query.strip()
    if len(q) < 3:
        return 0
    marker = "dest:" + q.lower()
    if cache.get_json(marker):
        return 0

    geo = geocode(q)
    if not geo:
        cache.set_json(marker, {"done": 1, "added": 0}, ttl=3600)
        return 0

    added = 0
    for row in fetch_around(geo["lat"], geo["lng"], geo["city"], geo["country"]):
        exists = db.scalar(
            select(Listing.id).where(Listing.title == row["title"], Listing.city == row["city"])
        )
        if not exists:
            db.add(Listing(**row))
            added += 1
    db.commit()
    cache.set_json(marker, {"done": 1, "added": added}, ttl=7 * 86400)
    if added:
        print(f"[data] On-demand: added {added} listings for {geo['city']}, {geo['country']}.")
    return added


# --------------------------------------------------------------------------- #
# Amadeus Self-Service — REAL nightly prices (needs API keys)
# --------------------------------------------------------------------------- #
_AMADEUS_BASE = "https://test.api.amadeus.com"  # use api.amadeus.com for production keys


def _amadeus_token() -> str | None:
    cached = cache.get_json("amadeus:token")
    if cached:
        return cached
    if not (settings.amadeus_api_key and settings.amadeus_api_secret):
        return None
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": settings.amadeus_api_key,
        "client_secret": settings.amadeus_api_secret,
    }).encode()
    req = urllib.request.Request(
        f"{_AMADEUS_BASE}/v1/security/oauth2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    except Exception as exc:  # pragma: no cover
        print(f"[data] Amadeus auth failed: {exc}")
        return None
    token = data.get("access_token")
    if token:
        cache.set_json("amadeus:token", token, ttl=max(60, int(data.get("expires_in", 1700)) - 60))
    return token


def _amadeus_get(path: str, token: str) -> dict:
    req = urllib.request.Request(f"{_AMADEUS_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_amadeus_listings(per_city: int = 6) -> list[dict]:
    """Real hotel offers (with nightly prices) near each seeded city."""
    token = _amadeus_token()
    if not token:
        return []
    listings, seen = [], set()
    for city, country, lat, lng, base, vibe in CITIES:
        try:
            hotels = _amadeus_get(
                f"/v1/reference-data/locations/hotels/by-geocode"
                f"?latitude={lat}&longitude={lng}&radius=8&radiusUnit=KM&hotelSource=ALL",
                token,
            ).get("data", [])[: per_city * 3]
            if not hotels:
                continue
            ids = ",".join(h["hotelId"] for h in hotels[:20])
            offers = _amadeus_get(
                f"/v3/shopping/hotel-offers?hotelIds={ids}&adults=1&roomQuantity=1", token
            ).get("data", [])
        except Exception as exc:  # pragma: no cover
            print(f"[data] Amadeus fetch failed for {city}: {exc}")
            continue

        count = 0
        for entry in offers:
            if count >= per_city:
                break
            hotel = entry.get("hotel", {})
            name = hotel.get("name")
            offer_list = entry.get("offers") or []
            if not name or not offer_list:
                continue
            key = (name.lower(), city)
            if key in seen:
                continue
            seen.add(key)
            try:
                price = float(offer_list[0]["price"]["total"])
            except (KeyError, ValueError, TypeError):
                continue
            d = _det(name + city)
            media = hotel.get("media") or []
            image = media[0].get("uri") if media else f"https://picsum.photos/seed/{_slug(name + city)}/640/420"
            listings.append({
                "title": name.title(), "kind": "stay", "city": city, "country": country,
                "lat": hotel.get("latitude", lat), "lng": hotel.get("longitude", lng),
                "price_per_night": round(price, 2), "price_is_estimate": False,
                "rating": round(4.0 + d * 0.9, 2), "review_count": int(60 + d * 540),
                "max_guests": 2 + int(d * 3), "tags": vibe, "amenities": ["wifi"],
                "description": f"Hotel in {city}, {country}. Live offer via Amadeus.",
                "image_url": image, "website": "",
                "booking_url": build_booking_url(name, city, country),
                "source": "amadeus", "popularity": int(d * 200),
            })
            count += 1
    return listings


# --------------------------------------------------------------------------- #
# Provider resolution
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Real attractions / things to do (for the itinerary planner)
# --------------------------------------------------------------------------- #
_ATTR_PRICE = {  # estimated entry fee range (USD) by category
    "museum": (10, 25), "gallery": (8, 18), "attraction": (12, 28), "zoo": (16, 30),
    "aquarium": (18, 32), "theme_park": (35, 75), "castle": (10, 22), "historic": (8, 16),
}
_FREE_CATS = {"viewpoint", "artwork", "park", "garden", "monument", "memorial",
              "place_of_worship", "fountain", "square"}
_CAT_WEIGHT = {  # marquee sights rank above the swarm of minor public artworks
    "museum": 3.0, "attraction": 2.6, "castle": 2.6, "theme_park": 2.6, "zoo": 2.4,
    "aquarium": 2.4, "viewpoint": 2.2, "gallery": 2.0, "historic": 2.0,
    "place_of_worship": 1.8, "park": 1.8, "garden": 1.3, "artwork": 0.3,
}
_CATEGORY_LABEL = {
    "museum": "Museum", "gallery": "Gallery", "attraction": "Attraction",
    "viewpoint": "Viewpoint", "artwork": "Public art", "zoo": "Zoo",
    "theme_park": "Theme park", "aquarium": "Aquarium", "castle": "Historic site",
    "historic": "Historic site", "park": "Park", "garden": "Garden",
    "place_of_worship": "Landmark",
}


def _attraction_category(tags: dict) -> str:
    t = tags.get("tourism")
    if t in {"museum", "gallery", "attraction", "viewpoint", "artwork", "zoo", "theme_park", "aquarium"}:
        return t
    if tags.get("historic"):
        return "castle" if tags["historic"] in {"castle", "fort", "palace"} else "historic"
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("leisure") == "garden":
        return "garden"
    if tags.get("amenity") == "place_of_worship":
        return "place_of_worship"
    return "attraction"


def _attraction_price(category: str, seed: str):
    if category in _FREE_CATS:
        return 0.0, "Free"
    lo, hi = _ATTR_PRICE.get(category, (10, 20))
    p = round(lo + (hi - lo) * _det(seed))
    return float(p), f"≈ ${p}"


def fetch_attractions(destination: str, radius: int = 6000, limit: int = 45):
    """Real things-to-do near a destination (geocode + Overpass), with estimated
    entry prices. Returns (attractions, geo). Cached per destination."""
    geo = geocode(destination)
    if not geo:
        return [], None
    key = "attractions:" + destination.lower().strip()
    cached = cache.get_json(key)
    if cached is not None:
        return cached, geo

    lat, lng = geo["lat"], geo["lng"]
    query = (
        "[out:json][timeout:40];("
        f'nwr["tourism"~"^(museum|gallery|attraction|viewpoint|artwork|zoo|theme_park|aquarium)$"]["name"](around:{radius},{lat},{lng});'
        f'nwr["historic"]["name"](around:{radius},{lat},{lng});'
        f'nwr["leisure"~"^(park|garden)$"]["name"](around:{radius},{lat},{lng});'
        ");out center 300;"
    )
    try:
        elements = _overpass_post(query, timeout=25)
    except Exception as exc:  # pragma: no cover
        print(f"[data] attractions fetch failed for {destination}: {exc}")
        return [], geo

    seen, out = set(), []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        a_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        a_lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if not name or a_lat is None or a_lng is None or name.lower() in seen:
            continue
        seen.add(name.lower())
        category = _attraction_category(tags)
        price, label = _attraction_price(category, name + destination)
        if tags.get("fee") == "no":
            price, label = 0.0, "Free"
        out.append({
            "name": name, "category": category,
            "category_label": _CATEGORY_LABEL.get(category, "Attraction"),
            "price": price, "price_label": label, "lat": a_lat, "lng": a_lng,
            # rank by category prominence, then notability (Wikipedia/Wikidata).
            "_score": _CAT_WEIGHT.get(category, 1.0)
            + (0.6 if tags.get("wikidata") else 0) + (0.6 if tags.get("wikipedia") else 0)
            + _det(name) * 0.3,
        })

    out.sort(key=lambda a: a["_score"], reverse=True)
    out = out[:limit]
    for a in out:
        a.pop("_score", None)
    cache.set_json(key, out, ttl=7 * 86400)
    return out, geo


def fetch_amadeus_activities(lat: float, lng: float, radius: int = 15) -> list[dict]:
    """Real tours & activities WITH prices and booking links from Amadeus."""
    token = _amadeus_token()
    if not token:
        return []
    try:
        data = _amadeus_get(
            f"/v1/shopping/activities?latitude={lat}&longitude={lng}&radius={radius}", token
        ).get("data", [])
    except Exception as exc:  # pragma: no cover
        print(f"[data] Amadeus activities failed: {exc}")
        return []
    out = []
    for a in data:
        name = a.get("name")
        if not name:
            continue
        geo = a.get("geoCode") or {}
        price_obj = a.get("price") or {}
        try:
            price = float(price_obj.get("amount"))
        except (TypeError, ValueError):
            price = 0.0
        pics = a.get("pictures") or []
        out.append({
            "name": name, "category": "activity", "category_label": "Activity",
            "price": price, "price_label": f"${round(price)}" if price else "See price",
            "lat": float(geo.get("latitude", lat)), "lng": float(geo.get("longitude", lng)),
            "book_url": a.get("bookingLink") or "", "image": pics[0] if pics else "",
        })
    return out


def fetch_things_to_do(destination: str):
    """Dispatch to the configured activities provider. Returns (items, geo, source).
    Amadeus gives real prices + booking links; OSM is the free default/fallback."""
    geo = geocode(destination)
    if not geo:
        return [], None, ""
    if settings.activities_provider.lower() == "amadeus" and settings.amadeus_api_key:
        acts = fetch_amadeus_activities(geo["lat"], geo["lng"])
        if len(acts) >= 6:
            return acts, geo, "amadeus"
        print("[data] Amadeus activities sparse; falling back to OpenStreetMap.")
    attractions, _ = fetch_attractions(destination)
    return attractions, geo, "openstreetmap"


_SNAPSHOT_PATH = Path(__file__).parent / "seed_snapshot.json"


def load_snapshot() -> list[dict]:
    """Real listings captured from a prior OpenStreetMap pull — lets a hosted
    demo boot instantly with worldwide data, no live network fetch."""
    try:
        return json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return []


def get_listings() -> list[dict]:
    from .seed import curated_listing_dicts  # local import avoids a cycle

    provider = settings.data_provider.lower()

    if provider == "snapshot":
        snap = load_snapshot()
        print(f"[data] Loaded {len(snap)} listings from baked snapshot.")
        return snap or curated_listing_dicts()

    if provider == "seed":
        return curated_listing_dicts()

    if provider == "amadeus":
        try:
            amadeus = fetch_amadeus_listings()
            if len(amadeus) >= 12:
                print(f"[data] Loaded {len(amadeus)} real listings (with prices) from Amadeus.")
                return amadeus
            print("[data] Amadeus returned too few results; falling back to OpenStreetMap.")
        except Exception as exc:  # pragma: no cover
            print(f"[data] Amadeus failed ({exc}); falling back to OpenStreetMap.")

    if provider in ("osm", "amadeus"):
        try:
            live = fetch_osm_listings()
            if len(live) >= 12:
                print(f"[data] Loaded {len(live)} real listings from OpenStreetMap.")
                return live
            print("[data] Overpass returned too few results; using curated catalog.")
        except Exception as exc:  # pragma: no cover
            print(f"[data] OSM fetch failed ({exc}); using curated catalog.")

    return curated_listing_dicts()
