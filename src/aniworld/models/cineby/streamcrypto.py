"""Decrypt cineby's ``enc=2`` (STREAMCRYPTO) source payloads.

cineby / the vidking player fetch the playable sources from
``api.wingsdatabase.com/cdn/sources-with-title?...&enc=2&seed=<seed>`` and
decrypt the response client-side. This is a straight port of that routine, so
the stream can be resolved over plain HTTP without driving a headless browser.

The scheme: base64url-decode the response, XOR it with a keystream derived from
the per-request ``seed`` (30 s TTL, from ``/seed?mediaId=<id>``) and the numeric
media id, verify the 4-byte ``mvm1`` magic header, and read the rest as UTF-8
JSON (``{"sources": [{quality, url}], "subtitles": [...]}``).
"""

import base64
import json

_MASK = 0xFFFFFFFF
_GOLDEN = 2654435769  # 0x9E3779B9
_MAGIC = bytes([109, 118, 109, 49])  # "mvm1"
# 16 constants (the SHA-256 round constants), indexed by i & 15.
_U = [
    1116352408, 1899447441, 3049323471, 3921009573,
    961987163, 1508970993, 2453635748, 2870763221,
    3624381080, 310598401, 607225278, 1426881987,
    1925078388, 2162078206, 2614888103, 3248222580,
]


def _imul(a, b):
    return (a * b) & _MASK


def _f(e):
    e &= _MASK
    e ^= e >> 16
    e = _imul(e, 2246822507)
    e ^= e >> 13
    e = _imul(e, 3266489909)
    e ^= e >> 16
    return e & _MASK


def _rotl(e, t):
    e &= _MASK
    t &= 31
    return e if t == 0 else ((e << t) | (e >> (32 - t))) & _MASK


def _fnv_f(text):
    t = 2166136261
    for ch in text:
        t = _imul(t ^ ord(ch), 16777619)
    return _f(t)


def _key_schedule(seed, media_id):
    n = _f(_fnv_f(seed) ^ _f((media_id & _MASK) ^ _GOLDEN))
    state = {}  # sparse 61-slot array
    for e in range(8):
        # the guard c(e) = (e*(e+1) & 1) == 0 is always true
        idx = n % 61
        n = _rotl((n + _GOLDEN) & _MASK, 7 + (e & 7))
        state[idx] = (n ^ _f(n)) & _MASK
        n = _f((n + idx) & _MASK)
    acc = _f(2779096485 ^ n)
    return state, acc


def _keystream(seed, media_id, length):
    state, acc = _key_schedule(seed, media_id)
    out = bytearray(length)
    pos = 0
    counter = 0
    while pos < length:
        a = acc
        i = a % 61
        mask = _MASK if (i in state) else 0
        low = state.get(i, 0) & _MASK
        n = (low ^ _imul(_GOLDEN, counter + 1)) & _MASK
        c = ((a ^ n) | (a & n & mask)) & _MASK
        c = (_rotl((c + a) & _MASK, i & 31) ^ _rotl(a, _imul(i, 7) & 31)) & _MASK
        acc = _f((c + _GOLDEN) & _MASK)
        state[i] = acc & _MASK
        counter += 1
        val = acc
        out[pos] = val & 255
        pos += 1
        if pos < length:
            out[pos] = (val >> 8) & 255
            pos += 1
        if pos < length:
            out[pos] = (val >> 16) & 255
            pos += 1
        if pos < length:
            out[pos] = (val >> 24) & 255
            pos += 1
    return out


def _b64url_decode(text):
    text = text.strip().replace("-", "+").replace("_", "/")
    text += "=" * (-len(text) % 4)
    return base64.b64decode(text)


def decrypt_sources(encrypted, seed, media_id):
    """Decrypt an ``enc=2`` payload into its parsed JSON dict.

    Raises ValueError if the magic header doesn't match (wrong seed / tampered).
    """
    data = bytearray(_b64url_decode(encrypted))
    ks = _keystream(seed, int(media_id), len(data))
    for i in range(len(data)):
        data[i] ^= ks[i]
    if bytes(data[: len(_MAGIC)]) != _MAGIC:
        raise ValueError("STREAMCRYPTO: bad seed or tampered payload")
    return json.loads(bytes(data[len(_MAGIC):]).decode("utf-8"))
