CREATE TABLE IF NOT EXISTS tracked_games (
  app_id             INTEGER PRIMARY KEY,
  name               TEXT NOT NULL,
  genre              TEXT,
  publisher          TEXT,
  release_date       TEXT,
  review_count       INTEGER,
  review_score_pct   REAL,
  first_tracked_date TEXT NOT NULL,
  -- Free-to-play games can't be "discounted" - excluded from clustering,
  -- the smart-buy model, and the deal score (see salecast/scrape.py,
  -- which keeps this current from Steam's own is_free flag).
  is_free            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS price_history (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  app_id                INTEGER NOT NULL REFERENCES tracked_games(app_id),
  date                  TEXT NOT NULL,
  price                 REAL,
  discount_pct          INTEGER,
  review_score_snapshot REAL,
  source                TEXT NOT NULL,
  UNIQUE (app_id, date, source)
);

CREATE TABLE IF NOT EXISTS cluster_labels (
  app_id       INTEGER PRIMARY KEY REFERENCES tracked_games(app_id),
  cluster_id   INTEGER,
  last_updated TEXT
);

-- One row per (game, "hits X% off within Y days") scenario - a single game
-- carries a different probability for each target_discount/horizon_days
-- combination the smart-buy model is asked about (see salecast/smart_buy.py).
CREATE TABLE IF NOT EXISTS smart_buy_scores (
  app_id          INTEGER NOT NULL REFERENCES tracked_games(app_id),
  target_discount INTEGER NOT NULL,
  horizon_days    INTEGER NOT NULL,
  probability     REAL,
  last_updated    TEXT,
  PRIMARY KEY (app_id, target_discount, horizon_days)
);

CREATE TABLE IF NOT EXISTS deal_scores (
  app_id          INTEGER PRIMARY KEY REFERENCES tracked_games(app_id),
  composite_score REAL,
  last_updated    TEXT
);

CREATE INDEX IF NOT EXISTS idx_price_history_app_date ON price_history(app_id, date);
