package de.tobidervogel.aniworld.ui

import android.annotation.SuppressLint
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.text.format.DateUtils
import android.webkit.CookieManager
import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.BuildConfig
import de.tobidervogel.aniworld.Einstellungen
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.download.AutoSync
import de.tobidervogel.aniworld.download.Speicher
import de.tobidervogel.aniworld.site.Sprache
import kotlinx.coroutines.launch

@OptIn(ExperimentalLayoutApi::class)
@SuppressLint("BatteryLife")
@Composable
fun EinstellungenSeite(oeffnen: (Ziel) -> Unit) {
    val app = App.self
    val e = app.einstellungen
    val ctx = LocalContext.current
    // Die Werte liegen in SharedPreferences; der Zähler sorgt dafür, dass nach jeder Änderung neu gezeichnet wird.
    e.stand.collectAsState().value
    Speicher.stand.collectAsState().value
    var ordnerDialog by remember { mutableStateOf(false) }
    var syncLaeuft by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val akkuFrei = Freigaben.akkuFrei(ctx)

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 32.dp)) {
        AppLeiste()
        SeitenTitel(stringResource(R.string.tab_einstellungen))

        Gruppe(stringResource(R.string.speicher)) {
            Zeile(stringResource(R.string.ordner), if (Speicher.vollzugriff()) e.ordner else stringResource(R.string.media_ohne_zugriff)) { ordnerDialog = true }
            Zeile(
                stringResource(R.string.zugriff_alle_dateien),
                if (Speicher.vollzugriff()) stringResource(R.string.erlaubt) else stringResource(R.string.nicht_erlaubt),
            ) {
                ctx.activity()?.let { Speicher.zugriffAnfragen(it) }
            }
            Schalter(stringResource(R.string.mp4), stringResource(R.string.mp4_text), e.mp4) { e.mp4 = it }
        }

        Gruppe(stringResource(R.string.sprache)) {
            FlowRow(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Sprache.entries.forEach { s -> SprachPille(s, e.sprache == s) { e.sprache = s } }
            }
            Text(stringResource(R.string.sprache_hinweis),
                color = Farbe.text3, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
        }

        Gruppe(stringResource(R.string.hoster_reihenfolge)) {
            val liste = e.hosterReihenfolge
            liste.forEachIndexed { i, h ->
                Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${i + 1}", color = Farbe.text3, style = MaterialTheme.typography.labelLarge, modifier = Modifier.width(28.dp))
                    Text(h, Modifier.weight(1f), color = Farbe.textStark)
                    IconButton(enabled = i > 0, onClick = { e.hosterReihenfolge = liste.toMutableList().apply { add(i - 1, removeAt(i)) } }) {
                        Icon(Icons.Rounded.KeyboardArrowUp, stringResource(R.string.hoch), tint = if (i > 0) Farbe.text2 else Farbe.linieHover)
                    }
                    IconButton(enabled = i < liste.lastIndex, onClick = { e.hosterReihenfolge = liste.toMutableList().apply { add(i + 1, removeAt(i)) } }) {
                        Icon(Icons.Rounded.KeyboardArrowDown, stringResource(R.string.runter), tint = if (i < liste.lastIndex) Farbe.text2 else Farbe.linieHover)
                    }
                }
            }
            Schalter(stringResource(R.string.browser_weg), stringResource(R.string.browser_weg_text), e.browserWeg) { e.browserWeg = it }
        }

        Gruppe(stringResource(R.string.player)) {
            Schalter("AniSkip", stringResource(R.string.aniskip_text), e.aniskip) { e.aniskip = it }
            Schalter(stringResource(R.string.auto_skip), stringResource(R.string.auto_skip_text), e.aniskipAuto) { e.aniskipAuto = it }
        }

        Gruppe(stringResource(R.string.downloads)) {
            Text(stringResource(R.string.parallel), Modifier.padding(start = 16.dp, top = 8.dp), color = Farbe.textStark)
            Row(Modifier.padding(16.dp, 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                (1..3).forEach { n -> Pille("$n", e.parallel == n) { e.parallel = n } }
            }
            Text(stringResource(R.string.segmente), Modifier.padding(start = 16.dp, top = 4.dp), color = Farbe.textStark)
            Row(Modifier.padding(16.dp, 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(4, 8, 12, 16).forEach { n -> Pille("$n", e.segmente == n) { e.segmente = n } }
            }
            Schalter(stringResource(R.string.nur_wlan), stringResource(R.string.nur_wlan_text), e.nurWlan) { e.nurWlan = it; AutoSync.planen(ctx) }
            Zeile(stringResource(R.string.akku), if (akkuFrei) stringResource(R.string.akku_aus) else stringResource(R.string.akku_an)) {
                if (!akkuFrei) Freigaben.akkuFreigeben(ctx)
            }
        }

        Gruppe(stringResource(R.string.autosync)) {
            Schalter(stringResource(R.string.autosync), stringResource(R.string.autosync_text), e.autoSync) { e.autoSync = it; AutoSync.planen(ctx) }
            if (e.autoSync) {
                Text(stringResource(R.string.autosync_abstand), Modifier.padding(start = 16.dp, top = 4.dp), color = Farbe.textStark)
                Row(Modifier.padding(16.dp, 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Einstellungen.AUTOSYNC_STUNDEN.forEach { h ->
                        Pille(stringResource(R.string.autosync_stunden, h), e.autoSyncStunden == h) { e.autoSyncStunden = h; AutoSync.planen(ctx) }
                    }
                }
            }
            Zeile(stringResource(R.string.autosync_jetzt), if (syncLaeuft) stringResource(R.string.autosync_laeuft) else autoSyncStand(e)) {
                if (!syncLaeuft) {
                    syncLaeuft = true
                    scope.launch {
                        try {
                            // Im Vordergrund darf das Browserfenster aufgehen, falls eine Seite prüft.
                            val b = AutoSync.lauf(app, still = false)
                            if (b == null) Toast.makeText(ctx, ctx.getString(R.string.autosync_laeuft), Toast.LENGTH_SHORT).show()
                        } finally {
                            syncLaeuft = false
                        }
                    }
                }
            }
        }

        Gruppe(stringResource(R.string.netz)) {
            Schalter(stringResource(R.string.doh), stringResource(R.string.doh_text), e.doh) { e.doh = it }
            Zeile(stringResource(R.string.cookies_loeschen), stringResource(R.string.cookies_text)) {
                CookieManager.getInstance().removeAllCookies(null)
                Toast.makeText(ctx, ctx.getString(R.string.cookies_geloescht), Toast.LENGTH_SHORT).show()
            }
        }

        Gruppe(stringResource(R.string.hilfe)) {
            Zeile(stringResource(R.string.einrichtung), stringResource(R.string.einrichtung_text)) { e.einrichtungFertig = false }
            Zeile(stringResource(R.string.protokoll), stringResource(R.string.protokoll_text)) { oeffnen(Ziel.ProtokollAnsicht) }
            Zeile(stringResource(R.string.original), stringResource(R.string.original_text)) {
                runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/phoenixthrush/AniWorld-Downloader"))) }
            }
            Zeile(stringResource(R.string.version), stringResource(R.string.version_text, BuildConfig.VERSION_NAME))
        }
    }

    if (ordnerDialog) {
        var text by remember { mutableStateOf(e.ordner) }
        AlertDialog(
            onDismissRequest = { ordnerDialog = false },
            title = { Text(stringResource(R.string.ordner_dialog), color = Farbe.textStark) },
            text = {
                Column {
                    OutlinedTextField(
                        text, { text = it }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Farbe.akzent,
                            unfocusedBorderColor = Farbe.linie,
                            focusedContainerColor = Farbe.eingabe,
                            unfocusedContainerColor = Farbe.eingabe,
                            cursorColor = Farbe.akzent,
                            focusedTextColor = Farbe.textStark,
                            unfocusedTextColor = Farbe.textStark,
                        ),
                    )
                    TextButton(onClick = { text = Einstellungen.STANDARD_ORDNER }) { Text(stringResource(R.string.standard), color = Farbe.link) }
                }
            },
            confirmButton = { TextButton(onClick = { e.ordner = text; ordnerDialog = false }) { Text(stringResource(R.string.speichern), color = Farbe.link) } },
            dismissButton = { TextButton(onClick = { ordnerDialog = false }) { Text(stringResource(R.string.abbrechen), color = Farbe.text) } },
            containerColor = Farbe.modal,
        )
    }
}

/** Karte wie .settings-card der Web-UI: Überschrift in der Karte, Zeilen durch Linien getrennt. */
/** „Zuletzt: 25.10., 14:02 · 12 Serien geprüft · 3 neue Folgen“ */
@Composable
private fun autoSyncStand(e: Einstellungen): String {
    if (e.autoSyncZuletzt == 0L) return stringResource(R.string.autosync_nie)
    val zeit = DateUtils.formatDateTime(LocalContext.current, e.autoSyncZuletzt, DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_SHOW_TIME or DateUtils.FORMAT_ABBREV_ALL)
    val teile = mutableListOf(
        stringResource(R.string.autosync_zuletzt, zeit),
        pluralStringResource(R.plurals.autosync_geprueft, e.autoSyncGeprueft, e.autoSyncGeprueft),
        pluralStringResource(R.plurals.autosync_neu, e.autoSyncNeu, e.autoSyncNeu),
    )
    if (e.autoSyncFehler > 0) teile += pluralStringResource(R.plurals.autosync_fehler, e.autoSyncFehler, e.autoSyncFehler)
    return teile.joinToString(" · ")
}

@Composable
private fun Gruppe(titel: String, inhalt: @Composable () -> Unit) {
    Column(Modifier.padding(horizontal = 16.dp, vertical = 6.dp).fillMaxWidth().karte().padding(bottom = 6.dp)) {
        Text(titel, color = Farbe.textStark, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 6.dp))
        inhalt()
    }
}

/** Zeile mit Titel und Wert; ohne [onClick] nur zur Anzeige, dann auch ohne Pfeil. */
@Composable
private fun Zeile(titel: String, wert: String, onClick: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(titel, color = Farbe.textStark, style = MaterialTheme.typography.bodyMedium)
            Text(wert, color = Farbe.text3, style = MaterialTheme.typography.bodySmall)
        }
        if (onClick != null) Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, null, tint = Farbe.text3)
    }
}

@Composable
private fun Schalter(titel: String, text: String, an: Boolean, aendern: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { aendern(!an) }.padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(titel, color = Farbe.textStark, style = MaterialTheme.typography.bodyMedium)
            Text(text, color = Farbe.text3, style = MaterialTheme.typography.bodySmall)
        }
        Spacer(Modifier.width(12.dp))
        Switch(an, aendern, colors = schalterFarben())
    }
}

@Composable
fun ProtokollSeite(zurueck: () -> Unit) {
    val ctx = LocalContext.current
    var text by remember { mutableStateOf(Protokoll.lesen()) }
    val scroll = rememberScrollState()
    LaunchedEffect(text) { scroll.scrollTo(scroll.maxValue) }
    Column(Modifier.fillMaxSize()) {
        Kopfzeile(stringResource(R.string.protokoll), zurueck) {
            TextButton(onClick = {
                ctx.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("AniApp-Protokoll", text.takeLast(20_000)))
                Toast.makeText(ctx, ctx.getString(R.string.kopiert), Toast.LENGTH_SHORT).show()
            }) { Text(stringResource(R.string.kopieren), color = Farbe.link) }
            TextButton(onClick = { Protokoll.leeren(); text = "" }) { Text(stringResource(R.string.leeren), color = Farbe.link) }
        }
        SelectionContainer(Modifier.weight(1f).fillMaxWidth().verticalScroll(scroll).horizontalScroll(rememberScrollState())) {
            Text(
                text.ifEmpty { stringResource(R.string.protokoll_leer) },
                fontFamily = FontFamily.Monospace,
                fontSize = 11.sp,
                color = Farbe.text2,
                modifier = Modifier.padding(12.dp),
            )
        }
        Spacer(Modifier.height(8.dp))
    }
}
