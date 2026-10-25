package de.tobidervogel.aniworld.site

import android.content.Context
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.Protokoll
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder

/** Ein Abschnitt zum Überspringen, in Millisekunden. */
data class Sprung(val art: String, val vonMs: Long, val bisMs: Long) {
    val name get() = if (art == "ed") "Ending" else "Opening"
}

/** Eine TV-Staffel bei MyAnimeList. */
data class MalStaffel(val id: Int, val folgen: Int?, val start: String)

/** Folge, für die Sprünge gesucht werden. Wird an den Player durchgereicht. */
data class Folgeninfo(val serieUrl: String, val serie: String, val staffel: Int, val folge: Int, val istFilm: Boolean)

/**
 * Opening und Ending über AniSkip, wie aniskip/ im Original: Titel bei Jikan (MyAnimeList)
 * suchen, die TV-Staffeln über Fortsetzungen einsammeln, dann pro Folge die Zeiten holen.
 */
object AniSkip {
    private const val JIKAN = "https://api.jikan.moe/v4"
    private const val ANISKIP = "https://api.aniskip.com/v1/skip-times"
    private const val MAX_ABRUFE = 15

    private fun normal(s: String) = s.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()

    // ------------------------------------------------------------ reine Funktionen (getestet)

    /** Suchtreffer von /anime?q=…: zuerst ein Titel, der genau passt, sonst der erste TV-Treffer. */
    fun ersterTreffer(json: String, titel: String): Int? {
        val daten = JSONObject(json).optJSONArray("data") ?: return null
        val gesucht = normal(titel)
        var erster: Int? = null
        for (i in 0 until daten.length()) {
            val o = daten.optJSONObject(i) ?: continue
            if (o.optString("type") != "TV") continue
            val id = o.optInt("mal_id").takeIf { it > 0 } ?: continue
            if (erster == null) erster = id
            val namen = buildList {
                add(o.optString("title")); add(o.optString("title_english"))
                o.optJSONArray("titles")?.let { t -> for (j in 0 until t.length()) add(t.optJSONObject(j)?.optString("title").orEmpty()) }
            }
            if (namen.any { it.isNotBlank() && normal(it) == gesucht }) return id
        }
        return erster
    }

    /** /anime/{id}/full → Staffel (nur wenn TV) und die verknüpften Fortsetzungen und Vorgänger. */
    fun eintrag(json: String): Pair<MalStaffel?, List<Int>> {
        val d = JSONObject(json).optJSONObject("data") ?: return null to emptyList()
        val id = d.optInt("mal_id")
        val staffel = if (d.optString("type") == "TV") {
            MalStaffel(id, d.optInt("episodes").takeIf { it > 0 }, d.optJSONObject("aired")?.optString("from").orEmpty())
        } else null
        val verwandt = ArrayList<Int>()
        val rel = d.optJSONArray("relations") ?: JSONArray()
        for (i in 0 until rel.length()) {
            val r = rel.optJSONObject(i) ?: continue
            if (r.optString("relation") !in setOf("Sequel", "Prequel")) continue
            val e = r.optJSONArray("entry") ?: continue
            for (j in 0 until e.length()) {
                val x = e.optJSONObject(j) ?: continue
                if (x.optString("type") == "anime") x.optInt("mal_id").takeIf { it > 0 }?.let { verwandt += it }
            }
        }
        return staffel to verwandt
    }

    /**
     * AniWorld-Staffel/Folge → MAL-Eintrag/Folge. Teilt MAL eine Staffel in Hälften, die AniWorld
     * zusammen führt, läuft die Folge in den nächsten Eintrag über (Folge 14 → Teil 2, Folge 1).
     */
    fun zuordnen(staffeln: List<MalStaffel>, staffel: Int, folge: Int): Pair<Int, Int>? {
        var i = staffel - 1
        if (i !in staffeln.indices || folge < 1) return null
        var f = folge
        while (true) {
            val n = staffeln[i].folgen ?: break
            if (f <= n || i + 1 > staffeln.lastIndex) break
            f -= n
            i++
        }
        return staffeln[i].id to f
    }

    /** Antwort von api.aniskip.com (v1, Felder von v2 werden auch verstanden). */
    fun spruenge(json: String): List<Sprung> {
        val o = JSONObject(json)
        if (!o.optBoolean("found")) return emptyList()
        val r = o.optJSONArray("results") ?: return emptyList()
        return (0 until r.length()).mapNotNull { i ->
            val e = r.optJSONObject(i) ?: return@mapNotNull null
            val iv = e.optJSONObject("interval") ?: return@mapNotNull null
            val von = iv.optDouble("start_time", iv.optDouble("startTime", Double.NaN))
            val bis = iv.optDouble("end_time", iv.optDouble("endTime", Double.NaN))
            val art = e.optString("skip_type").ifEmpty { e.optString("skipType") }
            if (von.isNaN() || bis.isNaN() || bis <= von || art !in setOf("op", "ed")) null
            else Sprung(art, (von * 1000).toLong(), (bis * 1000).toLong())
        }.sortedBy { it.vonMs }
    }

    // ------------------------------------------------------------ Netz

    private suspend fun jikan(pfad: String): String? {
        val netz = App.self.netz
        repeat(2) {
            val a = netz.anfrage("$JIKAN$pfad", mapOf("Accept" to "application/json"))
            if (a.ok) return a.text
            // Jikan erlaubt 3 Anfragen pro Sekunde; bei 429 kurz warten und einmal nachfassen.
            if (a.code != 429) return null
            delay(1_500)
        }
        return null
    }

    /** TV-Staffeln einer Serie, nach Ausstrahlung sortiert. Bleibt pro Serie gespeichert. */
    private suspend fun malStaffeln(info: Folgeninfo): List<MalStaffel> {
        val p = App.self.getSharedPreferences("aniskip", Context.MODE_PRIVATE)
        p.getString(info.serieUrl, null)?.let { roh ->
            val o = JSONObject(roh)
            val alt = System.currentTimeMillis() - o.optLong("zeit") > 7L * 24 * 3600 * 1000
            val liste = o.optJSONArray("staffeln") ?: JSONArray()
            // Leere Ergebnisse nach einer Woche neu versuchen; gefundene bleiben.
            if (liste.length() > 0 || !alt) {
                return (0 until liste.length()).map { i ->
                    val s = liste.getJSONObject(i)
                    MalStaffel(s.getInt("id"), s.optInt("folgen").takeIf { it > 0 }, s.optString("start"))
                }
            }
        }
        val suche = jikan("/anime?q=${URLEncoder.encode(info.serie, "UTF-8")}&type=tv&limit=8&order_by=popularity&sort=asc")
        val start = suche?.let { ersterTreffer(it, info.serie) }
        val gefunden = LinkedHashMap<Int, MalStaffel>()
        if (start != null) {
            val offen = ArrayDeque(listOf(start))
            val gesehen = HashSet<Int>()
            while (offen.isNotEmpty() && gesehen.size < MAX_ABRUFE) {
                val id = offen.removeFirst()
                if (!gesehen.add(id)) continue
                delay(400)
                val (staffel, verwandt) = jikan("/anime/$id/full")?.let { eintrag(it) } ?: continue
                staffel?.let { gefunden[it.id] = it }
                verwandt.filter { it !in gesehen }.forEach { offen.addLast(it) }
            }
        }
        val sortiert = gefunden.values.sortedWith(compareBy({ it.start.ifEmpty { "9999" } }, { it.id }))
        val arr = JSONArray()
        sortiert.forEach { arr.put(JSONObject().put("id", it.id).put("folgen", it.folgen ?: 0).put("start", it.start)) }
        p.edit().putString(info.serieUrl, JSONObject().put("zeit", System.currentTimeMillis()).put("staffeln", arr).toString()).apply()
        Protokoll.info("AniSkip: ${info.serie} → MAL ${sortiert.joinToString { it.id.toString() }}")
        return sortiert
    }

    /** Sprünge für eine Folge; leer, wenn AniSkip nichts kennt oder etwas schiefgeht. */
    suspend fun fuer(info: Folgeninfo): List<Sprung> {
        // Nur Animes: Für eine SerienStream-Serie würde die MAL-Suche irgendeinen Anime finden.
        if (info.istFilm || !App.self.aniworld.passt(info.serieUrl)) return emptyList()
        return try {
            val (mal, folge) = zuordnen(malStaffeln(info), info.staffel, info.folge) ?: return emptyList()
            val a = App.self.netz.anfrage("$ANISKIP/$mal/$folge?types=op&types=ed", mapOf("Accept" to "application/json"))
            if (!a.ok) emptyList() else spruenge(a.text)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Protokoll.fehler("AniSkip für ${info.serie} S${info.staffel}E${info.folge}", e)
            emptyList()
        }
    }
}
