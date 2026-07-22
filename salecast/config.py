import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(PROJECT_ROOT / "data" / "salecast.db")

ITAD_API_KEY = os.environ.get("ITAD_API_KEY")

# Cloudflare D1 (remote storage target for scheduled jobs; see .env.example)
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_D1_DATABASE_ID = os.environ.get("CLOUDFLARE_D1_DATABASE_ID")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")

# Discovery thresholds
MIN_REVIEWS = 500
MIN_AGE_MONTHS = 6
TARGET_TRACKED_COUNT = 1000

# How many top-by-review-count SteamSpy candidates to run through Steam's
# slow appdetails endpoint, as a multiple of TARGET_TRACKED_COUNT. Buffers
# against losses from the age/type filters without appdetails-ing the
# entire SteamSpy candidate pool (which can be 10k+ games).
CANDIDATE_POOL_MULTIPLIER = 2.0
DISCOVERY_PROGRESS_INTERVAL = 50

# Rate limiting (seconds between sequential requests)
STEAM_APPDETAILS_DELAY_SEC = 1.5
STEAMSPY_DELAY_SEC = 1.0

# Daily scrape also fetches a SteamSpy review-score snapshot per game
# (salecast/scrape.py), a second, more strictly rate-limited endpoint beyond
# the bulk 'all' pages discovery uses - gets its own delay between the two
# calls a single game's scrape makes (Steam appdetails, then SteamSpy).
SCRAPE_INTRA_CALL_DELAY_SEC = 0.5

# ITAD rate-limited hard in practice (429s observed well under its
# documented 1000/5min), so backfill is deliberately slower than the
# other clients: a longer delay between games, plus a delay between the
# two ITAD calls a single game's backfill makes (id resolve + price
# lookup), and more retries since 429 recovery can take a few attempts.
ITAD_DELAY_SEC = 2.0
ITAD_INTRA_CALL_DELAY_SEC = 1.0
ITAD_RETRIES = 5

STEAMSPY_MAX_PAGES = 150
