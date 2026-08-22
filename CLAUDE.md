# SaleCast — Claude Code project context

Steam deal-scoring ML side project. Solo, personal repo — optimize for shipping fast, not process. Full spec/rationale: `steam-smart-buy-plan.md`. Full architecture/usage docs: `README.md`. Start with this file; go to those two only for depth on a specific piece.

See `CLAUDE.local.md` (gitignored, not on GitHub) for account IDs, URLs, and anything not safe to publish.

## Stack
- Backend: FastAPI (`salecast/api.py`), deployed on Render (free tier)
- ML: scikit-learn — KMeans clustering (`salecast/clustering.py`), RandomForest/LogisticRegression smart-buy classifier (`salecast/smart_buy.py`)
- DB: Cloudflare D1 (remote, accessed over HTTP via `D1Connection`) — not a local file in production
- Frontend: static HTML/CSS/vanilla JS in `docs/`, deployed on Cloudflare Pages
- Automation: GitHub Actions — daily scrape, weekly discovery/backfill, monthly retrain (`.github/workflows/`)

## Deploy workflow — non-obvious gotchas
- **Frontend is NOT git-connected.** Pushing to `main` does nothing for `docs/`. After any `docs/` change, redeploy manually:
  `npx wrangler pages deploy docs --project-name=salecast`
- **Backend redeploys automatically on push to `main`** (Render is git-connected to this repo).
- Backend cold-starts on Render's free tier — first request after idle can be slow; don't mistake that for a bug.
- D1 schema/data changes go through `wrangler d1 execute` or the scripts in `scripts/`, not manual dashboard edits.
- `render.yaml` deliberately omits the Cloudflare secrets (`sync: false`) — they're set in the Render dashboard, not in git.

## Conventions
- Commit messages: short, imperative, plainly describe the fix/feature (see `git log` for style).
- Only commit when explicitly asked; only push when explicitly asked.
- Run `pytest` before considering a backend change done.
- This repo is public on GitHub — never commit real secrets. `.env`, API tokens, and keys stay gitignored.
