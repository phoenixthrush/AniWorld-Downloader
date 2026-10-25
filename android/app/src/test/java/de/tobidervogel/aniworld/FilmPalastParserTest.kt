package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.site.Einzelfilm
import de.tobidervogel.aniworld.site.FilmPalastParser
import de.tobidervogel.aniworld.site.Sprache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Gegen Ausschnitte der echten filmpalast.to-Seiten vom 25.10.2026 (fp_*.html). */
class FilmPalastParserTest {

    @Test
    fun liste() {
        val k = FilmPalastParser.karten(datei("fp_liste.html"))
        assertEquals(5, k.size)
        assertEquals("The Matrix 4 The Matrix: Resurrections", k[0].titel)
        assertEquals("https://filmpalast.to/stream/the-matrix-4-the-matrix-resurrections", k[0].url)
        assertEquals("https://filmpalast.to/files/movies/315/the-matrix-4-the-matrix-resurrections.jpg", k[0].cover)
        assertTrue(k.all { it.url.startsWith("https://filmpalast.to/stream/") })
    }

    @Test
    fun genres() {
        val g = FilmPalastParser.genres(datei("fp_start.html"))
        assertEquals("Abenteuer", g.first().name)
        assertEquals("Abenteuer", g.first().slug)
        assertTrue(g.any { it.slug == "Sci-Fi" || it.slug == "Action" })
        assertTrue(g.none { it.slug.isEmpty() || it.slug.contains('/') })
    }

    @Test
    fun film() {
        val url = "https://filmpalast.to/stream/the-matrix-4-the-matrix-resurrections"
        val html = datei("fp_film.html")
        val s = FilmPalastParser.film(html, url)
        assertEquals("The Matrix 4 The Matrix: Resurrections", s.titel)
        assertEquals("2021", s.jahre)
        // Nur die Genres des Films, nicht „Englisch“ aus der Menüleiste.
        assertEquals(listOf("Thriller", "Sci-Fi", "Action"), s.genres)
        assertEquals("6.6", s.imdb)
        assertTrue(s.beschreibung.startsWith("Thomas Anderson"))
        assertTrue(s.cover!!.startsWith("https://filmpalast.to/files/movies/"))
        assertTrue(s.staffeln.single().istFilme)

        val f = FilmPalastParser.folge(html, url)
        assertEquals("The Matrix 4 The Matrix: Resurrections (2021)", f.titel)
        assertEquals(setOf(Sprache.DE_DUB), f.sprachen)
    }

    @Test
    fun hoster() {
        val l = FilmPalastParser.links(datei("fp_film.html"), "https://filmpalast.to/stream/the-matrix-4-the-matrix-resurrections")
        val h = l.links[Sprache.DE_DUB]!!
        assertEquals(listOf("Firestream", "VIDARA", "VOE", "Vixeo", "FlyFile"), h.keys.toList())
        assertEquals("https://voe.sx/nfdbgcxhj3mn", h["VOE"])
        // Englische Fassungen erkennt die App an der Adresse.
        assertEquals(setOf(Sprache.EN_DUB), FilmPalastParser.links(datei("fp_film.html"), "https://filmpalast.to/stream/matrix-english").sprachen)
    }

    @Test
    fun adressenUndAblage() {
        assertEquals("https://filmpalast.to/stream/scream-7", FilmPalastParser.filmUrl("//filmpalast.to/stream/scream-7"))
        assertEquals("https://filmpalast.to/stream/scream-7", FilmPalastParser.filmUrl("https://www.filmpalast.to/stream/scream-7?x=1"))
        assertNull(FilmPalastParser.filmUrl("https://filmpalast.to/movies/new"))
        assertTrue(Einzelfilm.ist("https://filmpalast.to/stream/scream-7"))
        assertFalse(Einzelfilm.ist("https://serienstream.to/serie/lupin"))
        assertFalse(FilmPalastParser.weitereSeite("""<a href="https://filmpalast.to/movies/top/page/3">3</a>""", 1))
        assertTrue(FilmPalastParser.weitereSeite("""<a href='https://filmpalast.to/movies/top/page/2'>2</a>""", 1))
        val a = Auftrag(
            serie = "Scream 7", serieUrl = "https://filmpalast.to/stream/scream-7", cover = null, staffel = 0, folge = 1,
            istFilm = true, titel = "Scream 7 (2026)", url = "https://filmpalast.to/stream/scream-7", sprache = Sprache.DE_DUB, hoster = null,
        )
        assertEquals(File("/x/Filme"), Benennung.ordner(File("/x"), a))
        assertEquals("Scream 7 (2026)", Benennung.name(a))
    }
}
