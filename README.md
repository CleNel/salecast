# SaleCast (Steam Smart Buy)

**Live site: https://salecast.cleomenenelli.us**

Steam sales are constant, but discounts aren't equal. 30% off can be the best a game has ever gone on sale for, or worse than what it sold for last month. SaleCast answers one question for any tracked game: **is this discount actually worth buying into right now?**

It gives each game a 0-100 deal score built from three signals:

- **How deep today's discount is** relative to *that game's own* discount history, not an absolute number.
- **The modeled probability that an even better discount is coming soon.**
- **How much to trust the review score** (a Wilson interval, so a handful of perfect reviews doesn't beat thousands of good ones).

A clustering step groups games by discounting behavior first (some sale often and shallow, others rarely and deep), so "good deal" is judged against each game's own pattern.

## How it works

```
Steam + SteamSpy + IsThereAnyDeal
        |  discover, backfill, daily scrape
        v
 Cloudflare D1  -->  clustering --> smart-buy model --> deal score
        |
        v
 FastAPI (Render)  -->  static frontend (Cloudflare Pages)
```

Everything runs on a schedule via GitHub Actions, so the numbers stay current without manual upkeep.

**Stack:** Python, scikit-learn, FastAPI, Cloudflare D1 + Pages, Render, GitHub Actions.

## Quick start

```
pip install -r requirements.txt
cp .env.example .env
python scripts/run_discovery.py --limit 50
pytest
```

## Documentation

| Guide | Covers |
|---|---|
| [Setup](documentation/setup.md) | install, API keys, config, tests |
| [Usage](documentation/usage.md) | running each pipeline script, local vs. D1, offline analysis |
| [How the ML works](documentation/ml.md) | clustering, smart-buy model, deal score, and the design decisions behind them |
| [API](documentation/api.md) | endpoints and running the service |
| [Frontend](documentation/frontend.md) | the static site and running it locally |
| [Deployment and automation](documentation/deployment.md) | Render, Cloudflare Pages, GitHub Actions, secrets |
| [Project plan](steam-smart-buy-plan.md) | original spec and scope-decision rationale |
