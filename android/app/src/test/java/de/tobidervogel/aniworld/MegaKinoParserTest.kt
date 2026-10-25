package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.hoster.GxPlayer
import de.tobidervogel.aniworld.hoster.Stream
import de.tobidervogel.aniworld.site.Einzelfilm
import de.tobidervogel.aniworld.site.MegaKinoParser
import de.tobidervogel.aniworld.site.Sprache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Gegen gekürzte echte Seiten von megakino25.com vom 25.10.2026 (mk_*). */
class MegaKinoParserTest {
    private val b = "https://megakino25.com"

    @Test
    fun listen() {
        val start = MegaKinoParser.karten(datei("mk_start.html"), b, abListe = true)
        assertEquals(20, start.size)
        assertEquals("Crazy For You", start.first().titel)
        assertEquals("$b/films/6593-crazy-for-you.html", start.first().url)
        assertTrue(start.first().cover!!.startsWith("$b/uploads/posts/"))
        assertEquals("Filme / Thriller", start.first().genre)

        val genre = MegaKinoParser.karten(datei("mk_genre.html"), b, abListe = true)
        assertEquals("$b/serials/6572-visionquest-1-staffel.html", genre.first().url)
        assertTrue(MegaKinoParser.weitereSeite(datei("mk_genre.html"), 1))

        // Einträge liegen auch unter Genre-Pfaden (/crime/…, /action/…).
        val suche = MegaKinoParser.karten(datei("mk_suche.html"), b, abListe = true)
        assertEquals(18, suche.size)
        assertEquals("$b/crime/4692-the-penguin-staffel-1.html", suche.first().url)
        assertTrue(suche.any { it.titel == "Batman & Robin" })
    }

    @Test
    fun genres() {
        val g = MegaKinoParser.genres(datei("mk_start.html"))
        assertEquals("Animation", g.first().name)
        assertEquals("multfilm", g.first().slug)
        assertTrue(g.any { it.slug == "science-fiction" && it.name == "Sci-Fi" })
        assertEquals(19, g.size)
    }

    @Test
    fun film() {
        val url = "$b/films/6593-crazy-for-you.html"
        val html = datei("mk_film.html")
        assertFalse(MegaKinoParser.istSerie(html))
        val s = MegaKinoParser.eintrag(html, url, b)
        assertEquals("Crazy For You", s.titel)
        assertEquals("2025", s.jahre)
        assertEquals(listOf("Thriller"), s.genres)
        assertTrue(s.beschreibung.isNotEmpty())
        assertTrue(s.cover!!.startsWith("$b/uploads/posts/2026-10/"))
        assertTrue(Einzelfilm.ist(s))

        val f = MegaKinoParser.folgen(html, url, b, s.staffeln.single()).single()
        assertTrue(f.istFilm)
        assertEquals("Crazy For You (2025)", f.titel)

        // Der Trailer (YouTube) gehört nicht zu den Hostern.
        val l = MegaKinoParser.links(html, url)
        assertEquals(listOf("VOE", "Andromedans"), l.hoster(Sprache.DE_DUB))
        assertEquals("https://voe.sx/e/fopr9ctov7zn", l.links[Sprache.DE_DUB]!!["VOE"])

        val a = Auftrag(
            serie = s.titel, serieUrl = url, cover = null, staffel = 0, folge = 1,
            istFilm = true, titel = f.titel, url = url, sprache = Sprache.DE_DUB, hoster = null,
        )
        assertEquals(File("/x/Filme"), Benennung.ordner(File("/x"), a))
    }

    @Test
    fun serie() {
        val url = "$b/serials/6579-tulsa-king-4-staffel.html"
        val html = datei("mk_serial.html")
        assertTrue(MegaKinoParser.istSerie(html))
        val s = MegaKinoParser.eintrag(html, url, b)
        // Der Staffelzusatz wandert vom Titel in die Staffelnummer.
        assertEquals("Tulsa King", s.titel)
        assertEquals(listOf(4), s.staffeln.map { it.nummer })
        assertEquals(listOf("Drama", "Thriller"), s.genres)
        assertFalse(Einzelfilm.ist(s))

        val folgen = MegaKinoParser.folgen(html, url, b, s.staffeln.single())
        assertEquals(listOf(1, 2), folgen.map { it.nummer })
        assertEquals("$url#mkep=2", folgen[1].url)
        assertEquals("S04E02", folgen[1].kuerzel)

        val l = MegaKinoParser.links(html, folgen[1].url)
        assertEquals(mapOf("VOE" to "https://voe.sx/e/vkcjafo19lnp"), l.links[Sprache.DE_DUB])
        assertEquals("https://voe.sx/e/aptamyvs045k", MegaKinoParser.links(html, folgen[0].url).links[Sprache.DE_DUB]!!["VOE"])
    }

    @Test
    fun staffelImTitel() {
        assertEquals("Tulsa King" to 4, MegaKinoParser.staffelAusTitel("Tulsa King - 4 Staffel"))
        assertEquals("Batwoman" to 3, MegaKinoParser.staffelAusTitel("Batwoman - Staffel 3"))
        assertEquals("Dark Matter - Der Zeitenläufer" to 2, MegaKinoParser.staffelAusTitel("Dark Matter - Der Zeitenläufer - 2 Staffel"))
        assertNull(MegaKinoParser.staffelAusTitel("Crazy For You"))
    }

    @Test
    fun adressenUndDomain() {
        assertEquals("$b/films/6593-crazy-for-you.html", MegaKinoParser.serienUrl("/films/6593-crazy-for-you.html", b))
        // Eine Domain in der Adresse bleibt, die Folgenmarke fällt weg.
        assertEquals(
            "https://megakino24.org/serials/6579-tulsa-king-4-staffel.html",
            MegaKinoParser.serienUrl("https://www.megakino24.org/serials/6579-tulsa-king-4-staffel.html#mkep=2", b),
        )
        assertNull(MegaKinoParser.serienUrl("https://example.com/films/6593-crazy-for-you.html", b))
        assertNull(MegaKinoParser.serienUrl("/collection/2092-die-besten-weihnachtsfilme.html", b))
        assertEquals(2, MegaKinoParser.folge("$b/serials/1-x.html#mkep=2"))
        assertTrue(Einzelfilm.ist("$b/films/1-x.html", istFilm = true, staffel = 0))

        assertEquals("megakino25.com", MegaKinoParser.domain("megakino25.com\n"))
        assertEquals("megakino26.net", MegaKinoParser.domain("https://www.megakino26.net/"))
        // Fremde Domains aus dem Tracker werden nicht übernommen.
        assertNull(MegaKinoParser.domain("evil.example"))
        assertNull(MegaKinoParser.domain("<html>"))

        assertTrue(MegaKinoParser.brauchtToken("""<script>fetch("/index.php?yg=token").then(function(){ location.replace("/") })</script>"""))
        assertFalse(MegaKinoParser.brauchtToken(datei("mk_film.html")))
    }

    @Test
    fun gxPlayer() {
        val html = """<script>var player = {"uid":"u1","md5":"abc","id":"42","x":1};</script>"""
        val url = GxPlayer.ausHtml(html)!!
        assertEquals("https://watch.gxplayer.xyz/m3u8/u1/abc/master.txt?s=1&id=42&cache=1", url)
        assertTrue(Stream.istHls(url))
        assertFalse(Stream.istHls("https://x.example/video.mp4"))
        assertNull(GxPlayer.ausHtml("<html></html>"))
    }
}
