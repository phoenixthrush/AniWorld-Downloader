package de.tobidervogel.aniworld.download

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.MainActivity
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Arbeitet die Warteschlange ab, solange etwas wartet, und beendet sich danach selbst.
 * Läuft als Vordergrunddienst (dataSync), damit das System ihn nicht mitten in der Staffel beendet.
 */
class DownloadService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val laufend = ConcurrentHashMap<Long, Job>()
    private val wecker = Channel<Unit>(Channel.CONFLATED)
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var zuletztGemeldet = 0L
    // Mehrere Downloads melden gleichzeitig; darum atomar zählen.
    private val fertigeDieseRunde = AtomicInteger()
    private val fehlerDieseRunde = AtomicInteger()
    @Volatile private var letzteStartId = 0
    private val schleifeAktiv = AtomicBoolean(false)

    private val app get() = application as App

    override fun onBind(intent: Intent?): IBinder? = null

    @SuppressLint("WakelockTimeout")
    override fun onCreate() {
        super.onCreate()
        instanz = this
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AniApp:Downloads").apply { acquire() }
        @Suppress("DEPRECATION")
        wifiLock = getSystemService(WifiManager::class.java)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "AniApp:Downloads").apply { acquire() }
        app.db.laufendeZuruecksetzen()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        letzteStartId = startId
        // Jeder startForegroundService()-Aufruf verlangt startForeground(), auch wenn der Dienst schon läuft.
        // Den Diensttyp kennt Android erst ab 10; davor gibt es nur „Vordergrund“.
        val typ = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0
        ServiceCompat.startForeground(this, ID_LAUF, meldung(getString(R.string.dl_starten), null), typ)
        if (schleifeAktiv.compareAndSet(false, true)) scope.launch { schleife() } else wecker.trySend(Unit)
        return START_STICKY
    }

    override fun onDestroy() {
        instanz = null
        scope.cancel()
        _live.value = emptyMap()
        runCatching { wakeLock?.release() }
        runCatching { wifiLock?.release() }
        super.onDestroy()
    }

    private fun wlan(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    private suspend fun schleife() {
        while (true) {
            val wartend = app.db.wartende()
            val darf = !app.einstellungen.nurWlan || wlan()
            if (darf) {
                val frei = app.einstellungen.parallel - laufend.size
                wartend.filter { !laufend.containsKey(it.id) }.take(frei.coerceAtLeast(0)).forEach { starten(it) }
            }
            if (laufend.isEmpty() && (wartend.isEmpty() || !darf)) {
                if (wartend.isNotEmpty()) {
                    melden(getString(R.string.warte_wlan, wartend.size), null, sofort = true)
                } else {
                    val id = letzteStartId
                    schleifeAktiv.set(false)
                    // Kam in diesem Moment doch noch etwas dazu, weiterarbeiten statt aufhören.
                    if (app.db.wartende().isNotEmpty() && schleifeAktiv.compareAndSet(false, true)) continue
                    abschluss()
                    ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
                    // Nur beenden, wenn seitdem kein neuer Start kam (sonst läuft die neue Schleife schon).
                    stopSelf(id)
                    return
                }
            }
            withTimeoutOrNull(3_000) { wecker.receive() }
        }
    }

    private fun starten(a: Auftrag) {
        app.db.status(a.id, Status.LAEUFT)
        // LAZY: erst eintragen, dann starten. Sonst könnte ein sehr schneller Auftrag sich austragen,
        // bevor er eingetragen ist, und bliebe für immer als "läuft" stehen.
        val job = scope.launch(start = CoroutineStart.LAZY) {
            var zuletztDb = 0L
            try {
                val (datei, info) = Lader(app).ausfuehren(a) { l ->
                    _live.update { it + (a.id to l) }
                    val jetzt = System.currentTimeMillis()
                    if (jetzt - zuletztDb > 2_000) {
                        zuletztDb = jetzt
                        app.db.fortschritt(a.id, l.anteil ?: 0f, l.bytes, l.text)
                    }
                    melden()
                }
                app.db.fertig(a.id, datei.path, datei.length(), info)
                fertigeDieseRunde.incrementAndGet()
                Protokoll.info("Fertig: ${a.serie} ${a.kuerzel} → ${datei.path}")
            } catch (e: CancellationException) {
                // Pausiert oder entfernt: den Status setzt, wer abgebrochen hat.
                throw e
            } catch (e: Exception) {
                // Pause oder Entfernen kommt manchmal als IOException an (Umpacker, abgebrochener Aufruf).
                // Dann keinen Fehler eintragen: Den Status hat schon gesetzt, wer abgebrochen hat.
                if (!isActive) throw CancellationException("abgebrochen")
                Protokoll.fehler("${a.serie} ${a.kuerzel}", e)
                app.db.status(a.id, Status.FEHLER, e.message ?: e.javaClass.simpleName)
                fehlerDieseRunde.incrementAndGet()
            } finally {
                laufend.remove(a.id)
                _live.update { it - a.id }
                wecker.trySend(Unit)
            }
        }
        laufend[a.id] = job
        job.start()
    }

    /** Pausieren: Teile bleiben liegen und werden beim Fortsetzen weiterverwendet. */
    fun pausieren(id: Long) {
        laufend[id]?.cancel()
        app.db.status(id, Status.PAUSE)
        wecker.trySend(Unit)
    }

    fun entfernen(id: Long) {
        laufend[id]?.cancel()
        wecker.trySend(Unit)
    }

    private fun meldung(text: String, anteil: Float?): Notification {
        val b = NotificationCompat.Builder(this, App.KANAL_DOWNLOADS)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(getString(R.string.laedt_titel))
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(app.oeffnenIntent(MainActivity.TAB_DOWNLOADS))
        if (anteil != null) b.setProgress(1000, (anteil * 1000).toInt(), false) else b.setProgress(0, 0, laufend.isNotEmpty())
        return b.build()
    }

    private fun melden(text: String? = null, anteil: Float? = null, sofort: Boolean = false) {
        val jetzt = System.currentTimeMillis()
        if (!sofort && jetzt - zuletztGemeldet < 1_000) return
        zuletztGemeldet = jetzt
        val live = _live.value.values
        val t = text ?: run {
            val warten = app.db.wartende().size
            val tempo = live.sumOf { it.tempo }
            buildString {
                append(getString(R.string.n_laeuft, live.size))
                if (warten > 0) append(" · ").append(getString(R.string.n_warten, warten))
                if (tempo > 0) append(" · ").append(groesse(tempo)).append("/s")
            }
        }
        val a = anteil ?: live.mapNotNull { it.anteil }.takeIf { it.isNotEmpty() }?.average()?.toFloat()
        getSystemService(NotificationManager::class.java).notify(ID_LAUF, meldung(t, a))
    }

    private fun abschluss() {
        val fertig = fertigeDieseRunde.getAndSet(0)
        val fehler = fehlerDieseRunde.getAndSet(0)
        if (fertig == 0 && fehler == 0) return
        val text = buildString {
            append(getString(R.string.n_fertig, fertig))
            if (fehler > 0) append(", ").append(getString(R.string.n_mit_fehler, fehler))
        }
        val n = NotificationCompat.Builder(this, App.KANAL_DOWNLOADS)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(getString(R.string.dl_fertig_titel))
            .setContentText(text)
            .setAutoCancel(true)
            // Mit Fehlern in die Warteschlange, sonst gleich in die Bibliothek.
            .setContentIntent(app.oeffnenIntent(if (fehler > 0) MainActivity.TAB_DOWNLOADS else MainActivity.TAB_BIBLIOTHEK))
            .build()
        getSystemService(NotificationManager::class.java).notify(ID_ENDE, n)
    }

    companion object {
        private const val ID_LAUF = 1
        private const val ID_ENDE = 3

        @Volatile private var instanz: DownloadService? = null

        private val _live = MutableStateFlow<Map<Long, Live>>(emptyMap())
        val live: StateFlow<Map<Long, Live>> = _live

        fun starten(context: Context) {
            context.startForegroundService(Intent(context, DownloadService::class.java))
        }

        fun pausieren(app: App, id: Long) {
            instanz?.pausieren(id) ?: app.db.status(id, Status.PAUSE)
        }

        fun fortsetzen(app: App, id: Long) {
            app.db.status(id, Status.WARTET)
            starten(app)
        }

        /** Auftrag abbrechen und samt halbfertiger Teile entfernen. Fertige Dateien bleiben. */
        fun entfernen(app: App, id: Long) {
            instanz?.entfernen(id)
            app.db.loeschen(id)
            Speicher.arbeitsordner(app, id).deleteRecursively()
        }

        fun groesse(bytes: Long): String = when {
            bytes >= 1L shl 30 -> "%.1f GB".format(bytes / (1L shl 30).toDouble())
            bytes >= 1L shl 20 -> "%.1f MB".format(bytes / (1L shl 20).toDouble())
            bytes >= 1L shl 10 -> "%d KB".format(bytes / (1L shl 10))
            else -> "$bytes B"
        }
    }
}
