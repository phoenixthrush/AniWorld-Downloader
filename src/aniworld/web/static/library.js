/* Library tree.
 *
 * Three levels, each fetched only when it is opened:
 *   location -> title folders -> seasons/episodes of one title
 */

(function () {
  const tree = document.getElementById("libraryTree");
  const refreshBtn = document.getElementById("libraryRefresh");

  let locations = [];

  function locationQuery(location) {
    const params = new URLSearchParams();
    if (location.custom_path_id) params.set("path_id", location.custom_path_id);
    if (location.lang_folder) params.set("lang_folder", location.lang_folder);
    return params.toString();
  }

  function locationName(location) {
    return location.lang_folder
      ? `${location.label} / ${location.lang_folder}`
      : location.label;
  }

  function message(text) {
    return `<div class="empty-state">${esc(text)}</div>`;
  }

  /* ===== Level 1: locations ===== */
  async function load() {
    tree.innerHTML = message(t("common.loading", "Loading..."));
    try {
      const data = await apiFetch("/api/library/locations");
      locations = data.locations || [];
    } catch (error) {
      tree.innerHTML = message(t("library.load_failed", "Failed to load library."));
      return;
    }

    if (!locations.length) {
      tree.innerHTML = message(t("library.empty", "No downloaded content found."));
      return;
    }

    tree.innerHTML = locations
      .map(
        (location, index) => `
        <div class="library-node" data-location="${index}">
          <div class="library-row" data-toggle="location">
            <div class="library-row-left">
              <span class="arrow">&#9654;</span>
              <span class="library-name">${esc(locationName(location))}</span>
            </div>
            <div class="library-row-right">
              <span class="library-sub">${esc(location.path)}</span>
            </div>
          </div>
          <div class="library-children" data-level="titles"></div>
        </div>`
      )
      .join("");
  }

  /* ===== Level 2: title folders ===== */
  async function loadTitles(node) {
    const location = locations[Number(node.dataset.location)];
    const container = node.querySelector('[data-level="titles"]');
    container.innerHTML = message(t("common.loading", "Loading..."));

    let titles = [];
    try {
      const data = await apiFetch(`/api/library/titles?${locationQuery(location)}`);
      titles = data.titles || [];
    } catch (error) {
      container.innerHTML = message(t("common.failed", "Failed"));
      return;
    }

    if (!titles.length) {
      container.innerHTML = message(t("library.no_titles", "This folder is empty."));
      return;
    }

    container.innerHTML = titles
      .map(
        (folder) => `
        <div class="library-node" data-folder="${esc(folder)}">
          <div class="library-row" data-toggle="title">
            <div class="library-row-left">
              <span class="arrow">&#9654;</span>
              <span class="library-name">${esc(folder)}</span>
            </div>
            <div class="library-row-right">
              <span class="library-sub" data-summary></span>
              <button class="icon-btn" data-delete="title" title="${t("common.delete", "Delete")}">&times;</button>
            </div>
          </div>
          <div class="library-children" data-level="title"></div>
        </div>`
      )
      .join("");
  }

  /* ===== Level 3: seasons and episodes of one title ===== */
  async function loadTitle(node) {
    const locationNode = node.closest("[data-location]");
    const location = locations[Number(locationNode.dataset.location)];
    const container = node.querySelector('[data-level="title"]');
    container.innerHTML = message(t("common.loading", "Loading..."));

    let details;
    try {
      const query = locationQuery(location);
      const folder = encodeURIComponent(node.dataset.folder);
      details = await apiFetch(
        `/api/library/title?folder=${folder}${query ? `&${query}` : ""}`
      );
    } catch (error) {
      container.innerHTML = message(t("common.failed", "Failed"));
      return;
    }

    const summary = node.querySelector("[data-summary]");
    if (summary) {
      summary.textContent = `${details.total_episodes} ${t("library.episodes", "ep")} | ${formatSize(details.total_size)}`;
    }

    const seasonKeys = Object.keys(details.seasons).sort((a, b) => Number(a) - Number(b));
    if (!seasonKeys.length) {
      container.innerHTML = message(t("library.no_titles", "This folder is empty."));
      return;
    }

    container.innerHTML = seasonKeys
      .map((key) => {
        const episodes = details.seasons[key];
        const size = episodes.reduce((total, episode) => total + episode.size, 0);
        const count = episodes.filter((episode) => episode.is_video !== false).length;

        const rows = episodes
          .map(
            (episode) => `
            <div class="library-episode" data-episode="${episode.episode}">
              <span class="library-ep-num">E${String(episode.episode).padStart(3, "0")}</span>
              <span class="library-ep-file" title="${esc(episode.file)}">${esc(episode.file)}</span>
              <span class="library-ep-size">${formatSize(episode.size)}</span>
              <button class="icon-btn" data-delete="episode" title="${t("common.delete", "Delete")}">&times;</button>
            </div>`
          )
          .join("");

        return `
          <div class="library-node" data-season="${esc(key)}">
            <div class="library-row" data-toggle="season">
              <div class="library-row-left">
                <span class="arrow">&#9654;</span>
                <span class="library-name">${t("index.season", "Season")} ${esc(key)}</span>
              </div>
              <div class="library-row-right">
                <span class="library-sub">${count} ${t("library.episodes", "ep")} | ${formatSize(size)}</span>
                <button class="icon-btn" data-delete="season" title="${t("common.delete", "Delete")}">&times;</button>
              </div>
            </div>
            <div class="library-children">${rows}</div>
          </div>`;
      })
      .join("");
  }

  /* ===== Expanding ===== */
  const LOADERS = { location: loadTitles, title: loadTitle };

  tree.addEventListener("click", async (event) => {
    if (event.target.closest("[data-delete]")) return;

    const row = event.target.closest("[data-toggle]");
    if (!row) return;

    const node = row.parentElement;
    const children = row.nextElementSibling;
    const arrow = row.querySelector(".arrow");
    const expanding = !children.classList.contains("expanded");

    if (expanding && !node.dataset.loaded) {
      const loader = LOADERS[row.dataset.toggle];
      if (loader) {
        node.dataset.loaded = "1";
        await loader(node);
      }
    }

    children.classList.toggle("expanded", expanding);
    arrow.classList.toggle("expanded", expanding);
  });

  /* ===== Deleting ===== */
  function confirmMessage(kind, node) {
    const titleNode = node.closest("[data-folder]");
    const name = titleNode ? titleNode.dataset.folder : "";
    if (kind === "title") {
      return t("library.confirm_title", 'Really delete all of "{name}"?', { name });
    }
    if (kind === "season") {
      const season = node.closest("[data-season]").dataset.season;
      return t("library.confirm_season", 'Really delete season {season} of "{name}"?', {
        season,
        name
      });
    }
    return t("library.confirm_episode", "Really delete this episode?");
  }

  tree.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete]");
    if (!button) return;
    event.stopPropagation();

    const kind = button.dataset.delete;
    const titleNode = button.closest("[data-folder]");
    const locationNode = button.closest("[data-location]");
    const location = locations[Number(locationNode.dataset.location)];

    if (!window.confirm(confirmMessage(kind, button))) return;

    const payload = {
      folder: titleNode.dataset.folder,
      custom_path_id: location.custom_path_id,
      lang_folder: location.lang_folder
    };
    if (kind !== "title") {
      payload.season = Number(button.closest("[data-season]").dataset.season);
    }
    if (kind === "episode") {
      payload.episode = Number(button.closest("[data-episode]").dataset.episode);
    }

    try {
      await apiSend("/api/library/delete", "POST", payload);
      showToast(t("library.deleted", "Deleted"));
      await load();
    } catch (error) {
      showToast(error.message);
    }
  });

  if (refreshBtn) refreshBtn.addEventListener("click", load);
  load();
})();
