"""FastAPI application entrypoint.

Wires routers, security middleware (CORS, trusted hosts, HTTPS/HSTS, security
headers), startup DB init + seeding, health check, and serves the React SPA.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .cache import cache
from .config import settings
from .database import SessionLocal, init_db
from .routers import (
    analytics,
    auth,
    bookings,
    concierge,
    listings,
    recommendations,
    search,
    trips,
)
from .seed import seed_demo_users, seed_listings_if_empty
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).parent / "web"

# CDNs the SPA legitimately loads (React, Babel, Leaflet) + map tiles + images.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' https://unpkg.com 'unsafe-inline'; "
    "img-src 'self' https: data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'"
)


def _check_production_config() -> None:
    if settings.is_production:
        problems = []
        if settings.secret_key == "dev-secret-change-me":
            problems.append("SECRET_KEY is still the default — set a strong random value.")
        if settings.seed_demo_users:
            problems.append("SEED_DEMO_USERS is true in production — disable the demo login.")
        if problems:
            raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(problems))


def _seed_listings_bg() -> None:
    """Populate listings off the request path so startup is instant.

    The global OSM fetch + photo lookups take ~1 min on first boot; doing it
    synchronously would block the server (and fail the platform health check).
    On-demand search works immediately regardless; this just fills the catalog.
    """
    try:
        with SessionLocal() as db:
            if seed_listings_if_empty(db):
                print("[startup] Background listing seed complete.")
    except Exception as exc:  # pragma: no cover
        print(f"[startup] Background seed failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_production_config()
    init_db()
    if settings.auto_seed:
        # Demo users are seeded synchronously (instant) so login works at once.
        with SessionLocal() as db:
            seed_demo_users(db)
        if settings.data_provider.lower() == "seed":
            with SessionLocal() as db:  # deterministic, offline -> synchronous
                seed_listings_if_empty(db)
        else:  # OSM/Amadeus may hit the network -> fill in the background
            threading.Thread(target=_seed_listings_bg, daemon=True).start()
    print(f"[startup] env={settings.environment} cache={cache.backend} "
          f"llm={settings.llm_provider} https={settings.force_https}")
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add hardening headers and (optionally) force HTTPS behind a TLS proxy."""

    async def dispatch(self, request: Request, call_next):
        if settings.force_https:
            proto = request.headers.get("x-forwarded-proto", request.url.scheme)
            if proto == "http":
                https_url = request.url.replace(scheme="https")
                return RedirectResponse(str(https_url), status_code=307)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP
        if settings.force_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

if settings.hosts_list and settings.hosts_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts_list)

# CORS: the SPA is served same-origin, so this only matters for cross-origin API
# clients. Never combine a wildcard origin with credentials.
_origins = settings.origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, listings, search, recommendations, trips, bookings, analytics, concierge):
    app.include_router(r.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "cache": cache.backend,
        "llm_provider": settings.llm_provider,
        "environment": settings.environment,
    }


# Serve the SPA frontend (mounted last so /api routes take precedence).
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(WEB_DIR / "index.html"))
