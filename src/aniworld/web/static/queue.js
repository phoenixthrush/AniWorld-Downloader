/* Download queue modal, badge polling and the captcha viewer. */

(function () {
  const overlay = document.getElementById("queueOverlay");
  const list = document.getElementById("queueList");
  const badge = document.getElementById("queueBadge");
  const openBtn = document.getElementById("queueBtn");
  const clearBtn = document.getElementById("clearCompletedBtn");

  // Poll fast while the modal is open, slowly just to keep the badge fresh.
  const OPEN_INTERVAL = 1500;
  const BADGE_INTERVAL = 10000;

  const ACTIVE = ["queued", "running"];

  // A little longer than the poll, so the bar is still gliding towards the
  // last value when the next one arrives and never comes to a stop.
  list.style.setProperty("--progress-step", `${OPEN_INTERVAL + 200}ms`);

  let timer = null;
  let modalOpen = false;
  let inFlight = null;

  function schedule() {
    clearInterval(timer);
    timer = setInterval(refresh, modalOpen ? OPEN_INTERVAL : BADGE_INTERVAL);
  }

  async function refresh() {
    if (document.hidden && !modalOpen) return;
    if (inFlight) return;
    inFlight = apiFetch("/api/queue")
      .then((data) => {
        const items = data.items || [];
        updateBadge(items);
        if (modalOpen) render(items, data.ffmpeg_progress || {});
      })
      .catch(() => {})
      .finally(() => {
        inFlight = null;
      });
  }

  function updateBadge(items) {
    const active = items.filter((item) => ACTIVE.includes(item.status)).length;
    // themes hang off these, so they are set even when the badge is missing
    document.body.dataset.queue = active ? "active" : "idle";
    document.body.dataset.queueCount = String(active);
    if (!badge) return;
    badge.textContent = String(active);
    badge.hidden = active === 0;
  }

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
    const total = item.total_episodes || 1;
    const done = item.current_episode || 0;
    if (item.status === "completed") return 100;
    // ffmpeg reports one percentage for the file it is writing right now, and
    // the worker only ever runs one item, so it belongs to the running one
    const partial =
      item.status === "running" && ffmpeg.active ? (ffmpeg.percent || 0) / 100 : 0;
    return Math.min(100, Math.round(((done + partial) / total) * 100));
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

  function renderActions(item) {
    const buttons = [];
    if (item.status === "queued") {
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
        ${captchaBtn ? `<div class="action-row">${captchaBtn}</div>` : ""}
        ${renderErrors(item)}
      </div>`;
  }

  /* ===== Painting the list =====
     A running item changes on every poll, so rewriting the list would rebuild
     the button under the pointer a second at a time and make it flicker. Only
     the parts that actually moved are touched, and the buttons are left alone
     unless the set of them changes. */

  // Everything except the numbers that tick while a download runs
  function structure(item) {
    return JSON.stringify([
      item.title,
      item.status,
      isStopping(item),
      item.errors,
      item.captcha_url || "",
      item.total_episodes
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

  function paint(node, item, ffmpeg) {
    if (node.dataset.structure !== structure(item)) {
      // trimmed, the markup is indented and would leave text nodes behind
      node.outerHTML = renderItem(item, ffmpeg).trim();
      return list.querySelector(`[data-item="${item.id}"]`);
    }
    node.querySelector(".queue-item-meta").textContent = metaLine(item);
    setProgress(node, progressPercent(item, ffmpeg));
    return node;
  }

  function render(items, ffmpeg) {
    if (!items.length) {
      if (!list.querySelector(".empty-state")) {
        list.innerHTML = `<div class="empty-state">${t("queue.empty", "The download queue is empty.")}</div>`;
      }
      return;
    }

    const empty = list.querySelector(".empty-state");
    if (empty) empty.remove();

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

  /* ===== Actions ===== */
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
        refresh();
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  if (openBtn) {
    openBtn.addEventListener("click", () => {
      modalOpen = true;
      openModal("queueOverlay");
      list.innerHTML = `<div class="empty-state">${t("common.loading", "Loading...")}</div>`;
      refresh();
      schedule();
    });
  }

  overlay.addEventListener("modal-closed", () => {
    modalOpen = false;
    schedule();
  });

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
      const status = await apiFetch(`/api/captcha/${captchaId}/status`);
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

  window.refreshQueue = refresh;

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });

  refresh();
  schedule();
})();
