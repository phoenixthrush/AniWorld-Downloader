package de.tobidervogel.aniworld.ui

import de.tobidervogel.aniworld.site.Genre

/** Seiten, die über die Reiter gelegt werden. Ein einfacher Stapel statt Navigation-Bibliothek. */
sealed interface Ziel {
    data class Serie(val url: String, val titel: String, val cover: String?, val staffel: Int? = null) : Ziel
    /** @param quelle Name des Anbieters (AniWorld, SerienStream, Filmo) */
    data class GenreListe(val genre: Genre, val quelle: String) : Ziel
    /** Geladene Folgen einer Serie in der Bibliothek. */
    data class Ablage(val serieUrl: String, val titel: String) : Ziel
    data object Suche : Ziel
    data object ProtokollAnsicht : Ziel
}

/** Vorläufiger Titel aus dem Slug, bis die Seite geladen ist („one-piece“ → „One Piece“). */
fun titelAusAdresse(url: String): String =
    url.trimEnd('/').substringAfterLast('/').split('-').filter { it.isNotEmpty() }
        .joinToString(" ") { w -> w.replaceFirstChar { it.uppercase() } }
