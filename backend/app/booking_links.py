"""Build outbound booking/affiliate deep links for a listing.

These take the user to a real site (Booking.com by default) pre-searched for the
specific property + city. Set BOOKING_AFFILIATE_ID to attach your affiliate tag
so qualifying bookings earn commission.
"""
from __future__ import annotations

from urllib.parse import urlencode

from .config import settings


def build_booking_url(name: str, city: str, country: str = "") -> str:
    query = " ".join(p for p in (name, city, country) if p).strip()
    provider = settings.booking_provider

    if provider == "google":
        return "https://www.google.com/travel/search?" + urlencode({"q": query})
    if provider == "expedia":
        return "https://www.expedia.com/Hotel-Search?" + urlencode({"destination": query})

    # Default: Booking.com search deep link (works without approval; affiliate optional).
    params = {"ss": query}
    if settings.booking_affiliate_id:
        params["aid"] = settings.booking_affiliate_id
    return "https://www.booking.com/searchresults.html?" + urlencode(params)
