import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from salecast import config, db
from salecast.clients.d1_client import D1Connection
from salecast.deal_score import WEIGHTS as DEAL_SCORE_WEIGHTS

CLUSTER_FEATURE_LABELS = {
    "avg_discount_depth": "Average discount depth",
    "discount_depth_std": "Discount depth variance",
    "discount_frequency_per_year": "Discounts per year",
    "time_to_first_discount_days": "Days to first discount",
    "discount_depth_trend": "Discount trend (pct/yr)",
}

app = FastAPI(title="SaleCast API", description="Steam deal-quality lookups")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


def get_connection():
    """Which backend to query is chosen at request time via env vars (not
    import time), so tests can override this dependency and a deployed
    instance can be pointed at D1 purely through its environment, no code
    change - SALECAST_TARGET defaults to "d1" since that's what the
    scheduled jobs keep live; SALECAST_DB_PATH only matters for the
    sqlite fallback."""
    target = os.environ.get("SALECAST_TARGET", "d1")
    if target == "d1":
        conn = D1Connection()
    else:
        conn = db.get_connection(os.environ.get("SALECAST_DB_PATH", config.DB_PATH))
    try:
        yield conn
    finally:
        if hasattr(conn, "close"):
            conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/search")
def search_games(q: str = "", conn=Depends(get_connection)):
    q = q.strip()
    if len(q) < 2:
        return []

    rows = conn.execute(
        "SELECT app_id, name FROM tracked_games WHERE name LIKE ? ORDER BY review_count DESC LIMIT 20",
        (f"%{q}%",),
    ).fetchall()
    return [{"app_id": row["app_id"], "name": row["name"]} for row in rows]


@app.get("/game/{app_id}")
def get_game(app_id: int, conn=Depends(get_connection)):
    game = conn.execute("SELECT * FROM tracked_games WHERE app_id = ?", (app_id,)).fetchone()
    if game is None:
        raise HTTPException(status_code=404, detail=f"app_id {app_id} is not tracked")

    latest_price = conn.execute(
        "SELECT price, discount_pct, date FROM price_history WHERE app_id = ? ORDER BY date DESC LIMIT 1",
        (app_id,),
    ).fetchone()
    cluster = conn.execute(
        f"""
        SELECT cluster_id, {", ".join(CLUSTER_FEATURE_LABELS)}
        FROM cluster_labels WHERE app_id = ?
        """,
        (app_id,),
    ).fetchone()
    smart_buy_rows = conn.execute(
        """
        SELECT target_discount, horizon_days, probability FROM smart_buy_scores
        WHERE app_id = ? ORDER BY target_discount, horizon_days
        """,
        (app_id,),
    ).fetchall()
    deal = conn.execute(
        """
        SELECT composite_score, discount_ratio, smart_buy_probability, review_confidence
        FROM deal_scores WHERE app_id = ?
        """,
        (app_id,),
    ).fetchone()

    return {
        "app_id": app_id,
        "name": game["name"],
        "genre": game["genre"],
        "publisher": game["publisher"],
        "is_free": bool(game["is_free"]),
        "current_price": latest_price["price"] if latest_price else None,
        "current_discount_pct": latest_price["discount_pct"] if latest_price else None,
        "price_as_of": latest_price["date"] if latest_price else None,
        "cluster_id": cluster["cluster_id"] if cluster else None,
        "deal_score": deal["composite_score"] if deal else None,
        "smart_buy_probabilities": [
            {
                "target_discount": row["target_discount"],
                "horizon_days": row["horizon_days"],
                "probability": row["probability"],
            }
            for row in smart_buy_rows
        ],
        "deal_score_breakdown": _deal_score_breakdown(deal),
        "cluster_comparison": _cluster_comparison(conn, cluster),
    }


def _deal_score_breakdown(deal) -> list[dict] | None:
    """The three weighted contributions that sum to deal_score, pre-multiplied
    by their weight and scaled to 0-100 so the frontend just renders bars -
    the formula lives here, once, rather than being re-derived client-side."""
    if deal is None or deal["discount_ratio"] is None:
        return None
    return [
        {
            "component": "discount_ratio",
            "label": "Discount depth vs. own history",
            "contribution": round(100 * DEAL_SCORE_WEIGHTS["discount_ratio"] * deal["discount_ratio"], 1),
        },
        {
            "component": "smart_buy_probability",
            "label": "Smart-buy odds",
            "contribution": round(
                100 * DEAL_SCORE_WEIGHTS["smart_buy_probability"] * deal["smart_buy_probability"], 1
            ),
        },
        {
            "component": "review_confidence",
            "label": "Review confidence",
            "contribution": round(
                100 * DEAL_SCORE_WEIGHTS["review_confidence"] * deal["review_confidence"], 1
            ),
        },
    ]


def _cluster_comparison(conn, cluster) -> dict | None:
    """This game's own clustering-feature values next to its cluster's
    average for the same features - why it landed in that group, not just
    which group. None if the game hasn't been clustered (see
    salecast/features.py MIN_DISCOUNT_EVENTS)."""
    if cluster is None or cluster["cluster_id"] is None:
        return None

    columns = ", ".join(f"AVG({c}) AS {c}" for c in CLUSTER_FEATURE_LABELS)
    peers = conn.execute(
        f"SELECT {columns}, COUNT(*) AS n FROM cluster_labels WHERE cluster_id = ?",
        (cluster["cluster_id"],),
    ).fetchone()

    return {
        "cluster_id": cluster["cluster_id"],
        "peer_count": peers["n"],
        "features": [
            {
                "feature": key,
                "label": label,
                "value": cluster[key],
                "cluster_average": peers[key],
            }
            for key, label in CLUSTER_FEATURE_LABELS.items()
        ],
    }


@app.get("/game/{app_id}/history")
def get_game_history(app_id: int, conn=Depends(get_connection)):
    game = conn.execute("SELECT app_id FROM tracked_games WHERE app_id = ?", (app_id,)).fetchone()
    if game is None:
        raise HTTPException(status_code=404, detail=f"app_id {app_id} is not tracked")

    rows = conn.execute(
        "SELECT date, price, discount_pct FROM price_history WHERE app_id = ? ORDER BY date",
        (app_id,),
    ).fetchall()
    return [
        {"date": row["date"], "price": row["price"], "discount_pct": row["discount_pct"]}
        for row in rows
    ]
