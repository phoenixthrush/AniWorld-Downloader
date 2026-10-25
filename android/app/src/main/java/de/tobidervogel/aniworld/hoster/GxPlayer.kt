package de.tobidervogel.aniworld.hoster

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr

/**
 * Der eigene Player von MegaKino (gxplayer), übertragen aus extractors/provider/megakino.py:
 * Die Seite nennt uid, md5 und id, daraus ergibt sich die HLS-Playlist.
 */
object GxPlayer : Hoster {
    override val name = "GXPlayer"

    private fun feld(html: String, schluessel: String) =
        Regex(""""$schluessel"\s*:\s*"([^"]+)"""").find(html)?.groupValues?.get(1)

    fun ausHtml(html: String): String? {
        val uid = feld(html, "uid") ?: return null
        val md5 = feld(html, "md5") ?: return null
        val id = feld(html, "id") ?: return null
        return "https://watch.gxplayer.xyz/m3u8/$uid/$md5/master.txt?s=1&id=$id&cache=1"
    }

    override suspend fun aufloesen(netz: Netz, embed: String): Stream {
        val kopf = mapOf("User-Agent" to netz.userAgent)
        val seite = netz.anfrage(embed, kopf)
        if (!seite.ok) throw NetzFehler(tr(R.string.e_http, name, seite.code))
        val url = ausHtml(seite.text) ?: throw NetzFehler(tr(R.string.e_keine_quelle, name))
        return Stream(url, kopf + ("Referer" to Js.ursprung(seite.url) + "/"), name, hls = true)
    }
}
