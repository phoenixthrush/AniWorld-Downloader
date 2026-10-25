package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.site.BurningSeriesParser.BASIS
import de.tobidervogel.aniworld.site.BurningSeriesParser.HOSTS
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import java.util.concurrent.ConcurrentHashMap

/**
 * Zugriff auf Burning Series. Suche und Genres laufen über den Index `/andere-serien`, den die
 * App einmal pro Sitzung lädt. Der Weg zum Hoster führt über die Playerseite auf
 * burning-series.io/.net; deren Weiterleitung braucht oft einen echten Browser (Turnstile),
 * dafür öffnet sich wie bei AniWorld das Browserfenster.
 */
class BurningSeries(private val netz: Netz) : Anbieter {
    override val name = "BurningSeries"
    override val hosts = HOSTS

    private val indexSperre = Mutex()
    @Volatile private var indexCache: Map<String, List<Karte>>? = null
    private val serien = ConcurrentHashMap<String, Serie>()
    private val tabellen = ConcurrentHashMap<String, Map<Sprache, List<BurningSeriesParser.Zeile>>>()
    private val cover = ConcurrentHashMap<String, String>()

    // Burning Series drosselt viele Weiterleitungen kurz hintereinander, darum eine nach der anderen.
    private val weiterleitungSperre = Mutex()

    override fun serienUrl(url: String) = BurningSeriesParser.serienUrl(url)

    private suspend fun html(url: String) = netz.seite(url, header = mapOf("Referer" to "$BASIS/")).text

    private suspend fun index(): Map<String, List<Karte>> {
        indexCache?.let { return it }
        return indexSperre.withLock {
            indexCache ?: BurningSeriesParser.index(html("$BASIS/andere-serien")).also { indexCache = it }
        }
    }

    /** Cover stehen nur auf der Serienseite; für die Startseite höchstens acht gleichzeitig nachladen. */
    private suspend fun mitCover(karten: List<Karte>): List<Karte> = coroutineScope {
        val sperre = Semaphore(8)
        karten.map { k ->
            async {
                val c = cover[k.url] ?: sperre.withPermit {
                    try {
                        BurningSeriesParser.cover(html(k.url))?.also { cover[k.url] = it }
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        null
                    }
                }
                k.copy(cover = c)
            }
        }.awaitAll()
    }

    override suspend fun startseite(): Startseite {
        val start = html("$BASIS/")
        val neu = mitCover(BurningSeriesParser.neueSerien(start).take(12))
        val genres = runCatching { index().keys.map { Genre(it, it) } }.getOrDefault(emptyList())
        return Startseite(listOf(R.string.reihe_neue_serien to neu), genres)
    }

    override suspend fun neueFolgen(): List<NeueFolge> = BurningSeriesParser.neueFolgen(html("$BASIS/"))

    override suspend fun suche(text: String): List<Treffer> =
        BurningSeriesParser.suche(index(), text).map { Treffer(it.titel, it.url, it.genre, null) }

    /** Der Index enthält ganze Genres; die App blättert darin in Seiten zu 60. */
    override suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean> {
        val alle = index().entries.firstOrNull { it.key.equals(slug, ignoreCase = true) }?.value.orEmpty()
        val von = (seite - 1) * SEITE
        val teil = alle.drop(von).take(SEITE)
        return mitCover(teil) to (von + SEITE < alle.size)
    }

    override suspend fun serie(url: String, neu: Boolean): Serie {
        if (!neu) serien[url]?.let { return it }
        return BurningSeriesParser.serie(html(url), url).also { s ->
            serien[url] = s
            s.cover?.let { cover[url] = it }
        }
    }

    /** Beide Sprachtabellen einer Staffel, gleichzeitig geladen und für die Sitzung gemerkt. */
    private suspend fun tabellen(ref: StaffelRef, neu: Boolean = false): Map<Sprache, List<BurningSeriesParser.Zeile>> {
        if (!neu) tabellen[ref.url]?.let { return it }
        val t = coroutineScope {
            BurningSeriesParser.SPRACHEN.map { (kurz, sprache) ->
                async {
                    sprache to try {
                        BurningSeriesParser.staffel(html("${ref.url}/$kurz"), kurz)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        // Eine fehlende Sprache ist kein Fehler; die andere kann trotzdem da sein.
                        Protokoll.info("BurningSeries: ${ref.url}/$kurz nicht lesbar: ${e.message}")
                        emptyList()
                    }
                }
            }.awaitAll().filter { it.second.isNotEmpty() }.toMap()
        }
        tabellen[ref.url] = t
        return t
    }

    override suspend fun staffel(ref: StaffelRef, neu: Boolean): List<Folge> = BurningSeriesParser.folgen(ref, tabellen(ref, neu))

    override suspend fun links(folgenUrl: String): FolgenLinks {
        val m = Regex("""/serie/([^/]+)/(\d+)/""").find(folgenUrl) ?: throw NetzFehler(tr(R.string.e_bs_folge))
        val ref = StaffelRef(m.groupValues[2].toInt(), "$BASIS/serie/${m.groupValues[1]}/${m.groupValues[2]}", istFilme = false)
        return BurningSeriesParser.links(folgenUrl, tabellen(ref))
    }

    /**
     * Wie _resolve_hoster_link() im Original: Playerseite auf einer Stream-Domain laden,
     * `window.open(…)` lesen und der Weiterleitung folgen. Bleibt sie auf Burning Series
     * (Turnstile, Skript), übernimmt das Browserfenster.
     */
    override suspend fun hosterAdresse(redirect: String, folgenUrl: String): String = weiterleitungSperre.withLock {
        delay(1_500)
        val pfad = redirect.replace(Regex("""^https?://[^/]+/"""), "").trimStart('/')
        var vpn = false
        var letzter: Exception? = null
        for (basis in BurningSeriesParser.STREAM_DOMAINS) {
            val player = "$basis/$pfad"
            try {
                val p = netz.anfrage(player, mapOf("Referer" to folgenUrl))
                val ziel = BurningSeriesParser.streamZiel(p.text, basis)
                if (ziel == null) {
                    if (BurningSeriesParser.vpnHinweis(p.text)) vpn = true
                    continue
                }
                val a = netz.anfrage(ziel, mapOf("Referer" to player))
                if (!daheim(a.url)) return@withLock a.url
                if (BurningSeriesParser.vpnHinweis(a.text)) vpn = true
                // Die Weiterleitung läuft per Skript: sichtbar im Browser öffnen, der zeigt auch ein Rätsel.
                val ende = BrowserCheck.loesen(ziel, verlassen = true, heim = hosts + "burningseries.to")
                if (ende != null && !daheim(ende)) return@withLock ende
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                letzter = e
            }
        }
        throw NetzFehler(if (vpn) tr(R.string.e_bs_vpn) else letzter?.message ?: tr(R.string.e_weiterleitung, 0))
    }

    private fun daheim(url: String) = Netz.host(url).removePrefix("www.").let { it in hosts || it == "burningseries.to" }

    companion object {
        private const val SEITE = 60
    }
}
