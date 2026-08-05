// DubSync page: pick a local folder, search the show, auto-select the
// episodes whose files exist locally, queue the graft job.

let dsScan = null; // {files: [{name, rel, season, episode}], unparsed: [{name, rel}]}
let dsShow = null; // {url, title, poster_url}
let dsSeasons = []; // [{url, season_number, episode_count, are_movies}]
let dsEpisodes = {}; // season_number -> [{episode_number, url, title_de, title_en, available_languages}]
let dsPairs = {}; // "s:e" -> local filename (auto-match result)
let dsBrowserCurrent = null; // path shown in the browser modal

function showToast(msg) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3200);
}

function dsT(key, fallback) {
  return typeof window.t === "function" ? window.t(key, fallback) : fallback;
}

// ===== Init =====

async function dsInit() {
  let defaults = {};
  try {
    const resp = await fetch("/api/settings");
    const data = await resp.json();
    defaults = data.dubsync || {};
  } catch (e) {
    /* settings are optional prefill only */
  }

  document.getElementById("dsOffset").value = defaults.offset || "";
  document.getElementById("dsAutoAlign").checked = defaults.auto_align !== "0";
  document.getElementById("dsAllowResample").checked =
    defaults.allow_resample === "1";
  document.getElementById("dsCleanup").checked = defaults.cleanup === "1";

  const folder =
    localStorage.getItem("dubsyncFolder") || defaults.target_dir || "";
  if (folder) {
    document.getElementById("dsFolder").value = folder;
    dsRescan();
  }
  dsUpdateSummary();
}

// ===== Step 1: folder + scan =====

function dsFolderChanged() {
  const folder = document.getElementById("dsFolder").value.trim();
  if (folder) localStorage.setItem("dubsyncFolder", folder);
  dsRescan();
}

async function dsRescan() {
  const folder = document.getElementById("dsFolder").value.trim();
  const info = document.getElementById("dsScanInfo");
  const filesBox = document.getElementById("dsScanFiles");
  dsScan = null;
  filesBox.textContent = "";
  if (!folder) {
    info.textContent = "";
    if (dsSeasons.length) dsRenderEpisodes();
    dsApplyAutoSelection();
    return;
  }

  info.textContent = dsT("dubsync.scanning", "Scanning folder…");
  const recursive = document.getElementById("dsRecursive").checked ? "1" : "0";
  try {
    const resp = await fetch(
      "/api/dubsync/scan?path=" +
        encodeURIComponent(folder) +
        "&recursive=" +
        recursive
    );
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    dsScan = data;
  } catch (e) {
    info.textContent = dsT("dubsync.scan_failed", "Scan failed: ") + e.message;
    if (dsSeasons.length) dsRenderEpisodes();
    dsApplyAutoSelection();
    return;
  }

  // Neutral summary: a folder full of movies legitimately has no episode
  // numbers, so lead with the total and only break down parsing when useful.
  const nParsed = dsScan.files.length;
  const nUnparsed = dsScan.unparsed.length;
  const total = nParsed + nUnparsed;
  let text =
    total +
    " " +
    (total === 1
      ? dsT("dubsync.scan_found_one", "video file found")
      : dsT("dubsync.scan_found_many", "video files found"));
  if (nParsed && nUnparsed) {
    text +=
      " (" +
      nParsed +
      " " +
      dsT("dubsync.scan_with_ep", "with episode numbers") +
      ", " +
      nUnparsed +
      " " +
      dsT("dubsync.scan_without_ep", "without") +
      ")";
  } else if (!nParsed && nUnparsed) {
    text +=
      " (" +
      dsT(
        "dubsync.scan_movies_ok",
        "no episode numbers in the filenames — fine for movies"
      ) +
      ")";
  }
  info.textContent = text;

  // Movie dropdowns list every video file; rebuild them for the new scan.
  if (dsSeasons.length) dsRenderEpisodes();

  // Compact chip list: "S1E01 · file.mkv" for parsed files, "🎬 file.mkv"
  // for files without an episode number (typically movies).
  const chips = dsScan.files
    .map((f) => {
      const season = f.season === null ? "?" : f.season;
      return (
        "S" + season + "E" + String(f.episode).padStart(2, "0") + " · " + f.name
      );
    })
    .concat(dsScan.unparsed.map((u) => "🎬 " + u.name));
  for (const label of chips.slice(0, 60)) {
    const chip = document.createElement("span");
    chip.style.cssText =
      "display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;" +
      "border-radius:8px;background:rgba(37,99,235,0.12);color:#9db8e8;" +
      "font-size:0.75rem;";
    chip.textContent = label;
    filesBox.appendChild(chip);
  }
  if (chips.length > 60) {
    const more = document.createElement("span");
    more.className = "settings-hint";
    more.textContent = "+" + (chips.length - 60) + " …";
    filesBox.appendChild(more);
  }

  dsApplyAutoSelection();
}

// ===== Folder browser modal =====

async function dsBrowse(path) {
  const list = document.getElementById("dsBrowserList");
  list.textContent = "";
  try {
    const resp = await fetch(
      "/api/dubsync/browse" +
        (path ? "?path=" + encodeURIComponent(path) : "")
    );
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);

    dsBrowserCurrent = data.path;
    document.getElementById("dsBrowserPath").textContent = data.path;
    const upBtn = document.getElementById("dsBrowserUp");
    upBtn.disabled = !data.parent;
    upBtn.dataset.parent = data.parent || "";

    const videos = document.getElementById("dsBrowserVideos");
    videos.textContent = data.video_count
      ? data.video_count +
        " " +
        dsT("dubsync.browser_videos", "video file(s) in this folder")
      : "";

    if (!data.dirs.length) {
      const empty = document.createElement("div");
      empty.className = "settings-hint";
      empty.style.cssText = "padding: 12px";
      empty.textContent = dsT("dubsync.browser_empty", "No subfolders");
      list.appendChild(empty);
    }
    for (const dir of data.dirs) {
      const row = document.createElement("div");
      row.style.cssText =
        "padding:9px 14px;cursor:pointer;color:#c8cad0;font-size:0.88rem;" +
        "border-bottom:1px solid rgba(255,255,255,0.05);";
      row.textContent = "📁 " + dir.name;
      row.onmouseenter = () =>
        (row.style.background = "rgba(255,255,255,0.05)");
      row.onmouseleave = () => (row.style.background = "");
      row.onclick = () => dsBrowse(dir.path);
      list.appendChild(row);
    }
  } catch (e) {
    const err = document.createElement("div");
    err.className = "settings-hint";
    err.style.cssText = "padding: 12px";
    err.textContent = e.message;
    list.appendChild(err);
  }
}

function dsOpenBrowser() {
  document.getElementById("dsBrowserOverlay").style.display = "block";
  dsBrowse(document.getElementById("dsFolder").value.trim() || null);
}

function dsCloseBrowser() {
  document.getElementById("dsBrowserOverlay").style.display = "none";
}

function dsBrowserUp() {
  const parent = document.getElementById("dsBrowserUp").dataset.parent;
  if (parent) dsBrowse(parent);
}

function dsBrowserSelect() {
  if (!dsBrowserCurrent) return;
  document.getElementById("dsFolder").value = dsBrowserCurrent;
  dsCloseBrowser();
  dsFolderChanged();
}

// ===== Step 2: show search =====

async function dsSearchShows() {
  const keyword = document.getElementById("dsSearch").value.trim();
  const site = document.getElementById("dsSite").value;
  const box = document.getElementById("dsResults");
  if (!keyword) return;

  box.textContent = dsT("dubsync.searching", "Searching…");
  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, site }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);

    box.textContent = "";
    if (!data.results.length) {
      box.className = "settings-hint";
      box.textContent = dsT("dubsync.no_results", "No results");
      return;
    }
    box.className = "";
    for (const item of data.results.slice(0, 12)) {
      const row = document.createElement("div");
      row.style.cssText =
        "padding:9px 14px;cursor:pointer;color:#c8cad0;font-size:0.9rem;" +
        "border:1px solid rgba(255,255,255,0.07);border-radius:10px;" +
        "margin-bottom:6px;";
      row.textContent = item.title;
      row.onmouseenter = () =>
        (row.style.background = "rgba(255,255,255,0.05)");
      row.onmouseleave = () => (row.style.background = "");
      row.onclick = () => dsSelectShow(item);
      box.appendChild(row);
    }
  } catch (e) {
    box.className = "settings-hint";
    box.textContent = dsT("dubsync.search_failed", "Search failed: ") + e.message;
  }
}

async function dsSelectShow(item) {
  dsShow = { url: item.url, title: item.title, poster_url: "" };
  dsSeasons = [];
  dsEpisodes = {};
  dsPairs = {};

  document.getElementById("dsResults").textContent = "";
  const header = document.getElementById("dsShowHeader");
  header.style.display = "flex";
  header.style.cssText +=
    ";align-items:center;gap:14px;";
  header.textContent = "";

  const img = document.createElement("img");
  img.style.cssText =
    "width:52px;height:74px;object-fit:cover;border-radius:8px;display:none;";
  header.appendChild(img);

  const meta = document.createElement("div");
  const title = document.createElement("div");
  title.style.cssText = "color:#fff;font-weight:600;";
  title.textContent = item.title;
  meta.appendChild(title);
  const state = document.createElement("div");
  state.className = "settings-hint";
  state.style.margin = "4px 0 0";
  state.textContent = dsT("dubsync.loading_seasons", "Loading episode list…");
  meta.appendChild(state);
  header.appendChild(meta);

  const change = document.createElement("button");
  change.textContent = dsT("dubsync.change_show", "Change");
  change.style.cssText =
    "margin-left:auto;padding:8px 16px;border-radius:10px;cursor:pointer;" +
    "border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);" +
    "color:#c8cad0;font-size:0.82rem;";
  change.onclick = () => {
    dsShow = null;
    dsSeasons = [];
    dsEpisodes = {};
    dsPairs = {};
    header.style.display = "none";
    document.getElementById("dsEpisodesSection").style.display = "none";
    dsUpdateSummary();
  };
  header.appendChild(change);

  try {
    const [seriesResp, seasonsResp] = await Promise.all([
      fetch("/api/series?url=" + encodeURIComponent(item.url)),
      fetch("/api/seasons?url=" + encodeURIComponent(item.url)),
    ]);
    const series = await seriesResp.json();
    const seasonsData = await seasonsResp.json();
    if (!seasonsResp.ok)
      throw new Error(seasonsData.error || seasonsResp.statusText);

    if (seriesResp.ok && series.poster_url) {
      img.src = series.poster_url;
      img.style.display = "block";
    }
    dsSeasons = (seasonsData.seasons || []).filter(
      (s) => s.season_number !== null && s.season_number !== undefined
    );

    const episodeResults = await Promise.all(
      dsSeasons.map((s) =>
        fetch("/api/episodes?url=" + encodeURIComponent(s.url))
          .then((r) => r.json())
          .catch(() => ({ episodes: [] }))
      )
    );
    dsSeasons.forEach((s, i) => {
      dsEpisodes[s.season_number] = episodeResults[i].episodes || [];
    });

    if (dsSeasons.length && dsSeasons.every((s) => s.are_movies)) {
      state.textContent = dsT("dubsync.movie_source", "Movie");
    } else {
      state.textContent =
        dsSeasons.length +
        " " +
        (dsSeasons.length === 1
          ? dsT("dubsync.season_one", "season")
          : dsT("dubsync.season_many", "seasons"));
    }
    dsRenderEpisodes();
    dsApplyAutoSelection();
  } catch (e) {
    state.textContent =
      dsT("dubsync.load_failed", "Failed to load episodes: ") + e.message;
  }
}

// ===== Step 3: episode checklist =====

function dsRenderEpisodes() {
  const section = document.getElementById("dsEpisodesSection");
  const box = document.getElementById("dsSeasons");
  box.textContent = "";
  section.style.display = "block";

  for (const season of dsSeasons) {
    const sn = season.season_number;
    const episodes = dsEpisodes[sn] || [];
    const block = document.createElement("div");
    block.style.cssText = "margin-bottom: 16px";

    const head = document.createElement("label");
    head.style.cssText =
      "display:flex;align-items:center;gap:8px;color:#fff;font-weight:600;" +
      "font-size:0.92rem;cursor:pointer;margin-bottom:8px;";
    const all = document.createElement("input");
    all.type = "checkbox";
    all.style.cssText = "accent-color:#2563eb;cursor:pointer;";
    all.dataset.season = sn;
    all.onchange = () => {
      block.querySelectorAll("input[data-ep]").forEach((cb) => {
        // movie checkboxes stay disabled until a local file is chosen
        if (!cb.disabled) cb.checked = all.checked;
      });
      dsUpdateSummary();
    };
    head.appendChild(all);
    head.appendChild(
      document.createTextNode(
        season.are_movies
          ? dsT("dubsync.movies", "Movies")
          : dsT("dubsync.season_label", "Season") + " " + sn
      )
    );
    block.appendChild(head);

    if (season.are_movies) {
      // Movies carry no episode pattern in their filenames, so each one
      // gets an explicit local-file dropdown instead of automatic matching.
      const hint = document.createElement("div");
      hint.className = "settings-hint";
      hint.style.cssText = "margin:-2px 0 8px;";
      hint.textContent = dsT(
        "dubsync.movies_hint",
        "Pick the local file for each movie; the best title match is pre-selected."
      );
      block.appendChild(hint);

      const fileRels = dsAllFileRels();
      for (const ep of episodes) {
        const row = document.createElement("div");
        row.style.cssText =
          "display:flex;align-items:center;gap:10px;color:#c8cad0;" +
          "font-size:0.85rem;margin-bottom:6px;flex-wrap:wrap;";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.style.cssText = "accent-color:#2563eb;cursor:pointer;flex-shrink:0;";
        cb.dataset.ep = ep.episode_number;
        cb.dataset.season = sn;
        cb.dataset.movie = "1";
        cb.disabled = true;
        cb.title = dsT("dubsync.movie_need_file", "Choose a local file first");
        cb.onchange = dsUpdateSummary;
        row.appendChild(cb);

        const label = document.createElement("span");
        label.style.cssText =
          "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" +
          "flex:1 1 180px;min-width:0;";
        const epTitle = ep.title_de || ep.title_en || "";
        label.textContent =
          epTitle || dsT("dubsync.movie_n", "Movie") + " " + ep.episode_number;
        row.appendChild(label);

        const langs = ep.available_languages || [];
        if (langs.length && !langs.includes("German Dub")) {
          const warn = document.createElement("span");
          warn.title = dsT("dubsync.no_dub", "No German Dub available");
          warn.textContent = "⚠";
          warn.style.cssText = "color:#eab308;flex-shrink:0;";
          row.appendChild(warn);
        }

        const sel = document.createElement("select");
        sel.className = "sync-select";
        sel.style.cssText = "flex:0 1 320px;min-width:180px;font-size:0.82rem;";
        sel.dataset.movieSel = sn + ":" + ep.episode_number;
        const none = document.createElement("option");
        none.value = "";
        none.textContent = dsT("dubsync.movie_no_file", "— choose local file —");
        sel.appendChild(none);
        for (const rel of fileRels) {
          const opt = document.createElement("option");
          opt.value = rel;
          opt.textContent = rel;
          sel.appendChild(opt);
        }
        sel.onchange = () => {
          cb.disabled = !sel.value;
          cb.checked = !!sel.value;
          dsUpdateSummary();
        };
        row.appendChild(sel);

        block.appendChild(row);
      }
      box.appendChild(block);
      continue;
    }

    const grid = document.createElement("div");
    grid.style.cssText =
      "display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));" +
      "gap:4px 16px;";
    for (const ep of episodes) {
      const row = document.createElement("label");
      row.style.cssText =
        "display:flex;align-items:center;gap:8px;color:#c8cad0;" +
        "font-size:0.85rem;cursor:pointer;min-width:0;";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.style.cssText = "accent-color:#2563eb;cursor:pointer;flex-shrink:0;";
      cb.dataset.ep = ep.episode_number;
      cb.dataset.season = sn;
      cb.onchange = dsUpdateSummary;
      row.appendChild(cb);

      const label = document.createElement("span");
      label.style.cssText =
        "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
      const epTitle = ep.title_de || ep.title_en || "";
      label.textContent =
        "E" + String(ep.episode_number).padStart(2, "0") +
        (epTitle ? " · " + epTitle : "");
      row.appendChild(label);

      const langs = ep.available_languages || [];
      if (langs.length && !langs.includes("German Dub")) {
        const warn = document.createElement("span");
        warn.title = dsT("dubsync.no_dub", "No German Dub available");
        warn.textContent = "⚠";
        warn.style.cssText = "color:#eab308;flex-shrink:0;";
        row.appendChild(warn);
      }

      const marker = document.createElement("span");
      marker.dataset.pairMarker = sn + ":" + ep.episode_number;
      marker.style.cssText =
        "display:none;color:#4ade80;font-size:0.75rem;flex-shrink:0;";
      marker.textContent = "●";
      row.appendChild(marker);

      grid.appendChild(row);
    }
    block.appendChild(grid);
    box.appendChild(block);
  }
}

// Every scanned video file (parsed or not) as a path relative to the folder,
// for the movie pairing dropdowns.
function dsAllFileRels() {
  if (!dsScan) return [];
  const rels = dsScan.files
    .map((f) => f.rel || f.name)
    .concat(dsScan.unparsed.map((u) => u.rel || u.name));
  return [...new Set(rels)].sort();
}

// ===== Movie title matching (fuzzy filename <-> title guess) =====

const DS_NOISE_TOKENS = new Set([
  "1080p", "720p", "2160p", "480p", "bluray", "blu", "ray", "bdrip", "brrip",
  "web", "webrip", "webdl", "dl", "hdtv", "x264", "x265", "h264", "h265",
  "hevc", "avc", "aac", "ac3", "eac3", "dts", "flac", "opus", "german",
  "deutsch", "english", "ger", "eng", "japanese", "jap", "dub", "sub",
  "subbed", "dubbed", "dual", "multi", "remux", "hdr", "uhd", "sdr",
  "the", "der", "die", "das", "film", "movie",
]);

function dsNormTokens(s) {
  let text = String(s || "").toLowerCase();
  text = text.replace(/\.[a-z0-9]{2,4}$/, ""); // extension
  text = text.replace(/\[[^\]]*\]|\([^)]*\)/g, " "); // release groups, years
  text = text.replace(/[^a-z0-9äöüß]+/g, " ");
  return text
    .split(/\s+/)
    .filter(
      (t) => t && !DS_NOISE_TOKENS.has(t) && !/^(19|20)\d\d$/.test(t)
    );
}

// Dice coefficient over token sets: 0 (nothing shared) .. 1 (same tokens).
function dsTitleScore(a, b) {
  const ta = new Set(dsNormTokens(a));
  const tb = new Set(dsNormTokens(b));
  if (!ta.size || !tb.size) return 0;
  let inter = 0;
  ta.forEach((t) => {
    if (tb.has(t)) inter++;
  });
  return (2 * inter) / (ta.size + tb.size);
}

// Mirror of the backend matcher's season resolution: filename season if
// present, else the source's single season, else 1 — plus the
// absolute-numbering fallback for globally-unique episode numbers.
function dsApplyAutoSelection() {
  const warnings = document.getElementById("dsMatchWarnings");
  warnings.textContent = "";
  dsPairs = {};

  document
    .querySelectorAll("#dsSeasons [data-pair-marker]")
    .forEach((m) => (m.style.display = "none"));

  if (!dsSeasons.length) {
    dsUpdateSummary();
    return;
  }

  // Movie collections pair via the explicit dropdowns below, never via
  // filename episode numbers.
  const epSeasons = dsSeasons.filter((s) => !s.are_movies);

  const byKey = new Set();
  const absCount = {};
  for (const season of epSeasons) {
    for (const ep of dsEpisodes[season.season_number] || []) {
      byKey.add(season.season_number + ":" + ep.episode_number);
      absCount[ep.episode_number] = (absCount[ep.episode_number] || []).concat(
        season.season_number
      );
    }
  }
  const singleSeason =
    epSeasons.length === 1 ? epSeasons[0].season_number : null;

  document
    .querySelectorAll("#dsSeasons input[data-ep]:not([data-movie])")
    .forEach((cb) => (cb.checked = false));

  const unpaired = [];
  for (const f of (dsScan && dsScan.files) || []) {
    let season = f.season !== null ? f.season : singleSeason !== null ? singleSeason : 1;
    let key = season + ":" + f.episode;
    if (!byKey.has(key) && f.season === null) {
      const seasonsWithEp = absCount[f.episode] || [];
      if (seasonsWithEp.length === 1) {
        key = seasonsWithEp[0] + ":" + f.episode;
      }
    }
    if (byKey.has(key) && !(key in dsPairs)) {
      dsPairs[key] = f.name;
    } else if (!byKey.has(key)) {
      unpaired.push(f);
    }
  }

  for (const key of Object.keys(dsPairs)) {
    const [s, e] = key.split(":");
    const cb = document.querySelector(
      '#dsSeasons input[data-season="' + s + '"][data-ep="' + e + '"]'
    );
    if (cb) cb.checked = true;
    const marker = document.querySelector(
      '#dsSeasons [data-pair-marker="' + key + '"]'
    );
    if (marker) {
      marker.style.display = "inline";
      marker.title =
        dsT("dubsync.local_file", "Local file: ") + dsPairs[key];
    }
  }

  // Movie auto-pairing: guess each movie's local file by title similarity.
  const movieEntries = [];
  for (const season of dsSeasons) {
    if (!season.are_movies) continue;
    for (const ep of dsEpisodes[season.season_number] || []) {
      movieEntries.push({
        key: season.season_number + ":" + ep.episode_number,
        title: ep.title_de || ep.title_en || "",
      });
    }
  }
  const fileRels = dsAllFileRels();
  const usedRels = new Set();
  if (movieEntries.length === 1 && fileRels.length === 1) {
    // one movie, one file: unambiguous
    dsSetMoviePair(movieEntries[0].key, fileRels[0]);
    usedRels.add(fileRels[0]);
  } else {
    for (const movie of movieEntries) {
      let best = null;
      let bestScore = 0;
      for (const rel of fileRels) {
        if (usedRels.has(rel)) continue;
        const score = dsTitleScore(movie.title, rel);
        if (score > bestScore) {
          best = rel;
          bestScore = score;
        }
      }
      if (best && bestScore >= 0.35) {
        dsSetMoviePair(movie.key, best);
        usedRels.add(best);
      }
    }
  }

  const notes = [];
  const unpairedLeft = unpaired.filter((f) => !usedRels.has(f.rel || f.name));
  if (unpairedLeft.length) {
    notes.push(
      unpairedLeft.length +
        " " +
        dsT("dubsync.unpaired", "local file(s) have no matching episode: ") +
        unpairedLeft
          .slice(0, 5)
          .map((f) => f.name)
          .join(", ") +
        (unpairedLeft.length > 5 ? ", …" : "")
    );
  }
  // When the source has a Movies section, files without episode numbers are
  // normal candidates for the movie dropdowns, not a problem to warn about.
  const hasMovies = dsSeasons.some((s) => s.are_movies);
  const unparsedLeft = hasMovies
    ? []
    : ((dsScan && dsScan.unparsed) || []).filter(
        (u) => !usedRels.has(u.rel || u.name)
      );
  if (unparsedLeft.length) {
    notes.push(
      dsT("dubsync.unparsed_note", "Not recognised: ") +
        unparsedLeft
          .slice(0, 5)
          .map((u) => u.name)
          .join(", ") +
        (unparsedLeft.length > 5 ? ", …" : "")
    );
  }
  for (const note of notes) {
    const div = document.createElement("div");
    div.className = "settings-hint";
    div.style.cssText = "color:#eab308;margin-top:4px;";
    div.textContent = "⚠ " + note;
    warnings.appendChild(div);
  }

  dsUpdateSummary();
}

// Reflect a movie's auto-guessed local file in its dropdown + checkbox.
function dsSetMoviePair(key, rel) {
  const sel = document.querySelector(
    '#dsSeasons select[data-movie-sel="' + key + '"]'
  );
  if (!sel) return;
  sel.value = rel;
  const [s, e] = key.split(":");
  const cb = document.querySelector(
    '#dsSeasons input[data-movie][data-season="' + s + '"][data-ep="' + e + '"]'
  );
  if (cb) {
    cb.disabled = false;
    cb.checked = true;
  }
}

function dsSelectedEpisodes() {
  const selected = [];
  document
    .querySelectorAll("#dsSeasons input[data-ep]:not([data-movie])")
    .forEach((cb) => {
      if (cb.checked)
        selected.push([
          parseInt(cb.dataset.season, 10),
          parseInt(cb.dataset.ep, 10),
        ]);
    });
  return selected;
}

// Checked movies with a confirmed local file, as [season, episode, filename].
function dsSelectedMovies() {
  const selected = [];
  document
    .querySelectorAll("#dsSeasons input[data-ep][data-movie]")
    .forEach((cb) => {
      if (!cb.checked) return;
      const key = cb.dataset.season + ":" + cb.dataset.ep;
      const sel = document.querySelector(
        '#dsSeasons select[data-movie-sel="' + key + '"]'
      );
      if (sel && sel.value)
        selected.push([
          parseInt(cb.dataset.season, 10),
          parseInt(cb.dataset.ep, 10),
          sel.value,
        ]);
    });
  return selected;
}

function dsUpdateSummary() {
  const nEp = dsSelectedEpisodes().length;
  const nMov = dsSelectedMovies().length;
  const folder = document.getElementById("dsFolder").value.trim();
  const summary = document.getElementById("dsSummary");
  const btn = document.getElementById("dsEnqueueBtn");

  if (!dsShow || !folder) {
    summary.textContent = dsT(
      "dubsync.summary_incomplete",
      "Pick a folder and a show first"
    );
    btn.disabled = true;
    return;
  }
  const parts = [];
  if (nEp || !nMov) {
    parts.push(
      nEp +
        " " +
        (nEp === 1
          ? dsT("dubsync.summary_one", "episode selected")
          : dsT("dubsync.summary_many", "episodes selected"))
    );
  }
  if (nMov) {
    parts.push(
      nMov +
        " " +
        (nMov === 1
          ? dsT("dubsync.summary_movie_one", "movie selected")
          : dsT("dubsync.summary_movie_many", "movies selected"))
    );
  }
  summary.textContent = parts.join(", ");
  btn.disabled = nEp + nMov === 0;
}

// ===== Enqueue =====

async function dsEnqueue() {
  const folder = document.getElementById("dsFolder").value.trim();
  const episodes = dsSelectedEpisodes();
  const pairs = dsSelectedMovies();
  if (!dsShow || !folder || (!episodes.length && !pairs.length)) return;

  const btn = document.getElementById("dsEnqueueBtn");
  btn.disabled = true;
  try {
    const resp = await fetch("/api/dubsync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: dsShow.url,
        target_dir: folder,
        offset: document.getElementById("dsOffset").value.trim(),
        auto_align: document.getElementById("dsAutoAlign").checked,
        allow_resample: document.getElementById("dsAllowResample").checked,
        cleanup: document.getElementById("dsCleanup").checked,
        recursive: document.getElementById("dsRecursive").checked,
        episodes: episodes,
        pairs: pairs,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    showToast("✓ " + dsT("dubsync.queued", "DubSync job added to queue"));
    dsShowQueuedConfirmation();
  } catch (e) {
    showToast(dsT("dubsync.queue_failed", "Failed to enqueue: ") + e.message);
    dsUpdateSummary();
  } finally {
    btn.disabled = false;
  }
}

// Inline confirmation next to the button: green check + a link that opens
// the queue. Any later selection change redraws the summary over it.
function dsShowQueuedConfirmation() {
  const summary = document.getElementById("dsSummary");
  summary.textContent = "";

  const ok = document.createElement("span");
  ok.style.cssText = "color:#4ade80;font-weight:600;";
  ok.textContent = "✓ " + dsT("dubsync.queued", "DubSync job added to queue");
  summary.appendChild(ok);

  const link = document.createElement("a");
  link.href = "#";
  link.textContent = dsT("dubsync.view_queue", "View queue");
  link.style.cssText = "margin-left:12px;color:#6ea8fe;";
  link.onclick = (ev) => {
    ev.preventDefault();
    if (typeof openQueueModal === "function") openQueueModal();
  };
  summary.appendChild(link);

  // brief visual feedback on the button itself
  const btn = document.getElementById("dsEnqueueBtn");
  const original = btn.textContent;
  btn.textContent = "✓ " + dsT("dubsync.added", "Added");
  setTimeout(() => {
    btn.textContent = original;
  }, 2000);
}

document.addEventListener("DOMContentLoaded", dsInit);
