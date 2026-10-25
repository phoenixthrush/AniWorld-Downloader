package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.site.AniWorldParser
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.site.StaffelRef
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

fun datei(name: String): String =
    requireNotNull(object {}.javaClass.classLoader!!.getResource(name)) { "Testdatei fehlt: $name" }.readText()

class AniWorldParserTest {

    @Test
    fun startseiteAbschnitte() {
        val html = datei("start.html")
        val beliebt = AniWorldParser.abschnitt(html, "Derzeit beliebt")
        assertEquals(listOf("One Piece", "Frieren: Beyond Journey's End"), beliebt.map { it.titel })
        assertEquals("https://aniworld.to/anime/stream/one-piece", beliebt[0].url)
        assertEquals("https://aniworld.to/public/img/cover/one-piece-stream-cover-xyz_150x225.png", beliebt[0].cover)
        assertEquals("Abenteuer", beliebt[0].genre)
        val neu = AniWorldParser.abschnitt(html, "Neue Animes")
        assertEquals(listOf("https://aniworld.to/anime/stream/bullbuster"), neu.map { it.url })
        assertTrue(AniWorldParser.abschnitt(html, "Gibt es nicht").isEmpty())
    }

    @Test
    fun genreListe() {
        val genres = AniWorldParser.genres(datei("aniworld_genre_list.html"))
        assertEquals("Abenteuer", genres.first().name)
        assertEquals("abenteuer", genres.first().slug)
        assertTrue(genres.any { it.slug == "romantische-komoedie" && it.name == "Romantische Komödie" })
        assertEquals("uebermaessige-gewaltdarstellung", genres.last().slug)
    }

    @Test
    fun genreSeite() {
        val (karten, weiter) = AniWorldParser.genreSeite(datei("aniworld_genre_page.html"), "mecha", 1)
        assertTrue(weiter)
        assertEquals("BULLBUSTER", karten[0].titel)
        assertEquals("I'm the Evil Lord of an Intergalactic Empire!", karten[1].titel)
        assertTrue(karten[0].cover!!.endsWith("_200x300.jpg"))
        assertFalse(karten[0].cover!!.startsWith("data:"))
        val (_, letzte) = AniWorldParser.genreSeite(datei("aniworld_genre_page.html"), "mecha", 4)
        assertFalse(letzte)
    }

    @Test
    fun neueFolgenMitZusammengelegtenSprachen() {
        val folgen = AniWorldParser.neueFolgen(datei("aniworld_new_episodes.html"))
        assertEquals(3, folgen.size)
        val ogre = folgen[0]
        assertEquals("https://aniworld.to/anime/stream/the-ogres-bride/staffel-1/episode-11", ogre.url)
        assertEquals("The Ogre's Bride", ogre.titel)
        assertEquals(1, ogre.staffel)
        assertEquals(11, ogre.folge)
        assertEquals("Sa, 12.09.2026", ogre.datum)
        assertEquals(listOf(Sprache.DE_SUB, Sprache.EN_SUB), ogre.sprachen)
        assertTrue(folgen[1].titel.startsWith("Rich Girl Caretaker: I'm Secretly"))
        assertFalse(folgen[1].titel.contains("  "))
    }

    @Test
    fun sucheNurSerien() {
        val treffer = AniWorldParser.suche(datei("suche.json"))
        assertEquals(listOf("One Piece", "One Punch Man"), treffer.map { it.titel })
        assertEquals("https://aniworld.to/anime/stream/one-piece", treffer[0].url)
        assertEquals("Monkey D. Ruffy & seine Crew ...", treffer[0].beschreibung)
        assertTrue(AniWorldParser.suche("<html>kein json</html>").isEmpty())
    }

    @Test
    fun serie() {
        val url = "https://aniworld.to/anime/stream/goblin-slayer"
        val s = AniWorldParser.serie(datei("serie.html"), url)
        assertEquals("Goblin Slayer", s.titel)
        assertEquals("2018–2023", s.jahre)
        assertEquals("16", s.fsk)
        assertEquals("tt8690728", s.imdb)
        assertEquals(listOf("Action", "Fantasy", "Horror"), s.genres)
        assertEquals("Goblins - die schwächsten aller Monster. Eine junge Priesterin & ihr Abenteuer.", s.beschreibung)
        assertEquals("https://aniworld.to/public/img/cover/goblin-slayer-stream-cover-abc_220x330.png", s.cover)
        assertEquals(listOf("Staffel 1", "Staffel 2", "Filme"), s.staffeln.map { it.name })
        assertEquals("https://aniworld.to/anime/stream/goblin-slayer/staffel-2", s.staffeln[1].url)
        assertEquals("https://aniworld.to/anime/stream/goblin-slayer/filme", s.staffeln[2].url)
    }

    @Test
    fun staffel() {
        val ref = StaffelRef(1, "https://aniworld.to/anime/stream/goblin-slayer/staffel-1", false)
        val folgen = AniWorldParser.staffel(datei("staffel.html"), ref)
        assertEquals(2, folgen.size)
        val f1 = folgen[0]
        assertEquals(1, f1.nummer)
        assertEquals("https://aniworld.to/anime/stream/goblin-slayer/staffel-1/episode-1", f1.url)
        assertEquals("Das Schicksal der Abenteurer", f1.titelDe)
        assertEquals("The Fate of Particular Adventurers", f1.titelEn)
        assertEquals(setOf(Sprache.DE_DUB, Sprache.DE_SUB, Sprache.EN_SUB), f1.sprachen)
        assertEquals(listOf("VOE", "Filemoon", "Vidmoly"), f1.hoster)
        assertEquals("S01E01", f1.kuerzel)
        assertEquals("Dämonentöter & Co", folgen[1].titelDe)
        assertEquals(setOf(Sprache.DE_SUB), folgen[1].sprachen)
    }

    @Test
    fun filme() {
        val ref = StaffelRef(0, "https://aniworld.to/anime/stream/goblin-slayer/filme", true)
        val filme = AniWorldParser.staffel(datei("filme.html"), ref)
        assertEquals(1, filme.size)
        assertTrue(filme[0].istFilm)
        assertEquals(1, filme[0].nummer)
        assertEquals("Goblin's Crown", filme[0].titel)
        assertEquals("Film 1", filme[0].kuerzel)
        assertEquals("https://aniworld.to/anime/stream/goblin-slayer/filme/film-1", filme[0].url)
    }

    @Test
    fun folgenLinks() {
        val l = AniWorldParser.folgenLinks(datei("folge.html"))
        assertEquals(setOf(Sprache.DE_DUB, Sprache.EN_SUB, Sprache.DE_SUB), l.sprachen)
        assertEquals(listOf("VOE", "Filemoon"), l.hoster(Sprache.DE_DUB))
        assertEquals("https://aniworld.to/redirect/2738955", l.links[Sprache.DE_DUB]!!["VOE"])
        assertEquals("https://aniworld.to/redirect/2738802", l.links[Sprache.DE_SUB]!!["Vidmoly"])
        assertTrue(l.hoster(Sprache.EN_DUB).isEmpty())
    }

    @Test
    fun adressen() {
        assertEquals(
            "https://aniworld.to/anime/stream/one-piece",
            AniWorldParser.serienUrl("https://aniworld.to/anime/stream/one-piece/staffel-3/episode-2"),
        )
        assertNull(AniWorldParser.serienUrl("https://example.com/x"))
        assertNull(AniWorldParser.absolut("data:image/png;base64,AAA"))
        assertEquals(Sprache.DE_SUB, Sprache.ausFlagge("/public/img/japanese-german.svg"))
        assertEquals(Sprache.EN_SUB, Sprache.ausKey("2"))
    }

    /** Format von random_anime() im Original: JSON-Liste, `link` ist nur der Slug. */
    @Test
    fun zufall() {
        val json = """[{"name":"One Piece","link":"one-piece"},{"name":"X","link":"../böse"},{"name":"Frieren","link":"/frieren/"}]"""
        assertEquals(
            listOf("https://aniworld.to/anime/stream/one-piece", "https://aniworld.to/anime/stream/frieren"),
            AniWorldParser.zufall(json),
        )
        assertTrue(AniWorldParser.zufall("<html>DDoS-Guard</html>").isEmpty())
    }
}
