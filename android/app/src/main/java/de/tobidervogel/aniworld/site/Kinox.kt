package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.site.KinoxParser.BASIS
import de.tobidervogel.aniworld.tr
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/**
 * Zugriff auf kinox.to: Filme und Serien. Die Hoster einer Serienfolge liefert
 * /aGET/MirrorByEpisode, die Weiterleitung zum Hoster /aGET/Mirror. Davor steht oft eine
 * Seite „Verifizierung“, die nur ein echter Browser besteht; dafür öffnet sich das Browserfenster.
 */
class Kinox(private val netz: Netz) : Anbieter {
    override val name = "Kinox"
    override val hosts = KinoxParser.HOSTS

    private val seiten = ConcurrentHashMap<String, String>()

    override fun serienUrl(url: String) = KinoxParser.serienUrl(url)

    private suspend fun html(url: String) = netz.seite(url, header = mapOf("Referer" to "$BASIS/")).text

    private suspend fun eintragHtml(url: String, neu: Boolean = false): String {
        val u = KinoxParser.serienUrl(url) ?: url
        if (!neu) seiten[u]?.let { return it }
        return html(u).also { seiten[u] = it }
    }

    override suspend fun startseite(): Startseite {
        val kino = html("$BASIS/Kino-Filme.html")
        val genres = runCatching { KinoxParser.genres(html("$BASIS/")) }.getOrDefault(emptyList())
        return Startseite(listOf(R.string.reihe_kinofilme to KinoxParser.karten(kino)), genres)
    }

    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val html = html("$BASIS/Search.html?q=${URLEncoder.encode(text.trim(), "UTF-8")}")
        return KinoxParser.karten(html).map { Treffer(it.titel, it.url, it.genre, it.cover) }
    }

    /** Genre-Seiten laden ihre Karten per POST nach (Top 100 eines Genres), wie query_kinox(). */
    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        if (seite > 1) return emptyList<Karte>() to false
        val url = "$BASIS/Genre/${URLEncoder.encode(slug, "UTF-8")}/Popular"
        val seiteHtml = html(url)
        val parameter = KinoxParser.listenParameter(seiteHtml) ?: return KinoxParser.karten(seiteHtml) to false
        parameter.put("Length", 100)
        val a = netz.anfrage(
            "$BASIS/aGET/List/",
            mapOf("Referer" to url, "X-Requested-With" to "XMLHttpRequest"),
            formular = mapOf(
                "Page" to "1",
                "Per_Page" to "100",
                "ListMode" to "cover",
                "additional" to parameter.toString(),
                "iDisplayStart" to "0",
                "iDisplayLength" to "100",
            ),
        )
        if (!a.ok) throw NetzFehler(tr(R.string.e_http, "Kinox", a.code))
        return KinoxParser.karten(KinoxParser.listenInhalt(a.text)) to false
    }

    override suspend fun serie(url: String, neu: Boolean): Serie = KinoxParser.eintrag(eintragHtml(url, neu), KinoxParser.serienUrl(url) ?: url)

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> {
        val serie = KinoxParser.serienUrl(ref.url) ?: ref.url
        return KinoxParser.folgen(eintragHtml(serie, neu), serie, ref)
    }

    override suspend fun links(folgenUrl: String): FolgenLinks {
        val serie = KinoxParser.serienUrl(folgenUrl) ?: throw NetzFehler(tr(R.string.e_fehlt, "Kinox", "Stream"))
        val html = eintragHtml(serie, neu = true)
        val sprache = KinoxParser.sprache(html)
        val se = KinoxParser.staffelUndFolge(folgenUrl) ?: return KinoxParser.spiegel(html, sprache)
        val id = KinoxParser.serieId(html) ?: throw NetzFehler(tr(R.string.e_fehlt, "Kinox", "SeriesID"))
        val slug = KinoxParser.slug(serie).orEmpty()
        val liste = netz.anfrage(
            "$BASIS/aGET/MirrorByEpisode/?Addr=$slug&SeriesID=$id&Season=${se.first}&Episode=${se.second}",
            mapOf("Referer" to serie, "X-Requested-With" to "XMLHttpRequest"),
        )
        if (!liste.ok) throw NetzFehler(tr(R.string.e_http, "Kinox", liste.code))
        return KinoxParser.spiegel(liste.text, sprache)
    }

    /**
     * Spiegel → Weiterleitung → Hoster, wie _resolve_embed() im Original. Bleibt die
     * Weiterleitung auf Kinox („Verifizierung“), holt die App eine frische Adresse und öffnet
     * sie im Browserfenster; die alte gilt meist nur einmal.
     */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String {
        val referer = KinoxParser.serienUrl(folgenUrl) ?: "$BASIS/"
        suspend fun ziel(): String {
            val a = netz.anfrage("$BASIS/aGET/Mirror/$redirect", mapOf("Referer" to referer, "X-Requested-With" to "XMLHttpRequest"))
            if (!a.ok) throw NetzFehler(tr(R.string.e_http, "Kinox", a.code))
            return KinoxParser.weiterleitung(a.text) ?: throw NetzFehler(tr(R.string.e_keine_quelle, "Kinox"))
        }
        val erst = ziel()
        if (!daheim(erst)) return erst
        val a = netz.anfrage(erst, mapOf("Referer" to referer))
        if (a.ok && !daheim(a.url)) return a.url
        val ende = BrowserCheck.loesen(ziel(), verlassen = true, heim = hosts)
        if (ende != null && !daheim(ende)) return ende
        throw NetzFehler(tr(R.string.e_kinox_check))
    }

    private fun daheim(url: String) = Netz.host(url).removePrefix("www.") in hosts
}
