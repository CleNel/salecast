import logging
import time
from collections.abc import Iterator
from typing import Any

import requests

from salecast.clients._http import get_with_backoff

logger = logging.getLogger(__name__)

STEAMSPY_URL = "https://steamspy.com/api.php"


def get_all_page(page: int, session: requests.Session | None = None) -> list[dict[str, Any]] | None:
    """Fetches one page (up to 1000 apps) of SteamSpy's bulk 'all' listing,
    sorted by owner count descending.

    Returns:
      - a list of app dicts on success
      - [] if the page is genuinely empty (valid JSON, no entries -> real end of catalog)
      - None if the request failed or SteamSpy returned a non-JSON body
        (e.g. its "Connection failed: Too many connections" overload message,
        which comes back with HTTP 200 and must not be mistaken for end-of-catalog)
    """
    session = session or requests.Session()
    response = get_with_backoff(session, STEAMSPY_URL, params={"request": "all", "page": page})
    if response is None:
        return None
    try:
        payload = response.json()
    except ValueError:
        logger.warning(
            "Non-JSON SteamSpy response for page %d (likely rate-limited): %r",
            page, response.text[:80],
        )
        return None
    if not payload:
        return []
    return list(payload.values())


def iter_all_apps(
    delay_sec: float = 1.0, max_pages: int = 150, retries_per_page: int = 5
) -> Iterator[dict[str, Any]]:
    """Pages through SteamSpy's entire 'all' catalog, yielding one app record
    at a time. Stops when a page is confirmed genuinely empty. Retries
    transient failures (e.g. SteamSpy's overload message) with backoff
    before giving up on a page."""
    session = requests.Session()
    for page in range(max_pages):
        backoff_sec = delay_sec * 2
        apps = None
        for attempt in range(1, retries_per_page + 1):
            apps = get_all_page(page, session=session)
            if apps is not None:
                break
            logger.info(
                "Retrying SteamSpy page %d (attempt %d/%d) after %.1fs",
                page, attempt, retries_per_page, backoff_sec,
            )
            time.sleep(backoff_sec)
            backoff_sec *= 2

        if apps is None:
            logger.error(
                "Giving up on SteamSpy page %d after %d attempts; stopping pagination "
                "(catalog coverage may be incomplete)",
                page, retries_per_page,
            )
            return
        if not apps:
            logger.info("SteamSpy catalog exhausted at page %d", page)
            return

        yield from apps
        time.sleep(delay_sec)
