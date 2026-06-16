"""Dashboard analytics — engagement and recommendation-quality monitoring."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..cache import cache
from ..config import settings
from ..database import get_db
from ..models import Booking, Interaction, Listing, RecommendationLog, Trip, User
from ..schemas import DashboardOut
from ..security import get_admin_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _admin: User = Depends(get_admin_user)):
    totals = {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "listings": db.scalar(select(func.count()).select_from(Listing)) or 0,
        "bookings": db.scalar(select(func.count()).select_from(Booking)) or 0,
        "trips": db.scalar(select(func.count()).select_from(Trip)) or 0,
        "interactions": db.scalar(select(func.count()).select_from(Interaction)) or 0,
        "revenue": round(
            db.scalar(
                select(func.coalesce(func.sum(Booking.total_price), 0.0)).where(
                    Booking.status == "confirmed"
                )
            )
            or 0.0,
            2,
        ),
    }

    # Engagement by day (interaction counts grouped by date).
    day_col = func.date(Interaction.created_at)
    eng_rows = db.execute(
        select(day_col, func.count())
        .group_by(day_col)
        .order_by(day_col)
        .limit(30)
    ).all()
    engagement_by_day = [{"date": str(d), "interactions": c} for d, c in eng_rows]

    # Top listings by popularity.
    top_rows = db.execute(
        select(Listing).order_by(Listing.popularity.desc()).limit(8)
    ).scalars().all()
    top_listings = [
        {
            "id": l.id,
            "title": l.title,
            "city": l.city,
            "popularity": l.popularity,
            "rating": l.rating,
        }
        for l in top_rows
    ]

    # Popular tags across all listings weighted by popularity.
    tag_counter: Counter = Counter()
    for l in db.execute(select(Listing)).scalars():
        for t in l.tags or []:
            tag_counter[t.lower()] += 1 + (l.popularity or 0) // 50
    popular_tags = [{"tag": t, "weight": w} for t, w in tag_counter.most_common(12)]

    # Recommendation quality: acceptance (click/book) rate + avg score.
    rec_total = db.scalar(select(func.count()).select_from(RecommendationLog)) or 0
    rec_accepted = db.scalar(
        select(func.count()).select_from(RecommendationLog).where(
            RecommendationLog.accepted == 1
        )
    ) or 0
    avg_score = db.scalar(select(func.avg(RecommendationLog.score))) or 0.0
    recommendation_quality = {
        "served": rec_total,
        "accepted": rec_accepted,
        "acceptance_rate": round(rec_accepted / rec_total, 3) if rec_total else 0.0,
        "avg_score": round(float(avg_score), 3),
    }

    return DashboardOut(
        totals=totals,
        engagement_by_day=engagement_by_day,
        top_listings=top_listings,
        popular_tags=popular_tags,
        recommendation_quality=recommendation_quality,
        cache_backend=cache.backend,
        llm_provider=settings.llm_provider,
    )
