package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.site.AniSkip
import de.tobidervogel.aniworld.site.MalStaffel
import de.tobidervogel.aniworld.site.Sprung
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AniSkipTest {

    @Test
    fun suchtrefferBevorzugtGenauenTitel() {
        val json = """{"data":[
            {"mal_id":1,"type":"Movie","title":"Goblin Slayer: Goblin's Crown"},
            {"mal_id":2,"type":"TV","title":"Isekai Shoukan","title_english":"Something Else"},
            {"mal_id":37349,"type":"TV","title":"Goblin Slayer","titles":[{"type":"English","title":"Goblin Slayer"}]}
        ]}"""
        assertEquals(37349, AniSkip.ersterTreffer(json, "Goblin Slayer"))
        // Ohne genauen Treffer: erster TV-Eintrag, Filme zählen nicht.
        assertEquals(2, AniSkip.ersterTreffer(json, "Ganz anderer Titel"))
        assertNull(AniSkip.ersterTreffer("""{"data":[]}""", "x"))
    }

    @Test
    fun eintragMitFortsetzungen() {
        val json = """{"data":{"mal_id":37349,"type":"TV","episodes":12,"aired":{"from":"2018-10-07T00:00:00+00:00"},
            "relations":[
              {"relation":"Sequel","entry":[{"mal_id":47160,"type":"anime","name":"Goblin Slayer II"}]},
              {"relation":"Side story","entry":[{"mal_id":39000,"type":"anime","name":"OVA"}]},
              {"relation":"Adaptation","entry":[{"mal_id":5,"type":"manga","name":"Manga"}]},
              {"relation":"Prequel","entry":[{"mal_id":36000,"type":"anime","name":"Vorher"}]}
            ]}}"""
        val (staffel, verwandt) = AniSkip.eintrag(json)
        assertEquals(MalStaffel(37349, 12, "2018-10-07T00:00:00+00:00"), staffel)
        assertEquals(listOf(47160, 36000), verwandt)

        val film = AniSkip.eintrag("""{"data":{"mal_id":1,"type":"Movie","relations":[{"relation":"Sequel","entry":[{"mal_id":2,"type":"anime"}]}]}}""")
        assertNull(film.first)
        assertEquals(listOf(2), film.second)
    }

    @Test
    fun zuordnungMitGeteilterStaffel() {
        val mal = listOf(MalStaffel(10, 12, "2018"), MalStaffel(20, 13, "2020"), MalStaffel(21, 12, "2021"), MalStaffel(30, null, "2024"))
        assertEquals(10 to 5, AniSkip.zuordnen(mal, 1, 5))
        assertEquals(20 to 13, AniSkip.zuordnen(mal, 2, 13))
        // AniWorld führt beide Hälften als Staffel 2: Folge 14 ist bei MAL Teil 2, Folge 1.
        assertEquals(21 to 1, AniSkip.zuordnen(mal, 2, 14))
        // Unbekannte Folgenzahl: kein Überlauf.
        assertEquals(30 to 40, AniSkip.zuordnen(mal, 4, 40))
        assertNull(AniSkip.zuordnen(mal, 5, 1))
        assertNull(AniSkip.zuordnen(emptyList(), 1, 1))
    }

    @Test
    fun sprungzeiten() {
        val v1 = """{"found":true,"results":[
            {"interval":{"start_time":1187.09,"end_time":1277.09},"skip_type":"ed","skip_id":"b","episode_length":1422.04},
            {"interval":{"start_time":123.014,"end_time":213.014},"skip_type":"op","skip_id":"a","episode_length":1422.04}
        ]}"""
        assertEquals(listOf(Sprung("op", 123_014, 213_014), Sprung("ed", 1_187_090, 1_277_090)), AniSkip.spruenge(v1))
        assertEquals("Ending", AniSkip.spruenge(v1)[1].name)

        val v2 = """{"found":true,"results":[{"interval":{"startTime":10.0,"endTime":100.5},"skipType":"op"},{"interval":{"startTime":5,"endTime":9},"skipType":"recap"}]}"""
        assertEquals(listOf(Sprung("op", 10_000, 100_500)), AniSkip.spruenge(v2))
        assertTrue(AniSkip.spruenge("""{"found":false,"results":[]}""").isEmpty())
    }
}
