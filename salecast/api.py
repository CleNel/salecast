import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from salecast import config, db
from salecast.clients.d1_client import D1Connection

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
        "SELECT cluster_id FROM cluster_labels WHERE app_id = ?", (app_id,)
    ).fetchone()
    smart_buy_rows = conn.execute(
        """
        SELECT target_discount, horizon_days, probability FROM smart_buy_scores
        WHERE app_id = ? ORDER BY target_discount, horizon_days
        """,
        (app_id,),
    ).fetchall()
    deal = conn.execute(
        "SELECT composite_score FROM deal_scores WHERE app_id = ?", (app_id,)
    ).fetchone()

    return {
        "app_id": app_id,
        "name": game["name"],
        "genre": game["genre"],
        "publisher": game["publisher"],
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
    }
