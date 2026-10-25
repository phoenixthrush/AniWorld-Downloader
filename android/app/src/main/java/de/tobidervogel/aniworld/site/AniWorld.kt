package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.site.AniWorldParser.BASIS
import java.util.concurrent.ConcurrentHashMap

/** Zugriff auf aniworld.to: holt Seiten über [Netz] und lässt sie vom [AniWorldParser] lesen. */
class AniWorld(private val netz: Netz) : Anbieter {
    override val name = "AniWorld"
    override val hosts = setOf("aniworld.to")

    override fun serienUrl(url: String) = AniWorldParser.serienUrl(url)

    // Einfache Zwischenspeicher für die Sitzung: Zurück-Navigation soll nicht neu laden.
    private val serien = ConcurrentHashMap<String, Serie>()
    private val staffeln = ConcurrentHashMap<String, List<Folge>>()

    override suspend fun startseite(): Startseite {
        val html = netz.seite("$BASIS/").text
        return Startseite(
            reihen = listOf(
                R.string.reihe_beliebt to AniWorldParser.abschnitt(html, "Derzeit beliebt"),
                R.string.reihe_neue_animes to AniWorldParser.abschnitt(html, "Neue Animes"),
            ),
            genres = AniWorldParser.genres(html),
        )
    }

    override suspend fun neueFolgen(): List<NeueFolge> =
        AniWorldParser.neueFolgen(netz.seite("$BASIS/neue-episoden").text)

    override val hatZufall get() = true

    /** Wie random_anime() im Original: alle Serien über den Zufallsgenerator, eine davon zufällig. */
    override suspend fun zufall(): String? {
        val a = netz.seite(
            "$BASIS/ajax/randomGeneratorSeries",
            formular = mapOf("productionStart" to "all", "productionEnd" to "all", "genres[]" to "all"),
            header = mapOf("X-Requested-With" to "XMLHttpRequest", "Referer" to "$BASIS/"),
        )
        return AniWorldParser.zufall(a.text).randomOrNull()
    }

    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val a = netz.seite(
            "$BASIS/ajax/search",
            formular = mapOf("keyword" to text.trim()),
            header = mapOf(
                "X-Requested-With" to "XMLHttpRequest",
                "Accept" to "application/json, text/javascript, */*; q=0.01",
                "Referer" to "$BASIS/search",
            ),
        )
        return AniWorldParser.suche(a.text)
    }

    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        val url = if (seite > 1) "$BASIS/genre/$slug/$seite" else "$BASIS/genre/$slug"
        return AniWorldParser.genreSeite(netz.seite(url).text, slug, seite)
    }

    override suspend fun serie(url: String, neu: Boolean): Serie {
        if (!neu) serien[url]?.let { return it }
        return AniWorldParser.serie(netz.seite(url).text, url).also { serien[url] = it }
    }

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> {
        if (!neu) staffeln[ref.url]?.let { return it }
        return AniWorldParser.staffel(netz.seite(ref.url).text, ref).also { staffeln[ref.url] = it }
    }

    override suspend fun links(folgenUrl: String): FolgenLinks =
        AniWorldParser.folgenLinks(netz.seite(folgenUrl).text)

    /** `/redirect/<id>` führt per HTTP-Weiterleitung zum Hoster. */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String) = weiterleiten(netz, redirect, folgenUrl, hosts)
}
