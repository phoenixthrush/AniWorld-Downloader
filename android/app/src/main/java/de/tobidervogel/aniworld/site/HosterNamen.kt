package de.tobidervogel.aniworld.site

import java.net.URI

/**
 * Hostername aus einer Einbettungsadresse, für Seiten, die nur „Mirror 1“ oder gar keinen
 * Namen nennen (MegaKino, Moflix). Wie _ALIASES in models/common/provider_map.py; Unbekannte
 * heißen nach ihrer Domain, damit der Browser-Weg sie trotzdem versuchen kann.
 */
object HosterNamen {
    private val BEKANNT = listOf(
        "voe" to "VOE",
        "gupload" to "Gupload",
        "dood" to "Doodstream",
        "vidmoly" to "Vidmoly",
        "vidoza" to "Vidoza",
        "vidara" to "Vidara",
        "filemoon" to "Filemoon",
        "moflix-stream.click" to "MoflixClick",
        "gxplayer" to "GXPlayer",
    )

    fun ausAdresse(url: String): String? {
        val host = runCatching { URI(url.trim()).host }.getOrNull()?.lowercase()?.removePrefix("www.") ?: return null
        BEKANNT.firstOrNull { it.first in host }?.let { return it.second }
        val teile = host.split('.').filter { it.isNotEmpty() }
        val kern = if (teile.size >= 2) teile[teile.size - 2] else teile.firstOrNull() ?: return null
        return kern.replaceFirstChar { it.uppercase() }
    }
}
