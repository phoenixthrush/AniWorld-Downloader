package de.tobidervogel.aniworld.site

import org.jsoup.Jsoup
import org.jsoup.nodes.Element

/**
 * Liest Burning Series (bs.cine.to und Spiegel), wie models/burningseries/series.py im Original.
 *
 * Aufbau der Seite:
 * - `/andere-serien`: alle Serien, nach Genre gruppiert (dient als Suchindex)
 * - `/serie/<slug>`: Serie mit Beschreibung, Genres, Jahren, Cover und Staffelliste
 * - `/serie/<slug>/<staffel>/<sprache>`: Folgentabelle einer Staffel samt Hostern je Folge
 * - `/serie/<slug>/<staffel>/<folge>/<sprache>/<Hoster>`: Player mit `window.open(…)` zum Hoster
 */
object BurningSeriesParser {
    const val BASIS = "https://bs.cine.to"
    /** Domains, die noch den Player mit window.open ausliefern (bs.cine.to hat ihn nicht mehr). */
    val STREAM_DOMAINS = listOf("https://burning-series.io", "https://burning-series.net")
    val HOSTS = setOf("bs.cine.to", "burningseries.ac", "burningseries.cx", "burning-series.io", "burning-series.net", "bs.to")

    /** Sprachkürzel der Seite; Untertitel-Fassungen bietet sie nicht an. */
    val SPRACHEN = mapOf("de" to Sprache.DE_DUB, "en" to Sprache.EN_DUB)

    private val SERIE = Regex("""^(?:https?://[^/]+)?/?serie/([^/?#]+)""")
    private val FOLGE = Regex("""^(?:https?://[^/]+)?/?serie/([^/?#]+)/(\d+)/([^/?#]+)""")

    fun serienUrl(url: String): String? {
        val u = url.trim()
        if (Regex("""^https?://""").containsMatchIn(u) && hostVon(u) !in HOSTS) return null
        return SERIE.find(u)?.let { "$BASIS/serie/${it.groupValues[1]}" }
    }

    private fun hostVon(url: String) = url.substringAfter("://").substringBefore('/').removePrefix("www.").lowercase()

    /** Folge ohne Sprache: `…/serie/<slug>/<staffel>/<nr-titel>`. */
    fun folgenUrl(url: String): String? =
        FOLGE.find(url.trim())?.let { "$BASIS/serie/${it.groupValues[1]}/${it.groupValues[2]}/${it.groupValues[3]}" }

    private fun absolut(p: String?): String? {
        val s = p?.trim().orEmpty()
        return when {
            s.isEmpty() || s.startsWith("data:") -> null
            s.startsWith("//") -> "https:$s"
            s.startsWith("http") -> s
            else -> "$BASIS/" + s.trimStart('/')
        }
    }

    // ---------------------------------------------------------------- Index und Startseite

    /** Index nach Genre: Name → Serien. Dient für Suche und Genre-Listen. */
    fun index(html: String): Map<String, List<Karte>> {
        val doc = Jsoup.parse(html, BASIS)
        val ergebnis = LinkedHashMap<String, List<Karte>>()
        for (g in doc.select("div.genre")) {
            val name = g.selectFirst("span strong")?.text()?.trim().orEmpty()
            if (name.isEmpty()) continue
            ergebnis[name] = g.select("ul li a[href]").mapNotNull { a ->
                val url = serienUrl(a.attr("href")) ?: return@mapNotNull null
                val titel = a.text().trim().ifEmpty { a.attr("title").trim() }
                if (titel.isEmpty()) null else Karte(titel, url, null, name)
            }.distinctBy { it.url }
        }
        return ergebnis
    }

    /** Suche im Index wie query_burningseries(): Teilstring in Titel oder Slug, höchstens 30 Treffer. */
    fun suche(index: Map<String, List<Karte>>, text: String): List<Karte> {
        val t = text.trim().lowercase()
        if (t.isEmpty()) return emptyList()
        return index.values.asSequence().flatten().distinctBy { it.url }
            .filter { t in it.titel.lowercase() || t in it.url.substringAfterLast('/').lowercase().replace('-', ' ') || t in it.url.lowercase() }
            .take(30).toList()
    }

    /** „Neueste Serien“ der Startseite (ohne Cover; die holt [BurningSeries] einzeln nach). */
    fun neueSerien(html: String): List<Karte> =
        Jsoup.parse(html, BASIS).select("section#newest_series li a[href]").mapNotNull { a ->
            val url = serienUrl(a.attr("href")) ?: return@mapNotNull null
            Karte(a.text().trim(), url, null)
        }.filter { it.titel.isNotEmpty() }.distinctBy { it.url }

    /** „Neueste Episoden“: Titel, Staffel/Folge aus „S01 E04“, Sprache aus der Flagge. */
    fun neueFolgen(html: String): List<NeueFolge> =
        Jsoup.parse(html, BASIS).select("section#newest_episodes li").mapNotNull { li ->
            val a = li.selectFirst("a.title[href]") ?: return@mapNotNull null
            val m = FOLGE.find(a.attr("href")) ?: return@mapNotNull null
            val info = li.selectFirst("div.info")?.text().orEmpty()
            val se = Regex("""S(\d+)\s*E(\d+)""").find(info)
            val sprache = li.select("i.flag").mapNotNull { f ->
                f.classNames().firstOrNull { it.startsWith("flag-") }?.removePrefix("flag-")?.let { SPRACHEN[it] }
            }
            NeueFolge(
                titel = a.text().trim(),
                url = "$BASIS/serie/${m.groupValues[1]}/${m.groupValues[2]}/${m.groupValues[3]}",
                staffel = se?.groupValues?.get(1)?.toIntOrNull() ?: m.groupValues[2].toInt(),
                folge = se?.groupValues?.get(2)?.toIntOrNull() ?: Regex("""^(\d+)""").find(m.groupValues[3])?.groupValues?.get(1)?.toIntOrNull() ?: 1,
                datum = "",
                sprachen = sprache,
            )
        }

    /** Cover einer Serienseite (/public/images/cover/<id>.jpg). */
    fun cover(html: String): String? =
        absolut(Jsoup.parse(html, BASIS).selectFirst("#sp_right img[src], img[src*=/cover/]")?.attr("src"))

    // ---------------------------------------------------------------- Serie und Staffel

    fun serie(html: String, url: String): Serie {
        val doc = Jsoup.parse(html, BASIS)
        val links = doc.selectFirst("#sp_left")
        // Die Überschrift trägt „Staffel 1“ als <small>; das gehört nicht zum Titel.
        val h2 = links?.selectFirst("h2")?.clone()?.apply { select("small").remove() }
        val titel = h2?.text()?.trim().orEmpty().ifEmpty { url.substringAfterLast('/').replace('-', ' ') }
        val beschreibung = links?.selectFirst("p")?.text()?.trim().orEmpty()
        val infos = doc.select("div.infos > div")
        fun feld(name: String): Element? = infos.firstOrNull { it.selectFirst("span")?.text()?.trim() == name }?.selectFirst("p")
        val genres = feld("Genres")?.select("span")?.map { it.text().trim().trimEnd(',') }?.filter { it.isNotEmpty() }.orEmpty()
        val jahre = feld("Produktionsjahre")?.text()?.trim()?.replace(Regex("""\s*-\s*"""), "–")?.ifEmpty { null }
        val staffeln = doc.select("div.seasons li a[href]").mapNotNull { a ->
            val m = Regex("""serie/[^/]+/(\d+)""").find(a.attr("href")) ?: return@mapNotNull null
            val nr = m.groupValues[1].toInt()
            // „Specials“ ist Staffel 0; die Seite führt dort Sonderfolgen, keine Filme.
            StaffelRef(nr, "$url/$nr", istFilme = false, bezeichnung = a.text().trim().takeIf { nr == 0 && it.isNotEmpty() })
        }.distinctBy { it.nummer }.sortedWith(compareBy({ it.nummer == 0 }, { it.nummer }))
        return Serie(
            url = url,
            titel = titel,
            beschreibung = beschreibung,
            genres = genres,
            jahre = jahre,
            cover = cover(html),
            fsk = null,
            imdb = null,
            staffeln = staffeln,
        )
    }

    /** Eine Zeile der Folgentabelle in einer Sprache. */
    data class Zeile(val folgenUrl: String, val nummer: Int, val titel: String, val hoster: Map<String, String>)

    /**
     * Folgentabelle einer Staffel in einer Sprache; die Hoster stehen gleich mit in der Zeile.
     * Fehlt eine Sprache, zeigt die Seite eine andere an; solche Zeilen fallen über das Kürzel
     * am Ende der Adresse heraus.
     */
    fun staffel(html: String, sprache: String): List<Zeile> {
        val doc = Jsoup.parse(html, BASIS)
        return doc.select("table.episodes tr").mapNotNull { tr ->
            val a = tr.selectFirst("td a[href]") ?: return@mapNotNull null
            if (!a.attr("href").trimEnd('/').endsWith("/$sprache")) return@mapNotNull null
            val folge = folgenUrl(a.attr("href")) ?: return@mapNotNull null
            val nummer = a.text().trim().toIntOrNull()
                ?: Regex("""/(\d+)-""").find(folge)?.groupValues?.get(1)?.toIntOrNull() ?: return@mapNotNull null
            val titel = tr.selectFirst("strong")?.text()?.trim().orEmpty()
            val hoster = LinkedHashMap<String, String>()
            for (h in tr.select("a[href] i.hoster")) {
                val link = h.parent() ?: continue
                val name = link.attr("title").trim().ifEmpty { h.classNames().firstOrNull { it != "hoster" }.orEmpty() }
                val pfad = link.attr("href").trim().trimStart('/')
                if (name.isNotEmpty() && pfad.isNotEmpty()) hoster.putIfAbsent(name, pfad)
            }
            Zeile(folge, nummer, titel, hoster)
        }.distinctBy { it.folgenUrl }
    }

    /**
     * Folgen einer Staffel aus den Tabellen aller Sprachen: Eine Folge hat die Sprachen, in deren
     * Tabelle sie steht. Titel bevorzugt deutsch, der englische steht daneben.
     */
    fun folgen(ref: StaffelRef, tabellen: Map<Sprache, List<Zeile>>): List<Folge> {
        val alle = LinkedHashMap<String, MutableMap<Sprache, Zeile>>()
        for ((sprache, zeilen) in tabellen) for (z in zeilen) alle.getOrPut(z.folgenUrl) { LinkedHashMap() }[sprache] = z
        return alle.map { (url, proSprache) ->
            val de = proSprache[Sprache.DE_DUB]
            val en = proSprache[Sprache.EN_DUB]
            Folge(
                url = url,
                nummer = (de ?: en)!!.nummer,
                staffel = ref.nummer,
                istFilm = false,
                titelDe = de?.titel.orEmpty(),
                titelEn = en?.titel.orEmpty(),
                sprachen = proSprache.keys.toSortedSet(),
                hoster = proSprache.values.flatMap { it.hoster.keys }.distinct(),
            )
        }.sortedBy { it.nummer }
    }

    /** Hoster-Links einer Folge aus den Staffeltabellen; die Pfade sind relativ zur Seite. */
    fun links(folgenUrl: String, tabellen: Map<Sprache, List<Zeile>>): FolgenLinks =
        FolgenLinks(tabellen.mapNotNull { (sprache, zeilen) ->
            zeilen.firstOrNull { it.folgenUrl == folgenUrl }?.hoster?.takeIf { it.isNotEmpty() }?.let { sprache to it }
        }.toMap())

    /** Ziel von `window.open('…')` auf der Playerseite. */
    fun streamZiel(html: String, basis: String): String? {
        val roh = Regex("""window\.open\(\s*['"]([^'"]+)['"]""").find(html)?.groupValues?.get(1)?.trim() ?: return null
        return when {
            roh.startsWith("//") -> "https:$roh"
            roh.startsWith("/") -> basis + roh
            roh.startsWith("http") -> roh
            else -> null
        }
    }

    /** Hinweisseite „Streams nur per VPN“ statt Player (deutsche Netzsperre). */
    fun vpnHinweis(html: String): Boolean {
        val text = Jsoup.parse(html).text().lowercase()
        return "vpn" in text && listOf("burning series", "zensur", "gesperrt").any { it in text }
    }
}
