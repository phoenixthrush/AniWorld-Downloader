package de.tobidervogel.aniworld.net

import de.tobidervogel.aniworld.App
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.AbstractCoroutineContextElement
import kotlin.coroutines.CoroutineContext
import kotlin.coroutines.coroutineContext

/**
 * Markiert Abrufe im Hintergrund (Auto-Sync): Dort öffnet sich kein Browserfenster, eine
 * Prüfseite gilt sofort als nicht bestanden. Sonst hinge der Lauf bis zu zehn Minuten.
 */
object StillerAbruf : AbstractCoroutineContextElement(Schluessel) {
    // Eigener Schlüssel: Ein Objekt, das sich selbst als Schlüssel übergibt, ist beim Anlegen noch null.
    object Schluessel : CoroutineContext.Key<StillerAbruf>
}

/**
 * Vermittelt zwischen Netz (merkt, dass eine Schutzseite kommt) und Oberfläche (zeigt das
 * Browserfenster). Die Prüfung läuft sichtbar: Meist erledigt sie sich in ein paar Sekunden
 * von selbst, ein Rätsel löst der Nutzer selbst. Danach liegen die Cookies im CookieManager.
 */
object BrowserCheck {
    /**
     * @param verlassen true beim Redirect zum Hoster: fertig, sobald die Seite die Hosts in
     *                  [heim] verlässt. Das Ergebnis ist dann die Hoster-Adresse.
     */
    class Anfrage(val url: String, val verlassen: Boolean, val heim: Set<String>) {
        val ergebnis = CompletableDeferred<String?>()
    }

    private val _offen = MutableStateFlow<Anfrage?>(null)
    val offen: StateFlow<Anfrage?> = _offen

    /** Setzt MainActivity in onStart/onStop. */
    @Volatile var appSichtbar = false

    private val sperre = Mutex()
    @Volatile private var zuletztGeloest = 0L

    /** Liefert die Endadresse nach bestandener Prüfung, sonst null (abgebrochen, Zeit um). */
    suspend fun loesen(url: String, verlassen: Boolean = false, heim: Set<String> = emptySet()): String? {
        if (coroutineContext[StillerAbruf.Schluessel] != null) return null
        return loesenSichtbar(url, verlassen, heim)
    }

    private suspend fun loesenSichtbar(url: String, verlassen: Boolean, heim: Set<String>): String? = sperre.withLock {
        // Mehrere Seitenanfragen gleichzeitig: Die erste löst, die anderen versuchen es danach direkt nochmal.
        if (!verlassen && System.currentTimeMillis() - zuletztGeloest < 30_000) return@withLock url
        val anfrage = Anfrage(url, verlassen, heim)
        _offen.value = anfrage
        if (!appSichtbar) App.self.meldeCheck()
        val ende = withTimeoutOrNull(10 * 60_000L) { anfrage.ergebnis.await() }
        _offen.value = null
        App.self.checkMeldungWeg()
        if (ende != null && !verlassen) zuletztGeloest = System.currentTimeMillis()
        ende
    }
}
