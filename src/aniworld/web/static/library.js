let libraryLocations = [];
var libraryLangSep = false;

// --- Expanded state save/restore (uses semantic keys, survives index shifts) ---

function getExpandedState() {
  var state = { locations: {}, langFolders: {}, titles: {}, seasons: {} };
  libraryLocations.forEach(function (loc, li) {
    var locBody = document.getElementById("libraryLocBody" + li);
    if (locBody && locBody.classList.contains("expanded")) {
      state.locations[loc.label] = true;
    }
    if (libraryLangSep && loc.lang_folders) {
      loc.lang_folders.forEach(function (lf, lfi) {
        var lfId = "L" + li + "LF" + lfi;
        var lfBody = document.getElementById("libraryLfBody" + lfId);
        if (lfBody && lfBody.classList.contains("expanded")) {
          state.langFolders[loc.label + "::" + lf.name] = true;
        }
        lf.titles.forEach(function (title, ti) {
          var globalTi = lfId + "T" + ti;
          var titleBody = document.getElementById(
            "libraryTitleBody" + globalTi,
          );
          if (titleBody && titleBody.classList.contains("expanded")) {
            state.titles[loc.label + "::" + lf.name + "::" + title.folder] =
              true;
          }
          Object.keys(title.seasons).forEach(function (skey) {
            var sid = "libS" + globalTi + "_" + skey;
            var seasonBody = document.getElementById(sid + "Body");
            if (seasonBody && seasonBody.classList.contains("expanded")) {
              state.seasons[
                loc.label + "::" + lf.name + "::" + title.folder + "::" + skey
              ] = true;
            }
          });
        });
      });
    } else if (loc.titles) {
      loc.titles.forEach(function (title, ti) {
        var globalTi = "L" + li + "T" + ti;
        var titleBody = document.getElementById("libraryTitleBody" + globalTi);
        if (titleBody && titleBody.classList.contains("expanded")) {
          state.titles[loc.label + "::" + title.folder] = true;
        }
        Object.keys(title.seasons).forEach(function (skey) {
          var sid = "libS" + globalTi + "_" + skey;
          var seasonBody = document.getElementById(sid + "Body");
          if (seasonBody && seasonBody.classList.contains("expanded")) {
            state.seasons[loc.label + "::" + title.folder + "::" + skey] = true;
          }
        });
      });
    }
  });
  return state;
}

function restoreExpandedState(state) {
  libraryLocations.forEach(function (loc, li) {
    if (state.locations[loc.label]) {
      var body = document.getElementById("libraryLocBody" + li);
      var arrow = document.getElementById("libraryLocArrow" + li);
      if (body) body.classList.add("expanded");
      if (arrow) arrow.classList.add("expanded");
    }
    if (libraryLangSep && loc.lang_folders) {
      loc.lang_folders.forEach(function (lf, lfi) {
        var lfId = "L" + li + "LF" + lfi;
        if (state.langFolders[loc.label + "::" + lf.name]) {
          var body = document.getElementById("libraryLfBody" + lfId);
          var arrow = document.getElementById("libraryLfArrow" + lfId);
          if (body) body.classList.add("expanded");
          if (arrow) arrow.classList.add("expanded");
        }
        lf.titles.forEach(function (title, ti) {
          var globalTi = lfId + "T" + ti;
          if (state.titles[loc.label + "::" + lf.name + "::" + title.folder]) {
            var body = document.getElementById("libraryTitleBody" + globalTi);
            var arrow = document.getElementById("libraryTitleArrow" + globalTi);
            if (body) body.classList.add("expanded");
            if (arrow) arrow.classList.add("expanded");
          }
          Object.keys(title.seasons).forEach(function (skey) {
            var sid = "libS" + globalTi + "_" + skey;
            if (
              state.seasons[
              loc.label + "::" + lf.name + "::" + title.folder + "::" + skey
              ]
            ) {
              var body = document.getElementById(sid + "Body");
              var arrow = document.getElementById(sid + "Arrow");
              if (body) body.classList.add("expanded");
              if (arrow) arrow.classList.add("expanded");
            }
          });
        });
      });
    } else if (loc.titles) {
      loc.titles.forEach(function (title, ti) {
        var globalTi = "L" + li + "T" + ti;
        if (state.titles[loc.label + "::" + title.folder]) {
          var body = document.getElementById("libraryTitleBody" + globalTi);
          var arrow = document.getElementById("libraryTitleArrow" + globalTi);
          if (body) body.classList.add("expanded");
          if (arrow) arrow.classList.add("expanded");
        }
        Object.keys(title.seasons).forEach(function (skey) {
          var sid = "libS" + globalTi + "_" + skey;
          if (state.seasons[loc.label + "::" + title.folder + "::" + skey]) {
            var body = document.getElementById(sid + "Body");
            var arrow = document.getElementById(sid + "Arrow");
            if (body) body.classList.add("expanded");
            if (arrow) arrow.classList.add("expanded");
          }
        });
      });
    }
  });
}

// --- Load ---

async function loadLibrary() {
  var list = document.getElementById("libraryList");
  var prevState = getExpandedState();
  list.innerHTML = '<div class="library-empty">Loading...</div>';
  try {
    var resp = await fetch("/api/library");
    var data = await resp.json();
    libraryLocations = data.locations || [];
    libraryLangSep = !!data.lang_sep;
    renderLibrary(libraryLocations);
    restoreExpandedState(prevState);
  } catch (e) {
    console.error('loadLibrary failed:', e);
    list.innerHTML = '<div class="library-empty">Failed to load library: ' + e.message + '</div>';
  }
}

// --- Watched status ---

var WATCHED_BG = "rgba(76, 175, 80, 0.18)";

async function setWatchedStatus(locIndex, folder, skey, episode, file, watched) {
  var loc = libraryLocations[locIndex];
  var body = {
    folder: folder,
    season: skey,
    episode: episode,
    file: file,
    watched: watched,
    custom_path_id: loc ? loc.custom_path_id : null,
  };
  try {
    var resp = await fetch("/api/library/watched", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    var data = await resp.json();
    return !data.error;
  } catch (e) {
    return false;
  }
}

function applyWatchedStyle(epId, watched) {
  var el = document.getElementById(epId);
  if (!el) return;
  el.dataset.watched = watched ? "1" : "0";
  el.style.backgroundColor = watched ? WATCHED_BG : "";
  var btn = el.querySelector(".library-watched-toggle");
  if (btn) btn.textContent = watched ? "\u2713" : "\u25CB";
}

function markWatchedOnClick(epId, locIndex, folder, skey, episode, file) {
  // Fire-and-forget: don't block the new-tab navigation
  var el = document.getElementById(epId);
  if (el && el.dataset.watched === "1") return; // already watched
  setWatchedStatus(locIndex, folder, skey, episode, file, true).then(function (ok) {
    if (ok) applyWatchedStyle(epId, true);
  });
}

async function toggleWatched(epId, locIndex, folder, skey, episode, file) {
  var el = document.getElementById(epId);
  var currentlyWatched = el && el.dataset.watched === "1";
  var next = !currentlyWatched;
  var ok = await setWatchedStatus(locIndex, folder, skey, episode, file, next);
  if (ok) applyWatchedStyle(epId, next);
}

// --- Render helpers ---

function renderTitles(html, titles, idPrefix, padLeft, locIndex, langFolder, indices) {
  titles.forEach(function (title, i) {
    var ti = (indices && indices[i] !== undefined) ? indices[i] : i;
    var globalTi = idPrefix + "T" + ti;
    var seasonKeys = Object.keys(title.seasons).sort(function (a, b) {
      return parseInt(a) - parseInt(b);
    });

    html.push('<div class="library-title-section">');
    html.push(
      '<div class="library-title-header" onclick="toggleLibraryTitle(\'' +
      globalTi +
      '\')" style="padding-left:' +
      padLeft +
      'px">',
    );
    html.push('<div class="library-title-left">');
    html.push(
      '<span class="library-arrow" id="libraryTitleArrow' +
      globalTi +
      '">&#9654;</span>',
    );
    html.push(
      '<span class="library-title-name">' + escLib(title.folder) + "</span>",
    );
    html.push("</div>");
    html.push('<div class="library-title-right">');
    html.push(
      '<span class="library-meta">' + title.total_episodes + " ep</span>",
    );
    html.push(
      '<span class="library-meta library-meta-size">' +
      formatSize(title.total_size) +
      "</span>",
    );
    if (libraryCanDelete) {
      var delArgs =
        locIndex +
        "," +
        ti +
        ",null,null," +
        (langFolder !== null ? "'" + escLib(langFolder) + "'" : "null");
      html.push(
        '<button class="library-delete" onclick="event.stopPropagation();deleteLibraryItem(' +
        delArgs +
        ')" title="Delete title">&times;</button>',
      );
    }
    html.push("</div>");
    html.push("</div>");

    html.push(
      '<div class="library-title-body" id="libraryTitleBody' + globalTi + '">',
    );
    var seasonPad = padLeft + 16;
    var epPad = padLeft + 32;
    seasonKeys.forEach(function (skey) {
      var eps = title.seasons[skey];
      var sid = "libS" + globalTi + "_" + skey;
      var seasonSize = eps.reduce(function (acc, e) {
        return acc + e.size;
      }, 0);

      html.push(
        '<div class="library-season-header" onclick="toggleLibrarySeason(\'' +
        sid +
        '\')" style="padding-left:' +
        seasonPad +
        'px">',
      );
      html.push('<div class="library-season-left">');
      html.push(
        '<span class="library-arrow" id="' + sid + 'Arrow">&#9654;</span>',
      );
      var seasonEpCount = eps.filter(function (e) {
        return e.is_video !== false;
      }).length;
      var seasonLabel = (skey === "movie") ? "Filme" : ("Season " + skey);
      html.push("<span>" + seasonLabel + " (" + seasonEpCount + " ep)</span>");
      html.push("</div>");
      html.push('<div class="library-season-right">');
      html.push(
        '<span class="library-meta library-meta-size">' +
        formatSize(seasonSize) +
        "</span>",
      );
      if (libraryCanDelete) {
        var delArgs =
          locIndex +
          "," +
          ti +
          "," +
          skey +
          ",null," +
          (langFolder !== null ? "'" + escLib(langFolder) + "'" : "null");
        html.push(
          '<button class="library-delete" onclick="event.stopPropagation();deleteLibraryItem(' +
          delArgs +
          ')" title="Delete season">&times;</button>',
        );
      }
      html.push("</div>");
      html.push("</div>");

      html.push('<div class="library-season-body" id="' + sid + 'Body">');
      eps.forEach(function (ep, epi) {
        var epId = sid + "_E" + epi;
        var isWatched = !!ep.watched;
        var bgStyle = isWatched ? "background-color:" + WATCHED_BG + ";" : "";
        html.push(
          '<div class="library-episode" id="' + epId + '" data-watched="' +
          (isWatched ? "1" : "0") +
          '" style="padding-left:' + epPad + 'px;' + bgStyle + '">',
        );
        html.push(
          '<span class="library-ep-num">E' +
          String(ep.episode).padStart(3, "0") +
          "</span>",
        );
        var epUrl = (skey === "movie")
          ? "/files/" + encodeURIComponent(title.folder) + "/" + encodeURIComponent(ep.file)
          : "/files/" + encodeURIComponent(title.folder) + "/" +
            encodeURIComponent("Season " + String(skey).padStart(2, "0")) + "/" +
            encodeURIComponent(ep.file);
        var watchArgs =
          "'" + epId + "'," + locIndex + ",'" + escLib(title.folder) + "','" +
          skey + "'," + ep.episode + ",'" + escLib(ep.file) + "'";
        html.push(
          '<a class="library-ep-file" href="' + epUrl + '" target="_blank" onclick="markWatchedOnClick(' +
          watchArgs + ')">' + escLib(ep.file) + "</a>",
        );
        html.push(
          '<span class="library-ep-size">' + formatSize(ep.size) + "</span>",
        );
        html.push(
          '<button class="library-watched-toggle" onclick="event.stopPropagation();toggleWatched(' +
          watchArgs + ')" title="Als gesehen/ungesehen markieren">' +
          (isWatched ? "\u2713" : "\u25CB") + "</button>",
        );
        if (libraryCanDelete) {
          var delArgs =
            locIndex +
            "," +
            ti +
            "," +
            skey +
            "," +
            ep.episode +
            "," +
            (langFolder !== null ? "'" + escLib(langFolder) + "'" : "null");
          html.push(
            '<button class="library-delete" onclick="deleteLibraryItem(' +
            delArgs +
            ')" title="Delete episode">&times;</button>',
          );
        }
        html.push("</div>");
      });
      html.push("</div>");
    });
    html.push("</div>");
    html.push("</div>");
  });
}

// --- Main render ---

function renderLibrary(locations) {
  var list = document.getElementById("libraryList");
  if (!locations.length) {
    list.innerHTML =
      '<div class="library-empty">No downloaded content found</div>';
    return;
  }

  var html = [];
  locations.forEach(function (loc, li) {
    // Compute location totals
    var locTotalEps = 0;
    var locTotalSize = 0;
    if (libraryLangSep && loc.lang_folders) {
      loc.lang_folders.forEach(function (lf) {
        lf.titles.forEach(function (t) {
          locTotalEps += t.total_episodes;
          locTotalSize += t.total_size;
        });
      });
    } else if (loc.titles) {
      loc.titles.forEach(function (t) {
        locTotalEps += t.total_episodes;
        locTotalSize += t.total_size;
      });
    }

    // Location header
    html.push('<div class="library-title-section">');
    html.push(
      '<div class="library-location-header" onclick="toggleLibraryLocation(' +
      li +
      ')">',
    );
    html.push('<div class="library-title-left">');
    html.push(
      '<span class="library-arrow" id="libraryLocArrow' +
      li +
      '">&#9654;</span>',
    );
    html.push(
      '<span class="library-title-name" style="font-weight:600;color:#fff">' +
      escLib(loc.label) +
      "</span>",
    );
    html.push("</div>");
    html.push('<div class="library-title-right">');
    html.push('<span class="library-meta">' + locTotalEps + " ep</span>");
    html.push(
      '<span class="library-meta library-meta-size">' +
      formatSize(locTotalSize) +
      "</span>",
    );
    html.push("</div>");
    html.push("</div>");

    // Location body
    html.push('<div class="library-title-body" id="libraryLocBody' + li + '">');

    if (libraryLangSep && loc.lang_folders) {
      // Lang sep ON: Location > Lang Folder > Title > Season > Episode
      loc.lang_folders.forEach(function (lf, lfi) {
        var lfId = "L" + li + "LF" + lfi;
        var lfTotalEps = 0;
        var lfTotalSize = 0;
        lf.titles.forEach(function (t) {
          lfTotalEps += t.total_episodes;
          lfTotalSize += t.total_size;
        });

        // Lang folder header
        html.push('<div class="library-title-section">');
        html.push(
          '<div class="library-season-header" onclick="toggleLibraryLangFolder(\'' +
          lfId +
          '\')" style="padding-left:32px">',
        );
        html.push('<div class="library-season-left">');
        html.push(
          '<span class="library-arrow" id="libraryLfArrow' +
          lfId +
          '">&#9654;</span>',
        );
        html.push(
          '<span style="font-weight:500">' + escLib(lf.name) + "</span>",
        );
        html.push("</div>");
        html.push('<div class="library-season-right">');
        html.push('<span class="library-meta">' + lfTotalEps + " ep</span>");
        html.push(
          '<span class="library-meta library-meta-size">' +
          formatSize(lfTotalSize) +
          "</span>",
        );
        html.push("</div>");
        html.push("</div>");

        // Lang folder body (titles)
        html.push(
          '<div class="library-title-body" id="libraryLfBody' + lfId + '">',
        );
        renderTitles(html, lf.titles, lfId, 48, li, lf.name);
        html.push("</div>");
        html.push("</div>");
      });
    } else if (loc.titles) {
      // Location > MediaType (Filme/Serien) > [Alle | Genre] > Title > (Season >) Episode
      var mediaGroups = { series: [], movie: [] };
      loc.titles.forEach(function (t, ti) {
        var mt = t.media_type === "movie" ? "movie" : "series";
        mediaGroups[mt].push({ title: t, idx: ti });
      });
      ["series", "movie"].forEach(function (mtKey) {
        var entries = mediaGroups[mtKey];
        var mtLabel = mtKey === "movie" ? "Filme" : "Serien";
        var mtId = "L" + li + "MT" + mtKey;
        var mtEps = 0, mtSize = 0;
        entries.forEach(function (e) {
          mtEps += e.title.total_episodes;
          mtSize += e.title.total_size;
        });
        html.push('<div class="library-title-section">');
        html.push(
          '<div class="library-season-header" onclick="toggleLibrarySeason(\'' +
          mtId + '\')" style="padding-left:32px">'
        );
        html.push('<div class="library-season-left">');
        html.push('<span class="library-arrow" id="' + mtId + 'Arrow">&#9654;</span>');
        html.push('<span style="font-weight:600;color:#fff">' + mtLabel + "</span>");
        html.push("</div>");
        html.push('<div class="library-season-right">');
        html.push('<span class="library-meta">' + mtEps + " ep</span>");
        html.push('<span class="library-meta library-meta-size">' + formatSize(mtSize) + "</span>");
        html.push("</div>");
        html.push("</div>");
        html.push('<div class="library-title-body" id="' + mtId + 'Body">');

        // "Alle" tab: every title in this media-type group, ungrouped by genre
        if (entries.length) {
          var allId = mtId + "GAll";
          var allEps = 0, allSize = 0;
          entries.forEach(function (e) {
            allEps += e.title.total_episodes;
            allSize += e.title.total_size;
          });
          html.push('<div class="library-title-section">');
          html.push(
            '<div class="library-season-header" onclick="toggleLibrarySeason(\'' +
            allId + '\')" style="padding-left:48px">'
          );
          html.push('<div class="library-season-left">');
          html.push('<span class="library-arrow" id="' + allId + 'Arrow">&#9654;</span>');
          html.push('<span style="font-weight:500">Alle</span>');
          html.push("</div>");
          html.push('<div class="library-season-right">');
          html.push('<span class="library-meta">' + allEps + " ep</span>");
          html.push('<span class="library-meta library-meta-size">' + formatSize(allSize) + "</span>");
          html.push("</div>");
          html.push("</div>");
          html.push('<div class="library-title-body" id="' + allId + 'Body">');
          var allTitles = entries.map(function (e) { return e.title; });
          var allIndices = entries.map(function (e) { return e.idx; });
          renderTitles(html, allTitles, allId, 64, li, null, allIndices);
          html.push("</div>");
          html.push("</div>");
        }

        var genreGroups = {};
        entries.forEach(function (e) {
          var genreStr = e.title.genre || "Sonstiges";
          var genreList = genreStr.split(",").map(function (g) { return g.trim(); }).filter(Boolean);
          genreList.forEach(function (g) {
            if (!genreGroups[g]) genreGroups[g] = [];
            genreGroups[g].push(e);
          });
        });
        Object.keys(genreGroups).sort().forEach(function (genreName, gi) {
          var gEntries = genreGroups[genreName];
          var gId = mtId + "G" + gi;
          var gEps = 0, gSize = 0;
          gEntries.forEach(function (e) {
            gEps += e.title.total_episodes;
            gSize += e.title.total_size;
          });
          html.push('<div class="library-title-section">');
          html.push(
            '<div class="library-season-header" onclick="toggleLibrarySeason(\'' +
            gId + '\')" style="padding-left:48px">'
          );
          html.push('<div class="library-season-left">');
          html.push('<span class="library-arrow" id="' + gId + 'Arrow">&#9654;</span>');
          html.push('<span style="font-weight:500">' + escLib(genreName) + "</span>");
          html.push("</div>");
          html.push('<div class="library-season-right">');
          html.push('<span class="library-meta">' + gEps + " ep</span>");
          html.push('<span class="library-meta library-meta-size">' + formatSize(gSize) + "</span>");
          html.push("</div>");
          html.push("</div>");
          html.push('<div class="library-title-body" id="' + gId + 'Body">');
          var gTitles = gEntries.map(function (e) { return e.title; });
          var gIndices = gEntries.map(function (e) { return e.idx; });
          renderTitles(html, gTitles, gId, 64, li, null, gIndices);
          html.push("</div>");
          html.push("</div>");
        });

        html.push("</div>");
        html.push("</div>");
      });
    }

    html.push("</div>");
    html.push("</div>");
  });

  list.innerHTML = html.join("");
}

// --- Toggle helpers ---

function toggleLibraryLocation(index) {
  var body = document.getElementById("libraryLocBody" + index);
  var arrow = document.getElementById("libraryLocArrow" + index);
  if (!body) return;
  var expanded = body.classList.toggle("expanded");
  if (arrow) arrow.classList.toggle("expanded", expanded);
}

function toggleLibraryLangFolder(id) {
  var body = document.getElementById("libraryLfBody" + id);
  var arrow = document.getElementById("libraryLfArrow" + id);
  if (!body) return;
  var expanded = body.classList.toggle("expanded");
  if (arrow) arrow.classList.toggle("expanded", expanded);
}

function toggleLibraryTitle(id) {
  var body = document.getElementById("libraryTitleBody" + id);
  var arrow = document.getElementById("libraryTitleArrow" + id);
  if (!body) return;
  var expanded = body.classList.toggle("expanded");
  if (arrow) arrow.classList.toggle("expanded", expanded);
}

function toggleLibrarySeason(id) {
  var body = document.getElementById(id + "Body");
  var arrow = document.getElementById(id + "Arrow");
  if (!body) return;
  var expanded = body.classList.toggle("expanded");
  if (arrow) arrow.classList.toggle("expanded", expanded);
}

// --- Delete ---

async function deleteLibraryItem(
  locIndex,
  titleIndex,
  season,
  episode,
  langFolder,
) {
  var loc = libraryLocations[locIndex];
  if (!loc) return;

  var titles;
  if (libraryLangSep && loc.lang_folders && langFolder !== null) {
    var lf = loc.lang_folders.find(function (f) {
      return f.name === langFolder;
    });
    if (!lf) return;
    titles = lf.titles;
  } else {
    titles = loc.titles;
  }

  var title = titles[titleIndex];
  if (!title) return;

  var where = loc.label + (langFolder ? "/" + langFolder : "");
  var msg;
  if (season === null && episode === null) {
    msg = 'Delete entire title "' + title.folder + '" from ' + where + "?";
  } else if (episode === null) {
    msg =
      "Delete all episodes from Season " +
      season +
      ' in "' +
      title.folder +
      '" (' +
      where +
      ")?";
  } else {
    msg =
      "Delete S" +
      String(season).padStart(2, "0") +
      "E" +
      String(episode).padStart(3, "0") +
      ' from "' +
      title.folder +
      '" (' +
      where +
      ")?";
  }

  if (!confirm(msg)) return;

  try {
    var body = {
      folder: title.folder,
      season: season,
      episode: episode,
      custom_path_id: loc.custom_path_id,
    };
    if (langFolder) body.lang_folder = langFolder;
    var resp = await fetch("/api/library/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    var data = await resp.json();
    if (data.error) {
      if (typeof showToast === "function") showToast(data.error);
    } else {
      if (typeof showToast === "function") showToast("Deleted successfully");
    }
    loadLibrary();
  } catch (e) {
    if (typeof showToast === "function") showToast("Delete failed");
  }
}

// --- Utilities ---

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024)
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function escLib(s) {
  var d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

// Load library on page init
loadLibrary();
