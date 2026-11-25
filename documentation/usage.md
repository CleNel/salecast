# Usage

The pipeline is six scripts, run in this order. Each has a `--limit` smoke-test flag where it makes sense.

```
# Discover qualifying games (populates tracked_games)
python scripts/run_discovery.py --limit 50   # smoke test
python scripts/run_discovery.py              # full run (~15-70 min)

# Backfill full historical Steam price/discount events via ITAD (populates price_history)
python scripts/run_backfill.py --limit 20    # smoke test
python scripts/run_backfill.py               # full run

# Scrape current prices + a SteamSpy review-score snapshot (populates price_history daily)
python scripts/run_daily_scrape.py --limit 20
python scripts/run_daily_scrape.py

# Cluster tracked games by discounting behavior (populates cluster_labels)
python scripts/run_clustering.py

# Train the smart-buy model and score every game (populates smart_buy_scores)
python scripts/run_smart_buy.py

# Compute the composite deal score for every game (populates deal_scores)
python scripts/run_deal_score.py
```

There's also `scripts/check_price_staleness.py`, which exits non-zero if any tracked, non-free game has no price data within `--max-age-days` (default 14). The weekly workflow runs it as a health check.

## Local vs. remote database

All scripts default to the local SQLite file at `data/salecast.db`. Pass `--target d1` to read/write the remote Cloudflare D1 database instead (what the scheduled jobs do):

```
python scripts/run_discovery.py --target d1
```

## Offline analysis against live data

Export a snapshot of D1, load it into a local SQLite file, and point the clustering/smart-buy/deal-score scripts at it with `--db-path`:

```
npx wrangler d1 export salecast --remote --output=data/snapshot.sql
python scripts/run_clustering.py --db-path data/snapshot.db
python scripts/run_smart_buy.py --db-path data/snapshot.db
python scripts/run_deal_score.py --db-path data/snapshot.db
```

## Script options worth knowing

- `run_clustering.py`: `--k` overrides the automatic k choice; `--plot path.png` changes where the PCA scatter plot is saved (`--plot ''` skips it).
- `run_smart_buy.py`: `--model` forces logistic regression or random forest instead of auto-selecting.

How these steps work is in [ml.md](ml.md).
