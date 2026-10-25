package de.tobidervogel.aniworld.ui

import android.widget.Toast
import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.site.Anbieter
import de.tobidervogel.aniworld.site.Karte
import de.tobidervogel.aniworld.site.NeueFolge
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Geladene Startseiten pro Anbieter; lebt in der Activity, damit Zurück nicht neu lädt. */
class StartZustand(scope: CoroutineScope, anbieter: List<Anbieter>) {
    class ProQuelle(scope: CoroutineScope, val a: Anbieter) {
        val start = Ladung(scope) { a.startseite() }
        val neueFolgen = Ladung(scope) { a.neueFolgen() }
        val liste = LazyListState()

        fun laden(neu: Boolean = false) {
            start.start(neu)
            neueFolgen.start(neu)
        }
    }

    val quellen = anbieter.associate { it.name to ProQuelle(scope, it) }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun StartSeite(zustand: StartZustand, oeffnen: (Ziel) -> Unit) {
    val app = App.self
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    app.einstellungen.stand.collectAsState().value
    val quelle = app.einstellungen.startQuelle.takeIf { it in zustand.quellen } ?: zustand.quellen.keys.first()
    val z = zustand.quellen.getValue(quelle)
    val anbieter = z.a
    LaunchedEffect(quelle) { z.laden() }
    val stand by app.db.stand.collectAsState()
    val verlauf = remember(stand) { app.db.verlauf() }
    val start = z.start.daten
    var zufallLaeuft by remember { mutableStateOf(false) }

    PullToRefreshBox(
        isRefreshing = z.start.laeuft && start != null,
        onRefresh = { z.laden(neu = true) },
        modifier = Modifier.fillMaxSize(),
    ) {
        LazyColumn(state = z.liste, modifier = Modifier.fillMaxSize(), contentPadding = ListenRand) {
            item { AppLeiste() }
            item {
                Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 16.dp)) {
                    SeitenUmschalter(zustand.quellen.keys.toList(), quelle) { app.einstellungen.startQuelle = it }
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        // Die Suche läuft über alle Seiten, darum ohne Seitennamen.
                        SuchKnopf(stringResource(R.string.titel_suchen), Modifier.weight(1f)) { oeffnen(Ziel.Suche) }
                        if (anbieter.hatZufall) {
                            ZweitKnopf(stringResource(R.string.zufall), icon = Icons.Rounded.Shuffle, aktiv = !zufallLaeuft) {
                                zufallLaeuft = true
                                scope.launch {
                                    try {
                                        val url = anbieter.zufall()
                                        if (url != null) oeffnen(Ziel.Serie(url, titelAusAdresse(url), null))
                                        else Toast.makeText(ctx, ctx.getString(R.string.zufall_leer), Toast.LENGTH_SHORT).show()
                                    } catch (e: CancellationException) {
                                        throw e
                                    } catch (e: Exception) {
                                        Toast.makeText(ctx, e.message ?: ctx.getString(R.string.zufall_fehler), Toast.LENGTH_SHORT).show()
                                    } finally {
                                        zufallLaeuft = false
                                    }
                                }
                            }
                        }
                    }
                }
            }

            start?.reihen?.firstOrNull { (_, k) -> k.any { it.cover != null } }?.let { (titel, karten) ->
                item(key = "spotlight-$quelle") { Spotlight(titel, quelle, karten.filter { it.cover != null }.distinctBy { it.url }.take(6), oeffnen) }
            }

            // Zuletzt geöffnet gilt über alle Seiten hinweg; lange drücken nimmt einen Titel heraus.
            if (verlauf.isNotEmpty()) {
                item { Abschnitt(stringResource(R.string.zuletzt)) }
                item {
                    LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(verlauf, key = { it.url }) { v ->
                            PosterKarte(
                                v.titel, v.cover,
                                unter = app.anbieter(v.url).name,
                                onLongClick = { app.db.vergessen(v.url) },
                            ) { oeffnen(Ziel.Serie(v.url, v.titel, v.cover)) }
                        }
                    }
                }
            }

            z.neueFolgen.daten?.takeIf { it.isNotEmpty() }?.let { folgen ->
                item { Abschnitt(stringResource(R.string.neue_folgen)) }
                item {
                    LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(folgen.distinctBy { it.url }.take(40), key = { it.url }) { f -> NeueFolgeKarte(anbieter, f, oeffnen) }
                    }
                }
            }

            when {
                start != null -> {
                    start.reihen.forEach { (titel, karten) -> reihe(titel, karten, oeffnen) }
                    if (start.genres.isNotEmpty()) {
                        item { Abschnitt(stringResource(R.string.genres_entdecken)) }
                        item {
                            FlowRow(
                                Modifier.padding(horizontal = 16.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                start.genres.forEach { g -> Pille(g.name, gewaehlt = false) { oeffnen(Ziel.GenreListe(g, quelle)) } }
                            }
                        }
                    }
                }
                z.start.fehler != null -> item { Fehlerkasten(z.start.fehler!!, Modifier.padding(top = 12.dp)) { z.laden(neu = true) } }
                else -> item { LadeKreis(Modifier.padding(top = 24.dp)) }
            }
        }
    }
}

private fun LazyListScope.reihe(@StringRes titel: Int, karten: List<Karte>, oeffnen: (Ziel) -> Unit) {
    if (karten.isEmpty()) return
    item { Abschnitt(stringResource(titel)) }
    item {
        LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            // Seiten listen einen Titel manchmal doppelt; doppelte Schlüssel brächten die Liste zum Absturz.
            items(karten.distinctBy { it.url }, key = { it.url }) { k ->
                PosterKarte(k.titel, k.cover, unter = k.genre) { oeffnen(Ziel.Serie(k.url, k.titel, k.cover, k.staffel)) }
            }
        }
    }
}

/** Große Karten oben, wie die Spotlight-Leisten von Streamingseiten; wechseln alle sechs Sekunden. */
@Composable
private fun Spotlight(@StringRes reihe: Int, quelle: String, karten: List<Karte>, oeffnen: (Ziel) -> Unit) {
    if (karten.isEmpty()) return
    val pager = rememberPagerState { karten.size }
    LaunchedEffect(pager, karten.size) {
        while (karten.size > 1) {
            delay(6_000)
            if (!pager.isScrollInProgress) pager.animateScrollToPage((pager.currentPage + 1) % karten.size)
        }
    }
    Column(Modifier.padding(top = 18.dp)) {
        HorizontalPager(
            state = pager,
            contentPadding = PaddingValues(horizontal = 16.dp),
            pageSpacing = 10.dp,
            key = { karten[it].url },
        ) { i ->
            val k = karten[i]
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(212.dp)
                    .clip(Rund)
                    .border(1.dp, Farbe.linie, Rund)
                    .clickable { oeffnen(Ziel.Serie(k.url, k.titel, k.cover, k.staffel)) },
            ) {
                Cover(k.cover, Modifier.fillMaxSize().unscharf(26.dp), ecken = 0.dp)
                Box(
                    Modifier.fillMaxSize().background(
                        Brush.horizontalGradient(listOf(Farbe.hintergrund.copy(alpha = 0.96f), Farbe.hintergrund.copy(alpha = 0.55f))),
                    ),
                )
                Row(Modifier.fillMaxSize().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Cover(k.cover, Modifier.width(122.dp).height(183.dp), ecken = 10.dp)
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            SeitenLogo(quelle, 16.dp)
                            Spacer(Modifier.width(6.dp))
                            Text(stringResource(reihe), color = Farbe.text2, style = MaterialTheme.typography.labelMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(k.titel, color = Farbe.textStark, style = MaterialTheme.typography.titleLarge, maxLines = 3, overflow = TextOverflow.Ellipsis)
                        if (k.genre.isNotBlank()) {
                            Spacer(Modifier.height(4.dp))
                            Text(k.genre, color = Farbe.text3, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Spacer(Modifier.height(14.dp))
                        HauptKnopf(stringResource(R.string.ansehen), icon = Icons.Rounded.PlayArrow, klein = true) { oeffnen(Ziel.Serie(k.url, k.titel, k.cover, k.staffel)) }
                    }
                }
            }
        }
        if (karten.size > 1) {
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.Center) {
                repeat(karten.size) { i ->
                    val an = i == pager.currentPage
                    Box(
                        Modifier
                            .padding(horizontal = 3.dp)
                            .height(6.dp)
                            .width(if (an) 18.dp else 6.dp)
                            .clip(CircleShape)
                            .background(if (an) Farbe.akzent else Farbe.linieHover),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun NeueFolgeKarte(a: Anbieter, f: NeueFolge, oeffnen: (Ziel) -> Unit) {
    val serie = a.serienUrl(f.url) ?: return
    Column(
        Modifier
            .width(232.dp)
            .karte()
            .clickable { oeffnen(Ziel.Serie(serie, f.titel, null, f.staffel)) }
            .padding(12.dp),
    ) {
        Text(
            f.titel,
            style = MaterialTheme.typography.titleSmall,
            color = Farbe.textStark,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.height(40.dp),
        )
        Spacer(Modifier.height(8.dp))
        Text("S%02d · E%02d".format(f.staffel, f.folge), color = Farbe.link, style = MaterialTheme.typography.labelLarge)
        // Eigene Zeile für die Sprachen: Bei drei Fassungen reichte die Kartenbreite neben S/E nicht.
        Spacer(Modifier.height(6.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            f.sprachen.forEach { SprachMarke(it) }
        }
        Spacer(Modifier.height(4.dp))
        Text(f.datum, color = Farbe.text3, style = MaterialTheme.typography.labelSmall)
    }
}
