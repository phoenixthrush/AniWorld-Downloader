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
    applyAutosyncSchedule(settings);
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

  /* ===== Auto-Sync schedule =====
     The day chips and the times field build a phrase ("every mon,fri at
     22:00") and the server hands cron back. Cron the chips cannot show, a
     step or a day of the month, leaves them empty and is edited as text. */
  const WEEKDAYS = [
    [1, "settings.day_mon", "Mon"],
    [2, "settings.day_tue", "Tue"],
    [3, "settings.day_wed", "Wed"],
    [4, "settings.day_thu", "Thu"],
    [5, "settings.day_fri", "Fri"],
    [6, "settings.day_sat", "Sat"],
    [0, "settings.day_sun", "Sun"]
  ];
  const CRON_DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

  const dayPicker = el("autosyncDays");
  dayPicker.innerHTML = WEEKDAYS.map(
    ([number, key, fallback]) => `
      <label class="day-chip">
        <input type="checkbox" value="${number}" />
        <span>${esc(t(key, fallback))}</span>
      </label>`
  ).join("");

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  /* A cron field as plain numbers, or null for anything with a * / - in it. */
  function numberList(field, max) {
    const values = [];
    for (const part of field.split(",")) {
      if (!/^\d+$/.test(part)) return null;
      const value = Number(part);
      if (value > max) return null;
      values.push(value);
    }
    return values;
  }

  /* "0 8,22 * * 1,5" -> {days: [1, 5], times: ["08:00", "22:00"]} */
  function readCron(expression) {
    const lines = String(expression || "")
      .split(";")
      .map((line) => line.trim())
      .filter(Boolean);

    const times = new Set();
    let days = null;

    for (const line of lines) {
      const fields = line.split(/\s+/);
      if (fields.length !== 5) return null;
      const [minute, hour, monthDay, month, weekday] = fields;
      if (monthDay !== "*" || month !== "*") return null;

      const minutes = numberList(minute, 59);
      const hours = numberList(hour, 23);
      const picked = weekday === "*" ? [] : numberList(weekday, 6);
      if (!minutes || !hours || !picked) return null;

      // Lines that disagree on the days are not one row of chips
      const key = picked.join(",");
      if (days === null) days = key;
      else if (days !== key) return null;

      hours.forEach((h) => minutes.forEach((m) => times.add(`${pad(h)}:${pad(m)}`)));
    }

    if (!times.size) return null;
    return {
      days: days ? days.split(",").map(Number) : [],
      times: Array.from(times).sort()
    };
  }

  /* The reading the server last sent, shown whenever nothing is being typed */
  let savedSummary = "";

  function showSummary(text, invalid) {
    const summary = el("autosyncScheduleSummary");
    summary.textContent = text;
    summary.classList.toggle("invalid", Boolean(invalid));
  }

  function applyAutosyncSchedule(settings) {
    const mode = settings.autosync_mode === "cron" ? "cron" : "interval";
    el("autosyncMode").value = mode;
    el("autosyncIntervalRow").hidden = mode !== "interval";
    el("autosyncCronRow").hidden = mode === "interval";

    const seconds = Number(settings.autosync_interval_seconds) || 24 * 3600;
    const hourly = seconds % 3600 === 0;
    el("autosyncIntervalValue").value = hourly
      ? seconds / 3600
      : Math.round(seconds / 60);
    el("autosyncIntervalUnit").value = hourly ? "h" : "m";

    const expression = settings.autosync_cron || "";
    el("autosyncCron").value = expression;

    const parsed = readCron(expression);
    dayPicker.querySelectorAll("input").forEach((box) => {
      box.checked = Boolean(parsed && parsed.days.includes(Number(box.value)));
    });
    el("autosyncTimes").value = parsed ? parsed.times.join(", ") : "";

    // Nothing the chips can show, so point at the text field instead
    const custom = Boolean(expression) && !parsed;
    dayPicker.hidden = custom;
    el("autosyncTimes").closest(".inline-form").hidden = custom;
    if (custom) el("autosyncCronDetails").open = true;

    savedSummary = settings.autosync_schedule
      ? t("settings.autosync_runs", "Auto-Sync runs: {schedule}", {
          schedule: settings.autosync_schedule
        })
      : "";
    showSummary(savedSummary, false);
  }

  /* ===== Reading back what is on screen =====
     The parser lives on the server, so the fields ask it what they would mean
     while they are edited. Nothing here saves: that is the Save button, the
     same as the download path. Only the newest answer is shown, a slow reply
     to an older keystroke would otherwise land on top of a newer one. */
  let previewTimer = null;
  let previewToken = 0;

  /* Exactly what Save would send, so the reading cannot disagree with it. */
  function scheduleFields() {
    if (el("autosyncMode").value === "interval") {
      const amount = el("autosyncIntervalValue").value.trim();
      return amount
        ? { autosync_interval: amount + el("autosyncIntervalUnit").value }
        : null;
    }
    const typed = el("autosyncCron").value.trim();
    return typed ? { autosync_cron: typed } : null;
  }

  function preview(normalise) {
    clearTimeout(previewTimer);
    const token = ++previewToken;
    const fields = scheduleFields();
    if (!fields) {
      showSummary(savedSummary, false);
      return;
    }

    previewTimer = setTimeout(async () => {
      try {
        const data = await apiSend("/api/settings/schedule-preview", "POST", fields);
        if (token !== previewToken) return;
        // A time the pickers could not write as cron comes back as cron here
        if (normalise && data.cron) el("autosyncCron").value = data.cron;

        // Only worth appending when it says something the reading does not:
        // a sentence that became cron, not the same cron spaced differently
        const bare = (value) => String(value || "").replace(/\s+/g, "");
        const cron =
          data.cron &&
          data.cron !== data.description &&
          bare(data.cron) !== bare(fields.autosync_cron)
            ? ` (${data.cron})`
            : "";

        showSummary(
          t("settings.autosync_runs", "Auto-Sync runs: {schedule}", {
            schedule: data.description
          }) + cron,
          false
        );
      } catch (error) {
        if (token !== previewToken) return;
        showSummary(
          t("settings.autosync_invalid", "Not a schedule: {error}", {
            error: error.message
          }),
          true
        );
      }
    }, 250);
  }

  el("autosyncMode").addEventListener("change", () => {
    const mode = el("autosyncMode").value;
    el("autosyncIntervalRow").hidden = mode !== "interval";
    el("autosyncCronRow").hidden = mode === "interval";
    preview();
  });

  el("autosyncIntervalValue").addEventListener("input", preview);
  el("autosyncIntervalUnit").addEventListener("change", preview);

  /* The chips and the times write the text field, so what gets saved is
     always the one thing you can also read, and it reads as cron. */
  function cronFromPickers() {
    const days = Array.from(dayPicker.querySelectorAll("input:checked"))
      .map((box) => Number(box.value))
      .sort((a, b) => a - b);
    const dayField = days.length ? days.join(",") : "*";

    const written = el("autosyncTimes").value.trim() || "00:00";
    const parts = written
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    const clock = parts.map((part) => /^(\d{1,2}):(\d{2})$/.exec(part));

    // Anything not written as HH:MM ("8am", "noon") is left to the server:
    // the phrase goes out and comes back as cron with the reading
    if (clock.some((match) => !match)) {
      const named = days.length ? days.map((day) => CRON_DAYS[day]).join(",") : "day";
      return `every ${named} at ${written}`;
    }

    // Cron cannot put 08:00 and 22:30 on one line, they would cross-multiply
    // into four runs, so a minute of its own gets a line of its own
    const byMinute = new Map();
    clock.forEach((match) => {
      const minute = Number(match[2]);
      if (!byMinute.has(minute)) byMinute.set(minute, []);
      byMinute.get(minute).push(Number(match[1]));
    });

    return Array.from(byMinute.entries())
      .sort((a, b) => a[0] - b[0])
      .map(
        ([minute, hours]) =>
          `${minute} ${hours.sort((a, b) => a - b).join(",")} * * ${dayField}`
      )
      .join("; ");
  }

  function pickersChanged() {
    el("autosyncCron").value = cronFromPickers();
    preview(true);
  }

  dayPicker.addEventListener("change", pickersChanged);
  el("autosyncTimes").addEventListener("input", pickersChanged);
  el("autosyncCron").addEventListener("input", () => preview(false));

  const saveScheduleBtn = el("saveAutosyncScheduleBtn");

  saveScheduleBtn.addEventListener("click", async () => {
    const payload = scheduleFields() || {};
    payload.autosync_mode = el("autosyncMode").value;
    saveScheduleBtn.disabled = true;
    try {
      if (await save(payload)) load();
    } finally {
      saveScheduleBtn.disabled = false;
    }
  });

  [el("autosyncTimes"), el("autosyncCron"), el("autosyncIntervalValue")].forEach(
    (field) => {
      field.addEventListener("keydown", (event) => {
        if (event.key === "Enter") saveScheduleBtn.click();
      });
    }
  );

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

  /* ===== Custom CSS ===== */
  const cssBox = el("customCss");

  function showCssSize() {
    const bytes = new TextEncoder().encode(cssBox.value).length;
    if (!bytes) {
      el("cssSize").textContent = "";
      return;
    }
    // a short theme in KB reads "0.0", which tells nobody anything
    el("cssSize").textContent =
      bytes < 1024
        ? t("settings.css_size_bytes", "{size} bytes", { size: bytes })
        : t("settings.css_size", "{size} KB", { size: (bytes / 1024).toFixed(1) });
  }

  /* A browser drops a stylesheet that did not arrive as text/css, and says
     nothing anywhere, so the only place this can be caught is here. */
  function showCssWarnings(warnings) {
    const box = el("cssWarning");
    box.textContent = "";
    box.hidden = !warnings || !warnings.length;
    if (box.hidden) return;

    warnings.forEach((warning) => {
      const line = document.createElement("p");
      line.textContent = t(
        "settings.css_import_blocked",
        "{host} sends files as plain text, so browsers ignore this import.",
        { host: warning.host }
      );
      box.appendChild(line);

      if (!warning.suggestion) return;
      const fix = document.createElement("p");
      fix.textContent = `${t("settings.css_import_try", "Use this instead:")} `;
      const code = document.createElement("code");
      code.textContent = warning.suggestion;
      fix.appendChild(code);
      box.appendChild(fix);
    });
  }

  /* Point the tag at the new hash so the browser fetches the saved sheet
     instead of the cached one, and drop it entirely once the box is empty. */
  function applyCustomCss(version) {
    const existing = document.querySelector("link[data-custom-css]");
    if (!version) {
      if (existing) existing.remove();
      return;
    }
    if (existing) {
      existing.href = `/custom.css?v=${version}`;
      return;
    }
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.dataset.customCss = "1";
    link.href = `/custom.css?v=${version}`;
    document.head.appendChild(link);
  }

  async function loadCustomCss() {
    try {
      const data = await apiFetch("/api/custom-css");
      cssBox.value = data.css || "";
      showCssSize();
      showCssWarnings(data.warnings);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function saveCustomCss() {
    try {
      const data = await apiSend("/api/custom-css", "PUT", { css: cssBox.value });
      // the server hoists imports, so show back what it actually stored
      cssBox.value = data.css || "";
      showCssSize();
      showCssWarnings(data.warnings);
      applyCustomCss(data.version);
      showToast(t("settings.saved", "Saved"));
    } catch (error) {
      showToast(`${t("settings.save_failed", "Could not save")}: ${error.message}`);
    }
  }

  cssBox.addEventListener("input", showCssSize);
  el("saveCssBtn").addEventListener("click", saveCustomCss);
  el("resetCssBtn").addEventListener("click", () => {
    cssBox.value = "";
    saveCustomCss();
  });

  /* ===== Background shader =====
     Compiled here before it is saved, purely so a mistake comes back as a GLSL
     error with a line number instead of a black screen. The server stores the
     source and never runs it. */
  const shaderBox = el("customShader");

  const SHADER_PRELUDE = `#version 300 es
precision highp float;
uniform vec2 u_resolution;
uniform float u_time;
out vec4 fragColor;
`;

  function compileShader(source) {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2");
    if (!gl) return { ok: true, skipped: true };

    const shader = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(shader, SHADER_PRELUDE + source);
    gl.compileShader(shader);
    const ok = gl.getShaderParameter(shader, gl.COMPILE_STATUS);
    const log = ok ? "" : gl.getShaderInfoLog(shader) || "";
    gl.deleteShader(shader);
    // the prelude sits above the author's code, so reported lines are offset
    const offset = SHADER_PRELUDE.split("\n").length - 1;
    return {
      ok,
      log: log.replace(/(\d+):(\d+)/g, (m, col, line) => `${col}:${line - offset}`)
    };
  }

  function showShaderError(text) {
    const box = el("shaderError");
    box.textContent = text || "";
    box.hidden = !text;
  }

  function applyShader(version) {
    const existing = document.getElementById("themeShader");
    if (existing) existing.remove();
    if (!version) return;
    // the runner is only on the page once a shader exists, so reload to start it
    showToast(t("settings.shader_reload", "Saved. Reload to see it."));
  }

  async function loadShader() {
    if (!shaderBox) return;
    try {
      const data = await apiFetch("/api/custom-shader");
      shaderBox.value = data.shader || "";
      showShaderError("");
    } catch (error) {
      showToast(error.message);
    }
  }

  async function saveShader() {
    const source = shaderBox.value.trim();
    if (source) {
      const result = compileShader(source);
      if (!result.ok) {
        showShaderError(result.log.trim());
        el("shaderStatus").textContent = t("settings.shader_bad", "Not saved");
        return;
      }
    }
    showShaderError("");
    try {
      const data = await apiSend("/api/custom-shader", "PUT", { shader: source });
      shaderBox.value = data.shader || "";
      el("shaderStatus").textContent = "";
      applyShader(data.version);
      if (!data.version) showToast(t("settings.saved", "Saved"));
    } catch (error) {
      showToast(`${t("settings.save_failed", "Could not save")}: ${error.message}`);
    }
  }

  if (shaderBox) {
    el("saveShaderBtn").addEventListener("click", saveShader);
    el("clearShaderBtn").addEventListener("click", () => {
      shaderBox.value = "";
      saveShader();
    });
    shaderBox.addEventListener("input", () => {
      showShaderError("");
      el("shaderStatus").textContent = "";
    });
  }

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
  loadCustomCss();
  loadShader();
  loadCustomPaths();
  loadDiscordStatus();
  loadApiKeys();
})();
