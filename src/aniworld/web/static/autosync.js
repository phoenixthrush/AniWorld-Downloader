// Auto-Sync page logic

const autosyncList = document.getElementById("autosyncList");
const autosyncEmpty = document.getElementById("autosyncEmpty");

// Schedule map for computing next check time
const SCHEDULE_INTERVALS = {
  "1min": 60,
  "30min": 1800,
  "1h": 3600,
  "2h": 7200,
  "4h": 14400,
  "8h": 28800,
  "12h": 43200,
  "16h": 57600,
  "24h": 86400,
};
const SCHEDULE_LABELS = {
  "1min": "1 min",
  "30min": "30 min",
  "1h": "1h",
  "2h": "2h",
  "4h": "4h",
  "8h": "8h",
  "12h": "12h",
  "16h": "16h",
  "24h": "24h",
};

let currentSyncSchedule = "0";
let customPathsCache = [];
let langSepEnabled = false;

async function loadSyncSchedule() {
  try {
    const resp = await fetch("/api/settings");
    const data = await resp.json();
    currentSyncSchedule = data.sync_schedule || "0";
    langSepEnabled = data.lang_separation === "1";
  } catch (e) {
    /* ignore */
  }
}

async function loadCustomPathsForEdit() {
  try {
    const resp = await fetch("/api/custom-paths");
    const data = await resp.json();
    customPathsCache = data.paths || [];
  } catch (e) {
    customPathsCache = [];
  }
}

async function loadAutosyncJobs() {
  try {
    const res = await fetch("/api/autosync");
    const data = await res.json();
    renderJobs(data.jobs || []);
  } catch (e) {
    autosyncList.innerHTML =
      '<div class="queue-empty">Failed to load sync jobs.</div>';
  }
}

function computeNextCheck(lastCheck) {
  if (!lastCheck || currentSyncSchedule === "0") return "—";
  const interval = SCHEDULE_INTERVALS[currentSyncSchedule];
  if (!interval) return "—";
  const lastMs = new Date(lastCheck + "Z").getTime();
  const nextMs = lastMs + interval * 1000;
  const now = Date.now();
  if (nextMs <= now) return "Soon";
  return formatDate(
    new Date(nextMs)
      .toISOString()
      .replace("Z", "")
      .replace("T", " ")
      .slice(0, 19),
  );
}

function renderJobs(jobs) {
  if (!jobs.length) {
    autosyncList.innerHTML =
      '<div class="queue-empty">No sync jobs yet. Add a series via the search page.</div>';
    return;
  }
  let html =
    '<table class="user-table" style="table-layout:auto"><thead><tr>' +
    "<th>Title</th><th>Last Check</th><th>Re-Check at</th><th>Last New Found</th><th>Episodes</th>" +
    "<th>Download Path</th><th>Status</th><th>Added By</th><th>Actions</th>" +
    "</tr></thead><tbody>";
  for (const job of jobs) {
    const statusClass = job.enabled
      ? "queue-status-completed"
      : "queue-status-queued";
    const statusLabel = job.enabled ? "Enabled" : "Disabled";
    const lastCheck = job.last_check ? formatDate(job.last_check) : "—";
    const nextCheck = job.enabled ? computeNextCheck(job.last_check) : "—";
    const lastNew = job.last_new_found ? formatDate(job.last_new_found) : "—";
    let dlPath = "Default";
    if (job.custom_path_id) {
      const cp = customPathsCache.find((p) => p.id === job.custom_path_id);
      dlPath = cp ? cp.name : "Custom #" + job.custom_path_id;
    }
    const addedBy = job.added_by ? esc(job.added_by) : "—";
    html +=
      "<tr>" +
      '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;color:#e2e4e9" title="' +
      esc(job.series_url) +
      '">' +
      esc(job.title) +
      "</td>" +
      "<td>" +
      lastCheck +
      "</td>" +
      "<td>" +
      nextCheck +
      "</td>" +
      "<td>" +
      lastNew +
      "</td>" +
      "<td>" +
      job.episodes_found +
      "</td>" +
      "<td>" +
      dlPath +
      "</td>" +
      '<td><span class="queue-status ' +
      statusClass +
      '">' +
      statusLabel +
      "</span></td>" +
      "<td>" +
      addedBy +
      "</td>" +
      '<td><div class="queue-item-right">' +
      '<button class="queue-move" onclick="openEditModal(' +
      job.id +
      ')" title="Edit" style="font-size:.85rem">✎</button>' +
      '<button class="queue-move" onclick="syncNow(' +
      job.id +
      ')" title="Sync Now" style="font-size:.85rem;color:#6ea8fe">⟳</button>' +
      '<button class="queue-remove" onclick="removeJob(' +
      job.id +
      ')" title="Remove" style="font-size:.85rem">✕</button>' +
      "</div></td>" +
      "</tr>";
  }
  html += "</tbody></table>";
  autosyncList.innerHTML = html;
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr + "Z");
  if (isNaN(d.getTime())) {
    // Try without adding Z (already formatted)
    const d2 = new Date(isoStr);
    if (isNaN(d2.getTime())) return "—";
    const pad = (n) => String(n).padStart(2, "0");
    return (
      pad(d2.getDate()) +
      "." +
      pad(d2.getMonth() + 1) +
      "." +
      d2.getFullYear() +
      " " +
      pad(d2.getHours()) +
      ":" +
      pad(d2.getMinutes())
    );
  }
  const pad = (n) => String(n).padStart(2, "0");
  return (
    pad(d.getDate()) +
    "." +
    pad(d.getMonth() + 1) +
    "." +
    d.getFullYear() +
    " " +
    pad(d.getHours()) +
    ":" +
    pad(d.getMinutes())
  );
}

async function syncNow(id) {
  try {
    const res = await fetch("/api/autosync/" + id + "/sync", {
      method: "POST",
    });
    const data = await res.json();
    if (data.ok) {
      showToast("Sync started");
      setTimeout(loadAutosyncJobs, 2000);
    } else {
      showToast(data.error || "Failed to start sync");
    }
  } catch (e) {
    showToast("Failed to start sync");
  }
}

async function removeJob(id) {
  if (!confirm("Remove this sync job?")) return;
  try {
    const res = await fetch("/api/autosync/" + id, { method: "DELETE" });
    const data = await res.json();
    if (data.ok) {
      showToast("Sync job removed");
      loadAutosyncJobs();
    } else {
      showToast(data.error || "Failed to remove");
    }
  } catch (e) {
    showToast("Failed to remove sync job");
  }
}

// Edit modal
let currentJobs = [];

async function openEditModal(id) {
  try {
    const res = await fetch("/api/autosync");
    const data = await res.json();
    currentJobs = data.jobs || [];
    const job = currentJobs.find((j) => j.id === id);
    if (!job) {
      showToast("Job not found");
      return;
    }

    document.getElementById("editJobId").value = id;
    document.getElementById("editJobTitle").textContent =
      job.title || "Unknown";

    // Rebuild language dropdown based on lang separation setting
    const langSelect = document.getElementById("editLanguage");
    langSelect.innerHTML = "";
    if (langSepEnabled) {
      const opt = document.createElement("option");
      opt.value = "All Languages";
      opt.textContent = "All Languages";
      langSelect.appendChild(opt);
    }
    ["German Dub", "English Sub", "German Sub"].forEach((l) => {
      const opt = document.createElement("option");
      opt.value = l;
      opt.textContent = l;
      langSelect.appendChild(opt);
    });
    langSelect.value = job.language || "German Dub";

    document.getElementById("editProvider").value = job.provider || "VOE";
    document.getElementById("editEnabled").value = job.enabled ? "1" : "0";

    // Populate path dropdown
    const pathSelect = document.getElementById("editPath");
    while (pathSelect.options.length > 1) pathSelect.remove(1);
    await loadCustomPathsForEdit();
    customPathsCache.forEach(function (p) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name + " (" + p.path + ")";
      pathSelect.appendChild(opt);
    });
    pathSelect.value = job.custom_path_id ? String(job.custom_path_id) : "";

    document.getElementById("editOverlay").style.display = "block";
  } catch (e) {
    showToast("Failed to load job");
  }
}

function closeEditModal() {
  document.getElementById("editOverlay").style.display = "none";
}

async function saveEdit() {
  const id = document.getElementById("editJobId").value;
  const pathVal = document.getElementById("editPath").value;
  const body = {
    language: document.getElementById("editLanguage").value,
    provider: document.getElementById("editProvider").value,
    enabled: parseInt(document.getElementById("editEnabled").value),
    custom_path_id: pathVal ? parseInt(pathVal) : null,
  };
  try {
    const res = await fetch("/api/autosync/" + id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) {
      showToast("Job updated");
      closeEditModal();
      loadAutosyncJobs();
    } else {
      showToast(data.error || "Failed to update");
    }
  } catch (e) {
    showToast("Failed to update job");
  }
}

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(t._timer);
  t._timer = setTimeout(() => {
    t.style.display = "none";
  }, 3000);
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

// Init
Promise.all([loadSyncSchedule(), loadCustomPathsForEdit()]).then(
  loadAutosyncJobs,
);
setInterval(loadAutosyncJobs, 30000);
