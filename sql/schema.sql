CREATE TABLE IF NOT EXISTS tracked_games (
  app_id             INTEGER PRIMARY KEY,
  name               TEXT NOT NULL,
  genre              TEXT,
  publisher          TEXT,
  release_date       TEXT,
  review_count       INTEGER,
  review_score_pct   REAL,
  first_tracked_date TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS smart_buy_scores (
  app_id          INTEGER PRIMARY KEY REFERENCES tracked_games(app_id),
  probability     REAL,
  target_discount INTEGER,
  last_updated    TEXT
);

CREATE TABLE IF NOT EXISTS deal_scores (
  app_id          INTEGER PRIMARY KEY REFERENCES tracked_games(app_id),
  composite_score REAL,
  last_updated    TEXT
);

CREATE INDEX IF NOT EXISTS idx_price_history_app_date ON price_history(app_id, date);
