#!/usr/bin/env python3
"""samples.py - turn five drum hits (kick, snare, closed hat, tom, open hat) into Drum Chapel's Acoustic kit samples
(effects/drumchapel/samples_data.h): 8-bit mu-law at 24 kHz.

usage: samples.py KICK SNARE HAT TOM OPENHAT [-o samples_data.h] [--end VOICE=MS ...] [--wav DIR] [--note TEXT]

Each argument is one hit: a file, or several mixed ("in.wav+0.5*sub.wav+0.6*oh.wav": each file times its gain,
summed), or "-" for none: that voice keeps its synthesised definition (drumchapel.c). Without samples_data.h at all
the whole kit is synthesised (the Punch kit's kick and snare, Acoustic's own hat, tom and open hat), and the
reference, the kernel check and the image build still work.

A hit (AIFF or WAV, 16/24/32-bit integer PCM, any rate, mono or stereo; FLAC through ffmpeg first):
  mono      each file the mean of its channels, at 48 kHz (a fixed windowed sinc: Kaiser, 64 taps a phase, cut off
            at 0.97 x the lower Nyquist, float64 with numpy: the same input gives the same bytes every time), then
            the files summed with their gains;
  start     the onset is the first sample at 30 % of the peak; the hit starts at the quietest sample in the
            millisecond before it (a near-zero point, so there is no step at the start);
  end       the voice's length (END_MS below, or --end), or sooner if another hit follows in the file: the high band
            (first difference) is followed in 10 ms windows from 50 ms after the onset, and the hit ends 5 ms before
            the first window 6 dB over the quietest one so far; the last 30 % fade out on a raised cosine to 0;
  24 kHz    the same resampler, 48 -> 24 kHz;
  level     scaled to full scale (32,767) and coded as 8-bit mu-law (G.711, the bits inverted): each sample the code
            whose value (drumchapel_ulaw) is nearest.
The header holds each voice's codes and count (and --note's text in its comment: where the hits came from); drumchapel.c packs them four to a word. How loud each voice plays
against the others is drumchapel.c's (its sampled gains), not the files'.
"""
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

RATE = 48000                # the unit's rate: where the hits are cut
OUT_RATE = 24000            # what is stored
ONSET = 0.3                 # the onset: this fraction of the hit's peak
RISE_DB = 6.0               # the next event: this much over the quietest 10 ms so far
GUARD_MS = 5.0              # end this long before it
SKIP_MS = 50.0              # the hit's own decay is not searched before this
FADE = 0.3                  # the raised-cosine fade-out, a fraction of the kept length
TAPS = 32                   # the resampler's half-width, input samples
VOICES = ('KICK', 'SNARE', 'HAT', 'TOM', 'OPEN')          # = drumchapel.h DEF_*
END_MS = dict(KICK=350, SNARE=400, HAT=120, TOM=500, OPEN=800)   # 52,080 bytes: 13,020 words


def _ext80(b):
    e = struct.unpack('>H', b[:2])[0] & 0x7FFF
    return int.from_bytes(b[2:10], 'big') * 2.0 ** (e - 16383 - 63)


def read_audio(path):
    """(rate, float64 array frames x channels in -1..1) from an AIFF/AIFC (uncompressed), WAV or FLAC (ffmpeg) file."""
    if path.lower().endswith('.flac'):
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, 'x.wav')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-c:a', 'pcm_s24le', w], check=True)
            return read_audio(w)
    b = open(path, 'rb').read()
    if b[:4] == b'FORM' and b[8:12] in (b'AIFF', b'AIFC'):
        i, comm, ssnd, big = 12, None, None, True
        while i + 8 <= len(b):
            cid, n = b[i:i + 4], struct.unpack('>I', b[i + 4:i + 8])[0]
            if cid == b'COMM':
                comm = b[i + 8:i + 8 + n]
            elif cid == b'SSND':
                ssnd = b[i + 8:i + 8 + n]
            i += 8 + n + (n & 1)
        ch, nf, bits = struct.unpack('>hIh', comm[:8])
        rate = _ext80(comm[8:18])
        if b[8:12] == b'AIFC' and comm[18:22] not in (b'NONE', b'twos'):
            raise ValueError(f'{path}: compressed AIFC ({comm[18:22]!r})')
        off = struct.unpack('>I', ssnd[:4])[0]
        raw = ssnd[8 + off:]
    elif b[:4] == b'RIFF' and b[8:12] == b'WAVE':
        i, fmt, raw, big = 12, None, None, False
        while i + 8 <= len(b):
            cid, n = b[i:i + 4], struct.unpack('<I', b[i + 4:i + 8])[0]
            if cid == b'fmt ':
                fmt = b[i + 8:i + 8 + n]
            elif cid == b'data':
                raw = b[i + 8:i + 8 + n]
            i += 8 + n + (n & 1)
        tag, ch, rate, _, _, bits = struct.unpack('<HHIIHH', fmt[:16])
        if tag not in (1, 0xFFFE):
            raise ValueError(f'{path}: not integer PCM')
        nf = len(raw) // (ch * bits // 8)
    else:
        raise ValueError(f'{path}: not an AIFF, WAV or FLAC file')
    if bits not in (16, 24, 32):
        raise ValueError(f'{path}: {bits}-bit samples (16, 24 or 32 only)')
    w = bits // 8
    a = np.frombuffer(raw[:nf * ch * w], np.uint8).reshape(-1, w).astype(np.int64)
    if not big:
        a = a[:, ::-1]
    v = np.zeros(len(a), np.int64)
    for k in range(w):
        v = v << 8 | a[:, k]
    v = np.where(v >= 1 << (bits - 1), v - (1 << bits), v)
    return rate, v.reshape(nf, ch) / float(1 << (bits - 1))


def resample(x, rate, to=RATE):
    """x (mono, float64) at `rate` -> `to`, a fixed polyphase windowed sinc."""
    if rate == to:
        return x.copy()
    from fractions import Fraction
    q = Fraction(int(round(rate)), to)                    # input samples an output sample: up / down
    up, down = q.denominator, q.numerator                 # output n at input n x down / up
    cut = 0.97 * min(1.0, to / rate)                      # x the input's Nyquist
    k = np.arange(-TAPS + 1, TAPS + 1)
    ph = np.arange(up) / up                               # the fractional position of each phase
    t = ph[:, None] - k[None, :]                          # (input sample i0 + k) is at distance t
    wv = np.i0(8.6 * np.sqrt(np.clip(1 - (t / TAPS) ** 2, 0, None))) / np.i0(8.6)     # Kaiser, beta 8.6
    h = cut * np.sinc(cut * t) * wv                       # up x 2 TAPS
    n = int(len(x) * to // rate)
    pos = np.arange(n) * down
    i0, p = pos // up, pos % up
    xp = np.concatenate([np.zeros(TAPS), x, np.zeros(TAPS + 1)])
    idx = i0[:, None] + k[None, :] + TAPS
    return np.einsum('ij,ij->i', xp[idx], h[p])


def cut_points(x, end_ms):
    """(start, end, onset, the next event or None) in samples of x (48 kHz): see the docstring."""
    pk = np.max(np.abs(x))
    onset = int(np.argmax(np.abs(x) >= ONSET * pk))
    lo = max(0, onset - RATE // 1000)
    start = lo + int(np.argmin(np.abs(x[lo:onset + 1])))
    end = min(len(x), start + int(round(end_ms * RATE / 1000)))
    d = np.diff(x, prepend=x[0])
    w, hop = RATE // 100, RATE // 1000
    env = [10 * np.log10(np.mean(d[i:i + w] ** 2) + 1e-15) for i in range(onset, min(len(x), end + w) - w, hop)]
    s = int(SKIP_MS)
    lowest = env[s] if len(env) > s else 0.0
    for i in range(s, len(env)):
        lowest = min(lowest, env[i])
        if env[i] > lowest + RISE_DB:
            ev = onset + i * hop
            return start, min(end, ev - int(GUARD_MS * RATE / 1000)), onset, ev
    return start, end, onset, None


def ulaw_levels():
    """The value (x 32768) each of the 256 codes decodes to, as drumchapel_ulaw() does."""
    out = []
    for u in range(256):
        v = ~u & 0xFF
        t = (((v & 0x0F) << 3) + 0x84) << ((v & 0x70) >> 4)
        out.append(0x84 - t if v & 0x80 else t - 0x84)
    return np.array(out, dtype=np.float64)


def ulaw_encode(x):
    """Each sample (x 32768) to the code that decodes nearest to it (the lower code on a tie)."""
    lv = ulaw_levels()
    x = np.asarray(x, dtype=np.float64)
    return np.argmin(np.abs(x[:, None] - lv[None, :]), axis=1).astype(np.uint8)


def parse_mix(spec):
    """'a.wav+0.5*b.wav' -> [(path, gain)]."""
    out = []
    for term in spec.split('+'):
        g, _, p = term.rpartition('*')
        out.append((p, float(g) if g else 1.0))
    return out


def mixed(spec):
    """A hit's files at 48 kHz, mono, summed with their gains."""
    parts = []
    for p, g in parse_mix(spec):
        rate, a = read_audio(p)
        parts.append(g * resample(a.mean(axis=1), rate))
    y = np.zeros(max(len(x) for x in parts))
    for x in parts:
        y[:len(x)] += x
    return y


def convert(spec, end_ms):
    """A hit -> (its mu-law codes at 24 kHz, info)."""
    x = mixed(spec)
    start, end, onset, ev = cut_points(x, end_ms)
    y = x[start:end].copy()
    nf = int(len(y) * FADE)
    y[len(y) - nf:] *= 0.5 * (1 + np.cos(np.pi * (np.arange(1, nf + 1) / nf)))
    z = resample(y, RATE, OUT_RATE)
    z *= 32767.0 / np.max(np.abs(z))
    codes = ulaw_encode(z)
    info = dict(spec=spec, start_ms=start / RATE * 1000, onset_ms=onset / RATE * 1000,
                event_ms=None if ev is None else ev / RATE * 1000, ms=(end - start) / RATE * 1000, n=len(codes))
    return [int(c) for c in codes], info


def header(hits, note=''):
    def arr(name, v):
        rows = [', '.join(str(s) for s in v[k:k + 24]) for k in range(0, len(v), 24)]
        return f'static const unsigned char {name}[{len(v)}] = {{\n    ' + ',\n    '.join(rows) + '\n};\n'
    s = ('/* samples_data.h - written by samples.py (the Acoustic kit): each voice\'s hit, 8-bit mu-law (G.711, bits\n'
         ' * inverted) at 24 kHz.' + (f'\n * {note}' if note else '') + ' */\n'
         f'#define DC_SAMPLE_RATE {OUT_RATE}\n')
    for v in VOICES:
        if hits.get(v):
            s += f'#define DC_SAMPLE_{v}_N {len(hits[v])}\n' + arr(f'DC_SAMPLE_{v}', hits[v])
    return s


def write_wav(path, q, rate=OUT_RATE):
    data = struct.pack(f'<{len(q)}h', *q)
    open(path, 'wb').write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' +
                           struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', len(data)) + data)


def main():
    a = sys.argv[1:]
    opts = ('-o', '--end', '--wav', '--note')
    pos = [v for i, v in enumerate(a) if not (v.startswith('-') and v != '-') and (i == 0 or a[i - 1] not in opts)]
    if len(pos) != len(VOICES):
        sys.exit(__doc__)
    out = a[a.index('-o') + 1] if '-o' in a else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples_data.h')
    ends = dict(END_MS)
    for i, v in enumerate(a):
        if v == '--end':
            k, ms = a[i + 1].split('=')
            ends[k.upper()] = float(ms)
    hits, total = {}, 0
    for v, spec in zip(VOICES, pos):
        if spec == '-':
            print(f'samples.py: {v.lower()}: none (synthesised)')
            continue
        hits[v], i = convert(spec, ends[v])
        total += len(hits[v])
        ev = f', the next event at {i["event_ms"]:.1f} ms' if i['event_ms'] is not None else ''
        print(f'samples.py: {v.lower()}: onset {i["onset_ms"]:.1f} ms, start {i["start_ms"]:.2f} ms{ev}: {i["ms"]:.0f} ms, '
              f'{i["n"]} bytes')
    open(out, 'w').write(header(hits, a[a.index('--note') + 1] if '--note' in a else ''))
    print(f'samples.py: {total} bytes, {(total + 3) // 4} words (four mu-law bytes a word) -> {out}')
    if '--wav' in a:
        d = a[a.index('--wav') + 1]
        os.makedirs(d, exist_ok=True)
        lv = ulaw_levels()
        for v, c in hits.items():
            write_wav(os.path.join(d, f'acoustic_{v.lower()}.wav'), [int(lv[k]) for k in c])


if __name__ == '__main__':
    main()
