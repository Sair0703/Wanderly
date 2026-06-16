"""Seed the database with demo listings and users."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Listing, User
from .security import hash_password

# (title, kind, city, country, lat, lng, price, rating, reviews, guests, tags, amenities, desc, img)
_LISTINGS = [
    ("Sunlit Loft by the Sea", "stay", "Lisbon", "Portugal", 38.7223, -9.1393, 145, 4.8, 312, 4,
     ["beach", "city", "food", "relax"], ["wifi", "kitchen", "balcony", "ac"],
     "Bright loft steps from the waterfront with pastel-tiled charm.", "lisbon-loft"),
    ("Alfama Heritage Apartment", "stay", "Lisbon", "Portugal", 38.7139, -9.1262, 110, 4.6, 198, 3,
     ["history", "city", "art"], ["wifi", "kitchen", "washer"],
     "Restored apartment in the historic Alfama district.", "alfama"),
    ("Santorini Cliffside Suite", "stay", "Santorini", "Greece", 36.4618, 25.3765, 290, 4.9, 540, 2,
     ["beach", "island", "relax", "tropical"], ["pool", "wifi", "ac", "sea-view"],
     "Whitewashed suite with a private terrace over the caldera.", "santorini"),
    ("Kyoto Machiya Townhouse", "stay", "Kyoto", "Japan", 35.0116, 135.7681, 175, 4.85, 421, 5,
     ["history", "art", "nature", "relax"], ["wifi", "garden", "tatami"],
     "Traditional wooden townhouse near temple gardens.", "kyoto"),
    ("Shibuya Sky Studio", "stay", "Tokyo", "Japan", 35.6595, 139.7005, 160, 4.7, 389, 2,
     ["city", "nightlife", "food", "shopping"], ["wifi", "ac", "gym"],
     "Modern studio in the heart of Tokyo's nightlife.", "tokyo"),
    ("Alpine Chalet Retreat", "stay", "Zermatt", "Switzerland", 46.0207, 7.7491, 320, 4.9, 276, 8,
     ["ski", "mountain", "snow", "alpine", "nature"], ["fireplace", "wifi", "sauna", "ski-access"],
     "Cozy chalet with Matterhorn views and ski-in access.", "zermatt"),
    ("Marrakech Riad Oasis", "stay", "Marrakech", "Morocco", 31.6295, -7.9811, 95, 4.5, 233, 6,
     ["history", "desert", "food", "art"], ["pool", "wifi", "courtyard", "ac"],
     "Tranquil riad with a plunge pool and rooftop terrace.", "marrakech"),
    ("Bali Jungle Villa", "stay", "Ubud", "Indonesia", -8.5069, 115.2625, 130, 4.8, 612, 4,
     ["tropical", "nature", "relax", "adventure"], ["pool", "wifi", "yoga", "ac"],
     "Open-air villa surrounded by rice terraces.", "bali"),
    ("Manhattan Skyline Apartment", "stay", "New York", "USA", 40.7549, -73.984, 240, 4.6, 501, 4,
     ["city", "nightlife", "shopping", "art"], ["wifi", "gym", "doorman", "ac"],
     "High-floor apartment with skyline views in Midtown.", "nyc"),
    ("Parisian Montmartre Flat", "stay", "Paris", "France", 48.8867, 2.3431, 185, 4.7, 444, 3,
     ["city", "art", "food", "history"], ["wifi", "kitchen", "balcony"],
     "Charming flat below the Sacré-Cœur with café views.", "paris"),
    ("Cape Town Ocean Bungalow", "stay", "Cape Town", "South Africa", -33.9249, 18.4241, 150, 4.75, 287, 6,
     ["beach", "adventure", "nature", "wine"], ["wifi", "pool", "braai", "sea-view"],
     "Bungalow between Table Mountain and the Atlantic.", "capetown"),
    ("Reykjavik Aurora Cabin", "stay", "Reykjavik", "Iceland", 64.1466, -21.9426, 200, 4.8, 199, 4,
     ["nature", "cold", "adventure", "snow"], ["hot-tub", "wifi", "fireplace"],
     "Glass-roofed cabin for chasing the northern lights.", "reykjavik"),
    ("Tuscan Vineyard Villa", "stay", "Florence", "Italy", 43.7696, 11.2558, 210, 4.9, 358, 8,
     ["wine", "countryside", "food", "relax"], ["pool", "wifi", "vineyard", "kitchen"],
     "Stone villa amid rolling Tuscan vineyards.", "tuscany"),
    ("Barcelona Beachfront Pad", "stay", "Barcelona", "Spain", 41.3784, 2.1925, 165, 4.65, 412, 4,
     ["beach", "city", "nightlife", "food"], ["wifi", "ac", "balcony"],
     "Steps from Barceloneta beach and tapas bars.", "barcelona"),
    ("Queenstown Lakeside Lodge", "stay", "Queenstown", "New Zealand", -45.0312, 168.6626, 230, 4.85, 264, 6,
     ["adventure", "mountain", "nature", "lake"], ["wifi", "fireplace", "lake-view"],
     "Adventure hub lodge on Lake Wakatipu.", "queenstown"),
    ("Bangkok Riverside Suite", "stay", "Bangkok", "Thailand", 13.7563, 100.5018, 85, 4.5, 523, 3,
     ["city", "food", "nightlife", "tropical"], ["pool", "wifi", "ac", "gym"],
     "Modern suite overlooking the Chao Phraya river.", "bangkok"),
    ("Amsterdam Canal House", "stay", "Amsterdam", "Netherlands", 52.3676, 4.9041, 195, 4.7, 376, 4,
     ["city", "art", "history", "food"], ["wifi", "kitchen", "canal-view"],
     "Classic gabled canal house in the Jordaan.", "amsterdam"),
    ("Sedona Desert Casita", "stay", "Sedona", "USA", 34.8697, -111.761, 175, 4.8, 211, 2,
     ["desert", "nature", "adventure", "relax"], ["hot-tub", "wifi", "patio"],
     "Adobe casita framed by red-rock formations.", "sedona"),
    ("Dubrovnik Old Town Stone House", "stay", "Dubrovnik", "Croatia", 42.6407, 18.1077, 160, 4.75, 298, 5,
     ["beach", "history", "city"], ["wifi", "ac", "terrace", "sea-view"],
     "Stone house within the medieval city walls.", "dubrovnik"),
    ("Banff Mountain Cabin", "stay", "Banff", "Canada", 51.1784, -115.5708, 185, 4.8, 245, 6,
     ["mountain", "snow", "nature", "ski"], ["fireplace", "wifi", "hot-tub"],
     "Log cabin among the peaks of Banff National Park.", "banff"),
]

_USERS = [
    ("Ava Traveler", "demo@traveler.io", "demo1234",
     {"budget": 180, "trip_styles": ["beach", "city"], "interests": ["food", "art"], "climate": "warm"}),
    ("Sam Explorer", "sam@traveler.io", "demo1234",
     {"budget": 250, "trip_styles": ["adventure", "mountain"], "interests": ["nature", "adventure"], "climate": "cold"}),
]


def _img(slug: str) -> str:
    # Stable, royalty-free placeholder photos keyed by slug (no API key needed).
    return f"https://picsum.photos/seed/{slug}/640/420"


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(Listing)):
        return False

    for (title, kind, city, country, lat, lng, price, rating, reviews, guests,
         tags, amenities, desc, slug) in _LISTINGS:
        db.add(Listing(
            title=title, kind=kind, city=city, country=country, lat=lat, lng=lng,
            price_per_night=price, rating=rating, review_count=reviews, max_guests=guests,
            tags=tags, amenities=amenities, description=desc,
            image_url=_img(slug), popularity=reviews,
        ))

    # Demo login accounts are convenient locally but are a known public
    # credential — only seed them when explicitly enabled (off in production).
    if settings.seed_demo_users:
        for name, email, pw, prefs in _USERS:
            if not db.scalar(select(User).where(User.email == email)):
                matches_admin = bool(settings.admin_email) and email.lower() == settings.admin_email.lower()
                # In dev, make the primary demo account admin so the dashboard
                # is reachable; never auto-grant admin in production.
                dev_admin = (not settings.is_production) and email == "demo@traveler.io"
                db.add(User(name=name, email=email, hashed_password=hash_password(pw),
                            preferences=prefs, is_admin=matches_admin or dev_admin))

    db.commit()
    return True
