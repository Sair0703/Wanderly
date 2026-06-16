"""Booking-style workflows."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cache import cache
from ..config import settings
from ..database import get_db
from ..models import Booking, Interaction, Listing, RecommendationLog, User
from ..rate_limit import rate_limiter
from ..schemas import BookingCreate, BookingOut
from ..security import get_current_user

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

_write_limit = rate_limiter("bookings", settings.rate_limit_write, settings.rate_limit_window)


@router.post("", response_model=BookingOut, status_code=201, dependencies=[Depends(_write_limit)])
def create_booking(
    payload: BookingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing = db.get(Listing, payload.listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if payload.check_out <= payload.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    if payload.guests > listing.max_guests:
        raise HTTPException(
            status_code=400, detail=f"Max {listing.max_guests} guests for this stay"
        )

    nights = (payload.check_out - payload.check_in).days
    total = round(nights * listing.price_per_night, 2)

    booking = Booking(
        user_id=user.id,
        listing_id=listing.id,
        check_in=payload.check_in,
        check_out=payload.check_out,
        guests=payload.guests,
        total_price=total,
        status="confirmed",
    )
    db.add(booking)

    # Strong behavioral signal + recommendation acceptance tracking.
    db.add(Interaction(user_id=user.id, listing_id=listing.id, kind="book", weight=3.0))
    listing.popularity = (listing.popularity or 0) + 5
    rec = db.scalar(
        select(RecommendationLog)
        .where(RecommendationLog.user_id == user.id, RecommendationLog.listing_id == listing.id)
        .order_by(RecommendationLog.created_at.desc())
    )
    if rec:
        rec.accepted = 1

    db.commit()
    db.refresh(booking)
    cache.invalidate_prefix(f"recs:{user.id}")
    return BookingOut.model_validate(booking)


@router.get("", response_model=list[BookingOut])
def list_bookings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())
    ).scalars().all()
    return [BookingOut.model_validate(b) for b in rows]


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.user_id != user.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.status = "cancelled"
    db.commit()
    db.refresh(booking)
    return BookingOut.model_validate(booking)
