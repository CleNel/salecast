const DEFAULT_API_BASE = "https://salecast-api.onrender.com";

const apiBaseInput = document.getElementById("api-base");
const apiBaseSaveBtn = document.getElementById("api-base-save");
const searchInput = document.getElementById("search-input");
const resultsList = document.getElementById("results");
const gamePanel = document.getElementById("game-panel");

const filterGenreEl = document.getElementById("filter-genre");
const filterPriceMinEl = document.getElementById("filter-price-min");
const filterPriceMaxEl = document.getElementById("filter-price-max");
const filterOnSaleEl = document.getElementById("filter-on-sale");
const filterMinScoreEl = document.getElementById("filter-min-score");
const sortByEl = document.getElementById("sort-by");
const filtersClearBtn = document.getElementById("filters-clear");
const loadMoreBtn = document.getElementById("load-more");
const resultsSentinel = document.getElementById("results-sentinel");

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

// Browsing/filtering runs entirely client-side against a once-a-day static
// snapshot (docs/games_catalog.json, generated alongside deals.json) rather
// than hitting the (free-tier, sleep-prone) API per keystroke - the old
// /search endpoint only supported a name lookup and paid a cold-start tax on
// every query. Only the single-game detail panel still calls the live API.
const PAGE_SIZE = 30;

let catalogGames = [];
let catalogLoaded = false;
let currentResults = [];
let visibleCount = 0;

async function loadCatalog() {
  try {
    const response = await fetch("games_catalog.json");
    if (!response.ok) return;
    const data = await response.json();
    catalogGames = data.games || [];
    catalogLoaded = true;
    populateGenreOptions();
    applyFilters();
  } catch (err) {
    // Browsing/filtering just won't work; the game-detail lookup is unaffected.
  }
}

function populateGenreOptions() {
  const genres = [...new Set(catalogGames.map((g) => g.genre).filter(Boolean))].sort();
  for (const genre of genres) {
    const option = document.createElement("option");
    option.value = genre;
    option.textContent = genre;
    filterGenreEl.appendChild(option);
  }
}

function matchesFilters(game) {
  const query = searchInput.value.trim().toLowerCase();
  if (query && !game.name.toLowerCase().includes(query)) return false;

  if (filterGenreEl.value && game.genre !== filterGenreEl.value) return false;

  const minPrice = parseFloat(filterPriceMinEl.value);
  if (!Number.isNaN(minPrice) && (game.price === null || game.price < minPrice)) return false;

  const maxPrice = parseFloat(filterPriceMaxEl.value);
  if (!Number.isNaN(maxPrice) && (game.price === null || game.price > maxPrice)) return false;

  if (filterOnSaleEl.checked && !(game.discount_pct > 0)) return false;

  const minScore = parseFloat(filterMinScoreEl.value);
  if (minScore > 0 && (game.deal_score === null || game.deal_score < minScore)) return false;

  return true;
}

function sortResults(games) {
  const sorted = [...games];
  switch (sortByEl.value) {
    case "discount_pct":
      sorted.sort((a, b) => (b.discount_pct || 0) - (a.discount_pct || 0));
      break;
    case "price_asc":
      sorted.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
      break;
    case "price_desc":
      sorted.sort((a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity));
      break;
    case "review_score":
      sorted.sort((a, b) => (b.review_score_pct ?? -Infinity) - (a.review_score_pct ?? -Infinity));
      break;
    case "deal_score":
    default:
      sorted.sort((a, b) => (b.deal_score ?? -Infinity) - (a.deal_score ?? -Infinity));
      break;
  }
  return sorted;
}

function applyFilters() {
  if (!catalogLoaded) {
    setResultsMessage("Loading games…", true);
    return;
  }

  currentResults = sortResults(catalogGames.filter(matchesFilters));
  visibleCount = 0;
  resultsList.innerHTML = "";

  if (currentResults.length === 0) {
    setResultsMessage("No matches");
    loadMoreBtn.classList.add("hidden");
    return;
  }

  renderNextPage();
}

function renderNextPage() {
  const nextSlice = currentResults.slice(visibleCount, visibleCount + PAGE_SIZE);
  for (const game of nextSlice) {
    resultsList.appendChild(buildResultItem(game));
  }
  visibleCount += nextSlice.length;
  loadMoreBtn.classList.toggle("hidden", visibleCount >= currentResults.length);
}

function buildResultItem(game) {
  const li = document.createElement("li");
  li.className = "result-item";

  const name = document.createElement("span");
  name.className = "deals-item-name";
  name.textContent = game.name;
  li.appendChild(name);

  const meta = document.createElement("span");
  meta.className = "deals-item-meta";

  const priceSpan = document.createElement("span");
  priceSpan.textContent =
    game.price === null || game.price === undefined
      ? "No price data"
      : game.discount_pct > 0
        ? `$${Number(game.price).toFixed(2)} -${game.discount_pct}%`
        : `$${Number(game.price).toFixed(2)}`;
  meta.appendChild(priceSpan);

  if (game.deal_score !== null && game.deal_score !== undefined) {
    const score = document.createElement("span");
    score.className = `deals-item-score ${scoreClass(game.deal_score)}`;
    score.textContent = Math.round(game.deal_score);
    meta.appendChild(score);
  }

  li.appendChild(meta);
  li.addEventListener("click", () => loadGame(game.app_id));
  return li;
}

let filterDebounceTimer = null;
function scheduleApplyFilters() {
  clearTimeout(filterDebounceTimer);
  filterDebounceTimer = setTimeout(applyFilters, 200);
}

searchInput.addEventListener("input", scheduleApplyFilters);
filterGenreEl.addEventListener("change", applyFilters);
filterPriceMinEl.addEventListener("input", scheduleApplyFilters);
filterPriceMaxEl.addEventListener("input", scheduleApplyFilters);
filterOnSaleEl.addEventListener("change", applyFilters);
filterMinScoreEl.addEventListener("change", applyFilters);
sortByEl.addEventListener("change", applyFilters);
filtersClearBtn.addEventListener("click", () => {
  searchInput.value = "";
  filterGenreEl.value = "";
  filterPriceMinEl.value = "";
  filterPriceMaxEl.value = "";
  filterOnSaleEl.checked = false;
  filterMinScoreEl.value = "0";
  sortByEl.value = "deal_score";
  applyFilters();
});

loadMoreBtn.addEventListener("click", renderNextPage);

// Backs the "Load more" button with real infinite scroll: once the sentinel
// below it scrolls into view, load the next page automatically. The button
// stays as an explicit, always-visible affordance for anyone who'd rather
// click than scroll (or whose browser is slow to fire the observer).
const loadMoreObserver = new IntersectionObserver(
  (entries) => {
    if (entries[0].isIntersecting && !loadMoreBtn.classList.contains("hidden")) {
      renderNextPage();
    }
  },
  { rootMargin: "200px" }
);
loadMoreObserver.observe(resultsSentinel);

loadCatalog();

function scoreClass(score) {
  if (score === null || score === undefined) return "";
  if (score >= 65) return "good";
  if (score >= 35) return "mid";
  return "bad";
}

function scoreVerdict(score) {
  if (score >= 65) return "Buy now";
  if (score >= 35) return "Decent deal";
  return "Wait for a better price";
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
  const showVerdict = !game.is_free && dealScore !== null && dealScore !== undefined;

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
    <div class="steam-links">
      <a id="steam-link" class="steam-link steam-link-web" target="_blank" rel="noopener noreferrer">
        <svg class="steam-link-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 3h6v6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 14 21 3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        View on Steam Website
      </a>
      <a id="steam-app-link" class="steam-link steam-link-app">
        <svg class="steam-link-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect x="2" y="4" width="20" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        Open in Steam app
      </a>
    </div>
    <div class="score-row">
      <div class="score-main">
        <div class="deal-score ${dealScoreCssClass}">${dealScoreText}</div>
        ${showVerdict ? `<div class="score-verdict ${dealScoreCssClass}">${scoreVerdict(dealScore)}</div>` : ""}
      </div>
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
      ${
        game.deal_score_breakdown && game.deal_score_breakdown.length > 0
          ? `<ul class="score-component-descriptions">
        <li><strong>Discount depth vs. own history</strong> - how deep today's discount is, relative to the best deal this game has ever had.</li>
        <li><strong>Smart-buy odds</strong> - the model's estimate that a strong discount is coming soon.</li>
        <li><strong>Review confidence</strong> - how reliable this game's review score is, based on how many people rated it.</li>
      </ul>`
          : ""
      }
    </div>

    <div class="explain-section">
      <h3>Discount history at a glance</h3>
      <p class="explain-hint">The simple facts behind this game's own discounting.</p>
      <div class="chart-container" id="discount-summary"></div>
    </div>
  `;

  document.getElementById("game-name").textContent = game.name;
  document.getElementById("game-meta").textContent =
    [game.genre, game.publisher].filter(Boolean).join(" · ") + (game.genre || game.publisher ? " · " : "") + clusterLine;
  document.getElementById("steam-link").href = `https://store.steampowered.com/app/${game.app_id}/`;
  document.getElementById("steam-app-link").href = `steam://store/${game.app_id}`;

  const priceLineEl = document.getElementById("price-line");
  if (game.is_free) {
    priceLineEl.textContent = "Free to play or no longer sold on Steam";
  } else if (game.current_price === null || game.current_price === undefined) {
    priceLineEl.textContent = "No price data yet";
  } else {
    priceLineEl.textContent = "";
    // original_price is Steam's own list price, not derived from
    // current_price/discount_pct - a discounted price is rounded to the
    // cent (e.g. $39.99 at 75% off becomes $9.99, not $9.9975), so back-
    // solving price / (1 - discount/100) would recover $39.96, not $39.99.
    if (game.current_discount_pct && game.original_price) {
      const originalSpan = document.createElement("span");
      originalSpan.className = "original-price";
      originalSpan.textContent = `$${Number(game.original_price).toFixed(2)}`;
      priceLineEl.appendChild(originalSpan);
    }
    priceLineEl.appendChild(document.createTextNode(`$${Number(game.current_price).toFixed(2)}`));
    if (game.current_discount_pct) {
      const discountSpan = document.createElement("span");
      discountSpan.className = "discount";
      discountSpan.textContent = ` -${game.current_discount_pct}%`;
      priceLineEl.appendChild(discountSpan);
    }
  }

  renderDealScoreChart(game);
  renderDiscountSummary(game);
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
    game.deal_score_breakdown.map((row) => ({ label: row.label, value: row.contribution, max: row.max }))
  );
}

function renderDiscountSummary(game) {
  const container = document.getElementById("discount-summary");
  if (game.is_free) {
    container.innerHTML = '<p class="empty-state">Free to play or no longer sold - no discount history to show</p>';
    return;
  }
  const summary = game.discount_summary;
  if (!summary) {
    container.innerHTML = '<p class="empty-state">Not enough price history yet</p>';
    return;
  }

  const stats = [];

  stats.push(
    summary.historical_low_discount_pct > 0
      ? {
          value: `$${Number(summary.historical_low_price).toFixed(2)} (-${summary.historical_low_discount_pct}%)`,
          label: "All-time low",
        }
      : { value: "Never discounted", label: "All-time low" }
  );

  if (summary.avg_discount_depth !== null && summary.avg_discount_depth !== undefined) {
    stats.push({ value: `${Math.round(summary.avg_discount_depth)}%`, label: "Average discount when on sale" });
  }

  if (summary.discount_frequency_per_year !== null && summary.discount_frequency_per_year !== undefined) {
    stats.push({ value: `~${summary.discount_frequency_per_year.toFixed(1)}x/yr`, label: "Goes on sale" });
  }

  container.innerHTML = `<div class="discount-summary">${stats
    .map(
      (s) =>
        `<div class="discount-summary-stat"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`
    )
    .join("")}</div>`;

  const estimateHtml = nextSaleEstimateHtml(game.next_sale_estimate);
  if (estimateHtml) container.insertAdjacentHTML("beforeend", estimateHtml);
}

function formatWait(days) {
  if (days < 14) return `${days} day${days === 1 ? "" : "s"}`;
  if (days < 60) return `${Math.round(days / 7)} weeks`;
  return `${Math.round(days / 30)} months`;
}

// Only present for games not currently on sale with enough history. A range,
// not a date: backtested per-game date predictions were off by ~3 weeks.
function nextSaleEstimateHtml(est) {
  if (!est) return "";
  const range = est.low_days === 0
    ? `within about ${formatWait(est.high_days)}`
    : `in roughly ${formatWait(est.low_days)} to ${formatWait(est.high_days)}`;
  const lead = est.overdue
    ? `Overdue by its usual pattern (it typically goes on sale every ~${formatWait(est.typical_gap_days)}) - could come any time, most likely ${range}.`
    : `Next sale usually ${range}.`;
  const seasonal = est.days_until_seasonal_sale === 0
    ? "A Steam seasonal sale is on now."
    : `Next Steam seasonal sale starts in ~${formatWait(est.days_until_seasonal_sale)}.`;
  return `<p class="sale-estimate"><strong>When might it go on sale?</strong> ${lead} ${seasonal}
    <span class="sale-estimate-note">Rough estimate from this game's own ${est.past_sales} past sales; the real date is often outside the range.</span></p>`;
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
  currentResults = [];
  visibleCount = 0;
  loadMoreBtn.classList.add("hidden");
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
