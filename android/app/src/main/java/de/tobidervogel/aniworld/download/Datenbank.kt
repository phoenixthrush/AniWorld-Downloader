package de.tobidervogel.aniworld.download

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import de.tobidervogel.aniworld.site.Einzelfilm
import de.tobidervogel.aniworld.site.Folgeninfo
import de.tobidervogel.aniworld.site.Sprache
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.File

enum class Status { WARTET, LAEUFT, FERTIG, FEHLER, PAUSE }

data class Auftrag(
    val id: Long = 0,
    val serie: String,
    val serieUrl: String,
    val cover: String?,
    val staffel: Int,
    val folge: Int,
    val istFilm: Boolean,
    val titel: String,
    val url: String,
    val sprache: Sprache,
    val hoster: String?,
    /** Stellen der Folgennummer im Dateinamen (3 bei Staffeln ab 100 Folgen). */
    val stellen: Int = 2,
    val status: Status = Status.WARTET,
    val fortschritt: Float = 0f,
    val bytes: Long = 0,
    val datei: String? = null,
    val fehler: String? = null,
    val info: String? = null,
    val erstellt: Long = System.currentTimeMillis(),
) {
    val kuerzel get() = if (istFilm) "Film $folge" else "S%02dE%02d".format(staffel, folge)
    val folgeninfo get() = Folgeninfo(serieUrl, serie, staffel, folge, istFilm)
    /** Film ohne Reihe (Filmo, FilmPalast): „Serie“ und einzige Folge sind derselbe Film. */
    val einzelfilm get() = Einzelfilm.ist(serieUrl, istFilm, staffel)
    /** Name für Player und Listen: „Serie · S01E05“, beim Einzelfilm nur der Titel. */
    val anzeige get() = if (einzelfilm) titel.ifBlank { serie } else "$serie · $kuerzel"
}

data class Verlauf(val url: String, val titel: String, val cover: String?)

/**
 * SQLite ohne Room: vier kleine Tabellen. Version 2 brachte die Tabelle für Auto-Sync.
 * `stand` zählt bei jeder Änderung hoch, darauf hört die Oberfläche.
 */
class Datenbank(context: Context) : SQLiteOpenHelper(context, "aniworld.db", null, 2) {
    private val _stand = MutableStateFlow(0)
    val stand: StateFlow<Int> = _stand
    private fun geaendert() { _stand.value++ }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE auftrag (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serie TEXT NOT NULL, serie_url TEXT NOT NULL, cover TEXT,
                staffel INTEGER NOT NULL, folge INTEGER NOT NULL, ist_film INTEGER NOT NULL,
                titel TEXT NOT NULL, url TEXT NOT NULL, sprache TEXT NOT NULL, hoster TEXT,
                stellen INTEGER NOT NULL DEFAULT 2,
                status TEXT NOT NULL, fortschritt REAL NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
                datei TEXT, fehler TEXT, info TEXT, erstellt INTEGER NOT NULL,
                UNIQUE(url, sprache))"""
        )
        db.execSQL("CREATE TABLE verlauf (url TEXT PRIMARY KEY, titel TEXT NOT NULL, cover TEXT, zeit INTEGER NOT NULL)")
        db.execSQL("CREATE TABLE position (schluessel TEXT PRIMARY KEY, ms INTEGER NOT NULL, dauer INTEGER NOT NULL, zeit INTEGER NOT NULL)")
        autoSyncTabelle(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, alt: Int, neu: Int) {
        if (alt < 2) autoSyncTabelle(db)
    }

    /** Höchste Folge je Serie und Sprache, die Auto-Sync schon online gesehen hat. */
    private fun autoSyncTabelle(db: SQLiteDatabase) = db.execSQL(
        """CREATE TABLE IF NOT EXISTS autosync (
            serie_url TEXT NOT NULL, sprache TEXT NOT NULL, staffel INTEGER NOT NULL, folge INTEGER NOT NULL,
            PRIMARY KEY(serie_url, sprache))"""
    )

    // ------------------------------------------------------------ Aufträge

    private fun Cursor.auftrag() = Auftrag(
        id = getLong(getColumnIndexOrThrow("id")),
        serie = getString(getColumnIndexOrThrow("serie")),
        serieUrl = getString(getColumnIndexOrThrow("serie_url")),
        cover = getString(getColumnIndexOrThrow("cover")),
        staffel = getInt(getColumnIndexOrThrow("staffel")),
        folge = getInt(getColumnIndexOrThrow("folge")),
        istFilm = getInt(getColumnIndexOrThrow("ist_film")) == 1,
        titel = getString(getColumnIndexOrThrow("titel")),
        url = getString(getColumnIndexOrThrow("url")),
        sprache = runCatching { Sprache.valueOf(getString(getColumnIndexOrThrow("sprache"))) }.getOrDefault(Sprache.DE_DUB),
        hoster = getString(getColumnIndexOrThrow("hoster")),
        stellen = getInt(getColumnIndexOrThrow("stellen")),
        status = runCatching { Status.valueOf(getString(getColumnIndexOrThrow("status"))) }.getOrDefault(Status.FEHLER),
        fortschritt = getFloat(getColumnIndexOrThrow("fortschritt")),
        bytes = getLong(getColumnIndexOrThrow("bytes")),
        datei = getString(getColumnIndexOrThrow("datei")),
        fehler = getString(getColumnIndexOrThrow("fehler")),
        info = getString(getColumnIndexOrThrow("info")),
        erstellt = getLong(getColumnIndexOrThrow("erstellt")),
    )

    private fun abfrage(wo: String? = null, args: Array<String>? = null, sortierung: String = "erstellt, staffel, folge"): List<Auftrag> =
        readableDatabase.query("auftrag", null, wo, args, null, null, sortierung).use { c ->
            buildList { while (c.moveToNext()) add(c.auftrag()) }
        }

    fun alle(): List<Auftrag> = abfrage()
    fun auftrag(id: Long): Auftrag? = abfrage("id = ?", arrayOf(id.toString())).firstOrNull()
    fun fuerSerie(serieUrl: String): List<Auftrag> = abfrage("serie_url = ?", arrayOf(serieUrl))

    /** Die nächsten wartenden Aufträge in Einreihungsreihenfolge. */
    fun wartende(): List<Auftrag> = abfrage("status = ?", arrayOf(Status.WARTET.name), "erstellt, id")

    /**
     * Reiht ein; schon vorhandene Folgen (gleiche Sprache) werden nicht doppelt angelegt.
     * Pausierte, fehlgeschlagene und fertige, deren Datei inzwischen gelöscht ist, kommen zurück in die Warteschlange.
     * @return Anzahl neu eingereihter oder neu gestarteter Aufträge
     */
    fun einreihen(liste: List<Auftrag>): Int {
        var neu = 0
        val db = writableDatabase
        db.beginTransaction()
        try {
            for (a in liste) {
                val v = ContentValues().apply {
                    put("serie", a.serie); put("serie_url", a.serieUrl); put("cover", a.cover)
                    put("staffel", a.staffel); put("folge", a.folge); put("ist_film", if (a.istFilm) 1 else 0)
                    put("titel", a.titel); put("url", a.url); put("sprache", a.sprache.name); put("hoster", a.hoster)
                    put("stellen", a.stellen); put("status", Status.WARTET.name); put("erstellt", a.erstellt)
                }
                val alt = db.query("auftrag", null, "url = ? AND sprache = ?", arrayOf(a.url, a.sprache.name), null, null, null)
                    .use { c -> if (c.moveToFirst()) c.auftrag() else null }
                if (alt == null) {
                    if (db.insert("auftrag", null, v) != -1L) neu++
                    continue
                }
                val nochmal = alt.status == Status.FEHLER || alt.status == Status.PAUSE ||
                    (alt.status == Status.FERTIG && alt.datei?.let { File(it).exists() } != true)
                if (nochmal) {
                    db.update("auftrag", ContentValues().apply {
                        put("status", Status.WARTET.name); putNull("fehler"); put("hoster", a.hoster)
                        if (alt.status == Status.FERTIG) { putNull("datei"); put("fortschritt", 0f); put("bytes", 0) }
                    }, "id = ?", arrayOf(alt.id.toString()))
                    neu++
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        geaendert()
        return neu
    }

    private fun aendern(id: Long, v: ContentValues, melden: Boolean = true) {
        writableDatabase.update("auftrag", v, "id = ?", arrayOf(id.toString()))
        if (melden) geaendert()
    }

    fun status(id: Long, status: Status, fehler: String? = null) = aendern(id, ContentValues().apply {
        put("status", status.name)
        if (fehler != null) put("fehler", fehler) else putNull("fehler")
    })

    /** Fortschritt schreiben ohne die Oberfläche anzustoßen (die liest live mit). */
    fun fortschritt(id: Long, anteil: Float, bytes: Long, info: String?) = aendern(id, ContentValues().apply {
        put("fortschritt", anteil); put("bytes", bytes); put("info", info)
    }, melden = false)

    fun fertig(id: Long, datei: String, bytes: Long, info: String?) = aendern(id, ContentValues().apply {
        put("status", Status.FERTIG.name); put("datei", datei); put("bytes", bytes)
        put("fortschritt", 1f); put("info", info); putNull("fehler")
    })

    fun loeschen(id: Long) {
        writableDatabase.delete("auftrag", "id = ?", arrayOf(id.toString()))
        geaendert()
    }

    /** Nach einem Absturz liegen noch LAEUFT-Einträge herum; die laufen beim nächsten Start weiter. */
    fun laufendeZuruecksetzen() {
        writableDatabase.update("auftrag", ContentValues().apply { put("status", Status.WARTET.name) },
            "status = ?", arrayOf(Status.LAEUFT.name))
        geaendert()
    }

    fun fehlerNeuStarten(): Int {
        val n = writableDatabase.update("auftrag", ContentValues().apply { put("status", Status.WARTET.name); putNull("fehler") },
            "status = ?", arrayOf(Status.FEHLER.name))
        geaendert()
        return n
    }

    // ------------------------------------------------------------ Verlauf

    fun merken(url: String, titel: String, cover: String?) {
        writableDatabase.insertWithOnConflict("verlauf", null, ContentValues().apply {
            put("url", url); put("titel", titel); put("cover", cover); put("zeit", System.currentTimeMillis())
        }, SQLiteDatabase.CONFLICT_REPLACE)
        geaendert()
    }

    fun verlauf(anzahl: Int = 20): List<Verlauf> =
        readableDatabase.query("verlauf", null, null, null, null, null, "zeit DESC", anzahl.toString()).use { c ->
            buildList {
                while (c.moveToNext()) add(Verlauf(c.getString(0), c.getString(1), c.getString(2)))
            }
        }

    fun vergessen(url: String) {
        writableDatabase.delete("verlauf", "url = ?", arrayOf(url))
        geaendert()
    }

    // ------------------------------------------------------------ Abspielstand

    fun position(schluessel: String): Pair<Long, Long>? =
        readableDatabase.query("position", arrayOf("ms", "dauer"), "schluessel = ?", arrayOf(schluessel), null, null, null).use { c ->
            if (c.moveToFirst()) c.getLong(0) to c.getLong(1) else null
        }

    fun positionen(schluessel: Collection<String>): Map<String, Float> {
        if (schluessel.isEmpty()) return emptyMap()
        val platz = schluessel.joinToString(",") { "?" }
        return readableDatabase.rawQuery(
            "SELECT schluessel, ms, dauer FROM position WHERE schluessel IN ($platz)", schluessel.toTypedArray()
        ).use { c ->
            buildMap {
                while (c.moveToNext()) {
                    val dauer = c.getLong(2)
                    if (dauer > 0) put(c.getString(0), (c.getLong(1).toFloat() / dauer).coerceIn(0f, 1f))
                }
            }
        }
    }

    fun positionMerken(schluessel: String, ms: Long, dauer: Long) {
        writableDatabase.insertWithOnConflict("position", null, ContentValues().apply {
            put("schluessel", schluessel); put("ms", ms); put("dauer", dauer); put("zeit", System.currentTimeMillis())
        }, SQLiteDatabase.CONFLICT_REPLACE)
        geaendert()
    }

    // ------------------------------------------------------------ Auto-Sync

    fun marke(serieUrl: String, sprache: Sprache): Pair<Int, Int>? =
        readableDatabase.query("autosync", arrayOf("staffel", "folge"), "serie_url = ? AND sprache = ?", arrayOf(serieUrl, sprache.name), null, null, null)
            .use { c -> if (c.moveToFirst()) c.getInt(0) to c.getInt(1) else null }

    fun markeSetzen(serieUrl: String, sprache: Sprache, marke: Pair<Int, Int>) {
        writableDatabase.insertWithOnConflict("autosync", null, ContentValues().apply {
            put("serie_url", serieUrl); put("sprache", sprache.name); put("staffel", marke.first); put("folge", marke.second)
        }, SQLiteDatabase.CONFLICT_REPLACE)
    }
}
