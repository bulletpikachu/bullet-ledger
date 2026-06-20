const state = {
  activeGame: null,
  selectedGame: null,
  players: [],
  games: [],
  ledger: [],
};

const els = {
  refreshBtn: document.querySelector("#refreshBtn"),
  newGameForm: document.querySelector("#newGameForm"),
  activeGamePanel: document.querySelector("#activeGamePanel"),
  gameTitle: document.querySelector("#gameTitle"),
  gameStatus: document.querySelector("#gameStatus"),
  gameMeta: document.querySelector("#gameMeta"),
  addPlayerForm: document.querySelector("#addPlayerForm"),
  existingPlayerSelect: document.querySelector("#existingPlayerSelect"),
  activeEntries: document.querySelector("#activeEntries"),
  finishGameBtn: document.querySelector("#finishGameBtn"),
  balanceNote: document.querySelector("#balanceNote"),
  ledgerRows: document.querySelector("#ledgerRows"),
  historyRows: document.querySelector("#historyRows"),
  pastGamePanel: document.querySelector("#pastGamePanel"),
  pastGameTitle: document.querySelector("#pastGameTitle"),
  pastGameStatus: document.querySelector("#pastGameStatus"),
  pastGameMeta: document.querySelector("#pastGameMeta"),
  pastGameEntries: document.querySelector("#pastGameEntries"),
  toast: document.querySelector("#toast"),
};

function money(value) {
  const amount = Number(value || 0);
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function blindMoney(value) {
  const amount = Number(value || 0);
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function todayInputValue() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function profitClass(value) {
  if (Number(value) > 0) return "win";
  if (Number(value) < 0) return "loss";
  return "";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Something went wrong.");
  }
  return data;
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.add("hidden"), 2800);
}

async function loadAll() {
  const [players, activeGame, games, ledger] = await Promise.all([
    api("/api/players"),
    api("/api/games/active"),
    api("/api/games"),
    api("/api/ledger"),
  ]);
  state.players = players;
  state.activeGame = activeGame;
  state.games = games;
  state.ledger = ledger;
  render();
}

function render() {
  renderPlayerSelect();
  renderActiveGame();
  renderLedger();
  renderHistory();
  renderPastGame();
}

function renderPlayerSelect() {
  const selectedIds = new Set((state.activeGame?.entries || []).map((entry) => entry.player_id));
  const options = state.players
    .filter((player) => !selectedIds.has(player.id))
    .map((player) => `<option value="${player.id}">${escapeHtml(player.name)}</option>`);
  els.existingPlayerSelect.innerHTML = `<option value="">Add existing player...</option>${options.join("")}`;
}

function renderActiveGame() {
  const game = state.activeGame;
  els.activeGamePanel.classList.toggle("hidden", !game);
  els.newGameForm.classList.toggle("hidden", Boolean(game));

  if (!game) {
    els.gameTitle.textContent = "Start a game";
    els.gameStatus.textContent = "No active game";
    return;
  }

  els.gameTitle.textContent = game.title;
  els.gameStatus.textContent = "In progress";
  els.gameMeta.innerHTML = [
    `Date ${game.played_on}`,
    `Blinds ${blindMoney(game.small_blind)}/${blindMoney(game.big_blind)}`,
    `Stack ${money(game.starting_stack)}`,
  ]
    .map((item) => `<span class="meta-chip">${item}</span>`)
    .join("");

  els.activeEntries.innerHTML = game.entries.length
    ? game.entries.map(renderEntryRow).join("")
    : `<tr><td colspan="6">No players</td></tr>`;

  const totals = game.entries.reduce(
    (acc, entry) => {
      acc.buyIn += Number(entry.buy_in_total);
      acc.cashOut += Number(entry.cash_out);
      acc.profit += Number(entry.profit);
      return acc;
    },
    { buyIn: 0, cashOut: 0, profit: 0 }
  );
  els.balanceNote.textContent = `Total In ${money(totals.buyIn)} · Total Out ${money(totals.cashOut)} · Difference ${money(totals.profit)}`;
  els.finishGameBtn.disabled = game.entries.length === 0;
}

function renderEntryRow(entry) {
  const klass = profitClass(entry.profit);
  return `
    <tr>
      <td class="row-name">${escapeHtml(entry.player_name)}</td>
      <td>
        <input data-entry="${entry.id}" data-field="buy_in_total" type="number" min="0" step="0.01" value="${entry.buy_in_total}" aria-label="${escapeHtml(entry.player_name)} buy in">
      </td>
      <td>
        <input data-entry="${entry.id}" data-field="cash_out" type="number" min="0" step="0.01" value="${entry.cash_out}" aria-label="${escapeHtml(entry.player_name)} cash out">
      </td>
      <td class="settle-cell">
        <input data-settle-entry="${entry.id}" type="checkbox" ${entry.settled ? "checked" : ""} aria-label="${escapeHtml(entry.player_name)} settled">
      </td>
      <td class="money-cell ${klass}">${money(entry.profit)}</td>
      <td>
        <div class="entry-actions">
          <button data-action="buyin" data-entry="${entry.id}" type="button">Rebuy</button>
        </div>
      </td>
    </tr>
  `;
}

function renderLedger() {
  els.ledgerRows.innerHTML = state.ledger.length
    ? state.ledger.map((row) => {
        const klass = profitClass(row.total_profit);
        return `
          <article class="ledger-row">
            <div class="row-main">
              <span class="row-name">${escapeHtml(row.name)}</span>
              <span class="money-cell ${klass}">${money(row.total_profit)}</span>
            </div>
            <div class="row-stats">
              <span>${row.games_played} games</span>
              <span>In ${money(row.total_buy_in)}</span>
              <span>Out ${money(row.total_cash_out)}</span>
            </div>
          </article>
        `;
      }).join("")
    : `<p class="muted">Finished games will appear here.</p>`;
}

function renderHistory() {
  const finished = state.games.filter((game) => game.status === "finished");
  els.historyRows.innerHTML = finished.length
    ? finished.map((game) => {
        const klass = profitClass(game.total_profit);
        const selected = state.selectedGame?.id === game.id;
        const settled = Boolean(game.is_settled);
        return `
          <button class="history-row session-button${selected ? " selected" : ""}" data-game="${game.id}" type="button">
            <div class="row-main">
              <span class="row-name">${escapeHtml(game.title)}</span>
              <span>${game.played_on}</span>
            </div>
            <div class="row-stats">
              <span>${game.player_count} players</span>
              <span>BLINDS: ${blindMoney(game.small_blind)}/${blindMoney(game.big_blind)}</span>
              <span>IN: ${money(game.total_buy_in)}</span>
              <span>OUT: ${money(game.total_cash_out)}</span>
              <span class="${klass}">DIFF: ${money(game.total_profit)}</span>
              <span class="settled-indicator ${settled ? "settled" : "unsettled"}">${settled ? "SETTLED" : "NOT SETTLED"}</span>
            </div>
          </button>
        `;
      }).join("")
    : `<p class="muted">No recorded games.</p>`;
}

function renderPastGame() {
  const game = state.selectedGame;
  els.pastGamePanel.classList.toggle("hidden", !game);
  if (!game) return;

  const settledCount = game.entries.filter((entry) => entry.settled).length;
  const settled = Boolean(game.is_settled);
  els.pastGameTitle.textContent = game.title;
  els.pastGameStatus.textContent = `(${settledCount}/${game.entries.length}) settled`;
  els.pastGameStatus.classList.toggle("settled", settled);
  els.pastGameStatus.classList.toggle("unsettled", !settled);
  els.pastGameMeta.innerHTML = [
    `Date ${game.played_on}`,
    `Blinds ${blindMoney(game.small_blind)}/${blindMoney(game.big_blind)}`,
    `Stack ${money(game.starting_stack)}`,
  ]
    .map((item) => `<span class="meta-chip">${item}</span>`)
    .join("");

  els.pastGameEntries.innerHTML = game.entries.length
    ? game.entries.map(renderPastGameEntry).join("")
    : `<p class="muted">No players were recorded for this session.</p>`;
}

function renderPastGameEntry(entry) {
  const klass = profitClass(entry.profit);
  const settlementLabel = Number(entry.profit) >= 0 ? "Paid out" : "Paid";
  return `
    <label class="settlement-row">
      <input data-settle-entry="${entry.id}" type="checkbox" ${entry.settled ? "checked" : ""}>
      <span class="settlement-player">
        <span class="row-name">${escapeHtml(entry.player_name)}</span>
        <span class="row-stats">
          <span>In ${money(entry.buy_in_total)}</span>
          <span>Out ${money(entry.cash_out)}</span>
          <span class="${klass}">Profit ${money(entry.profit)}</span>
        </span>
      </span>
      <span class="settlement-status">${settlementLabel}</span>
    </label>
  `;
}

function formJson(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function entryInputs(entryId) {
  return [...document.querySelectorAll(`[data-entry="${entryId}"][data-field]`)];
}

async function saveEntry(entryId) {
  const payload = {};
  entryInputs(entryId).forEach((input) => {
    payload[input.dataset.field] = input.value;
  });
  state.activeGame = await api(`/api/entries/${entryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  await refreshAfterGameChange();
}

async function refreshAfterGameChange() {
  const [players, games, ledger] = await Promise.all([
    api("/api/players"),
    api("/api/games"),
    api("/api/ledger"),
  ]);
  state.players = players;
  state.games = games;
  state.ledger = ledger;
  render();
}

async function selectPastGame(gameId) {
  const game = await api(`/api/games/${gameId}`);
  if (game.status !== "finished") {
    throw new Error("Only finished sessions can be viewed here.");
  }
  state.selectedGame = game;
  renderHistory();
  renderPastGame();
  els.pastGamePanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

els.newGameForm.played_on.value = todayInputValue();

els.refreshBtn.addEventListener("click", () => {
  loadAll().then(() => showToast("Ledger refreshed.")).catch((error) => showToast(error.message));
});

els.newGameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    state.activeGame = await api("/api/games", {
      method: "POST",
      body: JSON.stringify(formJson(els.newGameForm)),
    });
    await refreshAfterGameChange();
    els.newGameForm.reset();
    els.newGameForm.played_on.value = todayInputValue();
    showToast("Game started.");
  } catch (error) {
    showToast(error.message);
  }
});

els.addPlayerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeGame) return;
  const payload = formJson(els.addPlayerForm);
  if (!payload.player_id) delete payload.player_id;
  if (!payload.name) delete payload.name;
  try {
    state.activeGame = await api(`/api/games/${state.activeGame.id}/players`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    els.addPlayerForm.reset();
    await refreshAfterGameChange();
    showToast("Player added.");
  } catch (error) {
    showToast(error.message);
  }
});

els.activeEntries.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button || !state.activeGame) return;
  const entryId = button.dataset.entry;
  try {
    if (button.dataset.action === "buyin") {
      state.activeGame = await api(`/api/entries/${entryId}`, {
        method: "PATCH",
        body: JSON.stringify({ buy_in_delta: state.activeGame.starting_stack }),
      });
      await refreshAfterGameChange();
    }
    if (button.dataset.action === "save-entry") {
      await saveEntry(entryId);
    }
  } catch (error) {
    showToast(error.message);
  }
});

els.activeEntries.addEventListener("change", async (event) => {
  const settleCheckbox = event.target.closest("input[data-settle-entry]");
  if (settleCheckbox) {
    if (!state.activeGame) return;
    try {
      state.activeGame = await api(`/api/entries/${settleCheckbox.dataset.settleEntry}/settled`, {
        method: "PATCH",
        body: JSON.stringify({ settled: settleCheckbox.checked }),
      });
      await refreshAfterGameChange();
      showToast(settleCheckbox.checked ? "Marked settled." : "Marked unsettled.");
    } catch (error) {
      settleCheckbox.checked = !settleCheckbox.checked;
      showToast(error.message);
    }
    return;
  }

  const input = event.target.closest("input[data-entry]");
  if (!input) return;
  try {
    await saveEntry(input.dataset.entry);
  } catch (error) {
    showToast(error.message);
  }
});

els.historyRows.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-game]");
  if (!button) return;
  try {
    await selectPastGame(button.dataset.game);
  } catch (error) {
    showToast(error.message);
  }
});

els.pastGameEntries.addEventListener("change", async (event) => {
  const checkbox = event.target.closest("input[data-settle-entry]");
  if (!checkbox || !state.selectedGame) return;
  try {
    state.selectedGame = await api(`/api/entries/${checkbox.dataset.settleEntry}/settled`, {
      method: "PATCH",
      body: JSON.stringify({ settled: checkbox.checked }),
    });
    await refreshAfterGameChange();
    showToast(checkbox.checked ? "Marked settled." : "Marked unsettled.");
  } catch (error) {
    checkbox.checked = !checkbox.checked;
    showToast(error.message);
  }
});

els.finishGameBtn.addEventListener("click", async () => {
  if (!state.activeGame) return;
  try {
    await api(`/api/games/${state.activeGame.id}/finish`, { method: "POST" });
    state.activeGame = null;
    await loadAll();
    showToast("Game saved to the ledger.");
  } catch (error) {
    showToast(error.message);
  }
});

loadAll().catch((error) => showToast(error.message));
