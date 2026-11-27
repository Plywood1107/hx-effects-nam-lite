#!/usr/bin/env python3
"""input_level.py - read the host probe's report (the probe image's "Probe" block) from a recording of the unit's output.

usage:
  input_level.py decode REC.wav [--channel N] [--volts V]     decode every frame in a recording
  input_level.py listen [--seconds S] [--device D] [--channel N] [--volts V] [--save REC.wav]
                                                              record from an audio input, then decode (needs the
                                                              sounddevice package in the venv)
  input_level.py selftest                                     the C reference's output through a simulated analog
                                                              path (gain, 44.1 kHz, noise, hum, DC), decoded

The Probe (effects/hostprobe, Mode Report) sends a frame every 3.02 s: a 6 kHz pilot, 34 words as 2 kHz / 4 kHz
tones of 2.5 ms a bit, then silence. Each frame carries the input meter's last 1-second window (peak, sum of
squares, sum), the host's call-list entry and instance struct, and the SDRAM memory test (hostprobe.h). Record the
pedal's output at 48 kHz (44.1 kHz works too), with the input gain set so the burst does not clip.

--volts V: the AC RMS voltage of the test sine, measured at the pedal's input with the cable plugged in. Prints the
dBu that reaches 0 dBFS, as NAM defines its input_level_dbu: the dBu of the RMS voltage of a sine whose peak is at
0 dBFS (NAM's calibration tutorial, https://neural-amp-modeler.readthedocs.io/en/latest/tutorials/calibration.html:
play "a sine wave with 1kHz frequency and 0dBFS peak amplitude", "measure the RMS voltage across its tip and
sleeve", dBu = 20 log10(V_RMS / 0.7746)). So:

    dBu at 0 dBFS = 20 log10(V / 0.7746) - L,   L = the sine's peak in dBFS = 20 log10(sqrt(2) x RMS)

L is taken from the window's RMS (DC removed), which a little noise moves far less than the peak; the peak's own
figure is printed beside it, and the two agree for a clean sine.
"""
import math
import os
import struct
import sys

import numpy as np

SYM48, NPILOT, NWORDS, NGAP = 120, 80, 34, 40
NBITS = 32 * NWORDS
NSYM = NPILOT + NBITS + NGAP
SYNC, MAGIC, PAT = 0x9E3779B9, 0x50524232, (0xA5C3F00D, 0x5A3C0FF2)
F0, F1, FP = 2000.0, 4000.0, 6000.0


def read_wav(path):
    """(samples as float64 [n, channels], sample rate): PCM 16/24/32-bit or float32/64."""
    data = open(path, 'rb').read()
    assert data[:4] == b'RIFF' and data[8:12] == b'WAVE', f'{path}: not a WAV file'
    pos, fmt, body = 12, None, None
    while pos + 8 <= len(data):
        cid, n = data[pos:pos + 4], struct.unpack('<I', data[pos + 4:pos + 8])[0]
        if cid == b'fmt ':
            fmt = struct.unpack('<HHIIHH', data[pos + 8:pos + 24])
            if fmt[0] == 0xFFFE:                                  # extensible: the subformat's first two bytes
                fmt = (struct.unpack('<H', data[pos + 32:pos + 34])[0],) + fmt[1:]
        elif cid == b'data':
            body = data[pos + 8:pos + 8 + n]
        pos += 8 + n + (n & 1)
    assert fmt and body is not None, f'{path}: no fmt or data chunk'
    tag, ch, rate, _, _, bits = fmt
    if tag == 3:
        x = np.frombuffer(body, dtype='<f4' if bits == 32 else '<f8').astype(np.float64)
    elif bits == 16:
        x = np.frombuffer(body, dtype='<i2') / 32768.0
    elif bits == 24:
        b = np.frombuffer(body[:len(body) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif bits == 32:
        x = np.frombuffer(body, dtype='<i4') / 2147483648.0
    else:
        raise SystemExit(f'{path}: {bits}-bit PCM not supported')
    return x[:len(x) // ch * ch].reshape(-1, ch), rate


def write_wav(path, x, rate):
    x = np.clip(np.asarray(x, dtype=np.float64), -1, 1)
    pcm = (x * 32767).astype('<i2').tobytes()
    ch = 1 if x.ndim == 1 else x.shape[1]
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt ' +
                struct.pack('<IHHIIHH', 16, 1, ch, rate, rate * 2 * ch, 2 * ch, 16) + b'data' + struct.pack('<I', len(pcm)) + pcm)


class Tones:
    """Running sums of x e^(-j w t) at each tone, so a window's energy at a tone is |S(b) - S(a)|^2."""

    def __init__(self, x, rate):
        t = np.arange(len(x)) / rate
        self.c = {f: np.concatenate([[0], np.cumsum(x * np.exp(-2j * np.pi * f * t))]) for f in (F0, F1, FP)}
        self.n = len(x)

    def power(self, f, a, b):
        a, b = np.clip(a, 0, self.n), np.clip(b, 0, self.n)
        return np.abs(self.c[f][b] - self.c[f][a]) ** 2


def bits_at(tn, start, sps, nbits):
    """The bits of nbits symbols from sample `start` (float), each judged on its middle 60%, and their margins."""
    k = np.arange(nbits)
    a = np.round(start + (k + 0.2) * sps).astype(np.int64)
    b = np.round(start + (k + 0.8) * sps).astype(np.int64)
    p0, p1 = tn.power(F0, a, b), tn.power(F1, a, b)
    return (p1 > p0).astype(np.uint8), np.abs(p1 - p0) / (p1 + p0 + 1e-30)


def words_of(bits):
    w = []
    for i in range(0, len(bits) - 31, 32):
        v = 0
        for bit in bits[i:i + 32]:
            v = v << 1 | int(bit)
        w.append(v)
    return w


def decode(x, rate):
    """Every frame found in mono signal x: a list of 34-word lists, in order."""
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean()
    sps = SYM48 * rate / 48000.0
    L = int(round(sps))
    tn = Tones(x, rate)
    hop = max(1, L // 8)
    starts = np.arange(0, len(x) - L, hop)
    pp, p0, p1 = (tn.power(f, starts, starts + L) for f in (FP, F0, F1))
    if not len(starts) or pp.max() <= 0:
        return []
    pilot = (pp > 4 * (p0 + p1)) & (pp > 0.05 * pp.max())
    frames, i = [], 0
    while i < len(pilot):
        if not pilot[i]:
            i += 1
            continue
        j = i
        while j < len(pilot) and pilot[j]:
            j += 1
        if (j - i) * hop < 0.5 * NPILOT * sps:                   # too short for a pilot
            i = j
            continue
        edge = starts[j - 1] + L                                 # about where the pilot stops
        best = None                                              # the sync word, up to 4 bits wrong (an echo, a
        for d in range(-L, L + 1, max(1, L // 40)):              # phone's codec); the checksum guards the frame
            bits, m = bits_at(tn, edge + d, sps, 32)
            wrong = bin(words_of(bits)[0] ^ SYNC).count('1')
            if wrong <= 4:
                score = (-wrong, float(m.mean()))
                if best is None or score > best[0]:
                    best = (score, edge + d)
        if best is not None:
            bits, _ = bits_at(tn, best[1], sps, NBITS)
            w = words_of(bits)
            if len(w) == NWORDS and w[0] == SYNC and w[33] == sum(w[1:33]) & 0xFFFFFFFF:
                frames.append(w)
        i = j + int(NBITS * sps / hop)
    return frames


def f32(u):
    return struct.unpack('<f', struct.pack('<I', u))[0]


def meter(w):
    """(peak dBFS, RMS dBFS, the sine's peak from the RMS in dBFS, DC) of a frame's window, or None before one."""
    n = w[31]
    if not w[7] or not n:
        return None
    pk, sq, sm = f32(w[4]), f32(w[5]), f32(w[6])
    dc = sm / n
    var = max(sq / n - dc * dc, 0.0)
    db = lambda v: 20 * math.log10(v) if v > 0 else -math.inf
    rms = math.sqrt(var)
    return db(pk), db(rms), db(math.sqrt(2) * rms), dc


def dbu(volts):
    return 20 * math.log10(volts / 0.7746)


def report(frames, volts=None, out=print):
    if not frames:
        out('no frames found: is the Probe first in the path, Mode on Report, and its burst reaching the recording '
            'unclipped?')
        return []
    results = []
    for w in frames:
        if w[1] != MAGIC:
            out(f'frame with version {w[1]:#010x}: not this tool\'s (expected {MAGIC:#010x})')
            continue
        m = meter(w)
        head = f'frame {w[2]:4d} (call {w[3]}, window {w[7]})'
        if m is None:
            out(f'{head}: no complete window yet')
        else:
            pk, rms, sine, dc = m
            line = f'{head}: peak {pk:7.2f} dBFS, RMS {rms:7.2f} dBFS (a sine of peak {sine:7.2f} dBFS), DC {dc:+.6f}'
            if volts:
                cal = dbu(volts) - sine
                results.append(cal)
                line += f' -> {cal:6.2f} dBu at 0 dBFS (from the peak: {dbu(volts) - pk:6.2f})'
            out(line)
    w = frames[-1]
    st = w[14:30]
    a, e = st[6], st[7]
    out(f'host: call-list entry {" ".join(f"{v:#x}" for v in w[10:14])}')
    out(f'      instance struct {" ".join(f"{v:#x}" for v in st)}')
    size = (e - a) & 0xFFFFFFFF
    if w[8]:
        out(f'SDRAM: words 6..7 = {a:#x}..{e:#x}, {size} words (asked for {w[30]}): the memory test wrote its two '
            f'words; {w[9]} mismatches since')
    else:
        out(f'SDRAM: words 6..7 = {a:#x}..{e:#x} ({size} words): not the block asked for ({w[30]} words), left alone')
    if results:
        out(f'dBu at 0 dBFS over {len(results)} frames: mean {np.mean(results):.2f}, spread {np.ptp(results):.2f} dB')
    return results


def pick_channel(x, rate, ch):
    if x.shape[1] == 1:
        return x[:, 0]
    if ch is not None:
        return x[:, ch]
    tn = [Tones(x[:, c], rate) for c in range(x.shape[1])]
    e = [abs(t.c[FP][-1]) + abs(t.c[F0][-1]) + abs(t.c[F1][-1]) for t in tn]
    return x[:, int(np.argmax(e))]


def opt(a, name, kind=str, default=None):
    return kind(a[a.index(name) + 1]) if name in a else default


def selftest():
    """The reference's output (a sine at three levels into the Probe) through an analog-ish path, decoded."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'effects', 'common'))
    import ctypes
    import kernel_rig as kr
    ref = kr.Reference(type('S', (), dict(name='hostprobe', order=['time', 'mode', 'level']))())
    st = ref.new()
    entry = (ctypes.c_uint32 * 4)(0x1, 0x2, 0x3, 0x4)
    inst = (ctypes.c_uint32 * 16)(*([0] * 6 + [0x300000, 0x310000] + [0] * 8))
    ref.lib.hostprobe_set_host(st, entry, inst)
    frame = NSYM * SYM48
    levels = (-20.0, -12.0, -6.0)
    n = 16 * ((frame * 9) // 16)
    t = np.arange(n) / 48000.0
    seg = n // 3
    amp = np.repeat([10 ** (lv / 20) for lv in levels], [seg, seg, n - 2 * seg])
    sine = (amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    out = np.zeros(n)
    kn = dict(time=0.5, mode=0, level=0.25)
    for b in range(0, n, 16):
        y = ref.process(st, kn, [float(v) for v in sine[b:b + 16]])
        out[b:b + 16] = [kr.f32(struct.unpack('<f', struct.pack('<I', v))[0]) for v in y]
    rng = np.random.default_rng(3)
    rec = 0.6 * out + 0.0003 * rng.standard_normal(n) + 0.002 * np.sin(2 * np.pi * 50 * t) + 0.01
    rec = np.concatenate([np.zeros(12345), rec])
    t44 = np.arange(int(len(rec) * 44100 / 48000)) / 44100.0
    rec44 = np.interp(t44, np.arange(len(rec)) / 48000.0 * (1 + 40e-6), rec)   # 44.1 kHz, the clocks 40 ppm apart
    ok = True
    for name, sig, rate in (('48 kHz', rec, 48000), ('44.1 kHz, 40 ppm', rec44, 44100)):
        frames = decode(sig, rate)
        got = [meter(w) for w in frames if meter(w)]
        print(f'[{name}] {len(frames)} frames decoded')
        if len(frames) < 7:
            ok = False
            print('  too few frames')
        for w, m in zip(frames, (meter(w) for w in frames)):
            if not m:
                continue
            k = min(int((w[7] - 0.5) * 48000 // seg), 2)
            win0 = (w[7] - 1) * 48000
            if (win0 // seg) != ((win0 + 47999) // seg):          # a window across a level change
                continue
            if abs(m[2] - levels[k]) > 0.01:
                ok = False
                print(f'  frame {w[2]}: sine {m[2]:.3f} dBFS, sent {levels[k]} dBFS')
        if got:
            print(f'  levels read: {sorted({round(m[2], 2) for m in got})}')
        if frames and (frames[-1][8] != 1 or frames[-1][9] != 0 or frames[-1][20:22] != [0x300000, 0x310000]):
            ok = False
            print('  host words wrong')
    v = 0.7746 * 10 ** ((12.0 - 6.0) / 20)                       # a sine at -6 dBFS that reads 12 dBu at 0 dBFS
    m = meter(next(w for w in reversed(decode(rec, 48000)) if meter(w)))
    cal = dbu(v) - m[2]
    print(f'  --volts {v:.4f} with the -6 dBFS frames: {cal:.3f} dBu at 0 dBFS (made to be 12.000)')
    ok &= abs(cal - 12.0) < 0.01
    print('SELFTEST OK' if ok else 'SELFTEST FAILED')
    return ok


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        sys.exit(__doc__)
    volts, ch = opt(a, '--volts', float), opt(a, '--channel', int)
    if a[0] == 'selftest':
        sys.exit(0 if selftest() else 1)
    if a[0] == 'decode':
        path = a[1]
        if not path.lower().endswith('.wav'):            # a phone's voice memo (.m4a) and the like: macOS converts it
            import subprocess
            import tempfile
            wav = os.path.join(tempfile.mkdtemp(), 'rec.wav')
            r = subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16', path, wav], capture_output=True, text=True)
            if r.returncode:
                sys.exit(f'input_level.py: could not convert {path} (afconvert): {r.stderr.strip()}')
            path = wav
        x, rate = read_wav(path)
    elif a[0] == 'listen':
        try:
            import sounddevice as sd
        except ImportError:
            sys.exit('input_level.py listen needs sounddevice (.venv/bin/pip install sounddevice); or record the '
                     'pedal\'s output at 48 kHz in any app and use: input_level.py decode REC.wav')
        secs, rate = opt(a, '--seconds', float, 10.0), 48000
        dev = opt(a, '--device')
        dev = int(dev) if dev and dev.isdigit() else dev
        info = sd.query_devices(dev, 'input')
        nch = min(2, int(info['max_input_channels']))
        print(f'recording {secs:g} s from "{info["name"]}" ({nch} channel(s), 48 kHz)...')
        x = sd.rec(int(secs * rate), samplerate=rate, channels=nch, dtype='float32', device=dev)
        sd.wait()
        x = x.astype(np.float64)
        if '--save' in a:
            write_wav(opt(a, '--save'), x, rate)
        peak = np.abs(x).max()
        if peak > 0.98:
            print(f'warning: the recording peaks at {peak:.3f}: turn the interface\'s input gain down')
    else:
        sys.exit(__doc__)
    report(decode(pick_channel(x, rate, ch), rate), volts)


if __name__ == '__main__':
    main()
