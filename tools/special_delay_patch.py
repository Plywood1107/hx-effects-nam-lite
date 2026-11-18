#!/usr/bin/env python3
"""Take Mono Ratchet's name off the app's hard-coded list of "special" delays, so the block that took over its
identity (Drum Chapel) is bypassed by its footswitch like any other delay.

The HX Effects app (3.80.0) singles out a few delays by Entry 3 name index: Tesselator (0x776/0xc07), Poly Sustain
(0x6f0), 0x660, Ratchet (Mono 0x789, Stereo 0xc0b) and, at two of the sites, 0x8a7/0xad5/0xaee. Three routines
compare against Mono Ratchet's index with `movw rX, #0x789; cmp ...` (0x280bd8de, 0x280f41c0, 0x280f612c; a fourth
movw #0x789 at 0x280ca8d2 is a log line number, left alone). Clearing the model's followEnable metadata and its Entry
0 Table 2 flag (build_all.py, 2026-11-18) did not change what the unit does: the block still ran when off. This makes
those three compares look for 0xffff, which no model has, so Mono Ratchet's identity is an ordinary delay; Stereo
Ratchet and the others stay special.

That alone did not do it either (2026-11-18, on the unit): the browser item's first byte is the block TYPE (0x08 an
ordinary delay; 0x18 Ratchet, Tesselator, Poly Sustain, Feedback Sim, Poly Pitch; 0x17 the synth generators; 0x16
loopers; 0x13..0x15 IRs), which the takeover keeps. This also makes Mono Ratchet's item type 0x08. Both are needed:
the routine at 0x280bd8a4 treats type 8 as ordinary unless the name is on the special list.

usage: .venv/bin/python tools/special_delay_patch.py BASE.hxf
Writes build/<base>_RatchetPlain.hxf and checks it: only those three instructions (and Entry 0's header CRC) differ
from the base, and every archive checksum holds (tools/l6ia_verify.py).
"""
import hashlib
import os
import struct
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import capstone  # noqa: E402
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

STOCK = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
RATCHET_MONO = 0x789
NOBODY = 0xffff
SPECIAL_TYPE, DELAY_TYPE = 0x18, 0x08            # browser item byte 0: the block type (0x18 Ratchet/Tesselator/Poly Sustain)
SITES = (0x280BD8DE, 0x280F41C0, 0x280F612C)    # movw rX, #0x789 followed by cmp


def patch_e0(e0):
    """Entry 0 (swapped bytes) with the three compares retargeted; returns (new bytes, [(va, file offset)])."""
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments_any(e0)
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    done = []
    for va in SITES:
        o = pa._e0_vaddr_to_foff(segs, va, 8)
        rd, imm = pa._decode_thumb_movw(bytes(e0[o:o + 4]))
        nxt = list(md.disasm(bytes(e0[o + 4:o + 6]), va + 4))
        assert imm == RATCHET_MONO and nxt and nxt[0].mnemonic == 'cmp' and nxt[0].op_str.endswith(f'r{rd}'), \
            f'unexpected code at {va:#x}'
        e0[o:o + 4] = pa._encode_thumb_movw(rd, NOBODY)
        done.append((va, o))
    A = pa.EFFECTS_E0                                 # the browser item's block type: special -> ordinary delay
    u = lambda va: struct.unpack_from('<I', e0, pa._e0_vaddr_to_foff(segs, va, 4))[0]
    items = []
    for slot in range(52):
        lp, lc = u(A.BLIST_PTR_TAB + 4 * slot), u(A.BLIST_CNT_TAB + 4 * slot)
        for k in range(lc if lp else 0):
            if u(lp + 48 * k + 4) == RATCHET_MONO:
                o = pa._e0_vaddr_to_foff(segs, lp + 48 * k, 4)
                assert e0[o] == SPECIAL_TYPE, f'browser item type {e0[o]:#x}'
                e0[o] = DELAY_TYPE
                items.append((lp + 48 * k, o))
    assert len(items) == 1, items
    done += [(va, o) for va, o in items]
    return bytes(l6ia.fix_internal_crcs(bytes(e0))), done


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        sys.exit(__doc__)
    base = os.path.abspath(sys.argv[1])
    arc, _ = pa.load_l6ia_from_any(base)
    assert pa.select_device(arc) is pa.EFFECTS_DSP, 'not an HX Effects image'
    e0 = bytes(pa.get_entry_swapped(arc, 0))
    e0n, done = patch_e0(e0)
    out_arc, _, _ = l6ia.rebuild_archive(arc, {0: e0n})
    stem = os.path.splitext(os.path.basename(base))[0]
    image = os.path.join(ROOT, 'build', f'{stem}_RatchetPlain.l6ia')
    out = os.path.join(ROOT, 'build', f'{stem}_RatchetPlain.hxf')
    open(image, 'wb').write(out_arc)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'hxf.py'), 'pack', image, out, '--donor', STOCK],
                   check=True, capture_output=True)

    ok = True

    def check(c, msg):
        nonlocal ok
        print(('  ok   ' if c else '  FAIL ') + msg)
        ok &= bool(c)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'l6ia_verify.py'), image], capture_output=True, text=True)
    check('ALL OK' in r.stdout, 'every archive checksum holds (l6ia_verify)')
    new_arc, _ = pa.load_l6ia_from_any(out)
    pn, po = l6ia.parse(new_arc), l6ia.parse(arc)
    raw = lambda img, p, k: img[p[k]['payload_off']: p[k]['payload_off'] + p[k]['payload_len']]
    check([k for k in range(len(po)) if raw(new_arc, pn, k) != raw(arc, po, k)] == [0], 'only Entry 0 differs from the base')
    n0 = bytes(pa.get_entry_swapped(new_arc, 0))
    allowed = set(range(0, 0x34))
    for _, o in done:
        allowed |= set(range(o, o + 4))
    diff = [i for i in range(len(e0)) if n0[i] != e0[i]] if len(n0) == len(e0) else None
    check(diff is not None and set(diff) <= allowed, f'Entry 0: only the three compares, the block type and the header changed ({len(diff or [])} bytes)')
    segs = pa._parse_e0_segments_any(bytearray(n0))
    check(n0[done[-1][1]] == DELAY_TYPE, f'its browser item (at {done[-1][0]:#x}) has block type {DELAY_TYPE:#x}, an ordinary delay')
    check(all(pa._decode_thumb_movw(n0[pa._e0_vaddr_to_foff(segs, va, 4):][:4])[1] == NOBODY for va, _ in done[:3]),
          'each compare now looks for 0xffff: ' + ', '.join(hex(va) for va, _ in done[:3]))
    md5 = hashlib.md5(open(out, 'rb').read()).hexdigest()
    print(f'\n{os.path.relpath(out, ROOT)}\nMD5 {md5}\n' + ('ALL OK' if ok else 'PROBLEMS'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
