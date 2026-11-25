# Frontend

`docs/` is a static page (plain HTML/CSS/JS, no build step) that searches tracked games by name and shows cluster, smart-buy probabilities and deal score, plus four charts (`docs/charts.js`) explaining *why*:

- price/discount history line
- stacked bar splitting the deal score into its three weighted signals
- smart-buy probabilities as bars
- diverging bars comparing this game's discount behavior to its cluster's average

It's a thin client for the [API](api.md) and holds no data of its own beyond the generated `deals.json` / `games_catalog.json` snapshots.

> `docs/` is the Cloudflare Pages deploy folder, so only site files belong there. Project documentation lives in `documentation/`.

## Run locally

```
uvicorn salecast.api:app --reload        # one terminal
cd docs && python -m http.server 8080    # another
```

Open `http://localhost:8080`, expand "API settings", and set the API base URL to `http://localhost:8000`. The page defaults to the deployed Render API, so local testing needs this override. The setting is a plain input persisted in browser local storage, not build-time config.
