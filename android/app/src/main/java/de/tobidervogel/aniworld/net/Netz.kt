package de.tobidervogel.aniworld.net

import android.content.Context
import android.webkit.CookieManager
import android.webkit.WebSettings
import de.tobidervogel.aniworld.Einstellungen
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.Dns
import okhttp3.FormBody
import okhttp3.Headers
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.dnsoverhttps.DnsOverHttps
import java.io.IOException
import java.net.InetAddress
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit

data class Antwort(val code: Int, val url: String, val text: String, val header: Headers) {
    val ok get() = code in 200..299
}

class NetzFehler(meldung: String, ursache: Throwable? = null) : IOException(meldung, ursache)

/**
 * Ein OkHttp-Client für alles: Seiten, Hoster, Segmente, Cover und Player.
 *
 * - DNS über HTTPS (Cloudflare), weil deutsche Provider aniworld.to per DNS sperren.
 *   Das Python-Original nutzt dafür `resolver=["doh+cloudflare://"]`.
 * - Cookies liegen im CookieManager der WebView. Löst der Browser-Check im Fenster
 *   eine DDoS-Guard-Prüfung, hat OkHttp die Cookies sofort mit.
 * - Überall derselbe User-Agent wie in der WebView; Doodstream etwa bindet den Link daran.
 */
class Netz(context: Context, private val einst: Einstellungen) {

    val userAgent: String = runCatching { WebSettings.getDefaultUserAgent(context) }
        .getOrDefault(FALLBACK_UA)
        .replace("; wv", "")
        .replace("Version/4.0 ", "")
        .replace(Regex(" Build/[^;)]+"), "")

    private val cookies = CookieManager.getInstance().apply { setAcceptCookie(true) }

    private val doh: Dns by lazy {
        DnsOverHttps.Builder()
            .client(OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).build())
            .url("https://cloudflare-dns.com/dns-query".toHttpUrl())
            .bootstrapDnsHosts(InetAddress.getByName("1.1.1.1"), InetAddress.getByName("1.0.0.1"))
            .build()
    }

    private val dns = object : Dns {
        override fun lookup(hostname: String): List<InetAddress> {
            if (!einst.doh) return Dns.SYSTEM.lookup(hostname)
            return try {
                doh.lookup(hostname)
            } catch (e: UnknownHostException) {
                Dns.SYSTEM.lookup(hostname)
            }
        }
    }

    private val jar = object : CookieJar {
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            for (c in cookies) this@Netz.cookies.setCookie(url.toString(), c.toString())
        }

        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val roh = this@Netz.cookies.getCookie(url.toString()) ?: return emptyList()
            return roh.split(';').mapNotNull { Cookie.parse(url, it.trim()) }
        }
    }

    val client: OkHttpClient = OkHttpClient.Builder()
        .dns(dns)
        .cookieJar(jar)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .addInterceptor { chain ->
            val r = chain.request()
            val b = r.newBuilder()
            if (r.header("User-Agent") == null) b.header("User-Agent", userAgent)
            if (r.header("Accept-Language") == null) b.header("Accept-Language", "de-DE,de;q=0.9,en;q=0.8")
            chain.proceed(b.build())
        }
        .build()

    /** Einfache Anfrage ohne Check-Behandlung. Läuft auf dem IO-Dispatcher. */
    suspend fun anfrage(
        url: String,
        header: Map<String, String> = emptyMap(),
        formular: Map<String, String>? = null,
        json: String? = null,
    ): Antwort = withContext(Dispatchers.IO) {
        val b = Request.Builder().url(url)
        b.header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        header.forEach { (k, v) -> b.header(k, v) }
        if (formular != null) {
            val f = FormBody.Builder()
            formular.forEach { (k, v) -> f.add(k, v) }
            b.post(f.build())
        }
        if (json != null) b.post(json.toRequestBody("application/json; charset=utf-8".toMediaType()))
        try {
            client.newCall(b.build()).execute().use { r ->
                Antwort(r.code, r.request.url.toString(), r.body?.string().orEmpty(), r.headers)
            }
        } catch (e: UnknownHostException) {
            throw NetzFehler(tr(R.string.e_dns, host(url)), e)
        } catch (e: IOException) {
            throw NetzFehler("${host(url)}: ${e.message ?: e.javaClass.simpleName}", e)
        }
    }

    /**
     * Seite von aniworld.to. Erkennt die DDoS-Guard-Prüfung und lässt sie einmal im
     * sichtbaren Browserfenster laufen (der Nutzer sieht sie und kann ein Rätsel lösen).
     */
    suspend fun seite(url: String, formular: Map<String, String>? = null, header: Map<String, String> = emptyMap()): Antwort {
        val kopf = mapOf("Referer" to ursprung(url) + "/") + header
        var a = anfrage(url, kopf, formular)
        if (Check.istCheck(a)) {
            Protokoll.info("Browser-Check nötig für ${host(url)} (HTTP ${a.code})")
            if (BrowserCheck.loesen(url) != null) a = anfrage(url, kopf, formular)
        }
        if (Check.istCheck(a)) {
            throw NetzFehler(tr(R.string.e_check, host(url)))
        }
        if (!a.ok) throw NetzFehler(tr(R.string.e_http, host(url), a.code))
        return a
    }

    fun cookiesSichern() = cookies.flush()

    companion object {
        /** Nur http(s): Alles andere (intent:, file:, javascript:) hat in den Browserfenstern nichts zu suchen. */
        fun istWeb(url: String) = url.startsWith("https://", ignoreCase = true) || url.startsWith("http://", ignoreCase = true)

        const val FALLBACK_UA =
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"

        fun host(url: String) = runCatching { url.toHttpUrl().host }.getOrDefault(url)

        fun ursprung(url: String) = runCatching { url.toHttpUrl().let { "${it.scheme}://${it.host}" } }.getOrDefault(url)
    }
}
