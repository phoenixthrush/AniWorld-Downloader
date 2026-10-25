package de.tobidervogel.aniworld.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import de.tobidervogel.aniworld.R

/**
 * Farben aus den Design-Werten der Web-UI (web/static/style.css, :root). Die halbdurchsichtigen
 * Flächen dort (rgba(255,255,255,.03) usw.) sind hier auf den Hintergrund #0a0a0f vorgerechnet.
 */
object Farbe {
    val hintergrund = Color(0xFF0A0A0F)      // --bg
    val flaeche = Color(0xFF111116)          // --surface
    val flaeche2 = Color(0xFF18181D)         // --surface-strong
    val flaecheHover = Color(0xFF222227)     // --surface-hover
    val modal = Color(0xFF101018)            // --surface-modal
    val nav = Color(0xFF0E0E14)              // --surface-nav
    val eingabe = Color(0xFF141419)          // --surface-input
    val poster = Color(0xFF12121A)           // --surface-poster
    val linie = Color(0xFF1E1E23)            // --border
    val linieHover = Color(0xFF34343A)       // --border-hover
    val text = Color(0xFFC8CAD0)             // --text
    val textStark = Color(0xFFFFFFFF)        // --text-strong
    val text2 = Color(0xFF9CA3AF)            // --text-dim
    val text3 = Color(0xFF6B7280)            // --text-muted
    val segment = Color(0xFF666666)          // --segment-text
    val akzent = Color(0xFF2563EB)           // --accent
    val akzentDunkel = Color(0xFF1D4ED8)     // --accent-dark
    val akzentFlaeche = Color(0x262563EB)    // --accent-soft
    val lila = Color(0xFF9333EA)             // --purple
    val link = Color(0xFF6EA8FE)             // --link
    val fehler = Color(0xFFEF4444)           // --danger
    val fehlerText = Color(0xFFFCA5A5)       // --danger-text
    val gut = Color(0xFF22C55E)              // --success
    val warnung = Color(0xFFF59E0B)          // --warning
    val hinweisText = Color(0xFFFCD34D)      // --notice-text

    val verlaufAkzent = Brush.linearGradient(listOf(akzent, akzentDunkel))        // --gradient-accent
    val verlaufFortschritt = Brush.horizontalGradient(listOf(akzent, lila))       // --gradient-progress
}

/** Seitenfarben wie der Umschalter der Web-UI (--site-*-bg). */
object Seitenfarbe {
    fun verlauf(seite: String): Brush = Brush.linearGradient(farben(seite))

    fun farben(seite: String): List<Color> = when (seite) {
        "SerienStream" -> listOf(Color(0xFF38BDF8), Color(0xFF2563EB))
        "Filmo" -> listOf(Color(0xFFD946EF), Color(0xFFA21CAF))
        "FilmPalast" -> listOf(Color(0xFF84CC16), Color(0xFF4D7C0F))
        "MegaKino" -> listOf(Color(0xFFEF4444), Color(0xFFB91C1C))
        "Kinox" -> listOf(Color(0xFF34D399), Color(0xFF059669))
        "BurningSeries" -> listOf(Color(0xFFFB923C), Color(0xFFEA580C))
        "Moflix" -> listOf(Color(0xFFF43F5E), Color(0xFFBE123C))
        else -> listOf(Color(0xFF8B5CF6), Color(0xFF6D28D9))
    }
}

@OptIn(ExperimentalTextApi::class)
private fun inter(gewicht: Int) =
    Font(R.font.inter, FontWeight(gewicht), variationSettings = FontVariation.Settings(FontVariation.weight(gewicht)))

/** Inter wie in der Web-UI (--font-body), als variable Schrift eingebunden. */
val Inter = FontFamily(inter(400), inter(500), inter(600), inter(700), inter(800))

private val schrift = Typography().let { t ->
    fun TextStyle.inter() = copy(fontFamily = Inter)
    Typography(
        displayLarge = t.displayLarge.inter(),
        displayMedium = t.displayMedium.inter(),
        displaySmall = t.displaySmall.inter(),
        headlineLarge = t.headlineLarge.inter().copy(fontWeight = FontWeight.Bold),
        headlineMedium = t.headlineMedium.inter().copy(fontWeight = FontWeight.Bold, fontSize = 26.sp, letterSpacing = (-0.5).sp),
        headlineSmall = t.headlineSmall.inter().copy(fontWeight = FontWeight.Bold, fontSize = 22.sp, letterSpacing = (-0.3).sp),
        titleLarge = t.titleLarge.inter().copy(fontWeight = FontWeight.SemiBold, fontSize = 18.sp),
        titleMedium = t.titleMedium.inter().copy(fontWeight = FontWeight.SemiBold, fontSize = 15.sp),
        titleSmall = t.titleSmall.inter().copy(fontWeight = FontWeight.SemiBold, fontSize = 14.sp),
        bodyLarge = t.bodyLarge.inter(),
        bodyMedium = t.bodyMedium.inter().copy(fontSize = 14.sp, lineHeight = 21.sp),
        bodySmall = t.bodySmall.inter().copy(fontSize = 12.5.sp),
        labelLarge = t.labelLarge.inter().copy(fontWeight = FontWeight.SemiBold),
        labelMedium = t.labelMedium.inter().copy(fontWeight = FontWeight.SemiBold),
        labelSmall = t.labelSmall.inter().copy(fontSize = 11.sp, fontWeight = FontWeight.SemiBold),
    )
}

private val farben = darkColorScheme(
    primary = Farbe.akzent,
    onPrimary = Color.White,
    primaryContainer = Farbe.akzentFlaeche,
    onPrimaryContainer = Farbe.link,
    secondary = Farbe.lila,
    onSecondary = Color.White,
    secondaryContainer = Farbe.flaeche2,
    onSecondaryContainer = Farbe.textStark,
    background = Farbe.hintergrund,
    onBackground = Farbe.text,
    surface = Farbe.hintergrund,
    onSurface = Farbe.text,
    surfaceVariant = Farbe.flaeche2,
    onSurfaceVariant = Farbe.text2,
    surfaceContainerLowest = Farbe.hintergrund,
    surfaceContainerLow = Farbe.flaeche,
    surfaceContainer = Farbe.flaeche,
    surfaceContainerHigh = Farbe.modal,
    surfaceContainerHighest = Farbe.flaeche2,
    outline = Farbe.linie,
    outlineVariant = Farbe.linie,
    error = Farbe.fehler,
    onError = Color.White,
)

@Composable
fun Thema(inhalt: @Composable () -> Unit) {
    MaterialTheme(colorScheme = farben, typography = schrift, content = inhalt)
}
