# SaleCast (Steam Smart Buy)

ML system that clusters Steam games by discounting behavior, predicts the probability a game hits a target discount, and combines both into a deal-quality score. See `steam-smart-buy-plan.md` for the full project spec.

This repo currently implements **Week 1: data foundation** — discovering a curated set of ~500-1000 qualifying games and backfilling historical price data — plus **Week 2: automation**, a Cloudflare D1 database and scheduled GitHub Actions jobs that keep it live — plus **Week 3: clustering**, grouping games by discounting behavior (how deep, how often, how it trends over time) via K-means.

## Setup

```
pip install -r requirements.txt
cp .env.example .env
```

Sign up for a free API key at https://isthereanydeal.com/apps/my/ and put it in `.env` as `ITAD_API_KEY=...`. This is required for the backfill step (not for discovery, which only uses Steam + SteamSpy).

To write to the remote Cloudflare D1 database (instead of the default local SQLite file), create a scoped API token at https://dash.cloudflare.com/profile/api-tokens (Custom Token, Account > D1 > Edit permission) and set `CLOUDFLARE_API_TOKEN` in `.env`. `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_D1_DATABASE_ID` are already filled in in `.env.example`.

## Usage

```
# Discover qualifying games (populates tracked_games)
python scripts/run_discovery.py --limit 50   # smoke test
python scripts/run_discovery.py              # full run (~15-70 min)

# Backfill full historical Steam price/discount events via ITAD (populates price_history)
python scripts/run_backfill.py --limit 20    # smoke test
python scripts/run_backfill.py               # full run

# Scrape current prices + a SteamSpy review-score snapshot for all tracked games (populates price_history daily)
python scripts/run_daily_scrape.py --limit 20  # smoke test
python scripts/run_daily_scrape.py             # full run

# Cluster tracked games by discounting behavior (populates cluster_labels)
python scripts/run_clustering.py
```

Clustering needs a full price history to compute meaningful features, so games with fewer than `MIN_DISCOUNT_EVENTS` (`salecast/features.py`) recorded discounts are skipped rather than force-fit. K is chosen automatically via silhouette score (`salecast/clustering.py`), excluding any k that isolates a cluster smaller than `MIN_CLUSTER_SIZE` (avoids a single outlier game becoming its own "cluster"). Pass `--k` to override, and `--plot path.png` to change where the PCA scatter plot is saved (`--plot ''` to skip it).

All four scripts default to the local SQLite file at `data/salecast.db`. Pass `--target d1` to read/write the remote Cloudflare D1 database instead (used by the scheduled GitHub Actions jobs):

```
python scripts/run_discovery.py --target d1
python scripts/run_backfill.py --target d1
python scripts/run_daily_scrape.py --target d1
python scripts/run_clustering.py --target d1
```

For offline analysis against a snapshot of the live D1 data instead of the small local dev database, export it first (`npx wrangler d1 export salecast --remote --output=data/snapshot.sql`, then load it into a local SQLite file), and point clustering at it with `--db-path`:

```
python scripts/run_clustering.py --db-path data/snapshot.db
```

Default thresholds (min review count, min age since release, target tracked-game count) live in `salecast/config.py`.

## Scheduled jobs

Two GitHub Actions workflows keep the D1 database live, both targeting `--target d1`:

- **`.github/workflows/daily-scrape.yml`** — runs `run_daily_scrape.py` every day at 06:00 UTC.
- **`.github/workflows/weekly-discovery.yml`** — runs `run_discovery.py` then `run_backfill.py` every Monday at 05:00 UTC, so newly-qualifying games get picked up and their full Steam price history backfilled (both scripts are idempotent, so this only does work for genuinely new games).

Both are also triggerable manually from the Actions tab (`workflow_dispatch`), with an optional `limit` input for a smoke test.

Set these as repo secrets (Settings > Secrets and variables > Actions) for the workflows to authenticate:

- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_D1_DATABASE_ID` — from `.env.example`.
- `CLOUDFLARE_API_TOKEN` — the scoped D1 token described above.
- `ITAD_API_KEY` — used by the weekly backfill step only.

## Tests

```
pytest
```
