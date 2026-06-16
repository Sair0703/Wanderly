"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    # Preferences drive personalization: budget, trip_styles, interests, climate.
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="stay")  # stay | destination
    city: Mapped[str] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(120), index=True)
    lat: Mapped[float] = mapped_column(Float, default=0.0)
    lng: Mapped[float] = mapped_column(Float, default=0.0)
    price_per_night: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    max_guests: Mapped[int] = mapped_column(Integer, default=2)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    amenities: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    # Real-data fields
    price_is_estimate: Mapped[bool] = mapped_column(default=False)
    website: Mapped[str] = mapped_column(String(500), default="")
    booking_url: Mapped[str] = mapped_column(String(700), default="")
    source: Mapped[str] = mapped_column(String(40), default="curated")  # openstreetmap | curated | amadeus
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Interaction(Base):
    """User behavior signal used by the recommender (view/like/click/book)."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    listing_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("listings.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # view | like | click | book | search
    query: Mapped[str] = mapped_column(String(255), default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="interactions")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    guests: Mapped[int] = mapped_column(Integer, default=1)
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="bookings")
    listing: Mapped["Listing"] = relationship()


class Trip(Base):
    """An LLM-generated personalized itinerary."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    days: Mapped[list] = mapped_column(JSON, default=list)  # [{day, title, activities[]}]
    listing_ids: Mapped[list] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(20), default="stub")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="trips")


class RecommendationLog(Base):
    """Records served recommendations to monitor recommendation quality."""

    __tablename__ = "recommendation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    accepted: Mapped[int] = mapped_column(Integer, default=0)  # 0/1 clicked or booked
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
