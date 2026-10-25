package de.tobidervogel.aniworld.site

import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element

/**
 * Liest filmo.to (nur Filme), wie models/filmo_to/episode.py und query_filmo() im Original.
 * Am 24.10.2026 gegen die echte Seite geprüft. Ein Film wird in der App eine „Serie“ mit
 * genau einer Folge, damit Laden, Streamen und Bibliothek ohne Sonderwege funktionieren.
 */
object FilmoParser {
    const val BASIS = "https://filmo.to"
    private val FILM = Regex("""^(?:https?://(?:www\.)?filmo\.to)?/movies/([\w-]+)""")

    /** In FolgenLinks steht statt einer Adresse das Quell-Token; [Filmo] tauscht es über /n ein. */
    const val TOKEN_PRAEFIX = "$BASIS/n#p="

    fun filmUrl(url: String): String? = FILM.find(url.trim())?.let { "$BASIS/movies/${it.groupValues[1]}" }

    private fun absolut(p: String?): String? {
        val s = p?.trim().orEmpty()
        if (s.isEmpty() || s.startsWith("data:")) return null
        return if (s.startsWith("http")) s else BASIS + "/" + s.trimStart('/')
    }

    /** Poster-Raster (/movies) und Spotlight-Karten (Suche); doppelte Filme fallen weg. */
    fun karten(html: String): List<Karte> {
        val doc = Jsoup.parse(html, BASIS)
        val ergebnis = LinkedHashMap<String, Karte>()
        for (a in doc.select("a[href*=/movies/]")) {
            val url = filmUrl(a.attr("href")) ?: continue
            if (url in ergebnis) continue
            val titel = a.selectFirst(".movie-poster-grid-card__title, .popular-spotlight-card__title")?.text()?.trim()
                ?: continue
            if (titel.isEmpty()) continue
            ergebnis[url] = Karte(titel, url, absolut(a.selectFirst("img")?.attr("src")))
        }
        return ergebnis.values.toList()
    }

    fun weitereSeite(html: String) = Jsoup.parse(html).selectFirst("a[rel=next]") != null

    /** Genres aus dem Filter der Filmliste; der Slug ist Filmos Zahl (genre_id). */
    fun genres(html: String): List<Genre> =
        Jsoup.parse(html).select("select[name=genre_id] option").mapNotNull { o ->
            val id = o.attr("value").trim()
            if (id.isEmpty() || !id.all(Char::isDigit)) null else Genre(o.text().trim(), id)
        }.distinctBy { it.slug }

    private fun feld(doc: Document, name: String): Element? =
        doc.select("dl").firstOrNull { dl: Element -> dl.selectFirst("h3")?.text()?.trim() == name }?.selectFirst("dd")

    fun film(html: String, url: String): Serie {
        val doc = Jsoup.parse(html, BASIS)
        val titel = doc.selectFirst("h1")?.text()?.trim().orEmpty().ifEmpty { url.substringAfterLast('/') }
        val jahr = feld(doc, "Erscheinungsdatum")?.text()?.let { Regex("""\b(\d{4})\b""").find(it)?.groupValues?.get(1) }
        val genres = feld(doc, "Genres")?.select("a")?.map { it.text().trim() }?.filter { it.isNotEmpty() }
            ?.ifEmpty { null }
            ?: feld(doc, "Genres")?.text()?.split(',')?.map { it.trim() }?.filter { it.isNotEmpty() }.orEmpty()
        val beschreibung = doc.selectFirst("p.movie-detail-synopsis")?.wholeText()?.trim()
            ?: doc.selectFirst("meta[property=og:description]")?.attr("content")?.trim().orEmpty()
        val poster = absolut(doc.selectFirst("img[src*=/img/poster/]")?.attr("src"))
            ?: absolut(doc.selectFirst("meta[property=og:image]")?.attr("content"))
        return Serie(
            url = url,
            titel = titel,
            beschreibung = beschreibung.replace(Regex("[ \\t]+"), " "),
            genres = genres,
            jahre = jahr,
            cover = poster,
            fsk = null,
            imdb = null,
            staffeln = listOf(StaffelRef(0, url, istFilme = true)),
        )
    }

    /** Der Film als einzige „Folge“, mit den Sprachen aus den Anbieterzeilen. */
    fun folge(html: String, url: String): Folge {
        val s = film(html, url)
        val l = links(html)
        return Folge(
            url = url,
            nummer = 1,
            staffel = 0,
            istFilm = true,
            titelDe = s.jahre?.let { "${s.titel} ($it)" } ?: s.titel,
            titelEn = "",
            sprachen = l.sprachen.toSortedSet(),
            hoster = l.links.values.flatMap { it.keys }.distinct(),
        )
    }

    fun links(html: String): FolgenLinks {
        val doc = Jsoup.parse(html, BASIS)
        val links = LinkedHashMap<Sprache, LinkedHashMap<String, String>>()
        for (zeile in doc.select(".provider-row")) {
            val sprache = when (zeile.selectFirst(".provider-row__lang")?.text()?.trim()?.lowercase()) {
                "deutsch", "german" -> Sprache.DE_DUB
                "english", "englisch" -> Sprache.EN_DUB
                else -> continue
            }
            for (chip in zeile.select("[data-provider-chip]")) {
                val name = chip.attr("aria-label").trim()
                val token = chip.attr("data-p").trim()
                if (name.isEmpty() || token.isEmpty()) continue
                links.getOrPut(sprache) { LinkedHashMap() }.putIfAbsent(name, TOKEN_PRAEFIX + token)
            }
        }
        return FolgenLinks(links)
    }

    /** Link auf der Zwischenseite „Video öffnen“ (/n/<x>), wenn Filmo nicht selbst weiterleitet. */
    fun externerLink(html: String): String? =
        Jsoup.parse(html, BASIS).select("a.open[href], a[target=_blank][href]")
            .map { it.attr("abs:href") }
            .firstOrNull { it.startsWith("http") && !it.contains("://filmo.to") && !it.contains("://www.filmo.to") }

    fun csrf(html: String): String? =
        Jsoup.parse(html).selectFirst("meta[name=csrf-token]")?.attr("content")?.trim()?.ifEmpty { null }
}
