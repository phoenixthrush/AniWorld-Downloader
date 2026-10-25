package de.tobidervogel.aniworld

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.VideoLibrary
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import de.tobidervogel.aniworld.download.DownloadService
import de.tobidervogel.aniworld.download.Speicher
import de.tobidervogel.aniworld.download.Status
import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.ui.AblageSeite
import de.tobidervogel.aniworld.ui.BibliothekSeite
import de.tobidervogel.aniworld.ui.BrowserFenster
import de.tobidervogel.aniworld.ui.EinrichtungSeite
import de.tobidervogel.aniworld.ui.EinstellungenSeite
import de.tobidervogel.aniworld.ui.Farbe
import de.tobidervogel.aniworld.ui.GenreSeite
import de.tobidervogel.aniworld.ui.ProtokollSeite
import de.tobidervogel.aniworld.ui.SerieSeite
import de.tobidervogel.aniworld.ui.StartSeite
import de.tobidervogel.aniworld.ui.StartZustand
import de.tobidervogel.aniworld.ui.SucheSeite
import de.tobidervogel.aniworld.ui.Thema
import de.tobidervogel.aniworld.ui.Trennlinie
import de.tobidervogel.aniworld.ui.WarteschlangeSeite
import de.tobidervogel.aniworld.ui.Ziel
import de.tobidervogel.aniworld.ui.titelAusAdresse
import kotlinx.coroutines.flow.update

class MainActivity : ComponentActivity() {
    private var tab by mutableStateOf(TAB_START)
    private val stapel = mutableStateListOf<Ziel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val start = StartZustand(lifecycleScope, App.self.anbieter)
        verarbeiten(intent)
        setContent {
            Thema {
                // Beim ersten Start die Einrichtung; sie fragt die Berechtigungen mit Erklärung ab.
                App.self.einstellungen.stand.collectAsState().value
                if (App.self.einstellungen.einrichtungFertig) Oberflaeche(start) else EinrichtungSeite { }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        verarbeiten(intent)
    }

    override fun onStart() {
        super.onStart()
        BrowserCheck.appSichtbar = true
        // Wartende Folgen nach einem Neustart oder Absturz, oder von Auto-Sync, wenn Android den Dienst
        // aus dem Hintergrund nicht starten ließ: Jetzt im Vordergrund geht es.
        if (App.self.db.alle().any { it.status == Status.WARTET || it.status == Status.LAEUFT }) DownloadService.starten(this)
    }

    override fun onResume() {
        super.onResume()
        // Zurück aus den Systemeinstellungen oder einem Berechtigungsdialog: Speicherzugriff neu prüfen.
        Speicher.stand.update { it + 1 }
    }

    override fun onStop() {
        BrowserCheck.appSichtbar = false
        super.onStop()
    }

    /** Benachrichtigung (Reiter) oder geteilter/geöffneter aniworld-Link. */
    private fun verarbeiten(i: Intent?) {
        i ?: return
        i.getStringExtra(EXTRA_TAB)?.let { tab = it; stapel.clear() }
        val text = when (i.action) {
            Intent.ACTION_VIEW -> i.dataString
            Intent.ACTION_SEND -> i.getStringExtra(Intent.EXTRA_TEXT)
            else -> null
        } ?: return
        val link = Regex("""https?://(?:www\.)?(?:aniworld\.to/anime/stream|serienstream\.(?:to|cx)/serie|s\.to/serie|filmo\.to/movies|filmpalast\.to/stream|(?:bs\.cine\.to|bs\.to|burning-?series\.(?:io|net|ac|cx))/serie|kino[xsz]\.(?:to|am|click)/Stream|megakino[a-z0-9-]*\.[a-z]{2,}/[a-z0-9-]+|moflix-stream\.xyz/titles)/[^\s"']+""")
            .find(text)?.value ?: return
        val serie = App.self.anbieter(link).serienUrl(link) ?: return
        val staffel = Regex("(?:staffel-|/season/)(\\d+)").find(link)?.groupValues?.get(1)?.toIntOrNull()
        tab = TAB_START
        stapel.clear()
        stapel += Ziel.Serie(serie, titelAusAdresse(serie), null, staffel)
    }

    @Composable
    private fun Oberflaeche(start: StartZustand) {
        val app = App.self
        val oeffnen: (Ziel) -> Unit = { stapel += it }
        val zurueck: () -> Unit = { if (stapel.isNotEmpty()) stapel.removeAt(stapel.lastIndex) }
        BackHandler(enabled = stapel.isNotEmpty()) { zurueck() }
        val stand by app.db.stand.collectAsState()
        val live by DownloadService.live.collectAsState()
        val offen = remember(stand) { app.db.alle().count { it.status == Status.WARTET || it.status == Status.LAEUFT } }

        Scaffold(
            containerColor = Farbe.hintergrund,
            contentWindowInsets = WindowInsets(0),
            bottomBar = {
                Column {
                    Trennlinie()
                    NavigationBar(containerColor = Farbe.nav, tonalElevation = 0.dp) {
                        val farben = NavigationBarItemDefaults.colors(
                            selectedIconColor = Farbe.link,
                            selectedTextColor = Farbe.textStark,
                            indicatorColor = Farbe.akzentFlaeche,
                            unselectedIconColor = Farbe.text3,
                            unselectedTextColor = Farbe.text3,
                        )
                        fun waehlen(t: String) {
                            tab = t
                            stapel.clear()
                        }
                        @Composable
                        fun Reiter(t: String, @StringRes text: Int, icon: ImageVector, zahl: Int = 0) {
                            NavigationBarItem(
                                selected = tab == t,
                                onClick = { waehlen(t) },
                                icon = {
                                    BadgedBox(badge = { if (zahl > 0) Badge(containerColor = Farbe.akzent, contentColor = Color.White) { Text("$zahl") } }) {
                                        Icon(icon, null)
                                    }
                                },
                                label = { Text(stringResource(text), maxLines = 1, style = MaterialTheme.typography.labelSmall) },
                                colors = farben,
                            )
                        }
                        Reiter(TAB_START, R.string.nav_start, Icons.Rounded.Home)
                        Reiter(TAB_DOWNLOADS, R.string.nav_warteschlange, Icons.Rounded.Download, maxOf(offen, live.size))
                        Reiter(TAB_BIBLIOTHEK, R.string.nav_bibliothek, Icons.Rounded.VideoLibrary)
                        Reiter(TAB_EINSTELLUNGEN, R.string.nav_einstellungen, Icons.Rounded.Settings)
                    }
                }
            },
        ) { innen ->
            Box(Modifier.fillMaxSize().padding(innen)) {
                when (val z = stapel.lastOrNull()) {
                    null -> when (tab) {
                        TAB_DOWNLOADS -> WarteschlangeSeite(oeffnen)
                        TAB_BIBLIOTHEK -> BibliothekSeite(oeffnen)
                        TAB_EINSTELLUNGEN -> EinstellungenSeite(oeffnen)
                        else -> StartSeite(start, oeffnen)
                    }
                    is Ziel.Serie -> key(z) { SerieSeite(z, zurueck) }
                    is Ziel.GenreListe -> GenreSeite(z, zurueck, oeffnen)
                    is Ziel.Ablage -> AblageSeite(z, zurueck, oeffnen)
                    Ziel.Suche -> SucheSeite(zurueck, oeffnen)
                    Ziel.ProtokollAnsicht -> ProtokollSeite(zurueck)
                }
            }
        }
        BrowserFenster()
    }

    companion object {
        const val EXTRA_TAB = "tab"
        const val TAB_START = "start"
        const val TAB_DOWNLOADS = "downloads"
        const val TAB_BIBLIOTHEK = "bibliothek"
        const val TAB_EINSTELLUNGEN = "einstellungen"
    }
}
