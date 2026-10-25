package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.site.FilmoParser
import de.tobidervogel.aniworld.site.Sprache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Gegen Ausschnitte der echten filmo.to-Seiten vom 24.10.2026 (filmo_*.html, Tokens ersetzt). */
class FilmoParserTest {

    @Test
    fun filmliste() {
        val html = datei("filmo_filme.html")
        val k = FilmoParser.karten(html)
        assertEquals(listOf("Awakening the Last Dream", "Masterplan", "LEGO Friends: Heartlake the Musical"), k.map { it.titel })
        assertEquals("https://filmo.to/movies/awakening-the-last-dream", k[0].url)
        assertTrue(k[0].cover!!.startsWith("https://filmo.to/img/poster/"))
        assertTrue(FilmoParser.weitereSeite(html))
        val g = FilmoParser.genres(html)
        assertEquals("Action", g.first().name)
        assertEquals("1", g.first().slug)
        assertTrue(g.none { it.slug.isEmpty() })
    }

    @Test
    fun suche() {
        val k = FilmoParser.karten(datei("filmo_suche.html"))
        assertEquals(listOf("Matrix", "Matrix Reloaded"), k.map { it.titel })
        assertEquals("https://filmo.to/movies/matrix-1", k[0].url)
    }

    @Test
    fun film() {
        val url = "https://filmo.to/movies/matrix-1"
        val html = datei("filmo_film.html")
        val f = FilmoParser.film(html, url)
        assertEquals("Matrix", f.titel)
        assertEquals("1999", f.jahre)
        assertEquals(listOf("Action", "Science Fiction"), f.genres)
        assertTrue(f.cover!!.startsWith("https://filmo.to/img/poster/"))
        assertEquals(1, f.staffeln.size)
        assertTrue(f.staffeln[0].istFilme)

        val folge = FilmoParser.folge(html, url)
        assertEquals("Matrix (1999)", folge.titel)
        assertEquals(setOf(Sprache.DE_DUB, Sprache.EN_DUB), folge.sprachen)
        assertEquals(listOf("VOE", "Byse"), folge.hoster)
        assertEquals("CSRF", FilmoParser.csrf(html))
    }

    @Test
    fun quellenAlsToken() {
        val l = FilmoParser.links(datei("filmo_film.html"))
        assertEquals(listOf("VOE", "Byse"), l.hoster(Sprache.DE_DUB))
        assertEquals(listOf("VOE", "Byse"), l.hoster(Sprache.EN_DUB))
        val voe = l.links[Sprache.DE_DUB]!!["VOE"]!!
        assertTrue(voe.startsWith(FilmoParser.TOKEN_PRAEFIX))
        assertFalse(voe.removePrefix(FilmoParser.TOKEN_PRAEFIX).isEmpty())
    }

    /** Echte Zwischenseite für Byse: Filmo leitet nicht weiter, sondern verlinkt. */
    @Test
    fun zwischenseite() {
        assertEquals("https://bysezejataos.com/d/eujg42emnstd", FilmoParser.externerLink(datei("filmo_oeffnen.html")))
        assertNull(FilmoParser.externerLink("""<a class="open" href="https://filmo.to/movies/x">x</a>"""))
    }

    @Test
    fun adressenUndAblage() {
        assertEquals("https://filmo.to/movies/matrix-1", FilmoParser.filmUrl("https://www.filmo.to/movies/matrix-1?x=1"))
        assertNull(FilmoParser.filmUrl("https://serienstream.to/serie/lupin"))
        val a = Auftrag(
            serie = "Matrix", serieUrl = "https://filmo.to/movies/matrix-1", cover = null, staffel = 0, folge = 1,
            istFilm = true, titel = "Matrix (1999)", url = "https://filmo.to/movies/matrix-1", sprache = Sprache.DE_DUB, hoster = null,
        )
        assertEquals(File("/x/Filme"), Benennung.ordner(File("/x"), a))
        assertEquals("Matrix (1999)", Benennung.name(a))
    }
}
