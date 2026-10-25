package de.tobidervogel.aniworld.site

import org.json.JSONArray
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import org.jsoup.parser.Parser

/**
 * Liest die HTML-Seiten von aniworld.to. Reine Funktionen ohne Netz, damit die Tests mit
 * gespeicherten Seiten laufen. Die Markierungen stammen aus den Python-Modellen
 * (models/aniworld_to, search.py); wo die Seite umgebaut wird, zuerst dort nachsehen.
 */
object AniWorldParser {
    const val BASIS = "https://aniworld.to"

    private val SERIEN_LINK = Regex("^/anime/stream/[a-zA-Z0-9-]+/?$")
    private val STAFFEL_LINK = Regex("""href="(?:https://aniworld\.to)?(/anime/stream/([a-zA-Z0-9-]+)/staffel-(\d+))"""")
    private val NEUE_FOLGE_LINK = Regex("""/anime/stream/[^"/]+/staffel-(\d+)/episode-(\d+)""")

    fun absolut(pfad: String?): String? {
        val p = pfad?.trim().orEmpty()
        if (p.isEmpty() || p.startsWith("data:")) return null
        return when {
            p.startsWith("http") -> p
            p.startsWith("//") -> "https:$p"
            p.startsWith("/") -> BASIS + p
            else -> "$BASIS/$p"
        }
    }

    /** Serien-URL ohne Staffel-/Folgenteil, z. B. für geteilte Links. */
    fun serienUrl(url: String): String? {
        val m = Regex("""https?://(?:www\.)?aniworld\.to/anime/stream/([a-zA-Z0-9-]+)""").find(url) ?: return null
        return "$BASIS/anime/stream/${m.groupValues[1]}"
    }

    private fun text(html: String) = Parser.unescapeEntities(html, false).replace(Regex("\\s+"), " ").trim()

    private fun bild(el: Element?): String? {
        el ?: return null
        return absolut(el.attr("data-src").ifBlank { el.attr("src") })
    }

    // ---------------------------------------------------------------- Startseite, Genres

    /** Cover-Karten, wie sie Startseite und Genre-Seiten gleich darstellen. */
    fun karten(html: String): List<Karte> {
        val doc = Jsoup.parseBodyFragment(html, BASIS)
        val gesehen = HashSet<String>()
        val ergebnis = ArrayList<Karte>()
        for (a in doc.select("a[href]")) {
            val href = a.attr("href").removePrefix(BASIS)
            if (!SERIEN_LINK.matches(href)) continue
            val url = BASIS + href.trimEnd('/')
            if (!gesehen.add(url)) continue
            val h3 = a.selectFirst("h3")
            val titel = (h3?.ownText()?.takeIf { it.isNotBlank() } ?: h3?.text() ?: a.attr("title")).trim()
            if (titel.isEmpty()) continue
            ergebnis += Karte(
                titel = titel,
                url = url,
                cover = bild(a.selectFirst("img")),
                genre = a.selectFirst("small")?.text()?.trim().orEmpty(),
            )
        }
        return ergebnis
    }

    /** Abschnitt der Startseite ab einer `<h2>`-Überschrift bis zur nächsten. */
    fun abschnitt(html: String, ueberschrift: String): List<Karte> {
        val kopf = Regex("<h2>\\s*${Regex.escape(ueberschrift)}\\s*</h2>", RegexOption.IGNORE_CASE).find(html)
            ?: return emptyList()
        val rest = html.substring(kopf.range.last + 1)
        val ende = rest.indexOf("<h2")
        return karten(if (ende >= 0) rest.substring(0, ende) else rest)
    }

    fun genres(html: String): List<Genre> {
        val doc = Jsoup.parse(html, BASIS)
        val liste = doc.selectFirst("ul.homeContentGenresList") ?: return emptyList()
        return liste.select("a[href*=/genre/]").mapNotNull { a ->
            val slug = a.attr("href").substringAfter("/genre/").trim('/').substringBefore('/')
            val name = a.text().trim()
            if (slug.isEmpty() || name.isEmpty()) null else Genre(name, slug)
        }.distinctBy { it.slug }
    }

    /** Karten einer Genre-Seite und ob es eine weitere Seite gibt. */
    fun genreSeite(html: String, slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        val start = html.indexOf("seriesListContainer")
        val karten = karten(if (start >= 0) html.substring(start) else html)
        val weiter = html.contains("/genre/$slug/${seite + 1}")
        return karten to weiter
    }

    fun neueFolgen(html: String): List<NeueFolge> {
        val doc = Jsoup.parse(html, BASIS)
        val wurzel = doc.selectFirst(".newEpisodeList") ?: doc.body()
        val nachUrl = LinkedHashMap<String, NeueFolge>()
        for (a in wurzel.select("a[href*=/staffel-]")) {
            val href = a.attr("href")
            val m = NEUE_FOLGE_LINK.find(href) ?: continue
            val url = absolut(href.substring(href.indexOf("/anime/stream/"))) ?: continue
            // Die Flaggen stehen als Geschwister neben dem Link, innerhalb derselben Zeile.
            val zeile = a.parent() ?: a
            val sprachen = zeile.select("img.flag").mapNotNull { Sprache.ausFlagge(it.attr("data-src").ifBlank { it.attr("src") }) }
            val alt = nachUrl[url]
            if (alt != null) {
                nachUrl[url] = alt.copy(sprachen = (alt.sprachen + sprachen).distinct())
            } else {
                nachUrl[url] = NeueFolge(
                    titel = a.selectFirst("strong")?.text()?.trim().orEmpty(),
                    url = url,
                    staffel = m.groupValues[1].toInt(),
                    folge = m.groupValues[2].toInt(),
                    datum = a.selectFirst(".elementFloatRight")?.text()?.trim().orEmpty(),
                    sprachen = sprachen.distinct(),
                )
            }
        }
        return nachUrl.values.toList()
    }

    // ---------------------------------------------------------------- Suche

    /** Antwort von POST /ajax/search: JSON-Liste mit title (mit <em>), link, description. */
    fun suche(json: String): List<Treffer> {
        val trimmed = json.trim()
        if (!trimmed.startsWith("[")) return emptyList()
        val arr = JSONArray(trimmed)
        val ergebnis = ArrayList<Treffer>()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val link = o.optString("link")
            if (!SERIEN_LINK.matches(link)) continue
            val titel = text(o.optString("title").ifBlank { o.optString("name") }.replace(Regex("</?em>"), ""))
            ergebnis += Treffer(
                titel = titel,
                url = BASIS + link.trimEnd('/'),
                beschreibung = text(o.optString("description").replace(Regex("<[^>]+>"), "")),
            )
        }
        return ergebnis.distinctBy { it.url }
    }

    /** Antwort von POST /ajax/randomGeneratorSeries: JSON-Liste, `link` ist nur der Slug. */
    fun zufall(json: String): List<String> {
        val t = json.trim()
        if (!t.startsWith("[")) return emptyList()
        val arr = JSONArray(t)
        return (0 until arr.length()).mapNotNull { i ->
            arr.optJSONObject(i)?.optString("link")?.trim('/', ' ')?.takeIf { it.matches(Regex("[\\w-]+")) }
                ?.let { "$BASIS/anime/stream/$it" }
        }
    }

    // ---------------------------------------------------------------- Serie

    fun serie(html: String, url: String): Serie {
        val doc = Jsoup.parse(html, BASIS)
        val kopf = doc.selectFirst("div.series-title")
        val titel = kopf?.selectFirst("h1 span")?.text()?.trim()
            ?: doc.selectFirst("h1")?.text()?.trim()
            ?: url.substringAfterLast('/')
        val jahre = kopf?.selectFirst("small")?.let { small: Element ->
            fun jahr(prop: String): String? = small.selectFirst("[itemprop=$prop] a")?.attr("href")
                ?.trimEnd('/')?.substringAfterLast('/')?.takeIf { j -> j.all(Char::isDigit) }
            val von = jahr("startDate")
            val bis = jahr("endDate")
            when {
                von == null -> null
                bis == null || bis == von -> von
                else -> "$von–$bis"
            }
        }
        val beschreibung = doc.selectFirst("p.seri_des")?.let { p: Element ->
            p.attr("data-full-description").ifBlank { p.ownText() }
        }?.trim().orEmpty()
        val genres = doc.select("div.genres [itemprop=genre]").map { it.text().trim() }.filter { it.isNotEmpty() }

        val slug = url.trimEnd('/').substringAfterLast('/')
        val staffeln = sortedMapOf<Int, StaffelRef>()
        for (m in STAFFEL_LINK.findAll(html)) {
            if (m.groupValues[2] != slug) continue
            val nr = m.groupValues[3].toInt()
            staffeln.getOrPut(nr) { StaffelRef(nr, BASIS + m.groupValues[1], false) }
        }
        val liste = staffeln.values.toMutableList()
        if (html.contains("title=\"Alle Filme\"") || html.contains("/anime/stream/$slug/filme\"")) {
            liste += StaffelRef(0, "$BASIS/anime/stream/$slug/filme", true)
        }

        return Serie(
            url = url,
            titel = titel,
            beschreibung = beschreibung,
            genres = genres,
            jahre = jahre,
            cover = bild(doc.selectFirst("div.seriesCoverBox img")),
            fsk = doc.selectFirst("[data-fsk]")?.attr("data-fsk")?.trim()?.ifEmpty { null },
            imdb = doc.selectFirst("[data-imdb]")?.attr("data-imdb")?.trim()?.ifEmpty { null },
            staffeln = liste,
        )
    }

    // ---------------------------------------------------------------- Staffel

    fun staffel(html: String, ref: StaffelRef): List<Folge> {
        val doc = Jsoup.parse(html, BASIS)
        val folgen = ArrayList<Folge>()
        for (tr in doc.select("tr[itemtype*=schema.org/Episode]")) {
            val link: String
            val nummer: Int?
            if (ref.istFilme) {
                link = tr.selectFirst("a[href*=/film-]")?.attr("href") ?: continue
                nummer = tr.attr("data-episode-season-id").toIntOrNull()
                    ?: Regex("film-(\\d+)").find(link)?.groupValues?.get(1)?.toIntOrNull()
            } else {
                link = tr.selectFirst("a[itemprop=url]")?.attr("href")
                    ?: tr.selectFirst("a[href*=/episode-]")?.attr("href") ?: continue
                nummer = tr.selectFirst("meta[itemprop=episodeNumber]")?.attr("content")?.toIntOrNull()
                    ?: Regex("episode-(\\d+)").find(link)?.groupValues?.get(1)?.toIntOrNull()
            }
            val zelle = tr.selectFirst("td.seasonEpisodeTitle")
            val de = zelle?.selectFirst("strong")?.text()?.trim().orEmpty()
            val en = zelle?.selectFirst("span")?.text()?.trim().orEmpty()
            folgen += Folge(
                url = absolut(link) ?: continue,
                nummer = nummer ?: (folgen.size + 1),
                staffel = ref.nummer,
                istFilm = ref.istFilme,
                titelDe = if (ref.istFilme) en.ifBlank { de } else de,
                titelEn = en,
                sprachen = tr.select("img.flag").mapNotNull {
                    Sprache.ausFlagge(it.attr("data-src").ifBlank { it.attr("src") })
                }.toSortedSet(),
                hoster = tr.select("i.icon[title]").map { it.attr("title").removePrefix("Hoster ").trim() }
                    .filter { it.isNotEmpty() }.distinct(),
            )
        }
        return folgen
    }

    // ---------------------------------------------------------------- Folge

    /** Hoster-Links der Folgenseite, gruppiert nach Sprache. */
    fun folgenLinks(html: String): FolgenLinks {
        val doc: Document = Jsoup.parse(html, BASIS)
        val links = LinkedHashMap<Sprache, LinkedHashMap<String, String>>()
        for (li in doc.select("li[data-lang-key]")) {
            val sprache = Sprache.ausKey(li.attr("data-lang-key")) ?: continue
            val a = li.selectFirst("a.watchEpisode") ?: continue
            val name = li.selectFirst("h4")?.text()?.trim()
                ?: li.selectFirst("i.icon")?.attr("title")?.removePrefix("Hoster ")?.trim()
                ?: continue
            val ziel = absolut(a.attr("href").ifBlank { li.attr("data-link-target") }) ?: continue
            links.getOrPut(sprache) { LinkedHashMap() }.putIfAbsent(name, ziel)
        }
        return FolgenLinks(links)
    }
}
