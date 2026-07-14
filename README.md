# SaleCast (Steam Smart Buy)

ML system that clusters Steam games by discounting behavior, predicts the probability a game hits a target discount, and combines both into a deal-quality score. See `steam-smart-buy-plan.md` for the full project spec.

This repo currently implements **Week 1: data foundation** — discovering a curated set of ~500-1000 qualifying games and backfilling historical price data — plus the storage layer for **Week 2: automation**, a Cloudflare D1 database that scheduled jobs write to.

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

# Backfill historical price data (populates price_history)
python scripts/run_backfill.py --limit 20    # smoke test
python scripts/run_backfill.py               # full run
```

Both scripts default to the local SQLite file at `data/salecast.db`. Pass `--target d1` to read/write the remote Cloudflare D1 database instead (used by the scheduled GitHub Actions jobs):

```
python scripts/run_discovery.py --target d1
python scripts/run_backfill.py --target d1
```

Default thresholds (min review count, min age since release, target tracked-game count) live in `salecast/config.py`.

## Tests

```
pytest
```
