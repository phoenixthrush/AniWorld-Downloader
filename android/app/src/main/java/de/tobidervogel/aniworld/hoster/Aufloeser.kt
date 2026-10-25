package de.tobidervogel.aniworld.hoster

import de.tobidervogel.aniworld.App
import de.tobidervogel.aniworld.Protokoll
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.site.FolgenLinks
import de.tobidervogel.aniworld.site.Sprache
import de.tobidervogel.aniworld.tr
import kotlinx.coroutines.CancellationException

/**
 * Von der Folge zur abspielbaren Adresse: Hoster in Reihenfolge durchprobieren, wie
 * build_provider_attempt_order() im Original. Die Sprache wechselt dabei nie von selbst.
 */
object Aufloeser {

    /** Gewählter Hoster zuerst, dann die Reihenfolge aus den Einstellungen, dann der Rest der Seite. */
    fun reihenfolge(verfuegbar: List<String>, gewaehlt: String?, einstellung: List<String>): List<String> {
        val liste = LinkedHashSet<String>()
        if (gewaehlt != null && gewaehlt in verfuegbar) liste += gewaehlt
        for (h in einstellung) verfuegbar.firstOrNull { it.equals(h, ignoreCase = true) }?.let { liste += it }
        liste += verfuegbar
        return liste.toList()
    }

    suspend fun stream(
        folgenUrl: String,
        links: FolgenLinks,
        sprache: Sprache,
        gewaehlt: String? = null,
        /** Hoster, deren Stream beim Laden schon gescheitert ist. */
        ausser: Set<String> = emptySet(),
        status: (String) -> Unit = {},
    ): Stream {
        val app = App.self
        val einst = app.einstellungen
        val proSprache = links.links[sprache]
            ?: throw NetzFehler(tr(R.string.sprache_fehlt, tr(sprache.anzeigeRes)))
        val fehler = ArrayList<String>()
        for (name in reihenfolge(proSprache.keys.toList(), gewaehlt, einst.hosterReihenfolge)) {
            if (name in ausser) continue
            val redirect = proSprache[name] ?: continue
            try {
                status(tr(R.string.hoster_oeffnet, name))
                val embed = app.anbieter(folgenUrl).hosterAdresse(redirect, folgenUrl)
                val extraktor = Hosters.fuer(name) ?: Hosters.fuer(embed)
                val direkt = extraktor?.let {
                    try {
                        it.aufloesen(app.netz, embed)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        Protokoll.fehler("$name: Extraktor", e)
                        fehler += "$name: ${e.message}"
                        null
                    }
                }
                // Immer den Namen von der Seite tragen: Daran erkennt der Lader, was er schon versucht hat.
                if (direkt != null) return direkt.copy(hoster = name)
                if (einst.browserWeg) {
                    status(tr(R.string.browser_liest, name))
                    Mitleser.mitlesen(app, app.netz, embed, name, Netz.ursprung(folgenUrl) + "/")?.let { return it }
                    fehler += tr(R.string.browser_kein_video, name)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Protokoll.fehler("$name: Weiterleitung", e)
                fehler += "$name: ${e.message}"
            }
        }
        throw NetzFehler(
            if (fehler.isEmpty()) tr(R.string.kein_hoster_sprache, tr(sprache.anzeigeRes))
            else tr(R.string.kein_hoster_video, fehler.joinToString("; "))
        )
    }
}
