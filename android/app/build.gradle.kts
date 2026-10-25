import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "de.tobidervogel.aniworld"
    compileSdk = 34

    defaultConfig {
        applicationId = "de.tobidervogel.aniworld"
        // Android 8 und neuer. Was erst später kam (Weichzeichnen ab 12, „Zugriff auf alle Dateien“
        // ab 11, Benachrichtigungsfrage ab 13), fragt der Code an Ort und Stelle ab.
        minSdk = 26
        // Bewusst 34 und nicht 36: Ab 35 begrenzt Android dataSync-Dienste auf 6 Stunden am Tag,
        // eine lange Staffel würde dann mitten im Download abbrechen.
        targetSdk = 34
        versionCode = 6
        versionName = "0.4.1"
    }

    // Eigener Schlüssel nur, wenn android/keystore.properties da ist (nicht im Repo):
    // storeFile, storePassword, keyAlias, keyPassword. Sonst signiert Gradle mit dem Debug-Schlüssel.
    // Wer Updates drüberinstallieren will, braucht immer denselben Schlüssel.
    val schluessel = rootProject.file("keystore.properties").takeIf { it.isFile }
        ?.let { f -> Properties().apply { f.inputStream().use { load(it) } } }
    if (schluessel != null) {
        signingConfigs.create("eigen") {
            storeFile = rootProject.file(schluessel.getProperty("storeFile"))
            storePassword = schluessel.getProperty("storePassword")
            keyAlias = schluessel.getProperty("keyAlias")
            keyPassword = schluessel.getProperty("keyPassword")
        }
    }

    buildTypes {
        debug {
            if (schluessel != null) signingConfig = signingConfigs.getByName("eigen")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName(if (schluessel != null) "eigen" else "debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
    lint {
        // Der Lint von AGP 8.4.1 rechnet mit Kotlin 2.0 und liest die stdlib von 2.3 falsch,
        // dann gilt jedes remember { liste.count { … } } als "gibt Unit zurück". Wieder an, sobald AGP neuer ist.
        disable += "RememberReturnType"
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    // Höchste Stände, die noch mit compileSdk 34 bauen (die nächsten verlangen 35).
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    // Auto-Sync im Hintergrund; 2.9 ist die letzte Reihe, die noch mit compileSdk 34 baut.
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    // Voller Symbolsatz; ohne R8 landet alles in der APK (rund 10 MB mehr).
    implementation("androidx.compose.material:material-icons-extended")

    // Netz: DoH, weil deutsche Provider aniworld.to per DNS sperren (das Python-Original macht dasselbe).
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:okhttp-dnsoverhttps:4.12.0")
    // HTML lesen: Selektoren statt der find()-Ketten aus dem Python-Code, übersteht kleine Umbauten der Seite.
    implementation("org.jsoup:jsoup:1.18.3")
    // Cover laden, über denselben OkHttp-Client (DoH, Cookies).
    implementation("io.coil-kt:coil-compose:2.7.0")

    // Player für Streams und fertige Downloads.
    implementation("androidx.media3:media3-exoplayer:1.4.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.4.1")
    implementation("androidx.media3:media3-datasource-okhttp:1.4.1")
    implementation("androidx.media3:media3-ui:1.4.1")

    testImplementation("junit:junit:4.13.2")
    // org.json ist auf dem Handy eingebaut, in JVM-Tests aber nur ein Stub.
    testImplementation("org.json:json:20250517")
}
