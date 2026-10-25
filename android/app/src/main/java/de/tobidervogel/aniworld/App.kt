package de.tobidervogel.aniworld

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.webkit.CookieManager
import androidx.annotation.StringRes
import androidx.core.app.NotificationCompat
import androidx.work.Configuration
import coil.ImageLoader
import coil.ImageLoaderFactory
import de.tobidervogel.aniworld.download.AutoSync
import de.tobidervogel.aniworld.download.Datenbank
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.site.Anbieter
import de.tobidervogel.aniworld.site.AniWorld
import de.tobidervogel.aniworld.site.BurningSeries
import de.tobidervogel.aniworld.site.FilmPalast
import de.tobidervogel.aniworld.site.Filmo
import de.tobidervogel.aniworld.site.Kinox
import de.tobidervogel.aniworld.site.MegaKino
import de.tobidervogel.aniworld.site.Moflix
import de.tobidervogel.aniworld.site.SerienStream

/**
 * Text aus den Ressourcen für Code ohne Context (Fehlermeldungen, Fortschritt). In reinen JVM-Tests
 * gibt es keine App; dann steht dort der Name der Ressource, damit Tests nicht abstürzen.
 */
fun tr(@StringRes id: Int, vararg args: Any): String =
    if (App.bereit) App.self.getString(id, *args) else "#$id ${args.joinToString(" ")}".trim()

/**
 * WorkManager (Auto-Sync) startet hier bei Bedarf statt über seinen Start-Provider: So ist er auch
 * dann bereit, wenn onCreate ihn schon braucht (Robolectric, Neustart in einem anderen Prozess).
 */
class App : Application(), ImageLoaderFactory, Configuration.Provider {
    override val workManagerConfiguration: Configuration get() = Configuration.Builder().build()

    lateinit var einstellungen: Einstellungen
    lateinit var netz: Netz
    lateinit var aniworld: AniWorld
    lateinit var serienstream: SerienStream
    lateinit var filmo: Filmo
    lateinit var filmpalast: FilmPalast
    lateinit var burningseries: BurningSeries
    lateinit var kinox: Kinox
    lateinit var megakino: MegaKino
    lateinit var moflix: Moflix
    lateinit var db: Datenbank

    val anbieter: List<Anbieter> get() = listOf(aniworld, serienstream, burningseries, kinox, megakino, moflix, filmo, filmpalast)

    /** Zuständige Seite für eine Adresse; unbekannte Adressen gehen an AniWorld. */
    fun anbieter(url: String): Anbieter = anbieter.firstOrNull { it.passt(url) } ?: aniworld

    override fun onCreate() {
        super.onCreate()
        self = this
        Protokoll.init(filesDir)
        // CookieManager einmal auf dem Hauptthread holen; danach geht er auch aus dem Netz-Thread.
        CookieManager.getInstance()
        einstellungen = Einstellungen(this)
        netz = Netz(this, einstellungen)
        aniworld = AniWorld(netz)
        serienstream = SerienStream(netz)
        filmo = Filmo(netz)
        filmpalast = FilmPalast(netz)
        burningseries = BurningSeries(netz)
        kinox = Kinox(netz)
        megakino = MegaKino(netz)
        moflix = Moflix(netz)
        db = Datenbank(this)

        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(KANAL_DOWNLOADS, getString(R.string.kanal_downloads), NotificationManager.IMPORTANCE_LOW)
        )
        nm.createNotificationChannel(
            NotificationChannel(KANAL_HINWEISE, getString(R.string.kanal_hinweise), NotificationManager.IMPORTANCE_HIGH)
        )
        nm.createNotificationChannel(
            NotificationChannel(KANAL_AUTOSYNC, getString(R.string.kanal_autosync), NotificationManager.IMPORTANCE_DEFAULT)
        )
        AutoSync.planen(this)
    }

    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .okHttpClient { netz.client }
        .crossfade(true)
        .build()

    fun oeffnenIntent(tab: String? = null): PendingIntent {
        val i = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (tab != null) i.putExtra(MainActivity.EXTRA_TAB, tab)
        return PendingIntent.getActivity(this, tab.hashCode(), i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    /** Läuft ein Download im Hintergrund in die Schutzseite, holt diese Meldung den Nutzer in die App. */
    fun meldeCheck() {
        val n = NotificationCompat.Builder(this, KANAL_HINWEISE)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(getString(R.string.check_titel))
            .setContentText(getString(R.string.check_text))
            .setContentIntent(oeffnenIntent())
            .setAutoCancel(true)
            .build()
        runCatching { getSystemService(NotificationManager::class.java).notify(ID_CHECK, n) }
    }

    fun checkMeldungWeg() {
        getSystemService(NotificationManager::class.java).cancel(ID_CHECK)
    }

    companion object {
        lateinit var self: App
        val bereit get() = ::self.isInitialized
        const val KANAL_DOWNLOADS = "downloads"
        const val KANAL_HINWEISE = "hinweise"
        const val KANAL_AUTOSYNC = "autosync"
        const val ID_CHECK = 2
        const val ID_AUTOSYNC = 4
    }
}
