/* The queue page: one page of rows at a time, with filters, search and sort,
 * plus the captcha viewer that queue rows link into.
 *
 * Only ever asks for PAGE_SIZE rows. The whole queue used to come down on every
 * poll, which grew without bound because nothing prunes finished downloads.
 */

(function () {
  const list = document.getElementById("queueList");
  if (!list) return;

  const filters = document.getElementById("queueFilters");
  const searchInput = document.getElementById("queueSearch");
  const sortSelect = document.getElementById("queueSort");
  const pager = document.getElementById("queuePager");
  const pagerLabel = document.getElementById("pagerLabel");
  const badge = document.getElementById("queueBadge");
  const clearBtn = document.getElementById("clearCompletedBtn");

  const PAGE_SIZE = 25;
  const POLL = 1500;
  // Long enough for a loaded server, short enough that a wedged request cannot
  // sit there forever holding the poller shut.
  const TIMEOUT = 10000;

  const ACTIVE = ["queued", "running"];

  // A little longer than the poll, so the bar is still gliding towards the
  // last value when the next one arrives and never comes to a stop.
  list.style.setProperty("--progress-step", `${POLL + 200}ms`);

  const state = { status: "", q: "", sort: "smart", page: 0 };
  let total = 0;
  let timer = null;
  let inFlight = false;
  let loaded = false;

  /* ===== Formatting ===== */
  const STATUS_LABELS = {
    queued: "Queued",
    running: "Running",
    completed: "Done",
    failed: "Failed",
    cancelled: "Cancelled"
  };

  function statusLabel(status) {
    return t(`queue.status.${status}`, STATUS_LABELS[status] || status);
  }

  // A running item that was asked to stop keeps downloading until the current
  // episode is written, so it needs a state of its own.
  function isStopping(item) {
    return item.status === "running" && Boolean(item.cancel_requested);
  }

  function progressPercent(item, ffmpeg) {
    const count = item.total_episodes || 1;
    const done = item.current_episode || 0;
    if (item.status === "completed") return 100;
    // ffmpeg reports one percentage for the file it is writing right now, and
    // the worker only ever runs one item, so it belongs to the running one
    const partial =
      item.status === "running" && ffmpeg.active ? (ffmpeg.percent || 0) / 100 : 0;
    return Math.min(100, Math.round(((done + partial) / count) * 100));
  }

  /* "bandwidth" is bytes off the wire, already formatted as MB/s by both the
     ffmpeg and the segment path. It needs two size samples, so it is empty for
     the first moment of a download. ffmpeg also reports a "speed=" multiplier
     against real time, but showing that in the gap swaps the unit under the
     reader a second later, so the reading stays in MB/s and just starts at 0. */
  function speedLabel(item, ffmpeg) {
    if (item.status !== "running") return "";
    return (ffmpeg.active && ffmpeg.bandwidth) || "0 MB/s";
  }

  function formatDuration(seconds) {
    if (seconds < 60) return t("queue.secs", "{n}s", { n: seconds });
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return t("queue.mins", "{n}min", { n: minutes });
    return t("queue.hours", "{h}h {m}min", {
      h: Math.floor(minutes / 60),
      m: minutes % 60
    });
  }

  // Only counts time spent downloading, waiting in the queue does not show up
  function durationLabel(item) {
    const seconds = item.duration_seconds;
    if (seconds == null) return null;
    const time = formatDuration(seconds);
    return item.status === "running"
      ? t("queue.active_for", "active for {time}", { time })
      : t("queue.took", "took {time}", { time });
  }

  function metaLine(item) {
    const counter = t("queue.episode_of", "Episode {current} of {total}", {
      current: Math.min((item.current_episode || 0) + 1, item.total_episodes),
      total: item.total_episodes
    });
    return [
      item.language,
      item.provider,
      ACTIVE.includes(item.status) ? counter : null,
      durationLabel(item)
    ]
      .filter(Boolean)
      .join(" | ");
  }

  /* ===== Rows ===== */

  // The list re-renders on every poll, so remember which error panels are open
  // or they snap shut under the user a second after they click them.
  const openErrors = new Set();

  list.addEventListener(
    "toggle",
    (event) => {
      const details = event.target.closest("[data-errors-for]");
      if (!details) return;
      const id = Number(details.dataset.errorsFor);
      if (details.open) openErrors.add(id);
      else openErrors.delete(id);
    },
    true // toggle does not bubble
  );

  function renderErrors(item) {
    let errors = [];
    try {
      errors = JSON.parse(item.errors || "[]");
    } catch (e) {
      errors = [];
    }
    if (!errors.length) return "";

    const captcha = errors.find((entry) => entry.captcha_url);
    const rows = errors
      .slice(0, 8)
      .map((entry) => `<li>${esc(entry.error || "")}</li>`)
      .join("");

    let markup = `<details class="queue-errors" data-errors-for="${item.id}"${openErrors.has(item.id) ? " open" : ""}><summary>${t("queue.errors", "Errors")} (${errors.length})</summary><ul>${rows}</ul></details>`;
    if (captcha) {
      markup += `<div class="action-row"><a class="btn btn-ghost" href="${esc(captcha.captcha_url)}" target="_blank" rel="noopener noreferrer">${t("queue.open_captcha", "Solve captcha in browser")}</a></div>`;
    }
    return markup;
  }

  /* Reordering only makes sense against the queue's own order, and only when
     the whole queue is on show; a filtered or re-sorted page would move a row
     past a neighbour the reader cannot see. */
  function reorderable() {
    return state.sort === "smart" && !state.status && !state.q;
  }

  function renderActions(item) {
    const buttons = [];
    if (item.status === "queued" && reorderable()) {
      buttons.push(
        `<button class="icon-btn" data-action="move" data-direction="up" data-id="${item.id}" title="Up">&uarr;</button>`,
        `<button class="icon-btn" data-action="move" data-direction="down" data-id="${item.id}" title="Down">&darr;</button>`
      );
    }
    if (ACTIVE.includes(item.status)) {
      const stopping = isStopping(item);
      const label = stopping
        ? t("queue.force_cancel", "Force cancel")
        : t("common.cancel", "Cancel");
      buttons.push(
        `<button class="icon-btn${stopping ? " icon-btn-danger" : ""}"
          data-action="${stopping ? "force" : "cancel"}" data-id="${item.id}"
          title="${label}" aria-label="${label}">&times;</button>`
      );
    } else {
      if (item.status === "failed" || item.status === "cancelled") {
        buttons.push(
          `<button class="icon-btn" data-action="retry" data-id="${item.id}" title="${t("common.retry", "Retry")}">&#8635;</button>`
        );
      }
      buttons.push(
        `<button class="icon-btn" data-action="remove" data-id="${item.id}" title="${t("common.remove", "Remove")}">&times;</button>`
      );
    }
    return buttons.join("");
  }

  function renderItem(item, ffmpeg) {
    const percent = progressPercent(item, ffmpeg);
    const meta = metaLine(item);

    const captchaBtn =
      item.status === "running" && item.captcha_url
        ? `<button class="btn btn-ghost" data-action="captcha" data-id="${item.id}">${t("queue.solve_captcha", "Solve captcha")}</button>`
        : "";

    const stopping = isStopping(item);
    const pill = stopping ? "status-cancelled" : `status-${item.status}`;
    const label = stopping
      ? t("queue.status.stopping", "Stopping after this episode")
      : statusLabel(item.status);

    return `
      <div class="queue-item" data-item="${item.id}">
        <div class="queue-item-head">
          <div>
            <div class="queue-item-title">${esc(item.title)}</div>
            <div class="queue-item-meta">${esc(meta)}</div>
          </div>
          <div class="queue-item-actions">
            <span class="status-pill ${pill}">${esc(label)}</span>
            ${renderActions(item)}
          </div>
        </div>
        <div class="progress-track"><div class="progress-fill" data-percent="${percent}" style="width:${percent}%"></div></div>
        <div class="progress-stats"${item.status === "running" ? "" : " hidden"}>
          <span data-progress-percent>${percent}%</span>
          <span data-progress-speed>${esc(speedLabel(item, ffmpeg))}</span>
        </div>
        ${captchaBtn ? `<div class="action-row">${captchaBtn}</div>` : ""}
        ${renderErrors(item)}
      </div>`;
  }

  /* ===== Painting =====
     A running item changes on every poll, so rewriting the list would rebuild
     the button under the pointer a second at a time and make it flicker. Only
     the parts that actually moved are touched. */

  /* Everything except the numbers that tick while a download runs. reorderable()
     belongs here too: a row that survives a sort or filter change would
     otherwise keep the move arrows it was built with. */
  function structure(item) {
    return JSON.stringify([
      item.title,
      item.status,
      isStopping(item),
      item.errors,
      item.captcha_url || "",
      item.total_episodes,
      reorderable()
    ]);
  }

  function setProgress(node, percent) {
    const fill = node.querySelector(".progress-fill");
    const previous = Number(fill.dataset.percent);
    // only animate forwards, a reset should land straight back at the start
    fill.classList.toggle("no-transition", percent < previous);
    fill.style.width = `${percent}%`;
    fill.dataset.percent = percent;
  }

  /* status decides whether the row is there at all and is part of structure(),
     so by the time we get here it only ever needs its numbers refreshed. */
  function setStats(node, item, ffmpeg, percent) {
    const percentNode = node.querySelector("[data-progress-percent]");
    if (!percentNode) return;
    percentNode.textContent = `${percent}%`;
    node.querySelector("[data-progress-speed]").textContent = speedLabel(item, ffmpeg);
  }

  function paint(node, item, ffmpeg) {
    if (node.dataset.structure !== structure(item)) {
      // trimmed, the markup is indented and would leave text nodes behind
      node.outerHTML = renderItem(item, ffmpeg).trim();
      return list.querySelector(`[data-item="${item.id}"]`);
    }
    const percent = progressPercent(item, ffmpeg);
    node.querySelector(".queue-item-meta").textContent = metaLine(item);
    setProgress(node, percent);
    setStats(node, item, ffmpeg, percent);
    return node;
  }

  function renderNotice(markup) {
    list.innerHTML = markup;
  }

  function render(items, ffmpeg) {
    if (!items.length) {
      const message =
        state.status || state.q
          ? t("queue.no_matches", "Nothing here matches that filter.")
          : t("queue.empty", "The download queue is empty.");
      renderNotice(`<div class="empty-state">${message}</div>`);
      return;
    }

    if (list.querySelector(".empty-state, .queue-error")) list.innerHTML = "";

    const wanted = new Set();
    items.forEach((item, index) => {
      wanted.add(String(item.id));
      let node = list.querySelector(`[data-item="${item.id}"]`);
      if (node) {
        node = paint(node, item, ffmpeg);
      } else {
        list.insertAdjacentHTML("beforeend", renderItem(item, ffmpeg).trim());
        node = list.lastElementChild;
      }
      node.dataset.structure = structure(item);
      // moving an existing node keeps it alive, so hover and focus survive
      if (list.children[index] !== node) {
        list.insertBefore(node, list.children[index] || null);
      }
    });

    Array.from(list.children).forEach((child) => {
      if (!wanted.has(child.dataset.item)) child.remove();
    });
  }

  /* ===== Controls ===== */
  function pageCount() {
    return Math.max(1, Math.ceil(total / PAGE_SIZE));
  }

  function paintControls(counts) {
    if (counts) {
      filters.querySelectorAll("[data-count]").forEach((node) => {
        node.textContent = counts[node.dataset.count] || 0;
      });
      const active = counts.active || 0;
      document.body.dataset.queue = active ? "active" : "idle";
      document.body.dataset.queueCount = String(active);
      if (badge) {
        badge.textContent = String(active);
        badge.hidden = active === 0;
      }
    }

    const pages = pageCount();
    pager.hidden = total <= PAGE_SIZE;
    pagerLabel.textContent = t("queue.page_of", "Page {page} of {pages}", {
      page: state.page + 1,
      pages: pages
    });
    pager.querySelector('[data-page="prev"]').disabled = state.page === 0;
    pager.querySelector('[data-page="next"]').disabled = state.page + 1 >= pages;
  }

  /* ===== Loading ===== */
  function query() {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(state.page * PAGE_SIZE),
      sort: state.sort
    });
    if (state.status) params.set("status", state.status);
    if (state.q) params.set("q", state.q);
    return `/api/queue?${params.toString()}`;
  }

  async function refresh() {
    if (document.hidden || inFlight) return;
    inFlight = true;
    try {
      const data = await apiFetch(query(), { timeoutMs: TIMEOUT });
      total = data.total || 0;

      // Deleting the last row of the last page would otherwise strand the
      // reader on an empty page with no way back except the pager.
      const pages = pageCount();
      if (state.page > 0 && state.page >= pages) {
        state.page = pages - 1;
        inFlight = false;
        return refresh();
      }

      render(data.items || [], data.ffmpeg_progress || {});
      paintControls(data.counts);
      loaded = true;
    } catch (error) {
      // Keep whatever is already on screen; only a first load has nothing to
      // show, and either way say what went wrong instead of sitting on
      // "Loading..." forever.
      if (!loaded) {
        renderNotice(
          `<div class="queue-error">
             <p>${esc(error.message)}</p>
             <button class="btn btn-secondary" data-action="reload">${t("common.retry", "Retry")}</button>
           </div>`
        );
      }
    } finally {
      inFlight = false;
    }
  }

  function reload(resetPage) {
    if (resetPage) state.page = 0;
    refresh();
  }

  function schedule() {
    clearInterval(timer);
    timer = setInterval(refresh, POLL);
  }

  /* ===== Events ===== */
  filters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-status]");
    if (!chip) return;
    filters.querySelectorAll(".chip").forEach((node) => node.classList.remove("is-active"));
    chip.classList.add("is-active");
    state.status = chip.dataset.status;
    reload(true);
  });

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = searchInput.value.trim();
      reload(true);
    }, 300);
  });

  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    reload(true);
  });

  pager.addEventListener("click", (event) => {
    const button = event.target.closest("[data-page]");
    if (!button || button.disabled) return;
    const pages = pageCount();
    state.page =
      button.dataset.page === "next"
        ? Math.min(state.page + 1, pages - 1)
        : Math.max(state.page - 1, 0);
    list.scrollIntoView({ block: "start", behavior: "smooth" });
    refresh();
  });

  const ENDPOINTS = {
    cancel: (id) => [`/api/queue/${id}/cancel`, "POST"],
    force: (id) => [`/api/queue/${id}/force-cancel`, "POST"],
    retry: (id) => [`/api/queue/${id}/retry`, "POST"],
    remove: (id) => [`/api/queue/${id}`, "DELETE"]
  };

  list.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;

    if (action === "reload") {
      refresh();
      return;
    }
    if (action === "captcha") {
      openCaptcha(Number(id));
      return;
    }

    try {
      if (action === "move") {
        await apiSend(`/api/queue/${id}/move`, "POST", {
          direction: button.dataset.direction
        });
      } else {
        const [url, method] = ENDPOINTS[action](id);
        await apiSend(url, method);
      }
      refresh();
    } catch (error) {
      showToast(error.message);
    }
  });

  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      try {
        await apiSend("/api/queue/completed", "DELETE");
        reload(true);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  /* ===== Captcha viewer ===== */
  const captchaOverlay = document.getElementById("captchaOverlay");
  const captchaImage = document.getElementById("captchaScreenshot");
  let captchaId = null;
  let captchaTimer = null;

  function openCaptcha(queueId) {
    captchaId = queueId;
    openModal("captchaOverlay");
    tickCaptcha();
    captchaTimer = setInterval(tickCaptcha, 700);
  }

  async function tickCaptcha() {
    if (captchaId == null) return;
    captchaImage.src = `/api/captcha/${captchaId}/screenshot?ts=${Date.now()}`;
    try {
      const status = await apiFetch(`/api/captcha/${captchaId}/status`, {
        timeoutMs: TIMEOUT
      });
      if (!status.active || status.done) closeCaptcha();
    } catch (e) {
      closeCaptcha();
    }
  }

  function closeCaptcha() {
    clearInterval(captchaTimer);
    captchaTimer = null;
    captchaId = null;
    closeModal("captchaOverlay");
  }

  captchaOverlay.addEventListener("modal-closed", () => {
    clearInterval(captchaTimer);
    captchaTimer = null;
    captchaId = null;
  });

  // Forward clicks to the real browser, scaled to its viewport size
  captchaImage.addEventListener("click", async (event) => {
    if (captchaId == null) return;
    const rect = captchaImage.getBoundingClientRect();
    const scaleX = captchaImage.naturalWidth / rect.width || 1;
    const scaleY = captchaImage.naturalHeight / rect.height || 1;
    try {
      await apiSend(`/api/captcha/${captchaId}/click`, "POST", {
        x: Math.round((event.clientX - rect.left) * scaleX),
        y: Math.round((event.clientY - rect.top) * scaleY)
      });
    } catch (error) {
      showToast(error.message);
    }
  });

  // Replaces the badge-only refresh from queue-badge.js while this page is up
  window.refreshQueue = refresh;

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });

  renderNotice(`<div class="empty-state">${t("common.loading", "Loading...")}</div>`);
  refresh();
  schedule();
})();
