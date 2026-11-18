#!/usr/bin/env python3
"""samples.py - turn two drum recordings (a kick and a snare, single hits) into Drum Chapel's Acoustic kit samples
(effects/drumchapel/samples_data.h).

usage: samples.py KICK SNARE [-o samples_data.h] [--kick-end MS] [--snare-end MS] [--wav DIR]

The recordings are the user's own bounces (possibly of a commercial drum instrument) and the repository is public,
so the output is git-ignored and must never be committed; nothing in the repository carries a sample of them.
Without the output the reference, the kernel check and the image build still work: the Acoustic kit then plays the
Punch kit's synthesised kick and snare (drumchapel.h).

Each file (AIFF or WAV, 16/24/32-bit integer PCM, any rate, mono or stereo) becomes one sample:
  mono      the mean of its channels;
  48 kHz    resampled with a fixed windowed sinc (Kaiser, 64 taps a phase, cut off at 0.97 x the lower Nyquist),
            in float64 with numpy: the same input gives the same words every time;
  start     the hit's onset is the first sample at 30 % of the file's peak; the sample starts at the quietest
            sample in the millisecond before it (a near-zero point, so there is no step at the start);
  end       the first hit only: the high band (first difference) is followed in 10 ms windows from 50 ms after
            the onset, and the sample ends 5 ms before the first window that is 6 dB over the quietest one so far
            (the next hit, or anything else that starts there), or at --kick-end / --snare-end (ms after the
            start); the last 30 % fade out on a raised cosine, so it ends at exactly 0;
  level     both scaled to the same peak (full scale) and rounded to 16 bits.
The header holds the two sample arrays (int16) and their lengths; drumchapel.c packs them two to a word.
"""
import os
import struct
import sys

import numpy as np

RATE = 48000
ONSET = 0.3                 # the onset: this fraction of the file's peak
RISE_DB = 6.0               # the next event: this much over the quietest 10 ms so far
GUARD_MS = 5.0              # end this long before it
SKIP_MS = 50.0              # the hit's own decay is not searched before this
FADE = 0.3                  # the raised-cosine fade-out, a fraction of the kept length
TAPS = 32                   # the resampler's half-width, input samples


def _ext80(b):
    e = struct.unpack('>H', b[:2])[0] & 0x7FFF
    return int.from_bytes(b[2:10], 'big') * 2.0 ** (e - 16383 - 63)


def read_audio(path):
    """(rate, float64 array frames x channels in -1..1) from an AIFF/AIFC (uncompressed) or WAV file."""
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
        raise ValueError(f'{path}: not an AIFF or WAV file')
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


def resample(x, rate):
    """x (mono, float64) at `rate` -> RATE, a fixed polyphase windowed sinc."""
    if rate == RATE:
        return x.copy()
    from fractions import Fraction
    q = Fraction(int(round(rate)), RATE)                  # input samples an output sample: up / down
    up, down = q.denominator, q.numerator                 # output n at input n x down / up
    cut = 0.97 * min(1.0, RATE / rate)                    # x the input's Nyquist
    k = np.arange(-TAPS + 1, TAPS + 1)
    ph = np.arange(up) / up                               # the fractional position of each phase
    t = ph[:, None] - k[None, :]                          # (input sample i0 + k) is at distance t
    wv = np.i0(8.6 * np.sqrt(np.clip(1 - (t / TAPS) ** 2, 0, None))) / np.i0(8.6)     # Kaiser, beta 8.6
    h = cut * np.sinc(cut * t) * wv                       # up x 2 TAPS
    n = int(len(x) * RATE // rate)
    pos = np.arange(n) * down
    i0, p = pos // up, pos % up
    xp = np.concatenate([np.zeros(TAPS), x, np.zeros(TAPS + 1)])
    idx = i0[:, None] + k[None, :] + TAPS
    return np.einsum('ij,ij->i', xp[idx], h[p])


def cut_points(x, end_ms=None):
    """(start, end, onset, the event found) in samples of x (48 kHz): see the docstring."""
    pk = np.max(np.abs(x))
    onset = int(np.argmax(np.abs(x) >= ONSET * pk))
    lo = max(0, onset - RATE // 1000)
    start = lo + int(np.argmin(np.abs(x[lo:onset + 1])))
    if end_ms is not None:
        return start, start + int(round(end_ms * RATE / 1000)), onset, None
    d = np.diff(x, prepend=x[0])
    w, hop = RATE // 100, RATE // 1000
    env = [10 * np.log10(np.mean(d[i:i + w] ** 2) + 1e-15) for i in range(onset, len(x) - w, hop)]
    s = int(SKIP_MS)
    lowest = env[s] if len(env) > s else 0.0
    for i in range(s, len(env)):
        lowest = min(lowest, env[i])
        if env[i] > lowest + RISE_DB:
            ev = onset + i * hop
            return start, ev - int(GUARD_MS * RATE / 1000), onset, ev
    return start, len(x), onset, None


def convert(path, end_ms=None):
    rate, a = read_audio(path)
    x = resample(a.mean(axis=1), rate)
    start, end, onset, ev = cut_points(x, end_ms)
    y = x[start:end].copy()
    nf = int(len(y) * FADE)
    y[len(y) - nf:] *= 0.5 * (1 + np.cos(np.pi * (np.arange(1, nf + 1) / nf)))
    y *= 32767.0 / np.max(np.abs(y))
    q = np.clip(np.round(y), -32768, 32767).astype(np.int64)
    info = dict(file=os.path.basename(path), rate=rate, start_ms=start / RATE * 1000, onset_ms=onset / RATE * 1000,
                event_ms=None if ev is None else ev / RATE * 1000, end_ms=end / RATE * 1000, n=len(q))
    return [int(v) for v in q], info


def header(kick, snare):
    def arr(name, v):
        rows = [', '.join(str(s) for s in v[k:k + 24]) for k in range(0, len(v), 24)]
        return f'static const short {name}[{len(v)}] = {{\n    ' + ',\n    '.join(rows) + '\n};\n'
    return ('/* samples_data.h - written by samples.py from local drum recordings (the Acoustic kit).\n'
            ' * NEVER COMMIT THIS FILE (it is git-ignored): the samples are the recordings\'. */\n'
            f'#define DC_SAMPLE_RATE {RATE}\n#define DC_SAMPLE_KICK_N {len(kick)}\n#define DC_SAMPLE_SNARE_N {len(snare)}\n'
            + arr('DC_SAMPLE_KICK', kick) + arr('DC_SAMPLE_SNARE', snare))


def write_wav(path, q):
    data = struct.pack(f'<{len(q)}h', *q)
    open(path, 'wb').write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' +
                           struct.pack('<IHHIIHH', 16, 1, 1, RATE, RATE * 2, 2, 16) + b'data' + struct.pack('<I', len(data)) + data)


def main():
    a = sys.argv[1:]
    pos = [v for i, v in enumerate(a) if not v.startswith('-') and (i == 0 or a[i - 1] not in ('-o', '--kick-end', '--snare-end', '--wav'))]
    if len(pos) != 2:
        sys.exit(__doc__)
    out = a[a.index('-o') + 1] if '-o' in a else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'samples_data.h')
    ends = [float(a[a.index(o) + 1]) if o in a else None for o in ('--kick-end', '--snare-end')]
    res = [convert(p, e) for p, e in zip(pos, ends)]
    open(out, 'w').write(header(res[0][0], res[1][0]))
    for name, (q, i) in zip(('kick', 'snare'), res):
        ev = f'next event at {i["event_ms"]:.1f} ms' if i['event_ms'] is not None else 'end given' if i['end_ms'] else 'no next event'
        print(f'samples.py: {name}: {i["file"]} ({i["rate"]:g} Hz): onset {i["onset_ms"]:.1f} ms, start {i["start_ms"]:.2f} ms, '
              f'{ev}, end {i["end_ms"]:.1f} ms: {i["n"]} samples ({i["n"] / RATE * 1000:.0f} ms at {RATE} Hz)')
    n = len(res[0][0]) + (len(res[0][0]) & 1) + len(res[1][0])
    print(f'samples.py: {(n + 1) // 2} words (two 16-bit samples a word) -> {out}')
    if '--wav' in a:
        d = a[a.index('--wav') + 1]
        os.makedirs(d, exist_ok=True)
        for name, (q, _) in zip(('kick', 'snare'), res):
            write_wav(os.path.join(d, f'acoustic_{name}.wav'), q)


if __name__ == '__main__':
    main()
