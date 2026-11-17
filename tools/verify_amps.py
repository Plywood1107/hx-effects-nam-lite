#!/usr/bin/env python3
"""Check an Amps-group image (build_amps.py) before it goes near the unit.

usage: .venv/bin/python tools/verify_amps.py [manifest.json]      (default build/amps_tweed_manifest.json)

The base is stock, or for a --base nam build the NAM + Click image: then section 0 checks that base first (its
MD5, and tools/verify/verify_nam_click.py on it), and sections 2..7 compare against it instead of stock.

1. The file is the one the manifest describes; every archive checksum holds.
2. Against stock: only Entry 0 differs. Its first four segments differ only in the bytes the manifest lists; a fifth
   segment is appended; header and CRC are right; and it is exactly what build_amps.entry0() makes.
3. The boot stage (Entry 1, unchanged) will load it: its own address check, emulated, accepts every segment.
4. Table 1 in the new segment: the 465 stock rows, then the amps' rows, with the HX Stomp's preset id and cost.
   The application's own table code, emulated on the stock and on the new image: the start-up routine builds the
   preset-id map and sorts the table; then both binary searches find every stock block with its stock cost and
   preset id, find every amp, and still fail for an unknown name.
5. The menu: Distortion has four lists named Mono, Stereo, Legacy, Amps; the Amps items are right; with preamps,
   EQ has three lists, Mono, Stereo, Preamps, and the Preamps items are right; every other list and count is stock.
5b. The list view's own code, emulated: three names at a time, the highlight never past the third.
6. What lets amp blocks run (flow slots, allocator, registry, limit) is as in the verified build_real.py image.
7. Each amp's and preamp's DSP graph fits the amp container's model slot and uses only routines in the unit's DSP
   program.
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
import zlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, ROOT)
import capstone  # noqa: E402
import unicorn  # noqa: E402
from unicorn import arm_const as R  # noqa: E402

import amp_patch as ap  # noqa: E402
import amps_group as ag  # noqa: E402
import build_amps  # noqa: E402
import l6ia  # noqa: E402
import memwin_patch as mp  # noqa: E402
import patch_amp as pa  # noqa: E402

ok = True


def check(c, msg):
    global ok
    print(('  ok   ' if c else '  FAIL ') + msg)
    ok &= bool(c)


man = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'amps_tweed_manifest.json')))
out = os.path.join(ROOT, man['output'])
stock_path = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
stomp_path = os.path.join(ROOT, 'firmware', 'HX_Stomp_v3.80.0_0x103966115.hxf')
A = pa.EFFECTS_E0
SEG = man['segment']
PRE = man.get('preamps', [])
ALL = man['amps'] + PRE
base_path = os.path.join(ROOT, man['base']) if man.get('base') else stock_path
BASE = f'the base image' if man.get('base') else 'stock'


def note(msg):
    print('  --   ' + msg)


if man.get('base'):
    print(f'0. the base: {man["base"]}')
    check(hashlib.md5(open(base_path, 'rb').read()).hexdigest() == man['base_md5'],
          f'it is the image the amps were built on ({man["base_md5"]})'
          + (', the same bytes hx-effects-nam-lite\'s `build.py nam` makes' if man['base_md5'] == build_amps.BASES['nam'][1] else ''))
    chk = man.get('base_check') or build_amps.NAM_CHECK
    r0 = subprocess.run([sys.executable, *chk], cwd=ROOT, capture_output=True, text=True)
    check(r0.stdout.strip().endswith('ALL OK'), f'its own verifier passes: {" ".join(chk)}')

print('1. the file')
check(hashlib.md5(open(out, 'rb').read()).hexdigest() == man['output_md5'], f'{man["output"]} is the image the manifest describes ({man["output_md5"]})')
new, _ = pa.load_l6ia_from_any(out)
old, _ = pa.load_l6ia_from_any(base_path)
tmp = os.path.join(ROOT, 'build', '_verify.l6ia')
open(tmp, 'wb').write(new)
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'l6ia_verify.py'), tmp], capture_output=True, text=True)
os.remove(tmp)
check('ALL OK' in r.stdout, 'every archive checksum holds (l6ia_verify)')

print(f'2. against {BASE}')
pn, po = l6ia.parse(new), l6ia.parse(old)


def raw(img, p, k):
    return img[p[k]['payload_off']: p[k]['payload_off'] + p[k]['payload_len']]


check(len(pn) == len(po) and [k for k in range(len(po)) if raw(new, pn, k) != raw(old, po, k)] == [0], f'only Entry 0 differs from {BASE}; Entries 2, 3, 4 and the boot stage are identical')
e0n, e0o = bytes(pa.get_entry_swapped(new, 0)), bytes(pa.get_entry_swapped(old, 0))
e3 = bytes(pa.get_entry_swapped(old, 3))
so, sn = pa._parse_e0_segments_any(bytearray(e0o)), pa._parse_e0_segments_any(bytearray(e0n))
check(len(sn) == len(so) + 1 == 5 and sn[:4] == so[:3] + [so[3]] and sn[4][2:4] == (SEG['seg_len'], SEG['seg_va']),
      f'five segments: {BASE}\'s four unchanged in place and size, then {SEG["seg_len"]} bytes for {SEG["seg_va"]:#x}')
hn = struct.unpack_from('<8I', e0n, 0)
ho = struct.unpack_from('<8I', e0o, 0)
check(hn[0] == ho[0] and hn[1] == len(e0n) == len(e0o) + 12 + SEG['seg_len'] and hn[3:5] == (2, 5) and hn[5:8] == ho[5:8] and len(e0n) <= 0x400000,
      f'header: size {hn[1]:#x} (+{len(e0n) - len(e0o)} bytes, under the boot stage\'s 4 MB limit), 5 segments, same entry point')
check(hn[2] == zlib.crc32(e0n[0x34:]) & 0xffffffff, 'image CRC correct')
allowed = set(range(4, 12)) | {16, 17, 18, 19}
for c in man['memwin_changes'] + man['amp_changes']:
    o = pa._e0_vaddr_to_foff(so, c['address'], c['length'])
    allowed |= set(range(o, o + c['length']))
d0 = {i for i in range(len(e0o)) if e0n[i] != e0o[i]}
check(d0 <= allowed, f'inside {BASE}\'s part: {len(d0)} bytes differ, all in the {len(man["memwin_changes"])} memory-window and {len(man["amp_changes"])} amp changes or the header')
e0b, chb, infob = build_amps.entry0(e0o, e3, man['amps'], PRE)
check(e0b == e0n and infob == SEG, f'Entry 0 is exactly: {BASE} -> memory window -> amp changes -> the new segment')

print('3. the boot stage will load it')
e1 = bytes(pa.get_entry_swapped(old, 1))
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
loop = [f'{i.mnemonic} {i.op_str}' for i in md.disasm(e1[0x136E:0x1376], 0x1400136E)]
check(loop == ['adds r5, #1', 'cmp sl, r5', 'beq #0x14001420', 'mov r0, r5'] and e1[0x1308:0x130C] == bytes.fromhex('d4f834a2'),
      'its loader loops over the header\'s segment count (0x14001308: count; 0x1400136e: next segment)')


def range_ok(lo, hi):
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
    uc.mem_map(0x14000000, 0x10000)
    uc.mem_write(0x14000000, e1)
    uc.reg_write(R.UC_ARM_REG_R0, lo)
    uc.reg_write(R.UC_ARM_REG_R1, hi)
    uc.reg_write(R.UC_ARM_REG_LR, 0x1400FF01)
    uc.emu_start(0x14000F4C | 1, 0x1400FF00, count=1000)
    return uc.reg_read(R.UC_ARM_REG_R0)


res = [range_ok(s[3], s[3] + s[2]) for s in sn]
check(res == [1] * 5 and range_ok(0x08000000, 0x08000100) == 0 and range_ok(0x1001F000, 0x10021000) == 0,
      f'its address check (0x14000f4c, emulated) accepts all five segments {[hex(s[3]) for s in sn]} and refuses bad ranges')

print('4. Table 1')
seg = e0n[sn[4][1]: sn[4][1] + sn[4][2]]
info = pa.parse_entry3_full(e3)
stock_rows_b = e0o[pa._e0_vaddr_to_foff(so, A.TAB1_BASE, 12 * A.TAB1_CNT):][:12 * A.TAB1_CNT]
stock_rows = [struct.unpack_from('<IHHI', stock_rows_b, 12 * i) for i in range(A.TAB1_CNT)]
n = SEG['rows']
rows = [struct.unpack_from('<IHHI', seg, 12 * i) for i in range(n)]
amp_rows = rows[A.TAB1_CNT:]
want = [(pa.find_model(info, a)['words'][2], ag.COSTS[a][0], 0, ag.COSTS[a][1]) for a in ALL]
check(seg[:12 * A.TAB1_CNT] == stock_rows_b and amp_rows == want and n == A.TAB1_CNT + len(ALL),
      f'{A.TAB1_CNT} rows of {BASE} byte for byte, then {len(man["amps"])} amp row(s)'
      + (f' and {len(PRE)} preamp row(s)' if PRE else '') + f': {amp_rows}')
check(len({r_[0] for r_ in rows}) == n and len({r_[1] for r_ in rows}) == n and max(r_[1] for r_ in rows) < ag.PRESET_MAP_ENTRIES,
      f'every name index and preset id unique; highest preset id {max(r_[1] for r_ in rows)} fits the {ag.PRESET_MAP_ENTRIES}-entry map')
if os.path.isfile(stomp_path):
    sarc, _ = pa.load_l6ia_from_any(stomp_path)
    s0 = bytes(pa.get_entry_swapped(sarc, 0))
    sinfo = pa.parse_entry3_full(bytes(pa.get_entry_swapped(sarc, 3)))
    good = []
    for a in ALL:
        sidx = pa.find_model(sinfo, a)['words'][2]
        row = struct.pack('<IHHI', sidx, ag.COSTS[a][0], 0, ag.COSTS[a][1])
        o = s0.find(row)
        good.append(o > 0 and s0.find(row, o + 1) < 0)
    check(all(good), 'each amp\'s' + (' and preamp\'s' if PRE else '') + ' preset id and cost are those in the HX Stomp\'s Table 1 (its row is there, once)')
else:
    note('the HX Stomp firmware is not in firmware/: the preset ids and costs (tools/amp_list.py) are not re-checked '
         'against it here (they were when the list was written, in hx-effects-stomp)')
txt = {va: [f'{i.mnemonic} {i.op_str}' for i in md.disasm(e0n[pa._e0_vaddr_to_foff(so, va, 4):][:4], va)] for va in (0x28100B44, 0x28100BCE, 0x28100D38, 0x28100B5C)}
check(txt == {0x28100B44: [f'movw r1, #{n - 1:#x}'], 0x28100BCE: [f'movw ip, #{n - 1:#x}'], 0x28100D38: [f'movw ip, #{n - 1:#x}'], 0x28100B5C: [f'movw r0, #{n:#x}']},
      f'the four size constants: last index {n - 1} (sort and both searches), count {n}')

INIT, COST, PID, MEMSET, MAP = 0x28100B20, 0x28100BCC, 0x28100D2C, 0x28114A04, 0x282A1978
LOGS = (0x280D3894, 0x280D38D8, 0x280D2F74)


def table_run(e0, segs, names):
    """Run the app's start-up routine, then both searches for each name. Returns (init result, table as left in
    memory, the preset-id map, {name: (cost result, cost, id result, id)})."""
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
    uc.mem_map(0x28000000, 0x300000)
    uc.mem_map(0x30000000, 0x10000)
    for s in segs:
        if s[3] >= 0x28000000:
            if s[3] >= 0x28300000:
                uc.mem_map(s[3], (s[2] + 0xFFF) & ~0xFFF)
            uc.mem_write(s[3], e0[s[1]: s[1] + s[2]])
    errors = []

    def hook(uc_, addr, size, _):
        if addr == MEMSET:
            uc_.mem_write(uc_.reg_read(R.UC_ARM_REG_R0), bytes([uc_.reg_read(R.UC_ARM_REG_R1) & 0xFF]) * uc_.reg_read(R.UC_ARM_REG_R2))
        elif addr in LOGS:
            errors.append(addr)
        else:
            return
        uc_.reg_write(R.UC_ARM_REG_PC, uc_.reg_read(R.UC_ARM_REG_LR) | 1)
    uc.hook_add(unicorn.UC_HOOK_CODE, hook)

    def call(fn, *args):
        for reg, v in zip((R.UC_ARM_REG_R0, R.UC_ARM_REG_R1, R.UC_ARM_REG_R2), args):
            uc.reg_write(reg, v)
        uc.reg_write(R.UC_ARM_REG_SP, 0x3000F000)
        uc.reg_write(R.UC_ARM_REG_LR, 0x30000101)
        uc.emu_start(fn | 1, 0x30000100, count=20_000_000)
        return uc.reg_read(R.UC_ARM_REG_R0)
    r0 = call(INIT)
    base = struct.unpack('<I', uc.mem_read(0x28100B58, 4))[0]
    end = struct.unpack('<I', uc.mem_read(0x28100B54, 4))[0]
    tab = [struct.unpack('<IHHI', uc.mem_read(a, 12)) for a in range(base, end, 12)]
    pmap = struct.unpack('<%dI' % ag.PRESET_MAP_ENTRIES, uc.mem_read(MAP, 4 * ag.PRESET_MAP_ENTRIES))
    res = {}
    for nm in names:
        uc.mem_write(0x30000200, bytes(8))
        a = call(COST, nm, 0x30000200)
        cost = struct.unpack('<I', uc.mem_read(0x30000200, 4))[0]
        uc.mem_write(0x30000200, b'\xee' * 8)
        b = call(PID, nm, 0x30000200)
        res[nm] = (a, cost, b, struct.unpack('<H', uc.mem_read(0x30000200, 2))[0])
    return r0, tab, pmap, res


UNKNOWN = 0xFFF0
names = [r_[0] for r_ in rows] + [UNKNOWN]
r0o, tabo, mapo, reso = table_run(e0o, so, [r_[0] for r_ in stock_rows] + [UNKNOWN])
r0n, tabn, mapn, resn = table_run(e0n, sn, names)
check(r0o == 0 and tabo == sorted(stock_rows) and all(reso[r_[0]] == (0, r_[3], 0, r_[1]) for r_ in stock_rows) and reso[UNKNOWN][0] == 0xFFFFFFEB,
      f'{BASE}\'s code on its own table (the emulation is sound): sorted, all {len(stock_rows)} blocks found, an unknown name gives -21')
check(r0n == 0 and tabn == sorted(rows) and len(tabn) == n, f'new image: the start-up routine sorts all {n} rows in the new segment')
check(all(resn[r_[0]] == (0, r_[3], 0, r_[1]) for r_ in stock_rows), f'new image: all {len(stock_rows)} blocks of {BASE} found with their cost and preset id')
check(all(resn[r_[0]] == (0, r_[3], 0, r_[1]) for r_ in amp_rows), f'new image: every amp{" and preamp" if PRE else ""} found: {[(r_[0], resn[r_[0]][1], resn[r_[0]][3]) for r_ in amp_rows]} (name index, cost, preset id)')
check(resn[UNKNOWN][0] == 0xFFFFFFEB and resn[UNKNOWN][2] == 0xFFFFFFEB, 'new image: an unknown name still gives -21 from both searches')
check(all(mapn[r_[1]] == r_[0] for r_ in rows) and [i for i, v in enumerate(mapn) if v != 0xFFFFFFFF and i not in {r_[1] for r_ in rows}] == []
      and all(mapn[i] == mapo[i] for i in range(ag.PRESET_MAP_ENTRIES) if i not in {r_[1] for r_ in amp_rows}),
      f'preset-id map: every row\'s id leads to its name; the other entries are as on {BASE}')

print('5. the menu')


def rd(va, n_):
    o = pa._e0_vaddr_to_foff(sn, va, n_)
    return e0n[o:o + n_]


def u32(va, e=None, sg=None):
    e, sg = (e0n, sn) if e is None else (e, sg)
    return struct.unpack_from('<I', e, pa._e0_vaddr_to_foff(sg, va, 4))[0]


lists_n = [(u32(A.BLIST_PTR_TAB + 4 * s), u32(A.BLIST_CNT_TAB + 4 * s)) for s in range(52)]
lists_o = [(u32(A.BLIST_PTR_TAB + 4 * s, e0o, so), u32(A.BLIST_CNT_TAB + 4 * s, e0o, so)) for s in range(52)]
PSLOT = 4 * ag.CAT_EQ + ag.PREAMPS_LIST
changed = {3: (SEG['items_va'], len(man['amps']))}
if PRE:
    changed[PSLOT] = (SEG['preamps_va'], len(PRE))
check(all(lists_n[s] == v for s, v in changed.items()) and [lists_n[s] for s in range(52) if s not in changed] == [lists_o[s] for s in range(52) if s not in changed],
      f'list 3 (Distortion\'s fourth): {len(man["amps"])} item(s) at {SEG["items_va"]:#x}'
      + (f'; list {PSLOT} (EQ\'s third): {len(PRE)} item(s) at {SEG["preamps_va"]:#x}' if PRE else '')
      + f'; the other {52 - len(changed)} lists are as on {BASE}')
cnt_n = [u32(A.SUBCAT_CNT + 4 * c) for c in range(13)]
cnt_o = [u32(A.SUBCAT_CNT + 4 * c, e0o, so) for c in range(13)]
cnt_w = list(cnt_o)
cnt_w[0] = 4
if PRE:
    cnt_w[ag.CAT_EQ] = 3
nm = [rd(A.SUBCAT_NAMES + 26 * k, 26).split(b'\0')[0].decode() for k in range(4)]
nm_eq = [rd(A.SUBCAT_NAMES + 26 * (4 * ag.CAT_EQ + k), 26).split(b'\0')[0].decode() for k in range(4)]
check(cnt_n == cnt_w and cnt_o[0] == 3 and cnt_o[ag.CAT_EQ] == 2 and nm == ['Mono', 'Stereo', 'Legacy', 'Amps']
      and nm_eq == (['Mono', 'Stereo', 'Preamps', ''] if PRE else ['Mono', 'Stereo', 'Legacy', '']),
      f'Distortion has {cnt_n[0]} lists: {nm}; EQ has {cnt_n[ag.CAT_EQ]}: {nm_eq[:cnt_n[ag.CAT_EQ]]}; the other categories\' counts are as on {BASE}')
items = [rd(SEG['items_va'] + 48 * k, 48) for k in range(len(man['amps']))]
good = True
for it, a, row in zip(items, man['amps'], amp_rows):
    m = pa.find_model(info, a)
    good &= struct.unpack_from('<IIIH', it, 0) == (0x11, row[0], 0xFFFFFFFF, row[1]) and it[14:40].split(b'\0')[0].decode('latin1') == m['displayName'] \
        and it[40:] == bytes.fromhex('0100000000000000') and (m.get('meta') or {}).get('category') == 'amp'
check(good, f'Amps items: type 0x11, the amp\'s own name index and preset id, names {[it[14:40].split(bytes(1))[0].decode() for it in items]}')
if PRE:
    pitems = [rd(SEG['preamps_va'] + 48 * k, 48) for k in range(len(PRE))]
    good = SEG['preamps_va'] == SEG['items_va'] + 48 * len(man['amps'])
    for it, a, row in zip(pitems, PRE, amp_rows[len(man['amps']):]):
        m = pa.find_model(info, a)
        good &= struct.unpack_from('<IIIH', it, 0) == (0x11, row[0], 0xFFFFFFFF, row[1]) and it[14:40].split(b'\0')[0].decode('latin1') == m['displayName'] \
            and it[40:] == bytes.fromhex('0100000000000000') and (m.get('meta') or {}).get('category') == 'preamp'
    check(good, f'Preamps items (right after the Amps items): type 0x11, each preamp\'s own name index and preset id, '
          f'names {[it[14:40].split(bytes(1))[0].decode() for it in pitems]}')
host_item = [1 for s in range(3) for k in range(lists_n[s][1]) if rd(lists_n[s][0] + 48 * k + 14, 16).startswith(b'Arbitrator Fuzz')]
check(len(host_item) == 2, 'Arbitrator Fuzz is back in the Mono and Stereo lists: no stock block is replaced')

print('5b. the list view, emulated')
DRAW, LOOP, LOOP_END, MOVE = 0x2807B6F4, 0x2807B8C0, 0x2807B976, 0x2809F11C
F_LO, F_HI = 0x2807B6F4, 0x2807BE40
GET_NAME, SET_TEXT, MASK_FN = 0x28110228, 0x2808F888, 0x2811041C
OBJ = 0x30002000
VMOVS = {}
for a_ in range(F_LO, F_HI, 2):
    ins = list(md.disasm(e0o[pa._e0_vaddr_to_foff(so, a_, 4):][:4], a_))
    if ins and ins[0].mnemonic == 'vmov' and ins[0].op_str in ('s16, r5', 'r5, s16'):
        VMOVS[a_] = ins[0].op_str


class View:
    """The list view's state and the two pieces of the app that use it, run in an emulator."""

    def __init__(self, e0, segs, cat, nlists, mask):
        self.e0, self.segs, self.cat, self.mask = e0, segs, cat, mask
        self.uc = uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
        uc.mem_map(0x28000000, 0x300000)
        uc.mem_map(0x30000000, 0x10000)
        for sg in segs:
            if 0x28000000 <= sg[3] < 0x28300000:
                uc.mem_write(sg[3], e0[sg[1]: sg[1] + sg[2]])
        uc.mem_write(OBJ + 0x2C, struct.pack('<I', nlists))
        uc.mem_write(OBJ + 0x34, struct.pack('<I', nlists))
        uc.mem_write(OBJ + 0x39, bytes([cat]))
        self.s16 = 0
        self.labels = {}
        self.range = (0, 0)
        uc.hook_add(unicorn.UC_HOOK_CODE, self.hook)

    def name(self, cat, sub):
        o = pa._e0_vaddr_to_foff(self.segs, 0x28100418 + 0x68 * cat + 0x1A * sub, 26)
        return self.e0[o:o + 26].split(b'\0')[0]

    def ret(self, r0=0):
        self.uc.reg_write(R.UC_ARM_REG_R0, r0)
        self.uc.reg_write(R.UC_ARM_REG_PC, self.uc.reg_read(R.UC_ARM_REG_LR) | 1)

    def hook(self, uc, addr, size, _):
        if addr in VMOVS and self.range[0] == F_LO:
            if VMOVS[addr] == 's16, r5':
                self.s16 = uc.reg_read(R.UC_ARM_REG_R5)
            else:
                uc.reg_write(R.UC_ARM_REG_R5, self.s16)
            uc.reg_write(R.UC_ARM_REG_PC, (addr + 4) | 1)
        elif self.range[0] <= addr < self.range[1] or addr >= 0x30000000:
            return
        elif addr == MASK_FN:
            uc.mem_write(uc.reg_read(R.UC_ARM_REG_R3), bytes([self.mask >> uc.reg_read(R.UC_ARM_REG_R2) & 1]))
            self.ret()
        elif addr == GET_NAME:
            cat, sub = uc.reg_read(R.UC_ARM_REG_R0), uc.reg_read(R.UC_ARM_REG_R1)
            if cat <= 14 and sub <= 3:
                uc.mem_write(uc.reg_read(R.UC_ARM_REG_R2), self.name(cat, sub).ljust(0x11, b'\0')[:0x11])
                self.ret()
            else:
                self.ret(0xFFFFFFFD)
        elif addr == SET_TEXT:
            p_ = uc.reg_read(R.UC_ARM_REG_R2)
            self.labels[uc.reg_read(R.UC_ARM_REG_R1)] = bytes(uc.mem_read(p_, 26)).split(b'\0')[0].decode('latin1')
            self.ret()
        else:
            self.ret()

    def get(self, off):
        return self.uc.mem_read(OBJ + off, 1)[0]

    def put(self, off, v):
        self.uc.mem_write(OBJ + off, bytes([v]))

    def window(self):
        """The three labels the draw loop puts up for the present state."""
        uc = self.uc
        self.labels = {}
        self.range = (F_LO, F_HI)
        uc.reg_write(R.UC_ARM_REG_R4, OBJ)
        uc.reg_write(R.UC_ARM_REG_SP, 0x3000E000)
        uc.emu_start(LOOP | 1, LOOP_END, count=200000)
        return [self.labels.get(k_, '?') for k_ in range(3)]

    def move(self, direction):
        uc = self.uc
        self.range = (MOVE, 0x2809F1EA)
        uc.reg_write(R.UC_ARM_REG_R0, OBJ)
        uc.reg_write(R.UC_ARM_REG_R1, direction & 0xFFFFFFFF)
        uc.reg_write(R.UC_ARM_REG_SP, 0x3000E000)
        uc.reg_write(R.UC_ARM_REG_LR, 0x30000101)
        uc.emu_start(MOVE | 1, 0x30000100, count=200000)

    def open_on(self, sub, clamp_va=None):
        """What opening the view on a block's list does: list index, and the highlight from it."""
        self.put(0x3C, sub)
        if clamp_va is None:
            self.put(0x27, sub)
        else:
            uc = self.uc
            self.range = (clamp_va, clamp_va + len(ag.SEL_CLAMP))
            uc.reg_write(R.UC_ARM_REG_R3, sub)
            uc.reg_write(R.UC_ARM_REG_R4, OBJ)
            uc.reg_write(R.UC_ARM_REG_R5, 0xB)
            uc.reg_write(R.UC_ARM_REG_LR, 0x30000101)
            uc.emu_start(clamp_va | 1, 0x30000100, count=100)

    def walk(self, moves):
        self.put(0x27, 0)
        self.put(0x3C, 0)
        self.put(0x3D, 0)
        out = [(self.get(0x3C), self.get(0x27), self.window())]
        for d_ in moves:
            self.move(d_)
            out.append((self.get(0x3C), self.get(0x27), self.window()))
        return out


WALK = [1, 1, 1, 1, -1, -1, -1, -1]
MSL, SLA = ['Mono', 'Stereo', 'Legacy'], ['Stereo', 'Legacy', 'Amps']
names_old = [View(e0o, so, 2, 3, 7).name(2, k) for k in range(4)]
w3o = View(e0o, so, 2, 3, 7).walk(WALK)
w3n = View(e0n, sn, 3, 3, 7).walk(WALK)
check(w3o == w3n and [x[2] for x in w3o] == [MSL] * 9 and [x[:2] for x in w3o] == [(0, 0), (1, 1), (2, 2), (2, 2), (2, 2), (1, 1), (0, 0), (0, 0), (0, 0)],
      'a three-list category (stock Distortion; Dynamics in the new image): Mono, Stereo, Legacy throughout, highlight 0-1-2, the same on both')
w2o, w2n = View(e0o, so, 4, 2, 3).walk(WALK), View(e0n, sn, 4, 2, 3).walk(WALK)
check(w2o == w2n and [x[:2] for x in w2o][:3] == [(0, 0), (1, 1), (1, 1)], 'a two-list category (stock EQ): identical on stock and new code')
if PRE:
    MSP = ['Mono', 'Stereo', 'Preamps']
    weq = View(e0n, sn, 4, 3, 7).walk(WALK)
    check([x[2] for x in weq] == [MSP] * 9 and [x[:2] for x in weq] == [(0, 0), (1, 1), (2, 2), (2, 2), (2, 2), (1, 1), (0, 0), (0, 0), (0, 0)],
          'EQ with three lists: Mono, Stereo, Preamps throughout, highlight 0-1-2, as any stock three-list category')
bug = View(e0n, sn, 2, 4, 15)
bug.uc.mem_write(ag.SEL_LIMIT_VA, ag.SEL_LIMIT_STOCK)             # the new image's lists, but the stock highlight limit
wb = bug.walk([1, 1, 1])
check(wb[-1] == (3, 3, ['Stereo', 'Stereo', 'Legacy']),
      f'without the fix, four lists reproduce what the unit showed: on the fourth list the highlight is at position {wb[-1][1]} and the three drawn are {wb[-1][2]}')
w4 = View(e0n, sn, 2, 4, 15).walk(WALK)
check(w4 == [(0, 0, MSL), (1, 1, MSL), (2, 2, MSL), (3, 2, SLA), (3, 2, SLA), (2, 1, SLA), (1, 0, SLA), (0, 0, MSL), (0, 0, MSL)],
      'with the fix: Mono/Stereo/Legacy for the first three lists; on the fourth the window slides to Stereo, Legacy, Amps with the highlight on Amps; back the same way')
opened = []
for sub in range(4):
    v_ = View(e0n, sn, 2, 4, 15)
    v_.open_on(sub, ag.SEL_CLAMP_VA)
    opened.append((sub, v_.get(0x27), v_.window()))
check(opened == [(0, 0, MSL), (1, 1, MSL), (2, 2, MSL), (3, 2, SLA)] and bytes(View(e0n, sn, 2, 4, 15).uc.mem_read(ag.SEL_CLAMP_VA, 20)) == ag.SEL_CLAMP,
      'opening the view on a block already in list 0, 1, 2 or 3: highlight 0, 1, 2, 2; on an amp block the window is Stereo, Legacy, Amps')
txt = [f'{i.mnemonic} {i.op_str}' for i in md.disasm(rd(ag.SEL_CLAMP_VA, 20), ag.SEL_CLAMP_VA)]
check(txt == ['mov ip, r3', 'cmp.w ip, #2', 'it hi', 'movhi.w ip, #2', 'strb.w ip, [r4, #0x27]', 'cmp r5, #0xb', 'bx lr']
      and [f'{i.mnemonic} {i.op_str}' for va_ in ag.SEL_SET_SITES for i in md.disasm(rd(va_, 4), va_)] == [f'bl #{ag.SEL_CLAMP_VA:#x}'] * 2
      and [f'{i.mnemonic} {i.op_str}' for i in md.disasm(rd(ag.SEL_LIMIT_VA, 2), ag.SEL_LIMIT_VA)] == ['movs r3, #2'],
      'the fix as written: limit `movs r3, #2`; both open sites call the 7-instruction routine (r3 kept, the flags of cmp r5, #0xb restored)')
check(rd(0x280ED46C, 2) == bytes.fromhex('0622'), 'the log string under that routine is unused: the instruction that loaded it (0x280ed46c) is now part of the allocator\'s amp path')

print('6. what lets amp blocks run')
real = os.path.join(ROOT, 'build', 'real_tweed_manifest.json')
mw = mp.apply(e0o)
rt = ap.runtime_changes(mw, e3)
sites = [(va, new_) for va, new_, _ in rt]
check(all(rd(va, len(new_)) == new_ for va, new_ in sites) and len(sites) == 6,
      'amp limit 3, records 6..8 on fx.13..fx.15, the allocator\'s amp path, the registry: the same bytes as the build_real.py image')
if os.path.isfile(real):
    check(json.load(open(real))['output_md5'] == 'fb6eb3816b9d69b8e32933414fc79da4',
          'that image (MD5 fb6eb381..., three amps working on the unit 2026-11-16) is the one those changes were proven in')
else:
    note('those changes were proven on the unit in hx-effects-stomp\'s build_real.py image (MD5 fb6eb381..., 2026-11-16)')

print('7. each amp on the DSP side')
sys.path.insert(0, os.path.join(ROOT, 're'))
import fw  # noqa: E402
import graphs  # noqa: E402

G = graphs.Graphs(fw.App(base_path))
p2 = l6ia.parse(old)[2]
prims, _ = pa.sharc_prim_table(old[p2['payload_off']: p2['payload_off'] + p2['payload_len']])
slot = [m_ for m_ in G.members(G.root('HD2_AppAmpHarness')) if m_[13] > 100]
check(len(slot) == 1 and tuple(slot[0][13:15]) == (1430, 506) and slot[0][17] == 154,
      f'the amp container (HD2_AppAmpHarness) gives its model {slot[0][13]} DM words, {slot[0][14]} PM words, {slot[0][17]} members')
proven = G.need(G.root('HD2_AmpTweedBluesBrt'))
worst, bad = [0, 0, 0], []
for a in ALL:
    root, seen, pr = G.root(a), set(), set()
    todo = [root]
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        for m_ in G.members(c):
            if 0x600000 <= m_[6] < 0x700000:
                todo.append(m_[6])
            else:
                pr.add(m_[6])
    dm, pm, sd, nmem = G.need(root)
    worst = [max(worst[0], dm), max(worst[1], pm), max(worst[2], nmem)]
    if dm > slot[0][13] or pm > slot[0][14] or sd > slot[0][15] or nmem > slot[0][17] or [x for x in pr if x and x not in prims]:
        bad.append(a)
check(not bad, f'every amp\'s{" and preamp" + chr(39) + "s" if PRE else ""} graph fits it (largest: {worst[0]} DM, {worst[1]} PM, {worst[2]} members; Tweed Blues Brt, '
      f'proven on the unit, is {proven[0]}, {proven[1]}, {proven[3]}) and uses only DSP routines the unit\'s DSP program has')

if man.get('base'):
    Gs = graphs.Graphs(fw.App(stock_path))
    io_, ib_ = Gs.info, G.info
    same3 = all(pa.find_model(io_, a_)['words'] == pa.find_model(ib_, a_)['words'] and
                pa.find_model(io_, a_)['params'] == pa.find_model(ib_, a_)['params'] for a_ in ALL)
    same4 = all(Gs.blob(pa.find_model(io_, a_)['blob_index']) == G.blob(pa.find_model(ib_, a_)['blob_index']) and
                Gs.need(Gs.root(a_)) == G.need(G.root(a_)) for a_ in ALL)
    harn = all(Gs.members(Gs.root(h)) == G.members(G.root(h)) for h in ('HD2_AppAmpHarness', 'HD2_AppAmpCabHarness'))
    check(same3 and same4 and harn, f'the base leaves every amp{" and preamp" if PRE else ""} as on stock: its model and parameters (Entry 3), its graph '
          f'and memory need (Entry 4), and the amp container itself')

print('ALL OK' if ok else 'PROBLEMS')
sys.exit(0 if ok else 1)
