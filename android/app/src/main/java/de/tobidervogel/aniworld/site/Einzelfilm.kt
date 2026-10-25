package de.tobidervogel.aniworld.site

/**
 * Wann ein Titel ein einzelner Film ist: auf reinen Filmseiten (Filmo, FilmPalast) immer, auf
 * gemischten Seiten (Kinox, MegaKino, Moflix) dann, wenn er nur aus „Staffel 0“ mit einem Film besteht. Solche
 * Titel haben in der App genau eine „Folge“ und landen gesammelt unter `<Ordner>/Filme/`.
 */
object Einzelfilm {
    private fun nurFilme(url: String) = FilmoParser.filmUrl(url) != null || FilmPalastParser.filmUrl(url) != null

    private fun gemischt(url: String) = KinoxParser.serienUrl(url) != null || MegaKinoParser.istEintrag(url) || MoflixParser.serienUrl(url) != null

    /** Für Downloads: Adresse der Serie plus Staffel und Film-Merkmal des Auftrags. */
    fun ist(serieUrl: String, istFilm: Boolean, staffel: Int): Boolean =
        nurFilme(serieUrl) || (gemischt(serieUrl) && istFilm && staffel == 0)

    /** Für die Oberfläche: geladene Serie. */
    fun ist(s: Serie): Boolean =
        nurFilme(s.url) || (gemischt(s.url) && s.staffeln.singleOrNull()?.let { it.istFilme && it.nummer == 0 } == true)

    /** Nur nach Adresse (reine Filmseiten). */
    fun ist(url: String): Boolean = nurFilme(url)
}
