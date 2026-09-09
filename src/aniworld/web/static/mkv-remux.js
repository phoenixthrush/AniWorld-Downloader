/* Matroska in the browser: demux a .mkv, re-package it as fragmented MP4.
 *
 * Why this exists. Browsers refuse to play Matroska in <video>, but the
 * streams inside a download are almost always H.264 + AAC, which every
 * browser decodes happily. Only the container is the problem, and a
 * container is metadata: the very same coded frames, wrapped in an fMP4
 * init segment plus moof/mdat fragments, play through Media Source
 * Extensions with nothing decoded or re-encoded on the way. That keeps
 * playback off the server, which is the constraint that shaped this whole
 * feature: the maintainers do not want ffmpeg in the request path just so
 * the Web UI can play a file.
 *
 * The file is deliberately dependency-free and loads three ways: as a
 * classic <script> in the page (window/self.MkvRemux), via require() under
 * Node (tests/webplayer_check.mjs verifies the output with ffprobe), and
 * inside a worker. Nothing here touches the DOM.
 *
 * Sections, in order:
 *   1. EBML   - vints, elements, a sliding-window byte reader
 *   2. Matroska - Segment/Info/Tracks/Cues, Clusters, Blocks, lacing
 *   3. Codecs - Matroska CodecID -> MP4 sample entry + MSE codec string
 *   4. MP4    - the box writer (init segment and fragments)
 *   5. Remux  - the Demuxer and the Fragmenter the player drives
 */
(function () {
  "use strict";

  // =====================================================================
  // 1. EBML
  // =====================================================================
  // Element ids are compared as the integer their raw bytes spell, marker
  // bits included, which is how they are written in the spec tables.
  const EBML_HEADER = 0x1a45dfa3;
  const SEGMENT = 0x18538067;
  const SEEK_HEAD = 0x114d9b74;
  const SEEK = 0x4dbb;
  const SEEK_ID = 0x53ab;
  const SEEK_POSITION = 0x53ac;
  const INFO = 0x1549a966;
  const TIMECODE_SCALE = 0x2ad7b1;
  const DURATION = 0x4489;
  const TRACKS = 0x1654ae6b;
  const TRACK_ENTRY = 0xae;
  const TRACK_NUMBER = 0xd7;
  const TRACK_TYPE = 0x83;
  const FLAG_DEFAULT = 0x88;
  const DEFAULT_DURATION = 0x23e383;
  const CODEC_ID = 0x86;
  const CODEC_PRIVATE = 0x63a2;
  const CODEC_DELAY = 0x56aa;
  const SEEK_PRE_ROLL = 0x56bb;
  const TRACK_NAME = 0x536e;
  const LANGUAGE = 0x22b59c;
  const LANGUAGE_BCP47 = 0x22b59d;
  const VIDEO = 0xe0;
  const PIXEL_WIDTH = 0xb0;
  const PIXEL_HEIGHT = 0xba;
  const AUDIO = 0xe1;
  const SAMPLING_FREQUENCY = 0xb5;
  const OUTPUT_SAMPLING_FREQUENCY = 0x78b5;
  const CHANNELS = 0x9f;
  const BIT_DEPTH = 0x6264;
  const CUES = 0x1c53bb6b;
  const CUE_POINT = 0xbb;
  const CUE_TIME = 0xb3;
  const CUE_TRACK_POSITIONS = 0xb7;
  const CUE_TRACK = 0xf7;
  const CUE_CLUSTER_POSITION = 0xf1;
  const CLUSTER = 0x1f43b675;
  const TIMECODE = 0xe7;
  const SIMPLE_BLOCK = 0xa3;
  const BLOCK_GROUP = 0xa0;
  const BLOCK = 0xa1;
  const BLOCK_DURATION = 0x9b;
  const REFERENCE_BLOCK = 0xfb;
  const TAGS = 0x1254c367;
  const CHAPTERS = 0x1043a770;
  const ATTACHMENTS = 0x1941a469;

  // A Cluster written by a live muxer carries "unknown" for its size and
  // ends where the next top-level element begins. These are the ids that
  // can legally follow one.
  const TOP_LEVEL = new Set([
    CLUSTER,
    CUES,
    TAGS,
    CHAPTERS,
    ATTACHMENTS,
    SEEK_HEAD,
    INFO,
    TRACKS,
    SEGMENT,
    EBML_HEADER,
  ]);

  const TRACK_TYPE_NAMES = { 1: "video", 2: "audio", 17: "subtitle" };

  /* Length of a vint from its first byte: the position of the top set bit.
     0 means "more than 8 bytes", which no valid file contains. */
  function vintLength(first) {
    for (let i = 0; i < 8; i += 1) {
      if (first & (0x80 >> i)) return i + 1;
    }
    return 0;
  }

  /* Big-endian unsigned integer. Values above 2^53 cannot occur in the
     fields this reads (sizes, timestamps), so a Number is exact. */
  function uint(bytes, offset, length) {
    let value = 0;
    for (let i = 0; i < length; i += 1) value = value * 256 + bytes[offset + i];
    return value;
  }

  /* A data-size vint with its marker stripped, plus whether every value bit
     was set (the "unknown size" encoding). */
  function readVint(bytes, offset) {
    const length = vintLength(bytes[offset]);
    if (!length || offset + length > bytes.length) return null;
    let value = bytes[offset] & (0xff >> length);
    let allOnes = value === (0xff >> length);
    for (let i = 1; i < length; i += 1) {
      const byte = bytes[offset + i];
      if (byte !== 0xff) allOnes = false;
      value = value * 256 + byte;
    }
    return { value, length, unknown: allOnes, next: offset + length };
  }

  /* Reads through the caller's byte source, keeping one window in memory.
     Parsing is sequential, so a single window turns a run of element
     headers and their payloads into one request; a seek simply misses. */
  class Reader {
    constructor(source, readAhead) {
      this.source = source;
      this.size = Number(source.size) || 0;
      this.readAhead = readAhead || 1 << 20;
      this.window = new Uint8Array(0);
      this.windowStart = 0;
      this.bytesRead = 0;
    }

    async bytes(offset, length) {
      if (offset < 0 || offset >= this.size) return new Uint8Array(0);
      const end = Math.min(this.size, offset + length);
      const start = this.windowStart;
      if (offset >= start && end <= start + this.window.length) {
        return this.window.subarray(offset - start, end - start);
      }
      const want = Math.min(this.size - offset, Math.max(length, this.readAhead));
      const data = await this.source.read(offset, want);
      this.window = data;
      this.windowStart = offset;
      this.bytesRead += data.length;
      return data.subarray(0, Math.min(data.length, end - offset));
    }
  }

  /* One element header at `offset`: its id, payload size and where the
     payload starts. Returns null at EOF or on a byte pattern that is not a
     vint, which is how a truncated file ends an iteration cleanly. */
  async function readElement(reader, offset) {
    if (offset >= reader.size) return null;
    const head = await reader.bytes(offset, 16);
    if (head.length < 2) return null;
    const idLength = vintLength(head[0]);
    if (!idLength || head.length < idLength + 1) return null;
    const id = uint(head, 0, idLength);
    const size = readVint(head, idLength);
    if (!size) return null;
    const headerLength = idLength + size.length;
    return {
      id,
      size: size.unknown ? 0 : size.value,
      unknown: size.unknown,
      start: offset,
      dataStart: offset + headerLength,
      end: size.unknown ? -1 : offset + headerLength + size.value,
    };
  }

  async function elementBytes(reader, element) {
    if (!element.size) return new Uint8Array(0);
    return reader.bytes(element.dataStart, element.size);
  }

  async function elementUint(reader, element) {
    const bytes = await elementBytes(reader, element);
    return uint(bytes, 0, bytes.length);
  }

  async function elementFloat(reader, element) {
    const bytes = await elementBytes(reader, element);
    if (bytes.length === 4) return new DataView(bytes.buffer, bytes.byteOffset, 4).getFloat32(0);
    if (bytes.length === 8) return new DataView(bytes.buffer, bytes.byteOffset, 8).getFloat64(0);
    return uint(bytes, 0, bytes.length);
  }

  async function elementString(reader, element) {
    const bytes = await elementBytes(reader, element);
    let text = "";
    for (let i = 0; i < bytes.length; i += 1) {
      if (!bytes[i]) break;
      text += String.fromCharCode(bytes[i]);
    }
    return text;
  }

  /* Walk the children of a master element, calling back per child. Unknown
     ids are skipped by their size, which is what keeps a file with elements
     this code has never heard of readable. */
  async function eachChild(reader, element, visit) {
    const limit = element.unknown ? reader.size : element.end;
    let offset = element.dataStart;
    while (offset < limit) {
      const child = await readElement(reader, offset);
      if (!child) return offset;
      if (element.unknown && TOP_LEVEL.has(child.id)) return offset;
      const stop = await visit(child);
      if (stop === false) return child.unknown ? limit : child.end;
      if (child.unknown) return limit;
      offset = child.end;
    }
    return limit;
  }

  // =====================================================================
  // 2. Blocks
  // =====================================================================
  /* One (Simple)Block payload: which track, when, and the coded frames.
     Lacing packs several frames into one block, so this returns a list. */
  function parseBlock(data) {
    if (data.length < 4) return null;
    const numberLength = vintLength(data[0]);
    if (!numberLength) return null;
    let trackNumber = data[0] & (0xff >> numberLength);
    for (let i = 1; i < numberLength; i += 1) trackNumber = trackNumber * 256 + data[i];

    let at = numberLength;
    const raw = (data[at] << 8) | data[at + 1];
    const relative = raw > 0x7fff ? raw - 0x10000 : raw;
    at += 2;
    const flags = data[at];
    at += 1;

    const lacing = (flags >> 1) & 0x03;
    const frames = [];
    if (lacing === 0) {
      frames.push(data.subarray(at));
    } else {
      const count = data[at] + 1;
      at += 1;
      const sizes = [];
      if (lacing === 2) {
        // fixed: every frame is the same size
        const each = Math.floor((data.length - at) / count);
        for (let i = 0; i < count; i += 1) sizes.push(each);
      } else if (lacing === 1) {
        // Xiph: 255-terminated byte runs, last size implicit
        for (let i = 0; i < count - 1; i += 1) {
          let size = 0;
          while (at < data.length && data[at] === 255) {
            size += 255;
            at += 1;
          }
          size += data[at];
          at += 1;
          sizes.push(size);
        }
        sizes.push(-1);
      } else {
        // EBML: first size, then signed deltas, last size implicit
        const first = readVint(data, at);
        if (!first) return null;
        sizes.push(first.value);
        at = first.next;
        for (let i = 1; i < count - 1; i += 1) {
          const delta = readVint(data, at);
          if (!delta) return null;
          const bias = Math.pow(2, 7 * delta.length - 1) - 1;
          sizes.push(sizes[sizes.length - 1] + (delta.value - bias));
          at = delta.next;
        }
        if (count > 1) sizes.push(-1);
      }
      for (let i = 0; i < count; i += 1) {
        const size = sizes[i] < 0 ? data.length - at : sizes[i];
        if (size < 0 || at + size > data.length) break;
        frames.push(data.subarray(at, at + size));
        at += size;
      }
    }

    return {
      trackNumber,
      relative,
      keyframe: (flags & 0x80) !== 0,
      invisible: (flags & 0x08) !== 0,
      laced: lacing !== 0,
      frames,
    };
  }

  // =====================================================================
  // 3. Codecs
  // =====================================================================
  // Matroska names a codec; MP4 wants a four-character sample entry plus a
  // configuration box, and MSE wants a codec string for isTypeSupported.
  // The coded frames themselves are never touched: AVC in Matroska is
  // already length-prefixed, which is exactly what avc1 expects.
  const AAC_SAMPLE_RATES = [
    96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025,
    8000, 7350,
  ];

  function hex2(value) {
    return value.toString(16).toUpperCase().padStart(2, "0");
  }

  function avcCodecString(avcC) {
    if (!avcC || avcC.length < 4) return "avc1.42E01E";
    return `avc1.${hex2(avcC[1])}${hex2(avcC[2])}${hex2(avcC[3])}`;
  }

  /* ISO/IEC 14496-15 Annex E. The compatibility flags are written with the
     bit order reversed, which is the part everyone gets wrong; trailing
     zero constraint bytes are omitted. */
  function hevcCodecString(hvcC) {
    if (!hvcC || hvcC.length < 13) return null;
    const profileSpace = hvcC[1] >> 6;
    const tier = (hvcC[1] >> 5) & 1;
    const profile = hvcC[1] & 0x1f;
    const compat = uint(hvcC, 2, 4);
    let reversed = 0;
    for (let i = 0; i < 32; i += 1) reversed = (reversed << 1) | ((compat >>> i) & 1);
    reversed = reversed >>> 0;

    const parts = ["hvc1"];
    parts.push((["", "A", "B", "C"][profileSpace] || "") + profile);
    parts.push(reversed.toString(16).toUpperCase());
    parts.push((tier ? "H" : "L") + hvcC[12]);
    const constraints = [];
    for (let i = 6; i < 12; i += 1) constraints.push(hvcC[i]);
    while (constraints.length && constraints[constraints.length - 1] === 0) constraints.pop();
    constraints.forEach((byte) => parts.push(hex2(byte)));
    return parts.join(".");
  }

  function av1CodecString(av1C) {
    if (!av1C || av1C.length < 3) return null;
    const profile = (av1C[1] >> 5) & 0x07;
    const level = av1C[1] & 0x1f;
    const tier = (av1C[2] >> 7) & 1;
    const high = (av1C[2] >> 6) & 1;
    const twelve = (av1C[2] >> 5) & 1;
    const depth = twelve ? 12 : high ? 10 : 8;
    const levelText = String(level).padStart(2, "0");
    return `av01.${profile}.${levelText}${tier ? "H" : "M"}.${String(depth).padStart(2, "0")}`;
  }

  /* VP9 in Matroska usually carries no CodecPrivate, so vpcC is built from
     what the track header says. The level has to be plausible or Chrome
     refuses the codec string outright, hence the resolution table. */
  function vp9Level(width, height, fps) {
    const rate = (width || 640) * (height || 360) * (fps || 30);
    const table = [
      [829440 * 30, 10],
      [2764800 * 30, 21],
      [4147200 * 30, 30],
      [8294400 * 30, 40],
      [8294400 * 60, 41],
      [16588800 * 60, 50],
      [33177600 * 60, 51],
    ];
    for (const entry of table) {
      if (rate <= entry[0]) return entry[1];
    }
    return 52;
  }

  function aacObjectType(asc) {
    if (!asc || !asc.length) return 2;
    const type = asc[0] >> 3;
    if (type !== 31 || asc.length < 2) return type;
    return 32 + (((asc[0] & 0x07) << 3) | (asc[1] >> 5));
  }

  /* An AudioSpecificConfig for plain AAC-LC, for the rare muxer that leaves
     CodecPrivate empty. Five bits object type, four bits rate index, four
     bits channel configuration, three bits of framing flags. */
  function synthesiseAsc(sampleRate, channels) {
    let index = AAC_SAMPLE_RATES.indexOf(sampleRate);
    if (index < 0) index = 4;
    const config = Math.min(7, Math.max(1, channels || 2));
    return new Uint8Array([(2 << 3) | (index >> 1), ((index & 1) << 7) | (config << 3)]);
  }

  /* Fills in track.mp4 (the sample entry) and track.codec (the MSE codec
     string). A codec neither can express leaves both null: the caller then
     transcodes it or says so, but nothing here throws. */
  function mapCodec(track) {
    const id = (track.codecId || "").toUpperCase();
    const priv = track.codecPrivate;
    track.mp4 = null;
    track.codec = null;

    if (id === "V_MPEG4/ISO/AVC") {
      track.mp4 = "avc1";
      track.codec = avcCodecString(priv);
    } else if (id === "V_MPEGH/ISO/HEVC") {
      const codec = hevcCodecString(priv);
      if (codec) {
        track.mp4 = "hvc1";
        track.codec = codec;
      }
    } else if (id === "V_AV1") {
      const codec = av1CodecString(priv);
      if (codec) {
        track.mp4 = "av01";
        track.codec = codec;
      }
    } else if (id === "V_VP9") {
      const fps = track.defaultDuration ? 1e9 / track.defaultDuration : 30;
      track.mp4 = "vp09";
      track.codec = `vp09.00.${String(vp9Level(track.width, track.height, fps)).padStart(2, "0")}.${String(track.bitDepth || 8).padStart(2, "0")}`;
    } else if (id === "A_AAC" || id.indexOf("A_AAC/") === 0) {
      track.mp4 = "mp4a";
      track.asc = priv && priv.length ? priv : synthesiseAsc(track.sampleRate, track.channels);
      track.codec = `mp4a.40.${aacObjectType(track.asc)}`;
    } else if (id === "A_OPUS") {
      track.mp4 = "Opus";
      track.codec = "opus";
    } else if (id === "A_FLAC") {
      track.mp4 = "fLaC";
      track.codec = "flac";
    } else if (id === "A_MPEG/L3") {
      track.mp4 = "mp4a";
      track.objectType = 0x6b;
      track.codec = "mp4a.6B";
    }
    return track;
  }

  // =====================================================================
  // 4. MP4
  // =====================================================================
  const Mp4 = (function () {
    function ascii(text) {
      const out = new Uint8Array(text.length);
      for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i) & 0xff;
      return out;
    }

    function concat(parts) {
      let size = 0;
      for (const part of parts) size += part.length;
      const out = new Uint8Array(size);
      let at = 0;
      for (const part of parts) {
        out.set(part, at);
        at += part.length;
      }
      return out;
    }

    function box(type) {
      const payloads = Array.prototype.slice.call(arguments, 1);
      let size = 8;
      for (const payload of payloads) size += payload.length;
      const header = new Uint8Array(8);
      new DataView(header.buffer).setUint32(0, size);
      header.set(ascii(type), 4);
      return concat([header].concat(payloads));
    }

    function fullBox(type, version, flags) {
      const payloads = Array.prototype.slice.call(arguments, 3);
      const head = new Uint8Array([version, (flags >> 16) & 0xff, (flags >> 8) & 0xff, flags & 0xff]);
      return box.apply(null, [type, head].concat(payloads));
    }

    function u8() {
      return new Uint8Array(Array.prototype.slice.call(arguments));
    }

    function u16() {
      const values = Array.prototype.slice.call(arguments);
      const out = new Uint8Array(values.length * 2);
      const view = new DataView(out.buffer);
      values.forEach((value, i) => view.setUint16(i * 2, value & 0xffff));
      return out;
    }

    function i16() {
      const values = Array.prototype.slice.call(arguments);
      const out = new Uint8Array(values.length * 2);
      const view = new DataView(out.buffer);
      values.forEach((value, i) => view.setInt16(i * 2, value));
      return out;
    }

    function u32() {
      const values = Array.prototype.slice.call(arguments);
      const out = new Uint8Array(values.length * 4);
      const view = new DataView(out.buffer);
      values.forEach((value, i) => view.setUint32(i * 4, value >>> 0));
      return out;
    }

    function i32() {
      const values = Array.prototype.slice.call(arguments);
      const out = new Uint8Array(values.length * 4);
      const view = new DataView(out.buffer);
      values.forEach((value, i) => view.setInt32(i * 4, value | 0));
      return out;
    }

    function u64(value) {
      const out = new Uint8Array(8);
      new DataView(out.buffer).setBigUint64(0, BigInt(Math.max(0, Math.round(value))));
      return out;
    }

    function zeros(count) {
      return new Uint8Array(count);
    }

    const MATRIX = u32(0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000);

    /* MPEG-4 descriptors use a base-128 length. Two bytes cover anything an
       AudioSpecificConfig can be, but the encoder is general so a long
       DecoderSpecificInfo cannot silently corrupt the chain. */
    function descriptor(tag, payload) {
      const lengths = [];
      let size = payload.length;
      do {
        lengths.unshift(size & 0x7f);
        size >>= 7;
      } while (size > 0);
      for (let i = 0; i < lengths.length - 1; i += 1) lengths[i] |= 0x80;
      return concat([u8(tag), new Uint8Array(lengths), payload]);
    }

    function esds(asc, objectType) {
      const specific = asc && asc.length ? descriptor(0x05, asc) : new Uint8Array(0);
      const config = descriptor(
        0x04,
        concat([u8(objectType || 0x40, 0x15), zeros(3), u32(0, 0), specific])
      );
      const sl = descriptor(0x06, u8(0x02));
      const es = descriptor(0x03, concat([u16(1), u8(0), config, sl]));
      return fullBox("esds", 0, 0, es);
    }

    /* Matroska stores the Opus identification header (little endian);
       dOps wants the same fields big endian, minus the magic. */
    function dOps(track) {
      const head = track.codecPrivate;
      const usable = head && head.length >= 19;
      const view = usable ? new DataView(head.buffer, head.byteOffset, head.length) : null;
      const channels = (usable ? head[9] : track.channels) || 2;
      const preSkip = view ? view.getUint16(10, true) : 312;
      const rate = view ? view.getUint32(12, true) : track.sampleRate || 48000;
      const gain = view ? view.getInt16(16, true) : 0;
      const family = view ? head[18] : 0;
      const parts = [u8(0, channels), u16(preSkip), u32(rate), i16(gain), u8(family)];
      if (family !== 0 && usable && head.length >= 21 + channels) {
        parts.push(head.subarray(19, 21 + channels));
      }
      return box("dOps", concat(parts));
    }

    /* Matroska's FLAC CodecPrivate is the whole stream header: the "fLaC"
       magic followed by metadata blocks. dfLa wants the blocks alone, with
       the last-block flag set on the one it carries. */
    function dfLa(track) {
      const priv = track.codecPrivate || new Uint8Array(0);
      let blocks = priv;
      const magic = priv.length > 4 && priv[0] === 0x66 && priv[1] === 0x4c && priv[2] === 0x61 && priv[3] === 0x43;
      if (magic) blocks = priv.subarray(4);
      const streamInfo = blocks.slice(0, Math.min(blocks.length, 38));
      if (streamInfo.length) streamInfo[0] |= 0x80;
      return fullBox("dfLa", 0, 0, streamInfo);
    }

    function vpcC(track) {
      const fps = track.defaultDuration ? 1e9 / track.defaultDuration : 30;
      const depth = track.bitDepth || 8;
      return fullBox(
        "vpcC",
        1,
        0,
        u8(0, vp9Level(track.width, track.height, fps), (depth << 4) | (1 << 1), 2, 2, 2),
        u16(0)
      );
    }

    function visualEntry(track) {
      const body = new Uint8Array(78);
      const view = new DataView(body.buffer);
      view.setUint16(6, 1); // data_reference_index
      view.setUint16(24, track.width || 0);
      view.setUint16(26, track.height || 0);
      view.setUint32(28, 0x00480000); // 72 dpi
      view.setUint32(32, 0x00480000);
      view.setUint16(40, 1); // frame_count
      view.setUint16(74, 0x0018); // depth
      view.setInt16(76, -1); // pre_defined
      let config;
      if (track.mp4 === "avc1") config = box("avcC", track.codecPrivate);
      else if (track.mp4 === "hvc1") config = box("hvcC", track.codecPrivate);
      else if (track.mp4 === "av01") config = box("av1C", track.codecPrivate);
      else config = vpcC(track);
      return box(track.mp4, body, config);
    }

    function audioEntry(track) {
      const body = new Uint8Array(28);
      const view = new DataView(body.buffer);
      view.setUint16(6, 1);
      view.setUint16(16, track.channels || 2);
      view.setUint16(18, 16);
      // 16.16 fixed point cannot hold 96 kHz; the mdhd timescale carries the
      // real rate and every decoder reads it from there.
      view.setUint32(24, (Math.min(65535, track.sampleRate || 48000) & 0xffff) << 16);
      if (track.mp4 === "Opus") return box("Opus", body, dOps(track));
      if (track.mp4 === "fLaC") return box("fLaC", body, dfLa(track));
      return box("mp4a", body, esds(track.asc, track.objectType));
    }

    function sampleEntry(track) {
      return track.type === "video" ? visualEntry(track) : audioEntry(track);
    }

    function trak(track) {
      const video = track.type === "video";
      const tkhd = fullBox(
        "tkhd",
        0,
        3, // enabled | in movie
        u32(0, 0, track.id, 0, 0),
        zeros(8),
        u16(0, 0, video ? 0 : 0x0100, 0), // layer, alternate_group, volume, reserved
        MATRIX,
        u32(video ? (track.width || 0) << 16 : 0, video ? (track.height || 0) << 16 : 0)
      );
      const mdhd = fullBox("mdhd", 0, 0, u32(0, 0, track.timescale, 0), u16(0x55c4, 0));
      const hdlr = fullBox(
        "hdlr",
        0,
        0,
        u32(0),
        ascii(video ? "vide" : "soun"),
        zeros(12),
        ascii(video ? "VideoHandler" : "SoundHandler"),
        zeros(1)
      );
      const dinf = box("dinf", fullBox("dref", 0, 0, u32(1), fullBox("url ", 0, 1)));
      const stbl = box(
        "stbl",
        fullBox("stsd", 0, 0, u32(1), sampleEntry(track)),
        fullBox("stts", 0, 0, u32(0)),
        fullBox("stsc", 0, 0, u32(0)),
        fullBox("stsz", 0, 0, u32(0, 0)),
        fullBox("stco", 0, 0, u32(0))
      );
      const mhd = video
        ? fullBox("vmhd", 0, 1, u16(0, 0, 0, 0))
        : fullBox("smhd", 0, 0, u16(0, 0));
      return box("trak", tkhd, box("mdia", mdhd, hdlr, box("minf", mhd, dinf, stbl)));
    }

    /* ftyp + moov. Duration is left at zero: this feeds MSE, which takes
       the duration from the MediaSource rather than from here. */
    function init(tracks) {
      const ftyp = box("ftyp", ascii("isom"), u32(1), ascii("isomiso2avc1iso6mp41"));
      const mvhd = fullBox(
        "mvhd",
        0,
        0,
        u32(0, 0, 1000, 0),
        u32(0x00010000),
        u16(0x0100, 0),
        zeros(8),
        MATRIX,
        zeros(24),
        u32(tracks.length + 1)
      );
      const trex = tracks.map((track) => fullBox("trex", 0, 0, u32(track.id, 1, 0, 0, 0)));
      const moov = box.apply(null, ["moov", mvhd].concat(tracks.map(trak), [box.apply(null, ["mvex"].concat(trex))]));
      return concat([ftyp, moov]);
    }

    function sampleFlags(sample) {
      // depends_on=2 marks a sync sample; depends_on=1 plus non_sync=1 a
      // frame that needs its references.
      return sample.keyframe ? 0x02000000 : 0x01010000;
    }

    /* One moof plus one mdat, with a traf per track. data_offset has to
       point at that track's first byte inside the mdat, so the moof is
       built twice: once to learn its size, once with the real offsets. */
    function fragment(sequence, runs) {
      const active = runs.filter((run) => run && run.samples && run.samples.length);
      if (!active.length) return null;

      const build = (offsets) => {
        const trafs = active.map((run, index) => {
          const entries = [];
          run.samples.forEach((sample) => {
            entries.push(
              u32(Math.max(0, sample.duration), sample.data.length, sampleFlags(sample)),
              i32(Math.round(sample.pts - sample.dts))
            );
          });
          const trun = fullBox.apply(
            null,
            ["trun", 1, 0x000f01, u32(run.samples.length), i32(offsets ? offsets[index] : 0)].concat(entries)
          );
          return box(
            "traf",
            fullBox("tfhd", 0, 0x020000, u32(run.id)),
            fullBox("tfdt", 1, 0, u64(run.samples[0].dts)),
            trun
          );
        });
        return box.apply(null, ["moof", fullBox("mfhd", 0, 0, u32(sequence))].concat(trafs));
      };

      const probe = build(null);
      const offsets = [];
      let at = probe.length + 8; // first byte after the mdat header
      for (const run of active) {
        offsets.push(at);
        for (const sample of run.samples) at += sample.data.length;
      }
      const payload = [];
      for (const run of active) {
        for (const sample of run.samples) payload.push(sample.data);
      }
      return concat([build(offsets), box.apply(null, ["mdat"].concat(payload))]);
    }

    return { init, fragment, box, fullBox, concat, ascii };
  })();

  // =====================================================================
  // 5. Remux
  // =====================================================================
  class Demuxer {
    constructor(reader) {
      this.reader = reader;
      this.tracks = [];
      this.byNumber = new Map();
      this.cues = [];
      this.timecodeScale = 1000000;
      this.duration = 0;
      this.segmentStart = 0;
      this.firstCluster = null;
      this.reorderDepth = 0;
      this.frameDuration = 0;
    }

    trackByNumber(number) {
      if (number == null) return null;
      return this.byNumber.get(Number(number)) || null;
    }

    async load() {
      const reader = this.reader;
      const header = await readElement(reader, 0);
      if (!header || header.id !== EBML_HEADER) {
        throw new Error("not a Matroska file");
      }

      let offset = header.unknown ? 0 : header.end;
      let segment = null;
      while (offset < reader.size) {
        const element = await readElement(reader, offset);
        if (!element) break;
        if (element.id === SEGMENT) {
          segment = element;
          break;
        }
        if (element.unknown) break;
        offset = element.end;
      }
      if (!segment) throw new Error("no Segment element");
      this.segmentStart = segment.dataStart;
      const segmentEnd = segment.unknown ? reader.size : segment.end;

      // Walk the Segment's children only as far as the first Cluster: past
      // that point everything worth having is reachable through SeekHead,
      // and scanning a 24-minute file to find Cues at the end would defeat
      // the whole design.
      const seek = new Map();
      let position = segment.dataStart;
      while (position < segmentEnd) {
        const element = await readElement(reader, position);
        if (!element) break;
        if (element.id === CLUSTER) {
          this.firstCluster = position;
          break;
        }
        await this.readTopLevel(element, seek);
        if (element.unknown) break;
        position = element.end;
      }

      await this.followSeekHead(seek);
      if (this.firstCluster == null && seek.has(CLUSTER)) {
        this.firstCluster = this.segmentStart + seek.get(CLUSTER);
      }
      this.cues.sort((a, b) => a.time - b.time);
      this.tracks.forEach(mapCodec);
      await this.probe();
      return this;
    }

    async readTopLevel(element, seek) {
      if (element.id === SEEK_HEAD) await this.readSeekHead(element, seek);
      else if (element.id === INFO) await this.readInfo(element);
      else if (element.id === TRACKS) await this.readTracks(element);
      else if (element.id === CUES) await this.readCues(element);
    }

    /* Cues, Tracks and Info usually sit before the first Cluster, but a file
       muxed in one pass puts them at the end and only leaves a SeekHead
       behind. Two rounds cover a SeekHead that points at another one. */
    async followSeekHead(seek) {
      for (let round = 0; round < 3; round += 1) {
        const wanted = [];
        if (!this.tracks.length && seek.has(TRACKS)) wanted.push(TRACKS);
        if (!this.cues.length && seek.has(CUES)) wanted.push(CUES);
        if (seek.has(SEEK_HEAD) && round === 0) wanted.push(SEEK_HEAD);
        if (!wanted.length) return;
        for (const id of wanted) {
          const at = this.segmentStart + seek.get(id);
          seek.delete(id);
          const element = await readElement(this.reader, at);
          if (element && element.id === id) await this.readTopLevel(element, seek);
        }
      }
    }

    async readSeekHead(element, seek) {
      const reader = this.reader;
      await eachChild(reader, element, async (entry) => {
        if (entry.id !== SEEK) return;
        let id = null;
        let position = null;
        await eachChild(reader, entry, async (field) => {
          if (field.id === SEEK_ID) {
            const bytes = await elementBytes(reader, field);
            id = uint(bytes, 0, bytes.length);
          } else if (field.id === SEEK_POSITION) {
            position = await elementUint(reader, field);
          }
        });
        if (id != null && position != null && !seek.has(id)) seek.set(id, position);
      });
    }

    async readInfo(element) {
      const reader = this.reader;
      let rawDuration = 0;
      await eachChild(reader, element, async (field) => {
        if (field.id === TIMECODE_SCALE) this.timecodeScale = await elementUint(reader, field);
        else if (field.id === DURATION) rawDuration = await elementFloat(reader, field);
      });
      this.duration = rawDuration ? (rawDuration * this.timecodeScale) / 1e9 : 0;
    }

    async readTracks(element) {
      const reader = this.reader;
      await eachChild(reader, element, async (entry) => {
        if (entry.id !== TRACK_ENTRY) return;
        const track = {
          number: 0,
          type: "other",
          codecId: "",
          codecPrivate: null,
          language: "und",
          name: "",
          isDefault: true,
          defaultDuration: null,
          width: 0,
          height: 0,
          channels: 0,
          sampleRate: 0,
          bitDepth: 0,
          codecDelay: 0,
          seekPreRoll: 0,
          codec: null,
          mp4: null,
        };
        await eachChild(reader, entry, async (field) => {
          switch (field.id) {
            case TRACK_NUMBER:
              track.number = await elementUint(reader, field);
              break;
            case TRACK_TYPE:
              track.type = TRACK_TYPE_NAMES[await elementUint(reader, field)] || "other";
              break;
            case FLAG_DEFAULT:
              track.isDefault = (await elementUint(reader, field)) !== 0;
              break;
            case DEFAULT_DURATION:
              track.defaultDuration = await elementUint(reader, field);
              break;
            case CODEC_ID:
              track.codecId = await elementString(reader, field);
              break;
            case CODEC_PRIVATE:
              track.codecPrivate = (await elementBytes(reader, field)).slice();
              break;
            case CODEC_DELAY:
              track.codecDelay = await elementUint(reader, field);
              break;
            case SEEK_PRE_ROLL:
              track.seekPreRoll = await elementUint(reader, field);
              break;
            case TRACK_NAME:
              track.name = await elementString(reader, field);
              break;
            case LANGUAGE:
            case LANGUAGE_BCP47:
              track.language = (await elementString(reader, field)) || track.language;
              break;
            case VIDEO:
              await eachChild(reader, field, async (sub) => {
                if (sub.id === PIXEL_WIDTH) track.width = await elementUint(reader, sub);
                else if (sub.id === PIXEL_HEIGHT) track.height = await elementUint(reader, sub);
              });
              break;
            case AUDIO:
              await eachChild(reader, field, async (sub) => {
                if (sub.id === SAMPLING_FREQUENCY) track.sampleRate = Math.round(await elementFloat(reader, sub));
                else if (sub.id === OUTPUT_SAMPLING_FREQUENCY) track.outputRate = Math.round(await elementFloat(reader, sub));
                else if (sub.id === CHANNELS) track.channels = await elementUint(reader, sub);
                else if (sub.id === BIT_DEPTH) track.bitDepth = await elementUint(reader, sub);
              });
              break;
            default:
              break;
          }
        });
        if (!track.sampleRate && track.type === "audio") track.sampleRate = 48000;
        if (!track.channels && track.type === "audio") track.channels = 2;
        if (track.number) {
          this.tracks.push(track);
          this.byNumber.set(track.number, track);
        }
      });
    }

    async readCues(element) {
      const reader = this.reader;
      const scale = this.timecodeScale / 1e9;
      await eachChild(reader, element, async (point) => {
        if (point.id !== CUE_POINT) return;
        let time = 0;
        const positions = [];
        await eachChild(reader, point, async (field) => {
          if (field.id === CUE_TIME) {
            time = await elementUint(reader, field);
          } else if (field.id === CUE_TRACK_POSITIONS) {
            let trackNumber = 0;
            let clusterPosition = null;
            await eachChild(reader, field, async (sub) => {
              if (sub.id === CUE_TRACK) trackNumber = await elementUint(reader, sub);
              else if (sub.id === CUE_CLUSTER_POSITION) clusterPosition = await elementUint(reader, sub);
            });
            if (clusterPosition != null) positions.push({ trackNumber, clusterPosition });
          }
        });
        positions.forEach((entry) => {
          this.cues.push({
            time: time * scale,
            offset: this.segmentStart + entry.clusterPosition,
            trackNumber: entry.trackNumber,
          });
        });
      });
    }

    /* Matroska blocks carry presentation time in decode order, so how far
       the encoder reorders has to be known before any DTS can be derived.
       Reading it out of the SPS VUI means a full sequence-parameter-set
       parse (emulation prevention, scaling lists) to learn one number that
       the first cluster measures exactly: the largest count of later-decoded
       frames that display earlier. Frame duration comes from the same pass
       when the track header did not state one. */
    async probe() {
      const video = this.tracks.find((track) => track.type === "video");
      this.frameDuration = video && video.defaultDuration ? video.defaultDuration / 1e9 : 0;
      if (!video || this.firstCluster == null) return;

      const times = [];
      for await (const sample of this.rawSamples(this.firstCluster)) {
        if (sample.trackNumber !== video.number) continue;
        times.push(sample.pts);
        if (times.length >= 240) break;
      }
      if (times.length < 2) {
        if (!this.frameDuration) this.frameDuration = 1 / 25;
        return;
      }

      let depth = 0;
      for (let i = 0; i < times.length; i += 1) {
        let later = 0;
        for (let j = i + 1; j < times.length; j += 1) {
          if (times[j] < times[i]) later += 1;
        }
        if (later > depth) depth = later;
      }
      this.reorderDepth = Math.min(4, depth);

      if (!this.frameDuration) {
        const sorted = times.slice().sort((a, b) => a - b);
        const gaps = [];
        for (let i = 1; i < sorted.length; i += 1) {
          const gap = sorted[i] - sorted[i - 1];
          if (gap > 0) gaps.push(gap);
        }
        gaps.sort((a, b) => a - b);
        this.frameDuration = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 1 / 25;
      }
    }

    nominalDuration(sample) {
      const track = this.byNumber.get(sample.trackNumber);
      if (track && track.defaultDuration) return track.defaultDuration / 1e9;
      if (track && track.type === "audio") {
        // an AAC frame is exactly 1024 samples, which is the only sane guess
        // when nothing else said how long the last packet lasts
        return 1024 / (track.sampleRate || 48000);
      }
      if (track && track.type === "video") return this.frameDuration || 1 / 25;
      return 0;
    }

    async blockGroup(element) {
      const reader = this.reader;
      const scale = this.timecodeScale / 1e9;
      let block = null;
      let duration = null;
      let referenced = false;
      await eachChild(reader, element, async (field) => {
        if (field.id === BLOCK) {
          block = parseBlock(await reader.bytes(field.dataStart, field.size));
        } else if (field.id === BLOCK_DURATION) {
          duration = (await elementUint(reader, field)) * scale;
        } else if (field.id === REFERENCE_BLOCK) {
          referenced = true;
        }
      });
      // A BlockGroup has no keyframe flag: a block that references nothing
      // is the keyframe.
      return { block, duration, keyframe: !referenced };
    }

    frames(block, clusterTicks, duration, keyframe) {
      const track = this.byNumber.get(block.trackNumber);
      if (!track) return [];
      const pts = (clusterTicks + block.relative) * (this.timecodeScale / 1e9);
      const count = block.frames.length;
      let each = duration;
      if (count > 1) {
        if (track.defaultDuration) each = track.defaultDuration / 1e9;
        else if (duration != null) each = duration / count;
        else each = null;
      }
      const out = [];
      for (let index = 0; index < count; index += 1) {
        out.push({
          trackNumber: block.trackNumber,
          pts: pts + (each ? index * each : 0),
          duration: count > 1 ? each : duration,
          keyframe: track.type === "video" ? keyframe : true,
          data: block.frames[index],
        });
      }
      return out;
    }

    /* Every sample from `offset` onwards, in file order. Durations are only
       filled in where the file states them; samples() derives the rest. */
    async *rawSamples(offset) {
      const reader = this.reader;
      let position = offset;
      while (position != null && position >= 0 && position < reader.size) {
        const cluster = await readElement(reader, position);
        if (!cluster) return;
        if (cluster.id !== CLUSTER) {
          // Cues or Tags sitting after the last cluster; skip and stop when
          // the size is unknown, since there is nothing left to play.
          if (cluster.unknown) return;
          position = cluster.end;
          continue;
        }

        const limit = cluster.unknown ? reader.size : cluster.end;
        let next = limit;
        let inside = cluster.dataStart;
        let timecode = 0;
        while (inside < limit) {
          const child = await readElement(reader, inside);
          if (!child) {
            next = limit;
            break;
          }
          if (cluster.unknown && TOP_LEVEL.has(child.id)) {
            next = inside;
            break;
          }
          if (child.id === TIMECODE) {
            timecode = await elementUint(reader, child);
          } else if (child.id === SIMPLE_BLOCK) {
            const block = parseBlock(await reader.bytes(child.dataStart, child.size));
            if (block) yield* this.frames(block, timecode, null, block.keyframe);
          } else if (child.id === BLOCK_GROUP) {
            const group = await this.blockGroup(child);
            if (group.block) yield* this.frames(group.block, timecode, group.duration, group.keyframe);
          }
          if (child.unknown) {
            next = limit;
            break;
          }
          inside = child.end;
        }
        position = next > position ? next : limit;
      }
    }

    /* Where the cluster covering `seconds` starts. Cues answer it in one
       lookup; without them the cluster headers are walked, which is the
       price a file muxed without an index charges for seeking. */
    async locate(seconds) {
      if (!seconds || seconds <= 0 || this.firstCluster == null) return this.firstCluster;
      if (this.cues.length) {
        let best = this.cues[0];
        for (const cue of this.cues) {
          if (cue.time <= seconds + 0.001) best = cue;
          else break;
        }
        return best.offset;
      }

      const scale = this.timecodeScale / 1e9;
      let position = this.firstCluster;
      let best = this.firstCluster;
      while (position != null && position < this.reader.size) {
        const cluster = await readElement(this.reader, position);
        if (!cluster || cluster.id !== CLUSTER) break;
        let timecode = 0;
        let end = cluster.unknown ? null : cluster.end;
        let inside = cluster.dataStart;
        const limit = cluster.unknown ? this.reader.size : cluster.end;
        while (inside < limit) {
          const child = await readElement(this.reader, inside);
          if (!child) break;
          if (cluster.unknown && TOP_LEVEL.has(child.id)) {
            end = inside;
            break;
          }
          if (child.id === TIMECODE) {
            timecode = await elementUint(this.reader, child);
            if (!cluster.unknown) break;
          }
          if (child.unknown) break;
          inside = child.end;
        }
        if (timecode * scale > seconds) break;
        best = position;
        if (end == null || end <= position) break;
        position = end;
      }
      return best;
    }

    /* Samples from the cluster covering `startSeconds`, with every duration
       filled in. A sample waits in the queue until the next sample of its
       own track fixes its length; the cap stops a track that simply stops
       appearing from blocking the ones that keep going. */
    async *samples(startSeconds) {
      const offset = await this.locate(startSeconds || 0);
      if (offset == null) return;
      const queue = [];
      const pending = new Map();

      const release = (force) => {
        const out = [];
        while (queue.length && (queue[0].duration != null || force || queue.length > 64)) {
          const head = queue.shift();
          if (head.duration == null || head.duration <= 0) head.duration = this.nominalDuration(head);
          out.push(head);
        }
        return out;
      };

      for await (const sample of this.rawSamples(offset)) {
        const previous = pending.get(sample.trackNumber);
        if (previous && previous.duration == null) {
          const gap = sample.pts - previous.pts;
          if (gap > 0) previous.duration = gap;
        }
        pending.set(sample.trackNumber, sample);
        queue.push(sample);
        for (const ready of release(false)) yield ready;
      }
      for (const ready of release(true)) yield ready;
    }

    /* Track ids are assigned from the selection, not from the Matroska
       track numbers, so the init segment and the fragments always agree. */
    selection(choice) {
      const video = this.trackByNumber(choice && choice.video);
      const audio = this.trackByNumber(choice && choice.audio);
      const out = [];
      if (video) out.push({ track: video, id: 1, timescale: 90000 });
      if (audio) out.push({ track: audio, id: video ? 2 : 1, timescale: audio.sampleRate || 48000 });
      return out;
    }

    initSegment(choice) {
      const chosen = this.selection(choice);
      if (!chosen.length) throw new Error("no track selected");
      return Mp4.init(
        chosen.map((entry) =>
          Object.assign({}, entry.track, { id: entry.id, timescale: entry.timescale })
        )
      );
    }
  }

  /* Turns the sample stream into moof/mdat fragments.
   *
   * DTS is the interesting part. Matroska stores presentation time only, so
   * for a stream with B-frames the decode timeline has to be rebuilt: with a
   * constant frame duration and a reorder depth of D, decode time is simply
   * the frame index on that grid, and every presentation time is shifted
   * forward by D frames so no composition offset goes negative and no
   * baseMediaDecodeTime goes below zero. The cost is a constant presentation
   * shift of D frame durations (about 80 ms at 24 fps), which is well inside
   * the tolerance of any seek. Streams without reorder (D = 0) keep their own
   * timestamps exactly.
   */
  class Fragmenter {
    constructor(demux, options) {
      const config = options || {};
      this.demux = demux;
      this.target = config.targetDuration || 4;
      this.byteCap = config.byteCap || 12 * 1024 * 1024;
      this.chosen = demux.selection({ video: config.video, audio: config.audio });
      this.videoTrack = this.chosen.length && this.chosen[0].track.type === "video" ? this.chosen[0].track : null;
      this.audioTrack = (this.chosen.find((entry) => entry.track.type === "audio") || {}).track || null;
      this.reset(config.sequence || 1);
    }

    reset(sequence) {
      this.sequence = sequence || this.sequence || 1;
      this.state = new Map();
      for (const entry of this.chosen) {
        this.state.set(entry.track.number, {
          id: entry.id,
          timescale: entry.timescale,
          track: entry.track,
          samples: [],
          pending: null,
          base: null,
          index: 0,
          lastDts: -1,
          firstDts: null,
          frameTicks: Math.max(1, Math.round((this.demux.frameDuration || 1 / 25) * entry.timescale)),
          delay: entry.track.type === "video" ? this.demux.reorderDepth : 0,
        });
      }
      this.bytes = 0;
    }

    times(state, sample) {
      const ticks = Math.round(sample.pts * state.timescale);
      if (state.delay === 0) {
        let dts = ticks;
        if (dts <= state.lastDts) dts = state.lastDts + 1;
        state.lastDts = dts;
        return { dts, pts: Math.max(dts, ticks) };
      }
      if (state.base == null) {
        state.base = ticks;
        state.index = 0;
      }
      const dts = state.base + state.index * state.frameTicks;
      state.index += 1;
      state.lastDts = dts;
      return { dts, pts: Math.max(dts, ticks + state.delay * state.frameTicks) };
    }

    commit(state, until) {
      const held = state.pending;
      if (!held) return;
      state.pending = null;
      let duration = until != null ? until - held.dts : null;
      if (duration == null || duration <= 0) {
        duration = Math.max(1, Math.round((held.seconds || 0) * state.timescale));
      }
      held.duration = duration;
      state.samples.push(held);
      this.bytes += held.data.length;
    }

    push(sample) {
      const state = this.state.get(sample.trackNumber);
      if (!state) return null;

      const stamped = this.times(state, sample);
      const entry = {
        dts: stamped.dts,
        pts: stamped.pts,
        duration: 0,
        keyframe: sample.keyframe,
        data: sample.data,
        seconds: sample.duration || this.demux.nominalDuration(sample),
      };
      this.commit(state, stamped.dts);
      if (state.firstDts == null) state.firstDts = stamped.dts;

      let fragment = null;
      if (this.shouldClose(sample, state, stamped.dts)) fragment = this.emit();
      state.pending = entry;
      return fragment;
    }

    shouldClose(sample, state, dts) {
      if (!this.bytes) return false;
      if (this.bytes >= this.byteCap) return true;
      const primary = this.videoTrack || this.audioTrack;
      if (!primary) return false;
      const lead = this.state.get(primary.number);
      if (!lead || lead.firstDts == null) return false;
      const elapsed = (lead.lastDts - lead.firstDts) / lead.timescale;
      if (elapsed < this.target) return false;
      // A fragment has to start on a keyframe, so only a video keyframe may
      // close one; audio-only streams can break anywhere.
      if (!this.videoTrack) return true;
      return sample.trackNumber === this.videoTrack.number && sample.keyframe;
    }

    emit() {
      const runs = [];
      for (const entry of this.chosen) {
        const state = this.state.get(entry.track.number);
        if (state && state.samples.length) runs.push({ id: state.id, samples: state.samples });
      }
      if (!runs.length) return null;
      const fragment = Mp4.fragment(this.sequence, runs);
      this.sequence += 1;
      for (const entry of this.chosen) {
        const state = this.state.get(entry.track.number);
        if (state) {
          state.samples = [];
          state.firstDts = null;
        }
      }
      this.bytes = 0;
      return fragment;
    }

    flush() {
      for (const entry of this.chosen) {
        const state = this.state.get(entry.track.number);
        if (state) this.commit(state, null);
      }
      return this.emit();
    }
  }

  // =====================================================================
  // Public surface
  // =====================================================================
  async function open(source, options) {
    if (!source || typeof source.read !== "function") {
      throw new Error("a source with size and read(offset, length) is required");
    }
    const reader = new Reader(source, options && options.readAhead);
    return new Demuxer(reader).load();
  }

  function codecString(track) {
    return track && track.codec ? track.codec : null;
  }

  function mimeType(video, audio) {
    const codecs = [];
    if (video && video.codec) codecs.push(video.codec);
    if (audio && audio.codec) codecs.push(audio.codec);
    const container = video ? "video/mp4" : "audio/mp4";
    return `${container}; codecs="${codecs.join(",")}"`;
  }

  const MkvRemux = {
    open,
    Demuxer,
    Fragmenter,
    Mp4,
    codecString,
    mimeType,
    parseBlock,
    mapCodec,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = MkvRemux;
  else if (typeof self !== "undefined") self.MkvRemux = MkvRemux;
  else if (typeof window !== "undefined") window.MkvRemux = MkvRemux;
})();
