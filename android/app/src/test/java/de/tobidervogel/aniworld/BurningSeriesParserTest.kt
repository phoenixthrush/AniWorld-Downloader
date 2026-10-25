package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.site.BurningSeriesParser
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.site.StaffelRef
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Gegen Ausschnitte der echten Burning-Series-Seiten vom 25.10.2026 (bs_*.html). */
class BurningSeriesParserTest {

    @Test
    fun indexUndSuche() {
        val index = BurningSeriesParser.index(datei("bs_index.html"))
        assertEquals(listOf("Abenteuer", "Action", "Drama"), index.keys.toList())
        val abenteuer = index.getValue("Abenteuer")
        assertEquals("2012 – Das Jahr Null", abenteuer[0].titel)
        assertEquals("https://bs.cine.to/serie/2012-Das-Jahr-Null", abenteuer[0].url)
        val treffer = BurningSeriesParser.suche(index, "breaking")
        assertEquals(listOf("https://bs.cine.to/serie/Breaking-Bad"), treffer.map { it.url })
        assertTrue(BurningSeriesParser.suche(index, "   ").isEmpty())
    }

    @Test
    fun startseite() {
        val html = datei("bs_start.html")
        val serien = BurningSeriesParser.neueSerien(html)
        assertEquals("Small Prophets", serien[0].titel)
        assertEquals("https://bs.cine.to/serie/Small-Prophets", serien[0].url)
        val folgen = BurningSeriesParser.neueFolgen(html)
        assertEquals("Untergetaucht", folgen[0].titel)
        assertEquals("https://bs.cine.to/serie/Untergetaucht/1/1-Die-Untergegangenen", folgen[0].url)
        assertEquals(1, folgen[0].staffel)
        assertEquals(1, folgen[0].folge)
        assertEquals(listOf(Sprache.DE_DUB), folgen[0].sprachen)
    }

    @Test
    fun serie() {
        val url = "https://bs.cine.to/serie/Breaking-Bad"
        val s = BurningSeriesParser.serie(datei("bs_serie.html"), url)
        assertEquals("Breaking Bad", s.titel)
        assertTrue(s.beschreibung.startsWith("Nachdem er von seiner lebensbedrohlichen Krankheit"))
        assertEquals(listOf("Drama", "Krimi", "Thriller"), s.genres)
        assertEquals("2008–2013", s.jahre)
        assertEquals("https://bs.cine.to/public/images/cover/29.jpg", s.cover)
        // Specials (Staffel 0) stehen hinten und behalten ihren Namen.
        assertEquals(listOf(1, 2, 3, 4, 5, 0), s.staffeln.map { it.nummer })
        assertEquals("Specials", s.staffeln.last().name)
        assertEquals("https://bs.cine.to/serie/Breaking-Bad/1", s.staffeln[0].url)
    }

    @Test
    fun staffelInBeidenSprachen() {
        val de = BurningSeriesParser.staffel(datei("bs_staffel_de.html"), "de")
        val en = BurningSeriesParser.staffel(datei("bs_staffel_en.html"), "en")
        assertEquals(7, de.size)
        assertEquals("Der Einstieg", de[0].titel)
        assertEquals("https://bs.cine.to/serie/Breaking-Bad/1/1-Der-Einstieg", de[0].folgenUrl)
        assertEquals(listOf("VOE", "Doodstream", "Vidmoly", "Filemoon"), de[0].hoster.keys.toList())
        assertEquals("serie/Breaking-Bad/1/1-Der-Einstieg/de/VOE", de[0].hoster["VOE"])
        // Zeilen in der falschen Sprache zählen nicht.
        assertTrue(BurningSeriesParser.staffel(datei("bs_staffel_de.html"), "en").isEmpty())

        val ref = StaffelRef(1, "https://bs.cine.to/serie/Breaking-Bad/1", istFilme = false)
        val folgen = BurningSeriesParser.folgen(ref, mapOf(Sprache.DE_DUB to de, Sprache.EN_DUB to en))
        assertEquals(7, folgen.size)
        assertEquals("Der Einstieg", folgen[0].titelDe)
        assertEquals("Pilot", folgen[0].titelEn)
        assertEquals(setOf(Sprache.DE_DUB, Sprache.EN_DUB), folgen[0].sprachen)
        assertEquals("S01E01", folgen[0].kuerzel)

        val l = BurningSeriesParser.links(folgen[0].url, mapOf(Sprache.DE_DUB to de, Sprache.EN_DUB to en))
        assertEquals(setOf(Sprache.DE_DUB, Sprache.EN_DUB), l.sprachen)
        assertEquals(listOf("VOE"), l.hoster(Sprache.EN_DUB))
    }

    @Test
    fun player() {
        assertEquals(
            "https://burning-series.io/stream/4985739856",
            BurningSeriesParser.streamZiel(datei("bs_player.html"), "https://burning-series.io"),
        )
        assertFalse(BurningSeriesParser.vpnHinweis("<p>Player</p>"))
        assertTrue(BurningSeriesParser.vpnHinweis("<p>Burning Series Streams via VPN abrufbar! Durch die Zensur …</p>"))
    }

    @Test
    fun adressen() {
        assertEquals("https://bs.cine.to/serie/Breaking-Bad", BurningSeriesParser.serienUrl("https://burning-series.io/serie/Breaking-Bad/1/de"))
        assertEquals("https://bs.cine.to/serie/Breaking-Bad", BurningSeriesParser.serienUrl("serie/Breaking-Bad"))
        assertNull(BurningSeriesParser.serienUrl("https://serienstream.to/serie/breaking-bad"))
        assertEquals(
            "https://bs.cine.to/serie/Breaking-Bad/1/1-Der-Einstieg",
            BurningSeriesParser.folgenUrl("serie/Breaking-Bad/1/1-Der-Einstieg/de/VOE"),
        )
    }
}
