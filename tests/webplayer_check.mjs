/* Verifies the browser remuxer (web/static/mkv-remux.js) against ffmpeg.
 *
 * Manual, like tests/provider_check.py: CI has no Node and no media files,
 * and the point of this check is exactly the thing a unit test cannot do,
 * namely hand a real decoder what the browser would receive and see whether
 * it plays. Run it whenever mkv-remux.js changes:
 *
 *   node tests/webplayer_check.mjs "/path/to/Some Episode.mkv" /tmp/out
 *
 * It remuxes the first minute of the file and another minute starting from a
 * seek into the middle, writes init.mp4, start.mp4 and seek.mp4, and then
 * asserts, through ffmpeg and ffprobe:
 *   - the output decodes with no errors at all
 *   - it holds about as many video frames as a minute of that file should
 *   - audio survived, with the sample entry the codec calls for
 *   - the seek lands on a keyframe within three seconds of what was asked
 *   - decode timestamps rise and never overtake presentation timestamps
 *   - peak RSS stays far below the size of the file, i.e. nothing buffered
 *     the whole thing
 * Exit code is 1 if any check fails, so it can gate a commit.
 */

import { createRequire } from "node:module";
import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const CANDIDATES = [
  path.join(here, "mkv-remux.js"),
  path.join(here, "..", "src", "aniworld", "web", "static", "mkv-remux.js"),
];

const SECONDS = 60;
const SEEK_TOLERANCE = 3;
const RSS_LIMIT_MB = 400;

function loadRemuxer() {
  for (const candidate of CANDIDATES) {
    try {
      return require(candidate);
    } catch (error) {
      if (error.code !== "MODULE_NOT_FOUND") throw error;
    }
  }
  throw new Error(`mkv-remux.js not found, looked in:\n  ${CANDIDATES.join("\n  ")}`);
}

/* The browser reads through HTTP Range requests; this is the same contract
   backed by a file handle, so the demuxer is exercised the way it will run. */
async function fileSource(file) {
  const handle = await fs.open(file, "r");
  const stat = await handle.stat();
  return {
    size: stat.size,
    async read(offset, length) {
      const buffer = Buffer.allocUnsafe(Math.max(0, length));
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, offset);
      return new Uint8Array(buffer.buffer, buffer.byteOffset, bytesRead);
    },
    close: () => handle.close(),
  };
}

async function ffprobe(args) {
  const { stdout } = await run("ffprobe", ["-v", "error", ...args], {
    maxBuffer: 64 * 1024 * 1024,
  });
  return stdout;
}

async function probeJson(args) {
  return JSON.parse(await ffprobe([...args, "-of", "json"]));
}

async function decodeErrors(file) {
  try {
    const { stderr } = await run("ffmpeg", ["-v", "error", "-i", file, "-f", "null", "-"], {
      maxBuffer: 64 * 1024 * 1024,
    });
    return stderr.trim();
  } catch (error) {
    return (error.stderr || String(error)).trim();
  }
}

function fps(rate) {
  if (!rate) return 0;
  const [num, den] = String(rate).split("/").map(Number);
  return den ? num / den : num;
}

/* Remux `seconds` of the file starting at `startAt`, exactly the way
   webplayer.js drives the demuxer: skip leading non-keyframe video after a
   seek, keep the audio, hand every sample to the fragmenter. */
async function remux(MkvRemux, demux, selection, startAt, seconds) {
  const fragmenter = new MkvRemux.Fragmenter(demux, {
    video: selection.video,
    audio: selection.audio,
    targetDuration: 4,
  });
  const chunks = [];
  let started = selection.video == null;
  let first = null;
  let firstVideoPts = null;

  for await (const sample of demux.samples(startAt)) {
    if (sample.trackNumber !== selection.video && sample.trackNumber !== selection.audio) continue;
    if (sample.trackNumber === selection.video) {
      if (!started) {
        if (!sample.keyframe) continue;
        started = true;
      }
      if (firstVideoPts === null) firstVideoPts = sample.pts;
    }
    if (!started) continue;
    if (first === null) first = sample.pts;
    if (sample.pts - first > seconds) break;
    const fragment = fragmenter.push(sample);
    if (fragment) chunks.push(fragment);
  }
  const rest = fragmenter.flush();
  if (rest) chunks.push(rest);
  return { chunks, firstVideoPts };
}

/* How far apart the file indexes its clusters, which is how far before a
   requested time playback can legitimately start. */
function cueSpacing(demux) {
  if (demux.cues.length < 2) return demux.duration && demux.cues.length ? demux.duration : 10;
  const gaps = [];
  for (let i = 1; i < demux.cues.length; i += 1) {
    const gap = demux.cues[i].time - demux.cues[i - 1].time;
    if (gap > 0) gaps.push(gap);
  }
  if (!gaps.length) return 10;
  gaps.sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)];
}

function report(results) {
  let failed = 0;
  for (const [ok, text] of results) {
    if (!ok) failed += 1;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${text}`);
  }
  return failed;
}

async function main() {
  const [file, outDirArg] = process.argv.slice(2);
  if (!file) {
    console.error("usage: node tests/webplayer_check.mjs <file.mkv> [outdir]");
    process.exit(2);
  }
  const outDir = outDirArg || path.join(path.dirname(file), "remux-check");
  await fs.mkdir(outDir, { recursive: true });

  const MkvRemux = loadRemuxer();
  const source = await fileSource(file);
  const results = [];

  const sourceInfo = await probeJson([
    "-show_entries",
    "format=duration:stream=codec_type,codec_name,r_frame_rate,nb_frames",
    "-i",
    file,
  ]);
  let sourceDuration = Number(sourceInfo.format.duration) || 0;
  const sourceVideo = (sourceInfo.streams || []).find((s) => s.codec_type === "video");
  const sourceAudio = (sourceInfo.streams || []).find((s) => s.codec_type === "audio");
  const rate = fps(sourceVideo && sourceVideo.r_frame_rate) || 25;

  // A file muxed live states no duration, so count its frames instead. Only
  // ever reached for such a file, where counting is cheap.
  if (!sourceDuration && sourceVideo) {
    const counted = await probeJson([
      "-select_streams",
      "v:0",
      "-count_frames",
      "-show_entries",
      "stream=nb_read_frames",
      "-i",
      file,
    ]);
    const frames = Number(((counted.streams || [])[0] || {}).nb_read_frames) || 0;
    if (frames) sourceDuration = frames / rate;
  }

  const demux = await MkvRemux.open(source, { readAhead: 1 << 20 });
  const video = demux.tracks.find((t) => t.type === "video" && t.mp4) || null;
  const audio =
    demux.tracks.find((t) => t.type === "audio" && t.mp4 && t.isDefault) ||
    demux.tracks.find((t) => t.type === "audio" && t.mp4) ||
    null;
  const selection = { video: video ? video.number : null, audio: audio ? audio.number : null };

  console.log(`\n${path.basename(file)}`);
  console.log(
    `  source   ${sourceDuration.toFixed(1)}s, ${sourceVideo ? sourceVideo.codec_name : "-"}/${
      sourceAudio ? sourceAudio.codec_name : "-"
    } @ ${rate.toFixed(3)} fps`
  );
  console.log(
    `  remuxer  duration ${demux.duration.toFixed(1)}s, ${demux.tracks.length} tracks, ${
      demux.cues.length
    } cues, reorder depth ${demux.reorderDepth}`
  );
  console.log(`  codecs   ${MkvRemux.mimeType(video, audio)}`);

  results.push([Boolean(video || audio), "a playable track was found"]);
  results.push([
    !sourceAudio || Boolean(audio),
    `the source's ${sourceAudio ? sourceAudio.codec_name : "audio"} track mapped to a sample entry`,
  ]);

  const init = demux.initSegment(selection);
  const initPath = path.join(outDir, "init.mp4");
  await fs.writeFile(initPath, init);

  // ---- from the start
  const startRun = await remux(MkvRemux, demux, selection, 0, SECONDS);
  const readAfterStart = demux.reader.bytesRead;
  const startPath = path.join(outDir, "start.mp4");
  await fs.writeFile(startPath, Buffer.concat([init, ...startRun.chunks].map(Buffer.from)));

  // ---- from a seek into the middle
  const seekTarget = sourceDuration > 2 * SECONDS ? Math.floor(sourceDuration / 2) : 0;
  const seekRun = await remux(MkvRemux, demux, selection, seekTarget, SECONDS);
  const seekBytes = demux.reader.bytesRead - readAfterStart;
  const seekPath = path.join(outDir, "seek.mp4");
  await fs.writeFile(seekPath, Buffer.concat([init, ...seekRun.chunks].map(Buffer.from)));

  const rssMb = process.memoryUsage().rss / 1024 / 1024;

  for (const [label, target] of [
    ["start.mp4", startPath],
    ["seek.mp4", seekPath],
  ]) {
    const errors = await decodeErrors(target);
    results.push([errors === "", `${label} decodes without errors${errors ? `: ${errors.split("\n")[0]}` : ""}`]);

    if (video) {
      const info = await probeJson([
        "-select_streams",
        "v:0",
        "-count_frames",
        "-show_entries",
        "stream=nb_read_frames,codec_name,codec_tag_string,width,height",
        "-i",
        target,
      ]);
      const stream = (info.streams || [])[0];
      const frames = stream ? Number(stream.nb_read_frames) : 0;
      const expected = Math.round(rate * Math.min(SECONDS, Math.max(1, sourceDuration - (label === "seek.mp4" ? seekTarget : 0))));
      const slack = Math.max(3, expected * 0.05);
      results.push([
        Math.abs(frames - expected) <= slack,
        `${label} has ${frames} video frames (about ${expected} expected)`,
      ]);
      results.push([
        Boolean(stream) && stream.width === video.width && stream.height === video.height,
        `${label} keeps ${video.width}x${video.height} as ${stream ? stream.codec_name : "?"}/${
          stream ? stream.codec_tag_string : "?"
        }`,
      ]);
    }

    if (audio) {
      const info = await probeJson([
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,codec_tag_string,sample_rate,channels",
        "-i",
        target,
      ]);
      const stream = (info.streams || [])[0];
      results.push([
        Boolean(stream) && Number(stream.sample_rate) === audio.sampleRate,
        `${label} keeps audio as ${stream ? stream.codec_name : "none"}/${
          stream ? stream.codec_tag_string : "-"
        } at ${stream ? stream.sample_rate : "?"} Hz`,
      ]);
    }

    // Timestamps: dts strictly rising, presentation never before decode.
    const packets = await probeJson(["-show_entries", "packet=stream_index,pts_time,dts_time,flags", "-i", target]);
    const perStream = new Map();
    let monotonic = true;
    let ordered = true;
    for (const packet of packets.packets || []) {
      const dts = Number(packet.dts_time);
      const pts = Number(packet.pts_time);
      const last = perStream.get(packet.stream_index);
      if (Number.isFinite(dts)) {
        if (last != null && dts <= last) monotonic = false;
        perStream.set(packet.stream_index, dts);
        if (Number.isFinite(pts) && pts + 1e-6 < dts) ordered = false;
      }
    }
    results.push([monotonic, `${label} decode timestamps rise strictly`]);
    results.push([ordered, `${label} presentation never precedes decode`]);
  }

  if (video && seekTarget > 0) {
    const packets = await probeJson([
      "-select_streams",
      "v:0",
      "-show_entries",
      "packet=pts_time,dts_time,flags",
      "-i",
      seekPath,
    ]);
    const first = (packets.packets || [])[0];
    const firstPts = first ? Number(first.pts_time) : NaN;
    results.push([Boolean(first) && String(first.flags).includes("K"), "seek.mp4 starts on a keyframe"]);
    // Playback has to start at or before the requested time, never after, or
    // the viewer silently loses content. How far before is set by the file:
    // the demuxer starts at the last indexed cluster at or before the
    // request, so the gap is one cue interval, and the player seeks the
    // media element the rest of the way inside what it just buffered.
    const spacing = cueSpacing(demux);
    const allowed = Math.max(SEEK_TOLERANCE, spacing * 1.5);
    results.push([
      Number.isFinite(firstPts) && firstPts <= seekTarget + 0.5 && seekTarget - firstPts <= allowed,
      `seek.mp4 starts at ${Number.isFinite(firstPts) ? firstPts.toFixed(2) : "?"}s for a ${seekTarget}s request (cues every ${spacing.toFixed(1)}s)`,
    ]);
  }

  results.push([
    rssMb < RSS_LIMIT_MB,
    `peak RSS ${rssMb.toFixed(0)} MB for a ${(source.size / 1024 / 1024).toFixed(0)} MB file`,
  ]);
  // A seek must not drag the whole file through the reader. Only worth
  // asserting on a file big enough for the difference to mean anything; a
  // 2 MB fixture is smaller than a couple of read-ahead windows.
  if (source.size > 64 * 1024 * 1024) {
    results.push([
      seekBytes < source.size / 4,
      `seeking to ${seekTarget}s read ${(seekBytes / 1024 / 1024).toFixed(0)} MB of ${(
        source.size /
        1024 /
        1024
      ).toFixed(0)} MB`,
    ]);
  } else {
    console.log(
      `  (read ${(demux.reader.bytesRead / 1024 / 1024).toFixed(1)} MB across three passes of a ${(
        source.size /
        1024 /
        1024
      ).toFixed(1)} MB fixture)`
    );
  }

  const failed = report(results);
  await source.close();
  console.log(`  ${failed ? `FAILED (${failed})` : "OK"}  ${outDir}`);
  process.exit(failed ? 1 : 0);
}

main().catch((error) => {
  console.error(`  FAIL  ${error && error.stack ? error.stack : error}`);
  process.exit(1);
});
