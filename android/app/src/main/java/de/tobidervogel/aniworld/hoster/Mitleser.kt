package de.tobidervogel.aniworld.hoster

import android.annotation.SuppressLint
import android.content.Context
import android.os.Message
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.net.Netz
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONArray
import java.util.Collections

/**
 * Ausweichweg, wenn kein Extraktor greift: Die Einbettungsseite läuft in einer unsichtbaren
 * WebView, und wir lesen mit, welche .m3u8/.mp4 der Player anfordert. So übersteht die App
 * auch Umbauten eines Hosters, für die es noch keinen Extraktor gibt.
 */
object Mitleser {

    private val VIDEO = Regex("""\.(m3u8|mp4)(\?|$)""", RegexOption.IGNORE_CASE)

    // Startet den Player, klickt gängige Play-Knöpfe und sucht nebenbei selbst nach einer Adresse.
    private const val SKRIPT = """(function(){try{
var v=document.querySelector('video');
if(v){v.muted=true;var p=v.play();if(p&&p.catch)p.catch(function(){});}
['.jw-icon-display','.jw-display-icon-container','.vjs-big-play-button','.plyr__control--overlaid','button[aria-label*="Play"]','.play-button','#play','.btn-play'].forEach(function(s){var b=document.querySelector(s);if(b){try{b.click();}catch(e){}}});
if(window.jwplayer){try{var it=jwplayer().getPlaylistItem();if(it&&it.file)return it.file;}catch(e){}}
var m=document.documentElement.innerHTML.match(/https?:\/\/[^"'\s<>\\]+\.m3u8[^"'\s<>\\]*/);
if(m)return m[0];
if(v&&v.currentSrc&&v.currentSrc.indexOf('http')==0)return v.currentSrc;
return '';}catch(e){return '';}})()"""

    fun istVideo(url: String) = url.startsWith("http") && VIDEO.containsMatchIn(url.substringBefore('#'))

    /** Wählt aus den gesehenen Adressen: Master-Playlist vor anderen m3u8 vor mp4. */
    fun auswaehlen(gesehen: List<String>): String? {
        val m3u8 = gesehen.filter { ".m3u8" in it.lowercase() }
        return m3u8.firstOrNull { "master" in it.lowercase() } ?: m3u8.firstOrNull() ?: gesehen.firstOrNull()
    }

    @SuppressLint("SetJavaScriptEnabled")
    /** @param referer Ursprung der Folgenseite; manche Hoster spielen nur mit passendem Referer ab. */
    suspend fun mitlesen(context: Context, netz: Netz, embed: String, hoster: String, referer: String, zeitMs: Long = 35_000): Stream? =
        withContext(Dispatchers.Main) {
            val gesehen = Collections.synchronizedList(ArrayList<String>())
            val erster = CompletableDeferred<Unit>()
            val startHost = Netz.host(embed)
            val web = WebView(context)
            var seite = embed
            try {
                with(web.settings) {
                    javaScriptEnabled = true
                    domStorageEnabled = true
                    allowFileAccess = false
                    allowContentAccess = false
                    mediaPlaybackRequiresUserGesture = false
                    userAgentString = netz.userAgent
                    // Popups (Werbung) nicht öffnen: Mehrfachfenster an, aber onCreateWindow lehnt ab.
                    setSupportMultipleWindows(true)
                    javaScriptCanOpenWindowsAutomatically = false
                }
                CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)
                web.webChromeClient = object : android.webkit.WebChromeClient() {
                    override fun onCreateWindow(view: WebView?, isDialog: Boolean, isUserGesture: Boolean, resultMsg: Message?) = false
                }
                web.webViewClient = object : WebViewClient() {
                    override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest): WebResourceResponse? {
                        val u = request.url.toString()
                        if (istVideo(u)) {
                            gesehen += u
                            erster.complete(Unit)
                        }
                        return null
                    }

                    override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest): Boolean {
                        if (!Netz.istWeb(request.url.toString())) return true
                        if (!request.isForMainFrame) return false
                        val u = request.url.toString()
                        // Hosterwechsel auf eine andere /e/-Domain zulassen, Werbeziele nicht. Server-Weiterleitungen
                        // und Wechsel innerhalb der aktuellen Domain gehören zum Hoster (VOE: /e/… → /access/…).
                        val erlaubt = request.isRedirect || Netz.host(u) == startHost || Netz.host(u) == Netz.host(seite) ||
                            "/e/" in u || "embed" in u
                        if (erlaubt) seite = u
                        return !erlaubt
                    }

                    override fun onPageFinished(view: WebView?, url: String?) {
                        if (url != null) seite = url
                        view?.evaluateJavascript(SKRIPT) { r -> gefundenImDom(r, gesehen, erster) }
                    }
                }
                web.loadUrl(embed, mapOf("Referer" to referer))

                val ok = withTimeoutOrNull(zeitMs) {
                    coroutineScope {
                        // Alle zwei Sekunden erneut anstoßen: Manche Player bauen sich erst spät auf.
                        val stupser = launch {
                            while (true) {
                                delay(2_000)
                                web.evaluateJavascript(SKRIPT) { r -> gefundenImDom(r, gesehen, erster) }
                            }
                        }
                        erster.await()
                        // Kurz weiter mitlesen: Oft kommt erst die Variante, danach die Master-Playlist.
                        delay(1_500)
                        stupser.cancel()
                    }
                } != null
                val url = if (ok) auswaehlen(gesehen.toList()) else null
                if (url == null) {
                    Protokoll.info("Mitlesen bei $hoster ohne Ergebnis")
                    return@withContext null
                }
                Protokoll.info("Mitlesen bei $hoster: ${url.take(80)}")
                Stream(
                    url = url,
                    header = mapOf(
                        "User-Agent" to netz.userAgent,
                        "Referer" to seite,
                        "Origin" to Js.ursprung(seite),
                    ),
                    hoster = "$hoster (Browser)",
                )
            } finally {
                web.stopLoading()
                web.destroy()
            }
        }

    private fun gefundenImDom(r: String?, gesehen: MutableList<String>, erster: CompletableDeferred<Unit>) {
        val wert = runCatching { JSONArray("[$r]").getString(0) }.getOrNull().orEmpty()
        if (istVideo(wert) && wert !in gesehen) {
            gesehen += wert
            erster.complete(Unit)
        }
    }
}
