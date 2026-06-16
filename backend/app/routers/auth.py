"""Authentication: register, login, profile, preference updates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..rate_limit import rate_limiter
from ..schemas import (
    PreferencesUpdate,
    TokenOut,
    UserCreate,
    UserLogin,
    UserOut,
)
from ..security import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Throttle credential endpoints per IP to blunt brute-force / signup spam.
_auth_limit = rate_limiter("auth", settings.rate_limit_auth, settings.rate_limit_window)


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_auth_limit)],
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    is_admin = bool(settings.admin_email) and payload.email.lower() == settings.admin_email.lower()
    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        preferences=payload.preferences.model_dump(),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut, dependencies=[Depends(_auth_limit)])
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Promote the configured admin email if not already flagged.
    if settings.admin_email and user.email.lower() == settings.admin_email.lower() and not user.is_admin:
        user.is_admin = True
        db.commit()
        db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get("/me/favorites")
def my_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models import Favorite, Listing
    from ..schemas import ListingOut

    rows = db.execute(
        select(Listing)
        .join(Favorite, Favorite.listing_id == Listing.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    ).scalars().all()
    return {
        "ids": [l.id for l in rows],
        "listings": [ListingOut.model_validate(l).model_dump() for l in rows],
    }


@router.put("/me/preferences", response_model=UserOut)
def update_preferences(
    payload: PreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.preferences = payload.preferences.model_dump()
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
