/* Auto-Sync page: status, last report and the exclusion list. */

(function () {
  const el = (id) => document.getElementById(id);

  const syncNowBtn = el("syncNowBtn");
  const exclusionsBody = el("exclusionsBody");
  let excludedUrls = new Set();

  // While a run is going, poll often enough to feel live
  const IDLE_POLL = 30000;
  const RUNNING_POLL = 3000;

  let timer = null;

  const STATUS_CLASS = {
    queued: "status-completed",
    "up-to-date": "status-queued",
    skipped: "status-cancelled",
    error: "status-failed"
  };

  const STATUS_LABELS = {
    queued: "Queued",
    "up-to-date": "Up to date",
    skipped: "Skipped",
    error: "Error"
  };

  function statusLabel(status) {
    const key = String(status).replace(/-/g, "_");
    return t(`autosync.status.${key}`, STATUS_LABELS[status] || status);
  }

  function formatTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString();
  }

  function schedule(running) {
    clearTimeout(timer);
    timer = setTimeout(load, running ? RUNNING_POLL : IDLE_POLL);
  }

  function renderReport(report) {
    const container = el("syncReport");
    if (!report) {
      container.innerHTML = `<div class="empty-state">${t("autosync.never_ran", "Auto-Sync has not run yet.")}</div>`;
      return;
    }
    if (report.error) {
      container.innerHTML = `<div class="empty-state">${esc(report.error)}</div>`;
      return;
    }

    const rows = report.results || [];
    if (!rows.length) {
      container.innerHTML = `<div class="empty-state">${t("autosync.no_matches", "No titles from the newest episodes matched your library.")}</div>`;
      return;
    }

    container.innerHTML = rows
      .map((row) => {
        const detail = row.reason
          ? esc(row.reason)
          : row.episodes
            ? t("autosync.queued_episodes", "{count} episodes queued in {language}", {
                count: row.episodes,
                language: row.language || ""
              })
            : esc(row.language || "");
        // A show held twice produces one row per copy, so each has to say which
        // library and language folder it is talking about.
        const where = row.where
          ? `<span class="sync-row-where">${esc(row.where)}</span>`
          : "";
        return `
          <div class="sync-row">
            <div class="sync-row-main">
              <span class="sync-row-title">${esc(row.title)}${where}</span>
              <span class="sync-row-detail">${detail}</span>
            </div>
            <span class="status-pill ${STATUS_CLASS[row.status] || "status-queued"}">${esc(statusLabel(row.status))}</span>
          </div>`;
      })
      .join("");
  }

  async function load() {
    let data;
    try {
      data = await apiFetch("/api/autosync/status");
    } catch (error) {
      schedule(false);
      return;
    }

    // Step 4 of "How it works" describes two different things
    el("howFill").hidden = Boolean(data.new_only);
    el("howNewOnly").hidden = !data.new_only;

    el("lastRun").textContent = formatTime(data.last_run);
    el("nextRun").textContent = data.running
      ? t("autosync.running", "Running...")
      : formatTime(data.next_run);

    const report = data.last_report;
    el("lastResult").textContent = report && !report.error
      ? t("autosync.result", "{queued} of {checked} queued", {
          queued: report.queued,
          checked: report.checked
        })
      : "-";

    renderReport(report);

    syncNowBtn.disabled = Boolean(data.running);
    syncNowBtn.textContent = data.running
      ? t("autosync.running", "Running...")
      : t("autosync.sync_now", "Sync now");

    schedule(data.running);
  }

  syncNowBtn.addEventListener("click", async () => {
    syncNowBtn.disabled = true;
    try {
      await apiSend("/api/autosync/run", "POST");
      showToast(t("autosync.started", "Sync started"));
      schedule(true);
      load();
    } catch (error) {
      showToast(error.message);
      syncNowBtn.disabled = false;
    }
  });

  /* ===== Exclusions ===== */
  async function loadExclusions() {
    let data;
    try {
      data = await apiFetch("/api/autosync/exclusions");
    } catch (error) {
      showToast(error.message);
      return;
    }

    const rows = data.exclusions || [];
    excludedUrls = new Set(rows.map((row) => row.series_url));
    if (!rows.length) {
      exclusionsBody.innerHTML = `<tr class="empty-row"><td colspan="3">${t("autosync.no_exclusions", "Nothing excluded.")}</td></tr>`;
      return;
    }

    exclusionsBody.innerHTML = rows
      .map(
        (row) => `
        <tr>
          <td>${esc(row.title || "-")}</td>
          <td><a href="${esc(row.series_url)}" target="_blank" rel="noopener noreferrer">${esc(row.series_url)}</a></td>
          <td>
            <button class="btn btn-danger" data-remove="${row.id}">${t("common.remove", "Remove")}</button>
          </td>
        </tr>`
      )
      .join("");
  }

  /* ===== Adding an exclusion =====
     Auto-Sync keys exclusions by series URL, so titles are looked up through
     the normal aniworld search to get one. */
  const searchInput = el("excludeSearch");
  const searchBtn = el("excludeSearchBtn");
  const searchResults = el("excludeResults");

  async function searchTitles() {
    const keyword = searchInput.value.trim();
    if (!keyword) return;

    searchBtn.disabled = true;
    searchResults.innerHTML = `<div class="empty-state">${t("common.loading", "Loading...")}</div>`;
    try {
      const data = await apiSend("/api/search", "POST", {
        keyword,
        site: "aniworld"
      });
      renderSearchResults(data.results || []);
    } catch (error) {
      searchResults.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
    } finally {
      searchBtn.disabled = false;
    }
  }

  function renderSearchResults(results) {
    if (!results.length) {
      searchResults.innerHTML = `<div class="empty-state">${t("index.no_results", "No results found.")}</div>`;
      return;
    }

    searchResults.innerHTML = results
      .slice(0, 12)
      .map((item) => {
        const already = excludedUrls.has(item.url);
        const title = decodeEntities(item.title);
        return `
          <div class="exclude-result">
            <span class="exclude-result-title" title="${esc(title)}">${esc(title)}</span>
            <button class="btn btn-ghost" data-add-url="${esc(item.url)}"
              data-add-title="${esc(title)}" ${already ? "disabled" : ""}>
              ${already ? t("autosync.already_excluded", "Excluded") : t("autosync.exclude", "Exclude")}
            </button>
          </div>`;
      })
      .join("");
  }

  searchBtn.addEventListener("click", searchTitles);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchTitles();
  });

  searchResults.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-add-url]");
    if (!button) return;
    button.disabled = true;
    try {
      await apiSend("/api/autosync/exclusions", "POST", {
        series_url: button.dataset.addUrl,
        title: button.dataset.addTitle
      });
      showToast(t("autosync.added", "Excluded from Auto-Sync"));
      button.textContent = t("autosync.already_excluded", "Excluded");
      await loadExclusions();
    } catch (error) {
      showToast(error.message);
      button.disabled = false;
    }
  });

  exclusionsBody.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-remove]");
    if (!button) return;
    try {
      await apiSend(`/api/autosync/exclusions/${button.dataset.remove}`, "DELETE");
      loadExclusions();
    } catch (error) {
      showToast(error.message);
    }
  });

  load();
  loadExclusions();
})();
