# Steam Smart Buy — Project Plan

A discount-clustering + probability-scoring + deal-scoring ML project built on free tools and a curated Steam dataset.

## 1. Goal

Build a small, self-updating ML system that:
1. Clusters games/publishers by their **discounting behavior** (unsupervised)
2. Predicts the **probability a game hits a target discount** within N days (supervised)
3. Combines both into a single **"is this actually a good deal" score**

The system stays live: new games get added automatically, and models retrain on a schedule — without needing paid infrastructure.

---

## 2. Scope decisions (and why)

| Decision | Why |
|---|---|
| Track ~500–2,000 games, not the full ~100k+ Steam library | Most of the library is shovelware/abandoned titles with no meaningful discount history or reviews. Including them adds noise, not signal, to clustering and prediction. It also keeps scrape time and storage trivial on free tiers. |
| Minimum review count filter (e.g. 500+) | Ensures review-sentiment and "confidence" signals are meaningful, and implicitly filters out low-quality/inactive titles. |
| Minimum age since release (e.g. 6+ months) | A game needs discount history to exist before you can learn a pattern from it. Tracking day-old releases wastes a slot in your dataset. |
| Daily price/discount scrape, weekly app-list check for new qualifying games | Prices change often enough to be worth daily checks; the "is this game now big enough to track" question changes slowly, so weekly is enough and keeps API calls low. |
| Clustering retrains monthly, smart-buy model retrains monthly (or after each major sale event) | Discounting "personality" (cluster membership) is a slow-moving trait — retraining daily would just add compute cost for no real change. The smart-buy model benefits most right after a sale event, when the most new labeled outcomes appear. |
| Start with logistic regression / gradient-boosted trees, not deep learning | These are the right size for a dataset of a few thousand games, they're fast/free to train on a laptop or Colab CPU, and feature importances are far easier to explain in an interview than a neural net's. |
| Composite score first, learned ranking model as a stretch goal | A hand-tuned composite is genuinely defensible and ships fast. Learned ranking is a nice "if I had more time" upgrade to mention, not a blocker to a working v1. |

---

## 3. Data sources (all free)

| Data | Source | Notes |
|---|---|---|
| Current price/discount, tags, genre, release date | Steam Store API (`store.steampowered.com/api/appdetails`) | Free, no key required, generous rate limits for a few thousand games/day |
| Full app list | Steam Web API `GetAppList` | Free, used weekly to detect new qualifying games |
| Review counts/scores | Steam Store API (`appdetails` includes review summary) or SteamSpy | Free |
| Historical price/discount data | Steam doesn't expose history itself — you build your own history by scraping daily going forward. For backfilling *past* history, IsThereAnyDeal (ITAD) has a free API with historical low prices | You likely need both: ITAD for backfilled history, your own daily scrape for the ongoing live dataset |
| Player counts (optional, for smart-buy features) | Steam Web API `GetNumberOfCurrentPlayers` | Free, useful signal for popularity trend |

---

## 4. Architecture overview

```
[Weekly Job: App Discovery]
  → pulls full Steam app list
  → filters by review count + age threshold
  → adds new qualifying games to tracked_games table

[Daily Job: Price Scrape]
  → for each tracked game, pulls current price/discount/review data
  → appends a row to price_history table

[Monthly Job: Retrain Clustering]
  → recomputes discount-behavior features per game
  → re-clusters (K-means), updates cluster labels

[Monthly / Post-Sale Job: Retrain Smart Buy Model]
  → recomputes features (cluster label, days since last discount, etc.)
  → retrains classifier, updates stored probabilities

[On-demand: Deal Scorer]
  → combines cluster label + smart-buy probability + review/value signals
  → computes composite score per game, exposed via API

[API + minimal frontend]
  → lookup a game → see cluster type, smart-buy probability, deal score
```

All scheduled jobs run via **GitHub Actions** (free for public repos) on cron triggers — no server needed to keep things "always on."

---

## 5. Storage

- **SQLite or free-tier Postgres (Supabase/Neon)** — either works fine at this scale (a few thousand games × daily rows for a year is still small, low tens of MB).
- Recommend Supabase/Neon over committing CSVs to git if you want the API to query live data directly, rather than re-reading files each request.

Tables:
- `tracked_games` (app_id, name, genre, publisher, release_date, first_tracked_date)
- `price_history` (app_id, date, price, discount_pct, review_score_snapshot)
- `cluster_labels` (app_id, cluster_id, last_updated)
- `smart_buy_scores` (app_id, probability, target_discount, last_updated)
- `deal_scores` (app_id, composite_score, last_updated)

---

## 6. Feature engineering

**Per-game discount features (for clustering):**
- Average discount depth
- Discount frequency (events/year)
- Time-to-first-discount after release
- Discount depth trend (getting steeper over time?)
- Variance in discount depth (consistent vs erratic)

**Smart-buy model features:**
- Cluster label (from above)
- Days since release
- Days since last discount
- Days until next known Steam sale window
- Current discount (if any)
- Genre, publisher
- Review score trend (improving/declining)
- Player count trend (optional)

**Deal score inputs:**
- Current discount %
- Review score + review count (confidence weight)
- Average playtime (value-for-money proxy, if available)
- Smart-buy probability (how close to historic floor price this is)

---

## 7. Modeling approach

1. **Clustering** — K-means on standardized discount-behavior features. Use silhouette score to pick k. Visualize with PCA/t-SNE for the README/demo.
2. **Smart-buy probability** — binary classification ("hits target discount within N days: yes/no") using logistic regression or LightGBM/XGBoost. Report feature importances. (Stretch: reframe as time-to-event with a Cox model for more depth.)
3. **Deal scorer** — v1: hand-weighted composite of normalized inputs. v2 (stretch): learned ranking model if you can define a "good deal" ground truth signal.

---

## 8. Week-by-week plan

**Week 1 — Data foundation**
- Set up Steam API + ITAD API access
- Define review-count/age thresholds, pull initial ~500–1000 qualifying games
- Backfill historical price data via ITAD where available
- Set up Supabase/Neon schema

**Week 2 — Automation**
- Build daily price-scrape script, wire into GitHub Actions cron
- Build weekly app-discovery script (new qualifying games)
- Verify a few days of real scraped data land correctly

**Week 3 — Clustering**
- Feature engineering for discount behavior
- Run K-means, tune k via silhouette score
- Visualize clusters, sanity-check against known publishers (e.g. does a AAA publisher cluster separately from small indie devs?)

**Week 4 — Smart-buy model**
- Label construction from historical data (did game X hit target discount within N days of point Y?)
- Train logistic regression / LightGBM baseline
- Evaluate (precision/recall, feature importance), iterate

**Week 5 — Deal scorer + API**
- Build composite scoring function
- Wrap everything in a small FastAPI service: `/game/{app_id}` → cluster, probability, deal score
- Deploy free on Render/Railway

**Week 6 — Frontend + polish**
- Minimal static frontend (search a game, see its scores) on GitHub Pages/Vercel
- Write README explaining the "why" behind each scoping decision (great interview material)
- Set up monthly retrain job for clustering + smart-buy model

---

## 9. Why this scales without costing anything

- Curated game list (not full library) keeps API calls, storage, and compute inside every free tier you'll touch (GitHub Actions minutes, Supabase/Neon storage caps, Render/Railway free hours)
- Tiered update frequency (daily prices, weekly discovery, monthly retrains) matches how fast each thing actually changes, rather than treating everything as needing real-time updates
- Growing the tracked list via an automated threshold filter means the project gets more useful over time without you manually maintaining a game list
