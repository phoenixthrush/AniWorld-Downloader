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

  function fileUrl(location, folder, relativePath) {
    const params = new URLSearchParams(locationQuery(location));
    params.set("folder", folder);
    params.set("path", relativePath);
    return `/api/library/file?${params.toString()}`;
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
          .map((episode) => {
            const playable = episode.is_video !== false && episode.path;
            const playUrl = playable ? fileUrl(location, folder, episode.path) : "";
            return `
            <div class="library-episode" data-episode="${episode.episode}"
                 data-playable="${playable ? "1" : "0"}" data-play="${esc(playUrl)}">
              <span class="library-ep-num">E${String(episode.episode).padStart(3, "0")}</span>
              <span class="library-ep-file" title="${esc(episode.file)}">${esc(episode.file)}</span>
              <span class="library-ep-size">${formatSize(episode.size)}</span>
              <button class="icon-btn" data-delete="episode" title="${t("common.delete", "Delete")}">&times;</button>
            </div>
            <div class="library-video-player"></div>`;
          })
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
    if (event.target.closest("[data-delete]") || event.target.closest("[data-play]")) return;

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

  /* ===== Inline player =====
   * Fullscreen is only requested through the standard Fullscreen API, which
   * covers desktop browsers. Where it is unavailable (notably iOS Safari for
   * <video>) the element is simply left to play inline with its native
   * controls; there is no vendor-specific fallback here.
   */
  function attachAutoPip(video, container) {
    video.addEventListener("fullscreenchange", () => {
      if (document.fullscreenElement === video) return;
      if (video.paused || video.ended) return;
      if (!document.pictureInPictureEnabled || video.disablePictureInPicture) return;
      if (document.pictureInPictureElement) return;
      video.requestPictureInPicture().catch(() => {});
    });

    // Leaving PiP closes the player rather than restoring it inline: once the
    // floating window is dismissed the row it belonged to may be long gone
    // from view, and reopening it is one click away.
    video.addEventListener("enterpictureinpicture", () => {
      container.style.display = "none";
    });
    video.addEventListener("leavepictureinpicture", () => {
      container.innerHTML = "";
      container.style.display = "";
    });
  }

  tree.addEventListener("click", (event) => {
    const row = event.target.closest("[data-playable='1']");
    if (!row) return;
    if (event.target.closest("[data-delete]")) return;

    const url = row.dataset.play;
    const container = row.nextElementSibling;
    if (!container || !container.classList.contains("library-video-player")) return;

    if (container.dataset.open === "1") {
      const openVideo = container.querySelector("video");
      if (openVideo && document.fullscreenElement === openVideo) {
        document.exitFullscreen().catch(() => {});
      }
      container.innerHTML = "";
      container.dataset.open = "0";
      return;
    }

    tree.querySelectorAll('.library-video-player[data-open="1"]').forEach((el) => {
      el.innerHTML = "";
      el.dataset.open = "0";
    });

    container.innerHTML = `<video controls autoplay src="${esc(url)}"></video>`;
    container.dataset.open = "1";

    const video = container.querySelector("video");
    attachAutoPip(video, container);
    if (video.requestFullscreen) {
      video.requestFullscreen().catch(() => {});
    }
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
