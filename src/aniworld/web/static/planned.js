// Planned releases page.

const plannedList = document.getElementById("plannedList");
const plannedEmpty = document.getElementById("plannedEmpty");

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3000);
}

function tt(key, fallback) {
  return typeof window.t === "function" ? window.t(key, fallback) : fallback;
}

async function loadPlannedPaths() {
  const select = document.getElementById("plannedPath");
  if (!select) return;
  try {
    const resp = await fetch("/api/custom-paths");
    const data = await resp.json();
    (data.paths || []).forEach(function (p) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
  } catch (e) {
    /* best-effort */
  }
}

async function loadPlanned() {
  try {
    const resp = await fetch("/api/planned");
    const data = await resp.json();
    renderPlanned(data.jobs || []);
  } catch (e) {
    showToast("Failed to load planned items: " + e.message);
  }
}

function statusLabel(status) {
  const map = {
    waiting: tt("planned.status_waiting", "Waiting"),
    found: tt("planned.status_found", "Found"),
    error: tt("planned.status_error", "Error"),
  };
  return map[status] || status;
}

function renderPlanned(jobs) {
  if (!jobs.length) {
    plannedList.innerHTML = "";
    plannedList.appendChild(plannedEmpty);
    plannedEmpty.style.display = "";
    return;
  }
  plannedEmpty.style.display = "none";
  plannedList.innerHTML = "";

  jobs.forEach(function (job) {
    const row = document.createElement("div");
    row.className = "planned-row";
    row.innerHTML =
      '<div class="planned-main">' +
      '<div class="planned-title">' +
      esc(job.title) +
      "</div>" +
      '<div class="planned-meta">' +
      esc(job.media_type === "movie" ? tt("planned.type_movie", "Movie") : tt("planned.type_series", "Series")) +
      " · " +
      esc(job.language) +
      " · " +
      esc(job.provider) +
      "</div>" +
      "</div>" +
      '<div class="planned-status planned-status-' +
      esc(job.status) +
      '">' +
      statusLabel(job.status) +
      "</div>" +
      '<div class="planned-check">' +
      (job.last_check ? esc(job.last_check) : "—") +
      "</div>" +
      '<div class="planned-actions">' +
      '<button class="btn-secondary" onclick="checkPlanned(' +
      job.id +
      ')">' +
      tt("planned.check_now", "Check now") +
      "</button>" +
      '<button class="btn-del" onclick="deletePlanned(' +
      job.id +
      ')">' +
      tt("common.delete", "Delete") +
      "</button>" +
      "</div>";
    plannedList.appendChild(row);
  });
}

async function addPlanned() {
  const title = document.getElementById("plannedTitle").value.trim();
  if (!title) {
    showToast("Title is required");
    return;
  }
  const pathVal = document.getElementById("plannedPath").value;
  const body = {
    title,
    media_type: document.getElementById("plannedType").value,
    language: document.getElementById("plannedLanguage").value,
    provider: document.getElementById("plannedProvider").value,
    auto_sync: document.getElementById("plannedAutoSync").checked,
  };
  if (pathVal) body.custom_path_id = parseInt(pathVal);

  try {
    const resp = await fetch("/api/planned", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    document.getElementById("plannedTitle").value = "";
    showToast("Added to planned");
    loadPlanned();
  } catch (e) {
    showToast("Failed to add: " + e.message);
  }
}

async function checkPlanned(id) {
  try {
    const resp = await fetch("/api/planned/" + id + "/check", { method: "POST" });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast(data.found ? "Found — queued for download" : "Not available yet");
    loadPlanned();
  } catch (e) {
    showToast("Check failed: " + e.message);
  }
}

async function deletePlanned(id) {
  if (!confirm("Remove this planned item?")) return;
  try {
    const resp = await fetch("/api/planned/" + id, { method: "DELETE" });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    loadPlanned();
  } catch (e) {
    showToast("Failed to remove: " + e.message);
  }
}

loadPlannedPaths();
loadPlanned();
setInterval(loadPlanned, 30000);
