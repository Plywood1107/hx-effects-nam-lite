#!/usr/bin/env python3
"""recipe.py - the setup page's recipe: how to turn the stock HX Effects 3.80.0 firmware into a tested build.

Line 6's firmware can't be shared, so the page (web/) never ships a firmware file. It ships a recipe instead: the
build's inner archive (the .l6ia inside the .hxf) as a list of COPY runs from the user's own stock archive and ADD
runs of new bytes (our code, data and the changed checksums). Applying it to the stock archive gives the build's
archive exactly; the page then repacks it as an .hxf the way tools/hxf.py does and checks the MD5s pinned here.

Format (little-endian), the whole thing zlib-compressed:
    'HXR1'
    16 bytes   MD5 of the stock archive          (the page refuses any other file)
    16 bytes   MD5 of the result archive
    16 bytes   MD5 of the result .hxf             (as tools/hxf.py pack --donor stock writes it)
    u32        result archive size
    u32        op count, then per op:
               u8 0 = COPY, u32 stock offset, u32 length
               u8 1 = ADD,  u32 length, then that many bytes

usage: .venv/bin/python tools/recipe.py make  BUILD.hxf OUT      (the page reads web/recipe-nam.bin, recipe-amps.bin, recipe-full.bin)   (stock from firmware/)
       .venv/bin/python tools/recipe.py apply RECIPE STOCK.hxf OUT.hxf        (what the page does, for testing)
"""
import hashlib
import os
import struct
import sys
import zlib

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import hxf  # noqa: E402

STOCK = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
KEY = 16          # bytes that must match to start a COPY
MIN_COPY = 32     # a shorter match is cheaper as ADD


def archive(path):
    raw = open(path, 'rb').read()
    return zlib.decompress([b for c, p, s, b in hxf._chunks(raw) if c == b'data'][0])


def _keys(buf, step):
    """A 64-bit hash of the KEY bytes at every `step`-aligned offset."""
    n = (len(buf) - KEY) // step + 1
    a = np.frombuffer(buf, np.uint8)
    idx = np.arange(n, dtype=np.int64) * step
    h = np.zeros(n, np.uint64)
    for j in range(0, KEY, 8):
        w = np.zeros(n, np.uint64)
        for b in range(8):
            w |= a[idx + j + b].astype(np.uint64) << np.uint64(8 * b)
        h = (h ^ w) * np.uint64(0x9E3779B97F4A7C15)
    return h


def diff(old, new):
    """[(0, src, n) | (1, bytes)] that rebuild `new` from `old`."""
    ok = _keys(old, 4)
    order = np.argsort(ok, kind='stable')
    sk = ok[order]
    nk = _keys(new, 4)
    pos = np.searchsorted(sk, nk)
    hit = (pos < len(sk)) & (sk[np.minimum(pos, len(sk) - 1)] == nk)
    cand = np.where(hit, order[np.minimum(pos, len(sk) - 1)] * 4, -1)

    def extend(s, d):
        n, step = 0, 4096
        while d + n < len(new) and s + n < len(old):
            m = min(step, len(new) - d - n, len(old) - s - n)
            if old[s + n:s + n + m] == new[d + n:d + n + m]:
                n += m
                continue
            if step == 1:
                break
            step //= 2
        return n

    ops, lit, d, expect = [], bytearray(), 0, None
    while d < len(new):
        best = (0, 0)
        if expect is not None and expect < len(old):
            best = (extend(expect, d), expect)
        if best[0] < MIN_COPY and d % 4 == 0 and d // 4 < len(cand) and cand[d // 4] >= 0:
            s = int(cand[d // 4])
            n = extend(s, d)
            if n > best[0]:
                best = (n, s)
        if best[0] >= MIN_COPY:
            if lit:
                ops.append((1, bytes(lit)))
                lit = bytearray()
            ops.append((0, best[1], best[0]))
            d += best[0]
            expect = best[1] + best[0]
        else:
            step = 4 - d % 4
            lit += new[d:d + step]
            d += step
            expect = None if expect is None else expect + step
    if lit:
        ops.append((1, bytes(lit)))
    return ops


def make(build, out):
    old, new = archive(STOCK), archive(build)
    ops = diff(old, new)
    body = bytearray(b'HXR1')
    body += hashlib.md5(old).digest() + hashlib.md5(new).digest()
    body += hashlib.md5(open(build, 'rb').read()).digest()
    body += struct.pack('<II', len(new), len(ops))
    for op in ops:
        body += struct.pack('<BII', 0, op[1], op[2]) if op[0] == 0 else struct.pack('<BI', 1, len(op[1])) + op[1]
    open(out, 'wb').write(zlib.compress(bytes(body), 9))
    added = sum(len(o[1]) for o in ops if o[0] == 1)
    print(f'{len(ops)} runs; {added:,} new bytes of {len(new):,}; recipe {os.path.getsize(out):,} bytes -> {os.path.relpath(out, ROOT)}')
    return out


def apply(recipe, stock_hxf, out_hxf):
    r = zlib.decompress(open(recipe, 'rb').read())
    assert r[:4] == b'HXR1', 'not a recipe'
    m_old, m_new, m_hxf = r[4:20], r[20:36], r[36:52]
    size, nops = struct.unpack_from('<II', r, 52)
    old = archive(stock_hxf)
    assert hashlib.md5(old).digest() == m_old, 'not the stock HX Effects 3.80.0 firmware'
    out, p = bytearray(), 60
    for _ in range(nops):
        if r[p] == 0:
            s, n = struct.unpack_from('<II', r, p + 1)
            out += old[s:s + n]
            p += 9
        else:
            n, = struct.unpack_from('<I', r, p + 1)
            out += r[p + 5:p + 5 + n]
            p += 5 + n
    assert len(out) == size and hashlib.md5(out).digest() == m_new, 'result archive MD5 mismatch'
    tmp = out_hxf + '.l6ia'
    open(tmp, 'wb').write(out)
    hxf.pack(tmp, out_hxf, stock_hxf)
    os.remove(tmp)
    ok = hashlib.md5(open(out_hxf, 'rb').read()).digest() == m_hxf
    print(('ok: ' if ok else 'MISMATCH: ') + f'{out_hxf} MD5 {hashlib.md5(open(out_hxf, "rb").read()).hexdigest()}')
    return ok


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['make'] and len(a) in (2, 3):
        make(os.path.abspath(a[1]), os.path.abspath(a[2]) if len(a) == 3 else os.path.join(ROOT, 'web', 'recipe.bin'))
    elif a[:1] == ['apply'] and len(a) == 4:
        sys.exit(0 if apply(*a[1:]) else 1)
    else:
        sys.exit(__doc__)
