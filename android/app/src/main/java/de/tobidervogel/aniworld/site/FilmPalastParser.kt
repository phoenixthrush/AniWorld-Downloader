package de.tobidervogel.aniworld.site

import org.jsoup.Jsoup
import org.jsoup.nodes.Element

/**
 * Liest filmpalast.to (nur Filme), wie models/filmpalast_to/episode.py und query_filmpalast() im
 * Original. Ein Film ist wie bei Filmo eine „Serie“ mit genau einer Folge. Die Filmseite verlinkt
 * die Hoster direkt (data-player-url), es gibt keine Weiterleitung über die Seite.
 */
object FilmPalastParser {
    const val BASIS = "https://filmpalast.to"
    private val FILM = Regex("""^(?:https?:)?(?://(?:www\.)?filmpalast\.to)?/stream/([\w-]+)""")

    fun filmUrl(url: String): String? = FILM.find(url.trim())?.let { "$BASIS/stream/${it.groupValues[1]}" }

    private fun absolut(p: String?): String? {
        val s = p?.trim().orEmpty()
        return when {
            s.isEmpty() || s.startsWith("data:") -> null
            s.startsWith("//") -> "https:$s"
            s.startsWith("http") -> s
            else -> BASIS + "/" + s.trimStart('/')
        }
    }

    /** Filmlisten (Neu, Top, Suche, Genre): je Film ein `<article class="liste …">`. */
    fun karten(html: String): List<Karte> {
        val doc = Jsoup.parse(html, BASIS)
        val ergebnis = LinkedHashMap<String, Karte>()
        for (art in doc.select("article.liste")) {
            val a = art.selectFirst("h2 a[href]") ?: continue
            val url = filmUrl(a.attr("href")) ?: continue
            if (url in ergebnis) continue
            val titel = a.attr("title").trim().ifEmpty { a.text().trim() }
            if (titel.isEmpty()) continue
            val cover = absolut(art.selectFirst("img.cover-opacity, img[class*=cover]")?.attr("src"))
            ergebnis[url] = Karte(titel, url, cover)
        }
        return ergebnis.values.toList()
    }

    /** Gibt es eine nächste Seite? Die Seitenlinks heißen …/page/<n>. */
    fun weitereSeite(html: String, seite: Int): Boolean =
        Jsoup.parse(html).select("a[href]").any { it.attr("href").trimEnd('/').endsWith("/page/${seite + 1}") }

    /** Genres aus der Seitenleiste (`section#genre`); der Slug steht in der Adresse /search/genre/<slug>. */
    fun genres(html: String): List<Genre> =
        Jsoup.parse(html, BASIS).select("section#genre a[href*=/search/genre/]").mapNotNull { a: Element ->
            val slug = a.attr("href").substringAfter("/search/genre/").trim('/').substringBefore('?')
            val name = a.text().trim()
            if (slug.isEmpty() || name.isEmpty()) null else Genre(name, slug)
        }.distinctBy { it.slug }

    /** Genres des Films selbst; die Menüleiste verlinkt ebenfalls „Englisch“, die zählt nicht. */
    private fun filmGenres(doc: org.jsoup.nodes.Document): List<String> =
        doc.select("#detail-content-list a[href*=/search/genre/]").map { it.text().trim() }.filter { it.isNotEmpty() }.distinct()

    /** Englische Fassungen führt die Seite als eigenen Film mit Genre „Englisch“. */
    private fun englisch(url: String, genres: List<String>) =
        "english" in url.lowercase() || genres.any { it.equals("Englisch", ignoreCase = true) }

    fun film(html: String, url: String): Serie {
        val doc = Jsoup.parse(html, BASIS)
        val titel = doc.selectFirst("em[itemprop=name]")?.text()?.trim().orEmpty()
            .ifEmpty { doc.selectFirst("h2")?.text()?.trim().orEmpty() }
            .ifEmpty { url.substringAfterLast('/') }
        val text = doc.text()
        val jahr = Regex("""Veröffentlicht:\s*(\d{4})""").find(text)?.groupValues?.get(1)
        val genres = filmGenres(doc).filterNot { it.equals("Englisch", ignoreCase = true) }
        val beschreibung = doc.selectFirst("span[itemprop=description]")?.text()?.trim().orEmpty()
        val cover = absolut(doc.selectFirst("img.cover2")?.attr("src"))
            ?: absolut(doc.selectFirst("[itemprop=image]")?.attr("src"))
        val imdb = Regex("""Imdb:\s*([\d.]+)/10""").find(text)?.groupValues?.get(1)
        return Serie(
            url = url,
            titel = titel,
            beschreibung = beschreibung,
            genres = genres,
            jahre = jahr,
            cover = cover,
            fsk = null,
            imdb = imdb,
            staffeln = listOf(StaffelRef(0, url, istFilme = true)),
        )
    }

    fun folge(html: String, url: String): Folge {
        val s = film(html, url)
        val l = links(html, url)
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

    /**
     * Hosterliste: `<p class="hostName">VOE HD</p>` und daneben der Knopf mit `data-player-url`
     * (ältere Seiten: `href`). „HD“ fällt weg, damit der Name zu den Extraktoren passt.
     */
    fun links(html: String, url: String): FolgenLinks {
        val doc = Jsoup.parse(html, BASIS)
        val sprache = if (englisch(url, filmGenres(doc))) Sprache.EN_DUB else Sprache.DE_DUB
        val hoster = LinkedHashMap<String, String>()
        for (ul in doc.select("ul.currentStreamLinks")) {
            val name = ul.selectFirst("p.hostName")?.text()?.trim()?.replace(Regex("""\s+HD$""", RegexOption.IGNORE_CASE), "")
                ?.takeIf { it.isNotEmpty() } ?: continue
            val knopf = ul.select("li.streamPlayBtn a").firstOrNull { it.hasAttr("data-player-url") || it.attr("href").startsWith("http") }
                ?: continue
            val ziel = absolut(knopf.attr("data-player-url").ifBlank { knopf.attr("href") }) ?: continue
            hoster.putIfAbsent(name, ziel)
        }
        return FolgenLinks(if (hoster.isEmpty()) emptyMap() else mapOf(sprache to hoster))
    }
}
