package de.tobidervogel.aniworld.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.os.Build
import androidx.annotation.DrawableRes
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import de.tobidervogel.aniworld.BuildConfig
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.download.Status
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.site.StaffelRef
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/** Die Activity hinter einem Compose-Kontext (für Berechtigungsdialoge). */
tailrec fun Context.activity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.activity()
    else -> null
}

/**
 * Unscharfer Hintergrund. Weichzeichnen kann Android erst ab 12; davor bleibt das Bild scharf
 * und wird stattdessen stark abgedunkelt, damit der Text darüber lesbar bleibt.
 */
fun Modifier.unscharf(radius: Dp): Modifier =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) blur(radius) else alpha(0.35f)

/** Lädt etwas einmal und merkt sich Ergebnis oder Fehler; lebt außerhalb der Komposition. */
class Ladung<T>(private val scope: CoroutineScope, private val holen: suspend () -> T) {
    var daten by mutableStateOf<T?>(null)
        private set
    var fehler by mutableStateOf<String?>(null)
        private set
    var laeuft by mutableStateOf(false)
        private set

    fun start(neu: Boolean = false) {
        if (laeuft || (daten != null && !neu)) return
        laeuft = true
        fehler = null
        scope.launch {
            try {
                daten = holen()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Protokoll.fehler("Laden fehlgeschlagen", e)
                fehler = e.message ?: e.javaClass.simpleName
            } finally {
                laeuft = false
            }
        }
    }
}

// Formen wie --radius (12px), --radius-sm (10px), --radius-xs (8px) der Web-UI.
val Rund = RoundedCornerShape(12.dp)
val RundKlein = RoundedCornerShape(10.dp)
val RundMini = RoundedCornerShape(8.dp)

/** Fläche mit Rahmen, wie .card der Web-UI. */
fun Modifier.karte(form: RoundedCornerShape = Rund, farbe: Color = Farbe.flaeche) =
    this.clip(form).background(farbe).border(1.dp, Farbe.linie, form)

@Composable
fun Cover(url: String?, modifier: Modifier = Modifier, ecken: Dp = 10.dp) {
    val ctx = LocalContext.current
    Box(modifier.clip(RoundedCornerShape(ecken)).background(Farbe.poster), contentAlignment = Alignment.Center) {
        if (url == null) {
            Icon(Icons.Rounded.Movie, null, tint = Farbe.linieHover, modifier = Modifier.size(28.dp))
        } else {
            AsyncImage(
                // Manche Seiten liefern Cover nur mit eigenem Referer aus.
                model = ImageRequest.Builder(ctx).data(url).addHeader("Referer", Netz.ursprung(url) + "/").build(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

/**
 * Poster mit Titelzeile darunter, wie die Karten der Web-UI. `breite = null`: volle Breite (Raster).
 * `unter`: zweite, gedämpfte Zeile (Genre, Jahr).
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PosterKarte(
    titel: String,
    cover: String?,
    modifier: Modifier = Modifier,
    breite: Dp? = 128.dp,
    unter: String? = null,
    onLongClick: (() -> Unit)? = null,
    onClick: () -> Unit,
) {
    val m = if (breite != null) modifier.width(breite) else modifier.fillMaxWidth()
    Column(m.karte().combinedClickable(onClick = onClick, onLongClick = onLongClick)) {
        Cover(cover, Modifier.fillMaxWidth().aspectRatio(2f / 3f), ecken = 0.dp)
        Column(Modifier.padding(horizontal = 10.dp, vertical = 9.dp)) {
            Text(
                titel,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                color = Farbe.textStark,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!unter.isNullOrBlank()) {
                Text(unter, style = MaterialTheme.typography.bodySmall, color = Farbe.text3, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** Suchleiste als Knopf (Startseite), sieht aus wie das Eingabefeld der Web-UI. */
@Composable
fun SuchKnopf(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(
        modifier
            .height(48.dp)
            .clip(RundKlein)
            .background(Farbe.eingabe)
            .border(1.dp, Farbe.linie, RundKlein)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.Search, null, tint = Farbe.text3, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, color = Farbe.text3, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

// ------------------------------------------------------------ Sprachen

private data class Badge(val flaggen: List<Int>, val text: String, val rand: Color, val schrift: Color)

/** Wie LANGUAGE_BADGES in home.js: Flagge(n) plus „Dub“/„Sub“, Farbe je Fassung. */
private fun badge(s: Sprache) = when (s) {
    Sprache.DE_DUB -> Badge(listOf(R.drawable.flagge_de), "Dub", Color(0x592563EB), Color(0xFF93C5FD))
    Sprache.DE_SUB -> Badge(listOf(R.drawable.flagge_jp, R.drawable.flagge_de), "Sub", Color(0x599333EA), Color(0xFFD8B4FE))
    Sprache.EN_DUB -> Badge(listOf(R.drawable.flagge_gb), "Dub", Color(0x5922C55E), Color(0xFF86EFAC))
    Sprache.EN_SUB -> Badge(listOf(R.drawable.flagge_jp, R.drawable.flagge_gb), "Sub", Color(0x59F59E0B), Color(0xFFFCD34D))
}

@Composable
fun SprachMarke(s: Sprache, aktiv: Boolean = true) {
    val b = badge(s)
    val form = RoundedCornerShape(5.dp)
    Row(
        Modifier
            .clip(form)
            .background(Farbe.flaeche2)
            .border(1.dp, if (aktiv) b.rand else Farbe.linie, form)
            .padding(horizontal = 6.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        b.flaggen.forEach { f ->
            Image(painterResource(f), null, Modifier.width(13.dp).height(9.dp).clip(RoundedCornerShape(1.dp)), contentScale = ContentScale.Crop)
        }
        Text(b.text, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, fontFamily = Inter, color = if (aktiv) b.schrift else Farbe.text3, maxLines = 1, softWrap = false)
    }
}

/** Langer Name für Auswahlknöpfe, wie die Sprachauswahl der Web-UI. */
@Composable
fun Sprache.anzeige(): String = stringResource(anzeigeRes)

/** „Staffel 2“ oder „Filme“ in der Sprache des Handys. */
@Composable
fun StaffelRef.anzeige(): String = bezeichnung ?: if (istFilme) stringResource(R.string.filme) else stringResource(R.string.staffel_n, nummer)

// ------------------------------------------------------------ Knöpfe

/** Hauptknopf mit blauem Verlauf (--gradient-accent). */
@Composable
fun HauptKnopf(
    text: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    aktiv: Boolean = true,
    klein: Boolean = false,
    onClick: () -> Unit,
) {
    Row(
        modifier
            .then(if (aktiv) Modifier.shadow(8.dp, RundKlein, ambientColor = Farbe.akzent, spotColor = Farbe.akzent) else Modifier)
            .clip(RundKlein)
            .background(if (aktiv) Farbe.verlaufAkzent else SolidColor(Farbe.flaeche2))
            .clickable(enabled = aktiv, onClick = onClick)
            .padding(horizontal = if (klein) 14.dp else 18.dp, vertical = if (klein) 9.dp else 13.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Icon(icon, null, tint = if (aktiv) Color.White else Farbe.text3, modifier = Modifier.size(19.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, color = if (aktiv) Color.White else Farbe.text3, fontWeight = FontWeight.SemiBold, fontFamily = Inter, fontSize = if (klein) 14.sp else 15.sp)
    }
}

/** Zweitknopf: dunkle Fläche mit Rahmen, wie „Random“ oder „Try again“ in der Web-UI. */
@Composable
fun ZweitKnopf(
    text: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    aktiv: Boolean = true,
    klein: Boolean = false,
    onClick: () -> Unit,
) {
    Row(
        modifier
            .clip(RundKlein)
            .background(Farbe.flaeche2)
            .border(1.dp, Farbe.linie, RundKlein)
            .clickable(enabled = aktiv, onClick = onClick)
            .padding(horizontal = if (klein) 12.dp else 16.dp, vertical = if (klein) 8.dp else 12.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Icon(icon, null, tint = if (aktiv) Farbe.text else Farbe.text3, modifier = Modifier.size(if (klein) 16.dp else 18.dp))
            Spacer(Modifier.width(if (klein) 5.dp else 7.dp))
        }
        Text(
            text,
            color = if (aktiv) Farbe.textStark else Farbe.text3,
            fontWeight = FontWeight.SemiBold,
            fontFamily = Inter,
            fontSize = if (klein) 13.sp else 14.sp,
            maxLines = 1,
        )
    }
}

/** Pille wie die Genre-Chips und Filter der Web-UI; gewählt mit blauem Rand auf blauer Tönung. */
@Composable
fun Pille(text: String, gewaehlt: Boolean, aktiv: Boolean = true, zahl: Int? = null, onClick: () -> Unit) {
    val form = RoundedCornerShape(50)
    Row(
        Modifier
            .clip(form)
            .background(if (gewaehlt && aktiv) Farbe.akzentFlaeche else Color.Transparent)
            .border(1.dp, if (gewaehlt && aktiv) Farbe.akzent else Farbe.linie, form)
            .clickable(enabled = aktiv, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelLarge,
            color = when {
                !aktiv -> Farbe.text3
                gewaehlt -> Farbe.textStark
                else -> Farbe.text
            },
        )
        if (zahl != null) {
            Spacer(Modifier.width(6.dp))
            Text("$zahl", style = MaterialTheme.typography.labelLarge, color = Farbe.text3)
        }
    }
}

/** Ankreuzfeld wie .checkbox der Web-UI: gerahmtes Kästchen, angekreuzt blau gefüllt. */
@Composable
fun Haken(an: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val form = RoundedCornerShape(6.dp)
    Box(
        modifier
            .size(22.dp)
            .clip(form)
            .background(if (an) Farbe.akzent else Color.Transparent)
            .border(1.5.dp, if (an) Farbe.akzent else Farbe.linieHover, form)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (an) Icon(Icons.Rounded.Check, null, tint = Color.White, modifier = Modifier.size(16.dp))
    }
}

/** Beschriftetes Feld wie .field der Web-UI: kleine gedämpfte Überschrift, darunter der Inhalt. */
@Composable
fun Feld(titel: String, modifier: Modifier = Modifier, inhalt: @Composable () -> Unit) {
    Column(modifier) {
        Text(titel, color = Farbe.text3, style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.height(8.dp))
        inhalt()
    }
}

/** Auswahlpille für eine Sprache: Flaggen-Marke plus langer Name. */
@Composable
fun SprachPille(s: Sprache, gewaehlt: Boolean, aktiv: Boolean = true, zahl: String? = null, onClick: () -> Unit) {
    val form = RoundedCornerShape(50)
    Row(
        Modifier
            .clip(form)
            .background(if (gewaehlt && aktiv) Farbe.akzentFlaeche else Color.Transparent)
            .border(1.dp, if (gewaehlt && aktiv) Farbe.akzent else Farbe.linie, form)
            .clickable(enabled = aktiv, onClick = onClick)
            .padding(start = 8.dp, end = 14.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SprachMarke(s, aktiv)
        Spacer(Modifier.width(8.dp))
        Text(
            s.anzeige(),
            style = MaterialTheme.typography.labelLarge,
            color = when {
                !aktiv -> Farbe.text3
                gewaehlt -> Farbe.textStark
                else -> Farbe.text
            },
        )
        if (zahl != null) {
            Spacer(Modifier.width(6.dp))
            Text(zahl, style = MaterialTheme.typography.labelLarge, color = Farbe.text3)
        }
    }
}

// ------------------------------------------------------------ Seiten

/**
 * Die Icons der Seiten liegen in der App (res/drawable-nodpi, von den Seiten selbst, Stand 25.10.2026).
 * Aus dem Netz geladen fehlten sie, sobald eine Seite DDoS-Guard oder Cloudflare vorschaltet.
 */
@DrawableRes
fun seitenLogo(seite: String): Int? = when (seite) {
    "AniWorld" -> R.drawable.logo_aniworld
    "SerienStream" -> R.drawable.logo_serienstream
    "Filmo" -> R.drawable.logo_filmo
    "FilmPalast" -> R.drawable.logo_filmpalast
    "BurningSeries" -> R.drawable.logo_burningseries
    "Kinox" -> R.drawable.logo_kinox
    "MegaKino" -> R.drawable.logo_megakino
    "Moflix" -> R.drawable.logo_moflix
    else -> null
}

/** Logo einer Seite; für eine unbekannte Seite ein Kürzel in ihrer Farbe. */
@Composable
fun SeitenLogo(seite: String, groesse: Dp = 20.dp) {
    val logo = seitenLogo(seite)
    if (logo != null) {
        Image(painterResource(logo), null, Modifier.size(groesse).clip(RoundedCornerShape(groesse / 4)), contentScale = ContentScale.Fit)
        return
    }
    Box(Modifier.size(groesse).clip(RoundedCornerShape(groesse / 4)).background(Seitenfarbe.verlauf(seite)), contentAlignment = Alignment.Center) {
        Text(seite.take(1), color = Color.White, fontWeight = FontWeight.Bold, fontFamily = Inter, fontSize = (groesse.value * 0.55f).sp)
    }
}

/**
 * Seitenumschalter wie .segmented in der Web-UI: gemeinsame Fläche, die gewählte Seite in ihrer
 * eigenen Farbe. Mit mehr Seiten als Platz lässt er sich seitlich wischen und rückt die gewählte ins Bild.
 */
@Composable
fun SeitenUmschalter(seiten: List<String>, gewaehlt: String, modifier: Modifier = Modifier, waehlen: (String) -> Unit) {
    val liste = rememberLazyListState()
    LaunchedEffect(gewaehlt) {
        val i = seiten.indexOf(gewaehlt)
        if (i >= 0) liste.animateScrollToItem(maxOf(0, i - 1))
    }
    LazyRow(
        modifier.fillMaxWidth().karte(),
        state = liste,
        contentPadding = PaddingValues(6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        items(seiten, key = { it }) { s ->
            val aktiv = s == gewaehlt
            val farben = Seitenfarbe.farben(s)
            Row(
                Modifier
                    .then(if (aktiv) Modifier.shadow(8.dp, RoundedCornerShape(9.dp), ambientColor = farben[0], spotColor = farben[0]) else Modifier)
                    .clip(RoundedCornerShape(9.dp))
                    .background(if (aktiv) Seitenfarbe.verlauf(s) else SolidColor(Color.Transparent))
                    .clickable { waehlen(s) }
                    .padding(vertical = 10.dp, horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SeitenLogo(s, 16.dp)
                Spacer(Modifier.width(6.dp))
                Text(
                    s,
                    color = if (aktiv) Color.White else Farbe.segment,
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = Inter,
                    fontSize = 13.sp,
                    maxLines = 1,
                )
            }
        }
    }
}

// ------------------------------------------------------------ Kopf und Abschnitte

/** Obere Leiste wie die Web-UI: Logo, App-Name und Version. */
@Composable
fun AppLeiste(rechts: @Composable () -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().height(60.dp).padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Image(painterResource(R.drawable.logo), null, Modifier.size(32.dp).clip(CircleShape))
        Spacer(Modifier.width(10.dp))
        Text(stringResource(R.string.app_name), color = Farbe.textStark, fontWeight = FontWeight.Bold, fontFamily = Inter, fontSize = 18.sp)
        Spacer(Modifier.width(8.dp))
        Text("v${BuildConfig.VERSION_NAME}", color = Farbe.text3, fontFamily = Inter, fontSize = 13.sp, modifier = Modifier.weight(1f))
        rechts()
    }
    Trennlinie()
}

@Composable
fun Trennlinie(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(1.dp).background(Farbe.linie))
}

@Composable
fun Kopfzeile(titel: String, zurueck: (() -> Unit)? = null, rechts: @Composable () -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().height(56.dp).padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (zurueck != null) {
            IconButton(onClick = zurueck) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, stringResource(R.string.zurueck), tint = Farbe.textStark) }
        } else {
            Spacer(Modifier.width(12.dp))
        }
        Text(
            titel,
            style = MaterialTheme.typography.titleLarge,
            color = Farbe.textStark,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        rechts()
    }
}

/** Große Seitenüberschrift wie „Download Queue“ / „Settings“ in der Web-UI. */
@Composable
fun SeitenTitel(titel: String, modifier: Modifier = Modifier, rechts: @Composable () -> Unit = {}) {
    Row(modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        // Eine Zeile: Mit einem Knopf daneben brach „Warteschlange“ auf schmalen Handys sonst um.
        Text(
            titel,
            style = MaterialTheme.typography.headlineMedium,
            fontSize = 24.sp,
            color = Farbe.textStark,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Spacer(Modifier.width(8.dp))
        rechts()
    }
}

@Composable
fun Abschnitt(titel: String, modifier: Modifier = Modifier, rechts: @Composable () -> Unit = {}) {
    Row(modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 24.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(titel, style = MaterialTheme.typography.titleLarge, color = Farbe.textStark, modifier = Modifier.weight(1f))
        rechts()
    }
}

@Composable
fun LadeKreis(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = Farbe.akzent, strokeWidth = 3.dp, modifier = Modifier.size(28.dp))
    }
}

@Composable
fun Fehlerkasten(text: String, modifier: Modifier = Modifier, nochmal: (() -> Unit)? = null) {
    Column(
        modifier.fillMaxWidth().padding(16.dp).karte().padding(18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Rounded.ErrorOutline, null, tint = Farbe.fehler)
        Text(text, color = Farbe.text2, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyMedium)
        if (nochmal != null) ZweitKnopf(stringResource(R.string.erneut_versuchen), onClick = nochmal)
    }
}

/** Hinweis wie .notice der Web-UI (gelb getönt). */
@Composable
fun Hinweis(text: String, modifier: Modifier = Modifier, aktion: Pair<String, () -> Unit>? = null) {
    Column(
        modifier.fillMaxWidth().clip(RundKlein).background(Color(0x14F59E0B)).border(1.dp, Color(0x40F59E0B), RundKlein).padding(14.dp),
    ) {
        Text(text, color = Farbe.hinweisText, style = MaterialTheme.typography.bodyMedium)
        if (aktion != null) {
            Spacer(Modifier.height(10.dp))
            ZweitKnopf(aktion.first, onClick = aktion.second)
        }
    }
}

// ------------------------------------------------------------ Status und Fortschritt

/** Status-Pille wie --status-* in der Web-UI. */
@Composable
fun StatusPille(s: Status) {
    val (text, grund, schrift) = when (s) {
        Status.WARTET -> Triple(stringResource(R.string.status_wartet), Color(0x336B7280), Color(0xFF9CA3AF))
        Status.LAEUFT -> Triple(stringResource(R.string.status_laeuft), Color(0x332563EB), Color(0xFF93C5FD))
        Status.FERTIG -> Triple(stringResource(R.string.status_fertig), Color(0x2E22C55E), Color(0xFF86EFAC))
        Status.FEHLER -> Triple(stringResource(R.string.status_fehler), Color(0x2EEF4444), Color(0xFFFCA5A5))
        Status.PAUSE -> Triple(stringResource(R.string.status_pause), Color(0x2EF59E0B), Color(0xFFFCD34D))
    }
    Text(
        text,
        color = schrift,
        fontSize = 11.5.sp,
        fontWeight = FontWeight.SemiBold,
        fontFamily = Inter,
        modifier = Modifier.clip(RoundedCornerShape(50)).background(grund).padding(horizontal = 9.dp, vertical = 3.dp),
    )
}

/** Fortschrittsbalken mit dem Verlauf Blau → Lila (--gradient-progress); ohne Wert läuft er durch. */
@Composable
fun Fortschritt(anteil: Float?, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(5.dp).clip(CircleShape).background(Color(0x12FFFFFF))) {
        if (anteil != null) {
            Box(Modifier.fillMaxWidth(anteil.coerceIn(0f, 1f)).height(5.dp).clip(CircleShape).background(Farbe.verlaufFortschritt))
        } else {
            LinearProgressIndicator(color = Farbe.akzent, trackColor = Color.Transparent, modifier = Modifier.fillMaxWidth().height(5.dp))
        }
    }
}

fun dauerText(ms: Long): String {
    val s = ms / 1000
    return if (s >= 3600) "%d:%02d:%02d".format(s / 3600, s / 60 % 60, s % 60) else "%d:%02d".format(s / 60, s % 60)
}

/** Innenabstand der Listen unter der Navigationsleiste. */
val ListenRand = PaddingValues(bottom = 28.dp)
