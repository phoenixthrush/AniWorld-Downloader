package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Antwort
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.site.SerienStreamParser.BASIS
import de.tobidervogel.aniworld.tr
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/**
 * Zugriff auf serienstream.to. Fällt die Domain aus, geht es wie in models/s_to/http.py auf
 * serienstream.cx weiter; der Host, der zuletzt geantwortet hat, bleibt der erste Versuch.
 * (Den Notweg über die nackte IP lässt die App weg: der bräuchte abgeschaltete Zertifikatsprüfung.)
 */
class SerienStream(private val netz: Netz) : Anbieter {
    override val name = "SerienStream"
    override val hosts = SerienStreamParser.HOSTS

    private val spiegel = listOf("serienstream.to", "serienstream.cx")
    @Volatile private var aktiv = 0

    private val serien = ConcurrentHashMap<String, Serie>()
    private val staffeln = ConcurrentHashMap<String, List<Folge>>()

    override fun serienUrl(url: String) = SerienStreamParser.serienUrl(url)

    /** Adresse auf einen Spiegel umschreiben (alles in der App ist auf serienstream.to normiert). */
    private fun auf(url: String, host: String) =
        url.replace(Regex("""^https?://(?:www\.)?(?:serienstream\.(?:to|cx)|s\.to)"""), "https://$host")

    private suspend fun seite(url: String): Antwort {
        var letzter: Exception? = null
        for (i in spiegel.indices) {
            val idx = (aktiv + i) % spiegel.size
            try {
                val a = netz.seite(auf(url, spiegel[idx]))
                if (idx != aktiv) Protokoll.info("SerienStream: weiter über ${spiegel[idx]}")
                aktiv = idx
                return a
            } catch (e: NetzFehler) {
                letzter = e
            }
        }
        throw letzter ?: NetzFehler(tr(R.string.e_nicht_erreichbar, name))
    }

    override suspend fun startseite(): Startseite {
        val beliebt = seite("$BASIS/beliebte-serien").text
        val start = runCatching { seite("$BASIS/").text }.getOrNull()
        return Startseite(
            reihen = listOf(
                R.string.reihe_neue_staffeln to SerienStreamParser.abschnitt(beliebt, "Neue Staffeln"),
                R.string.reihe_meistgesehen to SerienStreamParser.abschnitt(beliebt, "Meistgesehen"),
            ),
            genres = SerienStreamParser.genres(start ?: beliebt),
        )
    }

    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val (treffer, _) = SerienStreamParser.suche(seite("$BASIS/suche?term=${URLEncoder.encode(text.trim(), "UTF-8")}").text)
        return treffer
    }

    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        val url = if (seite > 1) "$BASIS/genre/$slug?page=$seite" else "$BASIS/genre/$slug"
        return SerienStreamParser.genreSeite(seite(url).text)
    }

    override suspend fun serie(url: String, neu: Boolean): Serie {
        if (!neu) serien[url]?.let { return it }
        return SerienStreamParser.serie(seite(url).text, url).also { serien[url] = it }
    }

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> {
        if (!neu) staffeln[ref.url]?.let { return it }
        return SerienStreamParser.staffel(seite(ref.url).text, ref).also { staffeln[ref.url] = it }
    }

    override suspend fun links(folgenUrl: String): FolgenLinks =
        SerienStreamParser.folgenLinks(seite(folgenUrl).text)

    /** `/r?t=…` leitet zum Hoster; aus Rechenzentren steht davor DDoS-Guard, vom Handy aus meist nicht. */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String {
        val host = spiegel[aktiv]
        return weiterleiten(netz, auf(redirect, host), auf(folgenUrl, host), hosts)
    }
}
