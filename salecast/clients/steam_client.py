import logging
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import requests

from salecast.clients._http import get_with_backoff

logger = logging.getLogger(__name__)

APP_LIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

_RELEASE_DATE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B %Y", "%b %Y", "%Y")


def _parse_release_date(raw: str | None) -> str | None:
    """Best-effort parse of Steam's free-text release_date.date into ISO 8601.
    Returns None if it can't be parsed (e.g. empty string, 'Coming soon')."""
    if not raw:
        return None
    for fmt in _RELEASE_DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    logger.debug("Could not parse release date: %r", raw)
    return None


def get_app_list(session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Returns [{"appid": int, "name": str}, ...] for the full Steam catalog."""
    session = session or requests.Session()
    response = get_with_backoff(session, APP_LIST_URL)
    if response is None:
        return []
    return response.json().get("applist", {}).get("apps", [])


def get_app_details(
    app_id: int, session: requests.Session | None = None, retries: int = 3
) -> dict[str, Any] | None:
    """Fetches and parses appdetails for a single app_id. Returns a dict with
    the fields SaleCast needs, or None if the app has no store page, the
    request failed, or the app isn't a 'game' entry."""
    # Steam infers price_overview's currency from the caller's IP when "cc"
    # is omitted - without pinning it, a scraper running on infra whose
    # egress region varies gets USD one run and e.g. INR/KRW the next, and
    # "final" (assumed to be USD cents below) silently corrupts.
    session = session or requests.Session()
    response = get_with_backoff(
        session, APP_DETAILS_URL, params={"appids": app_id, "cc": "us"}, retries=retries
    )
    if response is None:
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.warning("Malformed JSON in appdetails response for app %d", app_id)
        return None

    entry = payload.get(str(app_id))
    if not entry or not entry.get("success"):
        return None

    data = entry.get("data")
    if not data:
        return None

    price_overview = data.get("price_overview") or {}
    genres = data.get("genres") or []
    publishers = data.get("publishers") or []
    recommendations = data.get("recommendations") or {}

    return {
        "app_id": app_id,
        "name": data.get("name"),
        "type": data.get("type"),
        "genre": genres[0]["description"] if genres else None,
        "publisher": publishers[0] if publishers else None,
        "release_date": _parse_release_date((data.get("release_date") or {}).get("date")),
        "is_released": not (data.get("release_date") or {}).get("coming_soon", False),
        "is_free": bool(data.get("is_free", False)),
        "price": (price_overview.get("final") or 0) / 100 if price_overview else None,
        # Steam's own list price, not derived from price/discount_pct - a
        # discounted price is rounded to the cent (e.g. $39.99 at 75% off
        # becomes $9.99, not the exact $9.9975), so back-solving
        # price / (1 - discount_pct/100) recovers $39.96, not the real
        # $39.99. Capture it directly instead.
        "original_price": (price_overview.get("initial") or 0) / 100 if price_overview else None,
        "currency": price_overview.get("currency"),
        "discount_pct": price_overview.get("discount_percent"),
        "review_count": recommendations.get("total"),
    }


def rate_limited_appdetails_batch(
    app_ids: list[int], delay_sec: float = 1.5
) -> Iterator[tuple[int, dict[str, Any] | None]]:
    """Yields (app_id, details) one at a time, sleeping delay_sec between calls."""
    session = requests.Session()
    for app_id in app_ids:
        yield app_id, get_app_details(app_id, session=session)
        time.sleep(delay_sec)
