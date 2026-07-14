import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _retry_after_seconds(response: requests.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _request_with_backoff(
    method: str,
    session: requests.Session,
    url: str,
    retries: int,
    timeout: float,
    **kwargs: Any,
) -> requests.Response | None:
    backoff_sec = 1.0
    for attempt in range(1, retries + 1):
        wait_sec = backoff_sec
        try:
            response = session.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            logger.warning("Request error on attempt %d/%d for %s: %s", attempt, retries, url, exc)
        else:
            if response.status_code == 200:
                return response
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = _retry_after_seconds(response)
                if retry_after is not None:
                    wait_sec = retry_after
                logger.warning(
                    "Retryable status %d on attempt %d/%d for %s (waiting %.1fs)",
                    response.status_code, attempt, retries, url, wait_sec,
                )
            else:
                logger.warning("Non-retryable status %d for %s", response.status_code, url)
                return None

        if attempt < retries:
            time.sleep(wait_sec)
            backoff_sec *= 2

    logger.error("Exhausted retries for %s", url)
    return None


def get_with_backoff(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 3,
    timeout: float = 10.0,
) -> requests.Response | None:
    """GET with exponential backoff on 429/5xx and transient network errors.
    Returns the Response on success, or None if all retries are exhausted."""
    return _request_with_backoff(
        "GET", session, url, retries, timeout, params=params, headers=headers
    )


def post_with_backoff(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    json: Any = None,
    retries: int = 3,
    timeout: float = 10.0,
) -> requests.Response | None:
    """POST with exponential backoff on 429/5xx and transient network errors.
    Returns the Response on success, or None if all retries are exhausted."""
    return _request_with_backoff(
        "POST", session, url, retries, timeout, params=params, headers=headers, json=json
    )
