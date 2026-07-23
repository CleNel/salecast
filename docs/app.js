const DEFAULT_API_BASE = "https://salecast-api.onrender.com";

const apiBaseInput = document.getElementById("api-base");
const apiBaseSaveBtn = document.getElementById("api-base-save");
const searchInput = document.getElementById("search-input");
const resultsList = document.getElementById("results");
const gamePanel = document.getElementById("game-panel");

function getApiBase() {
  return localStorage.getItem("salecast_api_base") || DEFAULT_API_BASE;
}

apiBaseInput.value = getApiBase();

// Render's free tier spins the API down after ~15 min idle, so the first
// request after a lull eats a 30-60s cold-start. Fire a harmless ping the
// moment the page loads so that wake-up happens in the background while
// the visitor is still reading, instead of after they hit search.
fetch(`${getApiBase()}/health`).catch(() => {});

const LOADING_MESSAGES = [
  "Waking up the deal-hunting hamsters...",
  "Bribing the Steam servers with a coupon code...",
  "Politely asking the server to open its eyes...",
  "Consulting the deal oracle...",
  "Recalibrating the deal-o-meter...",
  "Summoning the smart-buy model from its nap...",
  "Checking the couch cushions for savings...",
  "Running the numbers (all of them)...",
  "Dusting off the price history...",
  "This may take a moment if the server's been napping...",
];

function startLoadingMessages(render, intervalMs = 1800) {
  let i = Math.floor(Math.random() * LOADING_MESSAGES.length);
  render(LOADING_MESSAGES[i]);
  const timer = setInterval(() => {
    i = (i + 1) % LOADING_MESSAGES.length;
    render(LOADING_MESSAGES[i]);
  }, intervalMs);
  return () => clearInterval(timer);
}

apiBaseSaveBtn.addEventListener("click", () => {
  const value = apiBaseInput.value.trim().replace(/\/+$/, "");
  if (value) {
    localStorage.setItem("salecast_api_base", value);
  }
});

function setResultsMessage(text, isLoading = false) {
  resultsList.innerHTML = "";
  const li = document.createElement("li");
  li.className = isLoading ? "empty-state loading-state" : "empty-state";
  li.textContent = text;
  resultsList.appendChild(li);
}

function renderResults(games) {
  resultsList.innerHTML = "";
  if (games.length === 0) {
    setResultsMessage("No matches");
    return;
  }
  for (const game of games) {
    const li = document.createElement("li");
    li.textContent = game.name;
    li.addEventListener("click", () => loadGame(game.app_id));
    resultsList.appendChild(li);
  }
}

let searchRequestId = 0;

async function runSearch(query) {
  const requestId = ++searchRequestId;
  const stopLoading = startLoadingMessages((text) => {
    if (requestId === searchRequestId) setResultsMessage(text, true);
  });

  try {
    const response = await fetch(`${getApiBase()}/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const games = await response.json();
    stopLoading();
    if (requestId === searchRequestId) renderResults(games);
  } catch (err) {
    stopLoading();
    if (requestId === searchRequestId) {
      setResultsMessage(`Couldn't reach the API at ${getApiBase()} - check the API settings below.`);
    }
  }
}

let debounceTimer = null;
searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  const query = searchInput.value.trim();
  if (query.length < 2) {
    resultsList.innerHTML = "";
    return;
  }
  debounceTimer = setTimeout(() => runSearch(query), 250);
});

function scoreClass(score) {
  if (score === null || score === undefined) return "";
  if (score >= 65) return "good";
  if (score >= 35) return "mid";
  return "bad";
}

function renderGame(game) {
  gamePanel.classList.remove("hidden");

  // Free-to-play games can't be "discounted", so their deal score and
  // smart-buy odds are meaningless (and the API doesn't compute them) -
  // show that plainly instead of a blank dash that reads like missing data.
  const dealScore = game.deal_score;
  const dealScoreText = game.is_free
    ? "Free"
    : dealScore === null || dealScore === undefined
      ? "—"
      : String(Math.round(dealScore));
  const dealScoreCssClass = game.is_free ? "free" : scoreClass(dealScore);

  const clusterLine = game.is_free
    ? "free to play or no longer sold - not applicable"
    : game.cluster_id === null || game.cluster_id === undefined
      ? "not enough discount history to cluster yet"
      : `cluster ${game.cluster_id}`;

  // Numbers interpolated below (target_discount, horizon_days, etc.) are all
  // server-controlled values, safe to inline; anything sourced from the
  // game's name/genre/publisher is set via textContent instead, since Steam
  // game names are arbitrary strings this app doesn't control.
  gamePanel.innerHTML = `
    <h2 id="game-name"></h2>
    <p class="game-meta" id="game-meta"></p>
    <div class="score-row">
      <div class="deal-score ${dealScoreCssClass}">${dealScoreText}</div>
      <div>
        <div class="score-label">${game.is_free ? "Deal score" : "Deal score (0-100)"}</div>
        <div class="price-line" id="price-line"></div>
      </div>
    </div>

    <div class="explain-section">
      <h3>Price &amp; discount history</h3>
      <p class="explain-hint">The actual data behind every chart below.</p>
      <div class="chart-container" id="history-chart"><p class="empty-state">Loading…</p></div>
    </div>

    <div class="explain-section">
      <h3>What makes up the deal score</h3>
      <p class="explain-hint">Three weighted signals, summing to the score above.</p>
      <div class="chart-container" id="deal-score-chart"></div>
    </div>

    <div class="explain-section">
      <h3>Smart-buy odds</h3>
      <p class="explain-hint">Probability of hitting each discount within its time window.</p>
      <div class="chart-container" id="smart-buy-chart"></div>
    </div>

    <div class="explain-section">
      <h3>How this compares to its cluster</h3>
      <p class="explain-hint">This game's discount behavior vs. its cluster's average.</p>
      <div class="chart-container" id="cluster-chart"></div>
    </div>
  `;

  document.getElementById("game-name").textContent = game.name;
  document.getElementById("game-meta").textContent =
    [game.genre, game.publisher].filter(Boolean).join(" · ") + (game.genre || game.publisher ? " · " : "") + clusterLine;

  const priceLineEl = document.getElementById("price-line");
  if (game.is_free) {
    priceLineEl.textContent = "Free to play or no longer sold on Steam";
  } else if (game.current_price === null || game.current_price === undefined) {
    priceLineEl.textContent = "No price data yet";
  } else {
    priceLineEl.textContent = `$${Number(game.current_price).toFixed(2)}`;
    if (game.current_discount_pct) {
      const discountSpan = document.createElement("span");
      discountSpan.className = "discount";
      discountSpan.textContent = ` -${game.current_discount_pct}%`;
      priceLineEl.appendChild(discountSpan);
    }
  }

  renderDealScoreChart(game);
  renderSmartBuyChart(game);
  renderClusterChart(game);
}

function renderDealScoreChart(game) {
  const container = document.getElementById("deal-score-chart");
  if (game.is_free) {
    container.innerHTML = '<p class="empty-state">Free to play or no longer sold - no deal score to break down</p>';
    return;
  }
  if (!game.deal_score_breakdown || game.deal_score_breakdown.length === 0) {
    container.innerHTML = '<p class="empty-state">No deal score computed yet</p>';
    return;
  }
  renderStackedBarChart(
    container,
    game.deal_score_breakdown.map((row) => ({ label: row.label, value: row.contribution }))
  );
}

function renderSmartBuyChart(game) {
  const container = document.getElementById("smart-buy-chart");
  if (game.is_free) {
    container.innerHTML = '<p class="empty-state">Free to play or no longer sold - no discount to track</p>';
    return;
  }
  renderProbabilityBars(
    container,
    game.smart_buy_probabilities.map((row) => ({
      label: `${row.target_discount}% off / ${row.horizon_days}d`,
      value: row.probability * 100,
    }))
  );
}

function renderClusterChart(game) {
  const container = document.getElementById("cluster-chart");
  if (game.is_free) {
    container.innerHTML = '<p class="empty-state">Free-to-play (or no-longer-sold) games aren\'t clustered</p>';
    return;
  }
  const comparison = game.cluster_comparison;
  if (!comparison) {
    container.innerHTML = '<p class="empty-state">Not enough discount history to cluster yet</p>';
    return;
  }
  const rows = comparison.features
    .filter((f) => f.cluster_average !== null && f.cluster_average !== 0)
    .map((f) => ({
      label: f.label,
      pctDiff: ((f.value - f.cluster_average) / Math.abs(f.cluster_average)) * 100,
    }));
  renderDivergingBars(container, rows);
}

async function loadGameHistory(appId) {
  const container = document.getElementById("history-chart");
  try {
    const response = await fetch(`${getApiBase()}/game/${appId}/history`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const rows = await response.json();
    if (document.getElementById("history-chart")) {
      renderPriceHistoryChart(container, rows);
    }
  } catch (err) {
    if (container) {
      container.innerHTML = "";
      const message = document.createElement("p");
      message.className = "empty-state";
      message.textContent = "Couldn't load price history.";
      container.appendChild(message);
    }
  }
}

function setGamePanelMessage(text, isLoading = false) {
  gamePanel.classList.remove("hidden");
  gamePanel.innerHTML = "";
  const message = document.createElement("p");
  message.className = isLoading ? "empty-state loading-state" : "empty-state";
  message.textContent = text;
  gamePanel.appendChild(message);
}

let gameRequestId = 0;

async function loadGame(appId) {
  resultsList.innerHTML = "";
  searchInput.value = "";
  const requestId = ++gameRequestId;
  const stopLoading = startLoadingMessages((text) => {
    if (requestId === gameRequestId) setGamePanelMessage(text, true);
  });

  try {
    const response = await fetch(`${getApiBase()}/game/${appId}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const game = await response.json();
    stopLoading();
    if (requestId === gameRequestId) {
      renderGame(game);
      loadGameHistory(appId);
    }
  } catch (err) {
    stopLoading();
    if (requestId === gameRequestId) {
      setGamePanelMessage(`Couldn't load that game (${err.message}).`);
    }
  }
}

const topDealsList = document.getElementById("top-deals-list");
const newDealsList = document.getElementById("new-deals-list");

function renderDealsList(listEl, games) {
  listEl.innerHTML = "";
  for (const game of games) {
    const li = document.createElement("li");

    const name = document.createElement("span");
    name.className = "deals-item-name";
    name.textContent = game.name;
    li.appendChild(name);

    const meta = document.createElement("span");
    meta.className = "deals-item-meta";

    const priceText = game.price === 0 ? "Free" : `$${Number(game.price).toFixed(2)} -${game.discount_pct}%`;
    const price = document.createElement("span");
    price.textContent = priceText;
    meta.appendChild(price);

    if (game.deal_score !== null && game.deal_score !== undefined) {
      const score = document.createElement("span");
      score.className = `deals-item-score ${scoreClass(game.deal_score)}`;
      score.textContent = Math.round(game.deal_score);
      meta.appendChild(score);
    }

    li.appendChild(meta);
    li.addEventListener("click", () => loadGame(game.app_id));
    listEl.appendChild(li);
  }
}

async function loadSidebarDeals() {
  // Static file generated daily alongside the rest of docs/ (see
  // scripts/generate_sidebar_deals.py) - deliberately not an API call, so
  // this sidebar loads at static-asset speed and never waits on Render.
  try {
    const response = await fetch("deals.json");
    if (!response.ok) return;
    const snapshot = await response.json();
    renderDealsList(topDealsList, snapshot.top_deals || []);
    renderDealsList(newDealsList, snapshot.new_deals || []);
  } catch (err) {
    // No sidebar data yet (e.g. local dev before the snapshot has been
    // generated) - fail quietly, the section just stays empty.
  }
}

loadSidebarDeals();
