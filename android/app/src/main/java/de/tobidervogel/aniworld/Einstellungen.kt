package de.tobidervogel.aniworld

import android.content.Context
import android.os.Environment
import de.tobidervogel.aniworld.site.Sprache
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Alle Einstellungen in einer SharedPreferences-Datei. `stand` zählt bei jeder Änderung hoch,
 * damit Compose neu zeichnet.
 */
class Einstellungen(context: Context) {
    private val p = context.getSharedPreferences("einstellungen", Context.MODE_PRIVATE)
    private val _stand = MutableStateFlow(0)
    val stand: StateFlow<Int> = _stand

    private fun geaendert() { _stand.value++ }

    var ordner: String
        get() = p.getString("ordner", null) ?: STANDARD_ORDNER
        set(v) { p.edit().putString("ordner", v.trim().trimEnd('/')).apply(); geaendert() }

    var sprache: Sprache
        get() = runCatching { Sprache.valueOf(p.getString("sprache", null)!!) }.getOrDefault(Sprache.DE_DUB)
        set(v) { p.edit().putString("sprache", v.name).apply(); geaendert() }

    /** Hoster in Versuchsreihenfolge. Unbekannte Namen von der Seite kommen hinten dran. */
    var hosterReihenfolge: List<String>
        get() = p.getString("hoster", null)?.split(',')?.map { it.trim() }?.filter { it.isNotEmpty() }
            ?.let { gespeichert -> gespeichert + STANDARD_HOSTER.filter { it !in gespeichert } }
            ?: STANDARD_HOSTER
        set(v) { p.edit().putString("hoster", v.joinToString(",")).apply(); geaendert() }

    /** Wie viele Folgen gleichzeitig laden. */
    var parallel: Int
        get() = p.getInt("parallel", 2).coerceIn(1, 3)
        set(v) { p.edit().putInt("parallel", v.coerceIn(1, 3)).apply(); geaendert() }

    /** Wie viele HLS-Segmente einer Folge gleichzeitig laden. */
    var segmente: Int
        get() = p.getInt("segmente", 8).coerceIn(1, 16)
        set(v) { p.edit().putInt("segmente", v.coerceIn(1, 16)).apply(); geaendert() }

    var doh: Boolean
        get() = p.getBoolean("doh", true)
        set(v) { p.edit().putBoolean("doh", v).apply(); geaendert() }

    /** HLS-Downloads nach MP4 umpacken (sonst bleibt .ts). */
    var mp4: Boolean
        get() = p.getBoolean("mp4", true)
        set(v) { p.edit().putBoolean("mp4", v).apply(); geaendert() }

    /** Wenn kein Extraktor klappt: Hoster im versteckten Browser öffnen und die Videoadresse mitlesen. */
    var browserWeg: Boolean
        get() = p.getBoolean("browserWeg", true)
        set(v) { p.edit().putBoolean("browserWeg", v).apply(); geaendert() }

    /** Opening/Ending-Zeiten von AniSkip holen und im Player einen Überspringen-Knopf zeigen. */
    var aniskip: Boolean
        get() = p.getBoolean("aniskip", true)
        set(v) { p.edit().putBoolean("aniskip", v).apply(); geaendert() }

    /** Statt Knopf direkt springen. */
    var aniskipAuto: Boolean
        get() = p.getBoolean("aniskipAuto", false)
        set(v) { p.edit().putBoolean("aniskipAuto", v).apply(); geaendert() }

    /** Welche Seite „Entdecken“ zeigt (Name des Anbieters). */
    var startQuelle: String
        get() = p.getString("startQuelle", null) ?: "AniWorld"
        set(v) { p.edit().putString("startQuelle", v).apply(); geaendert() }

    var nurWlan: Boolean
        get() = p.getBoolean("nurWlan", false)
        set(v) { p.edit().putBoolean("nurWlan", v).apply(); geaendert() }

    /** Einrichtung beim ersten Start abgeschlossen (oder übersprungen). */
    var einrichtungFertig: Boolean
        get() = p.getBoolean("einrichtungFertig", false)
        set(v) { p.edit().putBoolean("einrichtungFertig", v).apply(); geaendert() }

    /** Serien aus der Bibliothek regelmäßig auf neue Folgen prüfen (siehe AutoSync). */
    var autoSync: Boolean
        get() = p.getBoolean("autoSync", false)
        set(v) { p.edit().putBoolean("autoSync", v).apply(); geaendert() }

    var autoSyncStunden: Int
        get() = p.getInt("autoSyncStunden", 12).takeIf { it in AUTOSYNC_STUNDEN } ?: 12
        set(v) { p.edit().putInt("autoSyncStunden", v).apply(); geaendert() }

    /** Letzter Lauf: Zeitpunkt, geprüfte Serien, eingereihte Folgen, Fehler. 0 = noch nie. */
    val autoSyncZuletzt: Long get() = p.getLong("autoSyncZuletzt", 0)
    val autoSyncGeprueft: Int get() = p.getInt("autoSyncGeprueft", 0)
    val autoSyncNeu: Int get() = p.getInt("autoSyncNeu", 0)
    val autoSyncFehler: Int get() = p.getInt("autoSyncFehler", 0)

    fun autoSyncErgebnis(zeit: Long, geprueft: Int, neu: Int, fehler: Int) {
        p.edit().putLong("autoSyncZuletzt", zeit).putInt("autoSyncGeprueft", geprueft)
            .putInt("autoSyncNeu", neu).putInt("autoSyncFehler", fehler).apply()
        geaendert()
    }

    companion object {
        val STANDARD_ORDNER: String =
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES)?.absolutePath
                ?.let { "$it/AniWorld" } ?: "/storage/emulated/0/Movies/AniWorld"

        // VOE, Filemoon und Doodstream liefen beim letzten Provider-Check des Originals, Vidmoly nicht.
        val STANDARD_HOSTER = listOf("VOE", "Filemoon", "Doodstream", "Vidoza", "Vidmoly")

        val AUTOSYNC_STUNDEN = listOf(6, 12, 24)
    }
}
