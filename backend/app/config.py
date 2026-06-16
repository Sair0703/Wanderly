"""Application configuration.

Everything is overridable via environment variables so the same code runs
locally (SQLite + in-memory cache + stub LLM) and in production
(PostgreSQL + Redis + OpenAI/Anthropic) without changes.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Travel Recommendation Platform"
    environment: str = "development"  # "production" enables strict checks
    secret_key: str = "dev-secret-change-me"
    token_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # SQLite by default; set DATABASE_URL=postgresql://... in prod.
    database_url: str = "sqlite:///./travel.db"

    # Empty -> in-memory cache. Set REDIS_URL=redis://localhost:6379/0 in prod.
    redis_url: str = ""

    # LLM provider: "stub" (offline, deterministic), "openai", or "anthropic".
    llm_provider: str = "stub"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # --- Security / hardening ---
    # Comma-separated allowed CORS origins. "*" is rejected in production unless
    # the SPA is served same-origin (the default here), in which case CORS is
    # effectively unused. Set to your domain(s) when calling the API cross-origin.
    allowed_origins: str = "*"
    # Comma-separated Host header allowlist ("*" = any). Set to your domain in prod.
    allowed_hosts: str = "*"
    # Redirect http->https and send HSTS (expects a TLS-terminating proxy).
    force_https: bool = False
    # Per-IP rate limits (requests / window seconds).
    rate_limit_auth: int = 10          # register/login attempts
    rate_limit_window: int = 60
    rate_limit_write: int = 30         # bookings/trips/interactions
    # Bootstrap admin: a user registering/logging in with this email becomes admin.
    admin_email: str = ""

    # --- Listing data source ---
    # "osm"    -> real accommodations from OpenStreetMap (Overpass, no key)
    # "seed"   -> curated demo catalog (offline, deterministic)
    # "amadeus"-> Amadeus Self-Service hotel offers (real prices; needs keys)
    data_provider: str = "osm"
    amadeus_api_key: str = ""
    amadeus_api_secret: str = ""

    # --- Outbound booking / affiliate links ---
    # "booking" | "google" | "expedia"
    booking_provider: str = "booking"
    # Your Booking.com affiliate id (aid=...). Empty = plain search link.
    booking_affiliate_id: str = ""

    # Seeding
    auto_seed: bool = True             # populate listings on first run
    seed_demo_users: bool = True       # seed demo login accounts (disable in prod)

    cache_ttl_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
