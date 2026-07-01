"""AI Concierge — plain-English trip search.

Turns a natural request ("a beachfront place in Portugal under $150 for 4")
into structured filters, runs the same ranked search the rest of the app uses,
and replies conversationally. Works fully offline via a heuristic parser; when
an LLM is configured it could be swapped in for parsing/replies.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ConciergeRequest, ConciergeResponse, SearchRequest
from ..security import get_optional_user
from .search import run_search

router = APIRouter(prefix="/api/concierge", tags=["concierge"])

# Vibe synonyms -> canonical tag used by the catalog.
_TAG_SYNONYMS = {
    "beach": "beach", "beachfront": "beach", "seaside": "beach", "coastal": "beach",
    "city": "city", "urban": "city", "downtown": "city",
    "food": "food", "foodie": "food", "culinary": "food", "restaurant": "food",
    "history": "history", "historic": "history", "historical": "history", "ancient": "history",
    "nature": "nature", "outdoors": "nature", "outdoor": "nature", "scenic": "nature",
    "adventure": "adventure", "hiking": "adventure", "hike": "adventure", "trek": "adventure",
    "nightlife": "nightlife", "party": "nightlife", "clubbing": "nightlife", "bars": "nightlife",
    "art": "art", "museum": "art", "museums": "art", "gallery": "art",
    "relax": "relax", "relaxing": "relax", "spa": "relax", "chill": "relax", "quiet": "relax",
    "mountain": "mountain", "mountains": "mountain", "alpine": "mountain",
    "ski": "ski", "skiing": "ski", "snowboard": "ski",
    "snow": "snow", "tropical": "tropical", "wine": "wine", "vineyard": "wine",
    "desert": "desert", "island": "island", "lake": "lake",
}

_STOP_AFTER = r"(?:\s+(?:under|below|less|cheap|for|with|that|near|around|,|\.|!|\?)|$)"


def _parse(message: str) -> SearchRequest:
    text = message.strip()
    low = text.lower()

    # Budget: "under $150", "below 200", "$120/night", "under 100 dollars"
    budget = None
    m = re.search(r"(?:under|below|less than|max|up to)\s*\$?\s*(\d{2,5})", low)
    if not m:
        m = re.search(r"\$\s*(\d{2,5})", low)
    if not m:
        m = re.search(r"(\d{2,5})\s*(?:usd|dollars|/night|per night|a night|budget)", low)
    if m:
        budget = float(m.group(1))

    # Guests: "for 4", "4 people", "family of 5", "couple"
    guests = None
    g = re.search(r"(?:for|sleeps|party of|group of|family of)\s+(\d{1,2})", low)
    if not g:
        g = re.search(r"(\d{1,2})\s+(?:people|guests|adults|travel?lers|of us)", low)
    if g:
        guests = int(g.group(1))
    elif re.search(r"\bcouple\b|\bhoneymoon\b|\bromantic\b", low):
        guests = 2
    elif "solo" in low:
        guests = 1

    # Tags from synonyms.
    tags = []
    for word, tag in _TAG_SYNONYMS.items():
        if re.search(rf"\b{re.escape(word)}\b", low) and tag not in tags:
            tags.append(tag)

    # Destination: text after in/to/near/around/at, else nothing (general).
    destination = None
    d = re.search(rf"\b(?:in|to|near|around|at)\s+([a-zÀ-ſ'\-\s]+?){_STOP_AFTER}", low)
    if d:
        destination = d.group(1).strip().title()

    return SearchRequest(
        q=destination,
        max_price=budget,
        guests=guests,
        tags=tags,
        sort="relevance",
        personalize=True,
        limit=12,
    )


def _merge(context: dict, new: SearchRequest, message: str) -> SearchRequest:
    """Refine the previous turn's filters with the new message (multi-turn chat).
    Handles relative intents like "cheaper", "for 6", "more art", "in Rome"."""
    low = message.lower()
    q = new.q or context.get("destination")
    max_price = new.max_price if new.max_price else context.get("max_price")
    guests = new.guests if new.guests else context.get("guests")
    prev_tags = context.get("tags") or []
    # "add/also/more" keeps prior vibes; otherwise a fresh vibe list replaces them.
    if new.tags and re.search(r"\b(also|add|more|plus|with)\b", low):
        tags = list(dict.fromkeys(prev_tags + new.tags))
    else:
        tags = new.tags or prev_tags

    # Relative budget intents when no explicit number was given.
    if not new.max_price:
        base = max_price or 250
        if re.search(r"cheaper|less expensive|lower budget|more affordable|budget", low):
            max_price = round(base * 0.7)
        elif re.search(r"luxury|nicer|fancier|more expensive|splurge|upscale", low):
            max_price = round(base * 1.6)
    # Relative guest intents.
    if not new.guests and re.search(r"\b(more people|bigger group|larger)\b", low):
        guests = (guests or 2) + 2

    return SearchRequest(q=q, max_price=max_price, guests=guests, tags=tags,
                         sort="relevance", personalize=True, limit=12)


def _reply(req: SearchRequest, total: int) -> str:
    if total == 0:
        return ("I couldn't find a match for that yet — try naming a city "
                "(e.g. \"in Barcelona\") or loosening the budget.")
    bits = []
    if req.q:
        bits.append(f"in {req.q}")
    if req.tags:
        bits.append("for " + ", ".join(req.tags))
    if req.max_price:
        bits.append(f"under ${int(req.max_price)}/night")
    if req.guests:
        bits.append(f"sleeping {req.guests}")
    detail = " ".join(bits)
    return f"Found {total} stays {detail}. Here are the best matches for you:".replace("  ", " ")


@router.post("", response_model=ConciergeResponse)
def concierge(
    payload: ConciergeRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    parsed = _parse(payload.message)
    req = _merge(payload.context, parsed, payload.message) if payload.context else parsed
    result = run_search(req, db, user)
    understood = {
        "destination": req.q,
        "max_price": req.max_price,
        "guests": req.guests,
        "tags": req.tags,
    }
    return ConciergeResponse(
        reply=_reply(req, result.total),
        understood=understood,
        results=result.results,
    )
