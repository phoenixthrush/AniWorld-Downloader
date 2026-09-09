/* Library.
 *
 * Three views, one page, switched by the URL hash so the back button works:
 *   #/cards                    poster grid, one card per title, progress on each
 *   #/tree                     the original expandable tree (locations -> titles)
 *   #/series/<loc>/<folder>    one title: header, seasons, episode cards
 * Playing an episode opens the player modal (webplayer.js) on top of whatever
 * view is showing. Watch positions are saved every few seconds and on close.
 *
 * Episode thumbnails are made here too: an episode without a cached frame
 * gets one rendered in the background by the same client-side pipeline that
 * plays it, posted back to the server, and shown from then on.
 */

(function () {
  const cardsEl = document.getElementById("libraryCards");
  const tree = document.getElementById("libraryTree");
  const seriesEl = document.getElementById("librarySeries");
  const continueEl = document.getElementById("libraryContinue");
  const continueStrip = document.getElementById("continueStrip");
  const heading = document.getElementById("libraryHeading");
  const hint = document.getElementById("libraryHint");
  const backBtn = document.getElementById("libraryBack");
  const refreshBtn = document.getElementById("libraryRefresh");
  const viewSwitch = document.getElementById("libraryViewSwitch");
  const locationField = document.getElementById("libraryLocationField");
  const locationSelect = document.getElementById("libraryLocation");
  const isAdmin = Boolean(window.LIBRARY_ADMIN);
  const uiLanguage = (window.UI_LANGUAGE || "en").toLowerCase();

  let locations = [];
  let locationIndex = 0;
  let view = "cards";
  let series = null; // { location, folder, details, season, episodes: [...flat, ordered] }
  let thumbJob = 0; // bumps to cancel the background thumbnail worker

  /* ===== Helpers ===== */
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
    return key === "movie"
      ? t("library.movies", "Movies")
      : `${t("index.season", "Season")} ${esc(key)}`;
  }

  function fileUrl(location, folder, path) {
    const params = new URLSearchParams(locationQuery(location));
    params.set("folder", folder);
    params.set("path", path);
    return `/api/library/file?${params.toString()}`;
  }

  function thumbUrl(location, folder, path, bust) {
    const params = new URLSearchParams(locationQuery(location));
    params.set("folder", folder);
    params.set("path", path);
    if (bust) params.set("v", String(bust));
    return `/api/library/thumbnail?${params.toString()}`;
  }

  function coverUrl(location, card) {
    if (!card.cover) return "";
    if (card.cover.kind === "poster") {
      return `/api/proxy-image?url=${encodeURIComponent(card.cover.url)}`;
    }
    const params = new URLSearchParams(locationQuery(location));
    params.set("folder", card.folder);
    params.set("stem", card.cover.stem);
    return `/api/library/thumbnail?${params.toString()}`;
  }

  function episodeTitle(episode, seasonKey) {
    const de = episode.title_de || "";
    const en = episode.title_en || "";
    const preferred = uiLanguage === "de" ? de || en : en || de;
    if (preferred) return preferred;
    if (seasonKey === "movie") return episode.file.replace(/\.[^.]+$/, "");
    return t("library.untitled_episode", "Episode {n}", { n: episode.episode });
  }

  function episodeCode(seasonKey, episode) {
    if (seasonKey === "movie") return t("library.movie", "Movie");
    return `S${String(seasonKey).padStart(2, "0")}E${String(episode.episode).padStart(2, "0")}`;
  }

  function percent(progress) {
    if (!progress || !progress.duration) return progress && progress.watched ? 100 : 0;
    if (progress.watched) return 100;
    return Math.min(100, Math.round((progress.position / progress.duration) * 100));
  }

  function siteLabel(key) {
    const labels = {
      aniworld: "AniWorld",
      sto: "SerienStream",
      megakino: "MegaKino",
      htv: "Hanime",
      cineby: "Cineby",
      kinox: "Kinox",
      burningseries: "BurningSeries",
      filmpalast: "FilmPalast"
    };
    return labels[key] || key;
  }

  /* ===== Themed confirm (no window.confirm here) ===== */
  function confirmDelete(text) {
    const overlay = document.getElementById("libraryConfirm");
    const label = document.getElementById("libraryConfirmText");
    const ok = document.getElementById("libraryConfirmOk");
    const cancel = document.getElementById("libraryConfirmCancel");
    label.textContent = text;
    openModal("libraryConfirm");
    ok.focus();
    return new Promise((resolve) => {
      const finish = (answer) => {
        ok.removeEventListener("click", onOk);
        cancel.removeEventListener("click", onCancel);
        overlay.removeEventListener("modal-closed", onCancel);
        closeModal("libraryConfirm");
        resolve(answer);
      };
      const onOk = () => finish(true);
      const onCancel = () => finish(false);
      ok.addEventListener("click", onOk);
      cancel.addEventListener("click", onCancel);
      overlay.addEventListener("modal-closed", onCancel);
    });
  }

  /* ===== Routing ===== */
  function route() {
    const hash = window.location.hash.replace(/^#\/?/, "");
    const parts = hash.split("/");
    if (parts[0] === "series" && parts.length >= 3) {
      const index = Number(parts[1]);
      const folder = decodeURIComponent(parts.slice(2).join("/"));
      if (locations[index]) {
        locationIndex = index;
        openSeries(folder);
        return;
      }
    }
    view = parts[0] === "tree" ? "tree" : "cards";
    showList();
  }

  function navigate(hash) {
    if (window.location.hash === hash) route();
    else window.location.hash = hash;
  }

  function showList() {
    thumbJob += 1;
    series = null;
    window.scrollTo(0, 0);
    seriesEl.hidden = true;
    seriesEl.innerHTML = "";
    backBtn.hidden = true;
    heading.textContent = t("library.title", "Library");
    hint.hidden = false;
    viewSwitch.hidden = false;
    locationField.hidden = locations.length < 2;
    viewSwitch.querySelectorAll("[data-view]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.view === view));
    });
    cardsEl.hidden = view !== "cards";
    continueEl.hidden = view !== "cards";
    tree.hidden = view !== "tree";
    if (view === "cards") loadCards();
    else loadTree();
  }

  viewSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    navigate(`#/${button.dataset.view}`);
  });

  locationSelect.addEventListener("change", () => {
    locationIndex = Number(locationSelect.value) || 0;
    if (view === "cards") loadCards();
  });

  backBtn.addEventListener("click", () => navigate("#/cards"));

  /* ===== Level 0: locations ===== */
  async function loadLocations() {
    try {
      const data = await apiFetch("/api/library/locations");
      locations = data.locations || [];
    } catch (error) {
      locations = [];
      cardsEl.innerHTML = message(t("library.load_failed", "Failed to load library."));
      return false;
    }
    locationSelect.innerHTML = locations
      .map((location, index) => `<option value="${index}">${esc(locationName(location))}</option>`)
      .join("");
    if (locationIndex >= locations.length) locationIndex = 0;
    locationSelect.value = String(locationIndex);
    return locations.length > 0;
  }

  /* ===== Cards ===== */
  async function loadCards() {
    const location = locations[locationIndex];
    if (!location) {
      cardsEl.innerHTML = message(t("library.empty", "No downloaded content found."));
      continueEl.hidden = true;
      return;
    }
    cardsEl.innerHTML = message(t("common.loading", "Loading..."));
    loadContinue();
    let cards = [];
    try {
      const data = await apiFetch(`/api/library/cards?${locationQuery(location)}`);
      cards = data.cards || [];
    } catch (error) {
      cardsEl.innerHTML = message(t("library.load_failed", "Failed to load library."));
      return;
    }
    if (!cards.length) {
      cardsEl.innerHTML = message(t("library.no_cards", "Nothing here yet."));
      return;
    }
    cardsEl.innerHTML = cards.map((card) => renderCard(location, card)).join("");
  }

  function renderCard(location, card) {
    const cover = coverUrl(location, card);
    const total = card.episodes || 0;
    const done = card.watched || 0;
    const pct = total ? Math.round((done / total) * 100) : 0;
    const movieOnly = card.categories.length === 1 && card.categories[0] === "movies";
    const subtitleParts = [];
    if (card.year) subtitleParts.push(card.year);
    if (movieOnly) subtitleParts.push(t("library.movie", "Movie"));
    else if (total) subtitleParts.push(`${total} ${t("library.episodes", "ep")}`);
    if (done && !movieOnly) subtitleParts.push(`${done} ${t("library.watched", "watched")}`);
    const initials = (card.title || card.folder).trim().slice(0, 2).toUpperCase();
    return `
      <div class="poster-card" data-folder="${esc(card.folder)}" tabindex="0" role="button">
        <div class="cover">
          ${
            cover
              ? `<img src="${esc(cover)}" alt="" loading="lazy" />`
              : `<div class="cover-blank">${esc(initials)}</div>`
          }
          <div class="card-badges">
            ${card.site ? `<span class="pill">${esc(siteLabel(card.site))}</span>` : "<span></span>"}
            ${total && done >= total ? `<span class="pill pill-done">&#10003;</span>` : ""}
          </div>
          ${total ? `<div class="card-progress"><span style="width:${pct}%"></span></div>` : ""}
        </div>
        <div class="info">
          <div class="title" title="${esc(card.title)}">${esc(card.title)}</div>
          <div class="subtitle">${esc(subtitleParts.join(" · "))}</div>
        </div>
      </div>`;
  }

  cardsEl.addEventListener("click", (event) => {
    const card = event.target.closest(".poster-card");
    if (!card) return;
    navigate(`#/series/${locationIndex}/${encodeURIComponent(card.dataset.folder)}`);
  });

  cardsEl.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".poster-card");
    if (!card) return;
    event.preventDefault();
    navigate(`#/series/${locationIndex}/${encodeURIComponent(card.dataset.folder)}`);
  });

  /* ===== Continue watching ===== */
  async function loadContinue() {
    let items = [];
    try {
      items = (await apiFetch("/api/library/continue")).items || [];
    } catch (error) {
      items = [];
    }
    continueEl.hidden = !items.length || view !== "cards";
    if (!items.length) return;
    continueStrip.innerHTML = items
      .map((item, index) => {
        const location = {
          custom_path_id: item.custom_path_id,
          lang_folder: item.lang_folder
        };
        const seasonKey = item.season == null ? "movie" : String(item.season);
        const episode = {
          episode: item.episode,
          file: item.path.split("/").pop(),
          title_de: item.title_de,
          title_en: item.title_en
        };
        const pct = item.duration ? Math.round((item.position / item.duration) * 100) : 0;
        return `
          <div class="ep-card" data-continue="${index}" tabindex="0" role="button">
            <div class="ep-thumb">
              ${
                item.thumbnail
                  ? `<img src="${esc(thumbUrl(location, item.folder, item.path))}" alt="" loading="lazy" />`
                  : ""
              }
              <span class="pill ep-num">${esc(episodeCode(seasonKey, episode))}</span>
              <div class="ep-play">&#9654;</div>
              <div class="ep-progress"><span style="width:${pct}%"></span></div>
            </div>
            <div class="ep-info">
              <div class="ep-title" title="${esc(item.title)}">${esc(item.title)}</div>
              <div class="ep-sub"><span>${esc(episodeTitle(episode, seasonKey))}</span>
                <span>${esc(WebPlayer.formatTime(item.position))} / ${esc(WebPlayer.formatTime(item.duration))}</span></div>
            </div>
          </div>`;
      })
      .join("");
    continueStrip.dataset.items = JSON.stringify(items);
  }

  continueStrip.addEventListener("click", (event) => {
    const card = event.target.closest("[data-continue]");
    if (!card) return;
    const items = JSON.parse(continueStrip.dataset.items || "[]");
    const item = items[Number(card.dataset.continue)];
    if (!item) return;
    const index = locations.findIndex(
      (loc) =>
        (loc.custom_path_id || null) === (item.custom_path_id || null) &&
        (loc.lang_folder || null) === (item.lang_folder || null)
    );
    if (index < 0) return;
    locationIndex = index;
    openSeries(item.folder, { play: item.path });
    window.history.replaceState(
      null,
      "",
      `#/series/${index}/${encodeURIComponent(item.folder)}`
    );
  });

  /* ===== Series view ===== */
  async function openSeries(folder, options) {
    const location = locations[locationIndex];
    if (!location) return;
    thumbJob += 1;
    window.scrollTo(0, 0);
    cardsEl.hidden = true;
    continueEl.hidden = true;
    tree.hidden = true;
    hint.hidden = true;
    viewSwitch.hidden = true;
    locationField.hidden = true;
    backBtn.hidden = false;
    seriesEl.hidden = false;
    seriesEl.innerHTML = message(t("common.loading", "Loading..."));

    let details;
    try {
      const query = locationQuery(location);
      details = await apiFetch(
        `/api/library/title?folder=${encodeURIComponent(folder)}${query ? `&${query}` : ""}`
      );
    } catch (error) {
      seriesEl.innerHTML = message(t("common.failed", "Failed"));
      return;
    }

    const seasonKeys = Object.keys(details.seasons).sort((a, b) => {
      if (a === "movie") return 1;
      if (b === "movie") return -1;
      return Number(a) - Number(b);
    });
    const episodes = [];
    seasonKeys.forEach((key) => {
      details.seasons[key]
        .filter((episode) => episode.is_video !== false)
        .forEach((episode) => episodes.push({ seasonKey: key, ...episode }));
    });
    let season = seasonKeys[0];
    // open on the season with the first unfinished episode
    const firstOpen = episodes.find((e) => !(e.progress && e.progress.watched));
    if (firstOpen) season = firstOpen.seasonKey;

    series = { location, folder, details, season, episodes, seasonKeys };
    heading.textContent = details.meta.title || folder;
    renderSeries();

    if (options && options.play) {
      const index = episodes.findIndex((e) => e.path === options.play);
      if (index >= 0) openPlayer(index);
    }
    startThumbnailWorker();
  }

  function renderSeries() {
    const { location, folder, details, episodes } = series;
    const meta = details.meta || {};
    const total = episodes.length;
    const watched = episodes.filter((e) => e.progress && e.progress.watched).length;
    const cover = meta.poster_url
      ? `/api/proxy-image?url=${encodeURIComponent(meta.poster_url)}`
      : (() => {
          const withThumb = episodes.find((e) => e.thumbnail);
          return withThumb ? thumbUrl(location, folder, withThumb.path) : "";
        })();
    const line = [];
    if (meta.year) line.push(`<span>${esc(meta.year)}</span>`);
    if (meta.genres && meta.genres.length) line.push(`<span>${esc(meta.genres.join(", "))}</span>`);
    if (meta.series_url) {
      line.push(
        `<a href="${esc(meta.series_url)}" target="_blank" rel="noopener noreferrer">${esc(
          t("library.open_on_site", "Open on {site}", { site: siteLabel(meta.site || "aniworld") })
        )}</a>`
      );
    }
    line.push(`<span>${esc(formatSize(details.total_size))}</span>`);

    seriesEl.innerHTML = `
      <div class="series-header">
        <div class="series-poster">${cover ? `<img src="${esc(cover)}" alt="" />` : ""}</div>
        <div class="series-info">
          <h2>${esc(meta.title || folder)}</h2>
          <div class="series-line">${line.join('<span aria-hidden="true">&middot;</span>')}</div>
          ${meta.description ? `<p class="series-description">${esc(meta.description)}</p>` : ""}
          ${
            total
              ? `<div class="series-progress">
                   <div class="library-sub">${esc(t("library.of_watched", "{watched} of {total} watched", { watched, total }))}</div>
                   <div class="bar"><span style="width:${total ? Math.round((watched / total) * 100) : 0}%"></span></div>
                 </div>`
              : ""
          }
          <div class="series-actions">
            ${
              isAdmin
                ? `<button class="btn btn-ghost" data-action="delete-title">${esc(t("library.delete_title", "Delete title"))}</button>`
                : ""
            }
          </div>
        </div>
      </div>
      ${
        series.seasonKeys.length > 1
          ? `<div class="season-tabs" role="tablist">${series.seasonKeys
              .map(
                (key) =>
                  `<button class="season-tab" role="tab" data-season="${esc(key)}" aria-selected="${String(
                    key === series.season
                  )}">${seasonLabel(key)}</button>`
              )
              .join("")}</div>`
          : `<h2>${seasonLabel(series.season)}</h2>`
      }
      <div class="episode-grid" id="episodeGrid"></div>`;
    renderEpisodes();
  }

  function renderEpisodes() {
    const grid = document.getElementById("episodeGrid");
    if (!grid) return;
    const { location, folder, episodes } = series;
    grid.innerHTML = episodes
      .map((episode, index) => {
        if (episode.seasonKey !== series.season) return "";
        return renderEpisode(location, folder, episode, index);
      })
      .join("");
  }

  function renderEpisode(location, folder, episode, index) {
    const pct = percent(episode.progress);
    const watched = Boolean(episode.progress && episode.progress.watched);
    const playable = WebPlayer.canPlayInBrowser(episode.file);
    const sub = [];
    if (episode.progress && episode.progress.duration && !watched && episode.progress.position > 0) {
      sub.push(
        t("library.resume", "Resume at {time}", {
          time: WebPlayer.formatTime(episode.progress.position)
        })
      );
    } else {
      sub.push(formatSize(episode.size));
    }
    return `
      <div class="ep-card${watched ? " is-watched" : ""}" data-index="${index}" tabindex="0" role="button"
           aria-label="${esc(episodeCode(episode.seasonKey, episode))} ${esc(episodeTitle(episode, episode.seasonKey))}">
        <div class="ep-thumb">
          ${
            episode.thumbnail
              ? `<img src="${esc(thumbUrl(location, folder, episode.path, episode.thumbVersion))}" alt="" loading="lazy" />`
              : `<div class="ep-pending" data-pending>${playable ? esc(t("library.thumb_pending", "Frame coming up")) : ""}</div>`
          }
          <span class="pill ep-num">${esc(episodeCode(episode.seasonKey, episode))}</span>
          ${watched ? `<span class="pill pill-done ep-check">&#10003;</span>` : ""}
          ${playable ? `<div class="ep-play">&#9654;</div>` : ""}
          ${pct ? `<div class="ep-progress"><span style="width:${pct}%"></span></div>` : ""}
        </div>
        <div class="ep-info">
          <div class="ep-title" title="${esc(episode.file)}">${esc(episodeTitle(episode, episode.seasonKey))}</div>
          <div class="ep-sub"><span>${esc(sub.join(" "))}</span></div>
        </div>
        <div class="ep-menu">
          <button class="icon-btn" data-action="toggle-watched" title="${esc(
            watched ? t("library.mark_unwatched", "Mark as unwatched") : t("library.mark_watched", "Mark as watched")
          )}">${watched ? "&#8635;" : "&#10003;"}</button>
          ${
            isAdmin
              ? `<button class="icon-btn" data-action="delete-episode" title="${esc(t("common.delete", "Delete"))}">&times;</button>`
              : ""
          }
        </div>
      </div>`;
  }

  seriesEl.addEventListener("click", async (event) => {
    if (!series) return;
    const tab = event.target.closest("[data-season]");
    if (tab) {
      series.season = tab.dataset.season;
      seriesEl.querySelectorAll("[data-season]").forEach((button) => {
        button.setAttribute("aria-selected", String(button.dataset.season === series.season));
      });
      renderEpisodes();
      return;
    }
    const action = event.target.closest("[data-action]");
    const card = event.target.closest(".ep-card");
    if (action) {
      event.stopPropagation();
      const episode = card ? series.episodes[Number(card.dataset.index)] : null;
      if (action.dataset.action === "toggle-watched" && episode) {
        await setWatched(episode, !(episode.progress && episode.progress.watched));
      } else if (action.dataset.action === "delete-episode" && episode) {
        await deleteEpisode(episode);
      } else if (action.dataset.action === "delete-title") {
        await deleteTitle();
      }
      return;
    }
    if (card) openPlayer(Number(card.dataset.index));
  });

  seriesEl.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".ep-card");
    if (!card || event.target.closest("button")) return;
    event.preventDefault();
    openPlayer(Number(card.dataset.index));
  });

  async function postProgress(episode, payload) {
    const { location, folder } = series;
    const body = {
      folder,
      path: episode.path,
      custom_path_id: location.custom_path_id,
      lang_folder: location.lang_folder,
      ...payload
    };
    const data = await apiSend("/api/library/progress", "POST", body);
    episode.progress = data.progress;
    return data.progress;
  }

  async function setWatched(episode, watched) {
    try {
      await postProgress(episode, { watched });
      renderSeries();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function deleteEpisode(episode) {
    const ok = await confirmDelete(t("library.confirm_episode", "Really delete this episode?"));
    if (!ok) return;
    const { location, folder } = series;
    try {
      await apiSend("/api/library/delete", "POST", {
        folder,
        custom_path_id: location.custom_path_id,
        lang_folder: location.lang_folder,
        season: episode.seasonKey === "movie" ? "movie" : Number(episode.seasonKey),
        episode: episode.episode
      });
      showToast(t("library.deleted", "Deleted"));
      openSeries(folder);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function deleteTitle() {
    const { location, folder, details } = series;
    const ok = await confirmDelete(
      t("library.confirm_title", 'Really delete all of "{name}"?', {
        name: details.meta.title || folder
      })
    );
    if (!ok) return;
    try {
      await apiSend("/api/library/delete", "POST", {
        folder,
        custom_path_id: location.custom_path_id,
        lang_folder: location.lang_folder
      });
      showToast(t("library.deleted", "Deleted"));
      navigate("#/cards");
    } catch (error) {
      showToast(error.message);
    }
  }

  /* ===== Thumbnails in the background =====
     One at a time, only while the series view is up and the tab is visible.
     A frame is rendered from a random spot in the episode, avoiding black
     frames, then posted so the next visitor sees it immediately. */
  async function startThumbnailWorker() {
    thumbJob += 1;
    const job = thumbJob;
    const current = series;
    if (!current || !window.WebPlayer) return;
    for (const episode of current.episodes) {
      if (job !== thumbJob) return;
      if (episode.thumbnail || episode.thumbAttempted) continue;
      if (!WebPlayer.canPlayInBrowser(episode.file)) continue;
      while (document.hidden && job === thumbJob) {
        await new Promise((r) => setTimeout(r, 1000));
      }
      episode.thumbAttempted = true;
      let result = null;
      for (let attempt = 0; attempt < 2 && (!result || result.dark); attempt += 1) {
        result = await WebPlayer.captureFrame({
          url: fileUrl(current.location, current.folder, episode.path),
          name: episode.file,
          width: 480
        });
        if (job !== thumbJob) return;
      }
      if (!result || !result.blob) continue;
      try {
        const image = await blobToDataUrl(result.blob);
        await apiSend("/api/library/thumbnail", "POST", {
          folder: current.folder,
          path: episode.path,
          custom_path_id: current.location.custom_path_id,
          lang_folder: current.location.lang_folder,
          image
        });
        episode.thumbnail = true;
        episode.thumbVersion = Date.now();
        // even when the server keeps nothing (sidecars off), show it now
        episode.localThumb = image;
        updateEpisodeThumb(episode);
      } catch (error) {
        /* a missing cover is not worth a toast */
      }
    }
  }

  function updateEpisodeThumb(episode) {
    if (!series) return;
    const index = series.episodes.indexOf(episode);
    const card = seriesEl.querySelector(`.ep-card[data-index="${index}"]`);
    if (!card) return;
    const pending = card.querySelector("[data-pending]");
    const img = document.createElement("img");
    img.alt = "";
    img.src = episode.localThumb || thumbUrl(series.location, series.folder, episode.path, episode.thumbVersion);
    if (pending) pending.replaceWith(img);
    else card.querySelector(".ep-thumb").prepend(img);
    // a title without a poster borrows its first frame for the header too
    const poster = seriesEl.querySelector(".series-poster");
    if (poster && !poster.querySelector("img")) {
      const cover = document.createElement("img");
      cover.alt = "";
      cover.src = img.src;
      poster.appendChild(cover);
    }
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /* ===== Player ===== */
  const overlay = document.getElementById("playerOverlay");
  const video = document.getElementById("playerVideo");
  const statusEl = document.getElementById("playerStatus");
  const titleEl = document.getElementById("playerTitle");
  const subEl = document.getElementById("playerSub");
  const prevBtn = document.getElementById("playerPrev");
  const nextBtn = document.getElementById("playerNext");
  const nextUp = document.getElementById("playerNextUp");
  const nextUpText = document.getElementById("playerNextUpText");
  const nextUpCancel = document.getElementById("playerNextUpCancel");

  let player = null; // { controller, episode, index, lastSaved, saveTimer, countdown }

  function setStatus(text, isError) {
    if (!text) {
      statusEl.hidden = true;
      statusEl.textContent = "";
      statusEl.classList.remove("is-error");
      return;
    }
    statusEl.hidden = false;
    statusEl.classList.toggle("is-error", Boolean(isError));
    statusEl.textContent = text;
  }

  function describeStatus(kind, detail) {
    switch (kind) {
      case "preparing":
        return t("library.player_preparing", "Preparing stream...");
      case "remuxing":
        return t("library.player_remuxing", "Repacking Matroska to MP4 in your browser...");
      case "transcoding":
        return t("library.player_transcoding", "Transcoding on your GPU ({codec} → H.264)...", {
          codec: detail.codec || "video"
        });
      default:
        return "";
    }
  }

  function openPlayer(index) {
    if (!series) return;
    const episode = series.episodes[index];
    if (!episode) return;
    closePlayer(false);

    const { location, folder, details } = series;
    const resume =
      episode.progress && !episode.progress.watched && episode.progress.position > 5
        ? episode.progress.position
        : 0;

    titleEl.textContent = `${episodeCode(episode.seasonKey, episode)} · ${episodeTitle(episode, episode.seasonKey)}`;
    subEl.textContent = details.meta.title || folder;
    prevBtn.disabled = index <= 0;
    nextBtn.disabled = index >= series.episodes.length - 1;
    nextUp.hidden = true;
    setStatus("");
    openModal("playerOverlay");

    const url = fileUrl(location, folder, episode.path);
    const controller = WebPlayer.attach(video, {
      url,
      name: episode.file,
      startAt: resume,
      onStatus(kind, detail) {
        if (kind === "error") return;
        if (kind === "native") return;
        if (kind === "no-audio") {
          showToast(`${detail.codec}: no audio in this browser`);
          return;
        }
        setStatus(describeStatus(kind, detail));
      },
      onError(error) {
        const text =
          error && error.message === "unsupported"
            ? t(
                "library.player_unsupported",
                "This browser can neither play nor transcode {codec}. The file can still be downloaded.",
                { codec: error.codec || "this codec" }
              )
            : t("library.player_failed", "Playback failed: {error}", {
                error: (error && error.message) || String(error)
              });
        setStatus(text, true);
      }
    });
    player = { controller, episode, index, lastSaved: resume, saveTimer: null, countdown: null };
    controller.ready
      .then(() => {
        if (player && player.controller === controller) {
          video.play().catch(() => {});
        }
      })
      .catch((error) => {
        if (player && player.controller === controller && !statusEl.classList.contains("is-error")) {
          controller.destroy();
          const text =
            error && error.message === "unsupported"
              ? t(
                  "library.player_unsupported",
                  "This browser can neither play nor transcode {codec}. The file can still be downloaded.",
                  { codec: error.codec || "this codec" }
                )
              : t("library.player_failed", "Playback failed: {error}", {
                  error: (error && error.message) || String(error)
                });
          setStatus(text, true);
        }
      });
  }

  function saveProgress(force) {
    if (!player || !series) return;
    const position = video.currentTime;
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    if (!force && Math.abs(position - player.lastSaved) < 5) return;
    if (!duration && !force) return;
    player.lastSaved = position;
    const episode = player.episode;
    postProgress(episode, { position, duration })
      .then(() => {
        if (series && series.episodes.includes(episode)) {
          const card = seriesEl.querySelector(`.ep-card[data-index="${series.episodes.indexOf(episode)}"]`);
          if (card) card.outerHTML = renderEpisode(series.location, series.folder, episode, series.episodes.indexOf(episode));
        }
      })
      .catch(() => {});
  }

  video.addEventListener("timeupdate", () => {
    if (!player) return;
    if (!statusEl.hidden && !statusEl.classList.contains("is-error") && video.currentTime > 0.5) {
      setStatus("");
    }
    saveProgress(false);
  });
  video.addEventListener("playing", () => {
    if (!statusEl.classList.contains("is-error")) setStatus("");
  });
  video.addEventListener("pause", () => saveProgress(true));
  video.addEventListener("ended", () => {
    if (!player) return;
    const episode = player.episode;
    postProgress(episode, {
      position: video.duration || episode.progress?.duration || 0,
      duration: video.duration || 0,
      watched: true
    })
      .then(() => renderSeries())
      .catch(() => {});
    if (player.index < series.episodes.length - 1) startCountdown();
  });

  function startCountdown() {
    let seconds = 8;
    nextUp.hidden = false;
    const tick = () => {
      nextUpText.textContent = t("library.next_up", "Next episode in {seconds}s", { seconds });
      if (seconds <= 0) {
        nextUp.hidden = true;
        openPlayer(player.index + 1);
        return;
      }
      seconds -= 1;
      player.countdown = setTimeout(tick, 1000);
    };
    tick();
  }

  nextUpCancel.addEventListener("click", () => {
    if (player && player.countdown) clearTimeout(player.countdown);
    nextUp.hidden = true;
  });
  prevBtn.addEventListener("click", () => player && openPlayer(player.index - 1));
  nextBtn.addEventListener("click", () => player && openPlayer(player.index + 1));

  function closePlayer(closeModalToo) {
    if (!player) return;
    if (player.countdown) clearTimeout(player.countdown);
    saveProgress(true);
    player.controller.destroy();
    player = null;
    nextUp.hidden = true;
    setStatus("");
    if (closeModalToo !== false) closeModal("playerOverlay");
  }

  overlay.addEventListener("modal-closed", () => closePlayer(false));
  overlay.querySelector("[data-close-modal]").addEventListener("click", () => closePlayer(false));

  // Keyboard: the video element handles space/arrows once focused; make sure
  // it is focused when the modal opens so that works from the first key.
  overlay.addEventListener("transitionend", () => {
    if (overlay.classList.contains("open")) video.focus();
  });
  document.addEventListener("keydown", (event) => {
    if (!player || !overlay.classList.contains("open")) return;
    if (event.target !== video && event.target.closest("button")) return;
    if (event.key === "f" || event.key === "F") {
      if (document.fullscreenElement) document.exitFullscreen();
      else if (video.requestFullscreen) video.requestFullscreen();
    } else if (event.key === "n" || event.key === "N") {
      if (!nextBtn.disabled) openPlayer(player.index + 1);
    }
  });
  window.addEventListener("beforeunload", () => {
    if (!player || !series) return;
    const payload = JSON.stringify({
      folder: series.folder,
      path: player.episode.path,
      custom_path_id: series.location.custom_path_id,
      lang_folder: series.location.lang_folder,
      position: video.currentTime,
      duration: Number.isFinite(video.duration) ? video.duration : 0
    });
    navigator.sendBeacon("/api/library/progress", new Blob([payload], { type: "application/json" }));
  });

  /* ===== Tree view (the original) ===== */
  async function loadTree() {
    tree.innerHTML = message(t("common.loading", "Loading..."));
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
          <div class="library-children" data-level="types"></div>
        </div>`
      )
      .join("");
  }

  function renderTitles(titles) {
    return titles
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
              <button class="icon-btn" data-open="series" title="${esc(t("library.view_cards", "Cards"))}">&#9636;</button>
              ${isAdmin ? `<button class="icon-btn" data-delete="title" title="${t("common.delete", "Delete")}">&times;</button>` : ""}
            </div>
          </div>
          <div class="library-children" data-level="title"></div>
        </div>`
      )
      .join("");
  }

  async function loadTypes(node) {
    const location = locations[Number(node.dataset.location)];
    const container = node.querySelector('[data-level="types"]');
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

    const seriesTitles = titles
      .filter((entry) => (entry.categories || []).includes("series"))
      .map((entry) => entry.folder);
    const movies = titles
      .filter((entry) => (entry.categories || []).includes("movies"))
      .map((entry) => entry.folder);

    const sections = [
      { key: "series", label: t("library.series", "Series"), titles: seriesTitles },
      { key: "movies", label: t("library.movies", "Movies"), titles: movies }
    ].filter((section) => section.titles.length);

    container.innerHTML = sections
      .map(
        (section) => `
        <div class="library-node" data-type="${esc(section.key)}">
          <div class="library-row" data-toggle="type">
            <div class="library-row-left">
              <span class="arrow">&#9654;</span>
              <span class="library-name">${esc(section.label)}</span>
            </div>
            <div class="library-row-right">
              <span class="library-sub">${section.titles.length}</span>
            </div>
          </div>
          <div class="library-children" data-level="titles">${renderTitles(section.titles)}</div>
        </div>`
      )
      .join("");
  }

  async function loadTitle(node) {
    const locationNode = node.closest("[data-location]");
    const location = locations[Number(locationNode.dataset.location)];
    const container = node.querySelector('[data-level="title"]');
    const folder = node.dataset.folder;
    container.innerHTML = message(t("common.loading", "Loading..."));

    let details;
    try {
      const query = locationQuery(location);
      details = await apiFetch(
        `/api/library/title?folder=${encodeURIComponent(folder)}${query ? `&${query}` : ""}`
      );
    } catch (error) {
      container.innerHTML = message(t("common.failed", "Failed"));
      return;
    }

    const summary = node.querySelector("[data-summary]");
    if (summary) {
      summary.textContent = `${details.total_episodes} ${t("library.episodes", "ep")} | ${formatSize(details.total_size)}`;
    }

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
          .map((episode) => {
            const done = episode.progress && episode.progress.watched;
            return `
            <div class="library-episode" data-episode="${episode.episode}" data-path="${esc(episode.path)}">
              <span class="library-ep-num">E${String(episode.episode).padStart(3, "0")}${done ? " &#10003;" : ""}</span>
              <span class="library-ep-file" title="${esc(episode.file)}">${esc(episode.file)}</span>
              <span class="library-ep-size">${formatSize(episode.size)}</span>
              ${isAdmin ? `<button class="icon-btn" data-delete="episode" title="${t("common.delete", "Delete")}">&times;</button>` : ""}
            </div>`;
          })
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
                ${isAdmin ? `<button class="icon-btn" data-delete="season" title="${t("common.delete", "Delete")}">&times;</button>` : ""}
              </div>
            </div>
            <div class="library-children">${rows}</div>
          </div>`;
      })
      .join("");
  }

  const LOADERS = { location: loadTypes, title: loadTitle };

  tree.addEventListener("click", async (event) => {
    if (event.target.closest("[data-delete]")) return;
    const open = event.target.closest("[data-open]");
    if (open) {
      event.stopPropagation();
      const titleNode = open.closest("[data-folder]");
      const locationNode = open.closest("[data-location]");
      locationIndex = Number(locationNode.dataset.location);
      navigate(`#/series/${locationIndex}/${encodeURIComponent(titleNode.dataset.folder)}`);
      return;
    }
    const episodeRow = event.target.closest(".library-episode");
    if (episodeRow && episodeRow.dataset.path) {
      const titleNode = episodeRow.closest("[data-folder]");
      const locationNode = episodeRow.closest("[data-location]");
      locationIndex = Number(locationNode.dataset.location);
      window.history.replaceState(
        null,
        "",
        `#/series/${locationIndex}/${encodeURIComponent(titleNode.dataset.folder)}`
      );
      openSeries(titleNode.dataset.folder, { play: episodeRow.dataset.path });
      return;
    }

    const row = event.target.closest("[data-toggle]");
    if (!row) return;

    const node = row.parentElement;
    const children = row.nextElementSibling;
    const arrow = row.querySelector(".arrow");
    const expanding = !children.classList.contains("expanded");

    if (row.dataset.toggle === "type") {
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

  function confirmMessage(kind, node) {
    const titleNode = node.closest("[data-folder]");
    const name = titleNode ? titleNode.dataset.folder : "";
    if (kind === "title") {
      return t("library.confirm_title", 'Really delete all of "{name}"?', { name });
    }
    if (kind === "season") {
      const season = node.closest("[data-season]").dataset.season;
      if (season === "movie") {
        return t("library.confirm_movies", 'Really delete all movies of "{name}"?', {
          name
        });
      }
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

    if (!(await confirmDelete(confirmMessage(kind, button)))) return;

    const payload = {
      folder: titleNode.dataset.folder,
      custom_path_id: location.custom_path_id,
      lang_folder: location.lang_folder
    };
    if (kind !== "title") {
      const season = button.closest("[data-season]").dataset.season;
      payload.season = season === "movie" ? season : Number(season);
    }
    if (kind === "episode") {
      payload.episode = Number(button.closest("[data-episode]").dataset.episode);
    }

    try {
      await apiSend("/api/library/delete", "POST", payload);
      showToast(t("library.deleted", "Deleted"));
      await loadTree();
    } catch (error) {
      showToast(error.message);
    }
  });

  /* ===== Boot ===== */
  async function boot() {
    const ok = await loadLocations();
    if (!ok) {
      cardsEl.innerHTML = message(t("library.empty", "No downloaded content found."));
      return;
    }
    route();
  }

  refreshBtn.addEventListener("click", async () => {
    await loadLocations();
    route();
  });
  window.addEventListener("hashchange", route);
  boot();
})();
