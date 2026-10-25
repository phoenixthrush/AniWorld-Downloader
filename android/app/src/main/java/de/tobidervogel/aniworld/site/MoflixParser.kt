package de.tobidervogel.aniworld.site

import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener

/**
 * Liest Moflix, wie models/moflix_stream/ und query_moflix() im Original. Die Seite ist eine
 * Web-App: Die Startseite bringt ihre Reihen als `window.bootstrapData` mit, alles andere
 * kommt als JSON von /api/v1. Adressen: `/titles/<id>` und `/titles/<id>/season/<s>/episodes/<e>`.
 * Alles ist deutsch; die Hoster heißen nur „Mirror 1“, „Mirror 2“, ihr Name kommt aus der Adresse.
 */
object MoflixParser {
    const val BASIS = "https://moflix-stream.xyz"
    private val TITEL = Regex(
        """^(?:https?://(?:www\.)?moflix-stream\.xyz)?/titles/(\d+)(?:/(?!season(?:[/?]|$)|episodes(?:[/?]|$))[^/?#]+)?(?:/season/(\d+)(?:/episodes/(\d+))?)?/?(?:\?[^#]*)?(?:#.*)?$""",
        RegexOption.IGNORE_CASE,
    )

    /** Reihen der Startseite (Kanal-Slug → Titel der Reihe in der App). */
    val REIHEN = listOf("trending-movies", "top-10-movies-serien", "now-playing")

    private fun teile(url: String): MatchResult? {
        val u = url.trim()
        if (u.startsWith("http", ignoreCase = true) && !Regex("""^https?://(?:www\.)?moflix-stream\.xyz/""", RegexOption.IGNORE_CASE).containsMatchIn(u)) return null
        return TITEL.find(u)
    }

    fun titelId(url: String): String? = teile(url)?.groupValues?.get(1)

    fun serienUrl(url: String): String? = titelId(url)?.let { "$BASIS/titles/$it" }

    fun folgenUrl(id: String, staffel: Int, folge: Int) = "$BASIS/titles/$id/season/$staffel/episodes/$folge"

    /** Staffel und Folge aus einer Folgenadresse; null bei einem Film oder der Titelseite. */
    fun staffelUndFolge(url: String): Pair<Int, Int>? {
        val m = teile(url) ?: return null
        val s = m.groupValues[2].toIntOrNull() ?: return null
        val e = m.groupValues[3].toIntOrNull() ?: return null
        return s to e
    }

    private fun bild(p: String?): String? {
        val s = p?.trim().orEmpty()
        return when {
            s.isEmpty() || s == "null" -> null
            s.startsWith("http") -> s
            else -> "$BASIS/" + s.trimStart('/')
        }
    }

    /** `window.bootstrapData = {…}` aus dem HTML; liest genau ein JSON-Objekt, egal was danach kommt. */
    fun bootstrap(html: String): JSONObject? {
        val m = Regex("""window\.bootstrapData\s*=\s*""").find(html) ?: return null
        return runCatching { JSONTokener(html.substring(m.range.last + 1)).nextValue() as? JSONObject }.getOrNull()
    }

    fun csrf(html: String): String? = bootstrap(html)?.optString("csrf_token")?.takeIf { it.isNotBlank() }

    /** Die Antwort der API als Objekt; null, wenn statt JSON eine Seite kam. */
    fun json(text: String): JSONObject? {
        val t = text.trimStart()
        if (!t.startsWith("{")) return null
        return runCatching { JSONObject(t) }.getOrNull()
    }

    private fun JSONArray?.objekte(): List<JSONObject> =
        if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

    /** Ein Titel aus einer Liste; Personen (Suche) und Einträge ohne Zahlen-ID fallen weg. */
    private fun karte(t: JSONObject): Karte? {
        if (t.optString("model_type", "title") != "title") return null
        val id = t.opt("id")?.toString()?.takeIf { it.matches(Regex("""\d+""")) } ?: return null
        val name = t.optString("name").trim().ifEmpty { return null }
        val jahr = t.optInt("year", 0).takeIf { it > 0 }
        val art = if (t.optBoolean("is_series")) "Serie" else "Film"
        return Karte(name, "$BASIS/titles/$id", bild(t.optString("poster")), listOfNotNull(art, jahr?.toString()).joinToString(" · "))
    }

    fun karten(liste: JSONArray?): List<Karte> = liste.objekte().mapNotNull { karte(it) }.distinctBy { it.url }

    /** Reihen der Startseite aus `loaders.channelPage`, nur die mit Inhalt; Schlüssel ist der Kanal-Slug. */
    fun startReihen(html: String): Map<String, List<Karte>> {
        val kanaele = bootstrap(html)?.optJSONObject("loaders")?.optJSONObject("channelPage")?.optJSONObject("channel")
            ?.optJSONObject("content")?.optJSONArray("data")
        val ergebnis = LinkedHashMap<String, List<Karte>>()
        for (k in kanaele.objekte()) {
            val karten = karten(k.optJSONObject("content")?.optJSONArray("data"))
            if (karten.isNotEmpty()) ergebnis[k.optString("slug")] = karten
        }
        return ergebnis
    }

    /** Genres, die auf der Startseite vorkommen; Ersatz, wenn die Genre-Liste der API nicht kommt. */
    fun genresAusStart(html: String): List<Genre> {
        val kanaele = bootstrap(html)?.optJSONObject("loaders")?.optJSONObject("channelPage")?.optJSONObject("channel")
            ?.optJSONObject("content")?.optJSONArray("data")
        return kanaele.objekte().flatMap { k -> k.optJSONObject("content")?.optJSONArray("data").objekte() }
            .flatMap { it.optJSONArray("genres").objekte() }
            .mapNotNull { g -> g.optString("name").takeIf { it.isNotBlank() }?.let { Genre(g.optString("display_name").ifBlank { it }, it) } }
            .distinctBy { it.slug }.sortedBy { it.name }
    }

    /** /api/v1/moflix/recommendations?route=genre…: `genres` ist eine Liste von Namen. */
    fun genres(json: JSONObject): List<Genre> {
        val g = json.optJSONArray("genres") ?: return emptyList()
        return (0 until g.length()).mapNotNull { g.optString(it).trim().takeIf { n -> n.isNotEmpty() } }
            .map { Genre(it.replaceFirstChar { c -> c.uppercase() }, it) }.distinctBy { it.slug }
    }

    /** /api/v1/search/<text>: Treffer unter `results`, gemischt mit Personen. */
    fun suche(json: JSONObject): List<Treffer> =
        karten(json.optJSONArray("results")).map { Treffer(it.titel, it.url, it.genre, it.cover) }

    // ---------------------------------------------------------------- Titel

    fun istSerie(titel: JSONObject) = titel.optBoolean("is_series") || titel.optString("type") == "series"

    /** /api/v1/titles/<id>: `title` und `seasons.data[].number`. Ein Film wird „Staffel 0“ mit einer Folge. */
    fun serie(json: JSONObject, url: String): Serie {
        val t = json.optJSONObject("title") ?: JSONObject()
        val name = t.optString("name").trim().ifEmpty { "Moflix ${titelId(url).orEmpty()}" }
        val genres = t.optJSONArray("genres").objekte().mapNotNull { g ->
            g.optString("display_name").ifBlank { g.optString("name") }.trim().takeIf { it.isNotEmpty() }
        }
        val jahr = t.optInt("year", 0).takeIf { it > 0 }?.toString()
        val staffeln = if (!istSerie(t)) listOf(StaffelRef(0, url, istFilme = true)) else {
            val nummern = json.optJSONObject("seasons")?.optJSONArray("data").objekte()
                .map { it.optInt("number", -1) }.filter { it >= 0 }.distinct().sorted()
            nummern.ifEmpty { listOf(1) }.map { StaffelRef(it, url, istFilme = false, bezeichnung = if (it == 0) "Specials" else null) }
        }
        val imdb = t.optString("imdb_id").takeIf { it.startsWith("tt") }
        return Serie(url, name, t.optString("description").trim().takeUnless { it == "null" }.orEmpty(), genres, jahr,
            bild(t.optString("poster")), null, imdb, staffeln)
    }

    /** Nur der Film selbst als einzige „Folge“. */
    fun film(json: JSONObject, url: String): Folge {
        val s = serie(json, url)
        return Folge(url, 1, 0, true, s.jahre?.let { "${s.titel} ($it)" } ?: s.titel, "", sortedSetOf(Sprache.DE_DUB), emptyList())
    }

    /**
     * /api/v1/titles/<id>/seasons/<n>: `episodes.data[]` mit `episode_number` und `name`.
     * Gibt auch zurück, ob eine weitere Seite folgt (das Original blättert, solange next_page gesetzt ist).
     */
    fun folgen(json: JSONObject, id: String, staffel: Int): Pair<List<Folge>, Boolean> {
        val seite = json.optJSONObject("episodes") ?: return emptyList<Folge>() to false
        val folgen = seite.optJSONArray("data").objekte().mapNotNull { e ->
            val nr = e.optInt("episode_number", 0).takeIf { it > 0 } ?: return@mapNotNull null
            val name = e.optString("name").trim().takeUnless { it == "null" }.orEmpty()
            Folge(folgenUrl(id, staffel, nr), nr, staffel, false, name, "", sortedSetOf(Sprache.DE_DUB), emptyList())
        }
        val weiter = !seite.isNull("next_page")
        return folgen to weiter
    }

    /**
     * Hoster aus `videos[]` (beim Film im Titel, bei einer Folge unter `episode`). Nur https-Adressen,
     * benannt nach ihrer Domain wie host_to_provider() im Original.
     */
    fun links(json: JSONObject): FolgenLinks {
        val quelle = json.optJSONObject("episode") ?: json.optJSONObject("title") ?: json
        val hoster = LinkedHashMap<String, String>()
        for (v in quelle.optJSONArray("videos").objekte()) {
            val src = v.optString("src").trim()
            if (!src.startsWith("https://")) continue
            val name = HosterNamen.ausAdresse(src) ?: continue
            hoster.putIfAbsent(name, src)
        }
        return FolgenLinks(if (hoster.isEmpty()) emptyMap() else mapOf(Sprache.DE_DUB to hoster))
    }
}
