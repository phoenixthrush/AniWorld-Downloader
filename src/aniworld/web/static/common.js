/* Small helpers shared by every page. */

function esc(value) {
  const node = document.createElement("div");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
}

// Search results arrive HTML-escaped from the sites, decode before re-escaping
function decodeEntities(value) {
  const node = document.createElement("textarea");
  node.innerHTML = value == null ? "" : String(value);
  return node.value;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.remove("show"), 4000);
}

/* options.timeoutMs aborts the request instead of letting it hang forever.
   A poller that never settles is worse than one that fails: the failure can be
   shown and retried, the hang just leaves the page on "Loading..." for good. */
async function apiFetch(url, options) {
  const { timeoutMs, ...init } = options || {};
  let timer = null;
  if (timeoutMs) {
    const controller = new AbortController();
    init.signal = controller.signal;
    timer = setTimeout(() => controller.abort(), timeoutMs);
  }

  let response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(t("common.timed_out", "The server did not answer in time"));
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }

  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }
  if (!response.ok) {
    const message = (data && data.error) || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data || {};
}

function apiSend(url, method, body) {
  return apiFetch(url, {
    method: method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/* ===== Modals ===== */

/* Themes read body[data-modal] to react to a dialog being up, which beats
   every theme writing its own :has(.overlay.open) and breaking when a class
   gets renamed. Kept in one place so it cannot drift from reality. */
function syncModalState() {
  document.body.dataset.modal = document.querySelector(".overlay.open")
    ? "open"
    : "closed";
}

function openModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.classList.add("open");
  syncModalState();
}

function closeModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.classList.remove("open");
  syncModalState();
}

document.addEventListener("click", (event) => {
  const overlay = event.target.closest("[data-close-on-backdrop]");
  if (overlay && event.target === overlay) {
    overlay.classList.remove("open");
    overlay.dispatchEvent(new CustomEvent("modal-closed"));
    syncModalState();
    return;
  }

  const closeBtn = event.target.closest("[data-close-modal]");
  if (closeBtn) {
    const parent = closeBtn.closest(".overlay");
    if (parent) {
      parent.classList.remove("open");
      parent.dispatchEvent(new CustomEvent("modal-closed"));
      syncModalState();
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".overlay.open").forEach((overlay) => {
    overlay.classList.remove("open");
    overlay.dispatchEvent(new CustomEvent("modal-closed"));
  });
  syncModalState();
});

/* ===== Mobile navigation ===== */
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("navToggle");
  const nav = document.getElementById("mainNav");
  if (!toggle || !nav) return;
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
});

/* ===== Update Checker ===== */
async function checkUpdate() {
  const badge = document.getElementById("appVersionBadge");
  if (!badge) return;
  
  const current = badge.dataset.currentVersion;
  if (!current) return;

  const cacheKey = "aniworld_latest_release";
  const cacheTimeKey = "aniworld_latest_release_time";
  
  const now = Date.now();
  let latest = localStorage.getItem(cacheKey);
  const lastCheck = localStorage.getItem(cacheTimeKey);

  if (!latest || !lastCheck || now - parseInt(lastCheck) > 24 * 60 * 60 * 1000) {
    try {
      const res = await fetch("https://api.github.com/repos/phoenixthrush/AniWorld-Downloader/releases/latest");
      if (res.ok) {
        const data = await res.json();
        latest = data.tag_name.replace(/^v\.?/, "");
        localStorage.setItem(cacheKey, latest);
      }
    } catch (e) {
      console.error("Failed to check for updates", e);
    } finally {
      // Always update the check time so we don't spam the API on failures or rate limits
      localStorage.setItem(cacheTimeKey, now.toString());
    }
  }

  if (latest && isNewerVersion(latest, current)) {
    badge.innerHTML = `v${current} <span class="update-available-badge">Update Available</span>`;
  }
}

function isNewerVersion(latest, current) {
  const l = latest.split('.').map(Number);
  const c = current.split('.').map(Number);
  for(let i=0; i<Math.max(l.length, c.length); i++) {
    const lPart = l[i] || 0;
    const cPart = c[i] || 0;
    if (lPart > cPart) return true;
    if (lPart < cPart) return false;
  }
  return false;
}

document.addEventListener("DOMContentLoaded", checkUpdate);
