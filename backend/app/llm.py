"""LLM service for itinerary + suggestion generation.

Pluggable provider:
  * "stub"      -> deterministic, offline generator (default; no API key needed)
  * "openai"    -> OpenAI Chat Completions
  * "anthropic" -> Anthropic Messages API

Real providers are called via urllib (stdlib) so no SDK dependency is required.
Any provider error degrades gracefully to the stub so the app stays functional.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional

from .config import settings


# --------------------------------------------------------------------------- #
# Deterministic offline generator
# --------------------------------------------------------------------------- #
_ACTIVITY_BANK = {
    "food": ["a local food market tour", "a regional cooking class", "dinner at a celebrated bistro"],
    "history": ["the old town walking tour", "the national museum", "a historic landmark visit"],
    "beach": ["a morning at the main beach", "a sunset coastal walk", "a snorkeling trip"],
    "nightlife": ["a rooftop bar crawl", "a live music venue", "the night market"],
    "adventure": ["a guided hike", "a kayaking excursion", "a zipline park"],
    "art": ["the contemporary art gallery", "a street-art district stroll", "an artisan workshop"],
    "nature": ["a botanical garden", "a scenic viewpoint", "a nature reserve"],
    "relax": ["a spa afternoon", "a slow café morning", "a riverside picnic"],
    "city": ["the downtown landmarks loop", "a rooftop skyline view", "a neighborhood food walk"],
    "shopping": ["the boutique shopping street", "a vintage market", "a designer district"],
}
_DEFAULT_INTERESTS = ["city", "food", "history", "nature"]


def _stub_itinerary(
    destination: str, days: int, interests: list[str], stays: list[dict]
) -> dict[str, Any]:
    interests = [i.lower() for i in interests] or _DEFAULT_INTERESTS
    times = ["Morning", "Afternoon", "Evening"]
    plan_days = []
    for d in range(1, days + 1):
        focus = interests[(d - 1) % len(interests)]
        bank = _ACTIVITY_BANK.get(focus, _ACTIVITY_BANK["city"])
        from .booking_links import build_activity_url
        activities = [
            {"time": times[i], "name": bank[i % len(bank)], "category": focus.capitalize(),
             "price": 0.0, "price_label": "", "book_url": build_activity_url(bank[i % len(bank)], destination)}
            for i in range(3)
        ]
        plan_days.append(
            {
                "day": d,
                "title": f"Day {d}: {focus.capitalize()} in {destination}",
                "activities": activities,
                "est_cost": 0,
            }
        )
    stay_line = (
        f" We suggest staying at {stays[0]['title']}." if stays else ""
    )
    summary = (
        f"A {days}-day personalized trip to {destination} focused on "
        f"{', '.join(interests[:3])}.{stay_line}"
    )
    return {"title": f"{days}-Day {destination} Trip", "summary": summary, "days": plan_days}


def _stub_suggestions(prefs: dict) -> list[str]:
    styles = prefs.get("trip_styles") or ["city break"]
    interests = prefs.get("interests") or ["food", "culture"]
    budget = prefs.get("budget", 200)
    picks = [
        f"A {styles[0]} weekend with great {interests[0]} — around ${int(budget)}/night.",
        f"An off-season escape leaning into {', '.join(interests[:2])}.",
        f"A longer slow-travel route mixing {styles[0]} stops and hidden gems.",
    ]
    return picks


# --------------------------------------------------------------------------- #
# Remote providers (stdlib urllib)
# --------------------------------------------------------------------------- #
def _http_json(url: str, headers: dict, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _extract_json(text: str) -> Optional[dict]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _openai_itinerary(prompt: str) -> Optional[dict]:
    data = _http_json(
        "https://api.openai.com/v1/chat/completions",
        {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        {
            "model": settings.openai_model,
            "messages": [
                {"role": "system", "content": "You are a travel planner. Respond ONLY with JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        },
    )
    return _extract_json(data["choices"][0]["message"]["content"])


def _anthropic_itinerary(prompt: str) -> Optional[dict]:
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        {
            "model": settings.anthropic_model,
            "max_tokens": 1500,
            "messages": [
                {"role": "user", "content": prompt + "\n\nRespond ONLY with JSON."}
            ],
        },
    )
    return _extract_json(data["content"][0]["text"])


def _prompt(destination: str, days: int, interests: list[str], budget: Optional[float]) -> str:
    return (
        f"Create a {days}-day travel itinerary for {destination}. "
        f"Traveler interests: {', '.join(interests) or 'general'}. "
        f"Nightly budget: ${budget or 'flexible'}. "
        'Return JSON: {"title": str, "summary": str, '
        '"days": [{"day": int, "title": str, "activities": [str, str, str]}]}'
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_itinerary(
    destination: str,
    days: int,
    interests: list[str],
    stays: list[dict],
    budget: Optional[float] = None,
) -> tuple[dict[str, Any], str]:
    provider = settings.llm_provider
    try:
        if provider == "openai" and settings.openai_api_key:
            result = _openai_itinerary(_prompt(destination, days, interests, budget))
            if result and result.get("days"):
                return result, "openai"
        elif provider == "anthropic" and settings.anthropic_api_key:
            result = _anthropic_itinerary(_prompt(destination, days, interests, budget))
            if result and result.get("days"):
                return result, "anthropic"
    except Exception:
        pass  # fall through to deterministic stub
    return _stub_itinerary(destination, days, interests, stays), "stub"


def generate_suggestions(prefs: dict) -> tuple[list[str], str]:
    # Suggestions use the same provider machinery but the stub is always safe.
    return _stub_suggestions(prefs), "stub"


def _stub_review_summary(reviews: list[dict]) -> str:
    n = len(reviews)
    if not n:
        return ""
    avg = round(sum(r["rating"] for r in reviews) / n, 1)
    pos = [r["comment"] for r in reviews if r["rating"] >= 4 and r.get("comment")]
    neg = [r["comment"] for r in reviews if r["rating"] <= 2 and r.get("comment")]
    parts = [f"Guests rate this {avg}/5 across {n} review{'s' if n != 1 else ''}."]
    if pos:
        parts.append(f"Loved: “{pos[0][:90]}”")
    if neg:
        parts.append(f"Some note: “{neg[0][:90]}”")
    return " ".join(parts)


def _remote_review_summary(reviews: list[dict]) -> Optional[str]:
    joined = "\n".join(f"- {r['rating']}/5: {r.get('comment', '')}" for r in reviews[:30])
    prompt = (
        "Summarize these guest reviews in 1-2 sentences for a traveler deciding "
        "whether to book. Mention recurring praise and any concerns.\n" + joined
    )
    try:
        if settings.llm_provider == "openai" and settings.openai_api_key:
            data = _http_json(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                {"model": settings.openai_model,
                 "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
            )
            return data["choices"][0]["message"]["content"].strip()
        if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
            data = _http_json(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
                {"model": settings.anthropic_model, "max_tokens": 200,
                 "messages": [{"role": "user", "content": prompt}]},
            )
            return data["content"][0]["text"].strip()
    except Exception:
        pass
    return None


def summarize_reviews(reviews: list[dict]) -> tuple[str, str]:
    """Return (summary, provider). Empty string if there are no reviews."""
    if not reviews:
        return "", "none"
    if settings.llm_provider in ("openai", "anthropic"):
        remote = _remote_review_summary(reviews)
        if remote:
            return remote, settings.llm_provider
    return _stub_review_summary(reviews), "stub"
