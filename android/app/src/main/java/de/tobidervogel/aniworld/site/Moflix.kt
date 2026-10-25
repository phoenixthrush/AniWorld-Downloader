package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.net.Check
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.site.MoflixParser.BASIS
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/**
 * Zugriff auf moflix-stream.xyz: Filme und Serien, nur Deutsch. Vor der API sitzt Cloudflare;
 * verlangt es eine Prüfung, öffnet sich wie bei AniWorld das Browserfenster und der Nutzer
 * bestätigt dort selbst. Danach liegen die Cookies auch für die App bereit.
 */
class Moflix(private val netz: Netz) : Anbieter {
    override val name = "Moflix"
    override val hosts = setOf("moflix-stream.xyz")

    @Volatile private var token: String? = null
    private val titel = ConcurrentHashMap<String, JSONObject>()

    override fun serienUrl(url: String) = MoflixParser.serienUrl(url)

    private suspend fun startHtml(): String {
        val html = netz.seite("$BASIS/").text
        MoflixParser.csrf(html)?.let { token = it }
        return html
    }

    /**
     * Ein Aufruf der API, wie get_response() im Original: bei 429 kurz warten, bei einer
     * Cloudflare-Prüfung einmal das Browserfenster. Das Token stammt aus der Startseite.
     */
    private suspend fun api(pfad: String): JSONObject {
        if (token == null) runCatching { startHtml() }
        val url = BASIS + pfad
        fun kopf() = buildMap {
            put("Accept", "application/json")
            put("X-Requested-With", "XMLHttpRequest")
            put("Referer", "$BASIS/")
            token?.let { put("X-XSRF-TOKEN", it) }
        }
        var a = netz.anfrage(url, kopf())
        var versuche = 0
        while (a.code == 429 && versuche++ < 2) {
            delay(1_000L * versuche)
            a = netz.anfrage(url, kopf())
        }
        if (MoflixParser.json(a.text) == null && Check.istCheck(a)) {
            // Die Prüfung auf der Startseite lösen: Direkt aufgerufen leitet die API oft nur zur Anmeldung.
            if (BrowserCheck.loesen("$BASIS/") != null) a = netz.anfrage(url, kopf())
        }
        val json = MoflixParser.json(a.text)
        if (json == null && Check.istCheck(a)) throw NetzFehler(tr(R.string.e_check, "moflix-stream.xyz"))
        if (!a.ok) throw NetzFehler(tr(R.string.e_http, name, a.code))
        return json ?: throw NetzFehler(tr(R.string.e_fehlt, name, "JSON"))
    }

    private suspend fun titelJson(url: String, neu: Boolean = false): JSONObject {
        val id = MoflixParser.titelId(url) ?: throw NetzFehler(tr(R.string.e_fehlt, name, "ID"))
        if (!neu) titel[id]?.let { return it }
        return api("/api/v1/titles/$id").also { titel[id] = it }
    }

    override suspend fun startseite(): Startseite {
        val html = startHtml()
        val reihen = MoflixParser.startReihen(html)
        val genres = runCatching { MoflixParser.genres(api("/api/v1/moflix/recommendations?route=genre&mediaType=all&limit=1")) }
            .getOrNull().orEmpty().ifEmpty { MoflixParser.genresAusStart(html) }
        return Startseite(
            reihen = listOfNotNull(
                reihen["trending-movies"]?.let { R.string.reihe_beliebt to it },
                reihen["top-10-movies-serien"]?.let { R.string.reihe_top10 to it },
                reihen["now-playing"]?.let { R.string.reihe_kinofilme to it },
            ),
            genres = genres,
        )
    }

    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val q = URLEncoder.encode(text.trim(), "UTF-8").replace("+", "%20")
        return MoflixParser.suche(api("/api/v1/search/$q"))
    }

    /** Die Empfehlungen je Genre haben keine Seiten und höchstens 12 Titel (wie im Original). */
    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        if (seite > 1) return emptyList<Karte>() to false
        val g = URLEncoder.encode(slug, "UTF-8").replace("+", "%20")
        val json = api("/api/v1/moflix/recommendations?route=genre&mediaType=all&genres=$g&limit=12")
        return MoflixParser.karten(json.optJSONArray("titles")) to false
    }

    override suspend fun serie(url: String, neu: Boolean): Serie {
        val su = serienUrl(url) ?: url
        return MoflixParser.serie(titelJson(su, neu), su)
    }

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> {
        val su = serienUrl(ref.url) ?: ref.url
        if (ref.istFilme) return listOf(MoflixParser.film(titelJson(su, neu), su))
        val id = MoflixParser.titelId(su) ?: throw NetzFehler(tr(R.string.e_fehlt, name, "ID"))
        val alle = LinkedHashMap<Int, Folge>()
        // Seitenweise wie das Original, aber nie einer Adresse aus der Antwort folgen.
        for (seite in 1..20) {
            val (folgen, weiter) = MoflixParser.folgen(
                api("/api/v1/titles/$id/seasons/${ref.nummer}?perPage=500" + if (seite > 1) "&page=$seite" else ""), id, ref.nummer,
            )
            val vorher = alle.size
            folgen.forEach { alle.putIfAbsent(it.nummer, it) }
            if (!weiter || alle.size == vorher) break
        }
        return alle.values.sortedBy { it.nummer }
    }

    override suspend fun links(folgenUrl: String): FolgenLinks {
        val id = MoflixParser.titelId(folgenUrl) ?: throw NetzFehler(tr(R.string.e_fehlt, name, "ID"))
        val se = MoflixParser.staffelUndFolge(folgenUrl)
            ?: return MoflixParser.links(titelJson(folgenUrl, neu = true))
        return MoflixParser.links(api("/api/v1/titles/$id/seasons/${se.first}/episodes/${se.second}"))
    }

    /** Die Videos zeigen schon auf den Hoster. */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String = redirect
}
