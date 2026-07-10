/*
 * Lightweight interface translation.
 *
 * Both dictionaries are embedded so switching languages is instant and needs
 * no extra request. Elements are translated by data-attributes:
 *   data-i18n            -> textContent
 *   data-i18n-placeholder-> placeholder attribute
 *   data-i18n-title      -> title attribute
 *   data-i18n-html       -> innerHTML (use sparingly, values are trusted)
 * Dynamic strings from the other scripts use window.t("key", "fallback").
 */
(function () {
  const STRINGS = {
    en: {
      "nav.home": "Home",
      "nav.library": "Library",
      "nav.autosync": "Auto-Sync",
      "nav.planned": "Planned",
      "nav.queue": "Queue",
      "nav.settings": "Settings",
      "nav.logout": "Logout",
      "footer.opensource": "AniWorld Downloader is open source.",
      "footer.viewgithub": "View the project on GitHub",
      "queue.title": "Download Queue",
      "queue.empty": "The download queue is empty.",
      "queue.solve": "Solve",
      "captcha.title": "\u{1F512} Solve captcha",
      "captcha.hint": "Click the image to interact with the browser.",
      "index.search": "Search",
      "index.random": "Random",
      "index.episodes": "Episodes",
      "index.autosync": "Keep Updated (Auto-Sync)",
      "index.selectall": "Select All",
      "index.download_folder": "Download Folder",
      "index.default": "Default",
      "index.download_selected": "Download Selected",
      "index.download_all": "Download All",
      "index.download_all_langs": "Download All Languages",
      "index.show_unofficial": "Show unofficial chapters",
      "browse.new_movies": "New Movies",
      "browse.recent_series": "Recently Updated",
      "common.save": "Save",
      "common.add": "Add",
      "common.delete": "Delete",
      "common.edit": "Edit",
      "common.cancel": "Cancel",
      "common.remove": "Remove",
      "settings.title": "Settings",
      "settings.users": "User Management",
      "settings.add_user": "Add User",
      "settings.custom_paths": "Custom Paths",
      "settings.add_path": "Add Path",
      "settings.paths.default_for": "Default for sites",
      "settings.paths.default_hint":
        "Tick the sites a path should be the pre-selected download folder for.",
      "settings.persist_notice":
        "Changes are saved to your .env and persist across restarts.",
      "settings.autosync_defaults": "Auto-Sync Defaults",
      "settings.schedule": "Schedule",
      "settings.default_language": "Default Language",
      "settings.default_provider": "Default Provider",
      "settings.autosync_hint":
        "How often Auto-Sync checks for new episodes. Language and provider are defaults used when creating new sync jobs.",
      "settings.general": "Settings",
      "settings.download_path": "Download Path",
      "settings.download_path_hint": "Changes take effect immediately for new downloads",
      "settings.provider_fallback": "Provider Fallback Order",
      "settings.provider_fallback_hint":
        "Downloads always try the selected provider first. If that hoster fails, AniWorld Downloader falls back through this order.",
      "settings.lang_separation": "Separate languages into folders",
      "settings.lang_separation_hint":
        "When enabled, downloads are organized into subfolders by language (e.g. german-dub/, english-sub/)",
      "settings.disable_english_sub": "Disable English Sub downloads",
      "settings.disable_english_sub_hint":
        "When enabled, English Sub is hidden from the language selector and cannot be downloaded",
      "settings.enable_htv": "Enable Hanime tab",
      "settings.enable_htv_hint": "When enabled, the Hanime tab is shown on the home page",
      "settings.movie_folder": "Wrap movies in their own folder",
      "settings.movie_folder_hint":
        "When off, a movie is saved directly into the download path instead of a \"Title (Year)\" folder.",
      "settings.output_format": "Output Format",
      "settings.output_format_hint":
        "Container for downloaded files. MP4 is the most compatible with players and Plex.",
      "settings.ui_language": "Interface Language",
      "settings.ui_language_hint": "Language of this web interface.",
      "settings.interface": "Interface",
      "settings.config_file": "Configuration File",
      "settings.edit_env": "Edit .env",
      "settings.env_hint":
        "Edit the raw .env file. Handy for Docker users. Some values only take effect after a restart.",
      "settings.env_modal_title": "Edit .env",
      "settings.discord": "Discord Request Bot",
      "settings.discord.enable": "Enable Discord bot",
      "settings.discord.enable_hint":
        "Let users request movies and series from Discord. Requests are sent to you for approval.",
      "settings.discord.token": "Bot Token",
      "settings.discord.owner": "Owner User ID",
      "settings.discord.mode": "Mode",
      "settings.discord.mode_standard": "Standard (approve each request)",
      "settings.discord.mode_advanced": "Advanced (queue immediately)",
      "settings.discord.role": "Request Role ID (optional)",
      "settings.discord.guild": "Server ID (optional, faster command sync)",
      "settings.discord.status": "Status",
      "settings.ip": "IP Check",
      "settings.public_ip": "Container Public IP",
      "settings.refresh_ip": "Refresh IP",
      "planned.title": "Planned Releases",
      "planned.subtitle":
        "Watch for movies or series that aren't out yet. Once they appear on the selected site, they are downloaded automatically.",
      "planned.add": "Add Planned Item",
      "planned.name": "Title",
      "planned.site": "Site",
      "planned.type": "Type",
      "planned.type_movie": "Movie",
      "planned.type_series": "Series",
      "planned.language": "Language",
      "planned.provider": "Provider",
      "planned.autosync_after": "Keep series updated after first download",
      "planned.check_now": "Check now",
      "planned.status": "Status",
      "planned.last_check": "Last Check",
      "planned.empty": "Nothing planned yet.",
      "planned.status_waiting": "Waiting",
      "planned.status_found": "Found",
      "planned.status_error": "Error",
    },
    de: {
      "nav.home": "Start",
      "nav.library": "Bibliothek",
      "nav.autosync": "Auto-Sync",
      "nav.planned": "Geplant",
      "nav.queue": "Warteschlange",
      "nav.settings": "Einstellungen",
      "nav.logout": "Abmelden",
      "footer.opensource": "AniWorld Downloader ist Open Source.",
      "footer.viewgithub": "Projekt auf GitHub ansehen",
      "queue.title": "Download-Warteschlange",
      "queue.empty": "Die Warteschlange ist leer.",
      "queue.solve": "Lösen",
      "captcha.title": "\u{1F512} Captcha lösen",
      "captcha.hint": "Klick auf die Darstellung um mit dem Browser zu interagieren.",
      "index.search": "Suchen",
      "index.random": "Zufall",
      "index.episodes": "Episoden",
      "index.autosync": "Aktuell halten (Auto-Sync)",
      "index.selectall": "Alle auswählen",
      "index.download_folder": "Download-Ordner",
      "index.default": "Standard",
      "index.download_selected": "Auswahl herunterladen",
      "index.download_all": "Alle herunterladen",
      "index.download_all_langs": "Alle Sprachen herunterladen",
      "index.show_unofficial": "Inoffizielle Kapitel anzeigen",
      "browse.new_movies": "Neue Filme",
      "browse.recent_series": "Zuletzt aktualisiert",
      "common.save": "Speichern",
      "common.add": "Hinzufügen",
      "common.delete": "Löschen",
      "common.edit": "Bearbeiten",
      "common.cancel": "Abbrechen",
      "common.remove": "Entfernen",
      "settings.title": "Einstellungen",
      "settings.users": "Benutzerverwaltung",
      "settings.add_user": "Benutzer hinzufügen",
      "settings.custom_paths": "Eigene Pfade",
      "settings.add_path": "Pfad hinzufügen",
      "settings.paths.default_for": "Standard für Seiten",
      "settings.paths.default_hint":
        "Wähle die Seiten aus, für die dieser Pfad der voreingestellte Download-Ordner sein soll.",
      "settings.persist_notice":
        "Änderungen werden in deiner .env gespeichert und bleiben nach Neustarts erhalten.",
      "settings.autosync_defaults": "Auto-Sync-Standards",
      "settings.schedule": "Zeitplan",
      "settings.default_language": "Standardsprache",
      "settings.default_provider": "Standard-Hoster",
      "settings.autosync_hint":
        "Wie oft Auto-Sync nach neuen Episoden sucht. Sprache und Hoster sind Standardwerte für neue Sync-Aufträge.",
      "settings.general": "Einstellungen",
      "settings.download_path": "Download-Pfad",
      "settings.download_path_hint": "Änderungen gelten sofort für neue Downloads",
      "settings.provider_fallback": "Hoster-Ausweichreihenfolge",
      "settings.provider_fallback_hint":
        "Downloads versuchen immer zuerst den gewählten Hoster. Schlägt dieser fehl, geht AniWorld Downloader diese Reihenfolge durch.",
      "settings.lang_separation": "Sprachen in Ordner trennen",
      "settings.lang_separation_hint":
        "Wenn aktiviert, werden Downloads in Unterordner nach Sprache abgelegt (z. B. german-dub/, english-sub/)",
      "settings.disable_english_sub": "English-Sub-Downloads deaktivieren",
      "settings.disable_english_sub_hint":
        "Wenn aktiviert, wird English Sub aus der Sprachauswahl ausgeblendet und kann nicht heruntergeladen werden",
      "settings.enable_htv": "Hanime-Tab aktivieren",
      "settings.enable_htv_hint": "Wenn aktiviert, wird der Hanime-Tab auf der Startseite angezeigt",
      "settings.movie_folder": "Filme in eigenen Ordner packen",
      "settings.movie_folder_hint":
        "Wenn aus, wird ein Film direkt in den Download-Pfad gespeichert statt in einen \"Titel (Jahr)\"-Ordner.",
      "settings.output_format": "Ausgabeformat",
      "settings.output_format_hint":
        "Container für heruntergeladene Dateien. MP4 ist am kompatibelsten mit Playern und Plex.",
      "settings.ui_language": "Sprache der Oberfläche",
      "settings.ui_language_hint": "Sprache dieser Weboberfläche.",
      "settings.interface": "Oberfläche",
      "settings.config_file": "Konfigurationsdatei",
      "settings.edit_env": ".env bearbeiten",
      "settings.env_hint":
        "Bearbeite die .env-Datei direkt. Praktisch für Docker-Nutzer. Manche Werte gelten erst nach einem Neustart.",
      "settings.env_modal_title": ".env bearbeiten",
      "settings.discord": "Discord-Anfrage-Bot",
      "settings.discord.enable": "Discord-Bot aktivieren",
      "settings.discord.enable_hint":
        "Lass Nutzer Filme und Serien über Discord anfragen. Anfragen werden dir zur Freigabe geschickt.",
      "settings.discord.token": "Bot-Token",
      "settings.discord.owner": "Owner-Benutzer-ID",
      "settings.discord.mode": "Modus",
      "settings.discord.mode_standard": "Standard (jede Anfrage freigeben)",
      "settings.discord.mode_advanced": "Erweitert (sofort einreihen)",
      "settings.discord.role": "Anfrage-Rollen-ID (optional)",
      "settings.discord.guild": "Server-ID (optional, schnellere Befehle)",
      "settings.discord.status": "Status",
      "settings.ip": "IP-Prüfung",
      "settings.public_ip": "Öffentliche IP des Containers",
      "settings.refresh_ip": "IP aktualisieren",
      "planned.title": "Geplante Releases",
      "planned.subtitle":
        "Beobachte Filme oder Serien, die noch nicht erschienen sind. Sobald sie auf der gewählten Seite auftauchen, werden sie automatisch heruntergeladen.",
      "planned.add": "Geplanten Eintrag hinzufügen",
      "planned.name": "Titel",
      "planned.site": "Seite",
      "planned.type": "Typ",
      "planned.type_movie": "Film",
      "planned.type_series": "Serie",
      "planned.language": "Sprache",
      "planned.provider": "Hoster",
      "planned.autosync_after": "Serie nach erstem Download aktuell halten",
      "planned.check_now": "Jetzt prüfen",
      "planned.status": "Status",
      "planned.last_check": "Letzte Prüfung",
      "planned.empty": "Noch nichts geplant.",
      "planned.status_waiting": "Wartet",
      "planned.status_found": "Gefunden",
      "planned.status_error": "Fehler",
    },
  };

  const STORAGE_KEY = "aniworld.lang";

  function currentLang() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && STRINGS[stored]) return stored;
    const server = (window.ANIWORLD_UI_LANGUAGE || "en").toLowerCase();
    return STRINGS[server] ? server : "en";
  }

  function translate(key, fallback) {
    const lang = currentLang();
    const table = STRINGS[lang] || STRINGS.en;
    if (key in table) return table[key];
    if (key in STRINGS.en) return STRINGS.en[key];
    return fallback !== undefined ? fallback : key;
  }

  function applyI18n(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = translate(el.getAttribute("data-i18n"));
    });
    scope.querySelectorAll("[data-i18n-html]").forEach((el) => {
      el.innerHTML = translate(el.getAttribute("data-i18n-html"));
    });
    scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.setAttribute("placeholder", translate(el.getAttribute("data-i18n-placeholder")));
    });
    scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.setAttribute("title", translate(el.getAttribute("data-i18n-title")));
    });
    document.documentElement.setAttribute("lang", currentLang());
  }

  function setLanguage(lang) {
    if (!STRINGS[lang]) return;
    localStorage.setItem(STORAGE_KEY, lang);
    applyI18n();
    // Persist server-side too so it survives on other devices / as the default.
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ui_language: lang }),
    }).catch(() => {});
    document.dispatchEvent(new CustomEvent("i18n:changed", { detail: { lang } }));
  }

  window.t = translate;
  window.applyI18n = applyI18n;
  window.setLanguage = setLanguage;
  window.getLanguage = currentLang;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => applyI18n());
  } else {
    applyI18n();
  }
})();
