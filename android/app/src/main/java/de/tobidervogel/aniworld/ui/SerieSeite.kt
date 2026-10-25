package de.tobidervogel.aniworld.ui

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.PauseCircle
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material3.BottomSheetDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.download.Auftrag
import de.tobidervogel.aniworld.download.Benennung
import de.tobidervogel.aniworld.download.DownloadService
import de.tobidervogel.aniworld.download.Live
import de.tobidervogel.aniworld.download.Status
import de.tobidervogel.aniworld.hoster.Aufloeser
import de.tobidervogel.aniworld.site.Einzelfilm
import de.tobidervogel.aniworld.site.Folge
import de.tobidervogel.aniworld.site.FolgenLinks
import de.tobidervogel.aniworld.site.Folgeninfo
import de.tobidervogel.aniworld.site.Serie
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.site.StaffelRef
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import java.io.File

/**
 * Serienseite nach dem Serienfenster der Web-UI: Kopf mit Poster, Sprache für die ganze
 * Serie, Folgen zum Ankreuzen und unten „Auswahl herunterladen“. Antippen einer Folge
 * öffnet das Blatt mit Hoster-Wahl, Streamen und Abspielen.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SerieSeite(ziel: Ziel.Serie, zurueck: () -> Unit) {
    val app = App.self
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val anbieter = app.anbieter(ziel.url)
    var serie by remember(ziel.url) { mutableStateOf<Serie?>(null) }
    var fehler by remember(ziel.url) { mutableStateOf<String?>(null) }
    var staffelNr by rememberSaveable(ziel.url) { mutableIntStateOf(-1) }
    var gewaehlteSprache by rememberSaveable(ziel.url) { mutableStateOf<Sprache?>(null) }
    val folgen = remember(ziel.url) { mutableStateMapOf<String, List<Folge>>() }
    val folgenFehler = remember(ziel.url) { mutableStateMapOf<String, String>() }
    val auswahl = remember(ziel.url) { mutableStateMapOf<String, Folge>() }
    var gewaehlteFolge by remember { mutableStateOf<Folge?>(null) }
    var serieLaden by remember { mutableStateOf(false) }
    var beschreibungOffen by remember { mutableStateOf(false) }

    fun laden(neu: Boolean = false) {
        fehler = null
        scope.launch {
            try {
                val s = anbieter.serie(ziel.url, neu)
                serie = s
                app.db.merken(s.url, s.titel, s.cover ?: ziel.cover)
                if (staffelNr == -1 || s.staffeln.none { it.nummer == staffelNr }) {
                    staffelNr = (s.staffeln.firstOrNull { it.nummer == ziel.staffel } ?: s.staffeln.firstOrNull { !it.istFilme }
                        ?: s.staffeln.firstOrNull())?.nummer ?: 1
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                fehler = e.message
            }
        }
    }
    LaunchedEffect(ziel.url) { if (serie == null) laden() }

    val s = serie
    val ref = s?.staffeln?.firstOrNull { it.nummer == staffelNr }
    fun staffelHolen(r: StaffelRef, neu: Boolean) {
        folgenFehler.remove(r.url)
        scope.launch {
            try {
                folgen[r.url] = anbieter.staffel(r, neu)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                folgenFehler[r.url] = e.message ?: ctx.getString(R.string.fehler)
            }
        }
    }
    LaunchedEffect(ref?.url) { ref?.let { if (folgen[it.url] == null) staffelHolen(it, false) } }

    val stand by app.db.stand.collectAsState()
    val live by DownloadService.live.collectAsState()
    val auftraege = remember(stand, ziel.url) { app.db.fuerSerie(ziel.url).groupBy { it.url } }
    val liste = ref?.let { folgen[it.url] }
    val positionen = remember(stand, liste) { app.db.positionen(liste.orEmpty().map { it.url }) }

    // Sprache gilt für die ganze Serie, wie das Auswahlfeld der Web-UI. Fehlt sie in der Staffel, die nächstbeste.
    val vorhanden = liste.orEmpty().flatMap { it.sprachen }.toSet()
    val sprache = gewaehlteSprache?.takeIf { it in vorhanden }
        ?: app.einstellungen.sprache.takeIf { it in vorhanden }
        ?: Sprache.entries.firstOrNull { it in vorhanden }
        ?: app.einstellungen.sprache
    val einzelfilm = s != null && Einzelfilm.ist(s)

    fun herunterladen(auswahlListe: List<Folge>) {
        val ser = s ?: return
        val passend = auswahlListe.filter { sprache in it.sprachen }
        val n = einreihen(passend, sprache, null, ser, folgen.values)
        val fehlt = auswahlListe.size - passend.size
        val teile = mutableListOf(ctx.resources.getQuantityString(R.plurals.folgen_eingereiht, n, n))
        if (n < passend.size) teile += ctx.getString(R.string.n_schon_in_liste, passend.size - n)
        if (fehlt > 0) teile += ctx.getString(R.string.nicht_in_sprache, fehlt, ctx.getString(sprache.anzeigeRes))
        Toast.makeText(ctx, teile.joinToString(" · "), Toast.LENGTH_SHORT).show()
    }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = if (auswahl.isEmpty()) 32.dp else 100.dp)) {
            item { Kopf(s, ziel, anbieter.name, zurueck) }
            if (s == null) {
                item { if (fehler != null) Fehlerkasten(fehler!!) { laden(true) } else LadeKreis() }
                return@LazyColumn
            }
            if (s.beschreibung.isNotBlank()) {
                item {
                    Column(Modifier.padding(horizontal = 16.dp).clickable { beschreibungOffen = !beschreibungOffen }) {
                        Text(
                            s.beschreibung,
                            style = MaterialTheme.typography.bodyMedium,
                            color = Farbe.text2,
                            maxLines = if (beschreibungOffen) Int.MAX_VALUE else 4,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (!beschreibungOffen && s.beschreibung.length > 220) {
                            Text(stringResource(R.string.mehr_anzeigen), color = Farbe.link, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }

            if (vorhanden.isNotEmpty()) {
                item {
                    Feld(stringResource(R.string.sprache), Modifier.padding(start = 16.dp, end = 16.dp, top = 20.dp)) {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Sprache.entries.filter { it in vorhanden }.forEach { sp ->
                                SprachPille(sp, gewaehlt = sp == sprache) { gewaehlteSprache = sp }
                            }
                        }
                    }
                }
            }

            if (einzelfilm) {
                // Filmo: ein Film, keine Folgenliste. Laden, Streamen und Abspielen direkt hier.
                val f = liste?.firstOrNull()
                item {
                    when {
                        f != null -> FilmAktionen(s, f, sprache, auftraege[f.url].orEmpty(), live, { herunterladen(listOf(f)) }) { gewaehlteFolge = f }
                        ref != null && folgenFehler[ref.url] != null -> Fehlerkasten(folgenFehler[ref.url]!!) { staffelHolen(ref, true) }
                        else -> LadeKreis()
                    }
                }
                return@LazyColumn
            }

            item {
                Row(Modifier.padding(start = 16.dp, end = 16.dp, top = 24.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.folgen), style = MaterialTheme.typography.titleLarge, color = Farbe.textStark)
                    if (liste != null) {
                        Spacer(Modifier.width(8.dp))
                        Text("${liste.size}", style = MaterialTheme.typography.titleSmall, color = Farbe.text3)
                    }
                    Spacer(Modifier.weight(1f))
                    if (!liste.isNullOrEmpty()) {
                        val alle = liste.all { it.url in auswahl }
                        Row(
                            Modifier.clip(RundMini).clickable {
                                if (alle) liste.forEach { auswahl.remove(it.url) } else liste.forEach { auswahl[it.url] = it }
                            }.padding(6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Haken(alle) { if (alle) liste.forEach { auswahl.remove(it.url) } else liste.forEach { auswahl[it.url] = it } }
                            Spacer(Modifier.width(8.dp))
                            Text(stringResource(R.string.alle_auswaehlen), color = Farbe.text, style = MaterialTheme.typography.labelLarge)
                        }
                    }
                }
            }
            if (s.staffeln.size > 1) {
                item {
                    LazyRow(
                        contentPadding = PaddingValues(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(s.staffeln, key = { it.url }) { st ->
                            val markiert = folgen[st.url]?.count { it.url in auswahl }?.takeIf { it > 0 }
                            Pille(st.anzeige(), gewaehlt = st.nummer == staffelNr, zahl = markiert) { staffelNr = st.nummer }
                        }
                    }
                }
                item {
                    Row(Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 4.dp)) {
                        ZweitKnopf(stringResource(R.string.ganze_serie_laden), icon = Icons.Rounded.Download) { serieLaden = true }
                    }
                }
            }
            when {
                ref == null -> item { Text(stringResource(R.string.keine_staffeln), color = Farbe.text2, modifier = Modifier.padding(16.dp)) }
                liste != null -> {
                    item { Spacer(Modifier.height(6.dp)) }
                    items(liste, key = { it.url }) { f ->
                        FolgenZeile(
                            f = f,
                            sprache = sprache,
                            auftraege = auftraege[f.url].orEmpty(),
                            live = live,
                            gesehen = positionen[f.url],
                            gewaehlt = f.url in auswahl,
                            waehlen = { if (f.url in auswahl) auswahl.remove(f.url) else auswahl[f.url] = f },
                            schnell = { herunterladen(listOf(f)) },
                        ) { gewaehlteFolge = f }
                    }
                    if (liste.isEmpty()) item { Text(stringResource(R.string.keine_folgen), color = Farbe.text2, modifier = Modifier.padding(16.dp)) }
                }
                folgenFehler[ref.url] != null -> item { Fehlerkasten(folgenFehler[ref.url]!!) { staffelHolen(ref, true) } }
                else -> item { LadeKreis() }
            }
        }

        if (auswahl.isNotEmpty() && s != null) {
            AuswahlLeiste(
                anzahl = auswahl.size,
                sprache = sprache,
                modifier = Modifier.align(Alignment.BottomCenter),
                leeren = { auswahl.clear() },
            ) {
                herunterladen(auswahl.values.sortedWith(compareBy({ it.istFilm }, { it.staffel }, { it.nummer })))
                auswahl.clear()
            }
        }
    }

    gewaehlteFolge?.let { f ->
        if (s != null) FolgenBlatt(s, f, sprache, auftraege[f.url].orEmpty(), folgen.values) { gewaehlteFolge = null }
    }
    if (serieLaden && s != null) StaffelBlatt(s, s.staffeln, folgen, sprache) { serieLaden = false }
}

@Composable
private fun Kopf(s: Serie?, ziel: Ziel.Serie, quelle: String, zurueck: () -> Unit) {
    val cover = s?.cover ?: ziel.cover
    Box(Modifier.fillMaxWidth()) {
        // Unscharfes Cover als Hintergrund, nach unten in den Seitenhintergrund ausgeblendet.
        Cover(cover, Modifier.matchParentSize().unscharf(30.dp), ecken = 0.dp)
        Box(
            Modifier.matchParentSize().background(
                Brush.verticalGradient(listOf(Farbe.hintergrund.copy(alpha = 0.5f), Farbe.hintergrund.copy(alpha = 0.85f), Farbe.hintergrund)),
            ),
        )
        Column(Modifier.statusBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = zurueck) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, stringResource(R.string.zurueck), tint = Farbe.textStark) }
                Spacer(Modifier.weight(1f))
                Row(
                    Modifier.padding(end = 12.dp).clip(RoundedPill).background(Color(0x99000000)).padding(horizontal = 10.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    SeitenLogo(quelle, 16.dp)
                    Spacer(Modifier.width(6.dp))
                    Text(quelle, color = Farbe.text, style = MaterialTheme.typography.labelMedium)
                }
            }
            Row(Modifier.padding(start = 16.dp, end = 16.dp, bottom = 18.dp), verticalAlignment = Alignment.Bottom) {
                Cover(cover, Modifier.width(116.dp).height(174.dp), ecken = 10.dp)
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        s?.titel ?: ziel.titel,
                        style = MaterialTheme.typography.headlineSmall,
                        color = Farbe.textStark,
                        maxLines = 4,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(8.dp))
                    s?.genres?.takeIf { it.isNotEmpty() }?.let { g ->
                        Text(g.take(4).joinToString(" · "), color = Farbe.text3, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                        Spacer(Modifier.height(4.dp))
                    }
                    val details = listOfNotNull(
                        s?.jahre,
                        s?.fsk?.let { "FSK $it" },
                        s?.staffeln?.count { !it.istFilme }?.takeIf { it > 0 }?.let { pluralStringResource(R.plurals.staffeln_n, it, it) },
                    )
                    if (details.isNotEmpty()) Text(details.joinToString(" · "), color = Farbe.text3, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

private val RoundedPill = RoundedCornerShape(50)

/** Zustand einer Folge in der Warteschlange, für Symbol und Knöpfe. */
private class FolgenStand(auftraege: List<Auftrag>) {
    val fertig = auftraege.firstOrNull { it.status == Status.FERTIG && it.datei?.let { d -> File(d).exists() } == true }
    val laufend = auftraege.firstOrNull { it.status == Status.LAEUFT }
    val wartet = auftraege.firstOrNull { it.status == Status.WARTET }
    val pause = auftraege.firstOrNull { it.status == Status.PAUSE }
    val fehler = auftraege.firstOrNull { it.status == Status.FEHLER }
}

@Composable
private fun StandSymbol(st: FolgenStand, live: Map<Long, Live>, laden: (() -> Unit)?) {
    Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
        when {
            st.fertig != null -> Icon(Icons.Rounded.CheckCircle, stringResource(R.string.geladen), tint = Farbe.gut)
            st.laufend != null -> {
                val l = live[st.laufend.id]
                if (l?.anteil != null) CircularProgressIndicator(progress = { l.anteil }, color = Farbe.akzent, trackColor = Farbe.flaeche2, strokeWidth = 3.dp, modifier = Modifier.size(22.dp))
                else CircularProgressIndicator(color = Farbe.akzent, strokeWidth = 3.dp, modifier = Modifier.size(22.dp))
            }
            st.wartet != null -> Icon(Icons.Rounded.Schedule, stringResource(R.string.status_wartet), tint = Farbe.text2)
            st.pause != null -> Icon(Icons.Rounded.PauseCircle, stringResource(R.string.status_pause), tint = Farbe.warnung)
            laden != null -> IconButton(onClick = laden) {
                Icon(
                    if (st.fehler != null) Icons.Rounded.ErrorOutline else Icons.Rounded.Download,
                    stringResource(R.string.laden),
                    tint = if (st.fehler != null) Farbe.fehler else Farbe.text2,
                )
            }
        }
    }
}

@Composable
private fun FolgenZeile(
    f: Folge,
    sprache: Sprache,
    auftraege: List<Auftrag>,
    live: Map<Long, Live>,
    gesehen: Float?,
    gewaehlt: Boolean,
    waehlen: () -> Unit,
    schnell: () -> Unit,
    onClick: () -> Unit,
) {
    val st = FolgenStand(auftraege)
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 3.dp)
            .clip(RundKlein)
            .background(if (gewaehlt) Farbe.akzentFlaeche else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(start = 8.dp, top = 10.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Haken(gewaehlt, onClick = waehlen)
        Spacer(Modifier.width(12.dp))
        Text(
            if (f.istFilm) "F${f.nummer}" else "E${f.nummer}",
            color = if (st.fertig != null) Farbe.gut else Farbe.text3,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.width(38.dp),
        )
        Column(Modifier.weight(1f)) {
            Text(
                f.titel.ifBlank { f.kuerzel },
                style = MaterialTheme.typography.bodyMedium,
                color = Farbe.textStark,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (f.titelEn.isNotBlank() && f.titelEn != f.titel) {
                Text(f.titelEn, style = MaterialTheme.typography.bodySmall, color = Farbe.text3, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (f.sprachen.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) { f.sprachen.forEach { SprachMarke(it) } }
            }
            if (gesehen != null && gesehen > 0.01f) {
                Spacer(Modifier.height(8.dp))
                Fortschritt(gesehen, Modifier.padding(end = 8.dp))
            }
        }
        // Schnell laden in der Seriensprache; gibt es die nicht, öffnet sich das Blatt.
        StandSymbol(st, live, laden = if (sprache in f.sprachen) schnell else onClick)
    }
}

/** Untere Leiste mit der Auswahl, wie die Knöpfe unter der Folgenliste der Web-UI. */
@Composable
private fun AuswahlLeiste(anzahl: Int, sprache: Sprache, modifier: Modifier, leeren: () -> Unit, laden: () -> Unit) {
    Column(modifier.fillMaxWidth().background(Farbe.nav)) {
        Trennlinie()
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = leeren) { Icon(Icons.Rounded.Close, stringResource(R.string.auswahl_aufheben), tint = Farbe.text2) }
            Column(Modifier.weight(1f)) {
                Text(pluralStringResource(R.plurals.folgen_ausgewaehlt, anzahl, anzahl), color = Farbe.textStark, style = MaterialTheme.typography.titleSmall)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SprachMarke(sprache)
                    Spacer(Modifier.width(6.dp))
                    Text(sprache.anzeige(), color = Farbe.text3, style = MaterialTheme.typography.bodySmall)
                }
            }
            HauptKnopf(stringResource(R.string.auswahl_herunterladen), icon = Icons.Rounded.Download, klein = true, onClick = laden)
        }
    }
}

@Composable
private fun FilmAktionen(
    s: Serie,
    f: Folge,
    sprache: Sprache,
    auftraege: List<Auftrag>,
    live: Map<Long, Live>,
    laden: () -> Unit,
    optionen: () -> Unit,
) {
    val ctx = LocalContext.current
    val st = FolgenStand(auftraege)
    Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 22.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        val datei = st.fertig?.datei
        when {
            datei != null -> HauptKnopf(stringResource(R.string.abspielen), Modifier.fillMaxWidth(), icon = Icons.Rounded.PlayArrow) {
                PlayerActivity.starten(ctx, datei, f.titel, emptyMap(), f.url, f.info(s))
            }
            st.laufend != null || st.wartet != null -> {
                val anteil = st.laufend?.let { live[it.id]?.anteil }
                Column(Modifier.fillMaxWidth().karte().padding(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StatusPille(if (st.laufend != null) Status.LAEUFT else Status.WARTET)
                        Spacer(Modifier.width(8.dp))
                        Text(st.laufend?.let { live[it.id]?.text } ?: stringResource(R.string.in_warteschlange), color = Farbe.text2, style = MaterialTheme.typography.bodySmall, maxLines = 1)
                    }
                    Spacer(Modifier.height(10.dp))
                    Fortschritt(anteil)
                }
            }
            else -> HauptKnopf(
                stringResource(R.string.film_herunterladen),
                Modifier.fillMaxWidth(),
                icon = Icons.Rounded.Download,
                aktiv = sprache in f.sprachen,
                onClick = laden,
            )
        }
        ZweitKnopf(stringResource(R.string.streamen_oder_hoster), Modifier.fillMaxWidth(), icon = Icons.Rounded.PlayArrow, onClick = optionen)
        if (st.fehler != null && st.fertig == null) {
            Text(st.fehler.fehler ?: stringResource(R.string.letzter_versuch), color = Farbe.fehlerText, style = MaterialTheme.typography.bodySmall)
        }
    }
}

private fun Folge.info(s: Serie) = Folgeninfo(s.url, s.titel, staffel, nummer, istFilm)

/** Titel für den Player: „Serie · S01E05“, beim Einzelfilm nur der Film. */
private fun Folge.anzeige(s: Serie) = if (Einzelfilm.ist(s)) titel.ifBlank { s.titel } else "${s.titel} · $kuerzel"

/**
 * Reiht Folgen ein und startet den Dienst. Die Stellen der Folgennummer kommen aus der ganzen
 * Staffel (soweit geladen), damit eine einzeln gewählte Folge 5 einer 120er-Staffel „E005“ heißt.
 */
private fun einreihen(liste: List<Folge>, sprache: Sprache, hoster: String?, s: Serie, bekannt: Collection<List<Folge>>): Int {
    if (liste.isEmpty()) return 0
    val app = App.self
    val staffeln = (bekannt.flatten() + liste).distinctBy { it.url }.groupBy { it.istFilm to it.staffel }
    val auftraege = liste.map { f ->
        val inStaffel = staffeln[f.istFilm to f.staffel].orEmpty()
        Auftrag(
            serie = s.titel, serieUrl = s.url, cover = s.cover,
            staffel = f.staffel, folge = f.nummer, istFilm = f.istFilm,
            titel = f.titel, url = f.url, sprache = sprache, hoster = hoster,
            stellen = Benennung.stellen(inStaffel.size, inStaffel.maxOfOrNull { it.nummer } ?: 0),
        )
    }
    val n = app.db.einreihen(auftraege)
    DownloadService.starten(app)
    return n
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Blatt(schliessen: () -> Unit, inhalt: @Composable () -> Unit) {
    ModalBottomSheet(
        onDismissRequest = schliessen,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = Farbe.modal,
        dragHandle = { BottomSheetDefaults.DragHandle(color = Farbe.linieHover) },
    ) {
        Column(Modifier.padding(horizontal = 20.dp).navigationBarsPadding().padding(bottom = 16.dp)) { inhalt() }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FolgenBlatt(s: Serie, f: Folge, seriensprache: Sprache, auftraege: List<Auftrag>, bekannt: Collection<List<Folge>>, schliessen: () -> Unit) {
    val app = App.self
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var links by remember(f.url) { mutableStateOf<FolgenLinks?>(null) }
    var fehler by remember(f.url) { mutableStateOf<String?>(null) }
    var status by remember(f.url) { mutableStateOf<String?>(null) }
    var sucht by remember(f.url) { mutableStateOf(false) }
    val vorhanden = links?.sprachen ?: f.sprachen
    var sprache by remember(f.url) { mutableStateOf(seriensprache.takeIf { it in f.sprachen } ?: f.sprachen.firstOrNull() ?: seriensprache) }
    var hoster by remember(f.url) { mutableStateOf<String?>(null) }
    val datei = auftraege.firstOrNull { it.status == Status.FERTIG }?.datei?.takeIf { File(it).exists() }

    LaunchedEffect(f.url) {
        try {
            val l = app.anbieter(f.url).links(f.url)
            links = l
            if (sprache !in l.sprachen) l.sprachen.firstOrNull()?.let { sprache = it }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            fehler = e.message
        }
    }

    Blatt(schliessen) {
        if (!f.istFilm || !Einzelfilm.ist(s)) Text(f.kuerzel, color = Farbe.link, style = MaterialTheme.typography.labelLarge)
        Text(f.titel.ifBlank { f.kuerzel }, style = MaterialTheme.typography.titleLarge, color = Farbe.textStark)
        if (f.titelEn.isNotBlank() && f.titelEn != f.titel) Text(f.titelEn, color = Farbe.text3, style = MaterialTheme.typography.bodyMedium)

        if (datei != null) {
            Spacer(Modifier.height(16.dp))
            HauptKnopf(stringResource(R.string.datei_abspielen), Modifier.fillMaxWidth(), icon = Icons.Rounded.PlayArrow) {
                PlayerActivity.starten(ctx, datei, f.anzeige(s), emptyMap(), f.url, f.info(s))
                schliessen()
            }
        }

        Spacer(Modifier.height(20.dp))
        Feld(stringResource(R.string.sprache)) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Sprache.entries.filter { it in vorhanden || it in f.sprachen }.forEach { sp ->
                    SprachPille(sp, gewaehlt = sp == sprache, aktiv = links == null || sp in vorhanden) { sprache = sp; hoster = null }
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        Feld(stringResource(R.string.hoster)) {
            when {
                fehler != null -> Text(fehler!!, color = Farbe.fehlerText, style = MaterialTheme.typography.bodySmall)
                links == null -> LadeKreis(Modifier.height(48.dp))
                else -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Pille(stringResource(R.string.automatisch), gewaehlt = hoster == null) { hoster = null }
                    links!!.hoster(sprache).forEach { h -> Pille(h, gewaehlt = hoster == h) { hoster = h } }
                }
            }
        }

        status?.let {
            Spacer(Modifier.height(14.dp))
            Text(it, color = Farbe.text2, style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(22.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ZweitKnopf(
                if (sucht) stringResource(R.string.sucht) else stringResource(R.string.streamen),
                Modifier.weight(1f),
                icon = Icons.Rounded.PlayArrow,
                aktiv = links != null && sprache in vorhanden && !sucht,
            ) {
                val l = links ?: return@ZweitKnopf
                sucht = true
                scope.launch {
                    try {
                        val st = Aufloeser.stream(f.url, l, sprache, hoster) { status = it }
                        status = null
                        PlayerActivity.starten(ctx, st.url, f.anzeige(s), st.header, f.url, f.info(s), sprache, hls = st.istHls)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        status = e.message
                    } finally {
                        sucht = false
                    }
                }
            }
            HauptKnopf(stringResource(R.string.herunterladen), Modifier.weight(1f), icon = Icons.Rounded.Download, aktiv = sprache in vorhanden) {
                val n = einreihen(listOf(f), sprache, hoster, s, bekannt)
                Toast.makeText(ctx, ctx.getString(if (n > 0) R.string.eingereiht else R.string.schon_in_liste), Toast.LENGTH_SHORT).show()
                schliessen()
            }
        }
    }
}

/** Ganze Serie auf einmal: lädt alle Staffeln und zeigt, wie viele Folgen es pro Sprache gibt. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StaffelBlatt(s: Serie, refs: List<StaffelRef>, cache: MutableMap<String, List<Folge>>, seriensprache: Sprache, schliessen: () -> Unit) {
    val app = App.self
    val ctx = LocalContext.current
    var folgen by remember(refs) { mutableStateOf<List<Folge>?>(null) }
    var fehler by remember(refs) { mutableStateOf<String?>(null) }
    var ohneFilme by remember { mutableStateOf(true) }

    LaunchedEffect(refs) {
        try {
            val alle = ArrayList<Folge>()
            for (r in refs) {
                alle += cache[r.url] ?: app.anbieter(r.url).staffel(r).also { cache[r.url] = it }
            }
            folgen = alle
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            fehler = e.message
        }
    }

    val auswahl = folgen?.filter { !(ohneFilme && it.istFilm) }.orEmpty()
    val zaehler = Sprache.entries.associateWith { sp -> auswahl.count { sp in it.sprachen } }
    var sprache by remember(folgen) {
        mutableStateOf(seriensprache.takeIf { (zaehler[it] ?: 0) > 0 } ?: zaehler.maxByOrNull { it.value }?.key ?: seriensprache)
    }
    val passend = auswahl.filter { sprache in it.sprachen }

    Blatt(schliessen) {
        Text(stringResource(R.string.ganze_serie_laden), style = MaterialTheme.typography.titleLarge, color = Farbe.textStark)
        Text(s.titel, color = Farbe.text3, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(18.dp))
        when {
            fehler != null -> Fehlerkasten(fehler!!)
            folgen == null -> LadeKreis()
            else -> {
                Feld(stringResource(R.string.sprache)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Sprache.entries.filter { (zaehler[it] ?: 0) > 0 }.forEach { sp ->
                            SprachPille(sp, gewaehlt = sp == sprache, zahl = "${zaehler[sp]}/${auswahl.size}") { sprache = sp }
                        }
                    }
                }
                if (refs.any { it.istFilme }) {
                    Spacer(Modifier.height(12.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.filme_weglassen), Modifier.weight(1f), color = Farbe.text)
                        Switch(ohneFilme, { ohneFilme = it }, colors = schalterFarben())
                    }
                }
                if (passend.size < auswahl.size) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        pluralStringResource(R.plurals.fehlen_in_sprache, auswahl.size - passend.size, auswahl.size - passend.size, sprache.anzeige()),
                        color = Farbe.text3, style = MaterialTheme.typography.bodySmall,
                    )
                }
                Spacer(Modifier.height(20.dp))
                HauptKnopf(pluralStringResource(R.plurals.n_folgen_herunterladen, passend.size, passend.size), Modifier.fillMaxWidth(), icon = Icons.Rounded.Download, aktiv = passend.isNotEmpty()) {
                    val n = einreihen(passend, sprache, null, s, cache.values)
                    Toast.makeText(ctx, ctx.resources.getQuantityString(R.plurals.folgen_eingereiht, n, n), Toast.LENGTH_SHORT).show()
                    schliessen()
                }
            }
        }
    }
}

@Composable
fun schalterFarben() = SwitchDefaults.colors(
    checkedTrackColor = Farbe.akzent,
    checkedThumbColor = Color.White,
    checkedBorderColor = Farbe.akzent,
    uncheckedTrackColor = Farbe.flaeche2,
    uncheckedThumbColor = Farbe.text3,
    uncheckedBorderColor = Farbe.linieHover,
)
