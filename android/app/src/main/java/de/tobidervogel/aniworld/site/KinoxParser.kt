package de.tobidervogel.aniworld.site

import org.json.JSONObject
import org.jsoup.Jsoup
import org.jsoup.nodes.Element

/**
 * Liest kinox.to, wie models/kinox/series.py und query_kinox() im Original. Kinox führt Filme und
 * Serien unter derselben Adressform `/Stream/<Slug>.html`; eine Serie erkennt man an der
 * Staffelauswahl. Jeder Eintrag hat genau eine Sprache (Flagge 1 = Deutsch, 2 = Englisch).
 */
object KinoxParser {
    const val BASIS = "https://kinox.to"
    val HOSTS = setOf("kinox.to", "kinos.to", "kinoz.to", "kinox.am", "kinox.click")
    private val EINTRAG = Regex("""^(?:https?://[^/]+)?/Stream/([^/.?#]+)(?:\.html)?""")

    /** Genres für Erwachsene zeigt die App nicht an. */
    private val AUSGEBLENDET = setOf("adult", "erotik", "porn")

    fun serienUrl(url: String): String? {
        val u = url.trim()
        if (Regex("""^https?://""").containsMatchIn(u) && u.substringAfter("://").substringBefore('/').removePrefix("www.").lowercase() !in HOSTS) return null
        return EINTRAG.find(u)?.let { "$BASIS/Stream/${it.groupValues[1]}.html" }
    }

    fun slug(url: String): String? = EINTRAG.find(url.trim())?.groupValues?.get(1)

    /** Folge einer Serie: dieselbe Seite mit `?s=<Staffel>&e=<Folge>`, wie kinox_episode_url(). */
    fun folgenUrl(serienUrl: String, staffel: Int, folge: Int) = "$serienUrl?s=$staffel&e=$folge"

    fun staffelUndFolge(url: String): Pair<Int, Int>? {
        val s = Regex("""[?&]s=(\d+)""").find(url)?.groupValues?.get(1)?.toIntOrNull() ?: return null
        val e = Regex("""[?&]e=(\d+)""").find(url)?.groupValues?.get(1)?.toIntOrNull() ?: return null
        return s to e
    }

    private fun absolut(p: String?): String? {
        val s = p?.trim().orEmpty()
        return when {
            s.isEmpty() || s.startsWith("data:") -> null
            s.startsWith("//") -> "https:$s"
            s.startsWith("http") -> s
            else -> "$BASIS/" + s.trimStart('/')
        }
    }

    private fun ausFlagge(flagge: String?): Sprache = if (flagge == "2") Sprache.EN_DUB else Sprache.DE_DUB

    private fun flagge(e: Element?): String? =
        e?.selectFirst("img[src*=/gr/sys/lng/]")?.attr("src")?.let { Regex("""/lng/(\d+)\.png""").find(it)?.groupValues?.get(1) }

    /**
     * Listen (Kinofilme, Suche, Genre): je Eintrag ein Kasten mit Kopfzeile, Bild, Beschreibung
     * und Flagge. Englische Einträge tragen „Englisch“ als Zusatz, weil Kinox Filme in beiden
     * Sprachen als getrennte Einträge führt.
     */
    fun karten(html: String): List<Karte> {
        val doc = Jsoup.parse(html, BASIS)
        val ergebnis = LinkedHashMap<String, Karte>()
        for (a in doc.select("div.Headlne a[href*=/Stream/]")) {
            val url = serienUrl(a.attr("href")) ?: continue
            if (url in ergebnis) continue
            val titel = a.attr("title").trim().ifEmpty { a.text().trim() }.replace(Regex("""\s*\(\d{4}\)\s*$"""), "")
            if (titel.isEmpty()) continue
            // Der Kasten um Kopf und Inhalt ist das Element mit dem onclick.
            val kasten = a.parents().firstOrNull { it.hasAttr("onclick") } ?: a.parent()?.parent()?.parent()
            val cover = absolut(kasten?.selectFirst("div.Thumb img")?.attr("src"))
            val englisch = ausFlagge(flagge(kasten)) == Sprache.EN_DUB
            ergebnis[url] = Karte(titel, url, cover, if (englisch) "Englisch" else "")
        }
        return ergebnis.values.toList()
    }

    /** Genres aus dem Menü; der Name steht vor der Anzahl in einem <span>. */
    fun genres(html: String): List<Genre> =
        Jsoup.parse(html, BASIS).select("a[href*=/Genre/]").mapNotNull { a ->
            val slug = a.attr("href").substringAfter("/Genre/").substringBefore('/').substringBefore('?').trim()
            val name = a.clone().apply { select("span").remove() }.text().trim().ifEmpty { slug }
            if (slug.isEmpty() || slug.lowercase() in AUSGEBLENDET || name.lowercase() in AUSGEBLENDET) null else Genre(name, slug)
        }.distinctBy { it.slug }

    /** Parameter der Genre-Liste (`input#ListParams`), die per POST /aGET/List/ nachgeladen wird. */
    fun listenParameter(html: String): JSONObject? =
        Jsoup.parse(html).selectFirst("input#ListParams")?.attr("value")?.let { runCatching { JSONObject(it) }.getOrNull() }

    /** Antwort von /aGET/List/: JSON mit dem HTML der Karten unter „Content“. */
    fun listenInhalt(json: String): String = runCatching { JSONObject(json).optString("Content") }.getOrDefault("")

    // ---------------------------------------------------------------- Eintrag

    private fun staffelAuswahl(doc: org.jsoup.nodes.Document) = doc.selectFirst("select#SeasonSelection")

    fun istSerie(html: String) = staffelAuswahl(Jsoup.parse(html)) != null

    fun serieId(html: String): String? = Jsoup.parse(html).selectFirst("input#EntryID")?.attr("value")?.trim()?.ifEmpty { null }

    fun eintrag(html: String, url: String): Serie {
        val doc = Jsoup.parse(html, BASIS)
        val og = doc.selectFirst("meta[property=og:title]")?.attr("content").orEmpty()
        // og:title lautet „Titel (Jahr) Stream online anschauen …“.
        val titel = og.split(Regex("""\bStream\b""")).first().replace(Regex("""\s*\(\d{4}\)\s*$"""), "").trim()
            .ifEmpty { slug(url).orEmpty().replace('_', ' ') }
        val jahr = Regex("""\((\d{4})\)""").find(og)?.groupValues?.get(1)
        val cover = absolut(doc.selectFirst("img[src^=/statics/]")?.attr("src"))
        val beschreibung = doc.selectFirst("div.Descriptore")?.text()?.trim().orEmpty()
        val genres = doc.select("li[title=Genre]").firstOrNull()?.text()?.split(',')?.map { it.trim() }?.filter { it.isNotEmpty() }.orEmpty()
        val auswahl = staffelAuswahl(doc)
        val staffeln = if (auswahl == null) {
            // Ein Film: wie bei Filmo eine „Staffel“ mit genau einer Folge.
            listOf(StaffelRef(0, url, istFilme = true))
        } else {
            auswahl.select("option[value]").mapNotNull { o -> o.attr("value").toIntOrNull() }.distinct().sorted()
                .map { StaffelRef(it, "$url?s=$it", istFilme = false) }
        }
        return Serie(url, titel, beschreibung, genres, jahr, cover, null, null, staffeln)
    }

    fun sprache(html: String): Sprache = ausFlagge(flagge(Jsoup.parse(html).selectFirst(".Flag, [class*=Flag]")))

    /** Folgen einer Staffel aus `<option value="<Staffel>" rel="1,2,3">`. Titel kennt Kinox nicht. */
    fun folgen(html: String, serienUrl: String, ref: StaffelRef): List<Folge> {
        val doc = Jsoup.parse(html, BASIS)
        val sp = sprache(html)
        if (ref.istFilme) {
            val s = eintrag(html, serienUrl)
            return listOf(Folge(serienUrl, 1, 0, true, s.jahre?.let { "${s.titel} ($it)" } ?: s.titel, "", sortedSetOf(sp), emptyList()))
        }
        val rel = staffelAuswahl(doc)?.selectFirst("option[value=${ref.nummer}]")?.attr("rel").orEmpty()
        return rel.split(',').mapNotNull { it.trim().toIntOrNull() }.distinct().sorted().map { e ->
            Folge(folgenUrl(serienUrl, ref.nummer, e), e, ref.nummer, false, "", "", sortedSetOf(sp), emptyList())
        }
    }

    /**
     * Spiegel aus einer Hosterliste (Filmseite oder /aGET/MirrorByEpisode): Name und das
     * `rel`, mit dem /aGET/Mirror/ die Weiterleitung liefert. „Dood.to“ wird zu „Dood“ gekürzt,
     * damit der Name zu den Extraktoren passt.
     */
    fun spiegel(html: String, sprache: Sprache): FolgenLinks {
        val hoster = LinkedHashMap<String, String>()
        for (li in Jsoup.parse(html).select("li.MirBtn[rel]")) {
            val name = li.selectFirst("div.Named")?.text()?.trim()?.substringBefore('.')?.ifEmpty { null } ?: continue
            hoster.putIfAbsent(name, li.attr("rel").trim())
        }
        return FolgenLinks(if (hoster.isEmpty()) emptyMap() else mapOf(sprache to hoster))
    }

    /** /aGET/Mirror/<rel> antwortet mit JSON; im iframe unter „Stream“ steht die Weiterleitung. */
    fun weiterleitung(json: String): String? {
        val iframe = runCatching { JSONObject(json).optString("Stream") }.getOrNull().orEmpty()
        val src = Regex("""src="([^"\s]+)"""").find(iframe)?.groupValues?.get(1)?.replace("\\/", "/") ?: return null
        return absolut(src)
    }
}
