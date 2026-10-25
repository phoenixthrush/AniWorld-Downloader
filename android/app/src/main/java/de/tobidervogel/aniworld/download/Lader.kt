package de.tobidervogel.aniworld.download

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.hoster.Aufloeser
import de.tobidervogel.aniworld.hoster.Stream
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr
import de.tobidervogel.aniworld.ui.Freigaben
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import kotlin.coroutines.coroutineContext

/** Zwischenstand eines laufenden Auftrags für Oberfläche und Benachrichtigung. */
data class Live(val text: String, val anteil: Float?, val bytes: Long, val tempo: Long)

object Speicher {
    /** Zählt hoch, wenn sich der Zugriff geändert haben kann (zurück aus den Einstellungen, Dialog beantwortet). */
    val stand = MutableStateFlow(0)

    /**
     * Darf die App in den gewählten Ordner schreiben? Ab Android 11 heißt das „Zugriff auf alle
     * Dateien“, davor reicht die alte Speicherberechtigung (Android 10 mit requestLegacyExternalStorage).
     */
    fun vollzugriff(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Environment.isExternalStorageManager()
        else ContextCompat.checkSelfPermission(App.self, Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED

    /** Die passende Freigabe öffnen: Einstellungsseite ab Android 11, sonst den Berechtigungsdialog. */
    fun zugriffAnfragen(activity: Activity) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Freigaben.oeffnen(
                activity,
                Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:${activity.packageName}")),
                Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
            )
        } else {
            ActivityCompat.requestPermissions(activity, arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), 2)
        }
    }

    /** Ohne „Zugriff auf alle Dateien“ landet alles in Android/media der App (auch für die Galerie sichtbar). */
    @Suppress("DEPRECATION")
    fun basis(app: App): File =
        if (vollzugriff()) File(app.einstellungen.ordner)
        else File(app.externalMediaDirs.firstOrNull() ?: app.getExternalFilesDir(null) ?: app.filesDir, "AniWorld")

    fun arbeitsordner(app: App, id: Long) = File(app.getExternalFilesDir(null) ?: app.filesDir, "arbeit/$id")
}

/** Führt einen Auftrag aus: Folgenseite → Hoster → Stream → Datei. */
class Lader(private val app: App) {

    private class Tempo {
        private val proben = ArrayDeque<Pair<Long, Long>>()
        @Synchronized
        fun messen(gesamt: Long): Long {
            val jetzt = System.currentTimeMillis()
            proben.addLast(jetzt to gesamt)
            while (proben.size > 2 && jetzt - proben.first().first > 5_000) proben.removeFirst()
            val (t0, b0) = proben.first()
            val dt = jetzt - t0
            return if (dt < 500) 0 else (gesamt - b0) * 1000 / dt
        }
    }

    suspend fun ausfuehren(a: Auftrag, melde: (Live) -> Unit): Pair<File, String> {
        val ordner = Benennung.ordner(Speicher.basis(app), a)
        if (!ordner.isDirectory && !ordner.mkdirs()) {
            throw IOException(tr(R.string.e_ordner, ordner.path))
        }
        val name = Benennung.name(a)
        listOf("mp4", "ts").map { File(ordner, "$name.$it") }.firstOrNull { it.length() > 0 }?.let {
            return it to tr(R.string.schon_vorhanden)
        }
        if (StatFs(ordner.path).availableBytes < 2L * 1024 * 1024 * 1024) {
            throw IOException(tr(R.string.e_platz))
        }

        melde(Live(tr(R.string.folgenseite_lesen), null, 0, 0))
        val links = app.anbieter(a.url).links(a.url)
        val versucht = HashSet<String>()
        var letzter: Exception? = null
        val arbeit = Speicher.arbeitsordner(app, a.id)
        // Obergrenze nur als Sicherung; normal endet die Schleife, wenn der Auflöser keinen Hoster mehr hat.
        repeat(8) {
            val stream = try {
                Aufloeser.stream(a.url, links, a.sprache, a.hoster, versucht) { melde(Live(it, null, 0, 0)) }
            } catch (e: NetzFehler) {
                // Alle Hoster durch: lieber den Fehler des letzten echten Downloads zeigen.
                throw letzter ?: e
            }
            try {
                arbeit.mkdirs()
                val (datei, info) = if (stream.istHls) hls(stream, a, arbeit, ordner, name, melde)
                else direkt(stream, ordner, name, melde)
                arbeit.deleteRecursively()
                MediaScannerConnection.scanFile(app, arrayOf(datei.path), null, null)
                return datei to info
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // Pausiert während des Umpackens: Das kommt als IOException an. Dann die geladenen Teile
                // behalten und abbrechen, statt sie zu löschen und den nächsten Hoster zu versuchen.
                currentCoroutineContext().ensureActive()
                Protokoll.fehler("${a.kuerzel} über ${stream.hoster} fehlgeschlagen", e)
                letzter = e
                versucht += stream.hoster.substringBefore(" (")
                arbeit.deleteRecursively()
            }
        }
        throw letzter ?: IOException(tr(R.string.e_download))
    }

    // ------------------------------------------------------------ HLS

    private suspend fun text(url: String, kopf: Map<String, String>): String = withContext(Dispatchers.IO) {
        val b = Request.Builder().url(url)
        kopf.forEach { (k, v) -> b.header(k, v) }
        app.netz.client.newCall(b.build()).execute().use { r ->
            if (!r.isSuccessful) throw IOException("Playlist: HTTP ${r.code}")
            r.body?.string().orEmpty()
        }
    }

    private class Teil(val datei: File, val seg: Hls.Segment)

    private suspend fun hls(
        stream: Stream, a: Auftrag, arbeit: File, ordner: File, name: String, melde: (Live) -> Unit,
    ): Pair<File, String> {
        val kopf = stream.header
        val ersterText = text(stream.url, kopf)
        var medienUrl = stream.url
        var medienText = ersterText
        var tonUrl: String? = null
        var hoehe = 0
        if (Hls.istMaster(ersterText)) {
            val m = Hls.master(ersterText, stream.url)
            val v = Hls.beste(m) ?: throw Hls.HlsNichtUnterstuetzt(tr(R.string.e_hls_varianten))
            hoehe = v.hoehe
            medienUrl = v.url
            medienText = text(v.url, kopf)
            tonUrl = Hls.tonspur(m, v, Hls.sprachkuerzel(a.sprache))?.url
        }
        val video = Hls.medien(medienText, medienUrl)
        val ton = tonUrl?.let { Hls.medien(text(it, kopf), it) }
        val info = stream.hoster + " · " + (if (hoehe > 0) "${hoehe}p" else "HLS")

        val teile = ArrayList<Teil>()
        video.init?.let { teile += Teil(File(arbeit, "v_init"), it) }
        video.segmente.forEachIndexed { i, s -> teile += Teil(File(arbeit, "v_%05d".format(i)), s) }
        ton?.init?.let { teile += Teil(File(arbeit, "a_init"), it) }
        ton?.segmente?.forEachIndexed { i, s -> teile += Teil(File(arbeit, "a_%05d".format(i)), s) }

        // Reste eines abgebrochenen Laufs nur weiterverwenden, wenn die Playlist gleich aufgebaut ist.
        val marke = File(arbeit, "playlist.txt")
        val kennung = "${stream.hoster}|${hoehe}|${teile.size}"
        if (marke.exists() && marke.readText() != kennung) {
            arbeit.listFiles()?.forEach { it.delete() }
        }
        marke.writeText(kennung)

        val videoDatei = File(arbeit, if (video.init != null) "video.mp4" else "video.ts")
        val tonDatei = ton?.let { File(arbeit, if (it.init != null) "ton.mp4" else "ton.ts") }
        // Nach einer Pause beim Umpacken liegen die Teile schon zusammengesetzt da: nicht alles neu laden.
        val zusammen = File(arbeit, "zusammengesetzt")
        val bytes = AtomicLong(0)
        if (zusammen.exists() && videoDatei.exists() && (tonDatei == null || tonDatei.exists())) {
            bytes.set(videoDatei.length() + (tonDatei?.length() ?: 0))
        } else {
            val gesamt = teile.size
            val fertig = AtomicInteger(teile.count { it.datei.exists() })
            bytes.set(teile.filter { it.datei.exists() }.sumOf { it.datei.length() })
            val tempo = Tempo()
            val schluessel = ConcurrentHashMap<String, ByteArray>()
            val sperre = Semaphore(app.einstellungen.segmente)
            melde(Live(tr(R.string.laedt, info), fertig.get().toFloat() / gesamt, bytes.get(), 0))

            coroutineScope {
                teile.filter { !it.datei.exists() }.map { t ->
                    async(Dispatchers.IO) {
                        sperre.withPermit {
                            val n = segment(t, kopf, schluessel)
                            val b = bytes.addAndGet(n)
                            val f = fertig.incrementAndGet()
                            melde(Live(tr(R.string.teile, info, f, gesamt), f.toFloat() / gesamt, b, tempo.messen(b)))
                        }
                    }
                }.awaitAll()
            }

            melde(Live(tr(R.string.zusammensetzen), null, bytes.get(), 0))
            zusammensetzen(teile.filter { it.datei.name.startsWith("v_") }.map { it.datei }, videoDatei)
            if (tonDatei != null) zusammensetzen(teile.filter { it.datei.name.startsWith("a_") }.map { it.datei }, tonDatei)
            zusammen.writeText("ok")
        }

        val ziel = File(ordner, "$name.mp4")
        // fMP4 ohne getrennten Ton ist schon eine gültige MP4.
        if (video.init != null && tonDatei == null) {
            verschieben(videoDatei, ziel)
            return ziel to info
        }
        if (app.einstellungen.mp4 || tonDatei != null) {
            melde(Live(tr(R.string.umpacken), null, bytes.get(), 0))
            val teil = File(ordner, ".$name.mp4.part")
            val ctx = coroutineContext
            try {
                withContext(Dispatchers.IO) { Umpacker.nachMp4(videoDatei, tonDatei, teil) { !ctx.isActive } }
                if (!teil.renameTo(ziel)) throw IOException(tr(R.string.e_umbenennen))
                return ziel to info
            } catch (e: CancellationException) {
                teil.delete()
                throw e
            } catch (e: Exception) {
                teil.delete()
                // Abgebrochen statt kaputt: nicht als .ts „fertig“ melden, sondern die Pause durchreichen.
                ctx.ensureActive()
                if (tonDatei != null) throw IOException(tr(R.string.e_umpacken_ton, e.message.orEmpty()), e)
                Protokoll.fehler("Umpacken nach MP4 fehlgeschlagen, behalte .ts", e)
            }
        }
        val ts = File(ordner, "$name.ts")
        verschieben(videoDatei, ts)
        return ts to "$info · TS"
    }

    private suspend fun segment(t: Teil, kopf: Map<String, String>, schluessel: ConcurrentHashMap<String, ByteArray>): Long {
        var versuch = 0
        while (true) {
            coroutineContext.ensureActive()
            try {
                val b = Request.Builder().url(t.seg.url)
                kopf.forEach { (k, v) -> b.header(k, v) }
                t.seg.bereich?.let { b.header("Range", "bytes=${it.first}-${it.last}") }
                var daten = app.netz.client.newCall(b.build()).execute().use { r ->
                    if (!r.isSuccessful) throw IOException("Segment: HTTP ${r.code}")
                    r.body?.bytes() ?: throw IOException(tr(R.string.e_segment_leer))
                }
                t.seg.schluessel?.let { k ->
                    val url = k.url ?: throw IOException(tr(R.string.e_schluessel_adresse))
                    val key = schluessel[url] ?: holeSchluessel(url, kopf).also { schluessel[url] = it }
                    daten = aes(daten, key, k.iv ?: Hls.ivAusNummer(t.seg.nr))
                }
                val tmp = File(t.datei.path + ".part")
                tmp.writeBytes(daten)
                if (!tmp.renameTo(t.datei)) throw IOException(tr(R.string.e_segment_speichern))
                return daten.size.toLong()
            } catch (e: IOException) {
                if (++versuch >= 4) throw e
                delay(1_500L * versuch)
            }
        }
    }

    private fun holeSchluessel(url: String, kopf: Map<String, String>): ByteArray {
        val b = Request.Builder().url(url)
        kopf.forEach { (k, v) -> b.header(k, v) }
        return app.netz.client.newCall(b.build()).execute().use { r ->
            if (!r.isSuccessful) throw IOException(tr(R.string.e_schluessel_http, r.code))
            r.body?.bytes()?.takeIf { it.size == 16 } ?: throw IOException(tr(R.string.e_schluessel_16))
        }
    }

    private fun aes(daten: ByteArray, key: ByteArray, iv: ByteArray): ByteArray {
        val c = Cipher.getInstance("AES/CBC/PKCS5Padding")
        c.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
        return c.doFinal(daten)
    }

    /** Hängt die Teile in Reihenfolge aneinander und löscht sie dabei, damit der Platz nicht doppelt belegt wird. */
    private suspend fun zusammensetzen(teile: List<File>, ziel: File) = withContext(Dispatchers.IO) {
        FileOutputStream(ziel).use { out ->
            for (t in teile) {
                ensureActive()
                t.inputStream().use { it.copyTo(out, 1 shl 16) }
            }
        }
        teile.forEach { it.delete() }
    }

    private fun verschieben(von: File, nach: File) {
        if (von.renameTo(nach)) return
        // Über Dateisystemgrenzen geht renameTo nicht; dann kopieren.
        val teil = File(nach.parentFile, ".${nach.name}.part")
        von.copyTo(teil, overwrite = true)
        if (!teil.renameTo(nach)) throw IOException(tr(R.string.e_ablegen, nach.path))
        von.delete()
    }

    // ------------------------------------------------------------ Direkt (MP4)

    private suspend fun direkt(stream: Stream, ordner: File, name: String, melde: (Live) -> Unit): Pair<File, String> =
        withContext(Dispatchers.IO) {
            val teil = File(ordner, ".$name.mp4.part")
            val ziel = File(ordner, "$name.mp4")
            var vorhanden = if (teil.exists()) teil.length() else 0L
            val b = Request.Builder().url(stream.url)
            stream.header.forEach { (k, v) -> b.header(k, v) }
            if (vorhanden > 0) b.header("Range", "bytes=$vorhanden-")
            val tempo = Tempo()
            var gesamtBekannt = -1L
            app.netz.client.newCall(b.build()).execute().use { r ->
                if (!r.isSuccessful) throw IOException("Video: HTTP ${r.code}")
                val typ = r.header("Content-Type").orEmpty()
                if (typ.startsWith("text/")) throw IOException(tr(R.string.e_webseite))
                val anhaengen = r.code == 206 && vorhanden > 0
                if (!anhaengen) vorhanden = 0
                val laenge = r.body?.contentLength() ?: -1
                val gesamt = if (laenge > 0) laenge + vorhanden else -1
                gesamtBekannt = gesamt
                val ein = r.body?.byteStream() ?: throw IOException(tr(R.string.e_video_leer))
                FileOutputStream(teil, anhaengen).use { out ->
                    val puffer = ByteArray(1 shl 18)
                    var geladen = vorhanden
                    var zuletzt = 0L
                    while (true) {
                        ensureActive()
                        val n = ein.read(puffer)
                        if (n < 0) break
                        out.write(puffer, 0, n)
                        geladen += n
                        val jetzt = System.currentTimeMillis()
                        if (jetzt - zuletzt > 500) {
                            zuletzt = jetzt
                            melde(Live(tr(R.string.laedt, stream.hoster), if (gesamt > 0) geladen.toFloat() / gesamt else null, geladen, tempo.messen(geladen)))
                        }
                    }
                }
            }
            // Verbindung vorzeitig zu: Teil behalten, der nächste Versuch setzt mit Range fort.
            if (gesamtBekannt > 0 && teil.length() < gesamtBekannt) {
                throw IOException(tr(R.string.e_unvollstaendig, teil.length() / 1024, gesamtBekannt / 1024))
            }
            // Werbeclips und Fehlerseiten sind winzig; eine echte Folge hat deutlich mehr.
            if (teil.length() < 15L * 1024 * 1024) {
                val groesse = teil.length()
                teil.delete()
                throw IOException(tr(R.string.e_zu_klein, groesse / 1024))
            }
            if (!teil.renameTo(ziel)) throw IOException(tr(R.string.e_umbenennen))
            ziel to "${stream.hoster} · MP4"
        }
}
