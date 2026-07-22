const DEFAULT_API_BASE = "http://localhost:8000";

const apiBaseInput = document.getElementById("api-base");
const apiBaseSaveBtn = document.getElementById("api-base-save");
const searchInput = document.getElementById("search-input");
const resultsList = document.getElementById("results");
const gamePanel = document.getElementById("game-panel");

function getApiBase() {
  return localStorage.getItem("salecast_api_base") || DEFAULT_API_BASE;
}

apiBaseInput.value = getApiBase();

apiBaseSaveBtn.addEventListener("click", () => {
  const value = apiBaseInput.value.trim().replace(/\/+$/, "");
  if (value) {
    localStorage.setItem("salecast_api_base", value);
  }
});

function setResultsMessage(text) {
  resultsList.innerHTML = "";
  const li = document.createElement("li");
  li.className = "empty-state";
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

async function runSearch(query) {
  try {
    const response = await fetch(`${getApiBase()}/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    renderResults(await response.json());
  } catch (err) {
    setResultsMessage(`Couldn't reach the API at ${getApiBase()} - check the API settings below.`);
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

  const dealScore = game.deal_score;
  const dealScoreText = dealScore === null || dealScore === undefined ? "—" : String(Math.round(dealScore));
  const clusterLine = game.cluster_id === null || game.cluster_id === undefined
    ? "not enough discount history to cluster yet"
    : `cluster ${game.cluster_id}`;

  const smartBuyRows = game.smart_buy_probabilities.length
    ? game.smart_buy_probabilities
        .map(
          (row) => `
        <tr>
          <td>${row.target_discount}% off</td>
          <td>within ${row.horizon_days} days</td>
          <td>${Math.round(row.probability * 100)}%</td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="3" class="empty-state">No smart-buy scores yet</td></tr>`;

  // Numbers above are all formatted server-side-controlled values, safe to
  // interpolate; anything sourced from the game's name/genre/publisher is
  // set via textContent below instead, since Steam game names are
  // arbitrary strings this app doesn't control.
  gamePanel.innerHTML = `
    <h2 id="game-name"></h2>
    <p class="game-meta" id="game-meta"></p>
    <div class="score-row">
      <div class="deal-score ${scoreClass(dealScore)}">${dealScoreText}</div>
      <div>
        <div class="score-label">Deal score (0-100)</div>
        <div class="price-line" id="price-line"></div>
      </div>
    </div>
    <table>
      <thead><tr><th>Target</th><th>Horizon</th><th>Probability</th></tr></thead>
      <tbody>${smartBuyRows}</tbody>
    </table>
  `;

  document.getElementById("game-name").textContent = game.name;
  document.getElementById("game-meta").textContent =
    [game.genre, game.publisher].filter(Boolean).join(" · ") + (game.genre || game.publisher ? " · " : "") + clusterLine;

  const priceLineEl = document.getElementById("price-line");
  if (game.current_price === null || game.current_price === undefined) {
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
}

async function loadGame(appId) {
  resultsList.innerHTML = "";
  searchInput.value = "";
  try {
    const response = await fetch(`${getApiBase()}/game/${appId}`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    renderGame(await response.json());
  } catch (err) {
    gamePanel.classList.remove("hidden");
    gamePanel.innerHTML = "";
    const message = document.createElement("p");
    message.className = "empty-state";
    message.textContent = `Couldn't load that game (${err.message}).`;
    gamePanel.appendChild(message);
  }
}
