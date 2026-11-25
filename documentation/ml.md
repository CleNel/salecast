# How the ML works

Three layers: cluster games by discounting behavior, predict the chance of a better discount, then combine both with review confidence into one deal score.

## Clustering (`salecast/clustering.py`, `salecast/features.py`)

Groups games by how they discount (some sale often and shallow, others rarely and deep) so "good deal" is judged against each game's own pattern.

- Games with fewer than `MIN_DISCOUNT_EVENTS` recorded discounts are skipped rather than force-fit.
- K is chosen automatically by silhouette score, **excluding any k that isolates a cluster smaller than `MIN_CLUSTER_SIZE`**. Raw silhouette picked k=5 on the real dataset because one game's extreme discount-depth trend split off by itself, which isn't a useful cluster.

## Smart-buy model (`salecast/labels.py`, `salecast/smart_buy.py`)

Answers "will this game hit X% off within Y days" for three scenarios (`SCENARIOS` in `labels.py`): 50%/30 days, 30%/14 days, 70%/60 days.

- Trained on synthetic observation points sampled every `OBSERVATION_STEP_DAYS` along each game's real price history.
- **`target_discount` and `horizon_days` are model features**, so one classifier generalizes across all three scenarios instead of tripling training/maintenance.
- Trains both a logistic regression and a random forest, picks the higher held-out ROC AUC, and writes one `smart_buy_scores` row per (game, scenario).
- **Train/test splits are by game, not by row** (`GroupShuffleSplit`). A row-level split would leak a game's own history between train and test and overstate how well the model generalizes.

## Deal score (`salecast/deal_score.py`)

A hand-weighted v1 composite, not a learned model (see `steam-smart-buy-plan.md` section 7 for why that's the deliberate starting point). 0-100 from:

- **Discount ratio (40%)**: current discount as a fraction of *this game's own* best-ever discount. 30% off means something very different for a game that tops out at 40% versus one that regularly hits 90%.
- **Smart-buy probability (35%)**: the model's probability for the canonical 50%-off/30-day scenario (`CANONICAL_TARGET_DISCOUNT` / `CANONICAL_HORIZON_DAYS`).
- **Review confidence (25%)**: lower bound of a **Wilson score interval** on the positive-review rate, not the raw percentage, so 5 perfect reviews don't outrank 50,000 reviews at 95% positive.

Average playtime is in the original plan but **not used**: SteamSpy's `average_forever` (the only free source) returns 0 for every game tested, including major titles, since Valve restricted that data years ago. It isn't faked.

## Next-sale estimate (`salecast/sale_estimate.py`)

For a game that isn't on sale, the API returns `next_sale_estimate`: a **range** of days until its next discount, from the 10th-90th percentile of its own past gaps between discounts, conditioned on how long it has already gone without one. It needs at least 4 past discount starts, and also reports the next Steam seasonal sale window for context.

It's a range on purpose. Backtested on the Jul 2026 snapshot (hide history after a cutoff, predict the next discount start):

- A per-game predicted *date* was off by ~3 weeks on average, no better than guessing the same ~39 days for every game.
- The 10th-90th percentile range contained the real next-sale date about 74-90% of the time depending on cutoff (the lower figure is the least biased, since later cutoffs only count games whose next sale already happened). The UI calls it "usually", not a guarantee.

Games past every gap they've ever shown are flagged `overdue` and get an open-ended lower bound.

## Data pipeline notes

- **D1 writes are batched** into one HTTP call per game/scenario (`D1Connection.execute_batch`). The full backfill took ~27s/game with one round trip per row; Cloudflare's `{"batch": [...]}` endpoint cut that by roughly an order of magnitude.
- Project-level scope decisions (why ~500-1000 games, tiered update frequencies, hand-tuned score first) are in `steam-smart-buy-plan.md`'s "Scope decisions" table.
