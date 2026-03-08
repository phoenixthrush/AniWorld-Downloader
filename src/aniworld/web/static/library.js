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
    list.innerHTML = '<div class="library-empty">Failed to load library</div>';
  }
}

// --- Render helpers ---

function renderTitles(html, titles, idPrefix, padLeft, locIndex, langFolder) {
  titles.forEach(function (title, ti) {
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
      html.push("<span>Season " + skey + " (" + seasonEpCount + " ep)</span>");
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
      eps.forEach(function (ep) {
        html.push(
          '<div class="library-episode" style="padding-left:' + epPad + 'px">',
        );
        html.push(
          '<span class="library-ep-num">E' +
            String(ep.episode).padStart(3, "0") +
            "</span>",
        );
        html.push(
          '<span class="library-ep-file">' + escLib(ep.file) + "</span>",
        );
        html.push(
          '<span class="library-ep-size">' + formatSize(ep.size) + "</span>",
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
      // Lang sep OFF: Location > Title > Season > Episode
      renderTitles(html, loc.titles, "L" + li, 32, li, null);
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
