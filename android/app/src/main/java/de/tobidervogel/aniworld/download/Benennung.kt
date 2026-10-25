package de.tobidervogel.aniworld.download

import java.io.File

/**
 * Ablage: `<Ordner>/<Serie>/Staffel 01/<Serie> S01E01.mp4`, Filme unter `<Serie>/Filme/`.
 * Angelehnt an die Jellyfin-Vorlage des Originals, nur kürzer und deutsch.
 */
object Benennung {
    private val VERBOTEN = Regex("""[\\/:*?"<>|\u0000-\u001F]""")

    /** Wie clean_title() im Original: Zeichen raus, die Dateisysteme nicht mögen. */
    fun sauber(name: String): String =
        name.replace(VERBOTEN, " ").replace(Regex("\\s+"), " ").trim().trimEnd('.').ifEmpty { "Unbenannt" }

    // Filme ohne Reihe (Filmo) liegen gesammelt unter `<Ordner>/Filme/<Titel (Jahr)>.mp4`.
    fun ordner(basis: File, a: Auftrag): File {
        if (a.einzelfilm) return File(basis, "Filme")
        val serie = File(basis, sauber(a.serie))
        return if (a.istFilm) File(serie, "Filme") else File(serie, "Staffel %02d".format(a.staffel))
    }

    fun name(a: Auftrag): String {
        if (a.einzelfilm) return sauber(a.titel.ifBlank { a.serie })
        val serie = sauber(a.serie)
        // Serienname nicht durch format() schicken: Ein "%" im Titel würde sonst als Platzhalter gelesen.
        return if (a.istFilm) serie + " Film " + "%02d".format(a.folge)
        else serie + " " + "S%02dE%0${a.stellen.coerceIn(2, 4)}d".format(a.staffel, a.folge)
    }

    /** Stellen der Folgennummer: zwei, ab 100 Folgen drei (damit die Sortierung stimmt). */
    fun stellen(anzahlFolgen: Int, hoechsteNummer: Int): Int =
        if (maxOf(anzahlFolgen, hoechsteNummer) >= 100) 3 else 2
}
