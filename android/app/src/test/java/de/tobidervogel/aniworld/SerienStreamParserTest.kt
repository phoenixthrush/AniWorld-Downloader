package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.site.SerienStreamParser
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.site.StaffelRef
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Gegen Ausschnitte der echten serienstream.to-Seiten vom 24.10.2026 (sto_*.html). */
class SerienStreamParserTest {

    @Test
    fun beliebteSerien() {
        val html = datei("sto_beliebt.html")
        val neu = SerienStreamParser.abschnitt(html, "Neue Staffeln")
        // Lupin steht mit zwei Staffeln drin, die App zeigt die Serie einmal.
        assertEquals(listOf("Vera - Ein ganz spezieller Fall", "Lupin"), neu.map { it.titel })
        assertEquals("https://serienstream.to/serie/vera-ein-ganz-spezieller-fall", neu[0].url)
        assertEquals(13, neu[0].staffel)
        assertEquals("https://serienstream.to/media/images/channel/desktop/lupin-fvg4t39m?format=jpg", neu[1].cover)
        val meist = SerienStreamParser.abschnitt(html, "Meistgesehen")
        assertEquals(listOf("VisionQuest", "The Terminal List", "Avatar - Die sieben Häfen"), meist.map { it.titel })
        assertNull(meist[0].staffel)
    }

    @Test
    fun genres() {
        val g = SerienStreamParser.genres(datei("sto_start.html"))
        assertEquals("abenteuer", g.first().slug)
        assertEquals("Abenteuer", g.first().name)
        assertTrue(g.any { it.slug == "anime" })
        assertEquals(g.size, g.map { it.slug }.toSet().size)
    }

    @Test
    fun genreSeite() {
        val (karten, weiter) = SerienStreamParser.genreSeite(datei("sto_genre.html"))
        assertEquals(listOf("10 - Tödlicher Einsatz", "10 Dinge, die ich an dir hasse", "100 Karat"), karten.map { it.titel })
        assertTrue(karten.all { it.cover!!.startsWith("https://serienstream.to/media/images/channel/") })
        assertTrue(weiter)
        assertFalse(SerienStreamParser.genreSeite("<div></div>").second)
    }

    @Test
    fun sucheNurSerien() {
        val (treffer, _) = SerienStreamParser.suche(datei("sto_suche.html"))
        assertEquals(listOf("Die Gangster Gang: Aller Anfang ist böse", "Angel Di Maria: Die Mauer durchbrechen"), treffer.map { it.titel })
        assertEquals("https://serienstream.to/serie/die-gangster-gang-aller-anfang-ist-bse", treffer[0].url)
        assertTrue(treffer[0].cover!!.endsWith("?format=jpg"))
        // Gleicher Aufbau wie im Python-Test test_only_series_group_is_parsed: Titel aus h6, nicht aus alt.
        val python = """<div data-group="all"><div class="card"><a href="/serie/ignored"></a><h6 class="show-title">ignored</h6></div></div>
            <div data-group="shows"><div class="card"><a href="/serie/from" class="show-cover"><picture><img alt="Poster" src="poster.jpg"></picture></a>
            <div class="card-body"><h6 class="show-title mb-0">From &amp; <em>Beyond</em></h6></div></div></div>"""
        assertEquals(listOf("From & Beyond"), SerienStreamParser.suche(python).first.map { it.titel })
    }

    @Test
    fun serie() {
        val url = "https://serienstream.to/serie/breaking-bad"
        val s = SerienStreamParser.serie(datei("sto_serie.html"), url)
        assertEquals("Breaking Bad", s.titel)
        assertEquals("2008–2013", s.jahre)
        assertEquals("16", s.fsk)
        assertEquals("tt0903747", s.imdb)
        assertTrue(s.beschreibung.startsWith("Nachdem er von seiner lebensbedrohlichen Krankheit erfahren hat"))
        assertEquals("https://serienstream.to/media/images/channel/desktop/breaking-bad-7c90ppib?format=jpg", s.cover)
        assertEquals(listOf("Staffel 1", "Staffel 2", "Staffel 3", "Staffel 4", "Staffel 5", "Filme"), s.staffeln.map { it.name })
        assertEquals("https://serienstream.to/serie/breaking-bad/staffel-0", s.staffeln.last().url)
        assertTrue(s.genres.isNotEmpty())
    }

    @Test
    fun staffel() {
        val ref = StaffelRef(2, "https://serienstream.to/serie/breaking-bad/staffel-2", false)
        val f = SerienStreamParser.staffel(datei("sto_staffel.html"), ref)
        assertEquals(3, f.size)
        assertEquals("https://serienstream.to/serie/breaking-bad/staffel-2/episode-1", f[0].url)
        assertEquals(1, f[0].nummer)
        assertEquals("Vorsichtsmaßnahmen", f[0].titelDe)
        assertEquals("Seven Thirty-Seven", f[0].titelEn)
        assertEquals(setOf(Sprache.DE_DUB), f[0].sprachen)
        assertEquals(listOf("VOE"), f[0].hoster)
        assertEquals("S02E03", f[2].kuerzel)

        // Zeile aus dem Python-Test test_sto_domains.py: beide Flaggen, Link per href.
        val python = """<table><tr class="episode-row"><td><a href="/serie/from/staffel-1/episode-1">Episode 1</a></td>
            <td><i class="svg-flag-german"></i><i class="svg-flag-english"></i></td></tr></table>"""
        val p = SerienStreamParser.staffel(python, StaffelRef(1, "https://serienstream.to/serie/from/staffel-1", false))
        assertEquals(setOf(Sprache.DE_DUB, Sprache.EN_DUB), p.single().sprachen)
    }

    @Test
    fun folgenLinks() {
        val l = SerienStreamParser.folgenLinks(datei("sto_folge.html"))
        assertEquals(setOf(Sprache.DE_DUB), l.sprachen)
        assertEquals(listOf("VOE"), l.hoster(Sprache.DE_DUB))
        assertTrue(l.links[Sprache.DE_DUB]!!["VOE"]!!.startsWith("https://serienstream.to/r?t="))
        val en = SerienStreamParser.folgenLinks("""<button data-play-url="/r?t=x" data-provider-name="Vidoza" data-language-label="Englisch"></button>""")
        assertEquals("https://serienstream.to/r?t=x", en.links[Sprache.EN_DUB]!!["Vidoza"])
    }

    @Test
    fun adressen() {
        assertEquals("https://serienstream.to/serie/lupin", SerienStreamParser.serienUrl("https://s.to/serie/stream/lupin"))
        assertEquals("https://serienstream.to/serie/lupin", SerienStreamParser.serienUrl("https://serienstream.cx/serie/lupin/staffel-2/episode-4"))
        assertEquals("https://serienstream.to/serie/lupin", SerienStreamParser.serienUrl("/serie/lupin/staffel-1"))
        assertNull(SerienStreamParser.serienUrl("https://aniworld.to/anime/stream/x"))
    }
}
