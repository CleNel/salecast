import logging
import sqlite3
import time
from datetime import date, datetime

from salecast import config
from salecast.clients import steam_client, steamspy_client

logger = logging.getLogger(__name__)


def months_since(release_date_iso: str, today: date | None = None) -> float:
    """Months elapsed between an ISO 8601 release date and today (or a
    given reference date), as a float."""
    today = today or date.today()
    released = datetime.strptime(release_date_iso, "%Y-%m-%d").date()
    days = (today - released).days
    return days / 30.44


def build_review_candidate_set(
    min_reviews: int,
    delay_sec: float = config.STEAMSPY_DELAY_SEC,
    max_pages: int = config.STEAMSPY_MAX_PAGES,
) -> dict[int, dict]:
    """Pages through SteamSpy's full catalog, keeping app_ids whose
    positive+negative review count clears min_reviews. Cheap pre-filter
    before hitting Steam's per-app appdetails endpoint. Returns
    {app_id: {"review_count": int, "review_score_pct": float}}.

    SteamSpy's positive+negative count is the value actually used to
    enforce min_reviews, and is what gets stored/reported downstream —
    Steam's own appdetails 'recommendations.total' field measures something
    different and is frequently much lower (or absent) even for games with
    a large, well-established SteamSpy review count, so it must not be used
    as the source of truth for the threshold that was actually applied."""
    candidates: dict[int, dict] = {}
    for app in steamspy_client.iter_all_apps(delay_sec=delay_sec, max_pages=max_pages):
        positive = app.get("positive") or 0
        negative = app.get("negative") or 0
        reviews = positive + negative
        if reviews >= min_reviews:
            candidates[app["appid"]] = {
                "review_count": reviews,
                "review_score_pct": round(100 * positive / reviews, 1) if reviews else None,
            }
    logger.info("SteamSpy pre-filter: %d candidates with >= %d reviews", len(candidates), min_reviews)
    return candidates


def enrich_and_filter_candidates(
    candidate_ids: list[int],
    min_age_months: int,
    delay_sec: float = config.STEAM_APPDETAILS_DELAY_SEC,
    conn: sqlite3.Connection | None = None,
    target_count: int | None = None,
    progress_every: int = config.DISCOVERY_PROGRESS_INTERVAL,
    review_data: dict[int, dict] | None = None,
) -> list[dict]:
    """Calls Steam's appdetails on each candidate (in the order given -
    callers should pass candidates sorted by descending signal so the most
    promising games are enriched first), keeping only entries that are
    actual games (not DLC/soundtracks/demos), have a parseable release
    date, and are at least min_age_months old.

    review_data, if given, should be the {app_id: {"review_count",
    "review_score_pct"}} dict from build_review_candidate_set — its values
    are stored as-is since they reflect the review threshold that was
    actually enforced. Falls back to Steam appdetails' own review count
    when review_data has no entry for a candidate (e.g. when this function
    is called standalone, outside the normal discovery.main() flow).

    If conn is given, each surviving game is inserted immediately
    (idempotent), so progress is visible in the DB and survives a crash
    or interruption partway through a long run.

    If target_count is given, stops early once that many survivors have
    been found (candidate_ids should already be priority-ordered for this
    to select the best candidates rather than an arbitrary subset)."""
    survivors: list[dict] = []
    today = date.today()
    start = time.time()
    processed = 0
    review_data = review_data or {}

    for app_id, details in steam_client.rate_limited_appdetails_batch(
        candidate_ids, delay_sec=delay_sec
    ):
        processed += 1
        keep = (
            details is not None
            and details.get("type") == "game"
            and details.get("is_released")
            and not details.get("is_free")
            and details.get("release_date")
            and months_since(details["release_date"], today) >= min_age_months
        )

        if keep:
            reviews = review_data.get(app_id, {})
            game = {
                "app_id": app_id,
                "name": details.get("name"),
                "genre": details.get("genre"),
                "publisher": details.get("publisher"),
                "release_date": details.get("release_date"),
                "review_count": reviews.get("review_count", details.get("review_count")),
                "review_score_pct": reviews.get("review_score_pct"),
                "first_tracked_date": today.isoformat(),
            }
            survivors.append(game)
            if conn is not None:
                insert_tracked_games(conn, [game])

        if processed % progress_every == 0 or processed == len(candidate_ids):
            elapsed = time.time() - start
            logger.info(
                "Discovery progress: %d/%d processed, %d survivors, %.0fs elapsed",
                processed, len(candidate_ids), len(survivors), elapsed,
            )

        if target_count is not None and len(survivors) >= target_count:
            logger.info(
                "Reached target_count=%d survivors after %d/%d candidates, stopping early",
                target_count, processed, len(candidate_ids),
            )
            break

    logger.info(
        "appdetails+age filter: %d/%d candidates processed, %d survived",
        processed, len(candidate_ids), len(survivors),
    )
    return survivors


def insert_tracked_games(conn: sqlite3.Connection, games: list[dict]) -> int:
    """INSERT OR IGNORE each game into tracked_games. Returns count of newly
    inserted rows (idempotent — re-running with the same games is a no-op)."""
    inserted = 0
    for game in games:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO tracked_games
                (app_id, name, genre, publisher, release_date, review_count,
                 review_score_pct, first_tracked_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game["app_id"], game["name"], game["genre"], game["publisher"],
                game["release_date"], game["review_count"], game["review_score_pct"],
                game["first_tracked_date"],
            ),
        )
        inserted += cursor.rowcount
    conn.commit()
    return inserted


def main(
    conn: sqlite3.Connection,
    min_reviews: int = config.MIN_REVIEWS,
    min_age_months: int = config.MIN_AGE_MONTHS,
    target_count: int | None = config.TARGET_TRACKED_COUNT,
    limit: int | None = None,
    candidate_pool_multiplier: float = config.CANDIDATE_POOL_MULTIPLIER,
) -> None:
    candidates = build_review_candidate_set(min_reviews)
    ranked_ids = sorted(candidates, key=lambda app_id: candidates[app_id]["review_count"], reverse=True)

    if limit is not None:
        pool_ids = ranked_ids[:limit]
        pool_target = None
        logger.info("Discovery limit=%d applied to candidate pool", limit)
    elif target_count is not None:
        pool_size = int(target_count * candidate_pool_multiplier)
        pool_ids = ranked_ids[:pool_size]
        pool_target = target_count
        logger.info(
            "Capped appdetails pool to top %d candidates by review count "
            "(target_count=%d x multiplier=%.1f)",
            pool_size, target_count, candidate_pool_multiplier,
        )
    else:
        pool_ids = ranked_ids
        pool_target = None

    survivors = enrich_and_filter_candidates(
        pool_ids, min_age_months, conn=conn, target_count=pool_target, review_data=candidates
    )

    total = conn.execute("SELECT COUNT(*) FROM tracked_games").fetchone()[0]
    logger.info(
        "Discovery complete: %d candidates -> %d pool -> %d survivors this run "
        "-> tracked_games now has %d total rows",
        len(candidates), len(pool_ids), len(survivors), total,
    )
