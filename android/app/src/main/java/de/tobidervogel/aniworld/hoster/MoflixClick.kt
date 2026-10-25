package de.tobidervogel.aniworld.hoster

import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

/**
 * Der Player von moflix-stream.click (XFileSharing), übertragen aus
 * extractors/provider/moflixclick.py: Im gepackten Skript steht `var links = {hls4, hls3, hls2}`.
 * Wie der Player selbst probiert die App hls4, dann hls3, dann hls2 und nimmt die erste Adresse,
 * die wirklich eine Playlist liefert (hls3 endet manchmal auf .txt).
 */
object MoflixClick : Hoster {
    override val name = "MoflixClick"
    private const val HOST = "moflix-stream.click"
    private val LINKS = Regex("""var\s+links\s*=\s*(\{[^}]+\})""")

    fun kandidaten(html: String): List<String> {
        for (js in Js.alleEntpackt(html) + html) {
            val roh = LINKS.find(js)?.groupValues?.get(1) ?: continue
            val links = runCatching { JSONObject(roh) }.getOrNull() ?: continue
            return listOf("hls4", "hls3", "hls2").mapNotNull { k -> links.optString(k).takeIf { it.startsWith("https://") } }
        }
        return emptyList()
    }

    override suspend fun aufloesen(netz: Netz, embed: String): Stream {
        if (Netz.host(embed) != HOST || !embed.startsWith("https://")) throw NetzFehler(tr(R.string.e_fehlt, name, "Embed"))
        val kopf = mapOf("User-Agent" to netz.userAgent)
        val seite = netz.anfrage(embed, kopf)
        if (!seite.ok) throw NetzFehler(tr(R.string.e_http, name, seite.code))
        val laden = kopf + ("Referer" to "https://$HOST/")
        for (url in kandidaten(seite.text)) {
            try {
                val p = netz.anfrage(url, laden)
                if (p.ok && p.text.trimStart().startsWith("#EXTM3U")) return Stream(url, laden, name, hls = true)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Protokoll.fehler("$name: Playlist", e)
            }
        }
        throw NetzFehler(tr(R.string.e_keine_quelle, name))
    }
}
