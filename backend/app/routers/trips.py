"""Trips / itineraries — LLM-generated, personalized day-by-day plans."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..llm import generate_itinerary
from ..models import Listing, Trip, User
from ..rate_limit import rate_limiter
from ..schemas import TripOut, TripRequest
from ..security import get_current_user

router = APIRouter(prefix="/api/trips", tags=["trips"])

_write_limit = rate_limiter("trips", settings.rate_limit_write, settings.rate_limit_window)


@router.post("", response_model=TripOut, status_code=201, dependencies=[Depends(_write_limit)])
def create_trip(
    payload: TripRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = user.preferences or {}
    interests = payload.interests or prefs.get("interests", []) + prefs.get("trip_styles", [])
    budget = payload.budget or prefs.get("budget")

    # Find candidate stays in the destination to ground the itinerary.
    like = f"%{payload.destination.lower()}%"
    stays = db.execute(
        select(Listing)
        .where((Listing.city.ilike(like)) | (Listing.country.ilike(like)))
        .order_by(Listing.rating.desc())
        .limit(5)
    ).scalars().all()
    stay_dicts = [{"id": s.id, "title": s.title, "city": s.city} for s in stays]

    plan, provider = generate_itinerary(
        payload.destination, payload.days, interests, stay_dicts, budget
    )

    end_date = None
    if payload.start_date:
        end_date = payload.start_date + timedelta(days=payload.days)

    trip = Trip(
        user_id=user.id,
        title=plan.get("title", f"{payload.days}-Day {payload.destination} Trip"),
        destination=payload.destination,
        start_date=payload.start_date,
        end_date=end_date,
        summary=plan.get("summary", ""),
        days=plan.get("days", []),
        listing_ids=[s["id"] for s in stay_dicts],
        generated_by=provider,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.get("", response_model=list[TripOut])
def list_trips(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.execute(
        select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc())
    ).scalars().all()


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if not trip or trip.user_id != user.id:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if not trip or trip.user_id != user.id:
        raise HTTPException(status_code=404, detail="Trip not found")
    db.delete(trip)
    db.commit()
