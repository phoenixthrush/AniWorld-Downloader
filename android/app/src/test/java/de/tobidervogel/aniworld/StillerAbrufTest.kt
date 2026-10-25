package de.tobidervogel.aniworld

import de.tobidervogel.aniworld.net.BrowserCheck
import de.tobidervogel.aniworld.net.StillerAbruf
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.Assert.assertNull
import org.junit.Test

class StillerAbrufTest {
    /** Im Hintergrund (Auto-Sync) darf eine Prüfseite nicht auf das Browserfenster warten. */
    @Test
    fun ohneBrowserfenster() = runBlocking {
        withContext(StillerAbruf) { assertNull(BrowserCheck.loesen("https://aniworld.to/")) }
    }
}
