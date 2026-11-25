# Setup

```
pip install -r requirements.txt
cp .env.example .env
```

## API keys

- **ITAD (required for backfill only):** sign up for a free key at https://isthereanydeal.com/apps/my/ and put it in `.env` as `ITAD_API_KEY=...`. Discovery only uses Steam + SteamSpy and doesn't need it.
- **Cloudflare D1 (only to write to the remote database):** create a scoped API token at https://dash.cloudflare.com/profile/api-tokens (Custom Token, Account > D1 > Edit) and set `CLOUDFLARE_API_TOKEN` in `.env`. `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_D1_DATABASE_ID` are already filled in in `.env.example`.

Without the Cloudflare token everything runs against a local SQLite file (`data/salecast.db`).

Default thresholds (min review count, min age since release, target tracked-game count) live in `salecast/config.py`.

## Tests

```
pytest
```
