package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.download.Hls
import de.tobidervogel.aniworld.site.Sprache
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class HlsTest {

    private val master = """
        #EXTM3U
        #EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",LANGUAGE="ja",NAME="Japanisch",DEFAULT=YES,URI="audio_ja.m3u8"
        #EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",LANGUAGE="de",NAME="Deutsch",URI="audio_de.m3u8"
        #EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2"
        index-v1-a1.m3u8
        #EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080,AUDIO="aud"
        https://cdn.test/hls/1080/index.m3u8?t=abc
        #EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720
        sub/720.m3u8
    """.trimIndent()

    @Test
    fun masterLesen() {
        val basis = "https://cdn.test/hls/master.m3u8?t=abc"
        assertTrue(Hls.istMaster(master))
        val m = Hls.master(master, basis)
        assertEquals(3, m.varianten.size)
        assertEquals("https://cdn.test/hls/index-v1-a1.m3u8", m.varianten[0].url)
        assertEquals("https://cdn.test/hls/sub/720.m3u8", m.varianten[2].url)
        val beste = Hls.beste(m)!!
        assertEquals(1080, beste.hoehe)
        assertEquals("https://cdn.test/hls/1080/index.m3u8?t=abc", beste.url)
        assertEquals("https://cdn.test/hls/audio_de.m3u8", Hls.tonspur(m, beste, Hls.sprachkuerzel(Sprache.DE_DUB))!!.url)
        assertEquals("https://cdn.test/hls/audio_ja.m3u8", Hls.tonspur(m, beste, Hls.sprachkuerzel(Sprache.DE_SUB))!!.url)
        assertNull(Hls.tonspur(m, m.varianten[2], listOf("de")))
    }

    /** Aufbau einer echten VOE-Playlist (Filmo, 24.10.2026): Ton getrennt in Deutsch und Englisch, dazu I-Frames. */
    @Test
    fun echteVoePlaylist() {
        val basis = "https://cdn.test/engine/hls2-c/01/17814/abc_,n,.urlset/master.m3u8?t=TOKEN"
        val m = Hls.master(datei("voe_master.m3u8"), basis)
        // Die I-Frame-Liste ist keine Variante zum Laden.
        assertEquals(1, m.varianten.size)
        val v = Hls.beste(m)!!
        assertEquals(720, v.hoehe)
        assertEquals("https://cdn.test/engine/hls2-c/01/17814/abc_,n,.urlset/index-v1-a1.m3u8?t=TOKEN", v.url)
        assertEquals("audio0", v.audioGruppe)
        assertTrue(Hls.tonspur(m, v, Hls.sprachkuerzel(Sprache.DE_DUB))!!.url.contains("index-a1.m3u8"))
        assertTrue(Hls.tonspur(m, v, Hls.sprachkuerzel(Sprache.EN_DUB))!!.url.contains("index-a2.m3u8"))
    }

    @Test
    fun medienMitSchluesselUndBereichen() {
        val text = """
            #EXTM3U
            #EXT-X-TARGETDURATION:6
            #EXT-X-MEDIA-SEQUENCE:7
            #EXT-X-KEY:METHOD=AES-128,URI="key.bin",IV=0x000102030405060708090A0B0C0D0E0F
            #EXTINF:6.0,
            seg-1.ts
            #EXT-X-KEY:METHOD=AES-128,URI="https://keys.test/k2"
            #EXTINF:5.5,
            seg-2.ts
            #EXT-X-KEY:METHOD=NONE
            #EXT-X-BYTERANGE:1000@0
            #EXTINF:4,
            big.ts
            #EXT-X-BYTERANGE:500
            #EXTINF:4,
            big.ts
            #EXT-X-ENDLIST
        """.trimIndent()
        val l = Hls.medien(text, "https://cdn.test/a/b/index.m3u8")
        assertEquals(4, l.segmente.size)
        assertEquals(19.5, l.dauer, 0.001)
        val s1 = l.segmente[0]
        assertEquals("https://cdn.test/a/b/seg-1.ts", s1.url)
        assertEquals(7L, s1.nr)
        assertEquals("https://cdn.test/a/b/key.bin", s1.schluessel!!.url)
        assertArrayEquals(ByteArray(16) { it.toByte() }, s1.schluessel!!.iv)
        assertEquals(8L, l.segmente[1].nr)
        assertNull(l.segmente[1].schluessel!!.iv)
        assertNull(l.segmente[2].schluessel)
        assertEquals(0L..999L, l.segmente[2].bereich)
        assertEquals(1000L..1499L, l.segmente[3].bereich)
        assertNull(l.init)
    }

    @Test
    fun fmp4MitInit() {
        val text = "#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\n#EXTINF:6,\n1.m4s\n#EXTINF:6,\n2.m4s\n"
        val l = Hls.medien(text, "https://cdn.test/v/index.m3u8")
        assertEquals("https://cdn.test/v/init.mp4", l.init!!.url)
        assertEquals(2, l.segmente.size)
    }

    @Test
    fun ungueltigeListen() {
        assertThrows(Hls.HlsNichtUnterstuetzt::class.java) { Hls.medien("<html>404</html>", "https://a.test/") }
        assertThrows(Hls.HlsNichtUnterstuetzt::class.java) {
            Hls.medien("#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI=\"k\"\n#EXTINF:6,\na.ts\n", "https://a.test/")
        }
    }

    @Test
    fun ivAusNummer() {
        val iv = Hls.ivAusNummer(0x0102)
        assertEquals(16, iv.size)
        assertEquals(1.toByte(), iv[14])
        assertEquals(2.toByte(), iv[15])
        assertEquals(0.toByte(), iv[0])
    }

    private fun auftrag(serie: String, staffel: Int, folge: Int, film: Boolean = false, stellen: Int = 2) = Auftrag(
        serie = serie, serieUrl = "u", cover = null, staffel = staffel, folge = folge, istFilm = film,
        titel = "", url = "u$folge", sprache = Sprache.DE_DUB, hoster = null, stellen = stellen,
    )

    @Test
    fun benennung() {
        val basis = File("/sdcard/Movies/AniWorld")
        val a = auftrag("Re:Zero – Starting Life in Another World?", 2, 5)
        assertEquals("Re Zero – Starting Life in Another World", Benennung.sauber(a.serie))
        assertEquals("Re Zero – Starting Life in Another World S02E05", Benennung.name(a))
        assertEquals(File(basis, "Re Zero – Starting Life in Another World/Staffel 02"), Benennung.ordner(basis, a))
        assertEquals("One Piece S01E007", Benennung.name(auftrag("One Piece", 1, 7, stellen = 3)))
        assertEquals("100% Liebe Film 02", Benennung.name(auftrag("100% Liebe", 0, 2, film = true)))
        assertEquals(File(basis, "100% Liebe/Filme"), Benennung.ordner(basis, auftrag("100% Liebe", 0, 2, film = true)))
        assertEquals(3, Benennung.stellen(12, 1100))
        assertEquals(2, Benennung.stellen(24, 24))
    }
}
