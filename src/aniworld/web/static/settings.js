// Download path settings
const downloadPathInput = document.getElementById("downloadPath");
const langSeparationCb = document.getElementById("langSeparation");
const disableEnglishSubCb = document.getElementById("disableEnglishSub");
const enableHtvCb = document.getElementById("enableHtv");
const syncScheduleSelect = document.getElementById("syncSchedule");
const syncLanguageSelect = document.getElementById("syncLanguage");
const syncProviderSelect = document.getElementById("syncProvider");
const providerFallbackOrderEl = document.getElementById("providerFallbackOrder");
const publicIpValue = document.getElementById("publicIpValue");
const publicIpMeta = document.getElementById("publicIpMeta");
const refreshPublicIpBtn = document.getElementById("refreshPublicIpBtn");
let availableProviders = [];
let providerFallbackOrder = [];

async function loadSettings() {
  try {
    const resp = await fetch("/api/settings");
    const data = await resp.json();
    downloadPathInput.value = data.download_path || "";
    if (langSeparationCb)
      langSeparationCb.checked = data.lang_separation === "1";
    if (disableEnglishSubCb)
      disableEnglishSubCb.checked = data.disable_english_sub === "1";
    if (enableHtvCb) enableHtvCb.checked = data.enable_htv === "1";
    if (syncScheduleSelect && data.sync_schedule)
      syncScheduleSelect.value = data.sync_schedule;

    const isLangSep = data.lang_separation === "1";
    let currentSyncLang = data.sync_language;
    if (currentSyncLang === "All Languages" && !isLangSep) {
      currentSyncLang = "German Dub";
    }
    updateSyncLanguageDropdown(isLangSep, currentSyncLang);

    availableProviders = Array.isArray(data.available_providers)
      ? data.available_providers
      : [];
    updateSyncProviderDropdown(availableProviders, data.sync_provider);
    renderProviderFallbackOrder(data.provider_fallback_order || availableProviders);
  } catch (e) {
    showToast("Failed to load settings: " + e.message);
  }
}

async function saveLangSeparation() {
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        download_path: downloadPathInput.value.trim(),
        lang_separation: langSeparationCb.checked,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast(
      "Language separation " +
      (langSeparationCb.checked ? "enabled" : "disabled"),
    );

    let currentSyncLang = syncLanguageSelect ? syncLanguageSelect.value : null;
    if (!langSeparationCb.checked && currentSyncLang === "All Languages") {
      currentSyncLang = "German Dub";
      updateSyncLanguageDropdown(false, currentSyncLang);
      saveSyncDefaults();
    } else {
      updateSyncLanguageDropdown(langSeparationCb.checked, currentSyncLang);
    }
  } catch (e) {
    showToast("Failed to save setting: " + e.message);
  }
}

function updateSyncLanguageDropdown(isLangSep, currentValue) {
  if (!syncLanguageSelect) return;
  syncLanguageSelect.innerHTML = "";
  if (isLangSep) {
    const opt = document.createElement("option");
    opt.value = "All Languages";
    opt.textContent = "All Languages";
    syncLanguageSelect.appendChild(opt);
  }
  const langs = ["German Dub", "English Sub", "German Sub"];
  langs.forEach((l) => {
    const opt = document.createElement("option");
    opt.value = l;
    opt.textContent = l;
    syncLanguageSelect.appendChild(opt);
  });
  if (currentValue) syncLanguageSelect.value = currentValue;
}

function updateSyncProviderDropdown(providers, currentValue) {
  if (!syncProviderSelect) return;
  syncProviderSelect.innerHTML = "";
  providers.forEach((provider) => {
    const opt = document.createElement("option");
    opt.value = provider;
    opt.textContent = provider;
    syncProviderSelect.appendChild(opt);
  });
  if (currentValue && providers.includes(currentValue)) {
    syncProviderSelect.value = currentValue;
  } else if (providers.length) {
    syncProviderSelect.value = providers[0];
  }
}

function renderProviderFallbackOrder(order) {
  if (!providerFallbackOrderEl) return;

  const normalized = Array.isArray(order) ? order.filter(Boolean) : [];
  providerFallbackOrder = normalized.filter((provider) =>
    availableProviders.includes(provider),
  );

  availableProviders.forEach((provider) => {
    if (!providerFallbackOrder.includes(provider)) {
      providerFallbackOrder.push(provider);
    }
  });

  providerFallbackOrderEl.innerHTML = "";
  if (!providerFallbackOrder.length) {
    providerFallbackOrderEl.textContent = "No providers available";
    return;
  }

  providerFallbackOrder.forEach((provider, index) => {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.alignItems = "center";
    row.style.justifyContent = "space-between";
    row.style.gap = "12px";
    row.style.padding = "8px 0";
    row.style.borderBottom = "1px solid rgba(255,255,255,.06)";

    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${provider}`;

    const controls = document.createElement("div");
    controls.style.display = "flex";
    controls.style.gap = "8px";

    const up = document.createElement("button");
    up.type = "button";
    up.textContent = "Up";
    up.disabled = index === 0;
    up.onclick = () => moveProviderFallback(index, -1);

    const down = document.createElement("button");
    down.type = "button";
    down.textContent = "Down";
    down.disabled = index === providerFallbackOrder.length - 1;
    down.onclick = () => moveProviderFallback(index, 1);

    controls.appendChild(up);
    controls.appendChild(down);
    row.appendChild(label);
    row.appendChild(controls);
    providerFallbackOrderEl.appendChild(row);
  });
}

function moveProviderFallback(index, direction) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= providerFallbackOrder.length) return;
  const updated = providerFallbackOrder.slice();
  [updated[index], updated[nextIndex]] = [updated[nextIndex], updated[index]];
  providerFallbackOrder = updated;
  renderProviderFallbackOrder(providerFallbackOrder);
  saveProviderFallbackOrder();
}

async function saveDisableEnglishSub() {
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        disable_english_sub: disableEnglishSubCb.checked,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast(
      "English Sub downloads " +
      (disableEnglishSubCb.checked ? "disabled" : "enabled"),
    );
  } catch (e) {
    showToast("Failed to save setting: " + e.message);
  }
}

async function saveEnableHtv() {
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enable_htv: enableHtvCb.checked,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast("Hanime tab " + (enableHtvCb.checked ? "enabled" : "disabled"));
  } catch (e) {
    showToast("Failed to save setting: " + e.message);
  }
}

async function saveDownloadPath() {
  const download_path = downloadPathInput.value.trim();
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ download_path }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast("Download path saved");
  } catch (e) {
    showToast("Failed to save settings: " + e.message);
  }
}

loadSettings();
refreshPublicIp();

async function refreshPublicIp() {
  if (!publicIpValue || !publicIpMeta || !refreshPublicIpBtn) return;
  refreshPublicIpBtn.disabled = true;
  publicIpValue.textContent = "Loading...";
  publicIpValue.classList.remove("is-error");
  publicIpMeta.textContent = "Checking current outbound IP address...";
  try {
    const resp = await fetch("/api/settings/public-ip", { cache: "no-store" });
    const data = await resp.json();
    if (!resp.ok || !data.ok || !data.ip) {
      throw new Error(data.error || "Failed to fetch public IP");
    }
    publicIpValue.textContent = data.ip;
    publicIpMeta.textContent =
      "Updated at " + new Date().toLocaleTimeString([], { timeStyle: "medium" });
  } catch (e) {
    publicIpValue.textContent = "Unavailable";
    publicIpValue.classList.add("is-error");
    publicIpMeta.textContent = e.message;
    showToast("Failed to fetch public IP: " + e.message);
  } finally {
    refreshPublicIpBtn.disabled = false;
  }
}

async function saveSyncSchedule() {
  if (!syncScheduleSelect) return;
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sync_schedule: syncScheduleSelect.value }),
    });
    const data = await resp.json();
    if (data.ok) showToast("Auto-Sync schedule saved");
    else showToast("Failed to save schedule");
  } catch (e) {
    showToast("Failed to save schedule: " + e.message);
  }
}

async function saveSyncDefaults() {
  const body = {};
  if (syncLanguageSelect) body.sync_language = syncLanguageSelect.value;
  if (syncProviderSelect) body.sync_provider = syncProviderSelect.value;
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) showToast("Auto-Sync defaults saved");
    else showToast("Failed to save defaults");
  } catch (e) {
    showToast("Failed to save defaults: " + e.message);
  }
}

async function saveProviderFallbackOrder() {
  try {
    const resp = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_fallback_order: providerFallbackOrder }),
    });
    const data = await resp.json();
    if (data.ok) showToast("Provider fallback order saved");
    else showToast(data.error || "Failed to save provider fallback order");
  } catch (e) {
    showToast("Failed to save provider fallback order: " + e.message);
  }
}

// Custom paths management
const customPathsBody = document.getElementById("customPathsBody");
const customPathsTable = document.getElementById("customPathsTable");

if (customPathsBody) {
  loadCustomPaths();
}

async function loadCustomPaths() {
  if (!customPathsBody) return;
  try {
    const resp = await fetch("/api/custom-paths");
    const data = await resp.json();
    renderCustomPaths(data.paths || []);
  } catch (e) {
    showToast("Failed to load custom paths: " + e.message);
  }
}

function renderCustomPaths(paths) {
  customPathsBody.innerHTML = "";
  if (!paths.length) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td colspan="3" style="color:#6b7280;text-align:center">No custom paths</td>';
    customPathsBody.appendChild(tr);
    return;
  }
  paths.forEach(function (p) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" +
      esc(p.name) +
      "</td>" +
      "<td style=\"font-family:'SF Mono','Fira Code',monospace;font-size:.82rem\">" +
      esc(p.path) +
      "</td>" +
      '<td><button class="btn-del" onclick="deleteCustomPath(' +
      p.id +
      ')">Delete</button></td>';
    customPathsBody.appendChild(tr);
  });
}

async function addCustomPath() {
  const name = document.getElementById("newPathName").value.trim();
  const path = document.getElementById("newPathValue").value.trim();
  if (!name || !path) {
    showToast("Name and path are required");
    return;
  }
  try {
    const resp = await fetch("/api/custom-paths", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, path: path }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    document.getElementById("newPathName").value = "";
    document.getElementById("newPathValue").value = "";
    showToast("Custom path added");
    loadCustomPaths();
  } catch (e) {
    showToast("Failed to add custom path: " + e.message);
  }
}

async function deleteCustomPath(id) {
  if (!confirm("Delete this custom path?")) return;
  try {
    const resp = await fetch("/api/custom-paths/" + id, { method: "DELETE" });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast("Custom path deleted");
    loadCustomPaths();
  } catch (e) {
    showToast("Failed to delete custom path: " + e.message);
  }
}

// User management (only runs if the user table exists)
const userTableBody = document.getElementById("userTableBody");

if (userTableBody) {
  loadUsers();
}

async function loadUsers() {
  if (!userTableBody) return;
  try {
    const resp = await fetch("/admin/api/users");
    const data = await resp.json();
    renderUsers(data.users || []);
  } catch (e) {
    showToast("Failed to load users: " + e.message);
  }
}

function renderUsers(users) {
  const adminCount = users.filter((u) => u.role === "admin").length;
  userTableBody.innerHTML = "";
  users.forEach((u) => {
    const isLastAdmin = u.role === "admin" && adminCount <= 1;
    const tr = document.createElement("tr");
    const authMethod = u.auth_method || "local";
    const authBadge =
      authMethod === "oidc"
        ? '<span class="auth-badge auth-sso">SSO</span>'
        : '<span class="auth-badge auth-local">Local</span>';
    tr.innerHTML =
      `<td>${u.id}</td>` +
      `<td>${esc(u.username)}</td>` +
      `<td>
        <select onchange="changeRole(${u.id}, this.value)" ${isLastAdmin ? "disabled" : ""}>
          <option value="user" ${u.role === "user" ? "selected" : ""}>User</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>Admin</option>
        </select>
      </td>` +
      `<td>${authBadge}</td>` +
      `<td>${esc(u.created_at)}</td>` +
      `<td>${isLastAdmin
        ? '<span style="color:#555">protected</span>'
        : `<button class="btn-del" onclick="deleteUser(${u.id})">Delete</button>`
      }</td>`;
    userTableBody.appendChild(tr);
  });
}

async function addUser() {
  const username = document.getElementById("newUsername").value.trim();
  const password = document.getElementById("newPassword").value;
  const role = document.getElementById("newRole").value;

  if (!username || !password) {
    showToast("Username and password required");
    return;
  }

  try {
    const resp = await fetch("/admin/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    document.getElementById("newUsername").value = "";
    document.getElementById("newPassword").value = "";
    showToast("User created");
    loadUsers();
  } catch (e) {
    showToast("Failed to create user: " + e.message);
  }
}

async function deleteUser(id) {
  if (!confirm("Delete this user?")) return;
  try {
    const resp = await fetch(`/admin/api/users/${id}`, { method: "DELETE" });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    showToast("User deleted");
    loadUsers();
  } catch (e) {
    showToast("Failed to delete user: " + e.message);
  }
}

async function changeRole(id, newRole) {
  try {
    const resp = await fetch(`/admin/api/users/${id}/role`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: newRole }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      loadUsers();
      return;
    }
    showToast("Role updated");
    loadUsers();
  } catch (e) {
    showToast("Failed to update role: " + e.message);
  }
}

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.display = "block";
  setTimeout(() => (t.style.display = "none"), 4000);
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}
