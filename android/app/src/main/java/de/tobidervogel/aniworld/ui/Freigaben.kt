package de.tobidervogel.aniworld.ui

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat

/**
 * Berechtigungen und Systemeinstellungen, die Einrichtung und Einstellungen gemeinsam nutzen.
 * Nicht jedes Gerät hat jede Einstellungsseite (Android Go, manche Hersteller); dann geht es
 * eine Stufe allgemeiner weiter, notfalls auf die App-Info.
 */
object Freigaben {
    fun benachrichtigungen(ctx: Context) = NotificationManagerCompat.from(ctx).areNotificationsEnabled()

    /** Benachrichtigungs-Einstellungen der App: dorthin, wenn der Dialog nach einer Ablehnung nicht mehr kommt. */
    fun benachrichtigungenOeffnen(ctx: Context) = oeffnen(
        ctx,
        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, ctx.packageName),
    )

    fun akkuFrei(ctx: Context) = ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)

    // Die direkte Frage nach der Ausnahme ist für Download-Apps ausdrücklich erlaubt.
    @SuppressLint("BatteryLife")
    fun akkuFreigeben(ctx: Context) = oeffnen(
        ctx,
        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}")),
        Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS),
    )

    /** Systemeinstellungen der App, falls eine Freigabe dort von Hand gesetzt werden muss. */
    fun appInfo(ctx: Context) = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${ctx.packageName}"))

    /** Öffnet das erste Ziel, das es auf dem Gerät gibt. */
    fun oeffnen(ctx: Context, vararg ziele: Intent) {
        for (i in ziele.toList() + appInfo(ctx)) {
            try {
                ctx.startActivity(i)
                return
            } catch (_: ActivityNotFoundException) {
            } catch (_: SecurityException) {
            }
        }
    }
}
