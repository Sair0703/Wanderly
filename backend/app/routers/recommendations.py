"""Personalized recommendations + LLM-generated travel suggestions."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..cache import cache
from ..database import get_db
from ..llm import generate_suggestions
from ..models import RecommendationLog, User
from ..pricing import annotate_deals
from ..recommender import recommend
from ..schemas import ScoredListing, SuggestionOut
from ..security import get_current_user

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[ScoredListing])
def my_recommendations(
    limit: int = 12,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = f"recs:{user.id}:{limit}"
    cached = cache.get_json(key)
    if cached:
        return [ScoredListing(**r) for r in cached]

    scored = recommend(db, user, limit=limit)

    # Log served recommendations for quality monitoring.
    for listing, score, reason in scored:
        db.add(RecommendationLog(
            user_id=user.id, listing_id=listing.id, score=score, reason=reason
        ))
    db.commit()

    results = [
        ScoredListing(
            **ScoredListing.model_validate(listing).model_dump(exclude={"score", "reason"}),
            score=score,
            reason=reason,
        )
        for listing, score, reason in scored
    ]
    annotate_deals(db, results)
    cache.set_json(key, [r.model_dump() for r in results], ttl=120)
    return results


@router.get("/suggestions", response_model=SuggestionOut)
def my_suggestions(user: User = Depends(get_current_user)):
    suggestions, provider = generate_suggestions(user.preferences or {})
    return SuggestionOut(suggestions=suggestions, generated_by=provider)
