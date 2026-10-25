package de.tobidervogel.aniworld.hoster

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Check
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr
import org.json.JSONArray
import org.json.JSONObject
import java.util.Base64

/** VOE, übertragen aus extractors/provider/voe.py. */
object Voe : Hoster {
    override val name = "VOE"

    private val JSON_SKRIPT = Regex("""<script\s+type=["']application/json["']>(.*?)</script>""", RegexOption.DOT_MATCHES_ALL)
    private val A168C = Regex("""var a168c='([^']+)'""")
    private val HLS = Regex("""'hls'\s*:\s*'([^']+)'""")
    private val WEITERLEITUNG = Regex("""['"](\s*https?://[^'"<>\s]+/e/[^'"<>\s]+)['"]""")
    private val LOCATION = Regex("""(?:location\.href|window\.location(?:\.href)?)\s*=\s*['"](https?://[^'"<>\s]+)['"]""")
    private val MUELL = listOf("@$", "^^", "~@", "%?", "*~", "!!", "#&")

    private fun rot13(s: String) = buildString(s.length) {
        for (c in s) append(
            when (c) {
                in 'A'..'Z' -> 'A' + (c - 'A' + 13) % 26
                in 'a'..'z' -> 'a' + (c - 'a' + 13) % 26
                else -> c
            }
        )
    }

    /** Fünf Schritte wie decode_voe_string(): ROT13, Müll raus, Base64, um 3 zurück, umdrehen, Base64, JSON. */
    fun entschluesseln(kodiert: String): JSONObject {
        var s = rot13(kodiert)
        for (m in MUELL) s = s.replace(m, "_")
        s = s.replace("_", "")
        s = String(Base64.getDecoder().decode(s), Charsets.UTF_8)
        s = buildString(s.length) { for (c in s) append(c - 3) }
        s = String(Base64.getDecoder().decode(s.reversed()), Charsets.UTF_8)
        return JSONObject(s)
    }

    /** Sucht die Quelle in allen bekannten Varianten der Einbettungsseite. */
    fun quelleAusHtml(html: String): String? {
        for (m in JSON_SKRIPT.findAll(html)) {
            val roh = m.groupValues[1].trim()
            // Seit Herbst 2026 steht der Wert in einer JSON-Liste (["…"]), früher als einzelner JSON-String.
            // Python verzeiht die Klammern (b64decode überspringt fremde Zeichen), java.util.Base64 nicht.
            val t = when {
                roh.startsWith("[") -> runCatching { JSONArray(roh).getString(0) }.getOrNull() ?: continue
                roh.startsWith("\"") -> runCatching { JSONArray("[$roh]").getString(0) }.getOrNull() ?: continue
                else -> roh
            }
            val q = runCatching { quelle(entschluesseln(t)) }.getOrNull()
            if (q != null) return q
        }
        A168C.find(html)?.let { m -> runCatching { quelle(entschluesseln(m.groupValues[1])) }.getOrNull()?.let { return it } }
        HLS.find(html)?.let { m ->
            val v = m.groupValues[1]
            // Ältere Seiten hatten die HLS-Adresse noch einmal base64-kodiert.
            return if (v.startsWith("http")) v else runCatching { String(Base64.getDecoder().decode(v)) }.getOrDefault(v)
        }
        return null
    }

    private fun quelle(o: JSONObject): String? =
        listOf("source", "direct_access_url", "file").firstNotNullOfOrNull { k -> o.optString(k).takeIf { it.startsWith("http") } }

    fun header(netz: Netz) = mapOf(
        "User-Agent" to netz.userAgent,
        "Accept" to "*/*",
        "Referer" to "https://voe.sx/",
        "Origin" to "https://voe.sx",
    )

    override suspend fun aufloesen(netz: Netz, embed: String): Stream {
        val kopf = mapOf("Referer" to "https://aniworld.to/")
        val seite = netz.anfrage(embed, kopf)
        if (seite.code == 404 || seite.code == 410) throw NetzFehler(tr(R.string.e_geloescht, "VOE", seite.code))
        if (Check.istSchutzseite(seite.text)) throw NetzFehler(tr(R.string.e_schutzseite, "VOE"))

        quelleAusHtml(seite.text)?.let { return Stream(it, header(netz), name) }

        // VOE wechselt die Domain: Die erste Seite leitet per Skript auf /e/ einer anderen Domain weiter.
        val weiter = (WEITERLEITUNG.find(seite.text) ?: LOCATION.find(seite.text))?.groupValues?.get(1)?.trim()
        if (weiter != null) {
            val zweite = netz.anfrage(weiter, mapOf("Referer" to embed))
            if (zweite.code == 404 || zweite.code == 410) throw NetzFehler(tr(R.string.e_geloescht, "VOE", zweite.code))
            (quelleAusHtml(zweite.text) ?: Js.M3U8.find(zweite.text)?.value)?.let { return Stream(it, header(netz), name) }
        }
        Js.M3U8.find(seite.text)?.let { return Stream(it.value, header(netz), name) }
        throw NetzFehler(tr(R.string.e_keine_quelle, "VOE"))
    }
}
