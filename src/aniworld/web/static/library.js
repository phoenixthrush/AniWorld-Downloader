/* Library tree.
 *
 * Four levels, each fetched only when it is opened:
 *   location -> genre group -> title folders -> seasons/episodes of one title
 *
 * The genre group is derived client-side from the "genre" field the titles
 * endpoint now returns (see library.list_titles_with_meta on the backend):
 * a title's main genre plus an always-present "all" group. Nothing extra is
 * fetched for this, it groups what /api/library/titles already returned.
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

  function seasonLabel(key) {
    return key === "movie" ? t("library.movies", "Movies") : `${t("index.season", "Season")} ${esc(key)}`;
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
          <div class="library-children" data-level="genres"></div>
        </div>`
      )
      .join("");
  }

  /* ===== Genre grouping, done on what titles() already returned ===== */
  function groupByGenre(titles) {
    const groups = new Map();
    groups.set("__all__", titles.slice());

    titles.forEach((entry) => {
      const genre = (entry.genre || "").trim();
      if (!genre) return;
      if (!groups.has(genre)) groups.set(genre, []);
      groups.get(genre).push(entry);
    });

    const ordered = [
      { key: "__all__", label: t("library.all", "All"), titles: groups.get("__all__") }
    ];
    Array.from(groups.keys())
      .filter((key) => key !== "__all__")
      .sort((a, b) => a.localeCompare(b))
      .forEach((key) => ordered.push({ key, label: key, titles: groups.get(key) }));
    return ordered;
  }

  /* ===== Level 2: genre groups, each holding its title folders ===== */
  async function loadTitles(node) {
    const location = locations[Number(node.dataset.location)];
    const container = node.querySelector('[data-level="genres"]');
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

    const groups = groupByGenre(titles);

    container.innerHTML = groups
      .map(
        (group) => `
        <div class="library-node" data-genre="${esc(group.key)}">
          <div class="library-row" data-toggle="genre">
            <div class="library-row-left">
              <span class="arrow">&#9654;</span>
              <span class="library-name">${esc(group.label)}</span>
            </div>
            <div class="library-row-right">
              <span class="library-sub">${group.titles.length}</span>
            </div>
          </div>
          <div class="library-children" data-level="titles">
            ${group.titles
              .map(
                (entry) => `
              <div class="library-node" data-folder="${esc(entry.folder)}">
                <div class="library-row" data-toggle="title">
                  <div class="library-row-left">
                    <span class="arrow">&#9654;</span>
                    <span class="library-name">${esc(entry.folder)}</span>
                  </div>
                  <div class="library-row-right">
                    <span class="library-sub" data-summary></span>
                    <button class="icon-btn" data-delete="title" title="${t("common.delete", "Delete")}">&times;</button>
                  </div>
                </div>
                <div class="library-children" data-level="title"></div>
              </div>`
              )
              .join("")}
          </div>
        </div>`
      )
      .join("");
  }

  /* ===== Level 3: seasons, episodes and movies of one title ===== */
  async function loadTitle(node) {
    const locationNode = node.closest("[data-location]");
    const location = locations[Number(locationNode.dataset.location)];
    const container = node.querySelector('[data-level="title"]');
    const folder = node.dataset.folder;
    container.innerHTML = message(t("common.loading", "Loading..."));

    let details;
    try {
      const query = locationQuery(location);
      const encodedFolder = encodeURIComponent(folder);
      details = await apiFetch(
        `/api/library/title?folder=${encodedFolder}${query ? `&${query}` : ""}`
      );
    } catch (error) {
      container.innerHTML = message(t("common.failed", "Failed"));
      return;
    }

    const summary = node.querySelector("[data-summary]");
    if (summary) {
      summary.textContent = `${details.total_episodes} ${t("library.episodes", "ep")} | ${formatSize(details.total_size)}`;
    }

    // "movie" sorts after every numbered season, not among them.
    const seasonKeys = Object.keys(details.seasons).sort((a, b) => {
      if (a === "movie") return 1;
      if (b === "movie") return -1;
      return Number(a) - Number(b);
    });
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
                <span class="library-name">${seasonLabel(key)}</span>
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

    // A genre group only toggles visibility; its titles were already
    // rendered by loadTitles(), there is nothing left to fetch for it.
    if (row.dataset.toggle === "genre") {
      children.classList.toggle("expanded", expanding);
      arrow.classList.toggle("expanded", expanding);
      return;
    }

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
      // "movie" is a synthetic season key, not a number - keep it as-is.
      const season = button.closest("[data-season]").dataset.season;
      payload.season = season === "movie" ? season : Number(season);
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
