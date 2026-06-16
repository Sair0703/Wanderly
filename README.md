# Wanderly — AI-Powered Travel Recommendation Platform

A full-stack platform that personalizes travel recommendations and trip discovery
using AI. Users search destinations and stays, a recommendation engine ranks
listings by their preferences and history, an LLM generates personalized
itineraries, and an analytics dashboard monitors engagement and recommendation
quality.

> Built to the resume spec: **Python (FastAPI) backend · React frontend ·
> PostgreSQL · Redis · LLM (OpenAI/Anthropic) · Docker · AWS-ready.**

---

## What it does (end-to-end flow)

```
search destinations & stays
        │
        ▼
recommendation engine ranks listings  ← user preferences + behavioral history
        │
        ▼
LLM generates personalized suggestions & day-by-day itineraries
        │
        ▼
frontend displays listings, maps, and trip plans
        │
        ▼
APIs handle booking-style workflows & user interactions
        │
        ▼
dashboards monitor engagement & recommendation quality
```

Search and recommendations are **cached** (Redis or in-memory) to support
scalable personalization flows.

### Key features

- **AI Concierge** — describe a trip in plain English ("a beachfront place in
  Barcelona under $170 for 4") and it parses budget/guests/vibe/destination and
  returns ranked real stays.
- **Personalized recommendations** — content + behavioral ranking with
  explainable "why this matches you" reasons.
- **AI itinerary planner** — day-by-day trips grounded in real listings.
- **Worldwide real inventory** — real hotels from OpenStreetMap, on-demand for
  any destination on Earth, with **real photos** (property photos where
  available, else a Wikipedia destination photo).
- **Real outbound booking** — deep links to Booking.com (affiliate-ready).
- **Guest reviews**, **wishlists/Saved**, **maps**, and an **admin analytics
  dashboard** (engagement + recommendation quality).

---

## Quick start (zero infrastructure — only Python needed)

The app runs out of the box with **SQLite + in-memory cache + an offline,
deterministic "stub" LLM** — no Postgres, Redis, Docker, or API keys required.

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000**. On first run the catalog is populated with
**real hotels pulled from OpenStreetMap** (no API key needed) and two demo users
are created. Sign in with the pre-filled demo account:

- **Email:** `demo@traveler.io`  **Password:** `demo1234`

### Run the tests

```bash
cd backend && python3 -m pytest -q
```

---

## Production stack (Docker · PostgreSQL · Redis · real LLM)

The same code switches to the full production stack via environment variables.

```bash
# Optional: enable real LLM itineraries
export LLM_PROVIDER=openai           # or "anthropic"
export OPENAI_API_KEY=sk-...

docker compose up --build            # -> http://localhost:8000
```

`docker-compose.yml` brings up:

| Service   | Image              | Role                                   |
|-----------|--------------------|----------------------------------------|
| `db`      | `postgres:16`      | Primary datastore (via SQLAlchemy)     |
| `redis`   | `redis:7`          | Search / recommendation cache          |
| `backend` | FastAPI + uvicorn  | API + serves the React SPA             |

Configuration is read from environment variables (see `.env.example`):
`DATABASE_URL`, `REDIS_URL`, `LLM_PROVIDER`, `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY`, `SECRET_KEY`, `AUTO_SEED`.

---

## Deploy publicly (Render — recommended)

A `render.yaml` blueprint is included. It provisions the web service **and** a
managed PostgreSQL database, wires `DATABASE_URL` automatically, and generates a
strong `SECRET_KEY` for you.

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, select the repo. Render reads `render.yaml`.
3. Set **`ADMIN_EMAIL`** to your email (so you become the admin after signing up).
4. Deploy. Your app is live at `https://<name>.onrender.com` over HTTPS.
5. (Optional) Add `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) as a secret env var
   and set `LLM_PROVIDER` to enable real AI-written itineraries.

The blueprint sets `ENVIRONMENT=production`, `FORCE_HTTPS=true`, and
`SEED_DEMO_USERS=false` so the public demo login is disabled. The app **refuses
to start in production** if the secret key is still the default or demo users
are enabled — a guardrail against accidentally shipping insecure config.

**Railway / Fly.io** work the same way (Dockerfile + a Postgres plugin/volume +
the same env vars); `postgres://` URLs are auto-normalized to the psycopg2 driver.

For horizontal scale (multiple instances), add a Redis instance and set
`REDIS_URL` — the rate limiter and caches then share state across instances.

---

## Real listing data & booking links

The listing catalog and the "Book" buttons use real data, configured by
`DATA_PROVIDER` and `BOOKING_PROVIDER`:

- **Listings (`DATA_PROVIDER=osm`, default):** real accommodations — hotels,
  guest houses, hostels — are fetched from **OpenStreetMap** via the Overpass
  API (no key required), with real names, coordinates, and websites. OSM has no
  nightly rates, so each listing shows a clearly-labelled **estimated** price
  (`≈`) used for ranking/budget filtering; the *real* price is on the partner
  site. Overpass requests try several mirrors and fall back to the curated
  catalog if all fail, so startup never breaks.
- **Global coverage (on-demand):** ~44 cities across every continent are seeded
  at first boot, and the catalog then grows to cover **anywhere on Earth** — when
  someone searches a destination we don't already have (e.g. "Porto", "Cusco",
  "Goa"), it is geocoded via **Nominatim** and its real hotels are fetched live,
  cached, and persisted. So the world is reachable without preloading millions of
  rows. (Verified live: Lima, Porto, Cusco, Honolulu, Krakow, …)
- **Prices with `DATA_PROVIDER=amadeus`:** the Amadeus Self-Service provider
  returns **real nightly prices** (and photos when available) near each seeded
  city; needs `AMADEUS_API_KEY`/`AMADEUS_API_SECRET` and falls back to OSM if
  unset. `DATA_PROVIDER=seed` forces the offline catalog (used by the tests).
- **Booking (`BOOKING_PROVIDER=booking`, default):** every listing has an
  outbound deep link that opens a **real Booking.com search** for that property
  (or Google Hotels / Expedia). Set **`BOOKING_AFFILIATE_ID`** to attach your
  affiliate tag so qualifying bookings earn commission. Outbound clicks are
  logged as signals that feed the recommender.

In the UI, "Check availability on Booking.com →" sends users to the live
listing; "Save to my trips" keeps the in-app planning/booking record (your DB).

## Architecture

```
travel-ai-platform/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, startup seed, serves SPA
│   │   ├── config.py          # env-driven settings (12-factor)
│   │   ├── database.py        # SQLAlchemy engine/session (SQLite⇄Postgres)
│   │   ├── cache.py           # Redis⇄in-memory TTL cache abstraction
│   │   ├── models.py          # User, Listing, Interaction, Booking, Trip, RecommendationLog
│   │   ├── schemas.py         # Pydantic v2 request/response models
│   │   ├── security.py        # PBKDF2 hashing + HMAC signed tokens (stdlib)
│   │   ├── recommender.py     # content-based + behavioral ranking engine
│   │   ├── llm.py             # pluggable LLM: stub / OpenAI / Anthropic
│   │   ├── seed.py            # demo listings + users
│   │   ├── routers/           # auth, listings, search, recommendations, trips, bookings, analytics
│   │   └── web/               # React SPA (index.html, app.js, styles.css)
│   ├── tests/test_api.py      # end-to-end pytest suite
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
└── .env.example
```

### The recommendation engine (`recommender.py`)

Each candidate listing is scored 0–1 by a weighted blend, with an explainable
reason string returned alongside:

| Signal                          | Weight | Source                                  |
|---------------------------------|:------:|-----------------------------------------|
| Preference / interest overlap   | 0.35   | user `trip_styles` + `interests` vs tags |
| Budget proximity                | 0.20   | nightly budget vs listing price          |
| Behavioral history affinity     | 0.20   | tag profile from past views/likes/books  |
| Quality (rating)                | 0.10   | listing rating                           |
| Climate fit                     | 0.10   | preferred climate vs climate tags        |
| Popularity                      | 0.05   | interaction-driven popularity            |

New users (cold start) fall back to popularity/quality ranking. Every served
recommendation is logged to `recommendation_logs`, and the dashboard computes an
**acceptance rate** (clicked/booked) and **average match score** to monitor
quality.

### The LLM layer (`llm.py`)

`LLM_PROVIDER` selects `stub` (default, offline & deterministic), `openai`, or
`anthropic`. Real providers are called via the stdlib (`urllib`) — no SDK
dependency — and **any provider error degrades gracefully back to the stub**, so
the app is never broken by a missing/expired key.

### Frontend

A React single-page app (`backend/app/web/`) with an Explore view (personalized
search + recommendations + AI suggestions), an AI Trip Planner, Bookings, and an
Analytics Dashboard. Maps use **Leaflet + OpenStreetMap** (no API key). It is
served directly by FastAPI, so the whole product runs from one process with no
build step.

---

## API reference

| Method | Path                                   | Description                          |
|--------|----------------------------------------|--------------------------------------|
| POST   | `/api/auth/register`                   | Create account + preferences         |
| POST   | `/api/auth/login`                      | Get bearer token                     |
| GET    | `/api/auth/me`                         | Current user                         |
| PUT    | `/api/auth/me/preferences`             | Update preferences                   |
| GET    | `/api/listings`                        | Browse listings                      |
| GET    | `/api/listings/{id}`                   | Listing detail (logs a view)         |
| POST   | `/api/listings/{id}/interactions`      | Log view/like/click/book             |
| POST   | `/api/search`                          | Filtered + personalized search       |
| GET    | `/api/recommendations`                 | Personalized ranked listings         |
| GET    | `/api/recommendations/suggestions`     | LLM travel suggestions               |
| POST   | `/api/trips`                           | Generate an AI itinerary             |
| GET    | `/api/trips` · `/api/trips/{id}`       | List / fetch trips                   |
| POST   | `/api/bookings`                        | Create a booking                     |
| GET    | `/api/bookings`                        | List bookings                        |
| POST   | `/api/bookings/{id}/cancel`            | Cancel a booking                     |
| GET    | `/api/analytics/dashboard`             | Engagement + recommendation quality  |
| GET    | `/api/health`                          | Health + active backends             |

Interactive OpenAPI docs are available at **`/docs`**.

---

## Deploying to AWS

The container is stateless and 12-factor, so it maps cleanly onto AWS:

- **Compute:** push `backend/` image to **ECR**, run on **ECS Fargate** (or
  Elastic Beanstalk / App Runner). The container serves both API and frontend.
- **Database:** **RDS for PostgreSQL** — set `DATABASE_URL`.
- **Cache:** **ElastiCache for Redis** — set `REDIS_URL`.
- **Secrets:** `SECRET_KEY`, `OPENAI_API_KEY` via **AWS Secrets Manager** /
  SSM Parameter Store.
- **Edge:** **ALB** in front of the service; **CloudFront** for static assets.
- The frontend can alternatively be built and hosted on **S3 + CloudFront**,
  pointing at the API's domain.

---

## Security

Hardening applied so the app is safe to expose publicly:

- **Passwords** hashed with PBKDF2-HMAC-SHA256 (120k rounds); **sessions** are
  HMAC-signed, expiring bearer tokens (stdlib — no extra crypto deps).
- **Production guardrail:** the app refuses to boot in `ENVIRONMENT=production`
  if `SECRET_KEY` is the default or demo users are enabled.
- **Rate limiting** per IP on auth (`RATE_LIMIT_AUTH`) and write endpoints
  (`RATE_LIMIT_WRITE`) — blunts brute-force and spam. Returns HTTP 429.
- **HTTPS:** `FORCE_HTTPS=true` redirects http→https and sends HSTS (behind the
  platform's TLS proxy via `--proxy-headers`).
- **Security headers** on every response: CSP, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- **CORS** is configurable and never pairs a wildcard origin with credentials;
  the SPA is served same-origin so cross-origin access is closed by default.
- **Trusted hosts** allowlist via `ALLOWED_HOSTS`.
- **Admin-only analytics:** the dashboard requires an admin account
  (bootstrap via `ADMIN_EMAIL`); regular users can't see platform-wide data.
- **No public demo login in prod** (`SEED_DEMO_USERS=false`).
- SQL injection is not a concern (queries are parameterized via SQLAlchemy).

**Further hardening worth doing as you grow:** move tokens from `localStorage`
to httpOnly cookies (with CSRF protection) to reduce XSS token theft, add email
verification + password reset, and precompile the frontend (below).

## Notes

- The React frontend uses in-browser Babel for a zero-build demo. For production,
  precompile (Vite/esbuild) and serve from a CDN — this also lets you tighten the
  CSP by removing `unsafe-eval`/`unsafe-inline`.
