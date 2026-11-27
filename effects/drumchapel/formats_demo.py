#!/usr/bin/env python3
"""formats_demo.py - the Acoustic kit's kick and snare in the sample formats under consideration, for listening.

usage: formats_demo.py [OUTDIR]     (default build/groove_renders/formats)

From samples_data.h (16-bit, 48 kHz, as the kit plays them now) it makes the same two samples as 8-bit mu-law at
48 kHz and as 8-bit mu-law at 24 kHz (samples.py's resampler at 24 kHz), writes them into effects/out/dc_formats.h,
and builds and runs render_formats.c, which plays each through the C reference's drumchapel_ulaw() and
drumchapel_interp() and writes the .wav files (each hit alone, and a two-bar beat at 120 BPM) and the error of each
against the 16-bit sample.
"""
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import samples  # noqa: E402

_LEVELS = None


def ulaw_levels():
    """The value (x 32768) each of the 256 codes decodes to, as drumchapel_ulaw() does."""
    out = []
    for u in range(256):
        v = ~u & 0xFF
        t = (((v & 0x0F) << 3) + 0x84) << ((v & 0x70) >> 4)
        out.append(0x84 - t if v & 0x80 else t - 0x84)
    return np.array(out, dtype=np.float64)


def ulaw_encode(x):
    """Each sample (x 32768) to the code that decodes nearest to it."""
    global _LEVELS
    if _LEVELS is None:
        _LEVELS = ulaw_levels()
    x = np.asarray(x, dtype=np.float64)
    return np.argmin(np.abs(x[:, None] - _LEVELS[None, :]), axis=1).astype(np.uint8)


def read_header(path):
    s = open(path).read()
    arr = {}
    for name in ('KICK', 'SNARE'):
        m = re.search(r'DC_SAMPLE_%s\[\d+\] = \{([^}]*)\}' % name, s)
        arr[name] = np.array([int(v) for v in m.group(1).replace('\n', ' ').split(',') if v.strip()], dtype=np.float64)
    return arr


def c_bytes(name, b):
    rows = [', '.join(str(int(v)) for v in b[i:i + 24]) for i in range(0, len(b), 24)]
    return f'#define {name}_N {len(b)}\nstatic const unsigned char {name}[{len(b)}] = {{\n    ' + ',\n    '.join(rows) + '\n};\n'


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'groove_renders', 'formats')
    os.makedirs(out, exist_ok=True)
    h = os.path.join(HERE, 'samples_data.h')
    if not os.path.isfile(h):
        sys.exit('formats_demo.py: no samples_data.h (run samples.py first)')
    arr = read_header(h)
    parts = ['/* dc_formats.h - written by formats_demo.py */\n']
    saved = samples.RATE
    for name, x in arr.items():
        parts.append(c_bytes(f'U48_{name}', ulaw_encode(x)))
        samples.RATE = 24000
        try:
            x24 = samples.resample(x / 32768.0, 48000) * 32768.0
        finally:
            samples.RATE = saved
        parts.append(c_bytes(f'U24_{name}', ulaw_encode(np.clip(np.round(x24), -32768, 32767))))
    os.makedirs(os.path.join(ROOT, 'effects', 'out'), exist_ok=True)
    open(os.path.join(ROOT, 'effects', 'out', 'dc_formats.h'), 'w').write(''.join(parts))
    r = subprocess.run(['make', '-s', '-C', os.path.join(ROOT, 'effects'), 'out/dc_formats'], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'formats_demo.py: build failed:\n{r.stderr}')
    subprocess.run([os.path.join(ROOT, 'effects', 'out', 'dc_formats'), out], check=True)


if __name__ == '__main__':
    main()
