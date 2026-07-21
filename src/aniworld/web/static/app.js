const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const searchSpinner = document.getElementById("searchSpinner");
const browseSpinner = document.getElementById("browseSpinner");
const resultsDiv = document.getElementById("results");
const overlay = document.getElementById("overlay");
const languageSelect = document.getElementById("languageSelect");
const providerSelect = document.getElementById("providerSelect");
const seasonAccordion = document.getElementById("seasonAccordion");
const episodeSpinner = document.getElementById("episodeSpinner");
const selectAllCb = document.getElementById("selectAll");
const autoSyncCheck = document.getElementById("autoSyncCheck");
const statusBar = document.getElementById("statusBar");
const statusText = document.getElementById("statusText");
const downloadAllBtn = document.getElementById("downloadAllBtn");
const downloadSelectedBtn = document.getElementById("downloadSelectedBtn");
const randomBtn = document.getElementById("randomBtn");
const browseDiv = document.getElementById("browse");
const newAnimesGrid = document.getElementById("newAnimesGrid");
const popularAnimesGrid = document.getElementById("popularAnimesGrid");
const newAnimesSection = document.getElementById("newAnimesSection");
const popularAnimesSection = document.getElementById("popularAnimesSection");
const newSeriesGrid = document.getElementById("newSeriesGrid");
const popularSeriesGrid = document.getElementById("popularSeriesGrid");
const newSeriesSection = document.getElementById("newSeriesSection");
const popularSeriesSection = document.getElementById("popularSeriesSection");
const popularMoviesGrid = document.getElementById("popularMoviesGrid");
const popularMoviesSection = document.getElementById("popularMoviesSection");
const mangaFireTrendingGrid = document.getElementById("mangaFireTrendingGrid");
const mangaFireTrendingSection = document.getElementById("mangaFireTrendingSection");
const kinoxMoviesGrid = document.getElementById("kinoxMoviesGrid");
const kinoxMoviesSection = document.getElementById("kinoxMoviesSection");
const filmpalastMoviesGrid = document.getElementById("filmpalastMoviesGrid");
const filmpalastMoviesSection = document.getElementById("filmpalastMoviesSection");
const burningseriesGrid = document.getElementById("burningseriesGrid");
const burningseriesSection = document.getElementById("burningseriesSection");
const cinebyGrid = document.getElementById("cinebyGrid");
const cinebySection = document.getElementById("cinebySection");

// Generic cached fetch wrapper
async function cachedFetch(url, options = {}, ttlMs = 300000) {
  if (options.method && options.method !== "GET") {
    return fetch(url, options);
  }
  const cacheKey = "fetchCache_" + url;
  const cached = sessionStorage.getItem(cacheKey);
  if (cached) {
    const parsed = JSON.parse(cached);
    if (Date.now() - parsed.timestamp < ttlMs) {
      return {
        ok: true,
        json: async () => parsed.data
      };
    }
  }
  const response = await fetch(url, options);
  if (response.ok) {
    const cloned = response.clone();
    cloned.json().then(data => {
      try {
        sessionStorage.setItem(cacheKey, JSON.stringify({
          timestamp: Date.now(),
          data: data
        }));
      } catch (e) {
        // Ignore quota exceeded errors
      }
    }).catch(() => {});
  }
  return response;
}

// Browse loaders for the added sites. Defined up here (before showBrowseSections
// and the initial syncSiteState run) so switching to one of these sites on load
// never hits a temporal-dead-zone error. makeBrowseLoader references
// renderBrowseCards / loadDownloadedFolders, which are hoisted function
// declarations, so calling it here is safe.
function makeBrowseLoader(endpoint, grid) {
  let loadedAt = 0;
  let promise = null;
  return async function (force = false) {
    if (!force && loadedAt && Date.now() - loadedAt < BROWSE_REFRESH_MS) return;
    if (promise) return promise;
    const showSpinner = !loadedAt || force;
    loadedAt = Date.now();
    if (showSpinner && browseSpinner) browseSpinner.style.display = "block";
    if (showSpinner && grid) grid.innerHTML = "";
    promise = (async () => {
      try {
        const resp = await cachedFetch(endpoint);
        await loadDownloadedFolders();
        const data = await resp.json();
        if (data.results) renderBrowseCards(grid, data.results);
      } catch (e) {
        loadedAt = 0;
      } finally {
        if (showSpinner && browseSpinner) browseSpinner.style.display = "none";
        promise = null;
      }
    })();
    return promise;
  };
}

const loadKinoxBrowse = kinoxMoviesGrid
  ? makeBrowseLoader("/api/kinox-movies", kinoxMoviesGrid)
  : () => {};
const loadFilmpalastBrowse = filmpalastMoviesGrid
  ? makeBrowseLoader("/api/filmpalast-movies", filmpalastMoviesGrid)
  : () => {};
const loadBurningseriesBrowse = burningseriesGrid
  ? makeBrowseLoader("/api/burningseries-series", burningseriesGrid)
  : () => {};
const loadCinebyBrowse = cinebyGrid
  ? makeBrowseLoader("/api/cineby-movies", cinebyGrid)
  : () => {};
const mangaFireControls = document.getElementById("mangaFireControls");
const showUnofficialCb = document.getElementById("showUnofficial");
const BROWSE_REFRESH_MS = 60000;

let currentSeasons = [];
let currentAllSeasons = [];
let currentSeriesTitle = "";
let currentSeriesUrl = "";
let currentOpenSeriesToken = 0;
let seasonEpisodesCache = {};
let seasonEpisodesLoading = {};
let providersLoadedForSeries = false;
// Provider data per language label
let availableProviders = null;
let langSeparationEnabled = false;
// Static list of providers rendered into the template
const staticProviders = Array.from(providerSelect.options).map((o) => o.value);

function isMangaFireUrl(url) {
  return url.includes("mangafire.to/title/");
}

function getVisibleMangaFireSeasons() {
  if (!currentAllSeasons.length) return [];
  if (!showUnofficialCb || showUnofficialCb.checked) return currentAllSeasons;
  return currentAllSeasons.filter((season) => (season.chapter_type || "").toLowerCase() === "official");
}

function rebuildMangaFireAccordion() {
  currentSeasons = getVisibleMangaFireSeasons();
  seasonEpisodesCache = {};
  seasonEpisodesLoading = {};
  buildAccordion(currentSeasons, currentOpenSeriesToken);
}

// Site toggle state
let currentSite = "aniworld";

// Downloaded folders cache
let downloadedFolders = [];

// Custom paths select
const customPathSelect = document.getElementById("customPathSelect");
const customPathRow = document.getElementById("customPathRow");

async function loadCustomPaths() {
  if (!customPathSelect || !customPathRow) return;
  try {
    const resp = await fetch("/api/custom-paths");
    const data = await resp.json();
    const paths = data.paths || [];
    // Remove old custom options (keep "Default")
    while (customPathSelect.options.length > 1) customPathSelect.remove(1);
    if (paths.length) {
      let defaultForSite = "";
      paths.forEach(function (p) {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name;
        customPathSelect.appendChild(opt);
        // Pre-select the first path marked as default for the current site.
        const sites = (p.default_sites || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        if (!defaultForSite && sites.includes(currentSite)) {
          defaultForSite = String(p.id);
        }
      });
      customPathSelect.value = defaultForSite;
      customPathRow.style.display = "";
    } else {
      customPathRow.style.display = "none";
    }
  } catch (e) {
    /* best-effort */
  }
}

async function loadDownloadedFolders() {
  try {
    const resp = await fetch("/api/downloaded-folders");
    const data = await resp.json();
    downloadedFolders = data.folders || [];
  } catch (e) {
    /* best-effort */
  }
}

let stoLoadedAt = 0;
let stoBrowsePromise = null;
async function loadStoBrowse(force = false) {
  if (!force && stoLoadedAt && Date.now() - stoLoadedAt < BROWSE_REFRESH_MS) return;
  if (stoBrowsePromise) return stoBrowsePromise;
  const showSpinner = !stoLoadedAt || force;
  stoLoadedAt = Date.now();
  if (showSpinner && browseSpinner) browseSpinner.style.display = "block";
  if (showSpinner && newSeriesGrid) newSeriesGrid.innerHTML = "";
  if (showSpinner && popularSeriesGrid) popularSeriesGrid.innerHTML = "";
  stoBrowsePromise = (async () => {
    try {
      const [newResp, popResp] = await Promise.all([
        cachedFetch("/api/new-series"),
        cachedFetch("/api/popular-series"),
      ]);
      await loadDownloadedFolders();
      const newData = await newResp.json();
      const popData = await popResp.json();
      if (newData.results) renderBrowseCards(newSeriesGrid, newData.results);
      if (popData.results) renderBrowseCards(popularSeriesGrid, popData.results);
    } catch (e) {
      stoLoadedAt = 0;
    } finally {
      if (showSpinner && browseSpinner) browseSpinner.style.display = "none";
      stoBrowsePromise = null;
    }
  })();
  return stoBrowsePromise;
}

let mkLoadedAt = 0;
let mkBrowsePromise = null;
async function loadMegakinoBrowse(force = false) {
  if (!force && mkLoadedAt && Date.now() - mkLoadedAt < BROWSE_REFRESH_MS) return;
  if (mkBrowsePromise) return mkBrowsePromise;
  const showSpinner = !mkLoadedAt || force;
  mkLoadedAt = Date.now();
  if (showSpinner && browseSpinner) browseSpinner.style.display = "block";
  if (showSpinner && popularMoviesGrid) popularMoviesGrid.innerHTML = "";
  mkBrowsePromise = (async () => {
    try {
      const resp = await cachedFetch("/api/popular-movies");
      await loadDownloadedFolders();
      const data = await resp.json();
      if (data.results) renderBrowseCards(popularMoviesGrid, data.results);
    } catch (e) {
      mkLoadedAt = 0;
    } finally {
      if (showSpinner && browseSpinner) browseSpinner.style.display = "none";
      mkBrowsePromise = null;
    }
  })();
  return mkBrowsePromise;
}

let htvLoadedAt = 0;
let htvBrowsePromise = null;
async function loadHtvBrowse(force = false) {
  if (!force && htvLoadedAt && Date.now() - htvLoadedAt < BROWSE_REFRESH_MS) return;
  if (htvBrowsePromise) return htvBrowsePromise;
  const showSpinner = !htvLoadedAt || force;
  htvLoadedAt = Date.now();
  if (showSpinner && browseSpinner) browseSpinner.style.display = "block";
  if (showSpinner && htvTrendingGrid) htvTrendingGrid.innerHTML = "";
  htvBrowsePromise = (async () => {
    try {
      const resp = await cachedFetch("/api/htv-trending");
      await loadDownloadedFolders();
      const data = await resp.json();
      if (data.results) renderBrowseCards(htvTrendingGrid, data.results);
    } catch (e) {
      htvLoadedAt = 0;
    } finally {
      if (showSpinner && browseSpinner) browseSpinner.style.display = "none";
      htvBrowsePromise = null;
    }
  })();
  return htvBrowsePromise;
}

let mangaFireLoadedAt = 0;
let mangaFireBrowsePromise = null;
async function loadMangaFireBrowse(force = false) {
  if (!force && mangaFireLoadedAt && Date.now() - mangaFireLoadedAt < BROWSE_REFRESH_MS) return;
  if (mangaFireBrowsePromise) return mangaFireBrowsePromise;
  const showSpinner = !mangaFireLoadedAt || force;
  mangaFireLoadedAt = Date.now();
  if (showSpinner && browseSpinner) browseSpinner.style.display = "block";
  if (showSpinner && mangaFireTrendingGrid) mangaFireTrendingGrid.innerHTML = "";
  mangaFireBrowsePromise = (async () => {
    try {
      const resp = await cachedFetch("/api/mangafire-trending");
      await loadDownloadedFolders();
      const data = await resp.json();
      if (data.results) renderBrowseCards(mangaFireTrendingGrid, data.results);
    } catch (e) {
      mangaFireLoadedAt = 0;
    } finally {
      if (showSpinner && browseSpinner) browseSpinner.style.display = "none";
      mangaFireBrowsePromise = null;
    }
  })();
  return mangaFireBrowsePromise;
}

function showBrowseSections() {
  const isAniworld = currentSite === "aniworld";
  const isSto = currentSite === "sto";
  const isMegakino = currentSite === "megakino";
  const isHtv = currentSite === "htv";
  const isMangaFire = currentSite === "mangafire";
  const isKinox = currentSite === "kinox";
  const isFilmpalast = currentSite === "filmpalast";
  const isBurningseries = currentSite === "burningseries";
  const isCineby = currentSite === "cineby";
  browseDiv.style.display = "";
  newAnimesSection.style.display = isAniworld ? "" : "none";
  popularAnimesSection.style.display = isAniworld ? "" : "none";
  newSeriesSection.style.display = isSto ? "" : "none";
  popularSeriesSection.style.display = isSto ? "" : "none";
  if (popularMoviesSection) popularMoviesSection.style.display = isMegakino ? "" : "none";
  if (htvTrendingSection) htvTrendingSection.style.display = isHtv ? "" : "none";
  if (mangaFireTrendingSection) mangaFireTrendingSection.style.display = isMangaFire ? "" : "none";
  if (kinoxMoviesSection) kinoxMoviesSection.style.display = isKinox ? "" : "none";
  if (filmpalastMoviesSection) filmpalastMoviesSection.style.display = isFilmpalast ? "" : "none";
  if (burningseriesSection) burningseriesSection.style.display = isBurningseries ? "" : "none";
  if (cinebySection) cinebySection.style.display = isCineby ? "" : "none";
  if (isAniworld) loadAniworldBrowse();
  else if (isSto) loadStoBrowse();
  else if (isMegakino) loadMegakinoBrowse();
  else if (isHtv) loadHtvBrowse();
  else if (isMangaFire) loadMangaFireBrowse();
  else if (isKinox) loadKinoxBrowse();
  else if (isFilmpalast) loadFilmpalastBrowse();
  else if (isBurningseries) loadBurningseriesBrowse();
  else if (isCineby) loadCinebyBrowse();
}

function normalizeQuotes(s) {
  return s
    .replace(/[\u2018\u2019\u2032\u0060]/g, "'")
    .replace(/[\u201C\u201D\u201E]/g, '"');
}

function isDownloaded(title) {
  if (!downloadedFolders.length || !title) return false;
  const clean = normalizeQuotes(
    unesc(title)
      .replace(/\s*\(.*$/, "")
      .trim()
      .toLowerCase(),
  );
  return downloadedFolders.some((f) =>
    normalizeQuotes(f.toLowerCase()).startsWith(clean),
  );
}

function addDownloadedBadge(card, title) {
  if (isDownloaded(title)) {
    const badge = document.createElement("div");
    badge.className = "downloaded-badge";
    card.style.position = "relative";
    card.appendChild(badge);
  }
}

const htvTrendingSection = document.getElementById("htvTrendingSection");
const htvTrendingGrid = document.getElementById("htvTrendingGrid");

const segmentedThumb = document.getElementById("segmentedThumb");
const htvEnabled = window.HTV_ENABLED;
const burningseriesEnabled = window.BURNINGSERIES_ENABLED;
const kinoxEnabled = window.KINOX_ENABLED;
// BurningSeries and Kinox are opt-in via .env (ANIWORLD_ENABLE_BURNINGSERIES /
// ANIWORLD_ENABLE_KINOX) and hidden unless enabled, same as the Hanime tab.
const sites = ["aniworld", "mangafire", "sto", "burningseries", "megakino", "cineby", "kinox", "filmpalast", "htv"].filter(
  (site) => {
    if (site === "htv") return htvEnabled;
    if (site === "burningseries") return burningseriesEnabled;
    if (site === "kinox") return kinoxEnabled;
    return true;
  },
);

// Movie-only sites behave like MegaKino (single item, no seasons).
const movieSites = ["megakino", "filmpalast"];

const siteLabelIds = {
  aniworld: "labelAniworld",
  sto: "labelSto",
  megakino: "labelMegakino",
  cineby: "labelCineby",
  kinox: "labelKinox",
  burningseries: "labelBurningSeries",
  filmpalast: "labelFilmPalast",
  mangafire: "labelMangaFire",
  htv: "labelHtv",
};

const thumbColors = {
  aniworld: { bg: "linear-gradient(135deg, #8b5cf6, #6d28d9)", shadow: "0 2px 8px rgba(139, 92, 246, 0.35)" },
  sto: { bg: "linear-gradient(135deg, #38bdf8, #2563eb)", shadow: "0 2px 8px rgba(56, 189, 248, 0.35)" },
  megakino: { bg: "linear-gradient(135deg, #ef4444, #b91c1c)", shadow: "0 2px 8px rgba(239, 68, 68, 0.35)" },
  cineby: { bg: "linear-gradient(135deg, #22d3ee, #0891b2)", shadow: "0 2px 8px rgba(34, 211, 238, 0.35)" },
  kinox: { bg: "linear-gradient(135deg, #34d399, #059669)", shadow: "0 2px 8px rgba(52, 211, 153, 0.35)" },
  burningseries: { bg: "linear-gradient(135deg, #fb923c, #ea580c)", shadow: "0 2px 8px rgba(251, 146, 60, 0.35)" },
  filmpalast: { bg: "linear-gradient(135deg, #84cc16, #4d7c0f)", shadow: "0 2px 8px rgba(132, 204, 22, 0.35)" },
  mangafire: { bg: "linear-gradient(135deg, #f59e0b, #b45309)", shadow: "0 2px 8px rgba(245, 158, 11, 0.35)" },
  htv: { bg: "linear-gradient(135deg, #ff4fa3, #db2777)", shadow: "0 2px 8px rgba(255, 79, 163, 0.35)" },
};

function updateSliderState(site) {
  for (const [siteKey, labelId] of Object.entries(siteLabelIds)) {
    const label = document.getElementById(labelId);
    if (label) label.classList.toggle("active", site === siteKey);
  }

  if (!segmentedThumb) return;
  const btn = document.getElementById(siteLabelIds[site]);
  if (!btn) return;
  const track = btn.parentElement;
  const trackRect = track.getBoundingClientRect();
  const btnRect = btn.getBoundingClientRect();
  segmentedThumb.style.width = btnRect.width + "px";
  segmentedThumb.style.transform = "translateX(" + (btnRect.left - trackRect.left - 3) + "px)";
  const color = thumbColors[site] || thumbColors.aniworld;
  segmentedThumb.style.background = color.bg;
  segmentedThumb.style.boxShadow = color.shadow;
}

function switchSite(site) {
  currentSite = site;
  localStorage.setItem("selectedSite", currentSite);

  updateSliderState(site);

  // Update heading
  const heading = document.getElementById("pageHeading");
  if (heading) {
    const headings = {
      aniworld: "AniWorld Downloader",
      sto: "SerienStream Downloader",
      megakino: "MegaKino Downloader",
      cineby: "Cineby Downloader",
      kinox: "Kinox Downloader",
      burningseries: "BurningSeries Downloader",
      filmpalast: "FilmPalast Downloader",
      mangafire: "MangaFire Downloader",
      htv: "Hanime Downloader",
    };
    heading.textContent = headings[site] || "AniWorld Downloader";
  }

  // Update search placeholder
  const isHtv = site === "htv";
  const isMangaFire = site === "mangafire";
  document.querySelector(".search-bar").style.display = "";
  const placeholders = {
    mangafire: "Search MangaFire...",
    htv: "Search HAnime...",
    sto: "Search S.to...",
    megakino: "Search MegaKino...",
    cineby: "Search Cineby...",
    kinox: "Search Kinox...",
    burningseries: "Search BurningSeries...",
    filmpalast: "Search FilmPalast...",
  };
  searchInput.placeholder = placeholders[site] || "Search AniWorld...";

  // Clear search results
  resultsDiv.innerHTML = "";
  searchInput.value = "";

  // Toggle browse sections per site
  showBrowseSections();

  // Toggle Random button
  randomBtn.style.display = site === "aniworld" ? "" : "none";

  // Update language dropdown & controls visibility
  const controlsDiv = document.querySelector(".controls");
  if (controlsDiv) controlsDiv.style.display = isHtv || isMangaFire ? "none" : "";
  if (mangaFireControls) mangaFireControls.style.display = isMangaFire ? "flex" : "none";
  if (!isHtv && !isMangaFire) rebuildLanguageSelect();

  // Reset providers
  availableProviders = null;
}

const siteLangMaps = {
  sto: () => window.STO_LANGS || {},
  megakino: () => window.MEGAKINO_LANGS || {},
  kinox: () => window.KINOX_LANGS || {},
  burningseries: () => window.BURNINGSERIES_LANGS || {},
  filmpalast: () => window.FILMPALAST_LANGS || {},
  cineby: () => window.CINEBY_LANGS || {},
};

function rebuildLanguageSelect() {
  const langs = (siteLangMaps[currentSite] || (() => window.ANIWORLD_LANGS || {}))();
  const previousValue = languageSelect.value;
  const preferredValue =
    currentSite === "megakino" || movieSites.includes(currentSite)
      ? "German Dub"
      : previousValue || window.DEFAULT_WEB_LANGUAGE || "German Dub";
  languageSelect.innerHTML = "";

  if (langSeparationEnabled) {
    const opt = document.createElement("option");
    opt.value = "All Languages";
    opt.textContent = "All Languages";
    languageSelect.appendChild(opt);
  }

  for (const [key, label] of Object.entries(langs)) {
    const opt = document.createElement("option");
    opt.value = label;
    opt.textContent = label;
    languageSelect.appendChild(opt);
  }

  const validValues = Array.from(languageSelect.options).map((opt) => opt.value);
  if (validValues.includes(preferredValue)) {
    languageSelect.value = preferredValue;
  } else if (
    currentSite === "aniworld" &&
    validValues.includes(window.DEFAULT_WEB_LANGUAGE)
  ) {
    languageSelect.value = window.DEFAULT_WEB_LANGUAGE;
  } else if (validValues.length) {
    languageSelect.value = validValues[0];
  }
}

// Restore site state from localStorage
(function syncSiteState() {
  const saved = localStorage.getItem("selectedSite");
  const initial = saved && saved !== "aniworld" && sites.includes(saved) ? saved : "aniworld";
  if (initial !== "aniworld") {
    switchSite(initial);
  } else {
    updateSliderState("aniworld");
  }
  requestAnimationFrame(() => updateSliderState(currentSite));
})();
window.addEventListener("resize", () => updateSliderState(currentSite));

searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") doSearch();
});
searchInput.addEventListener("input", () => {
  if (!searchInput.value.trim()) {
    resultsDiv.innerHTML = "";
    showBrowseSections();
  }
});
languageSelect.addEventListener("change", updateProviderDropdown);

function renderBrowseCards(grid, items) {
  grid.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "browse-card";
    card.onclick = () => openSeries(item.url);
    card.innerHTML =
      `<img src="${esc(item.poster_url)}" alt="" onerror="this.style.visibility='hidden'">` +
      `<div class="browse-info">` +
      `<div class="browse-title">${esc(item.title)}</div>` +
      `<div class="browse-genre">${esc(item.genre || "")}</div>` +
      `</div>`;
    addDownloadedBadge(card, item.title);
    grid.appendChild(card);
    // Sites without posters in their listing (e.g. burning-series) fill them
    // in lazily so the grid still shows instantly.
    if (!item.poster_url) loadPoster(item.url, card.querySelector("img"));
  });
}

let aniLoadedAt = 0;
let aniBrowsePromise = null;
async function loadAniworldBrowse(force = false) {
  if (!force && aniLoadedAt && Date.now() - aniLoadedAt < BROWSE_REFRESH_MS) return;
  if (aniBrowsePromise) return aniBrowsePromise;
  const showSpinner = !aniLoadedAt || force;
  aniLoadedAt = Date.now();
  if (showSpinner && browseSpinner) browseSpinner.style.display = "block";
  if (showSpinner && newAnimesGrid) newAnimesGrid.innerHTML = "";
  if (showSpinner && popularAnimesGrid) popularAnimesGrid.innerHTML = "";
  aniBrowsePromise = (async () => {
    try {
      const [newResp, popResp] = await Promise.all([
        cachedFetch("/api/new-animes"),
        cachedFetch("/api/popular-animes"),
      ]);
      await loadDownloadedFolders();
      const newData = await newResp.json();
      const popData = await popResp.json();
      if (newData.results) renderBrowseCards(newAnimesGrid, newData.results);
      if (popData.results) renderBrowseCards(popularAnimesGrid, popData.results);
    } catch (e) {
      aniLoadedAt = 0;
    } finally {
      if (showSpinner && browseSpinner) browseSpinner.style.display = "none";
      aniBrowsePromise = null;
    }
  })();
  return aniBrowsePromise;
}

function isBrowseVisible() {
  return browseDiv.style.display !== "none" && !searchInput.value.trim();
}

function refreshVisibleBrowse(force = false) {
  if (!isBrowseVisible()) return;
  if (currentSite === "aniworld") loadAniworldBrowse(force);
  else if (currentSite === "sto") loadStoBrowse(force);
  else if (currentSite === "megakino") loadMegakinoBrowse(force);
  else if (currentSite === "mangafire") loadMangaFireBrowse(force);
  else if (currentSite === "htv") loadHtvBrowse(force);
  else if (currentSite === "kinox") loadKinoxBrowse(force);
  else if (currentSite === "filmpalast") loadFilmpalastBrowse(force);
  else if (currentSite === "burningseries") loadBurningseriesBrowse(force);
  else if (currentSite === "cineby") loadCinebyBrowse(force);
}

setInterval(() => {
  refreshVisibleBrowse(false);
}, BROWSE_REFRESH_MS);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshVisibleBrowse(false);
});

window.addEventListener("focus", () => {
  refreshVisibleBrowse(false);
});

showBrowseSections();

async function doSearch() {
  const keyword = searchInput.value.trim();
  if (!keyword) return;
  searchBtn.disabled = true;
  searchSpinner.style.display = "block";
  resultsDiv.innerHTML = "";
  browseDiv.style.display = "none";
  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, site: currentSite }),
    });
    const data = await resp.json();
    renderResults(data.results || []);
  } catch (e) {
    showToast("Search failed: " + e.message);
  } finally {
    searchBtn.disabled = false;
    searchSpinner.style.display = "none";
  }
}

async function doRandom() {
  if (currentSite === "sto") {
    showToast("Random is not available for serienstream.to");
    return;
  }
  randomBtn.disabled = true;
  try {
    const resp = await fetch("/api/random");
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }
    openSeries(data.url);
  } catch (e) {
    showToast("Failed to fetch random anime: " + e.message);
  } finally {
    randomBtn.disabled = false;
  }
}

function renderResults(results) {
  resultsDiv.innerHTML = "";
  if (!results.length) {
    resultsDiv.innerHTML =
      '<div style="width:100%;text-align:center;color:#888;padding:40px">No results found.</div>';
    return;
  }
  results.forEach((r) => {
    const card = document.createElement("div");
    card.className = "card";
    card.onclick = () => openSeries(r.url);
    const posterSrc = r.poster_url ? esc(r.poster_url) : "";
    card.innerHTML = `<img src="${posterSrc}" alt="" data-url="${esc(r.url)}"><div class="info"><div class="title">${esc(r.title)}</div></div>`;
    addDownloadedBadge(card, r.title);
    resultsDiv.appendChild(card);
    if (!r.poster_url) loadPoster(r.url, card.querySelector("img"));
  });
}

async function loadPoster(url, imgEl) {
  try {
    const resp = await cachedFetch("/api/series?url=" + encodeURIComponent(url));
    const data = await resp.json();
    if (data.poster_url) imgEl.src = data.poster_url;
  } catch (e) {
    /* ignore poster load failure */
  }
}

async function openSeries(url) {
  const openToken = ++currentOpenSeriesToken;
  overlay.style.display = "block";
  document.getElementById("modalPoster").src = "";
  document.getElementById("modalTitle").textContent = "Loading...";
  document.getElementById("modalGenres").textContent = "";
  document.getElementById("modalYear").textContent = "";
  document.getElementById("modalDesc").textContent = "";
  seasonAccordion.innerHTML = "";
  statusBar.classList.remove("active");
  availableProviders = null;
  seasonEpisodesCache = {};
  seasonEpisodesLoading = {};
  providersLoadedForSeries = false;
  currentSeriesUrl = url;
  currentSeriesTitle = "";
  const isHtvSeries = url.includes("hanime.tv/");
  const isMangaFireSeries = isMangaFireUrl(url);
  const controlsDiv = document.querySelector(".controls");
  if (controlsDiv) controlsDiv.style.display = isHtvSeries || isMangaFireSeries ? "none" : "";
  if (mangaFireControls) mangaFireControls.style.display = isMangaFireSeries ? "flex" : "none";
  await checkLangSeparation();
  if (downloadAllLangsBtn && isMangaFireSeries) {
    downloadAllLangsBtn.style.display = "none";
  }
  if (!isHtvSeries && !isMangaFireSeries) {
    rebuildLanguageSelect();
    resetProviderDropdown();
  }
  if (showUnofficialCb) showUnofficialCb.checked = false;
  loadCustomPaths();

  try {
    const [seriesResp, seasonsResp] = await Promise.all([
      cachedFetch("/api/series?url=" + encodeURIComponent(url)),
      cachedFetch("/api/seasons?url=" + encodeURIComponent(url)),
    ]);
    const seriesData = await seriesResp.json();
    const seasonsData = await seasonsResp.json();
    if (openToken !== currentOpenSeriesToken) return;

    currentSeriesTitle = seriesData.title || "Unknown";
    const titleEl = document.getElementById("modalTitle");
    const titleUrl =
      (seriesData.episode_urls && seriesData.episode_urls[0]) || currentSeriesUrl;
    titleEl.innerHTML = `<a href="${titleUrl}" target="_blank" rel="noopener noreferrer">${currentSeriesTitle}</a>`;
    if (seriesData.poster_url)
      document.getElementById("modalPoster").src = seriesData.poster_url;
    document.getElementById("modalGenres").textContent = (
      seriesData.genres || []
    ).join(", ");
    document.getElementById("modalYear").textContent =
      seriesData.release_year || "";
    document.getElementById("modalDesc").textContent =
      seriesData.description || "";

    currentAllSeasons = seasonsData.seasons || [];
    currentSeasons = isMangaFireSeries ? getVisibleMangaFireSeasons() : currentAllSeasons;
    buildAccordion(currentSeasons, openToken);

    // Check if auto-sync exists for this series
    if (autoSyncCheck) {
      autoSyncCheck.checked = false;
      try {
        const syncResp = await fetch(
          "/api/autosync/check?url=" + encodeURIComponent(url),
        );
        const syncData = await syncResp.json();
        autoSyncCheck.checked = !!syncData.exists;
      } catch (e) {
        /* ignore */
      }
    }
  } catch (e) {
    showToast("Failed to load series: " + e.message);
  }
}

function buildAccordion(seasons, openToken) {
  seasonAccordion.innerHTML = "";
  selectAllCb.checked = false;
  episodeSpinner.style.display = seasons.length ? "block" : "none";

  seasons.forEach((season, index) => {
    const section = document.createElement("div");
    section.className = "season-section";
    section.dataset.seasonIndex = index;

    const count =
      typeof season.episode_count === "number" ? season.episode_count : "?";
    const label = currentSite === "mangafire"
      ? `Chapter ${season.season_number}`
      : season.are_movies
        ? `Movies (${count} episodes)`
        : `Season ${season.season_number} (${count} episodes)`;

    const header = document.createElement("div");
    header.className = "season-header" + (index === 0 ? " expanded" : "");
    header.innerHTML =
      `<div class="season-label"><span class="season-arrow">&#9654;</span> ${esc(label)}</div>` +
      `<label class="season-all-label" onclick="event.stopPropagation()"><input type="checkbox" onchange="toggleSeasonAll(this, ${index})"> All</label>`;
    header.addEventListener("click", () => toggleSeason(index));

    const body = document.createElement("div");
    body.className = "season-body" + (index === 0 ? " expanded" : "");
    body.id = "seasonBody-" + index;
    body.innerHTML =
      '<div style="color:#888;padding:12px 0;text-align:center">Loading episodes...</div>';

    section.appendChild(header);
    section.appendChild(body);
    seasonAccordion.appendChild(section);
  });

  if (seasons.length) {
    loadSeasonEpisodes(0, openToken).finally(() => {
      if (openToken === currentOpenSeriesToken) {
        episodeSpinner.style.display = "none";
      }
    });
  } else {
    episodeSpinner.style.display = "none";
  }
}

function toggleShowUnofficial() {
  if (currentSite !== "mangafire") return;
  rebuildMangaFireAccordion();
}

async function loadSeasonEpisodes(index, openToken = currentOpenSeriesToken) {
  if (seasonEpisodesCache[index]) return seasonEpisodesCache[index];
  if (seasonEpisodesLoading[index]) return seasonEpisodesLoading[index];
  const season = currentSeasons[index];
  const body = document.getElementById("seasonBody-" + index);
  if (!season || !body) return [];

  let epUrl = "/api/episodes?url=" + encodeURIComponent(season.url || currentSeriesUrl);
  if (!season.url && currentSeriesUrl) {
    epUrl += "&series_url=" + encodeURIComponent(currentSeriesUrl);
  }
  if (currentSite === "mangafire" && currentSeriesUrl) {
    epUrl += "&series_url=" + encodeURIComponent(currentSeriesUrl);
  }
  seasonEpisodesLoading[index] = cachedFetch(epUrl)
    .then((r) => r.json())
    .then((data) => {
      if (openToken !== currentOpenSeriesToken) return [];
      const episodes = data.episodes || [];
      seasonEpisodesCache[index] = episodes;
      renderSeasonEpisodes(index, episodes);
      if (!providersLoadedForSeries && episodes.length && currentSite !== "mangafire") {
        providersLoadedForSeries = true;
        fetchProviders(episodes[0].url);
      }
      return episodes;
    })
    .catch(() => {
      if (openToken === currentOpenSeriesToken) {
        body.innerHTML =
          '<div style="color:#888;padding:12px 0;text-align:center">Failed to load episodes.</div>';
      }
      return [];
    })
    .finally(() => {
      delete seasonEpisodesLoading[index];
    });

  return seasonEpisodesLoading[index];
}

function renderSeasonEpisodes(index, episodes) {
  const section = seasonAccordion.querySelector(`[data-season-index="${index}"]`);
  const body = document.getElementById("seasonBody-" + index);
  if (!section || !body) return;

  body.innerHTML = "";
  episodes.forEach((ep) => {
    const div = document.createElement("div");
    div.className = "episode-item";
    const pageCount = typeof ep.page_count === "number" ? ep.page_count : 0;
    const title = currentSite === "mangafire"
      ? `<span class="ep-title-main">${pageCount ? `Page ${ep.page_number} of ${pageCount}` : `Page ${ep.page_number}`}</span>`
      : (ep.title_en || ep.title_de)
        ? `<span class="ep-title-main">${esc(ep.title_en || ep.title_de)}</span>`
        : '<span class="ep-title-fallback">[Not Available]</span>';
    const languageBadges = renderEpisodeLanguageBadges(ep.available_languages || []);
    const dlIcon = ep.downloaded
      ? '<span class="ep-downloaded" title="Downloaded">&#10003;</span>'
      : "";
    const epPrefix = currentSite === "mangafire" ? "P" : "E";
    const chapterUrl = ep.chapter_url || ep.url || "";
    const value = currentSite === "mangafire"
      ? `${chapterUrl}##${ep.page_number}`
      : ep.url;
    const extraAttrs = currentSite === "mangafire"
      ? ` data-chapter-url="${esc(chapterUrl)}" data-page-number="${ep.page_number}"`
      : "";
    div.innerHTML = `<input type="checkbox" value="${esc(value)}" data-season="${index}"${extraAttrs}><span class="ep-num">${epPrefix}${ep.episode_number}</span>${dlIcon}<div class="ep-main"><span class="ep-title">${title}</span>${languageBadges}</div>`;
    body.appendChild(div);
  });

  const header = section.querySelector(".season-header");
  const season = currentSeasons[index];
  const allDownloaded =
    episodes.length > 0 && episodes.every((ep) => ep.downloaded);
  const seasonDlIcon = allDownloaded
    ? '<span class="season-downloaded" title="All episodes downloaded">&#10003;</span>'
    : "";
  const label = season.are_movies
    ? `Movies (${episodes.length} episodes)`
    : currentSite === "mangafire"
      ? `Chapter ${season.season_number}`
      : `Season ${season.season_number} (${episodes.length} episodes)`;
  header.innerHTML =
    `<div class="season-label"><span class="season-arrow">&#9654;</span> ${esc(label)}${seasonDlIcon}</div>` +
    `<label class="season-all-label" onclick="event.stopPropagation()"><input type="checkbox" onchange="toggleSeasonAll(this, ${index})"> All</label>`;
}

function renderEpisodeLanguageBadges(labels) {
  if (!labels.length) return "";
  return `<span class="ep-language-badges">${labels
    .map((label) => {
      const badge = getEpisodeLanguageBadge(label);
      const cls = getEpisodeLanguageBadgeClass(label);
      const flagMarkup = (badge ? badge.flags : [])
        .map(
          (flag) =>
            `<img class="ep-language-flag" src="/static/flags/${flag}.svg" alt="" aria-hidden="true">`,
        )
        .join("");
      const text = badge ? badge.text : label;
      return `<span class="ep-language-badge ${cls}" title="${esc(label)}">${flagMarkup}<span class="ep-language-badge-text">${esc(text)}</span></span>`;
    })
    .join("")}</span>`;
}

function getEpisodeLanguageBadge(label) {
  const badgeMap = {
    "German Dub": { flags: ["de"], text: "Dub" },
    "German Sub": { flags: ["jp", "de"], text: "Sub" },
    "English Dub": { flags: ["gb"], text: "Dub" },
    "English Sub": { flags: ["jp", "gb"], text: "Sub" },
    Japanese: { flags: ["jp"], text: "Dub" },
  };
  return badgeMap[label] || null;
}

function getEpisodeLanguageBadgeClass(label) {
  const classMap = {
    "German Dub": "badge-german-dub",
    "German Sub": "badge-german-sub",
    "English Dub": "badge-english-dub",
    "English Sub": "badge-english-sub",
    Japanese: "badge-german-dub",
  };
  return classMap[label] || "badge-default";
}

async function toggleSeason(index) {
  const section = seasonAccordion.querySelector(
    `[data-season-index="${index}"]`,
  );
  if (!section) return;
  const header = section.querySelector(".season-header");
  const body = section.querySelector(".season-body");
  if (!body.classList.contains("expanded") && !seasonEpisodesCache[index]) {
    await loadSeasonEpisodes(index);
  }
  header.classList.toggle("expanded");
  body.classList.toggle("expanded");
}

async function toggleSeasonAll(checkbox, seasonIndex) {
  const body = document.getElementById("seasonBody-" + seasonIndex);
  if (!body) return;
  if (!seasonEpisodesCache[seasonIndex]) {
    await loadSeasonEpisodes(seasonIndex);
  }
  body
    .querySelectorAll("input[type=checkbox]")
    .forEach((cb) => (cb.checked = checkbox.checked));
  syncSelectAll();
}

async function ensureAllSeasonsLoaded() {
  await Promise.all(currentSeasons.map((_, index) => loadSeasonEpisodes(index)));
}

async function toggleSelectAll() {
  const checked = selectAllCb.checked;
  if (checked) {
    await ensureAllSeasonsLoaded();
  }
  seasonAccordion
    .querySelectorAll("input[type=checkbox]")
    .forEach((cb) => (cb.checked = checked));
}

function syncSelectAll() {
  const all = seasonAccordion.querySelectorAll(
    ".episode-item input[type=checkbox]",
  );
  const checked = seasonAccordion.querySelectorAll(
    ".episode-item input[type=checkbox]:checked",
  );
  selectAllCb.checked = all.length > 0 && all.length === checked.length;
}

function getAllEpisodeUrls() {
  if (currentSite === "mangafire") {
    return collectMangaFireDownloadItems(false);
  }
  return Array.from(
    seasonAccordion.querySelectorAll(".episode-item input[type=checkbox]"),
  ).map((cb) => cb.value);
}

function getSelectedEpisodeUrls() {
  if (currentSite === "mangafire") {
    return collectMangaFireDownloadItems(true);
  }
  return Array.from(
    seasonAccordion.querySelectorAll(
      ".episode-item input[type=checkbox]:checked",
    ),
  ).map((cb) => cb.value);
}

function collectMangaFireDownloadItems(onlyChecked) {
  const selector = onlyChecked
    ? ".episode-item input[type=checkbox]:checked"
    : ".episode-item input[type=checkbox]";
  const grouped = new Map();
  seasonAccordion.querySelectorAll(selector).forEach((cb) => {
    const chapterUrl = cb.dataset.chapterUrl || cb.value.split("##")[0];
    const pageNumber = parseInt(cb.dataset.pageNumber || "0", 10);
    if (!chapterUrl || !pageNumber) return;
    if (!grouped.has(chapterUrl)) grouped.set(chapterUrl, new Set());
    grouped.get(chapterUrl).add(pageNumber);
  });

  return Array.from(grouped.entries()).map(([url, pageSet]) => ({
    url,
    series_url: currentSeriesUrl,
    selected_pages: Array.from(pageSet).sort((a, b) => a - b),
  }));
}

async function fetchProviders(episodeUrl) {
  try {
    const resp = await fetch(
      "/api/providers?url=" + encodeURIComponent(episodeUrl),
    );
    const data = await resp.json();
    if (data.providers) {
      availableProviders = data.providers;
      filterLanguageSelectToAvailable();
      updateProviderDropdown();
    }
  } catch (e) {
    // If provider fetch fails, keep the static list
  }
}

function filterLanguageSelectToAvailable() {
  if (!availableProviders) return;
  const availableLangs = Object.keys(availableProviders);
  if (!availableLangs.length) return;

  const previousValue = languageSelect.value;

  for (const opt of Array.from(languageSelect.options)) {
    if (opt.value === "All Languages") continue;
    opt.hidden = !availableLangs.includes(opt.value);
  }

  // Keep selection if still valid, otherwise pick first available
  const visibleOptions = Array.from(languageSelect.options).filter(
    (opt) => !opt.hidden,
  );
  const stillValid = visibleOptions.some((opt) => opt.value === previousValue);
  if (!stillValid && visibleOptions.length) {
    languageSelect.value = visibleOptions[0].value;
  }
}

function resetProviderDropdown() {
  providerSelect.innerHTML = "";
  if (currentSite !== "megakino") {
    staticProviders.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      providerSelect.appendChild(opt);
    });
  }
  selectDefaultProvider();
}

function updateProviderDropdown() {
  if (!availableProviders) return;

  const lang = languageSelect.value;
  const providers = availableProviders[lang];

  providerSelect.innerHTML = "";
  if (providers && providers.length) {
    providers.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      providerSelect.appendChild(opt);
    });
  } else {
    if (currentSite !== "megakino") {
      staticProviders.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p;
        opt.textContent = p;
        providerSelect.appendChild(opt);
      });
    }
  }
  selectDefaultProvider();
}

function selectDefaultProvider() {
  for (const opt of providerSelect.options) {
    if (opt.value === "VOE") {
      providerSelect.value = "VOE";
      return;
    }
  }

  if (providerSelect.options.length) {
    providerSelect.value = providerSelect.options[0].value;
  }
}

async function startDownload(all) {
  if (all) {
    episodeSpinner.style.display = "block";
    await ensureAllSeasonsLoaded();
    episodeSpinner.style.display = "none";
  }
  const episodes = all ? getAllEpisodeUrls() : getSelectedEpisodeUrls();
  if (!episodes.length) {
    showToast(all ? "No episodes available." : "No episodes selected.");
    return;
  }

  const isHtvDl = currentSeriesUrl.includes("hanime.tv/");
  const isMangaFireDl = isMangaFireUrl(currentSeriesUrl);
  const language = isHtvDl
    ? "Japanese"
    : isMangaFireDl
      ? "MangaFire"
      : languageSelect.value;
  const provider = isHtvDl
    ? "HanimeTV"
    : isMangaFireDl
      ? "MangaFire"
      : providerSelect.value;

  downloadAllBtn.disabled = true;
  downloadSelectedBtn.disabled = true;
  try {
    const dlBody = {
      episodes,
      language,
      provider,
      title: currentSeriesTitle,
      series_url: currentSeriesUrl,
    };
    if (isMangaFireDl) {
      const formatSelect = document.getElementById("mangaFireFormat");
      if (formatSelect) {
        dlBody.mangafire_format = formatSelect.value;
      }
    }
    if (customPathSelect && customPathSelect.value) {
      dlBody.custom_path_id = parseInt(customPathSelect.value);
    }
    const resp = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dlBody),
    });
    const data = await resp.json();
    if (data.error) {
      showToast(data.error);
      return;
    }

    showToast("Added to download queue");
    if (typeof loadQueue === "function") loadQueue();
  } catch (e) {
    showToast("Download request failed: " + e.message);
  } finally {
    downloadAllBtn.disabled = false;
    downloadSelectedBtn.disabled = false;
  }
}

function closeModal() {
  overlay.style.display = "none";
  if (autoSyncCheck) autoSyncCheck.checked = false;
}
function closeModalOutside(e) {
  if (e.target === overlay) closeModal();
}

// Auto-Sync toggle from modal checkbox
async function toggleAutoSync() {
  if (!autoSyncCheck) return;
  if (autoSyncCheck.checked) {
    // Select all episodes
    episodeSpinner.style.display = "block";
    await ensureAllSeasonsLoaded();
    episodeSpinner.style.display = "none";
    selectAllCb.checked = true;
    await toggleSelectAll();
    // Create sync job
    try {
      const isMangaFireDl = isMangaFireUrl(currentSeriesUrl);
      const body = {
        title: currentSeriesTitle,
        series_url: currentSeriesUrl,
        language: isMangaFireDl ? "MangaFire" : languageSelect.value,
        provider: isMangaFireDl ? "MangaFire" : providerSelect.value,
      };
      if (customPathSelect && customPathSelect.value) {
        body.custom_path_id = parseInt(customPathSelect.value);
      }
      const resp = await fetch("/api/autosync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.ok) {
        showToast('Auto-Sync enabled for "' + currentSeriesTitle + '"');
      } else if (resp.status === 409 && data.job) {
        const isMangaFireDl = isMangaFireUrl(currentSeriesUrl);
        const updateBody = {
          language: isMangaFireDl ? "MangaFire" : languageSelect.value,
          provider: isMangaFireDl ? "MangaFire" : providerSelect.value,
          custom_path_id:
            customPathSelect && customPathSelect.value
              ? parseInt(customPathSelect.value)
              : null,
        };
        const putResp = await fetch("/api/autosync/" + data.job.id, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updateBody),
        });
        const putData = await putResp.json();
        if (putData.ok) {
          showToast('Auto-Sync updated for "' + currentSeriesTitle + '"');
        } else {
          showToast(putData.error || "Failed to update sync job");
        }
      } else if (data.error) {
        showToast(data.error);
      }
    } catch (e) {
      showToast("Failed to create sync job");
      autoSyncCheck.checked = false;
    }
  } else {
    try {
      const resp = await fetch(
        "/api/autosync/check?url=" + encodeURIComponent(currentSeriesUrl),
      );
      const data = await resp.json();
      if (data.exists && data.job) {
        const delResp = await fetch("/api/autosync/" + data.job.id, {
          method: "DELETE",
        });
        const delData = await delResp.json();
        if (delData.ok) {
          showToast('Auto-Sync disabled for "' + currentSeriesTitle + '"');
        } else {
          showToast(delData.error || "Failed to remove sync job");
          autoSyncCheck.checked = true;
        }
      }
    } catch (e) {
      showToast("Failed to remove sync job");
      autoSyncCheck.checked = true;
    }
  }
}

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.display = "block";
  setTimeout(() => (t.style.display = "none"), 4000);
}

function unesc(s) {
  const d = document.createElement("textarea");
  d.innerHTML = s || "";
  return d.value;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = unesc(s);
  return d.innerHTML;
}

const downloadAllLangsBtn = document.getElementById("downloadAllLangsBtn");
let defaultSyncLanguage = "German Dub";

async function checkLangSeparation() {
  try {
    const resp = await fetch("/api/settings");
    const data = await resp.json();
    langSeparationEnabled = data.lang_separation === "1";
    if (data.sync_language) {
      defaultSyncLanguage = data.sync_language;
    }
    if (downloadAllLangsBtn) {
      downloadAllLangsBtn.style.display = langSeparationEnabled ? "" : "none";
    }
  } catch (e) {
    /* ignore */
  }
}

async function startDownloadAllLangs() {
  if (currentSite === "mangafire") {
    showToast("All Languages is not available for MangaFire.");
    return;
  }
  episodeSpinner.style.display = "block";
  await ensureAllSeasonsLoaded();
  episodeSpinner.style.display = "none";
  const episodes = getAllEpisodeUrls();
  if (!episodes.length) {
    showToast("No episodes available.");
    return;
  }
  if (!availableProviders) {
    showToast("Provider data not loaded yet.");
    return;
  }

  downloadAllLangsBtn.disabled = true;
  downloadAllBtn.disabled = true;
  downloadSelectedBtn.disabled = true;

  let queued = 0;
  try {
    for (const [lang, providers] of Object.entries(availableProviders)) {
      if (!providers.length) continue;
      const provider = providers.includes("VOE") ? "VOE" : providers[0];
      const dlBody = {
        episodes,
        language: lang,
        provider,
        title: currentSeriesTitle,
        series_url: currentSeriesUrl,
      };
      if (customPathSelect && customPathSelect.value) {
        dlBody.custom_path_id = parseInt(customPathSelect.value);
      }
      const resp = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dlBody),
      });
      const data = await resp.json();
      if (!data.error) queued++;
    }
    showToast("Queued downloads for " + queued + " language(s)");
    if (typeof loadQueue === "function") loadQueue();
  } catch (e) {
    showToast("Failed to queue downloads: " + e.message);
  } finally {
    downloadAllLangsBtn.disabled = false;
    downloadAllBtn.disabled = false;
    downloadSelectedBtn.disabled = false;
  }
}
