package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

/**
 * Zugriff auf MegaKino: Filme und Serienstaffeln, nur Deutsch. Die Domain holt die App einmal
 * pro Start vom Tracker wie get_megakino_domain(); gespeicherte Adressen mit einer alten
 * Domain laufen deshalb weiter. Vor dem ersten Abruf will die Seite ein Token-Cookie.
 */
class MegaKino(private val netz: Netz) : Anbieter {
    override val name = "MegaKino"
    override val hosts = setOf(MegaKinoParser.STANDARD)

    @Volatile private var aktuell: String? = null
    private val domainSperre = Mutex()
    private val seiten = ConcurrentHashMap<String, String>()

    /** Jede Domain mit „megakino“ gehört dazu, auch frühere. */
    override fun passt(url: String) = MegaKinoParser.istHost(Netz.host(url))

    override fun serienUrl(url: String) = MegaKinoParser.serienUrl(url, "https://${aktuell ?: MegaKinoParser.STANDARD}")

    /** Dieselbe Adresse auf der aktuellen Domain; nur so wird abgerufen. */
    private suspend fun live(url: String) = basis() + url.substringBefore('#').replace(Regex("""^https?://[^/?#]+"""), "")

    private suspend fun basis(): String {
        aktuell?.let { return "https://$it" }
        return domainSperre.withLock {
            aktuell ?: run {
                val d = runCatching {
                    val a = netz.anfrage(MegaKinoParser.TRACKER)
                    if (a.ok) MegaKinoParser.domain(a.text) else null
                }.getOrNull()
                if (d == null) Protokoll.info("MegaKino: Domain-Tracker nicht lesbar, nehme ${MegaKinoParser.STANDARD}")
                (d ?: MegaKinoParser.STANDARD).also { aktuell = it }
            }.let { "https://$it" }
        }
    }

    private suspend fun html(url: String): String {
        val b = basis()
        val kopf = mapOf("Referer" to "$b/")
        var text = netz.seite(url, header = kopf).text
        if (MegaKinoParser.brauchtToken(text)) {
            // Wie im Original: Token abholen (antwortet mit 204 und setzt das Cookie), dann noch einmal.
            netz.anfrage("$b/index.php?yg=token", kopf)
            text = netz.seite(url, header = kopf).text
            if (MegaKinoParser.brauchtToken(text)) throw NetzFehler(tr(R.string.e_check, Netz.host(url)))
        }
        return text
    }

    private suspend fun eintragHtml(url: String, neu: Boolean = false): String {
        val u = live(url)
        if (!neu) seiten[u]?.let { return it }
        return html(u).also { seiten[u] = it }
    }

    override suspend fun startseite(): Startseite {
        val b = basis()
        val start = html("$b/")
        val kino = runCatching { html("$b/kinofilme/") }.getOrNull()
        val serien = runCatching { html("$b/serials/") }.getOrNull()
        return Startseite(
            reihen = listOfNotNull(
                R.string.reihe_neu_erschienen to MegaKinoParser.karten(start, b, abListe = true),
                kino?.let { R.string.reihe_kinofilme to MegaKinoParser.karten(it, b, abListe = true) },
                serien?.let { R.string.reihe_neue_serien to MegaKinoParser.karten(it, b, abListe = true) },
            ).filter { it.second.isNotEmpty() },
            genres = MegaKinoParser.genres(start),
        )
    }

    /** Die Suche blättert in Schritten zu 20 Treffern wie query_megakino(); hier höchstens drei Seiten. */
    override suspend fun suche(text: String): List<Treffer> {
        if (text.isBlank()) return emptyList()
        val b = basis()
        val q = URLEncoder.encode(text.trim(), "UTF-8")
        val treffer = LinkedHashMap<String, Treffer>()
        for (p in 0 until 3) {
            val url = "$b/index.php?do=search&subaction=search&search_start=${p * 2}&full_search=0&result_from=${p * 20 + 1}&story=$q"
            val karten = (if (p == 0) html(url) else runCatching { html(url) }.getOrNull())
                ?.let { MegaKinoParser.karten(it, b, abListe = true) }.orEmpty()
            val neu = karten.filter { it.url !in treffer }
            if (neu.isEmpty()) break
            neu.forEach { treffer[it.url] = Treffer(it.titel, it.url, it.genre, it.cover) }
            if (karten.size < 20) break
        }
        return treffer.values.toList()
    }

    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        val b = basis()
        val s = URLEncoder.encode(slug, "UTF-8")
        val html = html(if (seite <= 1) "$b/$s/" else "$b/$s/page/$seite/")
        return MegaKinoParser.karten(html, b, abListe = true) to MegaKinoParser.weitereSeite(html, seite)
    }

    override suspend fun serie(url: String, neu: Boolean): Serie {
        val su = serienUrl(url) ?: url
        return MegaKinoParser.eintrag(eintragHtml(su, neu), su, basis())
    }

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> {
        val su = serienUrl(ref.url) ?: ref.url
        return MegaKinoParser.folgen(eintragHtml(su, neu), su, basis(), ref)
    }

    override suspend fun links(folgenUrl: String): FolgenLinks {
        val su = serienUrl(folgenUrl) ?: throw NetzFehler(tr(R.string.e_fehlt, name, "URL"))
        val folge = MegaKinoParser.folge(folgenUrl)
        return MegaKinoParser.links(eintragHtml(su, neu = true), if (folge != null) MegaKinoParser.folgenUrl(su, folge) else su)
    }

    /** Die Links zeigen schon auf den Hoster. */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String = redirect
}
