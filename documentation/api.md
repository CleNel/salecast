# API

`salecast/api.py` is a small FastAPI service.

| Endpoint | Returns |
|---|---|
| `GET /game/{app_id}` | cluster, all three smart-buy probabilities, deal score, a `deal_score_breakdown` (the three weighted contributions that sum to it), and a `cluster_comparison` (this game's discount-behavior features next to its cluster's average), plus `next_sale_estimate` (a days-until-next-sale range with a `confidence` of high/medium/low, only when the game isn't currently on sale and has 7+ past sales; see [ml.md](ml.md)) |
| `GET /game/{app_id}/history` | full price/discount time series, for the history chart |
| `GET /search?q=` | name search over tracked games |
| `GET /health` | liveness check |

## Run locally

```
uvicorn salecast.api:app --reload
```

Choose the backend with environment variables: `SALECAST_TARGET=d1` (default) or `SALECAST_TARGET=sqlite` together with `SALECAST_DB_PATH`.

Deployment is covered in [deployment.md](deployment.md).
