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
      "nav.dubsync": "DubSync",
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
      "index.extra_langs": "Also download:",
      "index.extra_langs_tip":
        "Everything ends up in one file: each extra dub becomes another audio track you can switch to in your player, timed to match automatically. Sub versions have their subtitles burned into the picture, so they are added as a second video track you can switch to instead.",
      "index.fetch_subs": "Add a real German subtitle track",
      "index.fetch_subs_tip":
        "Downloads the official German subtitles for this episode from the fansub scene and puts them into the file as subtitles you can turn on and off. Works for most anime from around 2020 onwards; if none are found the download simply completes without them.",
      "browse.new_movies": "New Movies",
      "browse.recent_series": "Recently Updated",
      "browse.trending_movies": "Trending Movies",
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
        "Changes made below are temporary and will be reset when AniWorld Downloader is restarted. To make settings persist, set them in your .env file at",
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
      "settings.dubsync": "DubSync",
      "settings.dubsync_hint":
        "Defaults for the DubSync page (see the DubSync tab in the navigation). Each queued job can override them.",
      "settings.dubsync_defaults": "Defaults",
      "settings.dubsync_target_hint":
        "Default local video folder, used to prefill the DubSync page.",
      "settings.dubsync_offset": "Manual offset (seconds)",
      "settings.dubsync_auto_align": "Automatic audio alignment",
      "settings.dubsync_auto_align_hint":
        "Detect each episode's dub offset by correlating the shared music/SFX bed. A manual offset always overrides detection.",
      "settings.dubsync_allow_resample":
        "Correct drift (re-encodes the dub track)",
      "settings.dubsync_allow_resample_hint":
        "Fixes PAL-speed dubs (~4% fast) via atempo. Only the added dub track is re-encoded; video and original audio stay untouched.",
      "settings.dubsync_cleanup": "Edit files in place",
      "settings.dubsync_cleanup_hint":
        "When off, results are written as *.dubsync.mkv copies next to the originals (safe default).",
      "settings.dubsync_saved": "DubSync defaults saved",
      "dubsync.page_hint":
        "Graft a German dub from AniWorld, SerienStream or a movie site losslessly onto your own archive-quality series and movie files as an additional audio track.",
      "dubsync.step1": "1. Local folder",
      "dubsync.step1_hint":
        "Pick the folder that holds your local video files. Filenames are scanned for season/episode numbers; movie files don't need any.",
      "dubsync.browse": "Browse…",
      "dubsync.recursive": "Include subfolders",
      "dubsync.scanning": "Scanning folder…",
      "dubsync.scan_failed": "Scan failed: ",
      "dubsync.scan_found_one": "video file found",
      "dubsync.scan_found_many": "video files found",
      "dubsync.scan_with_ep": "with episode numbers",
      "dubsync.scan_without_ep": "without",
      "dubsync.scan_movies_ok":
        "no episode numbers in the filenames — fine for movies",
      "dubsync.step2": "2. Show / Movie",
      "dubsync.step2_hint":
        "Search for the show or movie the dub should come from.",
      "dubsync.search": "Search",
      "dubsync.searching": "Searching…",
      "dubsync.search_failed": "Search failed: ",
      "dubsync.no_results": "No results",
      "dubsync.loading_seasons": "Loading episode list…",
      "dubsync.load_failed": "Failed to load episodes: ",
      "dubsync.change_show": "Change",
      "dubsync.season_one": "season",
      "dubsync.season_many": "seasons",
      "dubsync.step3": "3. Episodes & movies",
      "dubsync.step3_hint":
        "Episodes matching your local files are pre-selected. Movies have no episode numbers in their filenames, so each one gets a dropdown to confirm its local file. Adjust the selection before queueing.",
      "dubsync.season_label": "Season",
      "dubsync.movies": "Movies",
      "dubsync.movies_hint":
        "Pick the local file for each movie; the best title match is pre-selected.",
      "dubsync.movie_source": "Movie",
      "dubsync.movie_n": "Movie",
      "dubsync.movie_no_file": "— choose local file —",
      "dubsync.movie_need_file": "Choose a local file first",
      "dubsync.no_dub": "No German Dub available",
      "dubsync.local_file": "Local file: ",
      "dubsync.unpaired": "local file(s) have no matching episode: ",
      "dubsync.unparsed_note": "Not recognised: ",
      "dubsync.step4": "4. Options",
      "dubsync.step4_hint":
        "The usual settings work for most jobs — you can just press Add to queue.",
      "dubsync.offset": "Dub timing (seconds)",
      "dubsync.offset_auto": "automatic",
      "dubsync.offset_desc":
        "Leave empty — the timing is worked out automatically.",
      "dubsync.offset_tip":
        "Only needed when the dub is consistently too early or too late in every episode. Example: -0.5 starts the dub half a second earlier. Entering a value here turns off the automatic timing above.",
      "dubsync.auto_align": "Fix timing automatically (recommended)",
      "dubsync.auto_align_desc":
        "Lines the dub up with your video by comparing the two soundtracks.",
      "dubsync.auto_align_tip":
        "The dub comes from a stream that may start a little earlier or later than your file. DubSync listens for the music and sound effects both versions share and shifts the dub so it lines up. If it is not confident, it leaves the timing as-is and marks the job in the queue so you can check by ear.",
      "dubsync.allow_resample": "Fix wrong playback speed",
      "dubsync.allow_resample_desc":
        "Some dubs run slightly too fast; this slows the dub down to match your video.",
      "dubsync.allow_resample_tip":
        "Dubs taken from TV broadcasts sometimes run about 4% too fast. Fixing that means the dub track is converted once — your video and its original audio are never touched. Only kicks in when a speed difference is actually found.",
      "dubsync.cleanup": "Add the dub directly into my files",
      "dubsync.cleanup_desc":
        "When off, a new copy named *.dubsync.mkv is saved next to each file — the safe choice.",
      "dubsync.cleanup_tip":
        "Even with this on, your original is only replaced after the new version was written completely and successfully — a failed job never damages your files.",
      "dubsync.add": "Add to queue",
      "dubsync.added": "Added",
      "dubsync.view_queue": "View queue",
      "dubsync.summary_incomplete": "Pick a folder and a show first",
      "dubsync.summary_one": "episode selected",
      "dubsync.summary_many": "episodes selected",
      "dubsync.summary_movie_one": "movie selected",
      "dubsync.summary_movie_many": "movies selected",
      "dubsync.queued": "DubSync job added to queue",
      "dubsync.queue_failed": "Failed to enqueue: ",
      "dubsync.browser_title": "Choose a folder",
      "dubsync.browser_up": "← Back",
      "dubsync.browser_select": "Use this folder",
      "dubsync.browser_empty": "No subfolders",
      "dubsync.browser_videos": "video file(s) in this folder",
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
      "settings.discord.language": "Bot Language",
      "settings.discord.language_en": "English",
      "settings.discord.language_de": "German",
      "settings.discord.announce": "Announce Channel ID (optional)",
      "settings.discord.announce_hint": "When a requested download finishes, the requester is DM'd; if an announce channel is set, a “now available” message is posted there too.",
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
      "nav.dubsync": "DubSync",
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
      "index.extra_langs": "Zusätzlich laden:",
      "index.extra_langs_tip":
        "Alles landet in einer Datei: Jeder zusätzliche Dub wird eine weitere Tonspur, die sich im Player umschalten lässt – das Timing wird automatisch angepasst. Bei Sub-Versionen sind die Untertitel fest ins Bild eingebrannt, deshalb kommen sie als zweite, umschaltbare Videospur dazu.",
      "index.fetch_subs": "Echte deutsche Untertitelspur hinzufügen",
      "index.fetch_subs_tip":
        "Lädt die offiziellen deutschen Untertitel der Episode aus der Fansub-Szene und fügt sie als ein- und ausschaltbare Untertitelspur in die Datei ein. Funktioniert für die meisten Anime ab ca. 2020; wird nichts gefunden, läuft der Download einfach ohne Untertitel durch.",
      "browse.new_movies": "Neue Filme",
      "browse.recent_series": "Zuletzt aktualisiert",
      "browse.trending_movies": "Angesagte Filme",
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
        "Änderungen hier sind temporär und werden beim Neustart von AniWorld Downloader zurückgesetzt. Um Einstellungen dauerhaft zu speichern, trage sie in deine .env-Datei ein unter",
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
      "settings.dubsync": "DubSync",
      "settings.dubsync_hint":
        "Standardwerte für die DubSync-Seite (siehe DubSync-Tab in der Navigation). Jeder Auftrag kann sie überschreiben.",
      "settings.dubsync_defaults": "Standardwerte",
      "settings.dubsync_target_hint":
        "Standardordner der lokalen Videodateien; füllt die DubSync-Seite vor.",
      "settings.dubsync_offset": "Manueller Versatz (Sekunden)",
      "settings.dubsync_auto_align": "Automatische Tonspur-Ausrichtung",
      "settings.dubsync_auto_align_hint":
        "Erkennt den Versatz jeder Episode über die gemeinsame Musik-/Effektspur. Ein manueller Versatz hat immer Vorrang.",
      "settings.dubsync_allow_resample":
        "Drift korrigieren (kodiert die Dub-Spur neu)",
      "settings.dubsync_allow_resample_hint":
        "Behebt PAL-Geschwindigkeit (~4 % zu schnell) per atempo. Nur die neue Dub-Spur wird neu kodiert; Video und Originalton bleiben unberührt.",
      "settings.dubsync_cleanup": "Dateien direkt bearbeiten",
      "settings.dubsync_cleanup_hint":
        "Wenn aus, werden Ergebnisse als *.dubsync.mkv-Kopien neben den Originalen gespeichert (sichere Voreinstellung).",
      "settings.dubsync_saved": "DubSync-Standardwerte gespeichert",
      "dubsync.page_hint":
        "Fügt einen deutschen Dub von AniWorld, SerienStream oder einer Filmseite verlustfrei als zusätzliche Tonspur in deine eigenen hochwertigen Serien- und Filmdateien ein.",
      "dubsync.step1": "1. Lokaler Ordner",
      "dubsync.step1_hint":
        "Wähle den Ordner mit deinen lokalen Videodateien. Die Dateinamen werden nach Staffel-/Episodennummern durchsucht; Filmdateien brauchen keine.",
      "dubsync.browse": "Durchsuchen…",
      "dubsync.recursive": "Unterordner einbeziehen",
      "dubsync.scanning": "Ordner wird gescannt…",
      "dubsync.scan_failed": "Scan fehlgeschlagen: ",
      "dubsync.scan_found_one": "Videodatei gefunden",
      "dubsync.scan_found_many": "Videodateien gefunden",
      "dubsync.scan_with_ep": "mit Episodennummern",
      "dubsync.scan_without_ep": "ohne",
      "dubsync.scan_movies_ok":
        "keine Episodennummern in den Dateinamen — für Filme in Ordnung",
      "dubsync.step2": "2. Serie / Film",
      "dubsync.step2_hint":
        "Suche nach der Serie oder dem Film, aus der bzw. dem der Dub kommen soll.",
      "dubsync.search": "Suchen",
      "dubsync.searching": "Suche läuft…",
      "dubsync.search_failed": "Suche fehlgeschlagen: ",
      "dubsync.no_results": "Keine Ergebnisse",
      "dubsync.loading_seasons": "Episodenliste wird geladen…",
      "dubsync.load_failed": "Episoden konnten nicht geladen werden: ",
      "dubsync.change_show": "Ändern",
      "dubsync.season_one": "Staffel",
      "dubsync.season_many": "Staffeln",
      "dubsync.step3": "3. Episoden & Filme",
      "dubsync.step3_hint":
        "Episoden mit passenden lokalen Dateien sind vorausgewählt. Filmdateinamen tragen keine Episodennummern, daher hat jeder Film ein Dropdown zur Bestätigung seiner lokalen Datei. Passe die Auswahl vor dem Einreihen an.",
      "dubsync.season_label": "Staffel",
      "dubsync.movies": "Filme",
      "dubsync.movies_hint":
        "Wähle für jeden Film die lokale Datei; der beste Titel-Treffer ist vorausgewählt.",
      "dubsync.movie_source": "Film",
      "dubsync.movie_n": "Film",
      "dubsync.movie_no_file": "— lokale Datei wählen —",
      "dubsync.movie_need_file": "Wähle zuerst eine lokale Datei",
      "dubsync.no_dub": "Kein deutscher Dub verfügbar",
      "dubsync.local_file": "Lokale Datei: ",
      "dubsync.unpaired": "lokale Datei(en) ohne passende Episode: ",
      "dubsync.unparsed_note": "Nicht erkannt: ",
      "dubsync.step4": "4. Optionen",
      "dubsync.step4_hint":
        "Die Voreinstellungen passen für die meisten Aufträge — du kannst einfach auf „Zur Warteschlange“ drücken.",
      "dubsync.offset": "Dub-Timing (Sekunden)",
      "dubsync.offset_auto": "automatisch",
      "dubsync.offset_desc":
        "Leer lassen — das Timing wird automatisch ermittelt.",
      "dubsync.offset_tip":
        "Nur nötig, wenn der Dub in jeder Episode gleichmäßig zu früh oder zu spät kommt. Beispiel: -0.5 lässt den Dub eine halbe Sekunde früher starten. Ein Wert hier schaltet das automatische Timing oben aus.",
      "dubsync.auto_align": "Timing automatisch anpassen (empfohlen)",
      "dubsync.auto_align_desc":
        "Richtet den Dub am Video aus, indem beide Tonspuren verglichen werden.",
      "dubsync.auto_align_tip":
        "Der Dub stammt aus einem Stream, der etwas früher oder später starten kann als deine Datei. DubSync achtet auf Musik und Soundeffekte, die beide Fassungen teilen, und verschiebt den Dub passend. Ist es sich nicht sicher, bleibt das Timing unverändert und der Auftrag wird in der Warteschlange markiert, damit du per Ohr prüfen kannst.",
      "dubsync.allow_resample": "Falsche Abspielgeschwindigkeit korrigieren",
      "dubsync.allow_resample_desc":
        "Manche Dubs laufen etwas zu schnell; das bremst den Dub passend zum Video ab.",
      "dubsync.allow_resample_tip":
        "Dubs aus TV-Ausstrahlungen laufen manchmal ca. 4 % zu schnell. Die Korrektur wandelt nur die Dub-Spur einmal um — dein Video und sein Originalton werden nie angefasst. Greift nur, wenn tatsächlich ein Geschwindigkeitsunterschied gefunden wird.",
      "dubsync.cleanup": "Dub direkt in meine Dateien einfügen",
      "dubsync.cleanup_desc":
        "Wenn aus, wird eine neue Kopie namens *.dubsync.mkv neben jeder Datei gespeichert — die sichere Wahl.",
      "dubsync.cleanup_tip":
        "Auch wenn eingeschaltet: dein Original wird erst ersetzt, nachdem die neue Version vollständig und erfolgreich geschrieben wurde — ein fehlgeschlagener Auftrag beschädigt deine Dateien nie.",
      "dubsync.add": "Zur Warteschlange",
      "dubsync.added": "Hinzugefügt",
      "dubsync.view_queue": "Warteschlange öffnen",
      "dubsync.summary_incomplete": "Wähle zuerst einen Ordner und eine Serie",
      "dubsync.summary_one": "Episode ausgewählt",
      "dubsync.summary_many": "Episoden ausgewählt",
      "dubsync.summary_movie_one": "Film ausgewählt",
      "dubsync.summary_movie_many": "Filme ausgewählt",
      "dubsync.queued": "DubSync-Auftrag zur Warteschlange hinzugefügt",
      "dubsync.queue_failed": "Einreihen fehlgeschlagen: ",
      "dubsync.browser_title": "Ordner auswählen",
      "dubsync.browser_up": "← Zurück",
      "dubsync.browser_select": "Diesen Ordner verwenden",
      "dubsync.browser_empty": "Keine Unterordner",
      "dubsync.browser_videos": "Videodatei(en) in diesem Ordner",
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
      "settings.discord.language": "Bot-Sprache",
      "settings.discord.language_en": "Englisch",
      "settings.discord.language_de": "Deutsch",
      "settings.discord.announce": "Ankündigungs-Channel-ID (optional)",
      "settings.discord.announce_hint": "Wenn ein angefragter Download fertig ist, bekommt der Anfragende eine DM; ist ein Ankündigungs-Channel gesetzt, wird dort zusätzlich „jetzt verfügbar“ gepostet.",
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
