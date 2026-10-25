package de.tobidervogel.aniworld.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.BatteryChargingFull
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Folder
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.download.AutoSync
import de.tobidervogel.aniworld.download.Speicher
import de.tobidervogel.aniworld.site.Sprache
import kotlinx.coroutines.flow.update

private enum class Schritt { WILLKOMMEN, BENACHRICHTIGUNGEN, SPEICHER, AKKU, FERTIG }

/**
 * Einrichtung beim ersten Start: Schritt für Schritt erklären, wozu die App welche Freigabe braucht,
 * und sie dann erst abfragen. Jeder Schritt lässt sich überspringen; alles bleibt in den
 * Einstellungen erreichbar. Benachrichtigungen fragt Android erst ab 13 ab, davor fehlt der Schritt.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EinrichtungSeite(fertig: () -> Unit) {
    val ctx = LocalContext.current
    val e = App.self.einstellungen
    e.stand.collectAsState().value
    // Zurück aus den Systemeinstellungen zählt MainActivity hoch; dann die Freigaben neu lesen.
    Speicher.stand.collectAsState().value
    val schritte = remember {
        Schritt.entries.filter { it != Schritt.BENACHRICHTIGUNGEN || Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU }
    }
    var i by rememberSaveable { mutableIntStateOf(0) }
    // Nach einer Ablehnung zeigt Android den Dialog oft nicht mehr; beim zweiten Tippen dann die Systemeinstellung.
    var gefragt by rememberSaveable { mutableStateOf(setOf<String>()) }
    val schritt = schritte[i]
    val weiter = { if (i < schritte.lastIndex) i++ }
    val frage = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { Speicher.stand.update { it + 1 } }
    BackHandler(enabled = i > 0) { i-- }

    val erlaubt = when (schritt) {
        Schritt.BENACHRICHTIGUNGEN -> Freigaben.benachrichtigungen(ctx)
        Schritt.SPEICHER -> Speicher.vollzugriff()
        Schritt.AKKU -> Freigaben.akkuFrei(ctx)
        else -> false
    }

    Column(Modifier.fillMaxSize().background(Farbe.hintergrund).systemBarsPadding().padding(horizontal = 24.dp, vertical = 16.dp)) {
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally)) {
            schritte.indices.forEach { j ->
                Box(
                    Modifier.height(6.dp).width(if (j == i) 22.dp else 6.dp).clip(RoundedCornerShape(50))
                        .background(if (j <= i) Farbe.akzent else Farbe.linieHover),
                )
            }
        }
        Column(
            Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            when (schritt) {
                Schritt.WILLKOMMEN -> {
                    Image(painterResource(R.drawable.logo), null, Modifier.size(104.dp).clip(CircleShape))
                    Ueberschrift(stringResource(R.string.einrichtung_willkommen))
                    Erklaerung(stringResource(R.string.einrichtung_willkommen_text))
                    FlowRow(
                        Modifier.padding(top = 20.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        App.self.anbieter.forEach { SeitenLogo(it.name, 32.dp) }
                    }
                }
                Schritt.BENACHRICHTIGUNGEN -> Erklaerseite(
                    Icons.Rounded.Notifications, stringResource(R.string.einrichtung_benachrichtigungen),
                    stringResource(R.string.einrichtung_benachrichtigungen_text), erlaubt,
                )
                Schritt.SPEICHER -> Erklaerseite(
                    Icons.Rounded.Folder, stringResource(R.string.zugriff_alle_dateien),
                    stringResource(R.string.einrichtung_speicher_text, e.ordner), erlaubt,
                )
                Schritt.AKKU -> Erklaerseite(
                    Icons.Rounded.BatteryChargingFull, stringResource(R.string.akku),
                    stringResource(R.string.einrichtung_akku_text), erlaubt,
                )
                Schritt.FERTIG -> {
                    Icon(Icons.Rounded.CheckCircle, null, tint = Farbe.gut, modifier = Modifier.size(72.dp))
                    Ueberschrift(stringResource(R.string.einrichtung_fertig))
                    Erklaerung(stringResource(R.string.einrichtung_fertig_text))
                    FlowRow(
                        Modifier.padding(top = 20.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Sprache.entries.forEach { s -> SprachPille(s, e.sprache == s) { e.sprache = s } }
                    }
                    Row(
                        Modifier.padding(top = 24.dp).fillMaxWidth().karte().padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(stringResource(R.string.autosync), color = Farbe.textStark, style = MaterialTheme.typography.bodyMedium)
                            Text(stringResource(R.string.einrichtung_autosync_text), color = Farbe.text3, style = MaterialTheme.typography.bodySmall)
                        }
                        Spacer(Modifier.width(12.dp))
                        Switch(e.autoSync, { e.autoSync = it; AutoSync.planen(ctx) }, colors = schalterFarben())
                    }
                }
            }
        }
        when (schritt) {
            Schritt.WILLKOMMEN -> HauptKnopf(stringResource(R.string.einrichtung_los), Modifier.fillMaxWidth(), onClick = weiter)
            Schritt.FERTIG -> HauptKnopf(stringResource(R.string.einrichtung_oeffnen), Modifier.fillMaxWidth()) {
                e.einrichtungFertig = true
                fertig()
            }
            else -> {
                if (!erlaubt) {
                    HauptKnopf(stringResource(R.string.einrichtung_erlauben), Modifier.fillMaxWidth()) {
                        val zweites = schritt.name in gefragt
                        gefragt = gefragt + schritt.name
                        when (schritt) {
                            Schritt.BENACHRICHTIGUNGEN -> when {
                                zweites -> Freigaben.benachrichtigungenOeffnen(ctx)
                                Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU -> frage.launch(Manifest.permission.POST_NOTIFICATIONS)
                            }
                            // Ab Android 11 ist es ohnehin eine Einstellungsseite, davor ein Dialog wie oben.
                            Schritt.SPEICHER ->
                                if (zweites && Build.VERSION.SDK_INT < Build.VERSION_CODES.R) Freigaben.oeffnen(ctx)
                                else ctx.activity()?.let { Speicher.zugriffAnfragen(it) }
                            else -> Freigaben.akkuFreigeben(ctx)
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    ZweitKnopf(stringResource(R.string.einrichtung_spaeter), Modifier.fillMaxWidth(), onClick = weiter)
                } else {
                    HauptKnopf(stringResource(R.string.einrichtung_weiter), Modifier.fillMaxWidth(), onClick = weiter)
                }
            }
        }
    }
}

@Composable
private fun Erklaerseite(icon: ImageVector, titel: String, text: String, erlaubt: Boolean) {
    Box(Modifier.size(88.dp).clip(CircleShape).background(Farbe.akzentFlaeche), contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = Farbe.link, modifier = Modifier.size(42.dp))
    }
    Ueberschrift(titel)
    Erklaerung(text)
    if (erlaubt) {
        Row(Modifier.padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.CheckCircle, null, tint = Farbe.gut, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(6.dp))
            Text(stringResource(R.string.erlaubt), color = Farbe.gut, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun Ueberschrift(text: String) =
    Text(text, Modifier.padding(top = 24.dp), color = Farbe.textStark, style = MaterialTheme.typography.headlineMedium, textAlign = TextAlign.Center)

@Composable
private fun Erklaerung(text: String) =
    Text(text, Modifier.padding(top = 10.dp), color = Farbe.text2, style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
