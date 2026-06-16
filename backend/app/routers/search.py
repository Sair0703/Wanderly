"""Search with filtering, sorting, personalized re-ranking, and caching."""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..cache import cache
from ..data_sources import ensure_destination
from ..database import get_db
from ..models import Interaction, Listing, User
from ..recommender import recommend
from ..schemas import ScoredListing, SearchRequest, SearchResponse
from ..security import get_optional_user

router = APIRouter(prefix="/api/search", tags=["search"])


def _cache_key(payload: SearchRequest, user_id: Optional[int]) -> str:
    raw = json.dumps(payload.model_dump(), sort_keys=True, default=str) + f"|u={user_id}"
    return "search:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _text_filter(q: str):
    """Match if ANY word appears in ANY text field. Robust to multi-word place
    queries ("Lima Peru"), partial matches, and accent/wording differences in
    one of the words ("Edinburgh Scotland" -> matches on "Edinburgh")."""
    clauses = []
    for tok in q.lower().split():
        t = f"%{tok}%"
        clauses += [
            Listing.title.ilike(t),
            Listing.city.ilike(t),
            Listing.country.ilike(t),
            Listing.description.ilike(t),
        ]
    return or_(*clauses) if clauses else None


@router.post("", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    key = _cache_key(payload, user.id if user else None)
    cached = cache.get_json(key)
    if cached:
        return SearchResponse(total=cached["total"], results=cached["results"], cached=True)

    # Global coverage: if a text query names a destination whose CITY we don't
    # already cover, geocode it and ingest its real hotels live. We check the
    # city (not any field) so e.g. "Porto Portugal" isn't considered "covered"
    # just because we have Lisbon listings in the same country.
    if payload.q and len(payload.q.strip()) >= 3:
        toks = [t for t in payload.q.lower().split() if len(t) >= 3]
        city_hits = 0
        if toks:
            city_hits = db.scalar(
                select(func.count()).select_from(Listing).where(
                    or_(*[Listing.city.ilike(f"%{t}%") for t in toks])
                )
            ) or 0
        if city_hits < 6:
            ensure_destination(db, payload.q)

    stmt = select(Listing)
    if payload.q and _text_filter(payload.q) is not None:
        stmt = stmt.where(_text_filter(payload.q))
    if payload.city:
        stmt = stmt.where(Listing.city == payload.city)
    if payload.country:
        stmt = stmt.where(Listing.country == payload.country)
    if payload.min_price is not None:
        stmt = stmt.where(Listing.price_per_night >= payload.min_price)
    if payload.max_price is not None:
        stmt = stmt.where(Listing.price_per_night <= payload.max_price)
    if payload.guests:
        stmt = stmt.where(Listing.max_guests >= payload.guests)
    if payload.min_rating is not None:
        stmt = stmt.where(Listing.rating >= payload.min_rating)

    rows = db.execute(stmt).scalars().all()

    # Tag filter (JSON column -> filter in Python for DB portability).
    if payload.tags:
        wanted = {t.lower() for t in payload.tags}
        rows = [r for r in rows if wanted & {t.lower() for t in (r.tags or [])}]

    # Log the search as a behavioral signal.
    if user and payload.q:
        db.add(Interaction(user_id=user.id, kind="search", query=payload.q))
        db.commit()

    if payload.sort == "price_asc":
        rows.sort(key=lambda l: l.price_per_night)
        scored = [(l, 0.0, "") for l in rows]
    elif payload.sort == "price_desc":
        rows.sort(key=lambda l: l.price_per_night, reverse=True)
        scored = [(l, 0.0, "") for l in rows]
    elif payload.sort == "rating":
        rows.sort(key=lambda l: l.rating, reverse=True)
        scored = [(l, 0.0, "") for l in rows]
    else:  # relevance -> personalized recommender ranking
        scored = recommend(
            db, user if payload.personalize else None, candidates=rows, limit=len(rows) or 1
        )
        # Boost listings whose city actually matches the query to the top, so a
        # "Porto" search leads with Porto even if other places rank higher.
        if payload.q:
            toks = [t for t in payload.q.lower().split() if len(t) >= 3]
            scored.sort(
                key=lambda x: (any(t in x[0].city.lower() for t in toks), x[1]),
                reverse=True,
            )

    scored = scored[: payload.limit]
    results = [
        ScoredListing(
            **ScoredListing.model_validate(listing).model_dump(exclude={"score", "reason"}),
            score=score,
            reason=reason,
        )
        for listing, score, reason in scored
    ]

    response = SearchResponse(total=len(rows), results=results, cached=False)
    cache.set_json(key, {"total": response.total, "results": [r.model_dump() for r in results]})
    return response
