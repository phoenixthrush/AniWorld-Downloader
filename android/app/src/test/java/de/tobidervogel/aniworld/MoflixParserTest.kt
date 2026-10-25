package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.hoster.MoflixClick
import de.tobidervogel.aniworld.hoster.Stream
import de.tobidervogel.aniworld.site.Einzelfilm
import de.tobidervogel.aniworld.site.MoflixParser
import de.tobidervogel.aniworld.site.Sprache
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Startseite: gekürzte echte Seite von moflix-stream.xyz vom 25.10.2026 (mf_start.html).
 * Die API-Antworten sind nach den Feldern nachgebaut, die models/moflix_stream im Original liest.
 */
class MoflixParserTest {
    private val b = MoflixParser.BASIS

    @Test
    fun startseite() {
        val html = datei("mf_start.html")
        assertEquals("testtoken", MoflixParser.csrf(html))
        val reihen = MoflixParser.startReihen(html)
        assertEquals(listOf("trending-movies", "top-10-movies-serien", "now-playing"), reihen.keys.toList())
        val lupin = reihen["now-playing"]!!.first()
        assertEquals("Lupin", lupin.titel)
        assertEquals("$b/titles/4559774", lupin.url)
        assertEquals("Serie · 2021", lupin.genre)
        assertTrue(lupin.cover!!.startsWith("https://image.tmdb.org/"))

        val g = MoflixParser.genresAusStart(html)
        assertTrue(g.any { it.slug == "krimi" && it.name == "Krimi" })
        assertEquals(g.map { it.name }.sorted(), g.map { it.name })
    }

    @Test
    fun adressen() {
        assertEquals("$b/titles/4559774", MoflixParser.serienUrl("https://moflix-stream.xyz/titles/4559774/lupin/season/2/episodes/3"))
        assertEquals(2 to 3, MoflixParser.staffelUndFolge("$b/titles/4559774/lupin/season/2/episodes/3"))
        assertNull(MoflixParser.staffelUndFolge("$b/titles/4559768"))
        assertEquals("$b/titles/4559774/season/1/episodes/5", MoflixParser.folgenUrl("4559774", 1, 5))
        assertNull(MoflixParser.serienUrl("https://example.com/titles/4559774"))
        assertNull(MoflixParser.serienUrl("$b/titles/abc"))
    }

    @Test
    fun sucheOhnePersonen() {
        val json = JSONObject(
            """{"results":[
              {"id":4559774,"name":"Lupin","model_type":"title","is_series":true,"year":2021,"poster":"https://image.tmdb.org/t/p/original/a.jpg"},
              {"id":77,"name":"Omar Sy","model_type":"person"},
              {"id":"x1","name":"Kaputt","model_type":"title"},
              {"id":4559768,"name":"Kraken","model_type":"title","is_series":false,"poster":"storage/k.jpg"}
            ]}""",
        )
        val t = MoflixParser.suche(json)
        assertEquals(listOf("Lupin", "Kraken"), t.map { it.titel })
        assertEquals("$b/storage/k.jpg", t[1].cover)
        assertEquals("Film", t[1].beschreibung)
    }

    @Test
    fun serieUndFolgen() {
        val url = "$b/titles/4559774"
        val json = JSONObject(
            """{"title":{"id":4559774,"name":"Lupin","year":2021,"is_series":true,"description":"Assane Diop …",
               "poster":"https://image.tmdb.org/t/p/original/a.jpg","genres":[{"name":"drama","display_name":"Drama"},{"name":"krimi","display_name":"Krimi"}]},
               "seasons":{"data":[{"number":2,"episodes_count":5},{"number":1,"episodes_count":5}]}}""",
        )
        val s = MoflixParser.serie(json, url)
        assertEquals("Lupin", s.titel)
        assertEquals(listOf("Drama", "Krimi"), s.genres)
        assertEquals(listOf(1, 2), s.staffeln.map { it.nummer })
        assertFalse(Einzelfilm.ist(s))

        val seite = JSONObject(
            """{"episodes":{"data":[{"episode_number":1,"name":"Kapitel 1"},{"episode_number":2,"name":null},{"episode_number":0}],
               "next_page":null,"last_page":1}}""",
        )
        val (folgen, weiter) = MoflixParser.folgen(seite, "4559774", 2)
        assertFalse(weiter)
        assertEquals(listOf(1, 2), folgen.map { it.nummer })
        assertEquals("Kapitel 1", folgen[0].titelDe)
        assertEquals("", folgen[1].titelDe)
        assertEquals("$b/titles/4559774/season/2/episodes/2", folgen[1].url)
        assertEquals("S02E02", folgen[1].kuerzel)
        assertTrue(MoflixParser.folgen(JSONObject("""{"episodes":{"data":[],"next_page":2}}"""), "1", 1).second)

        val l = MoflixParser.links(
            JSONObject(
                """{"episode":{"videos":[
                  {"name":"Mirror 1","src":"https://moflix-stream.click/v/abc"},
                  {"name":"Mirror 2","src":"https://voe.sx/e/xyz"},
                  {"name":"Mirror 3","src":"http://unsicher.example/e/1"},
                  {"name":"Mirror 4","src":"https://voe.sx/e/doppelt"}]}}""",
            ),
        )
        assertEquals(listOf("MoflixClick", "VOE"), l.hoster(Sprache.DE_DUB))
        assertEquals("https://voe.sx/e/xyz", l.links[Sprache.DE_DUB]!!["VOE"])
    }

    @Test
    fun film() {
        val url = "$b/titles/4559768"
        val json = JSONObject(
            """{"title":{"id":4559768,"name":"Kraken - Erwachen der Tiefe","year":2025,"is_series":false,
               "videos":[{"name":"Mirror 1","src":"https://vidara.so/e/k1"}]}}""",
        )
        val s = MoflixParser.serie(json, url)
        assertEquals(listOf(0), s.staffeln.map { it.nummer })
        assertTrue(Einzelfilm.ist(s))
        val f = MoflixParser.film(json, url)
        assertTrue(f.istFilm)
        assertEquals("Kraken - Erwachen der Tiefe (2025)", f.titel)
        assertEquals(mapOf("Vidara" to "https://vidara.so/e/k1"), MoflixParser.links(json).links[Sprache.DE_DUB])

        val a = Auftrag(
            serie = s.titel, serieUrl = url, cover = null, staffel = 0, folge = 1,
            istFilm = true, titel = f.titel, url = url, sprache = Sprache.DE_DUB, hoster = null,
        )
        assertEquals(File("/x/Filme"), Benennung.ordner(File("/x"), a))
    }

    @Test
    fun keinJson() {
        assertNull(MoflixParser.json("<!DOCTYPE html><title>Just a moment...</title>"))
        assertEquals(1, MoflixParser.json("""{"a":1}""")!!.getInt("a"))
        assertNull(MoflixParser.bootstrap("<html></html>"))
    }

    @Test
    fun moflixClick() {
        val html = """<script>var links = {"hls2":"https://cdn.example/hls2/master.m3u8","hls3":"https://cdn.example/hls3/index.txt","hls4":"http://alt.example/x.m3u8"};</script>"""
        // hls4 ohne https fällt weg, Reihenfolge wie im Player: hls4, hls3, hls2.
        assertEquals(listOf("https://cdn.example/hls3/index.txt", "https://cdn.example/hls2/master.m3u8"), MoflixClick.kandidaten(html))
        assertTrue(MoflixClick.kandidaten("<html></html>").isEmpty())
        // Eine .txt-Playlist zählt als HLS, wenn der Extraktor es sagt.
        assertTrue(Stream("https://cdn.example/hls3/index.txt", emptyMap(), "MoflixClick", hls = true).istHls)
        assertFalse(Stream("https://cdn.example/hls3/index.txt", emptyMap(), "MoflixClick").istHls)
    }
}
