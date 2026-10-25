package de.tobidervogel.aniworld.site

import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element

/**
 * Liest MegaKino, wie models/megakino/series.py und query_megakino() im Original.
 *
 * Die Domain wechselt oft; die aktuelle steht in einem öffentlichen Tracker. Ein Eintrag liegt
 * unter `/<Bereich>/<ID>-<Slug>.html`, Filme wie Serien. Eine Serienseite ist genau eine Staffel
 * („Tulsa King - 4 Staffel“) und listet alle Folgen samt Hostern auf einmal; eine Folge
 * adressiert die App wie das Original mit `#mkep=<Nummer>`. Alles ist deutsch.
 */
object MegaKinoParser {
    const val TRACKER = "https://raw.githubusercontent.com/Yezun-hikari/new-domain-check/refs/heads/main/monitors/megakino/domain.txt"

    /** Letzte bekannte Domain, falls der Tracker nicht erreichbar ist. */
    const val STANDARD = "megakino25.com"

    private val HOST = Regex("""^(?:www\.)?megakino[a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}$""", RegexOption.IGNORE_CASE)
    private val EINTRAG = Regex("""^(?:https?://([^/?#]+))?/([a-z0-9-]+)/(\d+)-([^/?#]+?)\.html""", RegexOption.IGNORE_CASE)
    private val FOLGE = Regex("""#mkep=(\d+)$""")
    private val STAFFEL = Regex("""^(.*?)\s+-\s+(?:(\d+)\.?\s*Staffel|Staffel\s*(\d+))\s*$""", RegexOption.IGNORE_CASE)

    /** Bereiche mit derselben Adressform, die keine Filme oder Serien sind. */
    private val KEIN_EINTRAG = setOf("collection", "film-nachrichten", "xfsearch", "tags", "user", "news")

    /** Oberbegriffe in der Genrezeile („Filme / Thriller“), die kein Genre sind. */
    private val KEIN_GENRE = setOf("filme", "serien", "kinofilme")

    fun istHost(host: String) = HOST.matches(host)

    /**
     * Domain aus der Antwort des Trackers. Nur Namen mit „megakino“ gelten: Der Tracker liegt in
     * einem fremden Repository, und die App soll sich nicht auf eine beliebige Seite umlenken lassen.
     */
    fun domain(text: String): String? {
        val d = text.trim().lowercase().removePrefix("https://").removePrefix("http://").substringBefore('/').removePrefix("www.")
        return d.takeIf { istHost(it) }
    }

    /** Ist das eine Eintragsadresse von MegaKino (gleich welche Domain)? */
    fun istEintrag(url: String): Boolean = teile(url) != null

    private fun teile(url: String): List<String>? {
        val m = EINTRAG.find(url.trim()) ?: return null
        val host = m.groupValues[1]
        if (host.isNotEmpty() && !istHost(host)) return null
        if (m.groupValues[2].lowercase() in KEIN_EINTRAG) return null
        return m.groupValues
    }

    /**
     * Adresse eines Eintrags ohne Folgenmarke. Eine Domain in der Adresse bleibt stehen, damit
     * gespeicherte Adressen gleich bleiben; nur relative Adressen bekommen `basis`.
     */
    fun serienUrl(url: String, basis: String): String? = teile(url)?.let {
        val host = it[1].lowercase().removePrefix("www.")
        "${if (host.isEmpty()) basis else "https://$host"}/${it[2]}/${it[3]}-${it[4]}.html"
    }

    fun folgenUrl(serienUrl: String, folge: Int) = "$serienUrl#mkep=$folge"

    fun folge(url: String): Int? = FOLGE.find(url)?.groupValues?.get(1)?.toIntOrNull()

    private fun absolut(p: String?, basis: String): String? {
        val s = p?.trim().orEmpty()
        return when {
            s.isEmpty() || s.startsWith("data:") || "no-img" in s -> null
            s.startsWith("//") -> "https:$s"
            s.startsWith("http") -> s
            else -> "$basis/" + s.trimStart('/')
        }
    }

    private fun bild(img: Element?, basis: String): String? =
        img?.let { i -> listOf("data-src", "data-original", "src").firstNotNullOfOrNull { absolut(i.attr(it), basis) } }

    /** „Tulsa King - 4 Staffel“ → („Tulsa King“, 4); ohne Staffelangabe null. */
    fun staffelAusTitel(titel: String): Pair<String, Int>? {
        val m = STAFFEL.find(titel.trim()) ?: return null
        val nr = (m.groupValues[2].ifEmpty { m.groupValues[3] }).toIntOrNull() ?: return null
        return m.groupValues[1].trim() to nr
    }

    // ---------------------------------------------------------------- Listen

    /**
     * Posterkarten (`a.poster`). `abListe`: erst ab `#dle-content` lesen. Davor steht auf jeder
     * Genreseite dieselbe Werbereihe, sonst sähe jedes Genre aus wie das vorige (Issue #317 im Original).
     */
    fun karten(html: String, basis: String, abListe: Boolean = false): List<Karte> {
        val doc = Jsoup.parse(html, basis)
        val wurzel: Element = if (abListe) doc.selectFirst("#dle-content") ?: doc else doc
        val ergebnis = LinkedHashMap<String, Karte>()
        for (a in wurzel.select("a.poster[href]")) {
            val url = serienUrl(a.attr("href"), basis) ?: continue
            if (url in ergebnis) continue
            val titel = a.selectFirst(".poster__title")?.text()?.trim().orEmpty()
                .ifEmpty { a.selectFirst("img")?.attr("alt")?.trim().orEmpty() }
            if (titel.isEmpty()) continue
            // Unter dem Titel stehen Land und Jahr, dann „Filme / Thriller“ oder „Serien / Drama“.
            val art = a.select("ul.poster__subtitle li").map { it.text().trim() }
                .firstOrNull { it.startsWith("Filme") || it.startsWith("Serien") }.orEmpty()
            ergebnis[url] = Karte(titel, url, bild(a.selectFirst("img"), basis), art)
        }
        return ergebnis.values.toList()
    }

    /** Genres aus der Seitenleiste („Genres“). */
    fun genres(html: String): List<Genre> {
        val doc = Jsoup.parse(html)
        val titel = doc.select("div.side-block__title").firstOrNull { it.text().trim().equals("Genres", ignoreCase = true) } ?: return emptyList()
        val liste = titel.parent()?.selectFirst("ul") ?: return emptyList()
        return liste.select("a[href]").mapNotNull { a ->
            val slug = a.attr("href").trim().trim('/').takeIf { it.isNotEmpty() && '/' !in it && '?' !in it } ?: return@mapNotNull null
            val name = a.text().trim().ifEmpty { slug }
            Genre(name, slug)
        }.distinctBy { it.slug }
    }

    /** Gibt es nach Seite `seite` noch eine Seite (`/<slug>/page/<n>/`)? */
    fun weitereSeite(html: String, seite: Int): Boolean = "/page/${seite + 1}/" in html

    // ---------------------------------------------------------------- Eintrag

    private fun istSerie(doc: Document) = doc.selectFirst("select.se-select") != null

    fun istSerie(html: String) = istSerie(Jsoup.parse(html))

    /**
     * Film → „Staffel 0“ mit genau einer Folge (wie Kinox); Serie → die eine Staffel, deren Nummer im
     * Titel steht. Der Titel verliert den Staffelzusatz, damit alle Staffeln im selben Ordner landen.
     */
    fun eintrag(html: String, url: String, basis: String): Serie {
        val doc = Jsoup.parse(html, basis)
        val roh = (doc.selectFirst("h1[itemprop=name]")?.text() ?: doc.selectFirst("meta[itemprop=name]")?.attr("content")
            ?: doc.selectFirst("meta[property=og:title]")?.attr("content")).orEmpty().trim()
        val serie = istSerie(doc)
        val st = if (serie) staffelAusTitel(roh) else null
        val titel = st?.first ?: roh
        val jahr = doc.selectFirst("span[itemprop=dateCreated]")?.text()?.let { Regex("""\d{4}""").find(it)?.value }
        val genres = doc.selectFirst("div.pmovie__genres")?.text()?.split('/')?.map { it.trim() }
            ?.filter { it.isNotEmpty() && it.lowercase() !in KEIN_GENRE }.orEmpty()
        val cover = bild(doc.selectFirst("img[itemprop=image]"), basis)
            ?: absolut(doc.selectFirst("meta[itemprop=image]")?.attr("content"), basis)
        val beschreibung = doc.selectFirst("div.page__text[itemprop=description], div[itemprop=description]")?.text()?.trim().orEmpty()
        val staffeln = if (serie) listOf(StaffelRef(st?.second ?: 1, url, istFilme = false))
        else listOf(StaffelRef(0, url, istFilme = true))
        return Serie(url, titel.ifEmpty { url.substringAfterLast('/').substringBefore(".html") }, beschreibung, genres, jahr, cover, null, null, staffeln)
    }

    fun folgen(html: String, url: String, basis: String, ref: StaffelRef): List<Folge> {
        val doc = Jsoup.parse(html, basis)
        if (!istSerie(doc)) {
            val s = eintrag(html, url, basis)
            val hoster = filmHoster(doc).keys.toList()
            return listOf(Folge(url, 1, 0, true, s.jahre?.let { "${s.titel} ($it)" } ?: s.titel, "", sortedSetOf(Sprache.DE_DUB), hoster))
        }
        return folgenListe(doc).mapIndexed { i, (id, _) ->
            val nr = i + 1
            Folge(folgenUrl(url, nr), nr, ref.nummer, false, "", "", sortedSetOf(Sprache.DE_DUB), serienHoster(doc, id).keys.toList())
        }
    }

    /** `<option value="ep1">Episode 1</option>` aus der Folgenauswahl. */
    private fun folgenListe(doc: Document): List<Pair<String, String>> =
        doc.selectFirst("select.se-select")?.select("option[value]")?.map { it.attr("value").trim() to it.text().trim() }
            ?.filter { it.first.isNotEmpty() }.orEmpty()

    private fun serienHoster(doc: Document, id: String): Map<String, String> {
        val auswahl = doc.select("select.mr-select").firstOrNull { it.id() == id } ?: return emptyMap()
        val hoster = LinkedHashMap<String, String>()
        for (o in auswahl.select("option[value]")) {
            val url = o.attr("value").trim().takeIf { it.startsWith("http") } ?: continue
            val name = HosterNamen.ausAdresse(url) ?: o.text().trim().takeIf { it.isNotEmpty() } ?: continue
            hoster.putIfAbsent(name, url)
        }
        return hoster
    }

    /** Filmseite: ein iframe je Reiter in `div.tabs-block__content` (src oder data-src). */
    private fun filmHoster(doc: Document): Map<String, String> {
        val hoster = LinkedHashMap<String, String>()
        for (iframe in doc.select("div.tabs-block__content iframe")) {
            val roh = iframe.attr("src").ifEmpty { iframe.attr("data-src") }.trim()
            val url = if (roh.startsWith("//")) "https:$roh" else roh
            if (!url.startsWith("http") || "youtube." in url || "youtu.be" in url) continue
            hoster.putIfAbsent(HosterNamen.ausAdresse(url) ?: continue, url)
        }
        return hoster
    }

    /** Hoster der Folge (Serie) oder des Films. Die Links zeigen schon direkt auf den Hoster. */
    fun links(html: String, folgenUrl: String): FolgenLinks {
        val doc = Jsoup.parse(html)
        val hoster = if (istSerie(doc)) {
            val nr = folge(folgenUrl) ?: 1
            folgenListe(doc).getOrNull(nr - 1)?.let { serienHoster(doc, it.first) }.orEmpty()
        } else filmHoster(doc)
        return FolgenLinks(if (hoster.isEmpty()) emptyMap() else mapOf(Sprache.DE_DUB to hoster))
    }

    /** Antwortet die Seite noch mit der Weiche zum Token statt mit Inhalt? */
    fun brauchtToken(html: String) = "location.replace" in html || "yg=token" in html
}
