"""Listings: browse, detail, and interaction logging."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Interaction, Listing, User
from ..schemas import InteractionIn, ListingOut
from ..security import get_optional_user

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
