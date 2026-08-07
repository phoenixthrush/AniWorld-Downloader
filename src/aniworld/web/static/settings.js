/* Settings page. */

(function () {
  const el = (id) => document.getElementById(id);

  const SITE_OPTIONS = [
    ["aniworld", "AniWorld"],
    ["sto", "SerienStream"],
    ["burningseries", "BurningSeries"],
    ["megakino", "MegaKino"],
    ["cineby", "Cineby"],
    ["kinox", "Kinox"],
    ["filmpalast", "FilmPalast"],
    ["htv", "Hanime"],
    ["mangafire", "MangaFire"]
  ];

  const SECRET_PLACEHOLDER = "••••••••";

  let providerOrder = [];

  async function save(payload, message) {
    try {
      await apiSend("/api/settings", "PUT", payload);
      showToast(message || t("settings.saved", "Saved"));
      return true;
    } catch (error) {
      showToast(`${t("settings.save_failed", "Could not save")}: ${error.message}`);
      return false;
    }
  }

  /* ===== Load ===== */
  async function load() {
    let settings;
    try {
      settings = await apiFetch("/api/settings");
    } catch (error) {
      showToast(error.message);
      return;
    }

    el("downloadPath").value = settings.download_path || "";
    el("uiLanguage").value = settings.ui_language;
    el("outputFormat").value = settings.output_format;

    document.querySelectorAll("[data-setting]").forEach((box) => {
      box.checked = Boolean(settings[box.dataset.setting]);
    });

    providerOrder = settings.provider_fallback_order || [];
    savedOrder = providerOrder.slice();
    renderProviderOrder();
    applyDiscord(settings.discord || {});
  }

  /* ===== Simple toggles and selects ===== */
  document.querySelectorAll("[data-setting]").forEach((box) => {
    box.addEventListener("change", async () => {
      const ok = await save({ [box.dataset.setting]: box.checked });
      if (!ok) {
        box.checked = !box.checked;
        return;
      }
      // Enabling or disabling a tab changes the navbar and home page
      if (box.dataset.reload) setTimeout(() => window.location.reload(), 400);
    });
  });

  el("saveDownloadPathBtn").addEventListener("click", () => {
    save({ download_path: el("downloadPath").value.trim() });
  });

  el("uiLanguage").addEventListener("change", async () => {
    if (await save({ ui_language: el("uiLanguage").value })) {
      setTimeout(() => window.location.reload(), 400);
    }
  });

  el("outputFormat").addEventListener("change", () => {
    save({ output_format: el("outputFormat").value });
  });

  /* ===== Provider fallback order =====
     Rows are dragged with pointer events so it works with a mouse and on
     touch alike. Arrow keys do the same thing for keyboard users. */
  const providerList = el("providerOrder");

  function renderProviderOrder() {
    providerList.innerHTML = providerOrder
      .map(
        (provider, index) => `
        <div class="provider-row" tabindex="0" role="listitem"
          aria-label="${esc(provider)}">
          <span class="drag-grip" aria-hidden="true"></span>
          <span class="provider-rank">${index + 1}</span>
          <span class="provider-name">${esc(provider)}</span>
        </div>`
      )
      .join("");
  }

  function refreshRanks() {
    Array.from(providerList.children).forEach((row, index) => {
      row.querySelector(".provider-rank").textContent = index + 1;
    });
  }

  // Moves the row in the DOM instead of re-rendering, so the node being
  // dragged survives and keeps its pointer capture.
  function moveRow(from, to) {
    if (from === to) return;
    const rows = Array.from(providerList.children);
    const reference = from < to ? rows[to].nextSibling : rows[to];
    providerList.insertBefore(rows[from], reference);
    providerOrder.splice(to, 0, providerOrder.splice(from, 1)[0]);
    refreshRanks();
  }

  let savedOrder = [];
  let drag = null;

  async function commitOrder() {
    if (providerOrder.join() === savedOrder.join()) return;
    if (await save({ provider_fallback_order: providerOrder })) {
      savedOrder = providerOrder.slice();
    } else {
      providerOrder = savedOrder.slice();
      renderProviderOrder();
    }
  }

  providerList.addEventListener("pointerdown", (event) => {
    const row = event.target.closest(".provider-row");
    if (!row || event.button !== 0 || drag) return;

    const rows = Array.from(providerList.children);
    const rect = row.getBoundingClientRect();
    // rows are uniform, so one row plus the flex gap is a full step
    const gap = parseFloat(getComputedStyle(providerList).rowGap) || 0;
    drag = {
      row,
      pointerId: event.pointerId,
      startY: event.clientY,
      startIndex: rows.indexOf(row),
      step: rect.height + gap
    };
    drag.index = drag.startIndex;
    row.setPointerCapture(event.pointerId);
    row.classList.add("dragging");
    event.preventDefault();
  });

  providerList.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;

    const delta = event.clientY - drag.startY;
    let target = drag.startIndex + Math.round(delta / drag.step);
    target = Math.max(0, Math.min(providerOrder.length - 1, target));
    if (target !== drag.index) {
      moveRow(drag.index, target);
      drag.index = target;
    }
    // the row has already shifted by whole slots, only show what is left over
    const settled = (drag.index - drag.startIndex) * drag.step;
    drag.row.style.transform = `translateY(${delta - settled}px)`;
  });

  function endDrag() {
    if (!drag) return;
    drag.row.style.transform = "";
    drag.row.classList.remove("dragging");
    const moved = drag.index !== drag.startIndex;
    drag = null;
    if (moved) commitOrder();
  }

  providerList.addEventListener("pointerup", endDrag);
  providerList.addEventListener("pointercancel", endDrag);

  providerList.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    const row = event.target.closest(".provider-row");
    if (!row) return;

    const index = Array.from(providerList.children).indexOf(row);
    const target = index + (event.key === "ArrowUp" ? -1 : 1);
    if (target < 0 || target >= providerOrder.length) return;

    event.preventDefault();
    moveRow(index, target);
    row.focus();
    commitOrder();
  });

  /* ===== Custom paths ===== */
  function renderCustomPaths(paths) {
    const body = el("customPathsBody");
    if (!paths.length) {
      body.innerHTML = `<tr class="empty-row"><td colspan="4">${t("library.empty", "Nothing here yet.")}</td></tr>`;
      return;
    }

    body.innerHTML = paths
      .map((path) => {
        const enabled = (path.default_sites || "").split(",");
        const toggles = SITE_OPTIONS.map(
          ([key, label]) => `
            <label class="site-toggle">
              <input type="checkbox" data-path="${path.id}" data-site="${key}"
                ${enabled.includes(key) ? "checked" : ""} />
              <span>${label}</span>
            </label>`
        ).join("");

        return `
          <tr>
            <td>${esc(path.name)}</td>
            <td><code>${esc(path.path)}</code></td>
            <td><div class="site-toggles">${toggles}</div></td>
            <td>
              <button class="btn btn-danger" data-delete-path="${path.id}"
                data-name="${esc(path.name)}">${t("common.remove", "Remove")}</button>
            </td>
          </tr>`;
      })
      .join("");
  }

  async function loadCustomPaths() {
    try {
      const data = await apiFetch("/api/custom-paths");
      renderCustomPaths(data.paths || []);
    } catch (error) {
      showToast(error.message);
    }
  }

  el("addPathBtn").addEventListener("click", async () => {
    const name = el("newPathName").value.trim();
    const path = el("newPathValue").value.trim();
    if (!name || !path) {
      showToast(t("settings.path_required", "Name and path are required"));
      return;
    }
    try {
      await apiSend("/api/custom-paths", "POST", { name, path });
      el("newPathName").value = "";
      el("newPathValue").value = "";
      loadCustomPaths();
    } catch (error) {
      showToast(error.message);
    }
  });

  el("customPathsBody").addEventListener("change", async (event) => {
    const box = event.target.closest("[data-site]");
    if (!box) return;

    const pathId = box.dataset.path;
    const sites = Array.from(
      el("customPathsBody").querySelectorAll(`[data-path="${pathId}"]:checked`)
    ).map((checked) => checked.dataset.site);

    try {
      await apiSend(`/api/custom-paths/${pathId}`, "PUT", { default_sites: sites });
    } catch (error) {
      showToast(error.message);
      box.checked = !box.checked;
    }
  });

  el("customPathsBody").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-path]");
    if (!button) return;

    const message = t("settings.confirm_delete_path", 'Remove path "{name}"?', {
      name: button.dataset.name
    });
    if (!window.confirm(message)) return;

    try {
      await apiSend(`/api/custom-paths/${button.dataset.deletePath}`, "DELETE");
      loadCustomPaths();
    } catch (error) {
      showToast(error.message);
    }
  });

  /* ===== Discord ===== */
  function applyDiscord(discord) {
    el("discordEnabled").checked = Boolean(discord.enabled);
    // Never send the real token to the browser, show a placeholder instead
    el("discordToken").value = discord.token_set ? SECRET_PLACEHOLDER : "";
    el("discordOwner").value = discord.owner_id || "";
    el("discordMode").value = discord.mode || "standard";
    el("discordLanguage").value = discord.language || "en";
    el("discordRole").value = discord.request_role_id || "";
    el("discordGuild").value = discord.guild_id || "";
    el("discordAnnounce").value = discord.announce_channel_id || "";
  }

  el("saveDiscordBtn").addEventListener("click", async () => {
    const payload = {
      discord: {
        enabled: el("discordEnabled").checked,
        token: el("discordToken").value,
        owner_id: el("discordOwner").value.trim(),
        mode: el("discordMode").value,
        language: el("discordLanguage").value,
        request_role_id: el("discordRole").value.trim(),
        guild_id: el("discordGuild").value.trim(),
        announce_channel_id: el("discordAnnounce").value.trim()
      }
    };
    if (await save(payload)) setTimeout(loadDiscordStatus, 1500);
  });

  async function loadDiscordStatus() {
    const status = el("discordStatus");
    try {
      const data = await apiFetch("/api/discord/status");
      if (data.available === false) {
        status.textContent = t("settings.discord.unavailable", "discord.py is not installed");
        status.className = "status-pill status-cancelled";
        return;
      }
      if (data.running) {
        status.textContent = t("settings.discord.running", "Running as {user}", {
          user: data.user || "bot"
        });
        status.className = "status-pill status-completed";
        return;
      }
      status.textContent = data.error || t("settings.discord.stopped", "Stopped");
      status.className = data.error ? "status-pill status-failed" : "status-pill status-queued";
    } catch (error) {
      status.textContent = "";
    }
  }

  /* ===== Users ===== */
  function renderUsers(users) {
    const body = el("userTableBody");
    if (!body) return;

    body.innerHTML = users
      .map(
        (user) => `
        <tr>
          <td>${user.id}</td>
          <td>${esc(user.username)}</td>
          <td>
            <select data-role-for="${user.id}">
              <option value="user"${user.role === "user" ? " selected" : ""}>User</option>
              <option value="admin"${user.role === "admin" ? " selected" : ""}>Admin</option>
            </select>
          </td>
          <td>${esc(user.auth_method)}</td>
          <td>
            <button class="btn btn-danger" data-delete-user="${user.id}"
              data-name="${esc(user.username)}">${t("common.delete", "Delete")}</button>
          </td>
        </tr>`
      )
      .join("");
  }

  async function loadUsers() {
    try {
      const data = await apiFetch("/admin/api/users");
      renderUsers(data.users || []);
    } catch (error) {
      showToast(error.message);
    }
  }

  if (window.AUTH_ENABLED) {
    const addUserBtn = el("addUserBtn");
    if (addUserBtn) {
      addUserBtn.addEventListener("click", async () => {
        try {
          await apiSend("/admin/api/users", "POST", {
            username: el("newUsername").value.trim(),
            password: el("newPassword").value,
            role: el("newRole").value
          });
          el("newUsername").value = "";
          el("newPassword").value = "";
          loadUsers();
        } catch (error) {
          showToast(error.message);
        }
      });
    }

    const userBody = el("userTableBody");
    userBody.addEventListener("change", async (event) => {
      const select = event.target.closest("[data-role-for]");
      if (!select) return;
      try {
        await apiSend(`/admin/api/users/${select.dataset.roleFor}/role`, "PUT", {
          role: select.value
        });
      } catch (error) {
        showToast(error.message);
        loadUsers();
      }
    });

    userBody.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-delete-user]");
      if (!button) return;

      const message = t("settings.confirm_delete_user", 'Delete user "{name}"?', {
        name: button.dataset.name
      });
      if (!window.confirm(message)) return;

      try {
        await apiSend(`/admin/api/users/${button.dataset.deleteUser}`, "DELETE");
        loadUsers();
      } catch (error) {
        showToast(error.message);
      }
    });

    loadUsers();
  }

  /* ===== API keys ===== */
  const SCOPE_LABELS = {
    read: () => t("settings.scope_read", "Read only"),
    write: () => t("settings.scope_write", "Read and download"),
    admin: () => t("settings.scope_admin", "Full access")
  };

  function formatKeyDate(value) {
    if (!value) return "-";
    // sqlite hands back "YYYY-MM-DD HH:MM:SS" in UTC
    const date = new Date(value.replace(" ", "T") + "Z");
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  }

  function renderApiKeys(keys) {
    const body = el("apiKeysBody");
    if (!keys.length) {
      body.innerHTML = `<tr class="empty-row"><td colspan="6">${t("settings.no_keys", "No API keys yet.")}</td></tr>`;
      return;
    }

    body.innerHTML = keys
      .map((key) => {
        const scope = (SCOPE_LABELS[key.scope] || (() => key.scope))();
        const expires = key.expired
          ? `<span class="key-expired">${t("settings.api_key_expired", "Expired")}</span>`
          : esc(key.expires_at ? formatKeyDate(key.expires_at) : t("settings.expiry_never", "Never expires"));
        return `
          <tr>
            <td>${esc(key.name)}</td>
            <td><code>${esc(key.prefix)}...</code></td>
            <td>${esc(scope)}</td>
            <td>${esc(formatKeyDate(key.last_used_at))}</td>
            <td>${expires}</td>
            <td>
              <button class="btn btn-danger" data-delete-key="${key.id}"
                data-name="${esc(key.name)}">${t("common.delete", "Delete")}</button>
            </td>
          </tr>`;
      })
      .join("");
  }

  async function loadApiKeys() {
    try {
      const data = await apiFetch("/api/keys");
      renderApiKeys(data.keys || []);
    } catch (error) {
      showToast(error.message);
    }
  }

  el("addKeyBtn").addEventListener("click", async () => {
    const name = el("newKeyName").value.trim();
    if (!name) {
      showToast(t("settings.key_name_required", "Give the key a name"));
      return;
    }

    const button = el("addKeyBtn");
    button.disabled = true;
    try {
      const data = await apiSend("/api/keys", "POST", {
        name,
        scope: el("newKeyScope").value,
        expires_days: el("newKeyExpiry").value
      });
      el("newKeyName").value = "";
      el("newKeyValue").textContent = data.key;
      el("newKeyResult").hidden = false;
      loadApiKeys();
    } catch (error) {
      showToast(error.message);
    } finally {
      button.disabled = false;
    }
  });

  el("copyKeyBtn").addEventListener("click", async () => {
    const value = el("newKeyValue").textContent;
    try {
      await navigator.clipboard.writeText(value);
      showToast(t("settings.copied", "Copied"));
    } catch (error) {
      // Clipboard needs https or localhost, select the text so it can be copied by hand
      const range = document.createRange();
      range.selectNodeContents(el("newKeyValue"));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  });

  el("apiKeysBody").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-key]");
    if (!button) return;

    const message = t("settings.confirm_delete_key", 'Delete API key "{name}"? Anything using it stops working.', {
      name: button.dataset.name
    });
    if (!window.confirm(message)) return;

    try {
      await apiSend(`/api/keys/${button.dataset.deleteKey}`, "DELETE");
      loadApiKeys();
    } catch (error) {
      showToast(error.message);
    }
  });

  /* ===== IP check (never runs on its own) ===== */
  el("revealIpBtn").addEventListener("click", async () => {
    const value = el("publicIpValue");
    const meta = el("publicIpMeta");
    const button = el("revealIpBtn");

    button.disabled = true;
    value.textContent = t("settings.ip_loading", "Looking up...");
    meta.textContent = "";
    try {
      const data = await apiFetch("/api/settings/public-ip");
      value.textContent = data.ip;
      meta.textContent = t("settings.ip_source", "Source: {source}", {
        source: data.source
      });
      button.textContent = t("common.refresh", "Refresh");
    } catch (error) {
      value.textContent = t("settings.ip_failed", "Could not resolve IP");
      meta.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  load();
  loadCustomPaths();
  loadDiscordStatus();
  loadApiKeys();
})();
