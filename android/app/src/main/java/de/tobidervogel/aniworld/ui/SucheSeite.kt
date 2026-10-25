package de.tobidervogel.aniworld.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.site.Karte
import de.tobidervogel.aniworld.site.Treffer
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun SucheSeite(zurueck: () -> Unit, oeffnen: (Ziel) -> Unit) {
    val app = App.self
    app.einstellungen.stand.collectAsState().value
    var text by rememberSaveable { mutableStateOf("") }
    // Ergebnisse pro Anbieter, jeweils mit eigenem Fehler. Die gewählte Seite steht oben.
    var treffer by remember { mutableStateOf<Map<String, List<Treffer>>?>(null) }
    var fehler by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var laeuft by remember { mutableStateOf(false) }
    var fokussiert by remember { mutableStateOf(false) }
    val fokus = remember { FocusRequester() }
    val tastatur = LocalSoftwareKeyboardController.current
    val quelle = app.einstellungen.startQuelle
    val reihenfolge = app.anbieter.sortedBy { if (it.name == quelle) 0 else 1 }

    LaunchedEffect(Unit) { fokus.requestFocus() }
    // Erst suchen, wenn 350 ms nichts getippt wurde: spart Anfragen an die Seiten.
    LaunchedEffect(text) {
        if (text.trim().length < 2) { treffer = null; fehler = emptyMap(); return@LaunchedEffect }
        delay(350)
        laeuft = true
        val f = HashMap<String, String>()
        try {
            // Alle Seiten gleichzeitig; fällt eine aus, zeigen die anderen trotzdem ihre Treffer.
            treffer = coroutineScope {
                reihenfolge.map { a ->
                    async {
                        a.name to try {
                            a.suche(text)
                        } catch (e: CancellationException) {
                            throw e
                        } catch (e: Exception) {
                            f[a.name] = e.message ?: tr(R.string.fehler)
                            emptyList()
                        }
                    }
                }.awaitAll().toMap(LinkedHashMap())
            }
            fehler = f
        } finally {
            laeuft = false
        }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        Row(Modifier.statusBarsPadding().padding(start = 4.dp, end = 16.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = zurueck) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, stringResource(R.string.zurueck), tint = Farbe.textStark) }
            Row(
                Modifier
                    .weight(1f)
                    .height(48.dp)
                    .karte(RundKlein, Farbe.eingabe)
                    .border(1.dp, if (fokussiert) Farbe.akzent else Farbe.linie, RundKlein)
                    .padding(start = 14.dp, end = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Rounded.Search, null, tint = Farbe.text3, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(10.dp))
                BasicTextField(
                    value = text,
                    onValueChange = { text = it },
                    singleLine = true,
                    textStyle = TextStyle(color = Farbe.textStark, fontSize = 15.sp, fontFamily = Inter),
                    cursorBrush = SolidColor(Farbe.akzent),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { tastatur?.hide() }),
                    modifier = Modifier.weight(1f).focusRequester(fokus).onFocusChanged { fokussiert = it.isFocused },
                    decorationBox = { feld ->
                        if (text.isEmpty()) Text(stringResource(R.string.suche_feld), color = Farbe.text3, fontSize = 15.sp, fontFamily = Inter)
                        feld()
                    },
                )
                if (text.isNotEmpty()) {
                    IconButton(onClick = { text = "" }) { Icon(Icons.Rounded.Close, stringResource(R.string.leeren), tint = Farbe.text2) }
                }
            }
        }
        Trennlinie()
        if (laeuft && treffer == null) LadeKreis()
        if (treffer == null && !laeuft) {
            Text(
                stringResource(R.string.suche_alle, app.anbieter.joinToString(", ") { it.name }),
                color = Farbe.text3,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(20.dp),
            )
        }
        LazyColumn(contentPadding = ListenRand) {
            treffer?.forEach { (name, liste) ->
                item(key = "kopf-$name") {
                    Row(Modifier.padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        SeitenLogo(name, 20.dp)
                        Spacer(Modifier.width(10.dp))
                        Text(name, style = MaterialTheme.typography.titleMedium, color = Farbe.textStark, modifier = Modifier.weight(1f))
                        Text(if (liste.isEmpty()) "" else "${liste.size}", color = Farbe.text3, style = MaterialTheme.typography.labelLarge)
                    }
                }
                fehler[name]?.let { item(key = "fehler-$name") { Fehlerkasten(it) } }
                if (liste.isEmpty() && fehler[name] == null) {
                    item(key = "leer-$name") {
                        Text(stringResource(R.string.nichts_gefunden), color = Farbe.text3, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(horizontal = 16.dp))
                    }
                }
                items(liste.distinctBy { it.url }, key = { "$name|${it.url}" }) { t ->
                    TrefferZeile(t) { tastatur?.hide(); oeffnen(Ziel.Serie(t.url, t.titel, t.cover)) }
                }
            }
        }
    }
}

@Composable
private fun TrefferZeile(t: Treffer, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .karte(RundKlein)
            .clickable(onClick = onClick)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Cover(t.cover, Modifier.width(46.dp).height(69.dp), ecken = 6.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(t.titel, style = MaterialTheme.typography.titleSmall, color = Farbe.textStark, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (t.beschreibung.isNotBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(t.beschreibung, color = Farbe.text3, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** Alle Titel eines Genres als Raster, Seite für Seite nachgeladen. */
@Composable
fun GenreSeite(ziel: Ziel.GenreListe, zurueck: () -> Unit, oeffnen: (Ziel) -> Unit) {
    val app = App.self
    val genre = ziel.genre
    val quelle = app.anbieter.firstOrNull { it.name == ziel.quelle } ?: app.aniworld
    val karten = remember(ziel) { mutableStateListOf<Karte>() }
    var seite by remember(ziel) { mutableIntStateOf(0) }
    var weiter by remember(ziel) { mutableStateOf(true) }
    var laeuft by remember { mutableStateOf(false) }
    var fehler by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val raster = rememberLazyGridState()

    fun mehr() {
        if (laeuft || !weiter) return
        laeuft = true
        scope.launch {
            try {
                val (neu, gibtMehr) = quelle.genre(genre.slug, seite + 1)
                karten += neu.distinctBy { it.url }.filter { k -> karten.none { it.url == k.url } }
                seite++
                weiter = gibtMehr && neu.isNotEmpty()
                fehler = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                fehler = e.message
            } finally {
                laeuft = false
            }
        }
    }

    LaunchedEffect(ziel) { if (karten.isEmpty()) mehr() }
    LaunchedEffect(raster) {
        snapshotFlow { raster.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { letzter ->
            if (letzter >= karten.size - 6) mehr()
        }
    }

    Column(Modifier.fillMaxSize()) {
        Kopfzeile(genre.name, zurueck) {
            Row(Modifier.padding(end = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                SeitenLogo(quelle.name, 18.dp)
                Spacer(Modifier.width(6.dp))
                Text(quelle.name, color = Farbe.text3, style = MaterialTheme.typography.labelMedium)
            }
        }
        fehler?.let { Fehlerkasten(it) { mehr() } }
        LazyVerticalGrid(
            columns = GridCells.Fixed(3),
            state = raster,
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 28.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(karten, key = { it.url }) { k ->
                PosterKarte(k.titel, k.cover, breite = null) { oeffnen(Ziel.Serie(k.url, k.titel, k.cover, k.staffel)) }
            }
            if (laeuft) item(span = { GridItemSpan(maxLineSpan) }) { LadeKreis() }
            if (!laeuft && !weiter && karten.isEmpty() && fehler == null) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Text(stringResource(R.string.genre_leer), color = Farbe.text3, modifier = Modifier.padding(8.dp))
                }
            }
        }
    }
}
