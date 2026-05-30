const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const searchSpinner = document.getElementById("searchSpinner");
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
const BROWSE_REFRESH_MS = 60000;

let currentSeasons = [];
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

// Site toggle state
let currentSite = "aniworld";

// Downloaded folders cache
let downloadedFolders = [];

// Custom paths select
const customPathSelect = document.getElementById("customPathSelect");

async function loadCustomPaths() {
  if (!customPathSelect) return;
  try {
    const resp = await fetch("/api/custom-paths");
    const data = await resp.json();
    const paths = data.paths || [];
    // Remove old custom options (keep "Default")
    while (customPathSelect.options.length > 1) customPathSelect.remove(1);
    if (paths.length) {
      paths.forEach(function (p) {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name;
        customPathSelect.appendChild(opt);
      });
      customPathSelect.style.display = "";
    } else {
      customPathSelect.style.display = "none";
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
  stoLoadedAt = Date.now();
  stoBrowsePromise = (async () => {
    try {
      const [newResp, popResp] = await Promise.all([
        fetch("/api/new-series"),
        fetch("/api/popular-series"),
      ]);
      await loadDownloadedFolders();
      const newData = await newResp.json();
      const popData = await popResp.json();
      if (newData.results) renderBrowseCards(newSeriesGrid, newData.results);
      if (popData.results) renderBrowseCards(popularSeriesGrid, popData.results);
    } catch (e) {
      stoLoadedAt = 0;
    } finally {
      stoBrowsePromise = null;
    }
  })();
  return stoBrowsePromise;
}

function showBrowseSections() {
  const isAniworld = currentSite === "aniworld";
  browseDiv.style.display = "";
  newAnimesSection.style.display = isAniworld ? "" : "none";
  popularAnimesSection.style.display = isAniworld ? "" : "none";
  newSeriesSection.style.display = isAniworld ? "none" : "";
  popularSeriesSection.style.display = isAniworld ? "none" : "";
  if (isAniworld) loadAniworldBrowse();
  else loadStoBrowse();
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

function toggleSite() {
  const toggle = document.getElementById("siteToggle");
  currentSite = toggle.checked ? "sto" : "aniworld";
  localStorage.setItem("selectedSite", currentSite);

  // Update labels
  document
    .getElementById("labelAniworld")
    .classList.toggle("active", !toggle.checked);
  document
    .getElementById("labelSto")
    .classList.toggle("active", toggle.checked);

  // Update heading
  const heading = document.getElementById("pageHeading");
  if (heading)
    heading.textContent = toggle.checked
      ? "SerienStream Downloader"
      : "AniWorld Downloader";

  // Update search placeholder
  searchInput.placeholder = toggle.checked
    ? "Search for series..."
    : "Search for anime...";

  // Clear search results
  resultsDiv.innerHTML = "";
  searchInput.value = "";

  // Toggle browse sections per site
  showBrowseSections();

  // Toggle Random button
  randomBtn.style.display = toggle.checked ? "none" : "";

  // Update language dropdown
  rebuildLanguageSelect();

  // Reset providers
  availableProviders = null;
}

function rebuildLanguageSelect() {
  const langs =
    currentSite === "sto"
      ? window.STO_LANGS || {}
      : window.ANIWORLD_LANGS || {};
  const previousValue = languageSelect.value;
  const preferredValue = previousValue || window.DEFAULT_WEB_LANGUAGE || "German Dub";
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

// Restore site toggle state from localStorage
(function syncSiteToggle() {
  const toggle = document.getElementById("siteToggle");
  const saved = localStorage.getItem("selectedSite");
  if (saved === "sto") toggle.checked = true;
  if (toggle && toggle.checked) {
    currentSite = "sto";
    document.getElementById("labelAniworld").classList.remove("active");
    document.getElementById("labelSto").classList.add("active");
    const heading = document.getElementById("pageHeading");
    if (heading) heading.textContent = "SerienStream Downloader";
    searchInput.placeholder = "Search for series...";
    randomBtn.style.display = "none";
    rebuildLanguageSelect();
  }
})();

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
      `<img src="${esc(item.poster_url)}" alt="">` +
      `<div class="browse-info">` +
      `<div class="browse-title">${esc(item.title)}</div>` +
      `<div class="browse-genre">${esc(item.genre)}</div>` +
      `</div>`;
    addDownloadedBadge(card, item.title);
    grid.appendChild(card);
  });
}

let aniLoadedAt = 0;
let aniBrowsePromise = null;
async function loadAniworldBrowse(force = false) {
  if (!force && aniLoadedAt && Date.now() - aniLoadedAt < BROWSE_REFRESH_MS) return;
  if (aniBrowsePromise) return aniBrowsePromise;
  aniLoadedAt = Date.now();
  aniBrowsePromise = (async () => {
    try {
      const [newResp, popResp] = await Promise.all([
        fetch("/api/new-animes"),
        fetch("/api/popular-animes"),
      ]);
      await loadDownloadedFolders();
      const newData = await newResp.json();
      const popData = await popResp.json();
      if (newData.results) renderBrowseCards(newAnimesGrid, newData.results);
      if (popData.results) renderBrowseCards(popularAnimesGrid, popData.results);
    } catch (e) {
      aniLoadedAt = 0;
    } finally {
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
  else loadStoBrowse(force);
}

setInterval(() => {
  refreshVisibleBrowse(true);
}, BROWSE_REFRESH_MS);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshVisibleBrowse(true);
});

window.addEventListener("focus", () => {
  refreshVisibleBrowse(true);
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
    showToast("Random is not available for S.TO");
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
    card.innerHTML = `<img src="" alt="" data-url="${esc(r.url)}"><div class="info"><div class="title">${esc(r.title)}</div></div>`;
    addDownloadedBadge(card, r.title);
    resultsDiv.appendChild(card);
    loadPoster(r.url, card.querySelector("img"));
  });
}

async function loadPoster(url, imgEl) {
  try {
    const resp = await fetch("/api/series?url=" + encodeURIComponent(url));
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
  await checkLangSeparation();
  rebuildLanguageSelect();
  resetProviderDropdown();
  loadCustomPaths();

  try {
    const [seriesResp, seasonsResp] = await Promise.all([
      fetch("/api/series?url=" + encodeURIComponent(url)),
      fetch("/api/seasons?url=" + encodeURIComponent(url)),
    ]);
    const seriesData = await seriesResp.json();
    const seasonsData = await seasonsResp.json();
    if (openToken !== currentOpenSeriesToken) return;

    currentSeriesTitle = seriesData.title || "Unknown";
    const titleEl = document.getElementById("modalTitle");
    titleEl.innerHTML = `<a href="${currentSeriesUrl}" target="_blank" rel="noopener noreferrer">${currentSeriesTitle}</a>`;
    if (seriesData.poster_url)
      document.getElementById("modalPoster").src = seriesData.poster_url;
    document.getElementById("modalGenres").textContent = (
      seriesData.genres || []
    ).join(", ");
    document.getElementById("modalYear").textContent =
      seriesData.release_year || "";
    document.getElementById("modalDesc").textContent =
      seriesData.description || "";

    currentSeasons = seasonsData.seasons || [];
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
    const label = season.are_movies
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

async function loadSeasonEpisodes(index, openToken = currentOpenSeriesToken) {
  if (seasonEpisodesCache[index]) return seasonEpisodesCache[index];
  if (seasonEpisodesLoading[index]) return seasonEpisodesLoading[index];
  const season = currentSeasons[index];
  const body = document.getElementById("seasonBody-" + index);
  if (!season || !body) return [];

  seasonEpisodesLoading[index] = fetch(
    "/api/episodes?url=" + encodeURIComponent(season.url),
  )
    .then((r) => r.json())
    .then((data) => {
      if (openToken !== currentOpenSeriesToken) return [];
      const episodes = data.episodes || [];
      seasonEpisodesCache[index] = episodes;
      renderSeasonEpisodes(index, episodes);
      if (!providersLoadedForSeries && episodes.length) {
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
    const title = ep.title_en || ep.title_de || "";
    const languageBadges = renderEpisodeLanguageBadges(ep.available_languages || []);
    const dlIcon = ep.downloaded
      ? '<span class="ep-downloaded" title="Downloaded">&#10003;</span>'
      : "";
    div.innerHTML = `<input type="checkbox" value="${esc(ep.url)}" data-season="${index}"><span class="ep-num">E${ep.episode_number}</span>${dlIcon}<div class="ep-main"><span class="ep-title">${esc(title)}</span>${languageBadges}</div>`;
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
    : `Season ${season.season_number} (${episodes.length} episodes)`;
  header.innerHTML =
    `<div class="season-label"><span class="season-arrow">&#9654;</span> ${esc(label)}${seasonDlIcon}</div>` +
    `<label class="season-all-label" onclick="event.stopPropagation()"><input type="checkbox" onchange="toggleSeasonAll(this, ${index})"> All</label>`;
}

function renderEpisodeLanguageBadges(labels) {
  if (!labels.length) return "";
  return `<span class="ep-language-badges">${labels
    .map((label) => {
      const display = getEpisodeLanguageBadgeText(label);
      const cls = getEpisodeLanguageBadgeClass(label);
      return `<span class="ep-language-badge ${cls}" title="${esc(label)}">${esc(display)}</span>`;
    })
    .join("")}</span>`;
}

function getEpisodeLanguageBadgeText(label) {
  const badgeMap = {
    "German Dub": "🇩🇪 Dub",
    "German Sub": "🇯🇵🇩🇪 Sub",
    "English Dub": "🇬🇧 Dub",
    "English Sub": "🇯🇵🇬🇧 Sub",
  };
  return badgeMap[label] || label;
}

function getEpisodeLanguageBadgeClass(label) {
  const classMap = {
    "German Dub": "badge-german-dub",
    "German Sub": "badge-german-sub",
    "English Dub": "badge-english-dub",
    "English Sub": "badge-english-sub",
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
  return Array.from(
    seasonAccordion.querySelectorAll(".episode-item input[type=checkbox]"),
  ).map((cb) => cb.value);
}

function getSelectedEpisodeUrls() {
  return Array.from(
    seasonAccordion.querySelectorAll(
      ".episode-item input[type=checkbox]:checked",
    ),
  ).map((cb) => cb.value);
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
  staticProviders.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    providerSelect.appendChild(opt);
  });
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
    staticProviders.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      providerSelect.appendChild(opt);
    });
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

  const language = languageSelect.value;
  const provider = providerSelect.value;

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
      const body = {
        title: currentSeriesTitle,
        series_url: currentSeriesUrl,
        language: languageSelect.value,
        provider: providerSelect.value,
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
        // Job already exists — update it with current modal settings
        const updateBody = {
          language: languageSelect.value,
          provider: providerSelect.value,
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
    // Remove sync job
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
