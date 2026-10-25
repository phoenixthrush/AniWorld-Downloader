package de.tobidervogel.aniworld.hoster

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** Filemoon bzw. die Byse-Seiten dahinter, übertragen aus extractors/provider/filemoon.py. */
object Filemoon : Hoster {
    override val name = "Filemoon"

    private val CODE = Regex("/[de]/([a-zA-Z0-9]+)")
    private val QUELLEN = Regex("""sources\s*:\s*\[\s*\{[^}]*file:\s*['"]([^'"]+)['"]""", RegexOption.DOT_MATCHES_ALL)
    private val DATEI = Regex("""file\s*:\s*['"](https?://[^'"]+)['"]""")

    fun base64url(s: String): ByteArray {
        val rein = s.replace('-', '+').replace('_', '/')
        return Base64.getDecoder().decode(rein + "=".repeat((4 - rein.length % 4) % 4))
    }

    private fun gcm(schluessel: ByteArray, iv: String?, nutzlast: String?): JSONObject? {
        if (iv.isNullOrEmpty() || nutzlast.isNullOrEmpty()) return null
        val daten = base64url(nutzlast)
        if (daten.size <= 16) return null
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, SecretKeySpec(schluessel, "AES"), GCMParameterSpec(128, base64url(iv)))
        return JSONObject(String(c.doFinal(daten), Charsets.UTF_8))
    }

    /** playback-Objekt der Byse-API: Schlüssel aus key_parts (je 16 Byte), AES-256-GCM. */
    fun entschluesseln(playback: JSONObject): JSONObject? {
        val teile = playback.optJSONArray("key_parts") ?: return null
        val schluessel = ByteArrayOutputStream()
        for (i in 0 until teile.length()) {
            val t = teile.optString(i)
            if (t.isEmpty()) continue
            val b = base64url(t)
            if (b.size == 16) schluessel.write(b)
        }
        val k = schluessel.toByteArray()
        return runCatching { gcm(k, playback.optString("iv"), playback.optString("payload")) }.getOrNull()
            ?: runCatching { gcm(k, playback.optString("iv2"), playback.optString("payload2")) }.getOrNull()
    }

    fun besteQuelle(daten: JSONObject): String? {
        daten.optJSONArray("sources")?.let { arr ->
            var beste: String? = null
            var hoehe = -1
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                val url = o.optString("url").ifEmpty { o.optString("file") }
                // Byse schreibt die Qualität (Stand 24.10.2026) nur als label "1080p", ältere Antworten als height.
                val h = o.optInt("height", 0).takeIf { it > 0 }
                    ?: Regex("""(\d{3,4})p""").find(o.optString("label"))?.groupValues?.get(1)?.toIntOrNull()
                    ?: (o.optInt("bitrate_kbps", 0) / 10)
                if (url.isNotEmpty() && h >= hoehe) { beste = url; hoehe = h }
            }
            if (beste != null) return beste
        }
        return daten.optString("source").ifEmpty { daten.optString("file") }.ifEmpty { null }
    }

    fun ausText(text: String): String? =
        Js.M3U8.find(text)?.value
            ?: QUELLEN.find(text)?.groupValues?.get(1)
            ?: DATEI.find(text)?.groupValues?.get(1)?.takeIf { ".m3u8" in it || ".mp4" in it }

    override suspend fun aufloesen(netz: Netz, embed: String): Stream {
        val kopf = mapOf("User-Agent" to netz.userAgent, "Referer" to Js.ursprung(embed) + "/")
        // Fürs Laden der Segmente die Kopfzeilen, mit denen das Original (PROVIDER_HEADERS_D) erfolgreich lädt.
        val laden = mapOf("User-Agent" to netz.userAgent, "Referer" to "https://filemoon.to")
        val code = CODE.find(embed)?.groupValues?.get(1)

        // Weg 1: neue Byse-API mit verschlüsselten Wiedergabedaten.
        if (code != null) {
            val api = netz.anfrage("${Js.ursprung(embed)}/api/videos/$code", kopf + ("Accept" to "application/json"))
            if (api.ok) {
                val playback = runCatching { JSONObject(api.text).optJSONObject("playback") }.getOrNull()
                val daten = playback?.let { entschluesseln(it) }
                daten?.let { besteQuelle(it) }?.let { return Stream(it, laden, name) }
            }
        }

        // Weg 2: alte Seiten mit gepacktem Skript.
        val seite = netz.anfrage(embed, kopf)
        if (!seite.ok) throw NetzFehler(tr(R.string.e_http, "Filemoon", seite.code))
        for (js in Js.alleEntpackt(seite.text)) ausText(js)?.let { return Stream(it, laden, name) }
        ausText(seite.text)?.let { return Stream(it, laden, name) }
        throw NetzFehler(tr(R.string.e_keine_quelle, "Filemoon"))
    }
}
