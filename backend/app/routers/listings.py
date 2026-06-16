"""Listings: browse, detail, and interaction logging."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Favorite, Interaction, Listing, Review, User
from ..schemas import (
    FavoriteToggleOut,
    InteractionIn,
    ListingOut,
    ReviewCreate,
    ReviewOut,
    ReviewSummary,
)
from ..security import get_current_user, get_optional_user

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.get("", response_model=list[ListingOut])
def list_listings(
    city: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Listing)
    if city:
        stmt = stmt.where(Listing.city == city)
    if country:
        stmt = stmt.where(Listing.country == country)
    stmt = stmt.order_by(Listing.rating.desc()).offset(offset).limit(min(limit, 100))
    return db.execute(stmt).scalars().all()


@router.get("/cities", response_model=list[str])
def list_cities(db: Session = Depends(get_db)):
    rows = db.execute(select(Listing.city).distinct().order_by(Listing.city)).scalars()
    return list(rows)


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    # Count a view as engagement + a behavioral signal.
    listing.popularity = (listing.popularity or 0) + 1
    if user:
        db.add(Interaction(user_id=user.id, listing_id=listing.id, kind="view"))
    db.commit()
    db.refresh(listing)
    return listing


@router.post("/{listing_id}/interactions", status_code=201)
def log_interaction(
    listing_id: int,
    payload: InteractionIn,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if user:
        db.add(Interaction(
            user_id=user.id, listing_id=listing_id,
            kind=payload.kind, query=payload.query,
        ))
    if payload.kind in {"like", "click", "book"}:
        listing.popularity = (listing.popularity or 0) + 2
    db.commit()
    return {"ok": True}


@router.post("/{listing_id}/favorite", response_model=FavoriteToggleOut)
def toggle_favorite(
    listing_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.get(Listing, listing_id):
        raise HTTPException(status_code=404, detail="Listing not found")
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.listing_id == listing_id)
    )
    if existing:
        db.delete(existing)
        db.commit()
        return FavoriteToggleOut(saved=False)
    db.add(Favorite(user_id=user.id, listing_id=listing_id))
    db.add(Interaction(user_id=user.id, listing_id=listing_id, kind="like", weight=2.0))
    db.commit()
    return FavoriteToggleOut(saved=True)


@router.post("/{listing_id}/reviews", response_model=ReviewOut, status_code=201)
def add_review(
    listing_id: int,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.get(Listing, listing_id):
        raise HTTPException(status_code=404, detail="Listing not found")
    review = Review(
        user_id=user.id, listing_id=listing_id,
        rating=payload.rating, comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return ReviewOut(
        id=review.id, rating=review.rating, comment=review.comment,
        user_name=user.name, created_at=review.created_at,
    )


@router.get("/{listing_id}/reviews", response_model=ReviewSummary)
def list_reviews(listing_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Review, User.name)
        .join(User, Review.user_id == User.id)
        .where(Review.listing_id == listing_id)
        .order_by(Review.created_at.desc())
    ).all()
    reviews = [
        ReviewOut(id=r.id, rating=r.rating, comment=r.comment, user_name=name, created_at=r.created_at)
        for r, name in rows
    ]
    avg = round(sum(rv.rating for rv in reviews) / len(reviews), 2) if reviews else 0.0
    return ReviewSummary(average=avg, count=len(reviews), reviews=reviews)
