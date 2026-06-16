"""Content-based + behavioral recommendation engine.

Ranks listings for a user by combining:
  * preference match (budget proximity, trip-style/interest/tag overlap, climate)
  * behavioral history (tags from listings the user viewed/liked/booked)
  * intrinsic quality (rating) and popularity

Designed to be cheap and explainable ("reason" strings) and cached upstream.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Interaction, Listing, User

# Behavioral signal weights.
_KIND_WEIGHT = {"book": 3.0, "like": 2.0, "click": 1.0, "view": 0.5, "search": 0.3}

_CLIMATE_TAGS = {
    "warm": {"beach", "tropical", "desert", "island"},
    "cold": {"ski", "mountain", "snow", "alpine"},
    "temperate": {"city", "countryside", "wine", "lake"},
}


def _profile_from_history(db: Session, user_id: int) -> Counter:
    """Aggregate a tag-affinity profile from the user's past interactions."""
    profile: Counter = Counter()
    rows = db.execute(
        select(Interaction, Listing)
        .join(Listing, Interaction.listing_id == Listing.id)
        .where(Interaction.user_id == user_id)
        .order_by(Interaction.created_at.desc())
        .limit(200)
    ).all()
    for interaction, listing in rows:
        w = _KIND_WEIGHT.get(interaction.kind, 0.3) * (interaction.weight or 1.0)
        for tag in listing.tags or []:
            profile[tag.lower()] += w
    return profile


def score_listing(
    listing: Listing,
    prefs: dict,
    history_profile: Counter,
    max_history: float,
) -> tuple[float, str]:
    """Return (score in ~0..1, human-readable reason)."""
    reasons: list[str] = []
    score = 0.0
    tags = {t.lower() for t in (listing.tags or [])}

    # 1) Preference / interest / style overlap (weight 0.35)
    wanted = {t.lower() for t in prefs.get("trip_styles", [])} | {
        t.lower() for t in prefs.get("interests", [])
    }
    if wanted:
        overlap = tags & wanted
        match = len(overlap) / max(len(wanted), 1)
        score += 0.35 * match
        if overlap:
            reasons.append("matches your " + ", ".join(sorted(overlap)))

    # 2) Budget proximity (weight 0.20)
    budget = prefs.get("budget")
    if budget:
        diff = abs(listing.price_per_night - budget) / max(budget, 1)
        budget_score = max(0.0, 1.0 - diff)
        score += 0.20 * budget_score
        if listing.price_per_night <= budget:
            reasons.append("within budget")

    # 3) Climate fit (weight 0.10)
    climate = (prefs.get("climate") or "").lower()
    if climate in _CLIMATE_TAGS and tags & _CLIMATE_TAGS[climate]:
        score += 0.10
        reasons.append(f"{climate} climate")

    # 4) Behavioral history affinity (weight 0.20)
    if max_history > 0 and tags:
        affinity = sum(history_profile.get(t, 0.0) for t in tags) / (
            max_history * max(len(tags), 1)
        )
        score += 0.20 * min(affinity, 1.0)
        if affinity > 0:
            reasons.append("similar to places you liked")

    # 5) Quality + popularity (weight 0.15)
    score += 0.10 * (listing.rating / 5.0)
    score += 0.05 * min((listing.popularity or 0) / 1000.0, 1.0)
    if listing.rating >= 4.7:
        reasons.append("top rated")

    reason = "; ".join(reasons[:3]) or "popular pick"
    return round(min(score, 1.0), 4), reason


def recommend(
    db: Session,
    user: Optional[User],
    candidates: Optional[Iterable[Listing]] = None,
    limit: int = 12,
) -> list[tuple[Listing, float, str]]:
    """Rank candidate listings for a user. Falls back to popularity for guests."""
    if candidates is None:
        candidates = db.execute(select(Listing)).scalars().all()
    candidates = list(candidates)

    if user is None:
        ranked = sorted(
            candidates, key=lambda l: (l.rating, l.popularity), reverse=True
        )
        return [(l, round(l.rating / 5.0, 3), "popular pick") for l in ranked[:limit]]

    prefs = user.preferences or {}
    history = _profile_from_history(db, user.id)
    max_history = max(history.values()) if history else 0.0

    scored = [
        (listing, *score_listing(listing, prefs, history, max_history))
        for listing in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
