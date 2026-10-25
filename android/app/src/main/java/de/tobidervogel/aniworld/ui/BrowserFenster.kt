package de.tobidervogel.aniworld.ui

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.hoster.Hosters
import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.net.Check
import de.tobidervogel.aniworld.net.Netz
import kotlinx.coroutines.delay
import org.json.JSONArray

/**
 * Sichtbares Browserfenster für Schutzseiten. Erst wenn die Seite echten Inhalt zeigt
 * (oder beim Redirect aniworld.to verlässt), schließt es sich und die App macht weiter.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun BrowserFenster() {
    val anfrage by BrowserCheck.offen.collectAsState()
    val a = anfrage ?: return
    var web by remember(a) { mutableStateOf<WebView?>(null) }

    fun fertig(url: String?) {
        CookieManager.getInstance().flush()
        a.ergebnis.complete(url)
    }

    Dialog(
        onDismissRequest = { a.ergebnis.complete(null) },
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false),
    ) {
        Column(Modifier.fillMaxSize().background(Farbe.hintergrund).navigationBarsPadding()) {
            Kopfzeile(stringResource(R.string.browser_check), zurueck = { a.ergebnis.complete(null) })
            Text(
                if (a.verlassen) stringResource(R.string.browser_check_hoster, Netz.host(a.url))
                else stringResource(R.string.browser_check_seite, Netz.host(a.url)),
                color = Farbe.text2,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
            AndroidView(
                factory = { ctx ->
                    WebView(ctx).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        // Fremde Seiten sollen weder Dateien noch Inhalte anderer Apps lesen können.
                        settings.allowFileAccess = false
                        settings.allowContentAccess = false
                        // Gleicher User-Agent wie OkHttp: Die Freigabe-Cookies hängen am Browser.
                        settings.userAgentString = App.self.netz.userAgent
                        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                        webViewClient = object : WebViewClient() {
                            private fun verlassen(url: String): Boolean {
                                if (a.verlassen && Netz.host(url).removePrefix("www.") !in a.heim && url.startsWith("http")) {
                                    fertig(url)
                                    return true
                                }
                                return false
                            }

                            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest): Boolean {
                                // Nur Webseiten: intent:, market: und Ähnliches bleibt blockiert.
                                if (!Netz.istWeb(request.url.toString())) return true
                                return request.isForMainFrame && verlassen(request.url.toString())
                            }

                            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                                if (url != null && verlassen(url)) view?.stopLoading()
                            }
                        }
                        loadUrl(a.url)
                        web = this
                    }
                },
                modifier = Modifier.weight(1f).fillMaxWidth(),
            )
        }
    }

    // Regelmäßig nachsehen, ob die Schutzseite weg ist.
    LaunchedEffect(a, web) {
        val w = web ?: return@LaunchedEffect
        if (a.verlassen) {
            // Manche Seiten (Burning Series) leiten nicht weiter, sondern betten den Hoster nach der
            // Prüfung als iframe ein. Dann gilt dessen Adresse als Ziel.
            delay(2_000)
            while (!a.ergebnis.isCompleted) {
                w.evaluateJavascript(IFRAMES) { r ->
                    val srcs = runCatching { JSONArray("[$r]").getString(0) }.getOrNull().orEmpty().lines()
                    srcs.firstOrNull { istPlayer(it, a.heim) }?.let { fertig(it) }
                }
                delay(1_500)
            }
            return@LaunchedEffect
        }
        delay(1_500)
        while (!a.ergebnis.isCompleted) {
            w.evaluateJavascript("document.documentElement.outerHTML.substring(0, 6000)") { r ->
                val html = runCatching { JSONArray("[$r]").getString(0) }.getOrNull().orEmpty()
                val url = w.url.orEmpty()
                if (html.length > 200 && !Check.istSchutzseite(html) && Netz.host(url) == Netz.host(a.url)) fertig(url)
            }
            delay(1_500)
        }
    }

    DisposableEffect(a) {
        onDispose {
            web?.stopLoading()
            web?.destroy()
        }
    }
}

private const val IFRAMES = "Array.from(document.querySelectorAll('iframe')).map(function(f){return f.src}).join('\\n')"

/** Fremde Prüf- und Werbe-Frames, die nie der Hoster sind. */
private val KEIN_PLAYER = listOf("challenges.cloudflare.com", "google", "facebook", "recaptcha", "hcaptcha", "doubleclick", "twitter")

/** Ein eingebetteter Hoster: eigene Domain, bekannter Hoster oder typische Player-Adresse (/e/, /embed, /v/). */
private fun istPlayer(url: String, heim: Set<String>): Boolean {
    if (!Netz.istWeb(url)) return false
    val host = Netz.host(url).removePrefix("www.")
    if (host in heim || KEIN_PLAYER.any { it in host }) return false
    return Hosters.fuer(url) != null || Regex("""/(e|v|embed)/""").containsMatchIn(url)
}
