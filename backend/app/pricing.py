"""Price intelligence — label a listing's nightly rate against its city median.

Gives users an at-a-glance "is this a good deal?" signal Airbnb doesn't surface.
City medians are cached so this stays cheap on hot paths.
"""
from __future__ import annotations

import statistics
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cache import cache
from .models import Listing


def city_median(db: Session, city: str) -> float:
    key = f"median:{city.lower()}"
    cached = cache.get_json(key)
    if cached is not None:
        return float(cached)
    prices = db.execute(
        select(Listing.price_per_night).where(Listing.city == city)
    ).scalars().all()
    median = float(statistics.median(prices)) if prices else 0.0
    cache.set_json(key, median, ttl=600)
    return median


def deal_label(price: float, median: float) -> str:
    if not median or price <= 0:
        return ""
    ratio = price / median
    if ratio <= 0.8:
        return "Great deal"
    if ratio <= 0.95:
        return "Good value"
    if ratio <= 1.2:
        return "Typical price"
    return "Premium"


def annotate_deals(db: Session, items: Iterable) -> None:
    """Set `.deal` on each ScoredListing-like item (has .city, .price_per_night)."""
    items = list(items)
    cities = {it.city for it in items}
    medians = {c: city_median(db, c) for c in cities}
    for it in items:
        it.deal = deal_label(it.price_per_night, medians.get(it.city, 0.0))
