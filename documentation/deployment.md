# Deployment and automation

| Piece | Where | How it deploys |
|---|---|---|
| Database | Cloudflare D1 | schema/data changes via `wrangler d1 execute` or `scripts/` |
| API | Render (free tier) | automatic on push to `main` |
| Frontend | Cloudflare Pages | **manual** (see below) |
| Data jobs | GitHub Actions | scheduled |

Live site: https://salecast.cleomenenelli.us, talking to https://salecast-api.onrender.com. The Render free tier cold-starts, so the first request after idle is slow.

## API on Render

`render.yaml` deploys it as a Blueprint: connect the repo, then set `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_D1_DATABASE_ID` and `CLOUDFLARE_API_TOKEN` in Render's dashboard. They're deliberately left out of `render.yaml` so secrets never enter git.

## Frontend on Cloudflare Pages

Not git-connected. Pushing to `main` does **not** update the site. After any `docs/` change:

```
npx wrangler pages deploy docs --project-name=salecast
```

(The daily scrape workflow also redeploys it with fresh snapshots.) For a custom domain, add it under the Pages project's "Custom domains" tab; DNS is already in the same Cloudflare account.

## Scheduled jobs

Three GitHub Actions workflows keep D1 current, all with `--target d1`:

- **`daily-scrape.yml`**, daily 06:00 UTC: price scrape, deal-score recompute, regenerate `deals.json` / `games_catalog.json`, deploy to Pages.
- **`weekly-discovery.yml`**, Mondays 05:00 UTC: discovery, then ITAD backfill for new games (both idempotent), then the price-staleness check. Games tracked within the last 14 days are exempt from that check, since they haven't had a daily scrape yet.
- **`monthly-retrain.yml`**, 1st of the month 04:00 UTC: clustering, smart-buy, deal score. Discount personality changes slowly, so retraining more often adds cost for no real change.

All are triggerable from the Actions tab (`workflow_dispatch`); the daily and weekly ones take an optional `limit` for a smoke test. GitHub often starts scheduled runs hours late.

### Repo secrets

Settings > Secrets and variables > Actions:

- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_D1_DATABASE_ID`: from `.env.example`
- `CLOUDFLARE_API_TOKEN`: the scoped D1 token from [setup.md](setup.md)
- `ITAD_API_KEY`: weekly backfill only
