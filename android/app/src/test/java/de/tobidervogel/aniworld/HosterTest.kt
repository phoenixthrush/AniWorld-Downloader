package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.hoster.Aufloeser
import de.tobidervogel.aniworld.hoster.Doodstream
import de.tobidervogel.aniworld.hoster.Filemoon
import de.tobidervogel.aniworld.hoster.Hosters
import de.tobidervogel.aniworld.hoster.Js
import de.tobidervogel.aniworld.hoster.Mitleser
import de.tobidervogel.aniworld.hoster.Vidmoly
import de.tobidervogel.aniworld.hoster.Vidoza
import de.tobidervogel.aniworld.hoster.Voe
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

class HosterTest {

    /** Umkehrung von decode_voe_string(), um echte Seiten nachzubauen. */
    private fun voeKodieren(json: String): String {
        val b1 = Base64.getEncoder().encodeToString(json.toByteArray())
        val verschoben = b1.reversed().map { it + 3 }.joinToString("")
        val b2 = Base64.getEncoder().encodeToString(verschoben.toByteArray())
        // Müllzeichen einstreuen wie die Seite.
        val mitMuell = b2.substring(0, 4) + "@$" + b2.substring(4, 9) + "^^" + b2.substring(9) + "#&"
        return mitMuell.map { c ->
            when (c) {
                in 'A'..'Z' -> 'A' + (c - 'A' + 13) % 26
                in 'a'..'z' -> 'a' + (c - 'a' + 13) % 26
                else -> c
            }
        }.joinToString("")
    }

    @Test
    fun voeEntschluesseln() {
        val quelle = "https://cdn-abc.edgeon-bandwidth.com/engine/hls2/01/xyz/master.m3u8?t=1&s=2"
        val kodiert = voeKodieren("""{"source":"$quelle","title":"x"}""")
        assertEquals(quelle, Voe.entschluesseln(kodiert).getString("source"))

        // Variante 1: JSON-Skriptblock mit maskierten Zeichen.
        val skript = JSONArray().put(kodiert).toString().removePrefix("[").removeSuffix("]")
        val html = """<html><script type="application/json">$skript</script></html>"""
        assertEquals(quelle, Voe.quelleAusHtml(html))

        // Variante 1b (Stand 24.10.2026 auf voe.sx): JSON-Liste statt String.
        assertEquals(quelle, Voe.quelleAusHtml("""<script type="application/json">["$kodiert"]</script>"""))

        // Variante 2: var a168c
        assertEquals(quelle, Voe.quelleAusHtml("<script>var a168c='$kodiert';</script>"))

        // Variante 3: alte Seiten mit 'hls'
        assertEquals("https://x.test/a.m3u8", Voe.quelleAusHtml("var s = {'hls': 'https://x.test/a.m3u8'};"))
        assertNull(Voe.quelleAusHtml("<html>nichts</html>"))
    }

    private fun b64url(b: ByteArray) = Base64.getUrlEncoder().withoutPadding().encodeToString(b)

    @Test
    fun filemoonByseEntschluesseln() {
        val teil1 = ByteArray(16) { it.toByte() }
        val teil2 = ByteArray(16) { (it + 100).toByte() }
        val iv = ByteArray(12) { (it * 7).toByte() }
        val klar = """{"sources":[{"url":"https://a.test/360.m3u8","height":360},{"url":"https://a.test/1080.m3u8","height":1080}]}"""
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, SecretKeySpec(teil1 + teil2, "AES"), GCMParameterSpec(128, iv))
        val geheim = c.doFinal(klar.toByteArray())
        val playback = JSONObject()
            .put("key_parts", JSONArray().put(b64url(teil1)).put(b64url(teil2)))
            .put("iv", b64url(iv))
            .put("payload", b64url(geheim))
        val daten = Filemoon.entschluesseln(playback)!!
        assertEquals("https://a.test/1080.m3u8", Filemoon.besteQuelle(daten))

        // Byse am 24.10.2026: Qualität nur als label, ohne height.
        val labels = JSONObject("""{"sources":[{"url":"https://a.test/1080.m3u8","label":"1080p","bitrate_kbps":1952},{"url":"https://a.test/720.m3u8","label":"720p","bitrate_kbps":900}]}""")
        assertEquals("https://a.test/1080.m3u8", Filemoon.besteQuelle(labels))

        // Kaputter erster Teil: zweiter Satz (iv2/payload2) greift.
        playback.put("payload", b64url(ByteArray(40))).put("iv2", b64url(iv)).put("payload2", b64url(geheim))
        assertEquals("https://a.test/1080.m3u8", Filemoon.besteQuelle(Filemoon.entschluesseln(playback)!!))
    }

    @Test
    fun packerEntpacken() {
        val html = """<script>eval(function(p,a,c,k,e,d){while(c--)if(k[c])p=p.replace(new RegExp('\\b'+c.toString(a)+'\\b','g'),k[c]);return p}('0 1="2://3.4/5.6";7({1:1})',36,8,'var|file|https|cdn|example|master|m3u8|setup'.split('|'),0,{}))</script>"""
        val entpackt = Js.alleEntpackt(html)
        assertEquals(1, entpackt.size)
        assertTrue(entpackt[0].startsWith("var file=\"https://cdn.example/master.m3u8\""))
        assertEquals("https://cdn.example/master.m3u8", Filemoon.ausText(entpackt[0]))
    }

    @Test
    fun vidmolyUndVidoza() {
        assertEquals(
            "https://box.vidmoly.biz/hls/,abc,.urlset/master.m3u8",
            Vidmoly.ausHtml("""<script>player.setup({sources: [{file:"https://box.vidmoly.biz/hls/,abc,.urlset/master.m3u8"}]})</script>"""),
        )
        assertEquals(
            "https://str38.vidoza.net/x/v.mp4",
            Vidoza.ausHtml("""var a = { sourcesCode: [{ src: "https://str38.vidoza.net/x/v.mp4", type: "video/mp4" }] }"""),
        )
    }

    @Test
    fun doodLink() {
        val l = Doodstream.direktLink("https://dl.test/abc~", "tok123", 1_700_000_000)
        assertTrue(l.startsWith("https://dl.test/abc~"))
        assertTrue(l.endsWith("?token=tok123&expiry=1700000000"))
        assertEquals("https://dl.test/abc~".length + 10, l.indexOf('?'))
    }

    @Test
    fun hosterZuordnung() {
        assertEquals(Voe, Hosters.fuer("VOE"))
        assertEquals(Doodstream, Hosters.fuer("DoodStream"))
        assertEquals(Filemoon, Hosters.fuer("https://bysezejataos.com/e/abc"))
        assertNull(Hosters.fuer("Streamtape"))
        assertEquals("https://voe.sx", Js.ursprung("https://voe.sx/e/abc?x=1"))
    }

    @Test
    fun reihenfolge() {
        val seite = listOf("Vidmoly", "VOE", "Streamtape", "Filemoon")
        assertEquals(listOf("VOE", "Filemoon", "Vidmoly", "Streamtape"), Aufloeser.reihenfolge(seite, null, listOf("VOE", "Filemoon", "Doodstream", "Vidmoly")))
        assertEquals(listOf("Vidmoly", "VOE", "Filemoon", "Streamtape"), Aufloeser.reihenfolge(seite, "Vidmoly", listOf("VOE", "Filemoon", "Vidmoly")))
        assertEquals(seite.first(), Aufloeser.reihenfolge(seite, "Gibtsnicht", emptyList()).first())
    }

    @Test
    fun mitleserAuswahl() {
        assertTrue(Mitleser.istVideo("https://a.test/x/index-v1-a1.m3u8?t=1"))
        assertTrue(Mitleser.istVideo("https://a.test/v.mp4"))
        assertFalse(Mitleser.istVideo("https://a.test/player.js"))
        assertFalse(Mitleser.istVideo("https://a.test/mp4-guide.html"))
        assertEquals(
            "https://a.test/master.m3u8",
            Mitleser.auswaehlen(listOf("https://ads.test/clip.mp4", "https://a.test/index.m3u8", "https://a.test/master.m3u8")),
        )
        assertEquals("https://ads.test/clip.mp4", Mitleser.auswaehlen(listOf("https://ads.test/clip.mp4")))
        assertNull(Mitleser.auswaehlen(emptyList()))
    }
}
