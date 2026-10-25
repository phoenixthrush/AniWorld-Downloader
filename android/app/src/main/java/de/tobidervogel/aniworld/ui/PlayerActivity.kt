package de.tobidervogel.aniworld.ui

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.annotation.OptIn
import androidx.core.content.res.ResourcesCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import de.tobidervogel.aniworld.hoster.Stream
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.DefaultTimeBar
import androidx.media3.ui.PlayerView
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Status
import de.tobidervogel.aniworld.site.AniSkip
import de.tobidervogel.aniworld.site.Folgeninfo
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.site.Sprung
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.File

/**
 * Vollbild-Player für Streams und geladene Dateien. Merkt sich die Stelle pro Folge
 * (Schlüssel = Folgen-URL) und spielt bei geladenen Folgen die nächste direkt weiter.
 */
@OptIn(UnstableApi::class)
class PlayerActivity : ComponentActivity() {
    private var player: ExoPlayer? = null
    private lateinit var ansicht: PlayerView
    private lateinit var titelText: TextView
    private lateinit var sprungKnopf: TextView
    private var schluessel = ""
    private var spruenge: List<Sprung> = emptyList()
    private val uebersprungen = HashSet<Sprung>()
    private var steuerungSichtbar = false
    private var sprungSuche: Job? = null
    private val takt = Handler(Looper.getMainLooper())
    private val merken = object : Runnable {
        override fun run() {
            positionSichern()
            takt.postDelayed(this, 5_000)
        }
    }
    private val spaehen = object : Runnable {
        override fun run() {
            sprungPruefen()
            takt.postDelayed(this, 400)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }

        val dp = { v: Int -> TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt() }
        val wurzel = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        ansicht = PlayerView(this).apply {
            setShowNextButton(false)
            setShowPreviousButton(false)
            controllerShowTimeoutMs = 2_500
            // Zeitleiste im Blau der App statt im Standard-Weiß.
            findViewById<DefaultTimeBar>(androidx.media3.ui.R.id.exo_progress)?.apply {
                setPlayedColor(0xFF2563EB.toInt())
                setScrubberColor(0xFF6EA8FE.toInt())
                setBufferedColor(0x66FFFFFF)
            }
        }
        wurzel.addView(ansicht, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        titelText = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            typeface = ResourcesCompat.getFont(this@PlayerActivity, R.font.inter)
            setPadding(dp(24), dp(16), dp(24), dp(16))
            maxLines = 1
        }
        wurzel.addView(titelText, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP or Gravity.START))

        // Mit AniSkip-Zeiten: "Opening überspringen" genau während des Openings.
        // Ohne: "Opening +85 s" bei eingeblendeter Steuerung (Openings dauern fast immer 85–90 s).
        sprungKnopf = TextView(this).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(dp(18), dp(11), dp(18), dp(11))
            background = GradientDrawable().apply { cornerRadius = dp(10).toFloat(); setColor(0xE6111116.toInt()); setStroke(dp(1), 0x59FFFFFF) }
            typeface = ResourcesCompat.getFont(this@PlayerActivity, R.font.inter)
            setOnClickListener { springen() }
            visibility = View.GONE
        }
        wurzel.addView(sprungKnopf, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.END).apply {
            setMargins(0, 0, dp(24), dp(92))
        })
        ansicht.setControllerVisibilityListener(PlayerView.ControllerVisibilityListener { v ->
            titelText.visibility = v
            steuerungSichtbar = v == View.VISIBLE
            sprungPruefen()
        })
        setContentView(wurzel)

        val uri = intent.getStringExtra(EXTRA_URI) ?: return finish()
        val namen = intent.getStringArrayExtra(EXTRA_KOPF_NAMEN).orEmpty()
        val werte = intent.getStringArrayExtra(EXTRA_KOPF_WERTE).orEmpty()
        val kopf = namen.zip(werte).toMap()
        abspielen(uri, intent.getStringExtra(EXTRA_TITEL).orEmpty(), kopf, intent.getStringExtra(EXTRA_SCHLUESSEL).orEmpty(), info(intent),
            intent.getStringExtra(EXTRA_TON), intent.getBooleanExtra(EXTRA_HLS, false))
    }

    private fun abspielen(
        uri: String, titel: String, kopf: Map<String, String>, schluessel: String, info: Folgeninfo?, ton: String? = null, hls: Boolean = false,
    ) {
        player?.release()
        this.schluessel = schluessel
        titelText.text = titel
        val app = App.self
        spruenge = emptyList()
        uebersprungen.clear()
        sprungSuche?.cancel()
        if (info != null && app.einstellungen.aniskip) {
            sprungSuche = lifecycleScope.launch {
                spruenge = AniSkip.fuer(info)
                sprungPruefen()
            }
        }
        val http = OkHttpDataSource.Factory(app.netz.client).setDefaultRequestProperties(kopf)
        val quelle = DefaultDataSource.Factory(this, http)
        val p = ExoPlayer.Builder(this)
            .setMediaSourceFactory(DefaultMediaSourceFactory(quelle))
            .setSeekBackIncrementMs(10_000)
            .setSeekForwardIncrementMs(10_000)
            .build()
        player = p
        ansicht.player = p
        // VOE liefert Deutsch und Englisch als getrennte Tonspuren ohne Vorgabe; ohne das hier
        // nähme der Player die Sprache des Handys, also auch bei „Englisch“ den deutschen Ton.
        if (ton != null) {
            p.trackSelectionParameters = p.trackSelectionParameters.buildUpon().setPreferredAudioLanguage(ton).build()
        }

        val ziel = if (uri.startsWith("/")) Uri.fromFile(File(uri)) else Uri.parse(uri)
        val item = MediaItem.Builder().setUri(ziel)
        if (hls || Stream.istHls(uri)) item.setMimeType(MimeTypes.APPLICATION_M3U8)
        p.setMediaItem(item.build())

        app.db.position(schluessel)?.let { (ms, dauer) ->
            // Nur fortsetzen, wenn nicht ganz am Anfang oder schon fast am Ende.
            if (ms > 15_000 && (dauer <= 0 || ms < dauer - 60_000)) p.seekTo(ms)
        }
        p.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) amEnde()
            }

            override fun onPlayerError(error: PlaybackException) {
                Protokoll.fehler("Player: ${error.errorCodeName}", error)
                Toast.makeText(this@PlayerActivity, getString(R.string.wiedergabe_fehler, error.errorCodeName), Toast.LENGTH_LONG).show()
            }
        })
        p.prepare()
        p.playWhenReady = true
    }

    private fun amEnde() {
        val p = player ?: return
        App.self.db.positionMerken(schluessel, p.duration.coerceAtLeast(0), p.duration.coerceAtLeast(0))
        val n = naechsteGeladene(schluessel)
        if (n == null) {
            finish()
            return
        }
        abspielen(n.datei!!, n.anzeige, emptyMap(), n.url, n.folgeninfo)
    }

    /** Knopf zeigen oder (mit „automatisch überspringen“) gleich springen. */
    private fun sprungPruefen() {
        val p = player ?: return
        val pos = p.currentPosition
        val jetzt = spruenge.firstOrNull { pos >= it.vonMs && pos < it.bisMs - 1_000 }
        when {
            jetzt != null && App.self.einstellungen.aniskipAuto && jetzt !in uebersprungen -> {
                // Nur einmal pro Abschnitt: Wer zurückspult, will das Opening sehen.
                uebersprungen += jetzt
                p.seekTo(jetzt.bisMs)
                Toast.makeText(this, getString(R.string.uebersprungen, jetzt.name), Toast.LENGTH_SHORT).show()
                sprungKnopf.visibility = View.GONE
            }
            jetzt != null -> {
                sprungKnopf.text = getString(R.string.ueberspringen, jetzt.name)
                sprungKnopf.visibility = View.VISIBLE
            }
            spruenge.isEmpty() && steuerungSichtbar -> {
                sprungKnopf.text = getString(R.string.opening_plus)
                sprungKnopf.visibility = View.VISIBLE
            }
            else -> sprungKnopf.visibility = View.GONE
        }
    }

    private fun springen() {
        val p = player ?: return
        val pos = p.currentPosition
        val jetzt = spruenge.firstOrNull { pos >= it.vonMs && pos < it.bisMs }
        if (jetzt != null) {
            uebersprungen += jetzt
            p.seekTo(jetzt.bisMs)
        } else {
            p.seekTo(pos + 85_000)
        }
        sprungPruefen()
    }

    private fun naechsteGeladene(url: String): Auftrag? {
        val db = App.self.db
        val alle = db.alle().filter { it.status == Status.FERTIG && it.datei?.let { d -> File(d).exists() } == true }
        val jetzt = alle.firstOrNull { it.url == url } ?: return null
        return alle.filter { it.serieUrl == jetzt.serieUrl && it.istFilm == jetzt.istFilm }
            .firstOrNull {
                (it.staffel == jetzt.staffel && it.folge == jetzt.folge + 1) ||
                    (it.staffel == jetzt.staffel + 1 && it.folge == 1)
            }
    }

    private fun positionSichern() {
        val p = player ?: return
        if (schluessel.isEmpty() || p.duration <= 0) return
        App.self.db.positionMerken(schluessel, p.currentPosition, p.duration)
    }

    override fun onStart() {
        super.onStart()
        takt.postDelayed(merken, 5_000)
        takt.post(spaehen)
    }

    override fun onStop() {
        takt.removeCallbacks(merken)
        takt.removeCallbacks(spaehen)
        positionSichern()
        player?.pause()
        super.onStop()
    }

    override fun onDestroy() {
        player?.release()
        player = null
        super.onDestroy()
    }

    companion object {
        private const val EXTRA_URI = "uri"
        private const val EXTRA_HLS = "hls"
        private const val EXTRA_TITEL = "titel"
        private const val EXTRA_SCHLUESSEL = "schluessel"
        private const val EXTRA_KOPF_NAMEN = "kopfNamen"
        private const val EXTRA_KOPF_WERTE = "kopfWerte"
        private const val EXTRA_SERIE_URL = "serieUrl"
        private const val EXTRA_SERIE = "serie"
        private const val EXTRA_STAFFEL = "staffel"
        private const val EXTRA_FOLGE = "folge"
        private const val EXTRA_FILM = "film"
        private const val EXTRA_TON = "ton"

        /** Sprachkürzel für die Tonspur-Wahl im Player. */
        fun tonsprache(s: Sprache) = when (s) {
            Sprache.DE_DUB -> "de"
            Sprache.EN_DUB -> "en"
            else -> "ja"
        }

        /**
         * @param uri  Pfad einer geladenen Datei oder eine Stream-Adresse
         * @param info Serie/Staffel/Folge für die AniSkip-Zeiten (null: ohne)
         * @param hls  Stream ist sicher eine Playlist (siehe [Stream.hls])
         */
        fun starten(
            ctx: Context, uri: String, titel: String, kopf: Map<String, String>, schluessel: String, info: Folgeninfo?,
            sprache: Sprache? = null, hls: Boolean = false,
        ) {
            val i = Intent(ctx, PlayerActivity::class.java)
                .putExtra(EXTRA_URI, uri)
                .putExtra(EXTRA_HLS, hls)
                .putExtra(EXTRA_TITEL, titel)
                .putExtra(EXTRA_SCHLUESSEL, schluessel)
                .putExtra(EXTRA_KOPF_NAMEN, kopf.keys.toTypedArray())
                .putExtra(EXTRA_KOPF_WERTE, kopf.values.toTypedArray())
            if (sprache != null) i.putExtra(EXTRA_TON, tonsprache(sprache))
            if (info != null) {
                i.putExtra(EXTRA_SERIE_URL, info.serieUrl).putExtra(EXTRA_SERIE, info.serie)
                    .putExtra(EXTRA_STAFFEL, info.staffel).putExtra(EXTRA_FOLGE, info.folge).putExtra(EXTRA_FILM, info.istFilm)
            }
            ctx.startActivity(i)
        }

        private fun info(i: Intent): Folgeninfo? {
            val url = i.getStringExtra(EXTRA_SERIE_URL) ?: return null
            return Folgeninfo(url, i.getStringExtra(EXTRA_SERIE).orEmpty(), i.getIntExtra(EXTRA_STAFFEL, 0),
                i.getIntExtra(EXTRA_FOLGE, 0), i.getBooleanExtra(EXTRA_FILM, false))
        }
    }
}
