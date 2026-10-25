package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.AutoSync
import de.tobidervogel.aniworld.download.Status
import de.tobidervogel.aniworld.site.Folge
import de.tobidervogel.aniworld.site.Sprache
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AutoSyncTest {
    private val url = "https://aniworld.to/anime/stream/frieren"

    private fun auftrag(s: Int, f: Int, sprache: Sprache = Sprache.DE_SUB, status: Status = Status.FERTIG, erstellt: Long = 1, film: Boolean = false) =
        Auftrag(
            serie = "Frieren", serieUrl = url, cover = null, staffel = s, folge = f, istFilm = film, titel = "",
            url = "$url/staffel-$s/episode-$f", sprache = sprache, hoster = null, status = status, erstellt = erstellt,
        )

    private fun folge(s: Int, f: Int, vararg sp: Sprache = arrayOf(Sprache.DE_SUB)) =
        Folge("$url/staffel-$s/episode-$f", f, s, false, "", "", sp.toSortedSet(), emptyList())

    @Test
    fun bibliothek() {
        val stand = AutoSync.bibliothek(
            listOf(
                auftrag(1, 3), auftrag(1, 10), auftrag(2, 2),
                auftrag(2, 5, status = Status.PAUSE),
                // Die zuletzt angelegte Folge bestimmt die Sprache.
                auftrag(1, 1, Sprache.DE_DUB, erstellt = 0),
                auftrag(0, 1, film = true),
            ),
        ).single()
        assertEquals(Sprache.DE_SUB, stand.sprache)
        assertEquals(2 to 2, stand.staffel to stand.folge)
        assertTrue(AutoSync.bibliothek(listOf(auftrag(0, 1, film = true), auftrag(1, 1, status = Status.FEHLER))).isEmpty())
    }

    @Test
    fun ersteProefungReihtNichtsEin() {
        val stand = AutoSync.bibliothek(listOf(auftrag(1, 1))).single()
        // Eine Probefolge von 1100: ohne Marke darf nichts in die Warteschlange.
        val staffeln = mapOf(1 to (1..1100).map { folge(1, it) })
        assertTrue(AutoSync.neue(stand, staffeln, null, emptySet()).isEmpty())
        assertEquals(1 to 1100, AutoSync.marke(staffeln, Sprache.DE_SUB))
    }

    @Test
    fun nurWasNachDerMarkeErscheint() {
        val stand = AutoSync.bibliothek(listOf(auftrag(1, 4))).single()
        val staffeln = mapOf(
            1 to (1..12).map { folge(1, it) } + folge(1, 13, Sprache.EN_SUB),
            2 to listOf(folge(2, 1), folge(2, 2, Sprache.DE_DUB)),
        )
        // Letzte Prüfung sah bis S01E10: neu sind 11, 12 und S02E01; 13 und S02E02 fehlen in der Sprache.
        val neu = AutoSync.neue(stand, staffeln, 1 to 10, emptySet())
        assertEquals(listOf(1 to 11, 1 to 12, 2 to 1), neu.map { it.staffel to it.nummer })
        // Was schon einen Auftrag hat (auch gelöscht oder pausiert), kommt nicht wieder.
        val ohne = AutoSync.neue(stand, staffeln, 1 to 10, setOf("$url/staffel-1/episode-11"))
        assertEquals(listOf(1 to 12, 2 to 1), ohne.map { it.staffel to it.nummer })
        assertEquals(2 to 1, AutoSync.marke(staffeln, Sprache.DE_SUB))
    }

    @Test
    fun geladenUeberDerMarke() {
        // Von Hand schon weiter geladen als die Marke: nichts davor kommt zurück.
        val stand = AutoSync.bibliothek(listOf(auftrag(1, 12))).single()
        val staffeln = mapOf(1 to (1..14).map { folge(1, it) })
        assertEquals(listOf(13, 14), AutoSync.neue(stand, staffeln, 1 to 8, emptySet()).map { it.nummer })
    }
}
