let queueModalOpen = false;
let queuePollTimer = null;
let badgePollTimer = null;
let queueCustomPaths = [];

(async function loadQueueCustomPaths() {
  try {
    const resp = await fetch("/api/custom-paths");
    const data = await resp.json();
    queueCustomPaths = data.paths || [];
  } catch (e) {
    /* ignore */
  }
})();

function openQueueModal() {
  queueModalOpen = true;
  document.getElementById("queueOverlay").style.display = "block";
  loadQueue();
  if (queuePollTimer) clearInterval(queuePollTimer);
  queuePollTimer = setInterval(loadQueue, 2000);
}

function closeQueueModal() {
  queueModalOpen = false;
  document.getElementById("queueOverlay").style.display = "none";
  if (queuePollTimer) {
    clearInterval(queuePollTimer);
    queuePollTimer = null;
  }
}

let lastFfmpegProgress = {};

async function loadQueue() {
  try {
    const resp = await fetch("/api/queue");
    const data = await resp.json();
    const items = data.items || [];
    lastFfmpegProgress = data.ffmpeg_progress || {};
    renderQueue(items);
    updateBadge(items);
  } catch (e) {
    /* ignore */
  }
}

function updateBadge(items) {
  const active = items.filter(
    (i) => i.status === "queued" || i.status === "running",
  ).length;
  const badge = document.getElementById("queueBadge");
  if (active > 0) {
    badge.textContent = active;
    badge.style.display = "inline-block";
  } else {
    badge.style.display = "none";
  }
}

function renderQueue(items) {
  const list = document.getElementById("queueList");

  // Show active items on top, then last 3 finished (newest first)
  const running = items.filter((i) => i.status === "running");
  const queued = items.filter((i) => i.status === "queued");
  const done = items
    .filter(
      (i) =>
        i.status === "completed" ||
        i.status === "failed" ||
        i.status === "cancelled",
    )
    .slice(-3)
    .reverse();
  const visible = running.concat(queued, done);

  if (!visible.length) {
    list.innerHTML = '<div class="queue-empty">Queue is empty</div>';
    return;
  }

  // Remember which error panels are expanded before re-render
  const expandedErrors = new Set();
  list.querySelectorAll(".queue-error-details.expanded").forEach((el) => {
    expandedErrors.add(el.id);
  });

  let html = "";
  visible.forEach((item) => {
    const isRunning = item.status === "running";
    const isActive =
      isRunning || (item.status === "cancelled" && item.current_url);
    const cls = isActive ? "queue-item queue-item-active" : "queue-item";

    const isCancelling = item.status === "cancelled" && item.current_url;

    let statusBadge = "";
    if (item.status === "running")
      statusBadge =
        '<span class="queue-status queue-status-running">In Progress</span>';
    else if (item.status === "queued")
      statusBadge =
        '<span class="queue-status queue-status-queued">Queued</span>';
    else if (item.status === "completed")
      statusBadge =
        '<span class="queue-status queue-status-completed">Completed</span>';
    else if (item.status === "failed")
      statusBadge =
        '<span class="queue-status queue-status-failed">Failed</span>';
    else if (isCancelling)
      statusBadge =
        '<span class="queue-status queue-status-cancelling">Cancelling...</span>';
    else if (item.status === "cancelled")
      statusBadge =
        '<span class="queue-status queue-status-cancelled">Cancelled</span>';

    let progressHtml = "";
    if (isRunning || isCancelling || item.status === "cancelled") {
      const epPct =
        item.total_episodes > 0
          ? (item.current_episode / item.total_episodes) * 100
          : 0;
      const seInfo = item.current_url
        ? parseSeasonEpisode(item.current_url)
        : "";

      // Combine episode progress with in-episode ffmpeg progress
      let ffPct = 0;
      if (isRunning && lastFfmpegProgress.active && item.total_episodes > 0) {
        ffPct = (lastFfmpegProgress.percent || 0) / item.total_episodes;
      }
      const combinedPct = Math.min(Math.round(epPct + ffPct), 100);

      let label;
      if (isCancelling) {
        label =
          item.current_episode +
          "/" +
          item.total_episodes +
          " episodes - finishing current episode...";
      } else if (item.status === "cancelled") {
        label =
          item.current_episode +
          "/" +
          item.total_episodes +
          " episodes (stopped)";
      } else {
        let epDetail = item.current_episode + "/" + item.total_episodes + " episodes";
        if (seInfo) epDetail += " - " + seInfo;
        if (lastFfmpegProgress.active && lastFfmpegProgress.percent > 0) {
          epDetail +=
            " (" + lastFfmpegProgress.percent + "%" +
            (lastFfmpegProgress.speed ? " @ " + lastFfmpegProgress.speed : "") +
            ")";
        }
        label = epDetail;
      }
      progressHtml =
        '<div class="queue-progress">' +
        '<div class="queue-progress-info">' +
        "<span>" +
        label +
        "</span>" +
        "<span>" +
        combinedPct +
        "%</span>" +
        "</div>" +
        '<div class="queue-progress-bar"><div class="queue-progress-fill" style="width:' +
        combinedPct +
        '%"></div></div>' +
        "</div>";
    }

    let errorsHtml = "";
    if (item.errors) {
      let errors = [];
      try {
        errors =
          typeof item.errors === "string"
            ? JSON.parse(item.errors)
            : item.errors;
      } catch (e) {}
      if (errors.length) {
        const errId = "qerr-" + item.id;
        let details = "";
        errors.forEach(function (err) {
          var ep = err.url ? parseSeasonEpisode(err.url) : "";
          var label = ep ? ep + ": " : "";
          details +=
            '<div class="queue-error-detail">' +
            escQ(label + (err.error || "")) +
            "</div>";
        });
        errorsHtml =
          "<div class=\"queue-errors queue-errors-expandable\" onclick=\"this.classList.toggle('expanded');document.getElementById('" +
          errId +
          "').classList.toggle('expanded')\">" +
          errors.length +
          ' error(s) <span class="queue-errors-toggle">&#9654;</span>' +
          "</div>" +
          '<div class="queue-error-details" id="' +
          errId +
          '">' +
          details +
          "</div>";
      }
    }

    let actionBtn = "";
    if (item.status === "queued") {
      actionBtn =
        '<button class="queue-move" onclick="moveQueueItem(' +
        item.id +
        ',\'up\')" title="Move up">&#9650;</button>' +
        '<button class="queue-move" onclick="moveQueueItem(' +
        item.id +
        ',\'down\')" title="Move down">&#9660;</button>' +
        '<button class="queue-remove" onclick="removeQueueItem(' +
        item.id +
        ')" title="Remove">&times;</button>';
    } else if (item.status === "running") {
      actionBtn =
        '<button class="queue-cancel" onclick="cancelQueueItem(' +
        item.id +
        ')" title="Cancel after current episode">Cancel</button>';
    }

    const userHtml = item.username
      ? '<span class="queue-user">' + escQ(item.username) + "</span>"
      : "";

    let pathHtml = "";
    if (item.custom_path_id) {
      const cp = queueCustomPaths.find((p) => p.id === item.custom_path_id);
      const pathName = cp ? cp.name : "Custom #" + item.custom_path_id;
      pathHtml = '<span class="queue-path">' + escQ(pathName) + "</span>";
    }

    const syncBadge = (item.source || "").startsWith("sync")
      ? '<span class="queue-sync-badge">[Sync]</span> '
      : "";

    html +=
      '<div class="' +
      cls +
      '">' +
      '<div class="queue-item-header">' +
      '<div class="queue-item-title">' +
      syncBadge +
      escQ(item.title) +
      "</div>" +
      '<div class="queue-item-right">' +
      statusBadge +
      actionBtn +
      "</div>" +
      "</div>" +
      '<div class="queue-item-meta">' +
      "<span>" +
      item.total_episodes +
      " episode(s)</span>" +
      "<span>" +
      escQ(item.language) +
      "</span>" +
      "<span>" +
      escQ(item.provider) +
      "</span>" +
      pathHtml +
      userHtml +
      "</div>" +
      progressHtml +
      errorsHtml +
      "</div>";
  });

  list.innerHTML = html;

  // Restore expanded state (both the details panel and its sibling header)
  expandedErrors.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.classList.add("expanded");
      const header = el.previousElementSibling;
      if (header) header.classList.add("expanded");
    }
  });
}

function parseSeasonEpisode(url) {
  const m = url.match(/staffel-(\d+)\/episode-(\d+)/i);
  if (m) return "S" + m[1] + "E" + m[2];
  const f = url.match(/filme\/film-(\d+)/i);
  if (f) return "Film " + f[1];
  return "";
}

async function cancelQueueItem(id) {
  try {
    const resp = await fetch("/api/queue/" + id + "/cancel", {
      method: "POST",
    });
    const data = await resp.json();
    if (data.error) {
      if (typeof showToast === "function") showToast(data.error);
    } else {
      if (typeof showToast === "function")
        showToast("Cancelling after current episode...");
    }
    loadQueue();
  } catch (e) {
    /* ignore */
  }
}

async function moveQueueItem(id, direction) {
  try {
    const resp = await fetch("/api/queue/" + id + "/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction }),
    });
    const data = await resp.json();
    if (data.error && typeof showToast === "function") showToast(data.error);
    loadQueue();
  } catch (e) {
    /* ignore */
  }
}

async function removeQueueItem(id) {
  try {
    const resp = await fetch("/api/queue/" + id, { method: "DELETE" });
    const data = await resp.json();
    if (data.error) {
      if (typeof showToast === "function") showToast(data.error);
    }
    loadQueue();
  } catch (e) {
    /* ignore */
  }
}

function escQ(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

// ESC key closes queue modal
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape" && queueModalOpen) closeQueueModal();
});

// Background badge poll every 10s
(function startBadgePoll() {
  loadQueue();
  badgePollTimer = setInterval(function () {
    if (!queueModalOpen) loadQueue();
  }, 10000);
})();
