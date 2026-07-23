import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from salecast import config, db
from salecast.clients.d1_client import D1Connection
from salecast.deal_score import WEIGHTS as DEAL_SCORE_WEIGHTS

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
        "SELECT price, original_price, discount_pct, date FROM price_history "
        "WHERE app_id = ? ORDER BY date DESC LIMIT 1",
        (app_id,),
    ).fetchone()
    cluster = conn.execute(
        "SELECT cluster_id, avg_discount_depth, discount_frequency_per_year "
        "FROM cluster_labels WHERE app_id = ?",
        (app_id,),
    ).fetchone()
    deal = conn.execute(
        """
        SELECT composite_score, discount_ratio, smart_buy_probability, review_confidence
        FROM deal_scores WHERE app_id = ?
        """,
        (app_id,),
    ).fetchone()
    is_free = bool(game["is_free"])

    return {
        "app_id": app_id,
        "name": game["name"],
        "genre": game["genre"],
        "publisher": game["publisher"],
        "is_free": is_free,
        "current_price": latest_price["price"] if latest_price else None,
        "original_price": latest_price["original_price"] if latest_price else None,
        "current_discount_pct": latest_price["discount_pct"] if latest_price else None,
        "price_as_of": latest_price["date"] if latest_price else None,
        "cluster_id": cluster["cluster_id"] if cluster else None,
        "deal_score": deal["composite_score"] if deal else None,
        "deal_score_breakdown": _deal_score_breakdown(deal),
        "discount_summary": None if is_free else _discount_summary(conn, app_id, cluster),
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


def _discount_summary(conn, app_id: int, cluster) -> dict | None:
    """Plain-language discount history for this specific game - how deep
    it's ever gone, how often it goes on sale - in place of the old
    probability-bars and cluster-comparison charts, which required
    interpreting a model's output or a 5-feature diff rather than just
    reading a fact. None if there's no price history at all yet."""
    best = conn.execute(
        "SELECT price, discount_pct, date FROM price_history WHERE app_id = ? "
        "ORDER BY discount_pct DESC, price ASC LIMIT 1",
        (app_id,),
    ).fetchone()
    if best is None:
        return None

    return {
        "historical_low_price": best["price"],
        "historical_low_discount_pct": best["discount_pct"],
        "historical_low_date": best["date"],
        "avg_discount_depth": cluster["avg_discount_depth"] if cluster else None,
        "discount_frequency_per_year": cluster["discount_frequency_per_year"] if cluster else None,
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
