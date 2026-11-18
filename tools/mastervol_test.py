#!/usr/bin/env python3
"""Master-volume test image: is the App model's `masterVolume` wired on the HX Effects?

The HX Stomp's top-level App model has `masterVolume` (0..1, default 1.0), which its VOLUME knob drives. The HX
Effects' App model (HelixFx_App) has the same parameter, slot 46, but no knob. This tool takes a verified image and
changes only that parameter's starting value, 1.0 -> VALUE (default 0.5), in the two places it lives:

  Entry 3   the parameter's default (HelixFx_App, param `masterVolume`, float at record + 28)
  Entry 4   the App graph's initial value for slot 46 (blob 1, the root-path pinit whose pid is 46)

Defaults alone change nothing on the unit (tested 2026-11-17 with 0.5 and 0.1): the app's routine that applies the
saved global DSP settings at start-up (0x280c744c) walks global parameters 150..165 and, for 157, ignores the saved
value and writes 1.0 (`mov.w sb, #0x3f800000` at 0x280c7460). Read live over the memory window, global parameter 157
is the App model's slot 46, masterVolume, and its record holds the Entry 3 default. --force also changes that
constant to VALUE (an ARM immediate: 0.125, 0.25, 0.5 ... encode; 0.1 does not). That alone left the live value at
1.0 (read over the memory window, 2026-11-17): the HX Effects' own start-up routine (0x280a6914) sets 157 to 0.0
early (a start-up mute) and to 1.0 when it is done (`mov.w r3, #0x3f800000` at 0x280a6ae8, then the setter
0x280e98d4 with id 0x9d). --force changes that constant too, so the start-up value is VALUE.

usage: .venv/bin/python tools/mastervol_test.py BASE.hxf [VALUE] [--force]
Writes build/<base>_MasterVol<VALUE>[F].hxf and checks it: only those words differ from the base (every other byte
of every entry identical), and every archive checksum holds (tools/l6ia_verify.py).
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
APP, PARAM, SLOT, ROOT_PATH = 'HelixFx_App', 'masterVolume', 46, 0x0D
# the constants written into global parameter 157 (masterVolume): (address, register, register number)
FORCES = ((0x280C7460, 'sb', 9),          # applying saved global DSP settings: 157 is always given 1.0
          (0x280A6AE8, 'r3', 3))          # the end of the HX Effects' start-up routine: unmute to 1.0


def mov_imm(value, reg, rnum, va):
    """Thumb-2 `mov.w reg, #imm` for the float VALUE, or None if its bits are not an ARM modified immediate."""
    bits = struct.unpack('<I', struct.pack('<f', value))[0]
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    for imm12 in range(4096):
        i, imm3, imm8 = imm12 >> 11, (imm12 >> 8) & 7, imm12 & 0xFF
        enc = struct.pack('<HH', 0xF04F | i << 10, imm3 << 12 | rnum << 8 | imm8)
        ins = list(md.disasm(enc, va))
        if ins and f'{ins[0].mnemonic} {ins[0].op_str}' == f'mov.w {reg}, #{bits:#x}':
            return enc
    return None


def locate(arc):
    """(Entry 3 swapped, Entry 4 swapped, Entry 3 byte offset of the default, Entry 4 byte offset of the init value)."""
    e3 = bytes(pa.get_entry_swapped(arc, 3))
    e4 = bytes(pa.get_entry_swapped(arc, 4))
    info = pa.parse_entry3_full(e3)
    m = pa.find_model(info, APP)
    p = [x for x in m['params'] if x['name'] == PARAM]
    assert len(p) == 1 and p[0]['slot'] == SLOT and p[0]['min'] == 0.0 and p[0]['max'] == 1.0, p
    o3 = p[0]['off'] + 28
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    d = w4[3]
    ln, off = w4[d + 2 * m['blob_index']], w4[d + 2 * m['blob_index'] + 1]
    bw = w4[off: off + ln]
    pin, npin = bw[10], bw[11]
    hits = [bw[pin + 4 * k + 2] for k in range(npin)
            if bw[pin + 4 * k: pin + 4 * k + 4][0] == ROOT_PATH and bw[pin + 4 * k + 1] == SLOT and bw[pin + 4 * k + 3] == 1]
    assert len(hits) == 1, hits
    vo = hits[0]
    assert bw[vo] == 1, 'value record is not a plain value'
    o4 = 4 * (off + vo + 1)
    return e3, e4, o3, o4


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        sys.exit(__doc__)
    force = '--force' in sys.argv
    args = [a for a in sys.argv[1:] if a != '--force']
    base = os.path.abspath(args[0])
    value = float(args[1]) if len(args) > 1 else 0.5
    assert 0.0 <= value <= 1.0
    arc, _ = pa.load_l6ia_from_any(base)
    assert pa.select_device(arc) is pa.EFFECTS_DSP, 'not an HX Effects image'
    e3, e4, o3, o4 = locate(arc)
    one = struct.pack('<f', 1.0)
    assert e3[o3:o3 + 4] == one and e4[o4:o4 + 4] == one, 'the base does not start masterVolume at 1.0'
    new = struct.pack('<f', value)
    e3n = e3[:o3] + new + e3[o3 + 4:]
    e4n = e4[:o4] + new + e4[o4 + 4:]
    repl = {3: e3n, 4: e4n}
    e0 = bytes(pa.get_entry_swapped(arc, 0))
    segs = pa._parse_e0_segments_any(bytearray(e0))
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    offs = []
    for va, reg, rnum in FORCES:
        o0 = pa._e0_vaddr_to_foff(segs, va, 4)
        assert [f'{i.mnemonic} {i.op_str}' for i in md.disasm(e0[o0:o0 + 4], va)] == [f'mov.w {reg}, #0x3f800000'], f'unexpected code at {va:#x}'
        offs.append((va, reg, rnum, o0))
    if force:
        e0n = bytearray(e0)
        for va, reg, rnum, o0 in offs:
            enc = mov_imm(value, reg, rnum, va)
            if enc is None:
                sys.exit(f'{value} cannot be an ARM immediate; try 0.125, 0.25 or 0.5')
            e0n[o0:o0 + 4] = enc
        repl[0] = bytes(e0n)
    out_arc, _, _ = l6ia.rebuild_archive(arc, repl)

    stem = os.path.splitext(os.path.basename(base))[0]
    tag = f'{value:g}'.replace('.', 'p') + ('F' if force else '')
    build = os.path.join(ROOT, 'build')
    image = os.path.join(build, f'{stem}_MasterVol{tag}.l6ia')
    out = os.path.join(build, f'{stem}_MasterVol{tag}.hxf')
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

    def raw(img, p, k):
        return img[p[k]['payload_off']: p[k]['payload_off'] + p[k]['payload_len']]
    check(len(pn) == len(po) and [k for k in range(len(po)) if raw(new_arc, pn, k) != raw(arc, po, k)] == ([0, 3, 4] if force else [3, 4]),
          'only Entries ' + ('0, ' if force else '') + '3 and 4 differ from the base')
    if force:
        n0 = bytes(pa.get_entry_swapped(new_arc, 0))
        d0 = [i for i in range(len(e0)) if n0[i] != e0[i]] if len(n0) == len(e0) else None
        bits = struct.unpack('<I', new)[0]
        allowed = set(range(0, 0x34))
        good = []
        for va, reg, rnum, o0 in offs:
            allowed |= set(range(o0, o0 + 4))
            good.append([f'{i.mnemonic} {i.op_str}' for i in md.disasm(n0[o0:o0 + 4], va)] == [f'mov.w {reg}, #{bits:#x}'])
        check(d0 is not None and set(d0) <= allowed and all(good),
              f'Entry 0: only the two forced constants ({", ".join(hex(f[0]) for f in FORCES)}) and the header CRC changed, both now {value}')
    n3, n4 = bytes(pa.get_entry_swapped(new_arc, 3)), bytes(pa.get_entry_swapped(new_arc, 4))
    d3 = [i for i in range(len(e3)) if n3[i] != e3[i]] if len(n3) == len(e3) else None
    check(d3 is not None and set(d3) <= set(range(o3, o3 + 4)) | set(range(0, 0x30)),
          f'Entry 3: same size; only the default at {o3:#x} (and header checksum words) changed: {len(d3 or [])} bytes')
    check(n3[o3:o3 + 4] == new, f'Entry 3: {PARAM} default is now {value}')
    d4 = [i for i in range(0, len(e4), 4) if n4[i:i + 4] != e4[i:i + 4]] if len(n4) == len(e4) else None
    check(d4 == [o4] and n4[o4:o4 + 4] == new, f'Entry 4: exactly one word differs, the slot-{SLOT} initial value at {o4:#x}, now {value}')
    info = pa.parse_entry3_full(n3)
    check([p['default'] for p in pa.find_model(info, APP)['params'] if p['name'] == PARAM] == [struct.unpack('<f', new)[0]],
          'Entry 3 still parses; the parameter reads back with the new default')
    md5 = hashlib.md5(open(out, 'rb').read()).hexdigest()
    print(f'\n{os.path.relpath(out, ROOT)}\nMD5 {md5}\n' + ('ALL OK' if ok else 'PROBLEMS'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
