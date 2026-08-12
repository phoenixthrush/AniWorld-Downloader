/*
 * Interface translation.
 *
 * Both dictionaries ship with the page so switching is instant. Markup is
 * translated through data attributes:
 *   data-i18n             -> textContent
 *   data-i18n-placeholder -> placeholder
 *   data-i18n-title       -> title
 * Scripts use t("key", "fallback") for strings they build themselves.
 */
(function () {
  const STRINGS = {
    en: {},
    de: {
      "nav.home": "Start",
      "nav.library": "Bibliothek",
      "nav.queue": "Warteschlange",
      "nav.autosync": "Auto-Sync",
      "nav.settings": "Einstellungen",
      "nav.logout": "Abmelden",

      "common.save": "Speichern",
      "common.add": "Hinzufügen",
      "common.delete": "Löschen",
      "common.remove": "Entfernen",
      "common.refresh": "Aktualisieren",
      "common.retry": "Erneut versuchen",
      "common.cancel": "Abbrechen",
      "common.loading": "Wird geladen...",
      "common.timed_out": "Der Server hat nicht rechtzeitig geantwortet",
      "common.failed": "Fehlgeschlagen",

      "index.heading": "AniWorld Downloader",
      "index.search": "Suchen",
      "index.searching": "Wird gesucht...",
      "index.random": "Zufall",
      "index.episodes": "Episoden",
      "index.select_all": "Alle auswählen",
      "index.language": "Sprache",
      "index.provider": "Anbieter",
      "index.format": "Format",
      "index.download_folder": "Zielordner",
      "index.default": "Standard",
      "index.download_selected": "Auswahl herunterladen",
      "index.download_all": "Alle herunterladen",
      "index.loading_episodes": "Episoden werden geladen...",
      "index.loading_series": "Titel wird geladen...",
      "index.autosync_exclude": "Von Auto-Sync ausschließen",
      "index.autosync_excluded": "Von Auto-Sync ausgeschlossen",
      "index.autosync_included": "Wieder in Auto-Sync aufgenommen",
      "index.no_results": "Keine Ergebnisse gefunden.",
      "index.no_episodes_selected": "Keine Episoden ausgewählt.",
      "index.no_episodes": "Keine Episoden verfügbar.",
      "index.queued": "Zur Warteschlange hinzugefügt",
      "index.search_failed": "Suche fehlgeschlagen",
      "index.load_failed": "Titel konnte nicht geladen werden",
      "index.episodes_failed": "Episoden konnten nicht geladen werden.",
      "index.not_available": "[Nicht verfügbar]",
      "index.season": "Staffel",
      "index.movies": "Filme",
      "index.chapter": "Kapitel",
      "index.page": "Seite",
      "index.all": "Alle",

      "browse.new_animes": "Neue Animes",
      "browse.popular_animes": "Beliebte Animes",
      "browse.new_series": "Neue Serien",
      "browse.popular_series": "Beliebte Serien",
      "browse.popular_movies": "Beliebte Filme",
      "browse.new_movies": "Neue Filme",
      "browse.recent_series": "Kürzlich aktualisiert",
      "browse.trending_movies": "Angesagte Filme",
      "browse.trending_manga": "Angesagte Manga",
      "browse.trending_hentai": "Angesagt",
      "browse.genres": "Nach Genre entdecken",
      "browse.genre_failed": "Genre konnte nicht geladen werden",
      "browse.load_more": "Mehr laden",

      "queue.title": "Download-Warteschlange",
      "queue.empty": "Die Warteschlange ist leer.",
      "queue.no_matches": "Zu diesem Filter passt nichts.",
      "queue.clear_finished": "Erledigte entfernen",
      "queue.search": "Titel suchen",
      "queue.filter.all": "Alle",
      "queue.filter.active": "Aktiv",
      "queue.sort": "Sortierung",
      "queue.sort.smart": "Reihenfolge der Warteschlange",
      "queue.sort.newest": "Neueste zuerst",
      "queue.sort.oldest": "Älteste zuerst",
      "queue.sort.title": "Titel A-Z",
      "queue.page_of": "Seite {page} von {pages}",
      "queue.previous": "Zurück",
      "queue.next": "Weiter",
      "queue.solve_captcha": "Captcha lösen",
      "queue.open_captcha": "Captcha im Browser lösen",
      "queue.errors": "Fehler",
      "queue.episode_of": "Episode {current} von {total}",
      "queue.status.queued": "Wartet",
      "queue.status.running": "Läuft",
      "queue.status.completed": "Fertig",
      "queue.status.failed": "Fehler",
      "queue.status.cancelled": "Abgebrochen",
      "queue.status.stopping": "Stoppt nach dieser Episode",
      "queue.force_cancel": "Sofort abbrechen",
      "queue.took": "hat {time} gedauert",
      "queue.active_for": "läuft seit {time}",
      "queue.secs": "{n}s",
      "queue.mins": "{n} Min.",
      "queue.hours": "{h} Std. {m} Min.",
      "captcha.title": "Captcha lösen",
      "captcha.hint": "Klicke auf das Bild, um mit dem Browser zu interagieren.",

      "library.title": "Bibliothek",
      "library.hint":
        "Typ (Serie/Film) und Genre jedes Ordners werden sofort ermittelt; die Episodendateien selbst werden erst beim Öffnen eines Titels geladen.",
      "library.empty": "Keine heruntergeladenen Inhalte gefunden.",
      "library.no_titles": "Dieser Ordner ist leer.",
      "library.load_failed": "Bibliothek konnte nicht geladen werden.",
      "library.episodes": "Ep.",
      "library.confirm_title": 'Wirklich "{name}" komplett löschen?',
      "library.confirm_season": 'Wirklich Staffel {season} von "{name}" löschen?',
      "library.confirm_movies": 'Wirklich alle Filme von "{name}" löschen?',
      "library.confirm_episode": "Wirklich diese Episode löschen?",
      "library.series": "Serien",
      "library.movies": "Filme",
      "library.no_genre": "Sonstiges",
      "library.deleted": "Gelöscht",

      "settings.title": "Einstellungen",
      "settings.persist_notice":
        "Die meisten Änderungen gelten sofort, werden aber beim Neustart zurückgesetzt. Damit sie bleiben, trage sie in deiner .env-Datei ein unter",
      "settings.persist_notice_badge":
        "Nur die unten markierten Bereiche werden zurückgesetzt. Alles andere liegt auf der Festplatte und bleibt von selbst erhalten.",
      "settings.resets": "wird beim Neustart zurückgesetzt",
      "settings.users": "Benutzerverwaltung",
      "settings.user": "Benutzer",
      "settings.role": "Rolle",
      "settings.auth": "Anmeldung",
      "settings.custom_paths": "Eigene Pfade",
      "settings.custom_paths_hint":
        "Gib einem Ordner einen Namen und wähle ihn im Download-Dialog als Ziel aus.",
      "settings.name": "Name",
      "settings.path": "Pfad",
      "settings.path_required": "Name und Pfad sind erforderlich",
      "settings.default_for": "Standard für Seiten",
      "settings.default_for_hint":
        "Wähle aus, für welche Seiten dieser Pfad vorausgewählt sein soll.",
      "settings.defaults": "Standardwerte",
      "settings.download_path": "Downloadpfad",
      "settings.download_path_hint": "Gilt sofort für neue Downloads.",
      "settings.provider_fallback": "Anbieter-Reihenfolge",
      "settings.provider_fallback_hint":
        "Zieh einen Anbieter, um ihn zu verschieben. Der ausgewählte Anbieter wird immer zuerst versucht. Schlägt er fehl, wird diese Reihenfolge durchlaufen.",
      "settings.lang_separation": "Sprachen in eigene Ordner trennen",
      "settings.lang_separation_hint":
        "Downloads werden pro Sprache in Unterordner sortiert (german-dub/, english-sub/, ...).",
      "settings.disable_english_sub": "English-Sub-Downloads deaktivieren",
      "settings.disable_english_sub_hint":
        "English Sub wird aus der Sprachauswahl ausgeblendet und kann nicht heruntergeladen werden.",
      "settings.enable_htv": "Hanime-Tab aktivieren",
      "settings.enable_htv_hint": "Zeigt den Hanime-Tab auf der Startseite.",
      "settings.enable_burningseries": "BurningSeries-Tab aktivieren",
      "settings.enable_burningseries_hint":
        "Standardmäßig aus: Die Seite ist geoblockiert und zusätzlich durch Google reCAPTCHA geschützt, das wir nicht für dich lösen können. Nur einschalten, wenn du sie selbst erreichst.",
      "settings.enable_kinox": "Kinox-Tab aktivieren",
      "settings.enable_kinox_hint":
        "Standardmäßig aus: Kinox verlangt bei jedem einzelnen Download ein Captcha, das du jedes Mal von Hand lösen musst.",
      "settings.enable_library": "Bibliothek aktivieren",
      "settings.enable_autosync": "Auto-Sync aktivieren",
      "settings.enable_autosync_hint":
        "Prüft einmal täglich die neuesten Episoden auf aniworld.to und lädt fehlende Folgen von Serien nach, die du bereits hast. Fügt einen Auto-Sync-Tab nur für Admins hinzu.",
      "settings.autosync_new_only": "Auto-Sync: nur die neuen Episoden",
      "settings.autosync_new_only_hint":
        "Reiht nur die gerade erschienenen Episoden ein, statt alle fehlenden Folgen der Serie nachzuladen. Nutze das, wenn du absichtlich Lücken hast.",
      "autosync.title": "Auto-Sync",
      "autosync.sync_now": "Jetzt synchronisieren",
      "autosync.how_title": "So funktioniert es",
      "autosync.how_1": "Einmal täglich wird die Liste der neuesten Episoden von aniworld.to geladen.",
      "autosync.how_2": "Für jede neue Episode wird geprüft, ob du bereits einen Ordner mit diesem Titel in deiner Bibliothek hast.",
      "autosync.how_3": "Bei einem Treffer wird ermittelt, in welcher Sprache deine vorhandenen Dateien sind, entweder über den Sprachordner oder durch Auslesen der Ton- und Untertitelspuren einer Datei.",
      "autosync.how_4": "Ist die neue Episode in dieser Sprache verfügbar, werden alle noch fehlenden Folgen der Serie eingereiht, in denselben Ordner wie der Rest der Serie.",
      "autosync.how_4_new_only": "Ist die neue Episode in dieser Sprache verfügbar, wird sie in denselben Ordner wie der Rest der Serie eingereiht. Ältere fehlende Folgen bleiben unangetastet, da in den Einstellungen \"nur die neuen Episoden\" aktiv ist.",
      "autosync.how_note": "Es gibt keine Titelliste zu pflegen. Deine Bibliothek ist die Liste, und alles unten Ausgeschlossene wird übersprungen. Es werden nur aniworld.to-Titel berücksichtigt, da die Liste der neuesten Episoden nur dort existiert.",
      "autosync.status_title": "Status",
      "autosync.last_run": "Letzter Lauf",
      "autosync.next_run": "Nächster Lauf",
      "autosync.last_result": "Letztes Ergebnis",
      "autosync.excluded_title": "Ausgeschlossene Titel",
      "autosync.excluded_hint": "Ausgeschlossene Titel werden nie von Auto-Sync eingereiht, auch wenn du sie in der Bibliothek hast. Du kannst auch im Download-Dialog eines Titels \"Von Auto-Sync ausschließen\" anhaken.",
      "autosync.title_column": "Titel",
      "autosync.url_column": "URL",
      "autosync.search_placeholder": "Titel zum Ausschliessen suchen...",
      "autosync.exclude": "Ausschliessen",
      "autosync.already_excluded": "Ausgeschlossen",
      "autosync.added": "Von Auto-Sync ausgeschlossen",
      "autosync.no_exclusions": "Nichts ausgeschlossen.",
      "autosync.never_ran": "Auto-Sync wurde noch nicht ausgeführt.",
      "autosync.mixed_languages":
        "Halte pro Ordner nur eine Sprache. Ohne Sprachtrennung ermittelt Auto-Sync die Sprache eines Titels anhand einer einzigen Datei, der ersten gefundenen Episode, und behandelt den ganzen Titel als diese Sprache. Liegen in einem Ordner Episoden in mehreren Sprachen, sind die übrigen Sprachen für Auto-Sync unsichtbar und bekommen nie neue Episoden.",
      "autosync.turn_on_separation":
        "\"Sprachen in eigene Ordner trennen\" in den Einstellungen aktivieren",
      "autosync.status.queued": "In der Warteschlange",
      "autosync.status.up_to_date": "Aktuell",
      "autosync.status.skipped": "Übersprungen",
      "autosync.status.error": "Fehler",
      "autosync.no_matches": "Keine Titel aus den neuesten Episoden passen zu deiner Bibliothek.",
      "autosync.running": "Läuft...",
      "autosync.started": "Synchronisierung gestartet",
      "autosync.result": "{queued} von {checked} eingereiht",
      "autosync.queued_episodes": "{count} Episoden in {language} eingereiht",
      "settings.enable_library_hint":
        "Zeigt den Bibliothek-Tab zum Durchsehen und Löschen heruntergeladener Dateien.",
      "settings.interface": "Oberfläche",
      "settings.ui_language": "Sprache der Oberfläche",
      "settings.output_format": "Ausgabeformat",
      "settings.output_format_hint":
        "Container für heruntergeladene Dateien. MP4 ist am kompatibelsten mit Playern und Plex.",
      "settings.movie_folder": "Filme in eigenen Ordner legen",
      "settings.movie_folder_hint":
        'Ist die Option aus, landet ein Film direkt im Downloadpfad statt in einem "Titel (Jahr)"-Ordner.',
      "settings.appearance": "Aussehen",
      "settings.custom_css_hint":
        "Eigenes CSS für alle Nutzer dieser Instanz. Schreib eigene Regeln oder hol dir ein Theme mit einer einzigen Import-Zeile. Die Anmeldeseite wird nie mitgestaltet.",
      "settings.css_themes_hint":
        "Fertige Themes liegen in eigenen Repositories, zum Beispiel",
      "settings.css_clear": "Leeren",
      "settings.css_size": "{size} KB",
      "settings.css_size_bytes": "{size} Bytes",
      "settings.css_import_blocked":
        "{host} liefert Dateien als reinen Text aus, deshalb ignorieren Browser diesen Import.",
      "settings.css_import_try": "Nimm stattdessen das hier:",
      "settings.shader": "Hintergrund-Shader",
      "settings.shader_hint":
        "Ein GLSL-Fragment-Shader hinter der ganzen Seite. Schreib den Inhalt von main() und setze fragColor. Verfügbar: u_resolution, u_time und fragColor.",
      "settings.shader_safety":
        "Shader laufen auf der GPU und kommen nicht an Dateien, Cookies oder Netzwerk. Sie werden vor dem Speichern im Browser geprüft, pausieren bei verstecktem Tab und werden mit /settings?nocss=1 komplett übersprungen.",
      "settings.shader_reload": "Gespeichert. Zum Ansehen neu laden.",
      "settings.shader_bad": "Nicht gespeichert",
      "settings.css_recover":
        "Layout kaputt? Öffne /settings?nocss=1, um diese Seite ohne eigenes CSS zu laden.",
      "settings.css_import_hint":
        "Ein importiertes Theme wird vom Browser jedes Besuchers geladen. Der Host dahinter sieht also deren IP und kann das Theme jederzeit ändern. Importiere nur URLs, denen du vertraust.",
      "settings.discord": "Discord-Anfrage-Bot",
      "settings.discord.enable": "Discord-Bot aktivieren",
      "settings.discord.enable_hint":
        "Nutzer können Filme und Serien über Discord anfragen. Anfragen werden dir zur Freigabe geschickt.",
      "settings.discord.token": "Bot-Token",
      "settings.discord.owner": "Owner-Benutzer-ID",
      "settings.discord.mode": "Modus",
      "settings.discord.mode_standard": "Standard (jede Anfrage freigeben)",
      "settings.discord.mode_advanced": "Erweitert (sofort einreihen)",
      "settings.discord.language": "Bot-Sprache",
      "settings.discord.role": "Rollen-ID für Anfragen (optional)",
      "settings.discord.guild": "Server-ID (optional)",
      "settings.discord.announce": "Ankündigungs-Kanal-ID (optional)",
      "settings.discord.announce_hint":
        'Der Anfragende bekommt immer eine DM, wenn ein Download fertig ist. Mit Ankündigungskanal wird dort zusätzlich eine "jetzt verfügbar"-Nachricht gepostet.',
      "settings.discord.running": "Läuft als {user}",
      "settings.discord.stopped": "Gestoppt",
      "settings.discord.unavailable": "discord.py ist nicht installiert",
      "settings.ip": "IP-Prüfung",
      "settings.ip_hint":
        "Prüfe das nach dem Verbinden oder Trennen eines VPN, um die ausgehende IP zu bestätigen.",
      "settings.public_ip": "Aktuelle öffentliche IP",
      "settings.ip_hidden": "Verborgen",
      "settings.ip_meta": "Es wird nichts abgefragt, bis du auf Anzeigen klickst.",
      "settings.reveal": "Anzeigen",
      "settings.ip_loading": "Wird abgefragt...",
      "settings.ip_failed": "IP konnte nicht ermittelt werden",
      "settings.ip_source": "Quelle: {source}",
      "settings.saved": "Gespeichert",
      "settings.save_failed": "Speichern fehlgeschlagen",
      "settings.confirm_delete_user": 'Benutzer "{name}" wirklich löschen?',
      "settings.confirm_delete_path": 'Pfad "{name}" wirklich entfernen?',

      "settings.api_keys": "API-Schlüssel",
      "settings.api_keys_hint":
        "Mit einem Schlüssel können Skripte und andere Tools die JSON-API ohne Anmeldung nutzen. Schick ihn als X-API-Key-Header. Ein Schlüssel wird nur einmal angezeigt, direkt nach dem Erstellen.",
      "settings.api_keys_open":
        "Die Weboberfläche läuft ohne Anmeldung, die API ist also für jeden erreichbar, der diese Seite öffnen kann. Schlüssel werden trotzdem geprüft, aber starte die Weboberfläche mit -wa, wenn du die API absichern willst.",
      "settings.api_key_name": "Name (z. B. Homelab-Skript)",
      "settings.scope_read": "Nur lesen",
      "settings.scope_write": "Lesen und herunterladen",
      "settings.scope_admin": "Voller Zugriff",
      "settings.expiry_never": "Läuft nie ab",
      "settings.expiry_30": "30 Tage",
      "settings.expiry_90": "90 Tage",
      "settings.expiry_365": "1 Jahr",
      "settings.api_key_once": "Jetzt kopieren, er wird nicht noch einmal angezeigt",
      "settings.copy": "Kopieren",
      "settings.copied": "Kopiert",
      "settings.api_key_prefix": "Schlüssel",
      "settings.api_key_scope": "Zugriff",
      "settings.api_key_last_used": "Zuletzt benutzt",
      "settings.api_key_expires": "Läuft ab",
      "settings.api_key_expired": "Abgelaufen",
      "settings.no_keys": "Noch keine API-Schlüssel.",
      "settings.key_name_required": "Gib dem Schlüssel einen Namen",
      "settings.confirm_delete_key":
        'API-Schlüssel "{name}" löschen? Alles, was ihn benutzt, funktioniert danach nicht mehr.',
      "settings.api_docs": "Endpunkte und Beispiele",
      "settings.api_docs_hint":
        "Jeder schreibende Aufruf braucht Content-Type application/json. Lese-Schlüssel dürfen alles aus der Lese-Spalte, Schreib-Schlüssel zusätzlich Downloads, Schlüssel mit vollem Zugriff alles.",
      "settings.api_endpoint": "Endpunkt",
      "settings.api_needs": "Benötigt",
      "settings.api_what": "Funktion",
      "settings.api_ping": "Schlüssel prüfen und Zugriffsstufe anzeigen",
      "settings.api_search": "Auf einer Seite suchen, Body: keyword, site",
      "settings.api_series": "Titel, Poster, Beschreibung und Genres",
      "settings.api_seasons": "Staffeln einer Serie",
      "settings.api_episodes": "Episoden einer Staffel, mit Sprachen",
      "settings.api_providers": "Verfügbare Hoster je Sprache",
      "settings.api_queue": "Warteschlange mit Fortschritt",
      "settings.api_queue_page":
        "Eine Seite der Warteschlange mit Gesamtzahl und Zählern. Seitenweise abgerufene " +
        "Einträge enthalten kein episodes-Feld. status: queued, running, completed, failed, " +
        "cancelled, active, finished. sort: smart, newest, oldest, title",
      "settings.api_queue_counts": "Wie viele Einträge je Status vorhanden sind",
      "settings.api_download": "Episoden einreihen, siehe Beispiel unten",
      "settings.api_cancel": "Wartenden oder laufenden Eintrag abbrechen",
      "settings.api_retry": "Fehlgeschlagenen Eintrag erneut versuchen",
      "settings.api_remove": "Eintrag aus der Warteschlange entfernen",
      "settings.api_clear": "Fertige Einträge löschen",
      "settings.api_lib_locations": "Vorhandene Downloadordner",
      "settings.api_lib_titles": "Titel in einem Ordner",
      "settings.api_lib_title": "Dateien eines einzelnen Titels",
      "settings.api_lib_delete": "Titel, Staffel oder Episode löschen",
      "settings.api_sync_status": "Letzter Lauf und dessen Bericht",
      "settings.api_sync_run": "Sync sofort starten",
      "settings.api_settings": "Aktuelle Einstellungen lesen",
      "settings.api_example_queue": "Warteschlange lesen",
      "settings.api_example_download": "Download starten",
      "settings.api_example_hint":
        'Die Episoden-URLs kommen von /api/episodes, und /api/providers zeigt dir, welche Hoster die gewünschte Sprache haben. Mit "custom_path_id" landet der Download in einem deiner eigenen Pfade.'
    }
  };

  const language = window.UI_LANGUAGE === "de" ? "de" : "en";
  const dictionary = STRINGS[language] || {};

  window.t = function (key, fallback, values) {
    let text = dictionary[key] || fallback || key;
    if (values) {
      Object.keys(values).forEach(function (name) {
        text = text.replace("{" + name + "}", values[name]);
      });
    }
    return text;
  };

  function apply(root) {
    (root || document).querySelectorAll("[data-i18n]").forEach(function (el) {
      const value = dictionary[el.dataset.i18n];
      if (value) el.textContent = value;
    });
    (root || document)
      .querySelectorAll("[data-i18n-placeholder]")
      .forEach(function (el) {
        const value = dictionary[el.dataset.i18nPlaceholder];
        if (value) el.placeholder = value;
      });
    (root || document).querySelectorAll("[data-i18n-title]").forEach(function (el) {
      const value = dictionary[el.dataset.i18nTitle];
      if (value) el.title = value;
    });
  }

  window.applyTranslations = apply;
  document.addEventListener("DOMContentLoaded", function () {
    apply(document);
  });
})();
