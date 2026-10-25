package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.site.Einzelfilm
import de.tobidervogel.aniworld.site.KinoxParser
import de.tobidervogel.aniworld.site.Sprache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Gegen Ausschnitte der echten kinox.to-Seiten vom 25.10.2026 (kx_*). */
class KinoxParserTest {

    @Test
    fun listen() {
        val kino = KinoxParser.karten(datei("kx_kino.html"))
        assertTrue(kino.isNotEmpty())
        assertTrue(kino.all { it.url.startsWith("https://kinox.to/Stream/") && it.url.endsWith(".html") })
        assertTrue(kino.first().cover!!.startsWith("https://kinox.to/statics/thumbs/"))

        val suche = KinoxParser.karten(datei("kx_suche.html"))
        val bb = suche.filter { it.titel == "Breaking Bad" }
        // Kinox führt die englische Fassung als eigenen Eintrag.
        assertEquals(listOf("https://kinox.to/Stream/Breaking_Bad-1.html", "https://kinox.to/Stream/Breaking_Bad.html"), bb.map { it.url })
        assertEquals(listOf("Englisch", ""), bb.map { it.genre })
    }

    @Test
    fun genresOhneErwachsene() {
        val g = KinoxParser.genres(datei("kx_start.html"))
        assertEquals("Action", g.first().name)
        assertTrue(g.any { it.slug == "Comedy" && it.name == "Komödie" })
        assertTrue(g.none { it.slug == "Adult" })
    }

    @Test
    fun serie() {
        val url = "https://kinox.to/Stream/Breaking_Bad.html"
        val html = datei("kx_serie.html")
        assertTrue(KinoxParser.istSerie(html))
        assertEquals("2402", KinoxParser.serieId(html))
        val s = KinoxParser.eintrag(html, url)
        assertEquals("Breaking Bad", s.titel)
        assertEquals("2008", s.jahre)
        assertTrue(s.beschreibung.startsWith("Walter White"))
        assertEquals(listOf(1, 2, 3, 4, 5), s.staffeln.map { it.nummer })
        assertFalse(Einzelfilm.ist(s))
        assertEquals(Sprache.DE_DUB, KinoxParser.sprache(html))

        val folgen = KinoxParser.folgen(html, url, s.staffeln[1])
        assertEquals((1..13).toList(), folgen.map { it.nummer })
        assertEquals("https://kinox.to/Stream/Breaking_Bad.html?s=2&e=3", folgen[2].url)
        assertEquals(2 to 3, KinoxParser.staffelUndFolge(folgen[2].url))
        assertEquals("S02E03", folgen[2].kuerzel)
    }

    @Test
    fun film() {
        val url = "https://kinox.to/Stream/Bitteres_Fest.html"
        val html = datei("kx_film.html")
        assertFalse(KinoxParser.istSerie(html))
        val s = KinoxParser.eintrag(html, url)
        assertEquals("Bitteres Fest", s.titel)
        assertEquals("2026", s.jahre)
        assertTrue(Einzelfilm.ist(s))
        val f = KinoxParser.folgen(html, url, s.staffeln.single())
        assertEquals("Bitteres Fest (2026)", f.single().titel)
        assertTrue(f.single().istFilm)

        val l = KinoxParser.spiegel(html, Sprache.DE_DUB)
        assertEquals(listOf("Vidara", "Vinovo", "Dood"), l.hoster(Sprache.DE_DUB))
        assertEquals("Bitteres_Fest&Hoster=95", l.links[Sprache.DE_DUB]!!["Dood"])

        // Ablage wie bei den anderen Filmseiten.
        val a = Auftrag(
            serie = "Bitteres Fest", serieUrl = url, cover = null, staffel = 0, folge = 1,
            istFilm = true, titel = "Bitteres Fest (2026)", url = url, sprache = Sprache.DE_DUB, hoster = null,
        )
        assertEquals(File("/x/Filme"), Benennung.ordner(File("/x"), a))
    }

    @Test
    fun spiegelUndWeiterleitung() {
        val l = KinoxParser.spiegel(datei("kx_folge.html"), Sprache.DE_DUB)
        assertEquals(listOf("Vidara", "Vinovo", "Dood"), l.hoster(Sprache.DE_DUB))
        assertEquals("Breaking_Bad&Hoster=112&Season=2&Episode=3", l.links[Sprache.DE_DUB]!!["Vidara"])
        val ziel = KinoxParser.weiterleitung(datei("kx_mirror.json"))!!
        assertTrue(ziel.startsWith("https://kinox.to/redirect/"))
    }

    @Test
    fun adressen() {
        assertEquals("https://kinox.to/Stream/Breaking_Bad.html", KinoxParser.serienUrl("/Stream/Breaking_Bad.html?s=2&e=3"))
        assertEquals("https://kinox.to/Stream/Breaking_Bad.html", KinoxParser.serienUrl("https://kinos.to/Stream/Breaking_Bad.html"))
        assertNull(KinoxParser.serienUrl("https://example.com/Stream/Breaking_Bad.html"))
        assertNull(KinoxParser.staffelUndFolge("https://kinox.to/Stream/Bitteres_Fest.html"))
    }
}
