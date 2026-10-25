package de.tobidervogel.aniworld.net

/** Erkennt Schutzseiten (DDoS-Guard, Cloudflare, Captchas) statt echtem Inhalt. */
object Check {
    // Teilmenge von is_captcha_page() aus playwright/captcha.py, plus DDoS-Guard (davor sitzt aniworld.to).
    private val MARKER = listOf(
        // Nur Merkmale der Prüfseite selbst; check.ddos-guard.net kann auch auf normalen Seiten eingebunden sein.
        "ddos-guard/js-challenge",
        "<title>ddos-guard</title>",
        "just a moment",
        "checking your browser",
        "enable javascript and cookies",
        "attention required",
        "cf-turnstile",
        "cf_chl_",
        "challenge-running",
        "cdn-cgi/challenge-platform",
        "challenges.cloudflare.com",
        "jschl-answer",
    )

    fun istSchutzseite(html: String): Boolean {
        // Nur den Kopf prüfen: Normale Seiten können solche Wörter weiter unten in Skripten haben.
        val kopf = html.take(6000).lowercase()
        return MARKER.any { it in kopf }
    }

    fun istCheck(a: Antwort): Boolean =
        istSchutzseite(a.text) || (a.code in setOf(403, 429, 503) && a.text.length < 20_000)
}
