package de.tobidervogel.aniworld.download

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import de.tobidervogel.aniworld.R
import de.tobidervogel.aniworld.tr
import java.io.File
import java.io.IOException
import java.nio.ByteBuffer

/**
 * Packt die zusammengesetzten HLS-Segmente (MPEG-TS) ohne Neukodierung in eine MP4 um.
 * Statt FFmpeg (wie im Original) die Bordmittel MediaExtractor und MediaMuxer: Die lesen TS
 * mit H.264/H.265 und AAC, wie es VOE, Filemoon und Vidmoly liefern.
 */
object Umpacker {

    private class Quelle(val ex: MediaExtractor) {
        val ziel = HashMap<Int, Int>() // Spur im Extraktor -> Spur im Muxer
        var fertig = false
    }

    /**
     * @param video Datei mit Bild (und meist auch Ton)
     * @param ton   eigene Tondatei, falls die Playlist den Ton getrennt führt
     */
    fun nachMp4(video: File, ton: File?, ziel: File, stopp: () -> Boolean = { false }) {
        val quellen = ArrayList<Quelle>()
        var muxer: MediaMuxer? = null
        var gestartet = false
        try {
            val v = Quelle(MediaExtractor().apply { setDataSource(video.path) })
            quellen += v
            val t = ton?.let { Quelle(MediaExtractor().apply { setDataSource(it.path) }) }?.also { quellen += it }

            val m = MediaMuxer(ziel.path, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            muxer = m
            var hatBild = false
            var hatTon = false
            var puffer = 2 * 1024 * 1024
            fun spuren(q: Quelle, bild: Boolean, tonErlaubt: Boolean) {
                for (i in 0 until q.ex.trackCount) {
                    val f = q.ex.getTrackFormat(i)
                    val mime = f.getString(MediaFormat.KEY_MIME).orEmpty()
                    val passt = (bild && mime.startsWith("video/") && !hatBild) ||
                        (tonErlaubt && mime.startsWith("audio/") && !hatTon)
                    if (!passt) continue
                    // ID3- oder Untertitelspuren aus dem TS kann der MP4-Muxer nicht; die bleiben draußen.
                    q.ziel[i] = m.addTrack(f)
                    q.ex.selectTrack(i)
                    if (f.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) puffer = maxOf(puffer, f.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE))
                    if (mime.startsWith("video/")) hatBild = true else hatTon = true
                }
            }
            spuren(v, bild = true, tonErlaubt = t == null)
            if (t != null) spuren(t, bild = false, tonErlaubt = true)
            if (!hatBild) throw IOException(tr(R.string.e_keine_bildspur))

            // Zeitstempel auf 0 schieben: TS beginnt oft bei mehreren Sekunden.
            val start = quellen.mapNotNull { q -> q.ex.sampleTime.takeIf { it >= 0 } }.minOrNull() ?: 0L

            m.start()
            gestartet = true
            val buf = ByteBuffer.allocateDirect(puffer)
            val info = MediaCodec.BufferInfo()
            var zaehler = 0
            while (true) {
                // Immer die Quelle mit dem frühesten Zeitstempel zuerst: So bleiben Bild und Ton verschränkt.
                val q = quellen.filter { !it.fertig }.minByOrNull { it.ex.sampleTime } ?: break
                val spur = q.ex.sampleTrackIndex
                if (spur < 0) { q.fertig = true; continue }
                val ziel = q.ziel[spur]
                if (ziel == null) { q.ex.advance(); continue }
                buf.clear()
                val groesse = q.ex.readSampleData(buf, 0)
                if (groesse < 0) { q.fertig = true; continue }
                val flags = if (q.ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0
                info.set(0, groesse, maxOf(0L, q.ex.sampleTime - start), flags)
                m.writeSampleData(ziel, buf, info)
                q.ex.advance()
                if (++zaehler % 500 == 0 && stopp()) throw IOException(tr(R.string.e_abgebrochen))
            }
        } finally {
            quellen.forEach { runCatching { it.ex.release() } }
            muxer?.let { mx ->
                if (gestartet) runCatching { mx.stop() }
                runCatching { mx.release() }
            }
        }
    }
}
