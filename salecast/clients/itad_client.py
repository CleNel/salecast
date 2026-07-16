import logging
from typing import Any

import requests

from salecast import config
from salecast.clients._http import get_with_backoff, post_with_backoff

logger = logging.getLogger(__name__)

BASE_URL = "https://api.isthereanydeal.com"
LOOKUP_URL = f"{BASE_URL}/games/lookup/v1"
HISTORY_LOW_URL = f"{BASE_URL}/games/historylow/v1"
HISTORY_URL = f"{BASE_URL}/games/history/v2"

# Steam's shop id in ITAD's shop registry - we only track Steam prices.
STEAM_SHOP_ID = 61


class MissingApiKeyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "ITAD_API_KEY not set - see .env.example and sign up for a free key at "
            "https://isthereanydeal.com/apps/my/"
        )


def _require_api_key() -> str:
    if not config.ITAD_API_KEY:
        raise MissingApiKeyError()
    return config.ITAD_API_KEY


def resolve_itad_id(steam_app_id: int, session: requests.Session | None = None) -> str | None:
    """Resolves a Steam app_id to ITAD's internal game id (a UUID).
    Returns None if ITAD has no matching game."""
    api_key = _require_api_key()
    session = session or requests.Session()
    response = get_with_backoff(
        session, LOOKUP_URL, params={"key": api_key, "appid": steam_app_id},
        retries=config.ITAD_RETRIES,
    )
    if response is None:
        return None

    payload = response.json()
    if not payload.get("found"):
        return None
    return payload.get("game", {}).get("id")


def get_historical_low(
    itad_id: str, region: str = "US", session: requests.Session | None = None
) -> dict[str, Any] | None:
    """Fetches the all-time-low price for a resolved ITAD game id.
    Returns {"price": float, "currency": str, "shop": str} or None if
    no historical low is on record."""
    api_key = _require_api_key()
    session = session or requests.Session()
    response = post_with_backoff(
        session,
        HISTORY_LOW_URL,
        params={"key": api_key, "country": region},
        json=[itad_id],
        retries=config.ITAD_RETRIES,
    )
    if response is None:
        return None

    results = response.json()
    if not results:
        return None

    entry = results[0]
    low = entry.get("low")
    if not low:
        return None

    price = low.get("price") or {}
    return {
        "price": price.get("amount"),
        "currency": price.get("currency"),
        "shop": (low.get("shop") or {}).get("name"),
    }


def get_price_history(
    itad_id: str,
    since: str | None = None,
    region: str = "US",
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetches the full log of Steam price/discount changes for a resolved
    ITAD game id (GET /games/history/v2), optionally bounded by since (an
    ISO 8601 datetime - pass the game's release date to get its whole
    lifetime). Returns a list of {"date": "YYYY-MM-DD", "price": float,
    "discount_pct": int} ordered as ITAD returns them (newest first).
    Empty list if ITAD has no Steam price history on record."""
    api_key = _require_api_key()
    session = session or requests.Session()
    params = {"key": api_key, "id": itad_id, "country": region, "shops": STEAM_SHOP_ID}
    if since is not None:
        params["since"] = since

    response = get_with_backoff(session, HISTORY_URL, params=params, retries=config.ITAD_RETRIES)
    if response is None:
        return []

    events = response.json()
    history = []
    for event in events or []:
        deal = event.get("deal") or {}
        price = (deal.get("price") or {}).get("amount")
        timestamp = event.get("timestamp")
        if price is None or not timestamp:
            continue
        history.append(
            {
                "date": timestamp[:10],
                "price": price,
                "discount_pct": deal.get("cut"),
            }
        )
    return history
