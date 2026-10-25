package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.site.FilmPalastParser.BASIS
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/** Zugriff auf filmpalast.to. Nur Filme; jeder Film ist eine „Serie“ mit einer Folge. */
class FilmPalast(private val netz: Netz) : Anbieter {
    override val name = "FilmPalast"
    override val hosts = setOf("filmpalast.to", "filmpalast.la")

    private val filme = ConcurrentHashMap<String, String>()

    override fun serienUrl(url: String) = FilmPalastParser.filmUrl(url)

    // Kein eigenes Accept-Encoding setzen: Dann fragt OkHttp selbst nach gzip und entpackt auch.
    // (Das Original muss Brotli abwählen; OkHttp bietet es gar nicht erst an.)
    private suspend fun html(url: String) = netz.seite(url, header = mapOf("Referer" to "$BASIS/")).text

    private suspend fun filmHtml(url: String, neu: Boolean = false): String {
        if (!neu) filme[url]?.let { return it }
        return html(url).also { filme[url] = it }
    }

    override suspend fun startseite(): Startseite {
        val neu = html("$BASIS/movies/new")
        val top = runCatching { html("$BASIS/movies/top") }.getOrNull()
        return Startseite(
            reihen = listOfNotNull(
                R.string.reihe_neue_filme to FilmPalastParser.karten(neu),
                top?.let { R.string.reihe_top to FilmPalastParser.karten(it) },
            ),
            // Die Genre-Leiste steht auf jeder Seite, also auch auf der Filmliste.
            genres = FilmPalastParser.genres(neu),
        )
    }

    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val html = html("$BASIS/search/title/${URLEncoder.encode(text.trim(), "UTF-8").replace("+", "%20")}")
        return FilmPalastParser.karten(html).map { Treffer(it.titel, it.url, "Film", it.cover) }
    }

    /** Genre-Seiten haben keine weiteren Seiten (/page/2 antwortet mit 404). */
    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        if (seite > 1) return emptyList<Karte>() to false
        val html = html("$BASIS/search/genre/${URLEncoder.encode(slug, "UTF-8").replace("+", "%20")}")
        return FilmPalastParser.karten(html) to false
    }

    override suspend fun serie(url: String, neu: Boolean): Serie = FilmPalastParser.film(filmHtml(url, neu), url)

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> =
        listOf(FilmPalastParser.folge(filmHtml(ref.url, neu), ref.url))

    override suspend fun links(folgenUrl: String): FolgenLinks = FilmPalastParser.links(filmHtml(folgenUrl, neu = true), folgenUrl)

    /** Die Links zeigen schon auf den Hoster. */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String = redirect
}
