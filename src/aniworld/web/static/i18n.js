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
      "nav.settings": "Einstellungen",
      "nav.logout": "Abmelden",
      "footer.opensource": "AniWorld Downloader ist Open Source.",
      "footer.github": "Auf GitHub ansehen",

      "common.save": "Speichern",
      "common.add": "Hinzufügen",
      "common.delete": "Löschen",
      "common.remove": "Entfernen",
      "common.refresh": "Aktualisieren",
      "common.retry": "Erneut versuchen",
      "common.cancel": "Abbrechen",
      "common.loading": "Wird geladen...",
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

      "queue.title": "Download-Warteschlange",
      "queue.empty": "Die Warteschlange ist leer.",
      "queue.clear_finished": "Erledigte entfernen",
      "queue.solve_captcha": "Captcha lösen",
      "queue.open_captcha": "Captcha im Browser lösen",
      "queue.errors": "Fehler",
      "queue.episode_of": "Episode {current} von {total}",
      "queue.status.queued": "Wartet",
      "queue.status.running": "Läuft",
      "queue.status.completed": "Fertig",
      "queue.status.failed": "Fehler",
      "queue.status.cancelled": "Abgebrochen",
      "captcha.title": "Captcha lösen",
      "captcha.hint": "Klicke auf das Bild, um mit dem Browser zu interagieren.",

      "library.title": "Bibliothek",
      "library.hint":
        "Ordner werden erst beim Öffnen geladen, es wird nichts im Voraus durchsucht.",
      "library.empty": "Keine heruntergeladenen Inhalte gefunden.",
      "library.no_titles": "Dieser Ordner ist leer.",
      "library.load_failed": "Bibliothek konnte nicht geladen werden.",
      "library.episodes": "Ep.",
      "library.confirm_title": 'Wirklich "{name}" komplett löschen?',
      "library.confirm_season": 'Wirklich Staffel {season} von "{name}" löschen?',
      "library.confirm_episode": "Wirklich diese Episode löschen?",
      "library.deleted": "Gelöscht",

      "settings.title": "Einstellungen",
      "settings.persist_notice":
        "Änderungen gelten sofort, werden aber beim Neustart zurückgesetzt. Damit sie bleiben, trage sie in deiner .env-Datei ein unter",
      "settings.users": "Benutzerverwaltung",
      "settings.user": "Benutzer",
      "settings.role": "Rolle",
      "settings.auth": "Anmeldung",
      "settings.custom_paths": "Eigene Pfade",
      "settings.custom_paths_hint":
        "Gib einem Ordner einen Namen und wähle ihn im Download-Dialog als Ziel aus.",
      "settings.name": "Name",
      "settings.path": "Pfad",
      "settings.default_for": "Standard für Seiten",
      "settings.default_for_hint":
        "Wähle aus, für welche Seiten dieser Pfad vorausgewählt sein soll.",
      "settings.defaults": "Standardwerte",
      "settings.download_path": "Downloadpfad",
      "settings.download_path_hint": "Gilt sofort für neue Downloads.",
      "settings.provider_fallback": "Anbieter-Reihenfolge",
      "settings.provider_fallback_hint":
        "Der ausgewählte Anbieter wird immer zuerst versucht. Schlägt er fehl, wird diese Reihenfolge durchlaufen.",
      "settings.lang_separation": "Sprachen in eigene Ordner trennen",
      "settings.lang_separation_hint":
        "Downloads werden pro Sprache in Unterordner sortiert (german-dub/, english-sub/, ...).",
      "settings.disable_english_sub": "English-Sub-Downloads deaktivieren",
      "settings.disable_english_sub_hint":
        "English Sub wird aus der Sprachauswahl ausgeblendet und kann nicht heruntergeladen werden.",
      "settings.enable_htv": "Hanime-Tab aktivieren",
      "settings.enable_htv_hint": "Zeigt den Hanime-Tab auf der Startseite.",
      "settings.enable_library": "Bibliothek aktivieren",
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
      "settings.confirm_delete_path": 'Pfad "{name}" wirklich entfernen?'
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
