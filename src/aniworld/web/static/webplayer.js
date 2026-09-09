/* In-browser playback of downloaded episodes.
 *
 * The server only ever serves the file bytes (with Range support). Whatever
 * the browser cannot play as-is is fixed on the viewer's machine:
 *
 *   native     .mp4/.webm -> <video src>, nothing to do
 *   remux      .mkv with codecs the browser already decodes (nearly every
 *              download: H.264 + AAC) -> demuxed by mkv-remux.js and fed to
 *              Media Source Extensions as fragmented MP4. No decoding, no
 *              re-encoding, a few MB of buffer.
 *   transcode  a codec MSE refuses (HEVC on most Linux/Windows Chromes, AV1
 *              on older machines, AC-3 audio) -> decoded and re-encoded with
 *              WebCodecs, hardware-accelerated where the viewer's GPU allows,
 *              then packaged for MSE like the remux path. The server-side
 *              hardware encoding from #301 covers downloads; this is the same
 *              idea for playback, on the client's GPU instead of the server's.
 *
 * The same pipeline renders the episode thumbnails: captureFrame() seeks a
 * hidden video to a random point and draws it to a canvas.
 */

(function () {
  const NATIVE_EXTENSIONS = new Set(["mp4", "m4v", "mov", "webm"]);
  const AHEAD_SECONDS = 60; // how far past the playhead to keep buffering
  const BEHIND_SECONDS = 40; // how much to keep behind it before evicting
  const CHUNK = 2 * 1024 * 1024;

  const MediaSourceImpl = window.ManagedMediaSource || window.MediaSource || null;

  function extensionOf(name) {
    const clean = String(name || "").split("?")[0];
    const dot = clean.lastIndexOf(".");
    return dot >= 0 ? clean.slice(dot + 1).toLowerCase() : "";
  }

  function typeSupported(mime) {
    try {
      return Boolean(MediaSourceImpl && MediaSourceImpl.isTypeSupported(mime));
    } catch (error) {
      return false;
    }
  }

  function formatTime(seconds) {
    const total = Math.max(0, Math.floor(seconds || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const mm = h ? String(m).padStart(2, "0") : String(m);
    return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
  }

  /* ===== Byte source over HTTP Range =====
     Reads go straight to the file endpoint. A small read-ahead cache keeps
     the demuxer from issuing one request per EBML element. */
  class RangeSource {
    constructor(url) {
      this.url = url;
      this.size = 0;
      this.cache = null; // { offset, data }
    }

    async init() {
      const response = await fetch(this.url, { headers: { Range: "bytes=0-0" } });
      if (!response.ok && response.status !== 206) {
        throw new Error(`HTTP ${response.status}`);
      }
      const range = response.headers.get("Content-Range");
      const match = range && /\/(\d+)$/.exec(range);
      if (match) {
        this.size = Number(match[1]);
      } else {
        const length = Number(response.headers.get("Content-Length") || 0);
        this.size = length;
      }
      await response.arrayBuffer();
      return this;
    }

    async read(offset, length) {
      if (offset >= this.size) return new Uint8Array(0);
      const end = Math.min(this.size, offset + length);
      const cached = this.cache;
      if (cached && offset >= cached.offset && end <= cached.offset + cached.data.length) {
        return cached.data.subarray(offset - cached.offset, end - cached.offset);
      }
      const fetchEnd = Math.min(this.size, offset + Math.max(length, CHUNK));
      const response = await fetch(this.url, {
        headers: { Range: `bytes=${offset}-${fetchEnd - 1}` }
      });
      if (!(response.status === 206 || response.status === 200)) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = new Uint8Array(await response.arrayBuffer());
      this.cache = { offset, data };
      return data.subarray(0, end - offset);
    }
  }

  /* The transcoded path needs its own init segment and fragments, because
     the encoder's avcC describes the newly encoded stream rather than the
     file's. The box writer itself is the remuxer's, so there is one
     implementation of the MP4 boxes and one set of ffprobe checks over it
     (tests/webplayer_check.mjs). */
  const Mp4 = (window.MkvRemux && window.MkvRemux.Mp4) || null;

  /* ===== Transcoders (WebCodecs) =====
     Each takes demuxed samples in, hands fragments out. They are stateful
     across seeks only through reset(). */
  function avcLevelFor(width, height, fps) {
    const mbs = Math.ceil(width / 16) * Math.ceil(height / 16);
    const rate = mbs * (fps || 30);
    if (rate <= 245760 && mbs <= 8192) return "avc1.640028"; // 4.0: 1080p30
    if (rate <= 589824 && mbs <= 22080) return "avc1.640032"; // 5.0: 1440p / 1080p60
    return "avc1.640033"; // 5.1: 2160p30
  }

  class VideoTranscoder {
    constructor(track, trackId, onFragment, onStatus) {
      this.track = track;
      this.trackId = trackId;
      this.onFragment = onFragment;
      this.onStatus = onStatus;
      this.timescale = 90000;
      this.fps = track.defaultDuration ? 1e9 / track.defaultDuration : 24;
      this.decoder = null;
      this.encoder = null;
      this.pending = [];
      this.sequence = 1;
      this.initSent = false;
      this.description = null;
      this.frames = 0;
      this.error = null;
      this.lastDts = -1;
    }

    static async supported(track) {
      if (!window.VideoDecoder || !window.VideoEncoder || !track.codec) return false;
      try {
        const decode = await VideoDecoder.isConfigSupported({
          codec: track.codec,
          description: track.mp4 === "vp09" ? undefined : track.codecPrivate || undefined,
          codedWidth: track.width,
          codedHeight: track.height
        });
        const encode = await VideoEncoder.isConfigSupported({
          codec: avcLevelFor(track.width, track.height, 30),
          width: track.width,
          height: track.height,
          avc: { format: "avc" },
          hardwareAcceleration: "prefer-hardware"
        });
        return Boolean(decode.supported && encode.supported);
      } catch (error) {
        return false;
      }
    }

    async start() {
      const track = this.track;
      const bitrate = Math.round(track.width * track.height * this.fps * 0.08);
      this.encoder = new VideoEncoder({
        output: (chunk, meta) => this.onChunk(chunk, meta),
        error: (error) => {
          this.error = error;
        }
      });
      const encodeConfig = {
        codec: avcLevelFor(track.width, track.height, this.fps),
        width: track.width,
        height: track.height,
        bitrate: Math.min(bitrate, 25e6),
        framerate: this.fps,
        avc: { format: "avc" },
        latencyMode: "quality",
        hardwareAcceleration: "prefer-hardware"
      };
      const support = await VideoEncoder.isConfigSupported(encodeConfig);
      if (!support.supported) {
        encodeConfig.hardwareAcceleration = "no-preference";
      }
      this.encoder.configure(encodeConfig);
      this.decoder = new VideoDecoder({
        output: (frame) => this.onFrame(frame),
        error: (error) => {
          this.error = error;
        }
      });
      const decodeConfig = {
        codec: track.codec,
        codedWidth: track.width,
        codedHeight: track.height,
        hardwareAcceleration: "prefer-hardware"
      };
      if (track.codecPrivate && track.mp4 !== "vp09") decodeConfig.description = track.codecPrivate;
      this.decoder.configure(decodeConfig);
    }

    onFrame(frame) {
      if (this.encoder && this.encoder.state === "configured") {
        // a keyframe every ~4 s keeps seeks and fragment boundaries cheap
        const key = this.frames % Math.max(1, Math.round(this.fps * 4)) === 0;
        this.encoder.encode(frame, { keyFrame: key });
        this.frames += 1;
      }
      frame.close();
    }

    onChunk(chunk, meta) {
      if (meta && meta.decoderConfig && meta.decoderConfig.description && !this.initSent) {
        this.description = new Uint8Array(meta.decoderConfig.description);
        this.initSent = true;
        this.onFragment(
          Mp4.init([
            {
              id: this.trackId,
              type: "video",
              mp4: "avc1",
              codecPrivate: this.description,
              width: this.track.width,
              height: this.track.height,
              timescale: this.timescale
            }
          ]),
          "init"
        );
      }
      const data = new Uint8Array(chunk.byteLength);
      chunk.copyTo(data);
      const pts = Math.round((chunk.timestamp / 1e6) * this.timescale);
      const duration = Math.round(((chunk.duration || 1e6 / this.fps) / 1e6) * this.timescale);
      this.pending.push({ pts, duration, keyframe: chunk.type === "key", data });
      // Encoders emit in decode order with monotonic timestamps only when
      // B-frames are off (the default for WebCodecs H.264), so dts = pts.
      if (this.pending.length >= Math.round(this.fps * 2) || chunk.type === "key" && this.pending.length > 1) {
        this.flushFragment();
      }
    }

    flushFragment() {
      if (!this.pending.length || !this.initSent) return;
      const samples = this.pending.splice(0, this.pending.length).map((s) => {
        const dts = Math.max(s.pts, this.lastDts + 1);
        this.lastDts = dts;
        return { dts, pts: s.pts, duration: s.duration, keyframe: s.keyframe, data: s.data };
      });
      // start a fragment on a keyframe so MSE can drop the rest cleanly
      this.onFragment(
        Mp4.fragment(this.sequence++, [{ id: this.trackId, samples }]),
        "media"
      );
    }

    async push(sample) {
      if (this.error) throw this.error;
      while (this.decoder.decodeQueueSize > 8 || this.encoder.encodeQueueSize > 8) {
        await new Promise((r) => setTimeout(r, 10));
        if (this.error) throw this.error;
      }
      this.decoder.decode(
        new EncodedVideoChunk({
          type: sample.keyframe ? "key" : "delta",
          timestamp: Math.round(sample.pts * 1e6),
          duration: sample.duration ? Math.round(sample.duration * 1e6) : undefined,
          data: sample.data
        })
      );
    }

    async finish() {
      try {
        await this.decoder.flush();
        await this.encoder.flush();
      } catch (error) {
        /* a flush after an error has nothing to give */
      }
      this.flushFragment();
    }

    async reset() {
      try {
        if (this.decoder && this.decoder.state !== "closed") await this.decoder.flush();
        if (this.encoder && this.encoder.state !== "closed") await this.encoder.flush();
      } catch (error) {
        /* flushing a closed codec is fine to fail */
      }
      this.pending = [];
      this.frames = 0;
      this.lastDts = -1;
      if (this.decoder && this.decoder.state !== "closed") this.decoder.reset();
      if (this.encoder && this.encoder.state !== "closed") this.encoder.reset();
      await this.start();
    }

    close() {
      try {
        if (this.decoder) this.decoder.close();
        if (this.encoder) this.encoder.close();
      } catch (error) {
        /* already closed */
      }
    }
  }

  class AudioTranscoder {
    constructor(track, trackId, onFragment) {
      this.track = track;
      this.trackId = trackId;
      this.onFragment = onFragment;
      this.sampleRate = track.sampleRate || 48000;
      this.channels = Math.min(2, track.channels || 2);
      this.outCodec = null; // "mp4a.40.2" or "opus"
      this.decoder = null;
      this.encoder = null;
      this.pending = [];
      this.sequence = 1;
      this.initSent = false;
      this.error = null;
      this.lastDts = -1;
    }

    static async supported(track) {
      if (!window.AudioDecoder || !window.AudioEncoder || !track.codec) return false;
      try {
        const decode = await AudioDecoder.isConfigSupported({
          codec: track.codec,
          sampleRate: track.sampleRate || 48000,
          numberOfChannels: track.channels || 2,
          description: track.codecPrivate || undefined
        });
        if (!decode.supported) return false;
        return Boolean(await AudioTranscoder.pickOutput(track));
      } catch (error) {
        return false;
      }
    }

    static async pickOutput(track) {
      const rate = track.sampleRate || 48000;
      const channels = Math.min(2, track.channels || 2);
      for (const [codec, mime] of [
        ["mp4a.40.2", 'audio/mp4; codecs="mp4a.40.2"'],
        ["opus", 'audio/mp4; codecs="opus"']
      ]) {
        if (!typeSupported(mime)) continue;
        const support = await AudioEncoder.isConfigSupported({
          codec,
          sampleRate: rate,
          numberOfChannels: channels,
          bitrate: 160000
        });
        if (support.supported) return codec;
      }
      return null;
    }

    async start() {
      this.outCodec = await AudioTranscoder.pickOutput(this.track);
      this.encoder = new AudioEncoder({
        output: (chunk, meta) => this.onChunk(chunk, meta),
        error: (error) => {
          this.error = error;
        }
      });
      this.encoder.configure({
        codec: this.outCodec,
        sampleRate: this.sampleRate,
        numberOfChannels: this.channels,
        bitrate: 160000
      });
      this.decoder = new AudioDecoder({
        output: (data) => this.onData(data),
        error: (error) => {
          this.error = error;
        }
      });
      const config = {
        codec: this.track.codec,
        sampleRate: this.track.sampleRate || 48000,
        numberOfChannels: this.track.channels || 2
      };
      if (this.track.codecPrivate) config.description = this.track.codecPrivate;
      this.decoder.configure(config);
    }

    onData(data) {
      if (this.encoder && this.encoder.state === "configured") this.encoder.encode(data);
      data.close();
    }

    onChunk(chunk, meta) {
      if (!this.initSent) {
        const description = meta && meta.decoderConfig && meta.decoderConfig.description;
        // AAC needs its AudioSpecificConfig; Opus is self-describing
        if (this.outCodec === "mp4a.40.2" && !description) return;
        this.initSent = true;
        this.onFragment(
          Mp4.init([
            {
              id: this.trackId,
              type: "audio",
              mp4: this.outCodec === "opus" ? "Opus" : "mp4a",
              asc: description ? new Uint8Array(description) : null,
              codecPrivate: description ? new Uint8Array(description) : null,
              channels: this.channels,
              sampleRate: this.sampleRate,
              timescale: this.sampleRate
            }
          ]),
          "init"
        );
      }
      const data = new Uint8Array(chunk.byteLength);
      chunk.copyTo(data);
      const pts = Math.round((chunk.timestamp / 1e6) * this.sampleRate);
      const duration = Math.round(((chunk.duration || 21333) / 1e6) * this.sampleRate);
      this.pending.push({ pts, duration, keyframe: true, data });
      if (this.pending.length >= 40) this.flushFragment();
    }

    flushFragment() {
      if (!this.pending.length || !this.initSent) return;
      const samples = this.pending.splice(0, this.pending.length).map((s) => {
        const dts = Math.max(s.pts, this.lastDts + 1);
        this.lastDts = dts;
        return { ...s, dts };
      });
      this.onFragment(Mp4.fragment(this.sequence++, [{ id: this.trackId, samples }]), "media");
    }

    async push(sample) {
      if (this.error) throw this.error;
      while (this.decoder.decodeQueueSize > 16 || this.encoder.encodeQueueSize > 16) {
        await new Promise((r) => setTimeout(r, 10));
        if (this.error) throw this.error;
      }
      this.decoder.decode(
        new EncodedAudioChunk({
          type: "key",
          timestamp: Math.round(sample.pts * 1e6),
          duration: sample.duration ? Math.round(sample.duration * 1e6) : undefined,
          data: sample.data
        })
      );
    }

    async finish() {
      try {
        await this.decoder.flush();
        await this.encoder.flush();
      } catch (error) {
        /* nothing left to flush */
      }
      this.flushFragment();
    }

    async reset() {
      try {
        if (this.decoder && this.decoder.state !== "closed") await this.decoder.flush();
        if (this.encoder && this.encoder.state !== "closed") await this.encoder.flush();
      } catch (error) {
        /* fine */
      }
      this.pending = [];
      this.lastDts = -1;
      if (this.decoder && this.decoder.state !== "closed") this.decoder.reset();
      if (this.encoder && this.encoder.state !== "closed") this.encoder.reset();
      await this.start();
    }

    close() {
      try {
        if (this.decoder) this.decoder.close();
        if (this.encoder) this.encoder.close();
      } catch (error) {
        /* already closed */
      }
    }
  }

  /* ===== MSE playback of a Matroska file ===== */
  class MsePlayback {
    constructor(video, url, options) {
      this.video = video;
      this.url = url;
      this.options = options || {};
      this.mediaSource = null;
      this.buffers = {}; // name -> SourceBuffer
      this.queues = {}; // name -> [Uint8Array]
      this.demux = null;
      this.source = null;
      this.videoTrack = null;
      this.audioTrack = null;
      this.subtitleTrack = null;
      this.textTrack = null;
      this.mode = null;
      this.pumpToken = 0;
      this.pumping = false;
      this.destroyed = false;
      this.ended = false;
      this.onSeeking = () => this.handleSeek();
      this.onTimeUpdate = () => this.maybeResume();
      this.waiters = [];
      this.objectUrl = null;
    }

    status(kind, detail) {
      if (this.options.onStatus) this.options.onStatus(kind, detail || {});
    }

    async open() {
      if (!MediaSourceImpl) throw new Error("MediaSource unavailable");
      if (!window.MkvRemux) throw new Error("mkv-remux.js missing");
      this.status("preparing");
      this.source = await new RangeSource(this.url).init();
      this.demux = await MkvRemux.open(this.source);
      const tracks = this.demux.tracks || [];
      this.videoTrack = tracks.find((t) => t.type === "video") || null;
      this.audioTrack =
        tracks.find((t) => t.type === "audio" && t.isDefault) ||
        tracks.find((t) => t.type === "audio") ||
        null;
      this.subtitleTrack =
        tracks.find((t) => t.type === "subtitle" && t.isDefault) ||
        tracks.find((t) => t.type === "subtitle") ||
        null;
      if (!this.videoTrack && !this.audioTrack) throw new Error("no playable tracks");

      await this.plan();
      await this.attachMediaSource();
      return this;
    }

    /* Decide remux vs transcode per track. */
    async plan() {
      const v = this.videoTrack;
      const a = this.audioTrack;
      const videoOk = !v || (v.codec && typeSupported(`video/mp4; codecs="${v.codec}"`));
      const audioOk = !a || (a.codec && typeSupported(`audio/mp4; codecs="${a.codec}"`));
      this.transcodeVideo = false;
      this.transcodeAudio = false;
      if (!videoOk) {
        if (!(await VideoTranscoder.supported(v))) {
          const error = new Error("unsupported");
          error.codec = v.codecId || v.codec || "video";
          throw error;
        }
        this.transcodeVideo = true;
      }
      if (!audioOk) {
        if (await AudioTranscoder.supported(a)) {
          this.transcodeAudio = true;
        } else if (v && videoOk) {
          // video without sound beats nothing; say so
          this.audioTrack = null;
          this.status("no-audio", { codec: a.codecId });
        } else {
          const error = new Error("unsupported");
          error.codec = a.codecId || a.codec || "audio";
          throw error;
        }
      }
      this.mode = this.transcodeVideo || this.transcodeAudio ? "transcode" : "remux";
    }

    async attachMediaSource() {
      const ms = new MediaSourceImpl();
      this.mediaSource = ms;
      if (window.ManagedMediaSource && ms instanceof window.ManagedMediaSource) {
        this.video.disableRemotePlayback = true;
      }
      this.objectUrl = URL.createObjectURL(ms);
      await new Promise((resolve, reject) => {
        ms.addEventListener("sourceopen", resolve, { once: true });
        ms.addEventListener("error", reject, { once: true });
        this.video.src = this.objectUrl;
      });
      if (this.demux.duration) {
        try {
          ms.duration = this.demux.duration;
        } catch (error) {
          /* some browsers refuse until a buffer exists */
        }
      }

      // One SourceBuffer per pipeline: the remuxed tracks share one (they
      // come out of one fragmenter), each transcoded track has its own.
      const remuxed = [];
      if (this.videoTrack && !this.transcodeVideo) remuxed.push(this.videoTrack);
      if (this.audioTrack && !this.transcodeAudio) remuxed.push(this.audioTrack);
      if (remuxed.length) {
        const mime = MkvRemux.mimeType(
          this.videoTrack && !this.transcodeVideo ? this.videoTrack : null,
          this.audioTrack && !this.transcodeAudio ? this.audioTrack : null
        );
        this.addBuffer("remux", mime);
      }
      if (this.transcodeVideo) this.addBuffer("tvideo", 'video/mp4; codecs="avc1.640028"');
      if (this.transcodeAudio) {
        const codec = await AudioTranscoder.pickOutput(this.audioTrack);
        this.addBuffer("taudio", `audio/mp4; codecs="${codec}"`);
      }
      if (this.demux.duration) {
        try {
          ms.duration = this.demux.duration;
        } catch (error) {
          /* ignore */
        }
      }

      if (this.subtitleTrack) this.setupSubtitles();
      this.video.addEventListener("seeking", this.onSeeking);
      this.video.addEventListener("timeupdate", this.onTimeUpdate);
      this.startPump(this.options.startAt || 0);
    }

    addBuffer(name, mime) {
      const sb = this.mediaSource.addSourceBuffer(mime);
      sb.mode = "segments";
      sb.addEventListener("updateend", () => this.drain(name));
      sb.addEventListener("error", () => {
        this.fail(new Error(`SourceBuffer ${name} error`));
      });
      this.buffers[name] = sb;
      this.queues[name] = [];
    }

    enqueue(name, data) {
      if (this.destroyed || !this.buffers[name]) return;
      this.queues[name].push(data);
      this.drain(name);
    }

    drain(name) {
      const sb = this.buffers[name];
      const queue = this.queues[name];
      if (!sb || sb.updating || !queue || !queue.length) {
        if (!sb || !sb.updating) this.wake();
        return;
      }
      if (this.mediaSource.readyState !== "open") return;
      const next = queue[0];
      try {
        sb.appendBuffer(next);
        queue.shift();
      } catch (error) {
        if (error.name === "QuotaExceededError") {
          // buffer full: evict what is well behind the playhead, then retry
          // the same chunk (it is still at the head of the queue)
          this.evict(name).then(() => setTimeout(() => this.drain(name), 50));
          return;
        }
        this.fail(error);
      }
    }

    async evict(name) {
      const sb = this.buffers[name];
      const t = this.video.currentTime;
      if (!sb || sb.updating || t < BEHIND_SECONDS + 5) return;
      try {
        sb.remove(0, t - BEHIND_SECONDS);
        await new Promise((r) => sb.addEventListener("updateend", r, { once: true }));
      } catch (error) {
        /* nothing to remove */
      }
    }

    queuedBytes() {
      return Object.values(this.queues).reduce(
        (n, q) => n + q.reduce((m, b) => m + (b ? b.length : 0), 0),
        0
      );
    }

    bufferedAhead() {
      const t = this.video.currentTime;
      let ahead = Infinity;
      for (const sb of Object.values(this.buffers)) {
        let end = 0;
        try {
          for (let i = 0; i < sb.buffered.length; i += 1) {
            if (sb.buffered.start(i) <= t + 0.5 && sb.buffered.end(i) > end) end = sb.buffered.end(i);
          }
        } catch (error) {
          end = 0;
        }
        ahead = Math.min(ahead, end - t);
      }
      return ahead === Infinity ? 0 : ahead;
    }

    /* The pump waits here while enough is buffered ahead of the playhead. */
    async throttle(token) {
      while (!this.destroyed && token === this.pumpToken) {
        if (this.bufferedAhead() < AHEAD_SECONDS && this.queuedBytes() < 16 * 1024 * 1024) return;
        await new Promise((resolve) => {
          this.waiters.push(resolve);
          setTimeout(resolve, 500);
        });
      }
    }

    wake() {
      const waiters = this.waiters.splice(0, this.waiters.length);
      waiters.forEach((resolve) => resolve());
    }

    maybeResume() {
      this.wake();
      if (this.mode === "remux") this.trimBehind();
    }

    trimBehind() {
      const t = this.video.currentTime;
      if (t < BEHIND_SECONDS * 3) return;
      for (const sb of Object.values(this.buffers)) {
        if (sb.updating) continue;
        try {
          if (sb.buffered.length && sb.buffered.start(0) < t - BEHIND_SECONDS * 2) {
            sb.remove(0, t - BEHIND_SECONDS);
          }
        } catch (error) {
          /* ignore */
        }
      }
    }

    setupSubtitles() {
      const track = this.subtitleTrack;
      const lang = track.language && track.language !== "und" ? track.language : "";
      this.textTrack = this.video.addTextTrack("subtitles", track.name || lang || "Subtitles", lang);
      this.textTrack.mode = "hidden";
      this.isAss = /ASS|SSA/i.test(track.codecId || "");
    }

    addCue(sample) {
      if (!this.textTrack) return;
      let text = new TextDecoder().decode(sample.data);
      if (this.isAss) {
        // "ReadOrder,Layer,Style,Name,MarginL,MarginR,MarginV,Effect,Text"
        const parts = text.split(",");
        text = parts.slice(8).join(",");
        text = text.replace(/\{[^}]*\}/g, "").replace(/\\N/g, "\n").replace(/\\h/g, " ");
      }
      const duration = sample.duration || 3;
      try {
        this.textTrack.addCue(new VTTCue(sample.pts, sample.pts + duration, text.trim()));
      } catch (error) {
        /* overlapping or malformed cue, not worth stopping playback */
      }
    }

    async startPump(startAt) {
      this.pumpToken += 1;
      const token = this.pumpToken;
      this.pumping = true;
      this.ended = false;
      this.status(this.mode === "transcode" ? "transcoding" : "remuxing", {
        codec: this.transcodeVideo ? this.videoTrack.codecId : this.audioTrack && this.audioTrack.codecId
      });

      const fragmenter =
        this.buffers.remux &&
        new MkvRemux.Fragmenter(this.demux, {
          video: this.videoTrack && !this.transcodeVideo ? this.videoTrack.number : null,
          audio: this.audioTrack && !this.transcodeAudio ? this.audioTrack.number : null,
          targetDuration: 4
        });
      if (fragmenter && !this.initDone) {
        this.enqueue(
          "remux",
          this.demux.initSegment({
            video: this.videoTrack && !this.transcodeVideo ? this.videoTrack.number : null,
            audio: this.audioTrack && !this.transcodeAudio ? this.audioTrack.number : null
          })
        );
        this.initDone = true;
      }

      let vt = null;
      let at = null;
      try {
        if (this.transcodeVideo) {
          vt = this.videoTranscoder || new VideoTranscoder(this.videoTrack, 1, (data) => this.enqueue("tvideo", data), (k, d) => this.status(k, d));
          if (this.videoTranscoder) await vt.reset();
          else await vt.start();
          this.videoTranscoder = vt;
        }
        if (this.transcodeAudio) {
          at = this.audioTranscoder || new AudioTranscoder(this.audioTrack, 2, (data) => this.enqueue("taudio", data));
          if (this.audioTranscoder) await at.reset();
          else await at.start();
          this.audioTranscoder = at;
        }

        let firstVideoKey = !this.videoTrack;
        for await (const sample of this.demux.samples(startAt)) {
          if (this.destroyed || token !== this.pumpToken) return;
          const isVideo = this.videoTrack && sample.trackNumber === this.videoTrack.number;
          const isAudio = this.audioTrack && sample.trackNumber === this.audioTrack.number;
          const isSub = this.subtitleTrack && sample.trackNumber === this.subtitleTrack.number;
          if (isSub) {
            this.addCue(sample);
            continue;
          }
          if (!isVideo && !isAudio) continue;
          if (isVideo && !firstVideoKey) {
            if (!sample.keyframe) continue;
            firstVideoKey = true;
          }
          if (isVideo && this.transcodeVideo) {
            await vt.push(sample);
          } else if (isAudio && this.transcodeAudio) {
            await at.push(sample);
          } else if (fragmenter) {
            const fragment = fragmenter.push(sample);
            if (fragment) this.enqueue("remux", fragment);
          }
          await this.throttle(token);
        }
        if (this.destroyed || token !== this.pumpToken) return;
        if (fragmenter) {
          const rest = fragmenter.flush();
          if (rest) this.enqueue("remux", rest);
        }
        if (vt) await vt.finish();
        if (at) await at.finish();
        this.ended = true;
        this.finishWhenDrained(token);
      } catch (error) {
        if (!this.destroyed && token === this.pumpToken) this.fail(error);
      } finally {
        if (token === this.pumpToken) this.pumping = false;
      }
    }

    finishWhenDrained(token) {
      const check = () => {
        if (this.destroyed || token !== this.pumpToken) return;
        const busy = Object.entries(this.buffers).some(
          ([name, sb]) => sb.updating || this.queues[name].length
        );
        if (busy) {
          setTimeout(check, 100);
          return;
        }
        try {
          if (this.mediaSource.readyState === "open") this.mediaSource.endOfStream();
        } catch (error) {
          /* already ended */
        }
      };
      check();
    }

    handleSeek() {
      const target = this.video.currentTime;
      // Already buffered there: the element handles it.
      for (const sb of Object.values(this.buffers)) {
        let covered = false;
        try {
          for (let i = 0; i < sb.buffered.length; i += 1) {
            if (sb.buffered.start(i) <= target + 0.2 && sb.buffered.end(i) >= target + 1) covered = true;
          }
        } catch (error) {
          covered = false;
        }
        if (!covered) {
          this.restartAt(target);
          return;
        }
      }
      if (this.ended) return;
      // buffered but the pump may be parked far away, wake it
      this.wake();
    }

    restartAt(time) {
      this.pumpToken += 1;
      Object.entries(this.buffers).forEach(([name, sb]) => {
        this.queues[name] = [];
        try {
          if (sb.updating) sb.abort();
        } catch (error) {
          /* not updating */
        }
      });
      this.wake();
      this.startPump(Math.max(0, time));
    }

    fail(error) {
      if (this.destroyed) return;
      this.status("error", { error });
      if (this.options.onError) this.options.onError(error);
    }

    destroy() {
      this.destroyed = true;
      this.pumpToken += 1;
      this.wake();
      this.video.removeEventListener("seeking", this.onSeeking);
      this.video.removeEventListener("timeupdate", this.onTimeUpdate);
      if (this.videoTranscoder) this.videoTranscoder.close();
      if (this.audioTranscoder) this.audioTranscoder.close();
      try {
        if (this.mediaSource && this.mediaSource.readyState === "open") this.mediaSource.endOfStream();
      } catch (error) {
        /* ignore */
      }
      if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
      this.video.removeAttribute("src");
      this.video.load();
    }
  }

  /* ===== Public API ===== */
  function attach(video, options) {
    const ext = extensionOf(options.name || options.url);
    const controller = {
      mode: null,
      info: {},
      destroy() {
        if (controller.playback) controller.playback.destroy();
        else {
          video.removeAttribute("src");
          video.load();
        }
      }
    };

    if (NATIVE_EXTENSIONS.has(ext) && !options.forceRemux) {
      controller.mode = "native";
      video.src = options.url;
      if (options.startAt) {
        video.addEventListener(
          "loadedmetadata",
          () => {
            video.currentTime = options.startAt;
          },
          { once: true }
        );
      }
      controller.ready = Promise.resolve(controller);
      if (options.onStatus) options.onStatus("native");
      return controller;
    }

    const playback = new MsePlayback(video, options.url, options);
    controller.playback = playback;
    controller.ready = playback.open().then(() => {
      controller.mode = playback.mode;
      controller.info = {
        video: playback.videoTrack && (playback.videoTrack.codecId || playback.videoTrack.codec),
        audio: playback.audioTrack && (playback.audioTrack.codecId || playback.audioTrack.codec),
        transcodeVideo: playback.transcodeVideo,
        transcodeAudio: playback.transcodeAudio
      };
      if (options.startAt) {
        // the pump already started at startAt; move the playhead to match
        video.currentTime = options.startAt;
      }
      return controller;
    });
    return controller;
  }

  /* One frame from `at` seconds (or a fraction of the duration), as a JPEG blob.
     Used to build the episode covers; null when the browser cannot play the file. */
  async function captureFrame(options) {
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.crossOrigin = "anonymous";
    video.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:320px;height:180px;opacity:0;pointer-events:none";
    document.body.appendChild(video);

    const width = options.width || 480;
    const timeoutMs = options.timeoutMs || 30000;
    let controller = null;
    const cleanup = () => {
      if (controller) controller.destroy();
      video.remove();
    };

    try {
      const once = (event) =>
        new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error(`timeout waiting for ${event}`)), timeoutMs);
          video.addEventListener(
            event,
            () => {
              clearTimeout(timer);
              resolve();
            },
            { once: true }
          );
          video.addEventListener(
            "error",
            () => {
              clearTimeout(timer);
              reject(new Error("media error"));
            },
            { once: true }
          );
        });

      const metadata = once("loadedmetadata");
      controller = attach(video, { url: options.url, name: options.name, onStatus() {}, onError() {} });
      await controller.ready;
      await metadata;

      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      let target = options.at;
      if (target == null) target = 0.15 + Math.random() * 0.7;
      if (target <= 1 && duration) target *= duration;
      target = Math.max(0, Math.min(target, duration ? duration - 1 : target));

      const seeked = once("seeked");
      video.currentTime = target;
      await seeked;
      // Ensure a frame is actually decoded at the new position.
      if (video.readyState < 2) await once("canplay");
      if ("requestVideoFrameCallback" in video) {
        await new Promise((resolve) => {
          const timer = setTimeout(resolve, 1500);
          video.requestVideoFrameCallback(() => {
            clearTimeout(timer);
            resolve();
          });
          video.play().catch(() => {});
        });
        video.pause();
      }

      const ratio = video.videoWidth && video.videoHeight ? video.videoHeight / video.videoWidth : 9 / 16;
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = Math.round(width * ratio);
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      // a black frame (fade, scene cut) is not a cover; sample a few pixels
      const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      let sum = 0;
      for (let i = 0; i < pixels.length; i += 4 * 97) sum += pixels[i] + pixels[i + 1] + pixels[i + 2];
      const samples = Math.ceil(pixels.length / (4 * 97));
      const brightness = sum / (samples * 3);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
      return { blob, time: target, duration, dark: brightness < 12 };
    } catch (error) {
      return null;
    } finally {
      cleanup();
    }
  }

  function canPlayInBrowser(name) {
    const ext = extensionOf(name);
    if (NATIVE_EXTENSIONS.has(ext)) return true;
    return Boolean(MediaSourceImpl && window.MkvRemux) && (ext === "mkv" || ext === "webm");
  }

  window.WebPlayer = { attach, captureFrame, canPlayInBrowser, formatTime, extensionOf, Mp4 };
})();
