"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class Preferences(BaseModel):
    budget: Optional[float] = Field(default=200, description="Target nightly budget")
    trip_styles: list[str] = Field(default_factory=list)  # beach, city, adventure...
    interests: list[str] = Field(default_factory=list)  # food, history, nightlife...
    climate: Optional[str] = None  # warm, cold, temperate, any


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    preferences: Preferences = Field(default_factory=Preferences)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    preferences: dict
    is_admin: bool = False
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PreferencesUpdate(BaseModel):
    preferences: Preferences


# ---------- Listings ----------
class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    kind: str
    city: str
    country: str
    lat: float
    lng: float
    price_per_night: float
    rating: float
    review_count: int
    max_guests: int
    tags: list[str]
    amenities: list[str]
    description: str
    image_url: str
    popularity: int
    price_is_estimate: bool = False
    website: str = ""
    booking_url: str = ""
    source: str = "curated"


class ScoredListing(ListingOut):
    score: float = 0.0
    reason: str = ""


# ---------- Search ----------
class SearchRequest(BaseModel):
    q: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    guests: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    min_rating: Optional[float] = None
    sort: str = "relevance"  # relevance | price_asc | price_desc | rating
    personalize: bool = True
    limit: int = 24


class SearchResponse(BaseModel):
    total: int
    results: list[ScoredListing]
    cached: bool = False


# ---------- Interactions ----------
class InteractionIn(BaseModel):
    listing_id: Optional[int] = None
    kind: str = "view"  # view | like | click | book | search
    query: str = ""


# ---------- Bookings ----------
class BookingCreate(BaseModel):
    listing_id: int
    check_in: date
    check_out: date
    guests: int = 1


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    listing_id: int
    check_in: date
    check_out: date
    guests: int
    total_price: float
    status: str
    created_at: datetime
    listing: Optional[ListingOut] = None


# ---------- Trips / Itineraries ----------
class TripRequest(BaseModel):
    destination: str
    days: int = Field(default=3, ge=1, le=14)
    start_date: Optional[date] = None
    interests: list[str] = Field(default_factory=list)
    budget: Optional[float] = None


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    destination: str
    start_date: Optional[date]
    end_date: Optional[date]
    summary: str
    days: list[Any]
    listing_ids: list[int]
    generated_by: str
    created_at: datetime


class SuggestionOut(BaseModel):
    suggestions: list[str]
    generated_by: str


# ---------- Reviews ----------
class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rating: int
    comment: str
    user_name: str
    created_at: datetime


class ReviewSummary(BaseModel):
    average: float
    count: int
    reviews: list[ReviewOut]


# ---------- Favorites ----------
class FavoriteToggleOut(BaseModel):
    saved: bool


# ---------- AI Concierge ----------
class ConciergeRequest(BaseModel):
    message: str = Field(min_length=2, max_length=400)


class ConciergeResponse(BaseModel):
    reply: str
    understood: dict
    results: list[ScoredListing]


# ---------- Analytics ----------
class DashboardOut(BaseModel):
    totals: dict
    engagement_by_day: list[dict]
    top_listings: list[dict]
    popular_tags: list[dict]
    recommendation_quality: dict
    cache_backend: str
    llm_provider: str
