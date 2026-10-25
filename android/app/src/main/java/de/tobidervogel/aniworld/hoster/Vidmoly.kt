package de.tobidervogel.aniworld.hoster

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr

/** Vidmoly, übertragen aus extractors/provider/vidmoly.py. */
object Vidmoly : Hoster {
    override val name = "Vidmoly"

    private val SKRIPT = Regex("<script[^>]*>(.*?)</script>", setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE))
    private val DATEI = Regex("""file\s*:\s*['"]([^'"]+?\.m3u8[^'"]*)['"]""")

    fun ausHtml(html: String): String? {
        val skripte = SKRIPT.findAll(html).joinToString("\n") { it.groupValues[1] }
        return DATEI.find(skripte)?.groupValues?.get(1)
            ?: Js.alleEntpackt(html).firstNotNullOfOrNull { DATEI.find(it)?.groupValues?.get(1) }
    }

    override suspend fun aufloesen(netz: Netz, embed: String): Stream {
        val kopf = mapOf("Referer" to "https://vidmoly.biz", "User-Agent" to netz.userAgent)
        val seite = netz.anfrage(embed, kopf)
        if (!seite.ok) throw NetzFehler(tr(R.string.e_http, "Vidmoly", seite.code))
        val url = ausHtml(seite.text) ?: throw NetzFehler(tr(R.string.e_keine_quelle, "Vidmoly"))
        return Stream(url, kopf, name)
    }
}
