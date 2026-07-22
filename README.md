# SaleCast (Steam Smart Buy)

ML system that clusters Steam games by discounting behavior, predicts the probability a game hits a target discount, and combines both into a deal-quality score. See `steam-smart-buy-plan.md` for the full project spec and its scope-decision rationale.

This repo implements the full 6-week plan:

- **Week 1: data foundation** — discovers a curated set of ~500-1000 qualifying games and backfills their historical price data.
- **Week 2: automation** — a Cloudflare D1 database and scheduled GitHub Actions jobs keep it live (daily price scrape, weekly discovery).
- **Week 3: clustering** — groups games by discounting behavior (how deep, how often, how it trends over time) via K-means.
- **Week 4: smart-buy model** — predicts the probability a game hits a target discount within N days.
- **Week 5: deal scorer + API** — a composite 0-100 "how good is this deal" score, exposed via a small FastAPI service.
- **Week 6: frontend + polish** — a minimal static search page (`docs/`, deployable free on GitHub Pages) and a monthly GitHub Actions job that keeps clustering/smart-buy/deal-score current.

## Design decisions worth knowing about

The scope decisions behind the overall project (why ~500-1000 games not the full library, why tiered update frequencies, why a hand-tuned composite score first) are in `steam-smart-buy-plan.md`'s "Scope decisions" table. A few more came up during implementation, each because something in the real data forced the issue:

- **Clustering excludes a k that isolates a single outlier as its own cluster** (`MIN_CLUSTER_SIZE` in `salecast/clustering.py`) — raw silhouette score alone picked k=5 on the real dataset because one game's extreme discount-depth trend split off by itself, which isn't a useful "cluster."
- **The smart-buy model takes target_discount/horizon_days as features, not three separate models** — you asked for all three discount/timeframe scenarios to be considered, so one classifier generalizes across them instead of tripling the training/maintenance burden.
- **Review confidence uses a Wilson score interval, not the raw percentage** (`salecast/deal_score.py`) — otherwise 5 perfect reviews would outrank 50,000 reviews at 95% positive.
- **Average playtime was dropped from the deal score** despite being in the original plan — SteamSpy's only free source for it (`average_forever`) returns 0 for every real game tested; it's not silently faked.
- **D1 writes are batched into one HTTP call per game/scenario** (`D1Connection.execute_batch`) — the full backfill was taking ~27s/game with one round-trip per row; Cloudflare's `{"batch": [...]}` endpoint cut that down by roughly an order of magnitude.
- **Train/test splits are done by game, not by row** (`GroupShuffleSplit` in `salecast/smart_buy.py`) — a row-level split would let a game's own history leak between train and test, overstating how well the model generalizes to games it's never seen.

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

# Train the smart-buy model and score every tracked game (populates smart_buy_scores)
python scripts/run_smart_buy.py

# Compute the composite deal score for every tracked game (populates deal_scores)
python scripts/run_deal_score.py
```

Clustering needs a full price history to compute meaningful features, so games with fewer than `MIN_DISCOUNT_EVENTS` (`salecast/features.py`) recorded discounts are skipped rather than force-fit. K is chosen automatically via silhouette score (`salecast/clustering.py`), excluding any k that isolates a cluster smaller than `MIN_CLUSTER_SIZE` (avoids a single outlier game becoming its own "cluster"). Pass `--k` to override, and `--plot path.png` to change where the PCA scatter plot is saved (`--plot ''` to skip it).

The smart-buy model (`salecast/labels.py`, `salecast/smart_buy.py`) answers "will this game hit X% off within Y days" for three scenarios (`SCENARIOS` in `labels.py`: 50%/30 days, 30%/14 days, 70%/60 days), trained on synthetic observation points sampled every `OBSERVATION_STEP_DAYS` along each game's real price history, with `target_discount`/`horizon_days` themselves as model features so one classifier generalizes across all three. It trains both a logistic regression and a random forest on a game-level train/test split (so no game's own history leaks between train and test), picks whichever scores higher on held-out ROC AUC, and writes one `smart_buy_scores` row per (game, scenario). Pass `--model` to force a specific one instead of auto-selecting.

All six scripts default to the local SQLite file at `data/salecast.db`. Pass `--target d1` to read/write the remote Cloudflare D1 database instead (used by the scheduled GitHub Actions jobs):

```
python scripts/run_discovery.py --target d1
python scripts/run_backfill.py --target d1
python scripts/run_daily_scrape.py --target d1
python scripts/run_clustering.py --target d1
python scripts/run_smart_buy.py --target d1
python scripts/run_deal_score.py --target d1
```

For offline analysis against a snapshot of the live D1 data instead of the small local dev database, export it first (`npx wrangler d1 export salecast --remote --output=data/snapshot.sql`, then load it into a local SQLite file), and point any of these three scripts at it with `--db-path`:

```
python scripts/run_clustering.py --db-path data/snapshot.db
python scripts/run_smart_buy.py --db-path data/snapshot.db
python scripts/run_deal_score.py --db-path data/snapshot.db
```

Default thresholds (min review count, min age since release, target tracked-game count) live in `salecast/config.py`.

## Deal score

`salecast/deal_score.py` combines three signals into one 0-100 `deal_score` per game (a hand-weighted v1 composite, not a learned model — see `steam-smart-buy-plan.md` section 7 for why that's the deliberate starting point):

- **Discount ratio (40%)** — the current discount as a fraction of *this game's own* best-ever discount, not an absolute number. 30% off means something very different for a game that tops out at 40% off versus one that regularly hits 90%.
- **Smart-buy probability (35%)** — the smart-buy model's probability for the canonical 50%-off/30-day scenario (`CANONICAL_TARGET_DISCOUNT`/`CANONICAL_HORIZON_DAYS` in `deal_score.py`).
- **Review confidence (25%)** — a Wilson score interval lower bound on the review positive rate, not the raw percentage, so a game with 5 perfect reviews doesn't outrank one with 50,000 reviews at 95% positive.

`average playtime` is listed as a deal-score input in the project plan but isn't included: SteamSpy's per-app `average_forever` field (the only free source for it) returns 0 for every game tested, including major titles like The Witcher 3 - Valve restricted the data SteamSpy used to compute it years ago, so it's not actually available.

## API

`salecast/api.py` is a small FastAPI service: `GET /game/{app_id}` returns the game's cluster, all three smart-buy probabilities, and its deal score.

```
uvicorn salecast.api:app --reload
```

Set `SALECAST_TARGET=d1` (default) or `SALECAST_TARGET=sqlite` with `SALECAST_DB_PATH` as environment variables to choose the backend, same as the scripts above.

`render.yaml` deploys it free on [Render](https://render.com): connect this repo as a Blueprint, then set `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_D1_DATABASE_ID`, and `CLOUDFLARE_API_TOKEN` in Render's dashboard (left out of `render.yaml` itself so secrets never enter git).

## Frontend

`docs/` is a minimal static page (no build step - plain HTML/CSS/JS) that searches tracked games by name and shows their cluster, smart-buy probabilities, and deal score. It's a thin client for the API above; it holds no data of its own.

To run it locally:

```
uvicorn salecast.api:app --reload   # in one terminal
cd docs && python -m http.server 8080   # in another
```

Then open `http://localhost:8080`, expand "API settings", and point it at `http://localhost:8000` (uvicorn's default port) if you didn't run the API on 8080 already.

To publish it free on GitHub Pages: repo Settings > Pages > set source to the `main` branch, `/docs` folder. Once deployed, open the page's "API settings" and point `API base URL` at wherever `salecast/api.py` ends up running (e.g. the Render URL from the API section above) - it's a plain input persisted in the browser's local storage, not a build-time config, so this works without rebuilding or redeploying anything.

## Scheduled jobs

Three GitHub Actions workflows keep the D1 database live, all targeting `--target d1`:

- **`.github/workflows/daily-scrape.yml`** — runs `run_daily_scrape.py` every day at 06:00 UTC.
- **`.github/workflows/weekly-discovery.yml`** — runs `run_discovery.py` then `run_backfill.py` every Monday at 05:00 UTC, so newly-qualifying games get picked up and their full Steam price history backfilled (both scripts are idempotent, so this only does work for genuinely new games).
- **`.github/workflows/monthly-retrain.yml`** — runs `run_clustering.py`, `run_smart_buy.py`, then `run_deal_score.py` on the 1st of each month at 04:00 UTC, per the plan's "discounting personality changes slowly, retraining daily would just add compute cost for no real change" reasoning (see `steam-smart-buy-plan.md`).

All three are also triggerable manually from the Actions tab (`workflow_dispatch`); the daily/weekly ones take an optional `limit` input for a smoke test.

Set these as repo secrets (Settings > Secrets and variables > Actions) for the workflows to authenticate:

- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_D1_DATABASE_ID` — from `.env.example`.
- `CLOUDFLARE_API_TOKEN` — the scoped D1 token described above.
- `ITAD_API_KEY` — used by the weekly backfill step only.

## Tests

```
pytest
```
