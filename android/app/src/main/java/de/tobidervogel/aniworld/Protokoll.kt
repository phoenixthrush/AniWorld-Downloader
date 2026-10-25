package de.tobidervogel.aniworld

import android.util.Log
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Kleines Protokoll in einer Datei. In der App unter Einstellungen → Protokoll lesbar und kopierbar,
 * damit sich ein Fehler ohne ADB weitergeben lässt (Einstellungen → Protokoll → Kopieren).
 */
object Protokoll {
    private var datei: File? = null
    private val zeit = DateTimeFormatter.ofPattern("dd.MM. HH:mm:ss")
    private const val MAX_BYTES = 400_000L

    fun init(ordner: File) {
        datei = File(ordner, "protokoll.txt")
    }

    fun info(text: String) = schreiben("I", text, null)
    fun fehler(text: String, t: Throwable? = null) = schreiben("F", text, t)

    @Synchronized
    private fun schreiben(stufe: String, text: String, t: Throwable?) {
        val zeile = buildString {
            append(LocalDateTime.now().format(zeit)).append(' ').append(stufe).append(' ').append(text)
            if (t != null) append(" — ").append(t.javaClass.simpleName).append(": ").append(t.message)
        }
        if (stufe == "F") Log.w("AniWorld", zeile, t) else Log.i("AniWorld", zeile)
        val f = datei ?: return
        runCatching {
            if (f.length() > MAX_BYTES) {
                // Hintere Hälfte behalten, damit die Datei nicht endlos wächst.
                val rest = f.readText().takeLast((MAX_BYTES / 2).toInt())
                f.writeText(rest.substringAfter('\n'))
            }
            f.appendText(zeile + "\n")
        }
    }

    fun lesen(): String = runCatching { datei?.readText() }.getOrNull().orEmpty()

    fun leeren() {
        runCatching { datei?.writeText("") }
    }
}
