/* Home page: site switch, search, browse rows and the download modal. */

(function () {
  const el = (id) => document.getElementById(id);

  const searchInput = el("searchInput");
  const searchBtn = el("searchBtn");
  const randomBtn = el("randomBtn");
  const searchSpinner = el("searchSpinner");
  const resultsGrid = el("results");
  const browse = el("browse");
  const genreBar = el("genreBar");
  const genreList = el("genreList");
  const genreMore = el("genreMore");
  const genreMoreBtn = el("genreMoreBtn");

  const seriesOverlay = el("seriesOverlay");
  const seriesLoading = el("seriesLoading");
  const seriesContent = el("seriesContent");
  const languageSelect = el("languageSelect");
  const providerSelect = el("providerSelect");
  const languageProviderRow = el("languageProviderRow");
  const mangaFireRow = el("mangaFireRow");
  const customPathRow = el("customPathRow");
  const customPathSelect = el("customPathSelect");
  const autosyncRow = el("autosyncRow");
  const autosyncExclude = el("autosyncExclude");
  const accordion = el("seasonAccordion");
  const episodeSpinner = el("episodeSpinner");
  const selectAll = el("selectAll");
  const downloadSelectedBtn = el("downloadSelectedBtn");
  const downloadAllBtn = el("downloadAllBtn");

  const thumb = el("segmentedThumb");
  const siteButtons = Array.from(document.querySelectorAll(".segmented-btn"));

  // Browse rows are cached per process on the server, refresh occasionally here
  const BROWSE_REFRESH_MS = 300000;

  const SEARCH_PLACEHOLDERS = {
    aniworld: "Search AniWorld...",
    sto: "Search SerienStream...",
    burningseries: "Search BurningSeries...",
    megakino: "Search MegaKino...",
    cineby: "Search Cineby...",
    kinox: "Search Kinox...",
    filmpalast: "Search FilmPalast...",
    htv: "Search Hanime...",
    mangafire: "Search MangaFire..."
  };

  const LANGUAGE_BADGES = {
    "German Dub": { flags: ["de"], text: "Dub", css: "badge-german-dub" },
    "German Sub": { flags: ["jp", "de"], text: "Sub", css: "badge-german-sub" },
    "English Dub": { flags: ["gb"], text: "Dub", css: "badge-english-dub" },
    "English Sub": { flags: ["jp", "gb"], text: "Sub", css: "badge-english-sub" },
    Japanese: { flags: ["jp"], text: "Dub", css: "badge-german-dub" }
  };

  let currentSite = "aniworld";
  let downloadedFolders = [];
  let customPaths = [];

  // Open series state
  let openToken = 0;
  let seriesUrl = "";
  let seriesTitle = "";
  let seasons = [];
  let episodeCache = {};
  let episodeLoads = {};
  let availableProviders = null;

  const isHanime = (url) => url.includes("hanime.tv/");
  const isMangaFire = (url) => url.includes("mangafire.to/");

  /* ===== Site switch ===== */
  function moveThumb() {
    const active = siteButtons.find((btn) => btn.classList.contains("active"));
    if (!active || !thumb) return;
    thumb.style.width = `${active.offsetWidth}px`;
    // offsetLeft already starts inside the track padding, same origin as the
    // thumb, so it goes straight in without correcting for the padding
    thumb.style.transform = `translateX(${active.offsetLeft}px)`;
  }

  function switchSite(site) {
    currentSite = site;
    siteButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.site === site));
    moveThumb();
    searchInput.placeholder = SEARCH_PLACEHOLDERS[site] || "Search...";
    randomBtn.hidden = site !== "aniworld";
    resultsGrid.innerHTML = "";
    searchInput.value = "";
    resetGenre();
    updateGenreBar();
    showBrowseRows();
  }

  siteButtons.forEach((btn) => {
    btn.addEventListener("click", () => switchSite(btn.dataset.site));
  });
  window.addEventListener("resize", moveThumb);
  // The buttons are measured before Inter is done loading, so they grow a
  // couple of pixels afterwards and the thumb would stay at the old width
  if (document.fonts) document.fonts.ready.then(moveThumb);

  /* ===== Browse rows ===== */
  const browseState = {};

  function visibleSections() {
    return Array.from(browse.querySelectorAll(".browse-section")).filter((section) =>
      section.dataset.sites.split(",").includes(currentSite)
    );
  }

  function showBrowseRows() {
    browse.hidden = false;
    browse.querySelectorAll(".browse-section").forEach((section) => {
      section.hidden = !section.dataset.sites.split(",").includes(currentSite);
    });
    visibleSections().forEach(loadRow);
  }

  async function loadRow(section, force) {
    const key = section.dataset.row;
    const state = browseState[key] || (browseState[key] = { loadedAt: 0, pending: null });
    if (state.pending) return state.pending;
    if (!force && Date.now() - state.loadedAt < BROWSE_REFRESH_MS) return;

    const grid = section.querySelector(".browse-grid");
    if (!grid.children.length) {
      grid.innerHTML = `<div class="empty-state">${t("common.loading", "Loading...")}</div>`;
    }

    state.pending = apiFetch(`/api/${key.replace(/_/g, "-")}`)
      .then((data) => {
        state.loadedAt = Date.now();
        renderCards(grid, data.results || []);
      })
      .catch(() => {
        grid.innerHTML = `<div class="empty-state">${t("common.failed", "Failed")}</div>`;
      })
      .finally(() => {
        state.pending = null;
      });
    return state.pending;
  }

  function normalizeTitle(value) {
    return decodeEntities(value || "")
      .replace(/[\u2018\u2019\u201C\u201D]/g, "'")
      .toLowerCase()
      .trim();
  }

  function isDownloaded(title) {
    const normalized = normalizeTitle(title);
    if (!normalized) return false;
    return downloadedFolders.some((folder) => {
      const name = normalizeTitle(folder);
      return name === normalized || name.startsWith(`${normalized} (`);
    });
  }

  function renderCards(grid, items) {
    if (!items.length) {
      grid.innerHTML = `<div class="empty-state">${t("index.no_results", "No results found.")}</div>`;
      return;
    }

    grid.innerHTML = items
      .map((item) => {
        const title = decodeEntities(item.title);
        const badge = isDownloaded(title)
          ? '<span class="downloaded-badge">&#10003;</span>'
          : "";
        const subtitle = item.genre
          ? `<div class="subtitle">${esc(item.genre)}</div>`
          : "";
        return `
          <div class="poster-card" data-url="${esc(item.url)}">
            ${badge}
            <img src="${esc(item.poster_url || "")}" alt="" loading="lazy" />
            <div class="info">
              <div class="title" title="${esc(title)}">${esc(title)}</div>
              ${subtitle}
            </div>
          </div>`;
      })
      .join("");
  }

  document.addEventListener("click", (event) => {
    const card = event.target.closest(".poster-card");
    if (card && card.dataset.url) openSeries(card.dataset.url);
  });

  /* ===== Genres =====
     Only aniworld has genre pages. Picking one takes over the results grid so
     the chips stay reachable and you can hop straight to the next genre. */
  let genresLoaded = false;
  let activeGenre = null;
  let genrePage = 1;
  let genreItems = [];
  let genreLoading = false;

  function updateGenreBar() {
    genreBar.hidden = currentSite !== "aniworld";
    if (!genreBar.hidden) loadGenres();
  }

  async function loadGenres() {
    if (genresLoaded) return;
    genresLoaded = true;
    try {
      const data = await apiFetch("/api/genres");
      genreList.innerHTML = (data.genres || [])
        .map(
          (genre) =>
            `<button type="button" class="genre-chip" role="listitem"
               data-slug="${esc(genre.slug)}">${esc(genre.name)}</button>`
        )
        .join("");
    } catch (error) {
      genresLoaded = false;
      genreBar.hidden = true;
    }
  }

  function resetGenre() {
    activeGenre = null;
    genreItems = [];
    genreMore.hidden = true;
    genreList
      .querySelectorAll(".genre-chip.active")
      .forEach((chip) => chip.classList.remove("active"));
  }

  function clearGenre() {
    resetGenre();
    resultsGrid.innerHTML = "";
    showBrowseRows();
  }

  genreList.addEventListener("click", (event) => {
    const chip = event.target.closest(".genre-chip");
    if (!chip) return;
    // clicking the open genre again goes back to the browse rows
    if (chip.dataset.slug === activeGenre) {
      clearGenre();
      return;
    }
    resetGenre();
    activeGenre = chip.dataset.slug;
    chip.classList.add("active");
    searchInput.value = "";
    browse.hidden = true;
    resultsGrid.innerHTML = "";
    loadGenrePage(1);
  });

  genreMoreBtn.addEventListener("click", () => loadGenrePage(genrePage + 1));

  async function loadGenrePage(page) {
    if (genreLoading || !activeGenre) return;
    const slug = activeGenre;
    genreLoading = true;
    genreMoreBtn.disabled = true;
    if (page === 1) searchSpinner.classList.add("active");

    try {
      const data = await apiFetch(
        `/api/genre?slug=${encodeURIComponent(slug)}&page=${page}`
      );
      // a slow page 1 can land after the user already picked another genre
      if (slug !== activeGenre) return;
      genrePage = page;
      genreItems = genreItems.concat(data.results || []);
      renderCards(resultsGrid, genreItems);
      genreMore.hidden = !data.has_more;
    } catch (error) {
      showToast(`${t("browse.genre_failed", "Could not load genre")}: ${error.message}`);
      if (page === 1) clearGenre();
    } finally {
      genreLoading = false;
      genreMoreBtn.disabled = false;
      searchSpinner.classList.remove("active");
    }
  }

  /* ===== Search ===== */
  async function doSearch() {
    const keyword = searchInput.value.trim();
    if (!keyword) {
      clearGenre();
      return;
    }

    resetGenre();
    searchBtn.disabled = true;
    searchSpinner.classList.add("active");
    resultsGrid.innerHTML = "";
    browse.hidden = true;

    try {
      const data = await apiSend("/api/search", "POST", { keyword, site: currentSite });
      renderCards(resultsGrid, data.results || []);
      loadMissingPosters();
    } catch (error) {
      showToast(`${t("index.search_failed", "Search failed")}: ${error.message}`);
    } finally {
      searchBtn.disabled = false;
      searchSpinner.classList.remove("active");
    }
  }

  // serienstream search gives no posters, fetch them per card
  function loadMissingPosters() {
    resultsGrid.querySelectorAll(".poster-card").forEach(async (card) => {
      const image = card.querySelector("img");
      if (image.getAttribute("src")) return;
      try {
        const data = await apiFetch(
          `/api/series?url=${encodeURIComponent(card.dataset.url)}`
        );
        if (data.poster_url) image.src = data.poster_url;
      } catch (e) {
        /* a missing poster is not worth reporting */
      }
    });
  }

  searchBtn.addEventListener("click", doSearch);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") doSearch();
  });

  randomBtn.addEventListener("click", async () => {
    randomBtn.disabled = true;
    try {
      const data = await apiFetch(`/api/random?site=${currentSite}`);
      openSeries(data.url);
    } catch (error) {
      showToast(error.message);
    } finally {
      randomBtn.disabled = false;
    }
  });

  /* ===== Custom paths ===== */
  async function loadCustomPaths() {
    try {
      const data = await apiFetch("/api/custom-paths");
      customPaths = data.paths || [];
    } catch (e) {
      customPaths = [];
    }

    customPathRow.hidden = customPaths.length === 0;
    customPathSelect.innerHTML = `<option value="">${t("index.default", "Default")}</option>`;
    customPaths.forEach((path) => {
      const option = document.createElement("option");
      option.value = String(path.id);
      option.textContent = path.name;
      customPathSelect.appendChild(option);
    });

    // Pre-select a path that was marked as the default for this site
    const preferred = customPaths.find((path) =>
      (path.default_sites || "").split(",").includes(currentSite)
    );
    customPathSelect.value = preferred ? String(preferred.id) : "";
  }

  async function loadDownloadedFolders() {
    try {
      const data = await apiFetch("/api/downloaded-folders");
      downloadedFolders = data.folders || [];
    } catch (e) {
      downloadedFolders = [];
    }
  }

  /* ===== Series modal ===== */
  // Skeleton while loading, real content only once everything is in
  function showSkeleton(loading) {
    seriesLoading.hidden = !loading;
    seriesContent.hidden = loading;
  }

  function resetModal() {
    el("seriesPoster").removeAttribute("src");
    el("seriesTitle").textContent = "";
    el("seriesGenres").textContent = "";
    el("seriesYear").textContent = "";
    el("seriesDesc").textContent = "";
    accordion.innerHTML = "";
    selectAll.checked = false;
    episodeCache = {};
    episodeLoads = {};
    availableProviders = null;
  }

  function rebuildLanguageOptions() {
    const languages = window.SITE_LANGUAGES[currentSite] || window.SITE_LANGUAGES.aniworld;
    languageSelect.innerHTML = languages
      .map((language) => `<option value="${esc(language)}">${esc(language)}</option>`)
      .join("");
    if (languages.includes(window.DEFAULT_LANGUAGE)) {
      languageSelect.value = window.DEFAULT_LANGUAGE;
    }
  }

  function fillProviderSelect(providers) {
    providerSelect.innerHTML = providers
      .map((name) => `<option value="${esc(name)}">${esc(name)}</option>`)
      .join("");
    providerSelect.value = providers.includes("VOE") ? "VOE" : providers[0] || "";
  }

  function updateProviderSelect() {
    const forLanguage = availableProviders && availableProviders[languageSelect.value];
    if (forLanguage && forLanguage.length) {
      fillProviderSelect(forLanguage);
    } else if (currentSite !== "megakino") {
      fillProviderSelect(window.STATIC_PROVIDERS);
    } else {
      providerSelect.innerHTML = "";
    }
  }

  // Hide language options the title does not actually offer
  function restrictLanguages() {
    if (!availableProviders) return;
    const offered = Object.keys(availableProviders);
    if (!offered.length) return;

    const previous = languageSelect.value;
    Array.from(languageSelect.options).forEach((option) => {
      option.hidden = !offered.includes(option.value);
    });

    const visible = Array.from(languageSelect.options).filter((option) => !option.hidden);
    if (visible.length && !visible.some((option) => option.value === previous)) {
      languageSelect.value = visible[0].value;
    }
  }

  async function fetchProviders(episodeUrl) {
    try {
      const data = await apiFetch(`/api/providers?url=${encodeURIComponent(episodeUrl)}`);
      availableProviders = data.providers || null;
      restrictLanguages();
      updateProviderSelect();
    } catch (e) {
      // keep the static provider list when the probe fails
    }
  }

  languageSelect.addEventListener("change", updateProviderSelect);

  async function openSeries(url) {
    const token = ++openToken;
    seriesUrl = url;
    seriesTitle = "";
    resetModal();
    showSkeleton(true);
    openModal("seriesOverlay");

    const hanime = isHanime(url);
    const manga = isMangaFire(url);
    languageProviderRow.hidden = hanime || manga;
    mangaFireRow.hidden = !manga;
    if (!hanime && !manga) {
      rebuildLanguageOptions();
      fillProviderSelect(currentSite === "megakino" ? [] : window.STATIC_PROVIDERS);
    }
    loadCustomPaths();
    loadAutosyncExclusion(url);

    try {
      const [series, seasonData] = await Promise.all([
        apiFetch(`/api/series?url=${encodeURIComponent(url)}`),
        apiFetch(`/api/seasons?url=${encodeURIComponent(url)}`)
      ]);
      if (token !== openToken) return;

      seriesTitle = series.title || "Unknown";
      el("seriesTitle").innerHTML = `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(seriesTitle)}</a>`;
      if (series.poster_url) el("seriesPoster").src = series.poster_url;
      el("seriesGenres").textContent = (series.genres || []).join(", ");
      el("seriesYear").textContent = series.release_year || "";
      el("seriesDesc").textContent = series.description || "";

      seasons = seasonData.seasons || [];
      // Wait for the first season's episodes so the list is populated on reveal
      const firstEpisodes = await buildAccordion(token);
      if (token !== openToken) return;

      // The provider probe narrows the language/provider selects, so resolve it
      // before revealing or the dropdowns would visibly change afterwards
      if (firstEpisodes.length && !hanime && !manga) {
        await fetchProviders(firstEpisodes[0].url);
        if (token !== openToken) return;
      }

      showSkeleton(false);
    } catch (error) {
      if (token !== openToken) return;
      showSkeleton(false);
      // Leaving the modal blank would look like a hang
      el("seriesTitle").textContent = t("index.load_failed", "Failed to load title");
      el("seriesDesc").textContent = error.message;
      accordion.innerHTML = "";
      episodeSpinner.classList.remove("active");
      showToast(`${t("index.load_failed", "Failed to load title")}: ${error.message}`);
    }
  }

  // Only meaningful for aniworld titles, that is all Auto-Sync looks at
  async function loadAutosyncExclusion(url) {
    if (!autosyncRow) return;
    autosyncRow.hidden = true;
    if (!window.AUTOSYNC_ENABLED || !url.includes("aniworld.to/")) return;
    try {
      const data = await apiFetch(
        `/api/autosync/excluded?url=${encodeURIComponent(url)}`
      );
      autosyncExclude.checked = Boolean(data.excluded);
      autosyncRow.hidden = false;
    } catch (e) {
      autosyncRow.hidden = true;
    }
  }

  if (autosyncExclude) {
    autosyncExclude.addEventListener("change", async () => {
      try {
        await apiSend("/api/autosync/excluded", "POST", {
          series_url: seriesUrl,
          title: seriesTitle,
          excluded: autosyncExclude.checked
        });
        showToast(
          autosyncExclude.checked
            ? t("index.autosync_excluded", "Excluded from Auto-Sync")
            : t("index.autosync_included", "Included in Auto-Sync again")
        );
      } catch (error) {
        showToast(error.message);
        autosyncExclude.checked = !autosyncExclude.checked;
      }
    });
  }

  function seasonLabel(season, count) {
    const shown = typeof count === "number" ? count : season.episode_count;
    if (currentSite === "mangafire") {
      return `${t("index.chapter", "Chapter")} ${season.season_number}`;
    }
    const name = season.are_movies
      ? t("index.movies", "Movies")
      : `${t("index.season", "Season")} ${season.season_number}`;
    return typeof shown === "number" ? `${name} (${shown})` : name;
  }

  // Returns the first season's episodes so the caller can wait for them
  async function buildAccordion(token) {
    accordion.innerHTML = "";
    if (!seasons.length) {
      accordion.innerHTML = `<div class="accordion-message">${t("index.no_episodes", "No episodes available.")}</div>`;
      return [];
    }

    seasons.forEach((season, index) => {
      const section = document.createElement("div");
      section.className = "season-section";
      section.dataset.index = String(index);
      section.innerHTML = `
        <div class="season-header${index === 0 ? " expanded" : ""}">
          <span class="season-label"><span class="arrow">&#9654;</span> ${esc(seasonLabel(season))}</span>
          <label class="checkbox" style="margin:0">
            <input type="checkbox" data-season-all="${index}" />
            <span>${t("index.all", "All")}</span>
          </label>
        </div>
        <div class="season-body${index === 0 ? " expanded" : ""}" id="seasonBody-${index}">
          <div class="accordion-message">${t("index.loading_episodes", "Loading episodes...")}</div>
        </div>`;
      accordion.appendChild(section);
    });

    return loadEpisodes(0, token);
  }

  function episodesUrl(season) {
    let url = `/api/episodes?url=${encodeURIComponent(season.url || seriesUrl)}`;
    // HanimeTV seasons carry no URL of their own, and MangaFire needs the series
    if (!season.url || currentSite === "mangafire") {
      url += `&series_url=${encodeURIComponent(seriesUrl)}`;
    }
    return url;
  }

  function loadEpisodes(index, token = openToken) {
    if (episodeCache[index]) return Promise.resolve(episodeCache[index]);
    if (episodeLoads[index]) return episodeLoads[index];

    const season = seasons[index];
    const body = el(`seasonBody-${index}`);
    if (!season || !body) return Promise.resolve([]);

    episodeLoads[index] = apiFetch(episodesUrl(season))
      .then((data) => {
        if (token !== openToken) return [];
        const episodes = data.episodes || [];
        episodeCache[index] = episodes;
        renderEpisodes(index, episodes);
        return episodes;
      })
      .catch(() => {
        if (token === openToken) {
          body.innerHTML = `<div class="accordion-message">${t("index.episodes_failed", "Failed to load episodes.")}</div>`;
        }
        return [];
      })
      .finally(() => {
        delete episodeLoads[index];
      });

    return episodeLoads[index];
  }

  function renderBadges(labels) {
    if (!labels || !labels.length) return "";
    const badges = labels
      .map((label) => {
        const badge = LANGUAGE_BADGES[label];
        if (!badge) {
          return `<span class="lang-badge">${esc(label)}</span>`;
        }
        const flags = badge.flags
          .map((flag) => `<img src="/static/flags/${flag}.svg" alt="" aria-hidden="true" />`)
          .join("");
        return `<span class="lang-badge ${badge.css}" title="${esc(label)}">${flags}${badge.text}</span>`;
      })
      .join("");
    return `<span class="lang-badges">${badges}</span>`;
  }

  function renderEpisodes(index, episodes) {
    const body = el(`seasonBody-${index}`);
    const section = accordion.querySelector(`[data-index="${index}"]`);
    if (!body || !section) return;

    if (!episodes.length) {
      body.innerHTML = `<div class="accordion-message">${t("index.no_episodes", "No episodes available.")}</div>`;
      return;
    }

    const manga = currentSite === "mangafire";
    body.innerHTML = episodes
      .map((episode) => {
        const name = manga
          ? `${t("index.page", "Page")} ${episode.page_number}`
          : episode.title_en || episode.title_de;
        const title = name
          ? `<span class="ep-title">${esc(name)}</span>`
          : `<span class="ep-title ep-title-missing">${t("index.not_available", "[Not available]")}</span>`;
        const done = episode.downloaded ? '<span class="ep-done">&#10003;</span>' : "";
        const value = manga
          ? `${episode.chapter_url || episode.url}##${episode.page_number}`
          : episode.url;
        const extra = manga
          ? ` data-chapter-url="${esc(episode.chapter_url || episode.url)}" data-page="${episode.page_number}"`
          : "";

        return `
          <div class="episode-item">
            <input type="checkbox" value="${esc(value)}" data-season="${index}"${extra} />
            <span class="ep-num">${manga ? "P" : "E"}${episode.episode_number}</span>
            ${done}
            <div class="ep-main">${title}${renderBadges(episode.available_languages)}</div>
          </div>`;
      })
      .join("");

    // Refresh the header now that the real episode count is known
    const label = section.querySelector(".season-label");
    const allDone = episodes.every((episode) => episode.downloaded);
    label.innerHTML =
      `<span class="arrow">&#9654;</span> ${esc(seasonLabel(seasons[index], episodes.length))}` +
      (allDone ? ' <span class="ep-done">&#10003;</span>' : "");
  }

  accordion.addEventListener("click", async (event) => {
    if (event.target.closest(".checkbox")) return;
    const header = event.target.closest(".season-header");
    if (!header) return;

    const section = header.closest(".season-section");
    const index = Number(section.dataset.index);
    const body = section.querySelector(".season-body");
    if (!body.classList.contains("expanded") && !episodeCache[index]) {
      await loadEpisodes(index);
    }
    header.classList.toggle("expanded");
    body.classList.toggle("expanded");
  });

  accordion.addEventListener("change", async (event) => {
    const seasonAll = event.target.dataset.seasonAll;
    if (seasonAll !== undefined) {
      const index = Number(seasonAll);
      if (!episodeCache[index]) await loadEpisodes(index);
      el(`seasonBody-${index}`)
        .querySelectorAll("input[type=checkbox]")
        .forEach((box) => {
          box.checked = event.target.checked;
        });
    }
    syncSelectAll();
  });

  function syncSelectAll() {
    const boxes = accordion.querySelectorAll(".episode-item input[type=checkbox]");
    selectAll.checked = boxes.length > 0 && Array.from(boxes).every((box) => box.checked);
  }

  selectAll.addEventListener("change", async () => {
    if (selectAll.checked) await loadAllSeasons();
    accordion.querySelectorAll("input[type=checkbox]").forEach((box) => {
      box.checked = selectAll.checked;
    });
  });

  function loadAllSeasons() {
    return Promise.all(seasons.map((_, index) => loadEpisodes(index)));
  }

  /* ===== Download ===== */
  function selector(all) {
    return all
      ? ".episode-item input[type=checkbox]"
      : ".episode-item input[type=checkbox]:checked";
  }

  function collectEpisodes(all) {
    const boxes = Array.from(accordion.querySelectorAll(selector(all)));
    if (currentSite !== "mangafire") return boxes.map((box) => box.value);

    // MangaFire downloads whole chapters with a page selection
    const chapters = new Map();
    boxes.forEach((box) => {
      const chapter = box.dataset.chapterUrl;
      const page = Number(box.dataset.page || 0);
      if (!chapter || !page) return;
      if (!chapters.has(chapter)) chapters.set(chapter, new Set());
      chapters.get(chapter).add(page);
    });
    return Array.from(chapters.entries()).map(([url, pages]) => ({
      url,
      series_url: seriesUrl,
      selected_pages: Array.from(pages).sort((a, b) => a - b)
    }));
  }

  async function startDownload(all) {
    if (all) {
      episodeSpinner.classList.add("active");
      await loadAllSeasons();
      episodeSpinner.classList.remove("active");
    }

    const episodes = collectEpisodes(all);
    if (!episodes.length) {
      showToast(
        all
          ? t("index.no_episodes", "No episodes available.")
          : t("index.no_episodes_selected", "No episodes selected.")
      );
      return;
    }

    const hanime = isHanime(seriesUrl);
    const manga = isMangaFire(seriesUrl);
    const body = {
      episodes,
      title: seriesTitle,
      series_url: seriesUrl,
      language: hanime ? "Japanese" : manga ? "MangaFire" : languageSelect.value,
      provider: hanime ? "HanimeTV" : manga ? "MangaFire" : providerSelect.value
    };
    if (manga) body.mangafire_format = el("mangaFireFormat").value;
    if (customPathSelect.value) body.custom_path_id = Number(customPathSelect.value);

    downloadAllBtn.disabled = true;
    downloadSelectedBtn.disabled = true;
    try {
      await apiSend("/api/download", "POST", body);
      showToast(t("index.queued", "Added to download queue"));
      if (window.refreshQueue) window.refreshQueue();
    } catch (error) {
      showToast(error.message);
    } finally {
      downloadAllBtn.disabled = false;
      downloadSelectedBtn.disabled = false;
    }
  }

  downloadSelectedBtn.addEventListener("click", () => startDownload(false));
  downloadAllBtn.addEventListener("click", () => startDownload(true));

  seriesOverlay.addEventListener("modal-closed", () => {
    openToken += 1;
  });

  /* ===== Boot ===== */
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) visibleSections().forEach((section) => loadRow(section));
  });

  loadDownloadedFolders().then(() => {
    switchSite("aniworld");
  });
})();
