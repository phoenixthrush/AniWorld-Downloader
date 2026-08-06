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
    if (!badge) return;
    const active = items.filter((item) => ACTIVE.includes(item.status)).length;
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

  function progressPercent(item, ffmpeg) {
    const total = item.total_episodes || 1;
    const done = item.current_episode || 0;
    if (item.status === "completed") return 100;
    // ffmpeg reports the percentage of the episode currently being written
    const partial = item.status === "running" ? (ffmpeg[String(item.id)] || 0) / 100 : 0;
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

    let markup = `<details class="queue-errors"><summary>${t("queue.errors", "Errors")} (${errors.length})</summary><ul>${rows}</ul></details>`;
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
      buttons.push(
        `<button class="icon-btn" data-action="cancel" data-id="${item.id}" title="${t("common.cancel", "Cancel")}">&times;</button>`
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

  function render(items, ffmpeg) {
    if (!items.length) {
      list.innerHTML = `<div class="empty-state">${t("queue.empty", "The download queue is empty.")}</div>`;
      return;
    }

    list.innerHTML = items
      .map((item) => {
        const percent = progressPercent(item, ffmpeg);
        const counter = t("queue.episode_of", "Episode {current} of {total}", {
          current: Math.min((item.current_episode || 0) + 1, item.total_episodes),
          total: item.total_episodes
        });
        const meta = [
          item.language,
          item.provider,
          ACTIVE.includes(item.status) ? counter : null,
          durationLabel(item)
        ]
          .filter(Boolean)
          .join(" | ");

        const captchaBtn =
          item.status === "running" && item.captcha_url
            ? `<button class="btn btn-ghost" data-action="captcha" data-id="${item.id}">${t("queue.solve_captcha", "Solve captcha")}</button>`
            : "";

        return `
          <div class="queue-item">
            <div class="queue-item-head">
              <div>
                <div class="queue-item-title">${esc(item.title)}</div>
                <div class="queue-item-meta">${esc(meta)}</div>
              </div>
              <div class="queue-item-actions">
                <span class="status-pill status-${item.status}">${esc(statusLabel(item.status))}</span>
                ${renderActions(item)}
              </div>
            </div>
            <div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>
            ${captchaBtn ? `<div class="action-row">${captchaBtn}</div>` : ""}
            ${renderErrors(item)}
          </div>`;
      })
      .join("");
  }

  /* ===== Actions ===== */
  const ENDPOINTS = {
    cancel: (id) => [`/api/queue/${id}/cancel`, "POST"],
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
