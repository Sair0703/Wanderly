"""Build a day-by-day itinerary grounded in real places.

Distributes real attractions (fetched from OpenStreetMap) across the trip with
morning/afternoon/evening slots, attaches estimated per-activity prices, and
computes per-day and trip cost estimates.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from .booking_links import build_activity_url

_TIMES = ["Morning", "Afternoon", "Evening"]


def _interleave_by_category(attractions: list[dict]) -> list[dict]:
    """Round-robin across categories (preserving priority order within each) so a
    day mixes, say, a museum + a park + a viewpoint instead of three museums."""
    buckets: "OrderedDict[str, list]" = OrderedDict()
    for a in attractions:
        buckets.setdefault(a["category"], []).append(a)
    ordered = []
    while any(buckets.values()):
        for cat in list(buckets):
            if buckets[cat]:
                ordered.append(buckets[cat].pop(0))
    return ordered


def build_itinerary(
    destination: str,
    ndays: int,
    interests: list[str],
    attractions: list[dict],
    stays: list[dict],
) -> dict[str, Any]:
    attractions = _interleave_by_category(attractions)
    n = len(attractions)
    days, total, used = [], 0.0, 0
    for d in range(ndays):
        acts, day_cost = [], 0.0
        for slot in range(3):
            if n:
                a = attractions[(d * 3 + slot) % n]
                used += 1
                acts.append({
                    "time": _TIMES[slot],
                    "name": a["name"],
                    "category": a.get("category_label", "Attraction"),
                    "price": a["price"],
                    "price_label": a["price_label"],
                    "lat": a["lat"],
                    "lng": a["lng"],
                    "book_url": build_activity_url(a["name"], destination),
                })
                day_cost += a["price"]
        days.append({
            "day": d + 1,
            "title": f"Day {d + 1}: Exploring {destination}",
            "activities": acts,
            "est_cost": round(day_cost),
        })
        total += day_cost

    stops = min(n, ndays * 3)
    stay_line = f" Suggested base: {stays[0]['title']}." if stays else ""
    summary = (
        f"A {ndays}-day {destination} itinerary built around {stops} real places. "
        f"Estimated activities cost ≈ ${round(total)} for the trip (entry fees; "
        f"free sights count as $0).{stay_line}"
    )
    return {
        "title": f"{ndays}-Day {destination} Trip",
        "summary": summary,
        "days": days,
        "estimated_total": round(total),
    }
