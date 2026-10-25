package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.site.FilmoParser.BASIS
import de.tobidervogel.aniworld.tr
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/** Zugriff auf filmo.to. Nur Filme; jeder Film ist eine „Serie“ mit einer Folge. */
class Filmo(private val netz: Netz) : Anbieter {
    override val name = "Filmo"
    override val hosts = setOf("filmo.to")

    private val filme = ConcurrentHashMap<String, Serie>()

    override fun serienUrl(url: String) = FilmoParser.filmUrl(url)

    override suspend fun startseite(): Startseite {
        // Die Startseite von Filmo zeigt Breitbilder; die Filmliste hat Poster wie die anderen Seiten.
        val neu = netz.seite("$BASIS/movies?sort=release_desc").text
        val gut = runCatching { netz.seite("$BASIS/movies?sort=rating_desc").text }.getOrNull()
        return Startseite(
            reihen = listOfNotNull(
                R.string.reihe_neu_erschienen to FilmoParser.karten(neu),
                gut?.let { R.string.reihe_bestbewertet to FilmoParser.karten(it) },
            ),
            genres = FilmoParser.genres(neu),
        )
    }

    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val html = netz.seite("$BASIS/search?q=${URLEncoder.encode(text.trim(), "UTF-8")}").text
        return FilmoParser.karten(html).map { Treffer(it.titel, it.url, "Film", it.cover) }
    }

    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        val html = netz.seite("$BASIS/movies?genre_id=$slug" + if (seite > 1) "&page=$seite" else "").text
        return FilmoParser.karten(html) to FilmoParser.weitereSeite(html)
    }

    override suspend fun serie(url: String, neu: Boolean): Serie {
        if (!neu) filme[url]?.let { return it }
        return FilmoParser.film(netz.seite(url).text, url).also { filme[url] = it }
    }

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> =
        listOf(FilmoParser.folge(netz.seite(ref.url).text, ref.url))

    override suspend fun links(folgenUrl: String): FolgenLinks = FilmoParser.links(netz.seite(folgenUrl).text)

    /**
     * Quell-Token gegen eine Wiedergabe-Adresse tauschen, wie redirect_url im Original:
     * POST /n mit dem CSRF-Token der Filmseite, dann /n/<x>, das zum Hoster weiterleitet.
     */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String {
        val token = redirect.substringAfter(FilmoParser.TOKEN_PRAEFIX, "")
        if (token.isEmpty()) throw NetzFehler(tr(R.string.e_filmo_token))
        // Frisch laden: Das CSRF-Token gehört zur Sitzung, deren Cookie die Seite gerade setzt.
        val seite = netz.seite(folgenUrl)
        val csrf = FilmoParser.csrf(seite.text) ?: throw NetzFehler(tr(R.string.e_fehlt, name, "CSRF"))
        val antwort = netz.anfrage(
            "$BASIS/n",
            mapOf(
                "X-CSRF-TOKEN" to csrf,
                "X-Requested-With" to "XMLHttpRequest",
                "Referer" to folgenUrl,
                "Accept" to "application/json",
            ),
            json = JSONObject().put("p", token).toString(),
        )
        if (!antwort.ok) throw NetzFehler(tr(R.string.e_http, "Filmo /n", antwort.code))
        val x = runCatching { JSONObject(antwort.text).optString("x") }.getOrNull().orEmpty()
        if (x.isEmpty()) throw NetzFehler(tr(R.string.e_filmo_x))
        val ziel = "$BASIS/n/${URLEncoder.encode(x, "UTF-8").replace("+", "%20")}"
        val a = netz.anfrage(ziel, mapOf("Referer" to folgenUrl))
        if (Netz.host(a.url).removePrefix("www.") !in hosts) return a.url
        // Manche Hoster (Byse) leitet Filmo nicht weiter, sondern zeigt eine Seite „Video öffnen“ mit dem Link.
        FilmoParser.externerLink(a.text)?.let { return it }
        return weiterleiten(netz, ziel, folgenUrl, hosts)
    }
}
