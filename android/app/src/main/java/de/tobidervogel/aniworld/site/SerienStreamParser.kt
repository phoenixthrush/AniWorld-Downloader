package de.tobidervogel.aniworld.site

import org.jsoup.Jsoup
import org.jsoup.nodes.Element

/**
 * Liest serienstream.to (neues Layout seit 2025). Markierungen wie in models/s_to/ des Originals,
 * am 24.10.2026 gegen die echte Seite geprüft. Alle Adressen werden auf serienstream.to
 * vereinheitlicht; welcher Spiegel gerade antwortet, entscheidet erst [SerienStream].
 */
object SerienStreamParser {
    const val BASIS = "https://serienstream.to"
    val HOSTS = setOf("serienstream.to", "serienstream.cx", "s.to")

    private val SERIE = Regex("""^(?:https?://(?:www\.)?(?:serienstream\.(?:to|cx)|s\.to))?/serie/(?:stream/)?([a-zA-Z0-9-]+)(?:/staffel-(\d+))?""")
    private val FOLGE = Regex("""/serie/([a-zA-Z0-9-]+)/staffel-(\d+)/episode-(\d+)""")

    /** Serien-Adresse aus jeder Adresse der Seite (Staffel, Folge, alter s.to-Link). */
    fun serienUrl(url: String): String? = SERIE.find(url.trim())?.let { "$BASIS/serie/${it.groupValues[1]}" }

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

    private fun bild(img: Element?): String? =
        img?.let { absolut(it.attr("data-src").ifBlank { it.attr("src") }) }

    /**
     * Cover-Karten: Links auf /serie/… mit Bild (alt = Titel) oder Titelzeile (h6).
     * Doppelte Serien fallen weg; zeigt eine Karte auf eine Staffel, merkt sie sich die Nummer.
     */
    fun karten(html: String): List<Karte> {
        val doc = Jsoup.parseBodyFragment(html, BASIS)
        val ergebnis = LinkedHashMap<String, Karte>()
        for (a in doc.select("a[href*=/serie/]")) {
            val m = SERIE.find(a.attr("href")) ?: continue
            if (a.attr("href").contains("/episode-")) continue
            val url = "$BASIS/serie/${m.groupValues[1]}"
            if (url in ergebnis) continue
            // Titel: Titelzeile der Karte (Suche, Genre) vor dem alt-Text des Bildes (Startseite).
            // In der Suche umschließt ein Link die ganze Karte, ein zweiter nur das Bild.
            val karte = a.closest(".card, .show-card")
            val img = a.selectFirst("img") ?: karte?.selectFirst("img")
            fun nichtLeer(t: String?) = t?.trim()?.takeIf { it.isNotEmpty() }
            val titel = nichtLeer(a.selectFirst("h6")?.text()) ?: nichtLeer(karte?.selectFirst("h6")?.text())
                ?: nichtLeer(img?.attr("alt")) ?: a.attr("title").trim()
            if (titel.isEmpty()) continue
            ergebnis[url] = Karte(titel, url, bild(img), staffel = m.groupValues[2].toIntOrNull())
        }
        return ergebnis.values.toList()
    }

    /** Abschnitt von /beliebte-serien ab einer `<h2>`, deren Text den Hinweis enthält. */
    fun abschnitt(html: String, hinweis: String): List<Karte> {
        val i = Regex("<h2[^>]*>[^<]*${Regex.escape(hinweis)}", RegexOption.IGNORE_CASE).find(html) ?: return emptyList()
        val rest = html.substring(i.range.last + 1)
        val ende = rest.indexOf("<h2")
        return karten(if (ende >= 0) rest.substring(0, ende) else rest)
    }

    fun genres(html: String): List<Genre> {
        val doc = Jsoup.parse(html, BASIS)
        return doc.select("a[href*=/genre/]").mapNotNull { a ->
            val slug = a.attr("href").substringAfter("/genre/").substringBefore('?').substringBefore('#').trim('/')
            val name = a.text().trim()
            if (slug.isEmpty() || slug.contains('/') || name.isEmpty() || name.length > 30) null else Genre(name, slug)
        }.distinctBy { it.slug }
    }

    /** Suchergebnisse: nur die Gruppe „Serien“, nicht Folgen, Personen oder FAQ. */
    fun suche(html: String): Pair<List<Treffer>, String?> {
        val doc = Jsoup.parse(html, BASIS)
        val gruppe = doc.selectFirst("[data-group=shows]") ?: return emptyList<Treffer>() to null
        val treffer = karten(gruppe.outerHtml()).map { Treffer(it.titel, it.url, "", it.cover) }
        val weiter = gruppe.selectFirst("a[rel=next]")?.attr("abs:href")?.ifBlank { null }
        return treffer to weiter
    }

    /** Karten einer Genre-Seite und ob es eine weitere Seite gibt (?page=N). */
    fun genreSeite(html: String): Pair<List<Karte>, Boolean> {
        val doc = Jsoup.parse(html, BASIS)
        return karten(html) to (doc.selectFirst("a[rel=next]") != null)
    }

    fun serie(html: String, url: String): Serie {
        val doc = Jsoup.parse(html, BASIS)
        val titel = doc.selectFirst("h1")?.text()?.trim().orEmpty().ifEmpty { url.substringAfterLast('/') }
        val jahre = doc.select("a[href*=/jahr/]").mapNotNull { a ->
            a.attr("href").trimEnd('/').substringAfterLast('/').takeIf { j -> j.length == 4 && j.all(Char::isDigit) }
        }.distinct().let { j ->
            when (j.size) {
                0 -> null
                1 -> j[0]
                else -> "${j.first()}–${j.last()}"
            }
        }
        val fsk = Regex("""FSK (\d{1,2})""").find(html)?.groupValues?.get(1)
        val imdb = Regex("""imdb\.com/title/(tt\d{7,8})""").find(html)?.groupValues?.get(1)
        val genres = doc.select("li.series-group").firstOrNull { it.selectFirst("strong")?.text()?.startsWith("Genre") == true }
            ?.select("a")?.map { it.text().trim() }?.filter { it.isNotEmpty() }.orEmpty()

        val slug = SERIE.find(url)?.groupValues?.get(1).orEmpty()
        val staffeln = sortedMapOf<Int, StaffelRef>()
        for (a in doc.select("a[href*=/staffel-]")) {
            val m = SERIE.find(a.attr("href")) ?: continue
            if (m.groupValues[1] != slug || a.attr("href").contains("/episode-")) continue
            val nr = m.groupValues[2].toIntOrNull() ?: continue
            // Staffel 0 heißt auf der Seite „Filme“ und kommt in der App ans Ende.
            staffeln.getOrPut(nr) { StaffelRef(nr, "$BASIS/serie/$slug/staffel-$nr", nr == 0) }
        }
        val liste = staffeln.values.filter { !it.istFilme } + staffeln.values.filter { it.istFilme }

        return Serie(
            url = url,
            titel = titel,
            beschreibung = doc.selectFirst(".description-text")?.text()?.trim().orEmpty(),
            genres = genres,
            jahre = jahre,
            cover = bild(doc.selectFirst("img[data-src*=/media/images/channel/], img[src*=/media/images/channel/]")),
            fsk = fsk,
            imdb = imdb,
            staffeln = liste,
        )
    }

    fun staffel(html: String, ref: StaffelRef): List<Folge> {
        val doc = Jsoup.parse(html, BASIS)
        val folgen = ArrayList<Folge>()
        for (tr in doc.select("tr.episode-row")) {
            // Die Zeile verlinkt per onclick, nicht per href.
            val m = FOLGE.find(tr.attr("onclick")) ?: FOLGE.find(tr.select("a[href]").joinToString(" ") { it.attr("href") }) ?: continue
            if (m.groupValues[2].toInt() != ref.nummer) continue
            val nummer = tr.selectFirst(".episode-number-cell")?.text()?.trim()?.toIntOrNull() ?: m.groupValues[3].toInt()
            val de = tr.selectFirst(".episode-title-ger")?.text()?.trim().orEmpty()
            val en = tr.selectFirst(".episode-title-eng")?.text()?.trim().orEmpty()
            val klassen = tr.select("[class*=svg-flag-]").joinToString(" ") { it.className() }
            folgen += Folge(
                url = "$BASIS/serie/${m.groupValues[1]}/staffel-${m.groupValues[2]}/episode-${m.groupValues[3]}",
                nummer = nummer,
                staffel = ref.nummer,
                istFilm = ref.istFilme,
                titelDe = de.ifBlank { en },
                titelEn = en,
                sprachen = buildSet {
                    if ("svg-flag-german" in klassen) add(Sprache.DE_DUB)
                    if ("svg-flag-english" in klassen) add(Sprache.EN_DUB)
                }.toSortedSet(),
                hoster = tr.select("img.watch-link").map { it.attr("title").ifBlank { it.attr("alt") }.trim() }.filter { it.isNotEmpty() }.distinct(),
            )
        }
        return folgen.distinctBy { it.url }
    }

    fun folgenLinks(html: String): FolgenLinks {
        val doc = Jsoup.parse(html, BASIS)
        val links = LinkedHashMap<Sprache, LinkedHashMap<String, String>>()
        for (b in doc.select("[data-play-url]")) {
            val sprache = when (b.attr("data-language-label").trim().lowercase()) {
                "deutsch" -> Sprache.DE_DUB
                "englisch", "english" -> Sprache.EN_DUB
                else -> continue
            }
            val name = b.attr("data-provider-name").trim()
            val ziel = absolut(b.attr("data-play-url"))
            if (name.isEmpty() || ziel == null) continue
            links.getOrPut(sprache) { LinkedHashMap() }.putIfAbsent(name, ziel)
        }
        return FolgenLinks(links)
    }
}
