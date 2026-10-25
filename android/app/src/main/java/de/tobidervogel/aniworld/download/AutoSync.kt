package de.tobidervogel.aniworld.download

import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.MainActivity
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.StillerAbruf
import de.tobidervogel.aniworld.site.Folge
import de.tobidervogel.aniworld.site.Sprache
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * Auto-Sync nach web/autosync.py im Original: Serien, von denen schon Folgen in der Bibliothek
 * liegen, bekommen neu erscheinende Folgen ohne Zutun. Anders als das Original füllt die App keine
 * Lücken auf. Beim ersten Prüfen einer Serie merkt sie sich nur, was schon online ist (die „Marke“);
 * eingereiht wird erst, was danach erscheint. Sonst stünde nach einer einzigen Probefolge von
 * One Piece plötzlich die ganze Serie in der Warteschlange. Die Sprache ist die der zuletzt
 * angelegten Folge, einen Wechsel gibt es nie. Filme bleiben außen vor.
 */
object AutoSync {
    /** Was von einer Serie schon da ist: Sprache und letzte Folge (Staffel, Nummer). */
    data class Stand(
        val serieUrl: String,
        val serie: String,
        val cover: String?,
        val sprache: Sprache,
        val staffel: Int,
        val folge: Int,
    )

    data class Bericht(val geprueft: Int, val neu: Int, val serien: List<String>, val fehler: Int)

    private val folgenFolge = compareBy<Pair<Int, Int>>({ it.first }, { it.second })

    private val sperre = Mutex()

    /** Serien aus der Bibliothek, die Auto-Sync verfolgt; je Serie die Sprache der zuletzt angelegten Folge. */
    fun bibliothek(auftraege: List<Auftrag>): List<Stand> =
        auftraege.filter { it.status == Status.FERTIG && !it.istFilm && !it.einzelfilm && it.staffel > 0 }
            .groupBy { it.serieUrl }
            .mapNotNull { (url, liste) ->
                val sprache = liste.maxByOrNull { it.erstellt }?.sprache ?: return@mapNotNull null
                val letzte = liste.filter { it.sprache == sprache }.maxWithOrNull(compareBy({ it.staffel }, { it.folge }))
                    ?: return@mapNotNull null
                Stand(url, letzte.serie, letzte.cover, sprache, letzte.staffel, letzte.folge)
            }

    /** Folgen, die es in der Sprache schon gibt (ohne Filme), nach Staffel und Nummer sortiert. */
    private fun verfuegbar(staffeln: Map<Int, List<Folge>>, sprache: Sprache): List<Folge> =
        staffeln.values.flatten().filter { !it.istFilm && sprache in it.sprachen }.distinctBy { it.url }
            .sortedWith(compareBy({ it.staffel }, { it.nummer }))

    /** Höchste Folge, die in der Sprache online ist; die neue Marke nach einer Prüfung. */
    fun marke(staffeln: Map<Int, List<Folge>>, sprache: Sprache): Pair<Int, Int>? =
        verfuegbar(staffeln, sprache).lastOrNull()?.let { it.staffel to it.nummer }

    /**
     * Neu erschienene Folgen: hinter der Marke der letzten Prüfung und hinter der letzten geladenen
     * Folge, in der Sprache, und ohne Auftrag (auch pausierte oder gelöschte nicht, die hat der Nutzer
     * bewusst so gelassen). Ohne Marke ist es die erste Prüfung, dann kommt nichts.
     */
    fun neue(stand: Stand, staffeln: Map<Int, List<Folge>>, marke: Pair<Int, Int>?, bekannt: Set<String>): List<Folge> {
        marke ?: return emptyList()
        val grenze = maxOf(marke, stand.staffel to stand.folge, folgenFolge)
        return verfuegbar(staffeln, stand.sprache).filter { folgenFolge.compare(it.staffel to it.nummer, grenze) > 0 && it.url !in bekannt }
    }

    /**
     * Ein Durchlauf über die ganze Bibliothek. `still`: im Hintergrund kein Browserfenster öffnen;
     * eine Seite mit Prüfung wird dann übersprungen und beim nächsten Mal wieder versucht.
     * @return null, wenn gerade schon ein Lauf aktiv ist
     */
    suspend fun lauf(app: App, still: Boolean): Bericht? {
        if (!sperre.tryLock()) return null
        try {
            val alle = app.db.alle()
            val staende = bibliothek(alle)
            var neu = 0
            var fehler = 0
            val serien = ArrayList<String>()
            for ((i, st) in staende.withIndex()) {
                if (i > 0) delay(1_500)
                try {
                    val n = if (still) withContext(StillerAbruf) { pruefen(app, st, alle) } else pruefen(app, st, alle)
                    if (n > 0) { neu += n; serien += st.serie }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    fehler++
                    Protokoll.fehler("Auto-Sync: ${st.serie}", e)
                }
            }
            val b = Bericht(staende.size, neu, serien, fehler)
            app.einstellungen.autoSyncErgebnis(System.currentTimeMillis(), b.geprueft, b.neu, b.fehler)
            Protokoll.info("Auto-Sync: ${staende.size} Serien geprüft, $neu Folgen eingereiht, $fehler Fehler")
            if (neu > 0) {
                melden(app, b)
                // Aus dem Hintergrund darf Android 12+ den Dienst oft nicht starten; dann startet ihn die App beim Öffnen.
                runCatching { DownloadService.starten(app) }.onFailure { Protokoll.info("Auto-Sync: Dienst startet beim Öffnen der App") }
            }
            return b
        } finally {
            sperre.unlock()
        }
    }

    private suspend fun pruefen(app: App, st: Stand, alle: List<Auftrag>): Int {
        val anbieter = app.anbieter(st.serieUrl)
        val serie = anbieter.serie(st.serieUrl, neu = true)
        val alt = app.db.marke(st.serieUrl, st.sprache)
        // Nur ab der Staffel laden, in der zuletzt etwas passiert ist; frühere ändern sich nicht mehr.
        val ab = maxOf(st.staffel, alt?.first ?: 0)
        val staffeln = serie.staffeln.filter { !it.istFilme && it.nummer >= ab }
            .associate { ref -> ref.nummer to anbieter.staffel(ref, neu = true) }
        val bekannt = alle.filter { it.serieUrl == st.serieUrl && it.sprache == st.sprache }.map { it.url }.toSet()
        val folgen = neue(st, staffeln, alt, bekannt)
        val auftraege = folgen.map { f ->
            val inStaffel = staffeln[f.staffel].orEmpty()
            Auftrag(
                serie = serie.titel.ifBlank { st.serie }, serieUrl = st.serieUrl, cover = serie.cover ?: st.cover,
                staffel = f.staffel, folge = f.nummer, istFilm = false,
                titel = f.titel, url = f.url, sprache = st.sprache, hoster = null,
                stellen = Benennung.stellen(inStaffel.size, inStaffel.maxOfOrNull { it.nummer } ?: 0),
            )
        }
        val n = if (auftraege.isEmpty()) 0 else app.db.einreihen(auftraege)
        // Die Marke erst nach dem Einreihen weiterschieben, sonst gingen Folgen bei einem Fehler verloren.
        marke(staffeln, st.sprache)?.let { m -> app.db.markeSetzen(st.serieUrl, st.sprache, if (alt == null) m else maxOf(alt, m, folgenFolge)) }
        return n
    }

    private fun melden(app: App, b: Bericht) {
        val text = b.serien.joinToString(", ")
        val n = NotificationCompat.Builder(app, App.KANAL_AUTOSYNC)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(app.resources.getQuantityString(R.plurals.autosync_neu, b.neu, b.neu))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(app.oeffnenIntent(MainActivity.TAB_DOWNLOADS))
            .setAutoCancel(true)
            .build()
        runCatching { app.getSystemService(NotificationManager::class.java).notify(App.ID_AUTOSYNC, n) }
    }

    private const val ARBEIT = "autosync"

    /** Plant den regelmäßigen Lauf nach den Einstellungen oder nimmt ihn heraus. */
    fun planen(context: Context) {
        val e = (context.applicationContext as App).einstellungen
        val wm = WorkManager.getInstance(context)
        if (!e.autoSync) {
            wm.cancelUniqueWork(ARBEIT)
            return
        }
        val bedingungen = Constraints.Builder()
            .setRequiredNetworkType(if (e.nurWlan) NetworkType.UNMETERED else NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build()
        val anfrage = PeriodicWorkRequestBuilder<AutoSyncArbeit>(e.autoSyncStunden.toLong(), TimeUnit.HOURS)
            .setConstraints(bedingungen)
            .build()
        wm.enqueueUniquePeriodicWork(ARBEIT, ExistingPeriodicWorkPolicy.UPDATE, anfrage)
    }
}

/** Der geplante Lauf im Hintergrund. */
class AutoSyncArbeit(context: Context, parameter: WorkerParameters) : CoroutineWorker(context, parameter) {
    override suspend fun doWork(): Result {
        val app = applicationContext as App
        if (!app.einstellungen.autoSync) return Result.success()
        AutoSync.lauf(app, still = true)
        return Result.success()
    }
}
