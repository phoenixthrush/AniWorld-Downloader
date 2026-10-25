package de.tobidervogel.aniworld.site

import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.net.Netz
import de.tobidervogel.aniworld.net.NetzFehler
import de.tobidervogel.aniworld.tr

/** Startseite einer Quelle: Reihen (Titel als String-Ressource) und die Genres. */
data class Startseite(val reihen: List<Pair<Int, List<Karte>>>, val genres: List<Genre>)

/**
 * Eine Seite, von der die App Serien holt (AniWorld, SerienStream). Beide sind gleich aufgebaut:
 * Serie → Staffeln → Folgen → Hoster-Links pro Sprache → Weiterleitung zum Hoster.
 */
interface Anbieter {
    val name: String
    /** Hosts, die zu dieser Seite gehören (Spiegel eingeschlossen). */
    val hosts: Set<String>

    fun passt(url: String): Boolean = Netz.host(url).removePrefix("www.") in hosts
    /** Serien-Adresse aus einer beliebigen Adresse der Seite (Staffel, Folge, geteilter Link). */
    fun serienUrl(url: String): String?

    suspend fun startseite(): Startseite
    suspend fun neueFolgen(): List<NeueFolge> = emptyList()
    /** Adresse einer zufälligen Serie; null, wenn die Seite das nicht anbietet. */
    suspend fun zufall(): String? = null
    val hatZufall: Boolean get() = false
    suspend fun suche(text: String): List<Treffer>
    suspend fun genre(slug: String, seite: Int): Pair<List<Karte>, Boolean>
    suspend fun serie(url: String, neu: Boolean = false): Serie
    suspend fun staffel(ref: StaffelRef, neu: Boolean = false): List<Folge>
    suspend fun links(folgenUrl: String): FolgenLinks
    suspend fun hosterAdresse(redirect: String, folgenUrl: String): String
}

/**
 * Weiterleitung zum Hoster per HTTP. Bleibt die Antwort auf der Seite (Captcha oder
 * DDoS-Guard vor dem Hoster), öffnet sich das Browserfenster und der Nutzer klickt sich durch.
 */
suspend fun weiterleiten(netz: Netz, redirect: String, folgenUrl: String, heim: Set<String>): String {
    fun daheim(u: String) = Netz.host(u).removePrefix("www.") in heim
    val a = netz.anfrage(redirect, mapOf("Referer" to folgenUrl))
    // Was der Hoster selbst antwortet, ist hier egal; das prüft danach der Extraktor.
    if (!daheim(a.url)) return a.url
    val ende = BrowserCheck.loesen(redirect, verlassen = true, heim = heim)
    if (ende != null && !daheim(ende)) return ende
    throw NetzFehler(tr(R.string.e_weiterleitung, a.code))
}
