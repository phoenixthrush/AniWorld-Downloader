package de.tobidervogel.aniworld.ui

import android.media.MediaScannerConnection
import androidx.annotation.StringRes
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.OpenInNew
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.VideoLibrary
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.DownloadService
import de.tobidervogel.aniworld.download.Live
import de.tobidervogel.aniworld.download.Speicher
import de.tobidervogel.aniworld.download.Status
import java.io.File

// ------------------------------------------------------------ Warteschlange

private enum class Filter(val text: Int) {
    ALLE(R.string.filter_alle), LAEUFT(R.string.status_laeuft), WARTET(R.string.status_wartet), PAUSE(R.string.status_pause), FEHLER(R.string.status_fehler),
}

private fun Filter.passt(a: Auftrag) = when (this) {
    Filter.ALLE -> true
    Filter.LAEUFT -> a.status == Status.LAEUFT
    Filter.WARTET -> a.status == Status.WARTET
    Filter.PAUSE -> a.status == Status.PAUSE
    Filter.FEHLER -> a.status == Status.FEHLER
}

/** Warteschlange wie queue.html der Web-UI: Filter mit Zahlen, Karten mit Status und Fortschritt. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun WarteschlangeSeite(oeffnen: (Ziel) -> Unit) {
    val app = App.self
    val ctx = LocalContext.current
    val stand by app.db.stand.collectAsState()
    val live by DownloadService.live.collectAsState()
    Speicher.stand.collectAsState().value
    val offen = remember(stand) {
        app.db.alle().filter { it.status != Status.FERTIG }
            .sortedWith(compareBy({ reihe(it.status) }, { it.erstellt }, { it.staffel }, { it.folge }))
    }
    var filter by rememberSaveable { mutableStateOf(Filter.ALLE) }
    val sichtbar = offen.filter { filter.passt(it) }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = ListenRand) {
        item { AppLeiste() }
        item {
            SeitenTitel(stringResource(R.string.tab_warteschlange)) {
                if (offen.any { it.status == Status.LAEUFT || it.status == Status.WARTET }) {
                    ZweitKnopf(stringResource(R.string.alle_pausieren), icon = Icons.Rounded.Pause, klein = true) {
                        offen.filter { it.status == Status.LAEUFT || it.status == Status.WARTET }.forEach { DownloadService.pausieren(app, it.id) }
                    }
                } else if (offen.any { it.status == Status.PAUSE }) {
                    ZweitKnopf(stringResource(R.string.fortsetzen), icon = Icons.Rounded.PlayArrow, klein = true) {
                        offen.filter { it.status == Status.PAUSE }.forEach { DownloadService.fortsetzen(app, it.id) }
                    }
                }
            }
        }
        if (!Speicher.vollzugriff()) {
            item {
                Hinweis(
                    stringResource(R.string.zugriff_hinweis, app.einstellungen.ordner),
                    Modifier.padding(start = 16.dp, end = 16.dp, bottom = 12.dp),
                    aktion = stringResource(R.string.zugriff_erlauben) to {
                        ctx.activity()?.let { Speicher.zugriffAnfragen(it) }
                    },
                )
            }
        }
        item {
            LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(Filter.entries) { f ->
                    Pille(stringResource(f.text), gewaehlt = f == filter, zahl = offen.count { f.passt(it) }) { filter = f }
                }
            }
        }
        if (offen.any { it.status == Status.FEHLER }) {
            item {
                // Umbrechen statt abschneiden: Beide Knöpfe passen auf schmalen Handys nicht nebeneinander.
                FlowRow(
                    Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    ZweitKnopf(stringResource(R.string.fehler_neu_starten), icon = Icons.Rounded.Refresh, klein = true) { app.db.fehlerNeuStarten(); DownloadService.starten(app) }
                    ZweitKnopf(stringResource(R.string.fehler_entfernen), icon = Icons.Rounded.Close, klein = true) {
                        offen.filter { it.status == Status.FEHLER }.forEach { DownloadService.entfernen(app, it.id) }
                    }
                }
            }
        }
        item { Spacer(Modifier.height(12.dp)) }
        if (sichtbar.isEmpty()) {
            item {
                Leer(
                    Icons.Rounded.Download,
                    if (offen.isEmpty()) stringResource(R.string.warteschlange_leer) else stringResource(R.string.nichts_mit_filter),
                    if (offen.isEmpty()) stringResource(R.string.warteschlange_leer_text) else null,
                )
            }
        }
        items(sichtbar, key = { it.id }) { a -> AuftragKarte(a, live[a.id]) { oeffnen(Ziel.Serie(a.serieUrl, a.serie, a.cover)) } }
    }
}

private fun reihe(s: Status) = when (s) {
    Status.LAEUFT -> 0
    Status.WARTET -> 1
    Status.PAUSE -> 2
    Status.FEHLER -> 3
    Status.FERTIG -> 4
}

@Composable
private fun Leer(icon: ImageVector, titel: String, text: String?) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 32.dp, vertical = 40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(icon, null, tint = Farbe.linieHover, modifier = Modifier.size(44.dp))
        Spacer(Modifier.height(12.dp))
        Text(titel, color = Farbe.textStark, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        if (text != null) {
            Spacer(Modifier.height(6.dp))
            Text(text, color = Farbe.text3, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun AuftragKarte(a: Auftrag, l: Live?, zurSerie: () -> Unit) {
    val app = App.self
    Column(
        Modifier
            .padding(horizontal = 16.dp, vertical = 5.dp)
            .fillMaxWidth()
            .karte()
            .combinedClickable(onClick = {}, onLongClick = zurSerie)
            .padding(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Cover(a.cover, Modifier.width(42.dp).height(63.dp), ecken = 6.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    if (a.einzelfilm) a.titel.ifBlank { a.serie } else a.serie,
                    style = MaterialTheme.typography.titleSmall, color = Farbe.textStark, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                Text(
                    if (a.einzelfilm) stringResource(R.string.film) else a.kuerzel + (a.titel.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""),
                    color = Farbe.text3, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(5.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SprachMarke(a.sprache)
                    a.hoster?.let {
                        Spacer(Modifier.width(6.dp))
                        Text(it, color = Farbe.text3, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            Spacer(Modifier.width(8.dp))
            // Status und Knöpfe rechts oben, damit die Karte nicht unnötig hoch wird.
            Column(horizontalAlignment = Alignment.End) {
                StatusPille(a.status)
                Spacer(Modifier.height(6.dp))
                Row {
                    when (a.status) {
                        Status.LAEUFT, Status.WARTET -> KleinKnopf(Icons.Rounded.Pause, stringResource(R.string.pausieren)) { DownloadService.pausieren(app, a.id) }
                        Status.PAUSE, Status.FEHLER -> KleinKnopf(
                            if (a.status == Status.FEHLER) Icons.Rounded.Refresh else Icons.Rounded.PlayArrow,
                            stringResource(R.string.fortsetzen),
                        ) { DownloadService.fortsetzen(app, a.id) }
                        Status.FERTIG -> Unit
                    }
                    KleinKnopf(Icons.Rounded.Close, stringResource(R.string.entfernen)) { DownloadService.entfernen(app, a.id) }
                }
            }
        }
        when (a.status) {
            Status.LAEUFT -> {
                Spacer(Modifier.height(12.dp))
                Fortschritt(l?.anteil)
                Spacer(Modifier.height(6.dp))
                // Oben Hoster, Qualität und Teile, darunter Größe und Tempo; der Anteil steht rechts.
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        l?.text ?: stringResource(R.string.startet),
                        color = Farbe.text2, style = MaterialTheme.typography.labelSmall,
                        maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                    )
                    l?.anteil?.let { Text("${(it * 100).toInt()} %", color = Farbe.textStark, style = MaterialTheme.typography.labelSmall) }
                }
                val menge = listOfNotNull(
                    l?.bytes?.takeIf { it > 0 }?.let { DownloadService.groesse(it) },
                    l?.tempo?.takeIf { it > 0 }?.let { DownloadService.groesse(it) + "/s" },
                )
                if (menge.isNotEmpty()) {
                    Text(menge.joinToString(" · "), color = Farbe.text3, style = MaterialTheme.typography.labelSmall, maxLines = 1)
                }
            }
            Status.PAUSE -> if (a.bytes > 0) {
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.n_geladen, DownloadService.groesse(a.bytes)), color = Farbe.text3, style = MaterialTheme.typography.labelSmall)
            }
            Status.FEHLER -> {
                Spacer(Modifier.height(8.dp))
                Text(a.fehler ?: stringResource(R.string.fehler), color = Farbe.fehlerText, style = MaterialTheme.typography.bodySmall, maxLines = 4, overflow = TextOverflow.Ellipsis)
            }
            else -> Unit
        }
    }
}

@Composable
private fun KleinKnopf(icon: ImageVector, beschreibung: String, onClick: () -> Unit) {
    Box(
        Modifier.size(36.dp).clip(RundMini).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, beschreibung, tint = Farbe.text2, modifier = Modifier.size(20.dp)) }
}

// ------------------------------------------------------------ Bibliothek

private enum class Art(val text: Int) { ALLE(R.string.filter_alle), SERIEN(R.string.serien), FILME(R.string.filme) }

/** Ein Titel in der Bibliothek: alle fertigen Folgen einer Serie bzw. ein Film. */
private class Eintrag(val url: String, val folgen: List<Auftrag>) {
    val erste = folgen.first()
    val film = erste.einzelfilm
    val titel = if (film) erste.titel.ifBlank { erste.serie } else erste.serie
    val bytes = folgen.sumOf { it.bytes }
}

@Composable
fun BibliothekSeite(oeffnen: (Ziel) -> Unit) {
    val app = App.self
    val stand by app.db.stand.collectAsState()
    val eintraege = remember(stand) {
        app.db.alle().filter { it.status == Status.FERTIG }.groupBy { it.serieUrl }
            .map { (url, l) -> Eintrag(url, l) }
            .sortedByDescending { e -> e.folgen.maxOf { it.erstellt } }
    }
    var art by rememberSaveable { mutableStateOf(Art.ALLE) }
    val sichtbar = eintraege.filter {
        when (art) {
            Art.ALLE -> true
            Art.SERIEN -> !it.film
            Art.FILME -> it.film
        }
    }

    Column(Modifier.fillMaxSize()) {
        AppLeiste()
        SeitenTitel(stringResource(R.string.tab_bibliothek)) {
            if (eintraege.isNotEmpty()) {
                Text(DownloadService.groesse(eintraege.sumOf { it.bytes }), color = Farbe.text3, style = MaterialTheme.typography.labelLarge)
            }
        }
        Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Art.entries.forEach { a ->
                val zahl = when (a) {
                    Art.ALLE -> eintraege.size
                    Art.SERIEN -> eintraege.count { !it.film }
                    Art.FILME -> eintraege.count { it.film }
                }
                Pille(stringResource(a.text), gewaehlt = a == art, zahl = zahl) { art = a }
            }
        }
        if (sichtbar.isEmpty()) {
            Leer(Icons.Rounded.VideoLibrary, stringResource(R.string.bibliothek_leer), stringResource(R.string.bibliothek_leer_text))
        }
        LazyVerticalGrid(
            columns = GridCells.Fixed(3),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 28.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(sichtbar, key = { it.url }) { e ->
                PosterKarte(
                    e.titel, e.erste.cover,
                    breite = null,
                    unter = if (e.film) stringResource(R.string.film_groesse, DownloadService.groesse(e.bytes)) else pluralStringResource(R.plurals.folgen_n, e.folgen.size, e.folgen.size),
                ) { oeffnen(Ziel.Ablage(e.url, e.titel)) }
            }
        }
    }
}

/** Geladene Folgen eines Titels, nach Staffeln, mit Weiterschauen-Balken. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun AblageSeite(ziel: Ziel.Ablage, zurueck: () -> Unit, oeffnen: (Ziel) -> Unit) {
    val app = App.self
    val ctx = LocalContext.current
    val stand by app.db.stand.collectAsState()
    val folgen = remember(stand, ziel) {
        app.db.fuerSerie(ziel.serieUrl).filter { it.status == Status.FERTIG }
            .sortedWith(compareBy({ it.istFilm }, { it.staffel }, { it.folge }))
    }
    val positionen = remember(stand, folgen) { app.db.positionen(folgen.map { it.url }) }
    var loeschen by remember { mutableStateOf<Auftrag?>(null) }
    val erste = folgen.firstOrNull()

    Column(Modifier.fillMaxSize()) {
        Kopfzeile(ziel.titel, zurueck) {
            IconButton(onClick = { oeffnen(Ziel.Serie(ziel.serieUrl, ziel.titel, erste?.cover)) }) {
                Icon(Icons.AutoMirrored.Rounded.OpenInNew, stringResource(R.string.zur_serie), tint = Farbe.text2)
            }
        }
        LazyColumn(contentPadding = ListenRand) {
            if (erste != null) {
                item {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Cover(erste.cover, Modifier.width(84.dp).height(126.dp), ecken = 10.dp)
                        Spacer(Modifier.width(16.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (erste.einzelfilm) stringResource(R.string.film) else pluralStringResource(R.plurals.folgen_n, folgen.size, folgen.size),
                                color = Farbe.textStark, style = MaterialTheme.typography.titleMedium,
                            )
                            Text(DownloadService.groesse(folgen.sumOf { it.bytes }), color = Farbe.text3, style = MaterialTheme.typography.bodySmall)
                            Spacer(Modifier.height(12.dp))
                            // Weiterschauen: erste Folge, die nicht zu Ende gesehen ist.
                            val weiter = folgen.firstOrNull { (positionen[it.url] ?: 0f) < 0.9f } ?: erste
                            val da = weiter.datei?.let { File(it).exists() } == true
                            HauptKnopf(
                                if ((positionen[weiter.url] ?: 0f) > 0.01f) stringResource(R.string.weiterschauen) else if (erste.einzelfilm) stringResource(R.string.abspielen) else stringResource(R.string.kuerzel_abspielen, weiter.kuerzel),
                                icon = Icons.Rounded.PlayArrow,
                                klein = true,
                                aktiv = da,
                            ) { weiter.datei?.let { d -> PlayerActivity.starten(ctx, d, weiter.anzeige, emptyMap(), weiter.url, weiter.folgeninfo) } }
                        }
                    }
                }
            } else {
                item { Leer(Icons.Rounded.VideoLibrary, stringResource(R.string.keine_dateien), null) }
            }
            folgen.groupBy { if (it.istFilm) -1 else it.staffel }.forEach { (staffel, liste) ->
                if (erste?.einzelfilm != true) {
                    item(key = "kopf-$staffel") { Abschnitt(if (staffel == -1) stringResource(R.string.filme) else stringResource(R.string.staffel_n, staffel), Modifier.padding(top = 0.dp)) }
                }
                items(liste, key = { it.id }) { a ->
                    val da = a.datei?.let { File(it).exists() } == true
                    Row(
                        Modifier
                            .padding(horizontal = 16.dp, vertical = 4.dp)
                            .fillMaxWidth()
                            .karte(RundKlein)
                            .combinedClickable(
                                onClick = { a.datei?.takeIf { da }?.let { d -> PlayerActivity.starten(ctx, d, a.anzeige, emptyMap(), a.url, a.folgeninfo) } },
                                onLongClick = { loeschen = a },
                            )
                            .padding(start = 14.dp, top = 10.dp, bottom = 10.dp, end = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Rounded.PlayArrow, null, tint = if (da) Farbe.link else Farbe.text3, modifier = Modifier.size(24.dp))
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (a.einzelfilm) a.titel else a.kuerzel + (a.titel.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""),
                                color = Farbe.textStark, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis,
                            )
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                SprachMarke(a.sprache)
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    if (da) DownloadService.groesse(a.bytes) else stringResource(R.string.datei_fehlt),
                                    color = if (da) Farbe.text3 else Farbe.fehlerText, style = MaterialTheme.typography.bodySmall,
                                )
                            }
                            positionen[a.url]?.takeIf { it > 0.01f }?.let {
                                Spacer(Modifier.height(6.dp))
                                Fortschritt(it, Modifier.padding(end = 10.dp))
                            }
                        }
                        IconButton(onClick = { loeschen = a }) { Icon(Icons.Rounded.DeleteOutline, stringResource(R.string.loeschen), tint = Farbe.text3) }
                    }
                }
            }
        }
    }

    loeschen?.let { a ->
        AlertDialog(
            onDismissRequest = { loeschen = null },
            title = { Text(if (a.einzelfilm) stringResource(R.string.film_loeschen) else stringResource(R.string.kuerzel_loeschen, a.kuerzel), color = Farbe.textStark) },
            text = { Text(stringResource(R.string.datei_wird_geloescht), color = Farbe.text2) },
            confirmButton = {
                TextButton(onClick = {
                    a.datei?.let { d ->
                        File(d).delete()
                        MediaScannerConnection.scanFile(ctx, arrayOf(d), null, null)
                    }
                    app.db.loeschen(a.id)
                    loeschen = null
                }) { Text(stringResource(R.string.loeschen), color = Farbe.fehler) }
            },
            dismissButton = { TextButton(onClick = { loeschen = null }) { Text(stringResource(R.string.abbrechen), color = Farbe.text) } },
            containerColor = Farbe.modal,
        )
    }
}
