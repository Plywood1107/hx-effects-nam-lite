#!/usr/bin/env python3
"""Tuner note names with sharps (A#) instead of flats (Bb), for HX Effects 3.80.0.

How the stock tuner draws a note (fsTunerView, 2026-11-18):
  - the letter is TEXT: a table of 12 string pointers at 0x280a43c0, indexed by note mod 12 from C
    (C, D, D, E, E, F, G, G, A, A, B, B: the flat spelling; read at 0x280896c4 and 0x28089962);
  - the accidental is an IMAGE, Tuner_Flat (Entry 7 index 0x1eb, 32x88, 15-bit RGB, white on black; its pixels are
    Entry 8 item 0x1eb), shown where the 12-byte flag table at 0x280a43b4 has a 1 (C# D# F# G# A#, the same five
    notes in either spelling, so the flags stay as they are).
This makes the five accidentals use the letter below (C, C, D, D, E, F, F, G, G, A, A, B) and redraws Tuner_Flat as
a '#' in the same style (4-pixel uprights like the flat's stem, grey anti-aliasing). Tuner_FlatOff is blank and stays.

On the HX Effects the sign the user sees is NOT Tuner_Flat (2026-11-21, on the unit: F with a flat after the letter
change). The tuner also writes to a footswitch scribble strip (strip state structs of 0x276 bytes at 0x28122e78,
setters at 0x2808f2a4 text / 0x2808f564 icon / 0x2808f5b4 position, all `cmp r0,#5`: strips 0..5). For a flagged
note it sets icon (set 10, index 11) at x 0x4d, y 5 (0x2808990e). 0x2808e904 maps (set, index) to a 1-bit bitmap:
set 10's table is at 0x28090170, and item 11 is at 0x280986d8: bytes w, h (6, 19), then pages of 8 rows, one byte per
column, bit 7 the top row (0x28099700 draws it). That bitmap is now a 6x19 '#'. Same size, in place; nothing else in
the firmware points at it (one reference, the table). The Tuner_Flat redraw stays (harmless, and right should any
view use it).

usage: .venv/bin/python tools/tuner_sharps.py BASE.hxf     writes build/<base>_Sharps.hxf and checks it
       (build_all.py applies patch_e0/patch_e8 itself unless --flat-tuner)
"""
import hashlib
import os
import struct
import subprocess
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

STOCK = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
LETTERS = 0x280A43C0                     # 12 x char*, note mod 12 from C
FLAGS = 0x280A43B4                       # 12 bytes: 1 = draw the accidental image
FLAT_IMG, W, H = 0x1EB, 32, 88           # Tuner_Flat
STOCK_LETTERS = 'CDDEEFGGAABB'
SHARP_LETTERS = 'CCDDEFFGGAAB'
STOCK_FLAGS = bytes([0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0])
STRIP_ICON = 0x280986D8                  # scribble-strip icon (set 10, index 11): the flat the HX Effects shows
STRIP_FLAT = bytes.fromhex('0613ff0001010000ff800001c638e04080000000')
STRIP_SHARP_ROWS = ('......', '.#..#.', '.#..#.', '.#..#.', '.#..#.', '.#..#.', '######', '.#..#.', '.#..#.', '.#..#.',
                    '.#..#.', '.#..#.', '######', '.#..#.', '.#..#.', '.#..#.', '.#..#.', '.#..#.', '......')


def strip_bitmap(rows):
    """Rows of '#'/'.' as the strip's 1-bit bitmap: w, h, then per 8-row page one byte per column, bit 7 on top."""
    h, w = len(rows), len(rows[0])
    out = bytearray([w, h])
    for pg in range((h + 7) // 8):
        for x in range(w):
            out.append(sum(0x80 >> k for k in range(8) if pg * 8 + k < h and rows[pg * 8 + k][x] == '#'))
    return bytes(out)


STRIP_SHARP = strip_bitmap(STRIP_SHARP_ROWS)


def _letters(e0, segs):
    fo = lambda v, n=4: pa._e0_vaddr_to_foff(segs, v, n)
    ptrs = list(struct.unpack_from('<12I', e0, fo(LETTERS, 48)))
    text = ''.join(chr(e0[fo(p)]) for p in ptrs)
    return ptrs, text


def patch_e0(e0):
    """Entry 0 (swapped bytes) with the letter table in sharp spelling."""
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments_any(e0)
    fo = lambda v, n=4: pa._e0_vaddr_to_foff(segs, v, n)
    ptrs, text = _letters(e0, segs)
    assert text == STOCK_LETTERS, f'unexpected tuner letters {text!r}'
    assert bytes(e0[fo(FLAGS, 12): fo(FLAGS, 12) + 12]) == STOCK_FLAGS, 'unexpected tuner flag table'
    by_letter = {text[i]: ptrs[i] for i in range(12)}
    struct.pack_into('<12I', e0, fo(LETTERS, 48), *[by_letter[c] for c in SHARP_LETTERS])
    o = fo(STRIP_ICON, len(STRIP_FLAT))
    assert bytes(e0[o:o + len(STRIP_FLAT)]) == STRIP_FLAT, 'the scribble strip\'s flat icon is not the stock one'
    assert len(STRIP_SHARP) == len(STRIP_FLAT)
    e0[o:o + len(STRIP_SHARP)] = STRIP_SHARP
    return bytes(l6ia.fix_internal_crcs(bytes(e0)))


def sharp_pixels():
    """A '#' in Tuner_Flat's box: 15-bit grey levels (white on black), drawn at 8x and averaged (anti-aliasing)."""
    S = 8
    yy, xx = np.mgrid[0:H * S, 0:W * S] / S + 0.5 / S
    ink = np.zeros_like(xx, dtype=bool)
    for x0 in (8.0, 19.0):                                   # two uprights, 4 px like the flat's stem, leaning a little
        lean = (44.0 - yy) * 0.06
        ink |= (xx >= x0 + lean) & (xx < x0 + 4.0 + lean) & (yy >= 6) & (yy < 84)
    for yc in (34.0, 58.0):                                  # two bars rising to the right, 6 px thick
        yl = yc + (16.0 - xx) * 0.30
        ink |= (xx >= 2) & (xx < 30) & (yy >= yl - 3.0) & (yy < yl + 3.0)
    cov = ink.reshape(H, S, W, S).mean(axis=(1, 3))
    g = np.rint(cov * 31).astype(np.uint16)
    return (g << 10) | (g << 5) | g


def patch_e8(e8):
    """Entry 8 (swapped bytes) with Tuner_Flat's pixels replaced by the sharp."""
    e8 = bytearray(e8)
    ln, off = struct.unpack_from('<2I', e8, 0x18 + 8 * FLAT_IMG)
    assert ln == W * H * 2, f'Tuner_Flat is {ln} bytes, not {W}x{H}x2'
    old = np.frombuffer(bytes(e8[off:off + ln]), '<u2')
    assert old.max() == 0x7FFF and old[0] == 0x7FFF, 'Tuner_Flat is not the stock white flat'
    e8[off:off + ln] = sharp_pixels().astype('<u2').tobytes()
    return bytes(e8), off, ln


def check_image(old_arc, new_arc, e8_span):
    """(ok, messages): only Entries 0 and 8 differ; Entry 0 only in the letter table (and its header); Entry 8 only in
    the flat's pixels; the letters read back in sharp spelling."""
    msgs, ok = [], True
    po, pn = l6ia.parse(old_arc), l6ia.parse(new_arc)
    raw = lambda img, p, k: img[p[k]['payload_off']: p[k]['payload_off'] + p[k]['payload_len']]
    diff = [k for k in range(len(po)) if raw(old_arc, po, k) != raw(new_arc, pn, k)]
    o0, n0 = bytes(pa.get_entry_swapped(old_arc, 0)), bytes(pa.get_entry_swapped(new_arc, 0))
    segs = pa._parse_e0_segments_any(bytearray(n0))
    t = pa._e0_vaddr_to_foff(segs, LETTERS, 48)
    ic = pa._e0_vaddr_to_foff(segs, STRIP_ICON, len(STRIP_SHARP))
    d0 = [i for i in range(len(o0)) if o0[i] != n0[i]] if len(o0) == len(n0) else None
    o8, n8 = bytes(pa.get_entry_swapped(old_arc, 8)), bytes(pa.get_entry_swapped(new_arc, 8))
    off, ln = e8_span
    d8 = [i for i in range(len(o8)) if o8[i] != n8[i]] if len(o8) == len(n8) else None
    for c, m in ((diff == [0, 8], 'only Entries 0 and 8 differ'),
                 (d0 is not None and set(d0) <= set(range(0, 0x34)) | set(range(t, t + 48)) | set(range(ic, ic + len(STRIP_SHARP))),
                  'Entry 0: only the tuner letter table, the strip\'s flat icon (and the header)'),
                 (n0[ic:ic + len(STRIP_SHARP)] == STRIP_SHARP, 'the scribble strip\'s flat icon is now a #'),
                 (_letters(n0, segs)[1] == SHARP_LETTERS, f'tuner letters now {SHARP_LETTERS} (C C# D D# E F F# G G# A A# B)'),
                 (d8 is not None and d8 and set(d8) <= set(range(off, off + ln)), 'Entry 8: only Tuner_Flat\'s pixels (now a #)')):
        msgs.append(('  ok   ' if c else '  FAIL ') + m)
        ok &= bool(c)
    return ok, msgs


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        sys.exit(__doc__)
    base = os.path.abspath(sys.argv[1])
    arc, _ = pa.load_l6ia_from_any(base)
    assert pa.select_device(arc) is pa.EFFECTS_DSP, 'not an HX Effects image'
    e0n = patch_e0(bytes(pa.get_entry_swapped(arc, 0)))
    e8n, off, ln = patch_e8(bytes(pa.get_entry_swapped(arc, 8)))
    out_arc, _, _ = l6ia.rebuild_archive(arc, {0: e0n, 8: e8n})
    stem = os.path.splitext(os.path.basename(base))[0]
    image = os.path.join(ROOT, 'build', f'{stem}_Sharps.l6ia')
    out = os.path.join(ROOT, 'build', f'{stem}_Sharps.hxf')
    open(image, 'wb').write(out_arc)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'hxf.py'), 'pack', image, out, '--donor', STOCK],
                   check=True, capture_output=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'l6ia_verify.py'), image], capture_output=True, text=True)
    ok, msgs = check_image(arc, pa.load_l6ia_from_any(out)[0], (off, ln))
    ok &= 'ALL OK' in r.stdout
    print(('  ok   ' if 'ALL OK' in r.stdout else '  FAIL ') + 'every archive checksum holds (l6ia_verify)')
    print('\n'.join(msgs))
    print(f'\n{os.path.relpath(out, ROOT)}\nMD5 {hashlib.md5(open(out, "rb").read()).hexdigest()}\n' + ('ALL OK' if ok else 'PROBLEMS'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
