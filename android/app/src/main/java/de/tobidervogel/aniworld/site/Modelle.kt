package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R

/**
 * Sprachfassungen so, wie AniWorld sie über `data-lang-key` kennzeichnet.
 * Gleiche Zuordnung wie LANG_KEY_MAP im Python-Original (config.py).
 */
enum class Sprache(val key: String, val kurz: String, val lang: String, val flagge: String) {
    // Reihenfolge = Anzeigereihenfolge in der App, nicht die Schlüsselnummern.
    DE_DUB("1", "DE", "Deutsche Synchro", "german"),
    DE_SUB("3", "DE-Sub", "Deutsche Untertitel", "japanese-german"),
    EN_SUB("2", "EN-Sub", "Englische Untertitel", "japanese-english"),
    EN_DUB("4", "EN", "Englische Synchro", "english");

    /** Langer Name für die Oberfläche (strings.xml). */
    val anzeigeRes: Int
        get() = when (this) {
            DE_DUB -> R.string.sprache_de_dub
            DE_SUB -> R.string.sprache_de_sub
            EN_SUB -> R.string.sprache_en_sub
            EN_DUB -> R.string.sprache_en_dub
        }

    companion object {
        fun ausKey(key: String?): Sprache? = entries.firstOrNull { it.key == key?.trim() }

        /** `/public/img/japanese-german.svg` -> DE_SUB */
        fun ausFlagge(pfad: String?): Sprache? {
            val name = pfad?.substringAfterLast('/')?.substringBefore('.')?.lowercase() ?: return null
            return entries.firstOrNull { it.flagge == name }
        }
    }
}

/** Ein Cover in einer Liste (Startseite, Genre). `staffel`: Karte zeigt auf eine bestimmte Staffel. */
data class Karte(val titel: String, val url: String, val cover: String?, val genre: String = "", val staffel: Int? = null)

data class Genre(val name: String, val slug: String)

data class NeueFolge(
    val titel: String,
    val url: String,
    val staffel: Int,
    val folge: Int,
    val datum: String,
    val sprachen: List<Sprache>,
)

data class Treffer(val titel: String, val url: String, val beschreibung: String, val cover: String? = null)

/** @param bezeichnung eigener Name der Seite, z. B. „Specials“ für Staffel 0 bei Burning Series */
data class StaffelRef(val nummer: Int, val url: String, val istFilme: Boolean, val bezeichnung: String? = null) {
    val name get() = bezeichnung ?: if (istFilme) "Filme" else "Staffel $nummer"
}

data class Serie(
    val url: String,
    val titel: String,
    val beschreibung: String,
    val genres: List<String>,
    val jahre: String?,
    val cover: String?,
    val fsk: String?,
    val imdb: String?,
    val staffeln: List<StaffelRef>,
)

data class Folge(
    val url: String,
    val nummer: Int,
    val staffel: Int,
    val istFilm: Boolean,
    val titelDe: String,
    val titelEn: String,
    val sprachen: Set<Sprache>,
    val hoster: List<String>,
) {
    /** Kürzel wie "S01E05" oder "Film 2". */
    val kuerzel get() = if (istFilm) "Film $nummer" else "S%02dE%02d".format(staffel, nummer)

    /** Lesbarer Titel; bei Filmen ist nur der englische gesetzt. */
    val titel get() = titelDe.ifBlank { titelEn }
}

/** Hoster-Links einer Folge: Sprache -> (Hostername -> Redirect-URL bei aniworld.to). */
data class FolgenLinks(val links: Map<Sprache, Map<String, String>>) {
    val sprachen get() = links.keys
    fun hoster(sprache: Sprache): List<String> = links[sprache]?.keys?.toList().orEmpty()
}
