package de.tobidervogel.aniworld.download

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.tr
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.io.IOException

/**
 * HLS-Playlists lesen. Gegenstück zu models/common/hls.py: Was der Parser nicht sicher
 * versteht, meldet er als [HlsNichtUnterstuetzt]; dann probiert der Lader den nächsten Hoster.
 */
object Hls {
    class HlsNichtUnterstuetzt(text: String) : IOException(text)

    data class Variante(val url: String, val bandbreite: Long, val hoehe: Int, val audioGruppe: String?)
    data class Audiospur(val url: String, val gruppe: String, val sprache: String?, val name: String?, val standard: Boolean)
    data class Master(val varianten: List<Variante>, val audio: List<Audiospur>)

    class Schluessel(val methode: String, val url: String?, val iv: ByteArray?)

    data class Segment(
        val url: String,
        val dauer: Double,
        val nr: Long,
        val schluessel: Schluessel?,
        /** Byte-Bereich (inklusive), falls EXT-X-BYTERANGE gesetzt ist. */
        val bereich: LongRange?,
    )

    data class Medienliste(val segmente: List<Segment>, val init: Segment?) {
        val dauer get() = segmente.sumOf { it.dauer }
    }

    private val ATTRIBUT = Regex("""([A-Z0-9-]+)=("[^"]*"|[^,]*)""")

    fun attribute(zeile: String): Map<String, String> =
        ATTRIBUT.findAll(zeile.substringAfter(':')).associate { it.groupValues[1] to it.groupValues[2].trim('"') }

    fun aufloesen(basis: String, rel: String): String {
        if (rel.startsWith("http://") || rel.startsWith("https://")) return rel
        return basis.toHttpUrlOrNull()?.resolve(rel)?.toString() ?: throw HlsNichtUnterstuetzt(tr(R.string.e_hls_adresse, rel))
    }

    fun istMaster(text: String) = "#EXT-X-STREAM-INF" in text

    fun master(text: String, basis: String): Master {
        val zeilen = text.lines().map { it.trim() }
        val varianten = ArrayList<Variante>()
        val audio = ArrayList<Audiospur>()
        var i = 0
        while (i < zeilen.size) {
            val z = zeilen[i]
            when {
                z.startsWith("#EXT-X-STREAM-INF") -> {
                    val a = attribute(z)
                    // Die Adresse ist die nächste Zeile, die kein Kommentar ist.
                    var j = i + 1
                    while (j < zeilen.size && (zeilen[j].isEmpty() || zeilen[j].startsWith("#"))) j++
                    if (j < zeilen.size) {
                        varianten += Variante(
                            url = aufloesen(basis, zeilen[j]),
                            bandbreite = a["BANDWIDTH"]?.toLongOrNull() ?: a["AVERAGE-BANDWIDTH"]?.toLongOrNull() ?: 0,
                            hoehe = a["RESOLUTION"]?.substringAfter('x')?.toIntOrNull() ?: 0,
                            audioGruppe = a["AUDIO"],
                        )
                    }
                    i = j
                }
                z.startsWith("#EXT-X-MEDIA:") -> {
                    val a = attribute(z)
                    val uri = a["URI"]
                    if (a["TYPE"] == "AUDIO" && uri != null) {
                        audio += Audiospur(aufloesen(basis, uri), a["GROUP-ID"].orEmpty(), a["LANGUAGE"], a["NAME"], a["DEFAULT"] == "YES")
                    }
                }
            }
            i++
        }
        return Master(varianten, audio)
    }

    /** Beste Variante: höchste Auflösung, bei Gleichstand höchste Bandbreite. */
    fun beste(m: Master): Variante? = m.varianten.maxWithOrNull(compareBy<Variante>({ it.hoehe }, { it.bandbreite }))

    /**
     * Passende Tonspur zur Variante. `bevorzugt` sind Sprachkürzel wie "de", "deu", "ger".
     * Hat die Gruppe keine eigenen Adressen, ist der Ton schon im Video (null).
     */
    fun tonspur(m: Master, v: Variante, bevorzugt: List<String>): Audiospur? {
        val gruppe = m.audio.filter { it.gruppe == v.audioGruppe }
        if (gruppe.isEmpty()) return null
        return gruppe.firstOrNull { s -> bevorzugt.any { s.sprache?.lowercase()?.startsWith(it) == true } }
            ?: gruppe.firstOrNull { s -> bevorzugt.any { s.name?.lowercase()?.contains(it) == true } }
            ?: gruppe.firstOrNull { it.standard }
            ?: gruppe.first()
    }

    fun medien(text: String, basis: String): Medienliste {
        if (!text.trimStart().startsWith("#EXTM3U")) throw HlsNichtUnterstuetzt(tr(R.string.e_hls_keine))
        val segmente = ArrayList<Segment>()
        var init: Segment? = null
        var nr = 0L
        var dauer = 0.0
        var schluessel: Schluessel? = null
        var bereich: LongRange? = null
        // Ohne @offset geht ein Byte-Bereich direkt hinter dem vorigen derselben Datei weiter.
        var naechsterStart = 0L
        for (roh in text.lines()) {
            val z = roh.trim()
            when {
                z.isEmpty() -> Unit
                z.startsWith("#EXT-X-MEDIA-SEQUENCE:") -> nr = z.substringAfter(':').trim().toLongOrNull() ?: 0
                z.startsWith("#EXTINF:") -> dauer = z.substringAfter(':').substringBefore(',').trim().toDoubleOrNull() ?: 0.0
                z.startsWith("#EXT-X-KEY:") -> {
                    val a = attribute(z)
                    schluessel = when (val m = a["METHOD"]) {
                        null, "NONE" -> null
                        "AES-128" -> Schluessel(m, a["URI"]?.let { aufloesen(basis, it) }, a["IV"]?.let(::ivAusHex))
                        else -> throw HlsNichtUnterstuetzt(tr(R.string.e_hls_verschluesselung, m))
                    }
                }
                z.startsWith("#EXT-X-BYTERANGE:") -> {
                    val (laenge, start) = byteRange(z.substringAfter(':'), naechsterStart)
                    bereich = start until start + laenge
                    naechsterStart = start + laenge
                }
                z.startsWith("#EXT-X-MAP:") -> {
                    val a = attribute(z)
                    val uri = a["URI"] ?: throw HlsNichtUnterstuetzt(tr(R.string.e_hls_map))
                    val r = a["BYTERANGE"]?.let { val (l, s) = byteRange(it, 0); s until s + l }
                    init = Segment(aufloesen(basis, uri), 0.0, -1, schluessel, r)
                }
                z.startsWith("#") -> Unit
                else -> {
                    segmente += Segment(aufloesen(basis, z), dauer, nr, schluessel, bereich)
                    nr++
                    dauer = 0.0
                    if (bereich == null) naechsterStart = 0
                    bereich = null
                }
            }
        }
        if (segmente.isEmpty()) throw HlsNichtUnterstuetzt(tr(R.string.e_hls_segmente))
        return Medienliste(segmente, init)
    }

    private fun byteRange(wert: String, standardStart: Long): Pair<Long, Long> {
        val teile = wert.trim().split('@')
        val laenge = teile[0].toLongOrNull() ?: throw HlsNichtUnterstuetzt("Kaputter BYTERANGE: $wert")
        val start = teile.getOrNull(1)?.toLongOrNull() ?: standardStart
        return laenge to start
    }

    fun ivAusHex(hex: String): ByteArray {
        val h = hex.removePrefix("0x").removePrefix("0X").padStart(32, '0')
        return ByteArray(16) { i -> h.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }

    /** Ohne IV-Attribut ist die IV die Segmentnummer als 128-Bit-Zahl (RFC 8216, 5.2). */
    fun ivAusNummer(nr: Long): ByteArray {
        val iv = ByteArray(16)
        var n = nr
        for (i in 15 downTo 8) {
            iv[i] = (n and 0xFF).toByte()
            n = n ushr 8
        }
        return iv
    }

    /** Sprachkürzel, an denen die Tonspur in der Playlist erkannt wird. */
    fun sprachkuerzel(sprache: Sprache): List<String> = when (sprache) {
        Sprache.DE_DUB -> listOf("de", "ger", "deu", "german", "deutsch")
        Sprache.EN_DUB -> listOf("en", "eng", "english")
        else -> listOf("ja", "jp", "jpn", "japan")
    }
}
