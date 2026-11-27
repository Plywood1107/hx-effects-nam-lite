#!/usr/bin/env python3
"""Check a legacy-cabs image (build_amps.py --cabs all) before it goes near the unit.

usage: .venv/bin/python tools/verify_cabs.py build/amps_..._cabs_manifest.json

The cabs image is built from the same base as the amps image beside it (whose own check is tools/verify_amps.py),
and is compared with it:
1. The file is the one the manifest describes; every archive checksum holds; the amps image is the one its own
   manifest describes.
2. Against the amps image: only Entry 0 differs; its first four segments differ only at the listed cab sites; the
   fifth segment is the amps image's, with the cab rows after its Table 1 and the cab items after its items; header
   and CRC right; and Entry 0 is exactly what build_amps.entry0() makes.
3. Table 1: every cab's row (its name index, the HX Stomp's preset id, cost 720), checked against the Stomp's own
   Table 1; ids and name indices unused before; each cab has a Table 2 row and is a cab model. The application's
   start-up routine and both searches, emulated: every block found, an unknown name still fails.
4. The menu: EQ has four lists, Mono, Stereo, Preamps, Cabs; the 41 single items, checked against the Stomp's
   Single Legacy list; every other list as on the amps image. No dual items.
5. The code: the one patched site (the cab limit) disassembled; nothing branches into it. The block recount
   (0x280f0b8c) and the placement check (0x280f221c), emulated together on every combination of up to three blocks
   and every replacement: on the amps image they follow the stock rules, on the cabs image the new ones (two cabs
   per DSP), with nothing else changed. The allocator, emulated: a single cab takes the first free record.
6. The DSP side: the container a single cab builds, the slots that accept it, and every cab's graph fits its model
   slot and uses only routines in the unit's DSP program.
"""
import hashlib
import itertools
import json
import os
import re
import struct
import subprocess
import sys
import zlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 're'))
sys.path.insert(0, ROOT)
import capstone  # noqa: E402
import unicorn  # noqa: E402
from unicorn import arm_const as R  # noqa: E402

import amp_patch as ap  # noqa: E402
import amps_group as ag  # noqa: E402
import build_amps  # noqa: E402
import cabs_group as cg  # noqa: E402
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

ok = True


def check(c, msg):
    global ok
    print(('  ok   ' if c else '  FAIL ') + msg)
    ok &= bool(c)


if len(sys.argv) < 2:
    sys.exit(__doc__)
man = json.load(open(sys.argv[1]))
aman = json.load(open(os.path.join(ROOT, man['amps_manifest'])))
out, amps_out = os.path.join(ROOT, man['output']), os.path.join(ROOT, aman['output'])
stock_path = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
stomp_path = os.path.join(ROOT, 'firmware', 'HX_Stomp_v3.80.0_0x103966115.hxf')
base_path = os.path.join(ROOT, aman['base']) if aman.get('base') else stock_path
A = pa.EFFECTS_E0
SEG, ASEG = man['segment'], aman['segment']
AMPS, PRE, CABS = aman['amps'], aman.get('preamps', []), man['cabs']
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

print('1. the files')
check(hashlib.md5(open(out, 'rb').read()).hexdigest() == man['output_md5'], f'{man["output"]} is the image the manifest describes ({man["output_md5"]})')
check(hashlib.md5(open(amps_out, 'rb').read()).hexdigest() == aman['output_md5'] == man['amps_md5'],
      f'the amps image {aman["output"]} is the one its manifest describes ({aman["output_md5"]}; checked by tools/verify_amps.py)')
check(man['base_md5'] == aman['base_md5'] and man['set'] == aman['set'] and man['amps'] == AMPS and man.get('preamps', []) == PRE,
      'the same base, amps and preamps as the amps image')
new, _ = pa.load_l6ia_from_any(out)
old, _ = pa.load_l6ia_from_any(amps_out)
base, _ = pa.load_l6ia_from_any(base_path)
tmp = os.path.join(ROOT, 'build', '_verify_cabs.l6ia')
open(tmp, 'wb').write(new)
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'l6ia_verify.py'), tmp], capture_output=True, text=True)
os.remove(tmp)
check('ALL OK' in r.stdout, 'every archive checksum holds (l6ia_verify)')

print('2. against the amps image')
pn, po = l6ia.parse(new), l6ia.parse(old)


def raw(img, p, k):
    return img[p[k]['payload_off']: p[k]['payload_off'] + p[k]['payload_len']]


check(len(pn) == len(po) and [k for k in range(len(po)) if raw(new, pn, k) != raw(old, po, k)] == [0], 'only Entry 0 differs from the amps image')
e0n, e0o = bytes(pa.get_entry_swapped(new, 0)), bytes(pa.get_entry_swapped(old, 0))
e0b = bytes(pa.get_entry_swapped(base, 0))
e3 = bytes(pa.get_entry_swapped(old, 3))
sn, so = pa._parse_e0_segments_any(bytearray(e0n)), pa._parse_e0_segments_any(bytearray(e0o))
check(len(sn) == len(so) == 5 and sn[:4] == so[:4] and sn[4][1] == so[4][1] and sn[4][2:4] == (SEG['seg_len'], SEG['seg_va'])
      and SEG['seg_va'] == ASEG['seg_va'] == ag.SEG_VA,
      f'five segments: the first four as on the amps image, the fifth {ASEG["seg_len"]} -> {SEG["seg_len"]} bytes at {SEG["seg_va"]:#x}')
hn, ho = struct.unpack_from('<8I', e0n, 0), struct.unpack_from('<8I', e0o, 0)
check(hn[0] == ho[0] and hn[1] == len(e0n) == len(e0o) + SEG['seg_len'] - ASEG['seg_len'] and hn[3:5] == (2, 5) and hn[5:8] == ho[5:8]
      and len(e0n) <= 0x400000 and hn[2] == zlib.crc32(e0n[0x34:]) & 0xffffffff,
      f'header: size {hn[1]:#x} (+{len(e0n) - len(e0o)} bytes, under the boot stage\'s 4 MB), 5 segments, same entry point, CRC right')


def rd(va, n, e=None, sg=None):
    e, sg = (e0n, sn) if e is None else (e, sg)
    o = pa._e0_vaddr_to_foff(sg, va, n)
    return e[o:o + n]


def u32(va, e=None, sg=None):
    return struct.unpack('<I', rd(va, 4, e, sg))[0]


sites = {c['address']: c['length'] for c in man['cab_changes']}
allowed = set(range(4, 12)) | {16, 17, 18, 19} | set(range(sn[4][1] - 12, sn[4][1]))     # header; the fifth segment's header
for va, n in sites.items():
    o = pa._e0_vaddr_to_foff(so, va, n)
    allowed |= set(range(o, o + n))
end4 = sn[4][1]
d0 = {i for i in range(end4) if e0n[i] != e0o[i]}
n_amps = ASEG['rows']
n = SEG['rows']
slot_cab = 4 * cg.CAT_EQ + cg.CABS_LIST
want_sites = {ag.T1_END_LIT: 4, **{va: 4 for va, _ in ag.T1_LAST_SITES}, ag.T1_COUNT_SITE[0]: 4,
              A.BLIST_PTR_TAB + 4 * ag.AMPS_LIST: 4, A.BLIST_PTR_TAB + 4 * (4 * ag.CAT_EQ + ag.PREAMPS_LIST): 4,
              A.BLIST_PTR_TAB + 4 * slot_cab: 4, A.BLIST_CNT_TAB + 4 * slot_cab: 4, A.SUBCAT_CNT + 4 * cg.CAT_EQ: 4,
              A.SUBCAT_NAMES + 26 * slot_cab: 26, cg.CAB_LIMIT_VA: 2}
check(sites == want_sites, f'the listed changes are exactly the {len(want_sites)} expected sites: Table 1 end, size and '
      'count constants, the Amps/Preamps/Cabs list pointers, the Cabs count and name, EQ\'s list count, the cab limit')
check(d0 <= allowed and all(rd(va, c['length']) == bytes.fromhex(c['new']) for va, c in ((c['address'], c) for c in man['cab_changes'])),
      f'inside the first four segments: {len(d0)} bytes differ from the amps image, all at those sites, each holding the listed bytes')
e0x, chx, infox = build_amps.entry0(e0b, e3, AMPS, PRE, CABS)
check(e0x == e0n and infox == SEG, 'Entry 0 is exactly: the base -> memory window -> amp changes -> cab changes -> the new segment')

print('3. Table 1')
seg = e0n[sn[4][1]: sn[4][1] + sn[4][2]]
aseg = e0o[so[4][1]: so[4][1] + so[4][2]]
info = pa.parse_entry3_full(e3)
rows = [struct.unpack_from('<IHHI', seg, 12 * i) for i in range(n)]
arows = [struct.unpack_from('<IHHI', aseg, 12 * i) for i in range(n_amps)]
cab_rows = rows[n_amps:]
want = [(pa.find_model(info, c)['words'][2], cg.CABS[c][0], 0, cg.CABS[c][1]) for c in CABS]
check(n == n_amps + len(CABS) and rows[:n_amps] == arows and cab_rows == want and all(r_[3] == 720 for r_ in cab_rows),
      f'the amps image\'s {n_amps} rows byte for byte, then {len(CABS)} cab rows (cost 720 each)')
check(seg == aseg[:12 * n_amps] + seg[12 * n_amps:12 * n] + aseg[12 * n_amps:] + seg[len(aseg) + 12 * len(CABS):]
      and len(seg) == len(aseg) + 12 * len(CABS) + 48 * len(CABS),
      f'the segment: those rows, then the amps image\'s {len(AMPS) + len(PRE)} items unchanged, then {len(CABS)} cab items')
used_ids, used_idx = {r_[1] for r_ in arows}, {r_[0] for r_ in arows}
t2 = {u32(A.TAB2_BASE + 44 * i) for i in range(A.TAB2_CNT)}
cats = [(pa.find_model(info, c).get('meta') or {}).get('category') for c in CABS]
check(len({r_[0] for r_ in rows}) == n and len({r_[1] for r_ in rows}) == n and not ({r_[1] for r_ in cab_rows} & used_ids)
      and not ({r_[0] for r_ in cab_rows} & used_idx) and max(r_[1] for r_ in cab_rows) < ag.PRESET_MAP_ENTRIES,
      f'each cab\'s preset id and name index unused before (ids {min(r_[1] for r_ in cab_rows)}..{max(r_[1] for r_ in cab_rows)}, '
      f'all below the {ag.PRESET_MAP_ENTRIES}-entry map)')
check(all(r_[0] in t2 for r_ in cab_rows) and cats == ['cab'] * len(CABS), 'each cab has a Table 2 row and is a cab model (category "cab")')
sarc, _ = pa.load_l6ia_from_any(stomp_path)
s0 = bytes(pa.get_entry_swapped(sarc, 0))
s3 = bytes(pa.get_entry_swapped(sarc, 3))
sinfo = pa.parse_entry3_full(s3)
ss = pa._parse_e0_segments_any(bytearray(s0))
D = pa.E0_DEVICES[0x28D8FA80]
good = []
for c in CABS:
    sidx = pa.find_model(sinfo, c)['words'][2]
    row = struct.pack('<IHHI', sidx, cg.CABS[c][0], 0, cg.CABS[c][1])
    o = s0.find(row)
    good.append(o > 0 and s0.find(row, o + 1) < 0 and sidx == pa.find_model(info, c)['words'][2])
check(all(good), 'each cab\'s row is the HX Stomp\'s (its name index, preset id and cost: the row is in its Table 1, once)')

INIT, COST, PID, MEMSET, MAP = 0x28100B20, 0x28100BCC, 0x28100D2C, 0x28114A04, 0x282A1978
LOGS = (0x280D3894, 0x280D38D8, 0x280D2F74)


def table_run(e0, segs, names):
    """The app's start-up routine, then both searches for each name (as tools/verify_amps.py, section 4)."""
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
    uc.mem_map(0x28000000, 0x300000)
    uc.mem_map(0x30000000, 0x10000)
    for s in segs:
        if s[3] >= 0x28000000:
            if s[3] >= 0x28300000:
                uc.mem_map(s[3], (s[2] + 0xFFF) & ~0xFFF)
            uc.mem_write(s[3], e0[s[1]: s[1] + s[2]])

    def hook(uc_, addr, size, _):
        if addr == MEMSET:
            uc_.mem_write(uc_.reg_read(R.UC_ARM_REG_R0), bytes([uc_.reg_read(R.UC_ARM_REG_R1) & 0xFF]) * uc_.reg_read(R.UC_ARM_REG_R2))
        elif addr not in LOGS:
            return
        uc_.reg_write(R.UC_ARM_REG_PC, uc_.reg_read(R.UC_ARM_REG_LR) | 1)
    uc.hook_add(unicorn.UC_HOOK_CODE, hook)

    def call(fn, *args):
        for reg, v in zip((R.UC_ARM_REG_R0, R.UC_ARM_REG_R1), args):
            uc.reg_write(reg, v)
        uc.reg_write(R.UC_ARM_REG_SP, 0x3000F000)
        uc.reg_write(R.UC_ARM_REG_LR, 0x30000101)
        uc.emu_start(fn | 1, 0x30000100, count=20_000_000)
        return uc.reg_read(R.UC_ARM_REG_R0)
    r0 = call(INIT)
    b_, e_ = struct.unpack('<I', uc.mem_read(0x28100B58, 4))[0], struct.unpack('<I', uc.mem_read(0x28100B54, 4))[0]
    tab = [struct.unpack('<IHHI', uc.mem_read(a, 12)) for a in range(b_, e_, 12)]
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
r0n, tabn, mapn, resn = table_run(e0n, sn, [r_[0] for r_ in rows] + [UNKNOWN])
check(r0n == 0 and tabn == sorted(rows) and all(resn[r_[0]] == (0, r_[3], 0, r_[1]) for r_ in rows)
      and resn[UNKNOWN][0] == resn[UNKNOWN][2] == 0xFFFFFFEB,
      f'emulated: the start-up routine sorts all {n} rows; both searches find every block with its cost and preset id '
      f'(the cabs: {sorted({resn[r_[0]][1] for r_ in cab_rows})}); an unknown name still gives -21')
check(all(mapn[r_[1]] == r_[0] for r_ in rows) and [i for i, v in enumerate(mapn) if v != 0xFFFFFFFF and i not in {r_[1] for r_ in rows}] == [],
      'preset-id map: every row\'s id leads to its name, no other entry set')

print('4. the menu')
lists_n = [(u32(A.BLIST_PTR_TAB + 4 * s), u32(A.BLIST_CNT_TAB + 4 * s)) for s in range(52)]
lists_o = [(u32(A.BLIST_PTR_TAB + 4 * s, e0o, so), u32(A.BLIST_CNT_TAB + 4 * s, e0o, so)) for s in range(52)]
pslot = 4 * ag.CAT_EQ + ag.PREAMPS_LIST
shift = 12 * len(CABS)
check(lists_n[ag.AMPS_LIST] == (lists_o[ag.AMPS_LIST][0] + shift, lists_o[ag.AMPS_LIST][1]) == (SEG['items_va'], len(AMPS))
      and lists_n[pslot] == (lists_o[pslot][0] + shift, lists_o[pslot][1]) == (SEG['preamps_va'], len(PRE))
      and lists_o[slot_cab] == (0, 0) and lists_n[slot_cab] == (SEG['cabs_va'], len(CABS))
      and SEG['cabs_va'] == SEG['preamps_va'] + 48 * len(PRE)
      and [lists_n[s] for s in range(52) if s not in (ag.AMPS_LIST, pslot, slot_cab)] == [lists_o[s] for s in range(52) if s not in (ag.AMPS_LIST, pslot, slot_cab)],
      f'list {slot_cab} (EQ\'s fourth): {len(CABS)} items at {SEG["cabs_va"]:#x}; the Amps and Preamps lists moved by {shift} '
      'bytes with the longer table; every other list as on the amps image')
cnt_n = [u32(A.SUBCAT_CNT + 4 * c) for c in range(13)]
cnt_o = [u32(A.SUBCAT_CNT + 4 * c, e0o, so) for c in range(13)]
nm_eq = [rd(A.SUBCAT_NAMES + 26 * (4 * cg.CAT_EQ + k), 26).split(b'\0')[0].decode() for k in range(4)]
check(cnt_o[cg.CAT_EQ] == 3 and cnt_n[cg.CAT_EQ] == 4 and [c for k, c in enumerate(cnt_n) if k != cg.CAT_EQ] == [c for k, c in enumerate(cnt_o) if k != cg.CAT_EQ]
      and nm_eq == ['Mono', 'Stereo', 'Preamps', 'Cabs'] and rd(A.SUBCAT_NAMES + 26 * slot_cab, 26, e0o, so) == bytes(26),
      f'EQ has 4 lists: {nm_eq} (the fourth name field was empty); every other category as on the amps image')
D_single = 4 * 14 + 2                          # the Stomp's Cab category: Single Legacy


def stomp_list(slot):
    p_, c_ = struct.unpack_from('<I', s0, pa._e0_vaddr_to_foff(ss, D.BLIST_PTR_TAB + 4 * slot, 4))[0], \
        struct.unpack_from('<I', s0, pa._e0_vaddr_to_foff(ss, D.BLIST_CNT_TAB + 4 * slot, 4))[0]
    return [s0[pa._e0_vaddr_to_foff(ss, p_ + 48 * k, 48):][:48] for k in range(c_)]


st_single = stomp_list(D_single)
singles = [rd(SEG['cabs_va'] + 48 * k, 48) for k in range(len(CABS))]
st_by = {struct.unpack_from('<I', it, 4)[0]: it for it in st_single}
idxs = [pa.find_model(info, c)['words'][2] for c in CABS]


def disp(it):
    return it[14:40].split(b'\0')[0].decode('latin1')


check([struct.unpack_from('<I', it, 4)[0] for it in st_single] == idxs,
      f'the Stomp lists the same {len(CABS)} cabs in Single Legacy, in this order')
check(all(it[:14] == st_by[i][:14] and it[40:] == st_by[i][40:] and disp(it) == disp(st_by[i]) == cg.CABS[c][2] and it[14:40] == st_by[i][14:40]
          and struct.unpack_from('<IIIH', it)[0:4] == (cg.BTYPE_SINGLE, i, 0xFFFFFFFF, cg.CABS[c][0])
          for it, i, c in zip(singles, idxs, CABS)),
      'the 41 single items are the Stomp\'s byte for byte (type 0x0f, name index, 0xffffffff, preset id, name, 1, 0)')
print('5. the code')


def dis(va, nbytes, e=None, sg=None):
    return [f'{i.mnemonic} {i.op_str}' for i in md.disasm(rd(va, nbytes, e, sg), va)]


check(dis(cg.CAB_LIMIT_VA, 2, e0o, so) == ['cmp r4, #0'] and dis(cg.CAB_LIMIT_VA, 2) == [f'cmp r4, #{cg.CAB_LIMIT}'] and dis(ap.AMP_LIMIT_VA, 2) == ['cmp r3, #3']
      and dis(0x280F22B2, 2) == ['cmp r1, #2'], f'limits per DSP: amps 3 (the amp work), cabs 0 -> {cg.CAB_LIMIT}, IRs 2 (stock)')
code = rd(0x28000000, sn[2][2])
mdl = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
mdl.skipdata = True
pc_loads, branches = [], []
targets = {cg.CAB_LIMIT_VA, cg.CAB_LIMIT_VA + 1}
for i in mdl.disasm(code, 0x28000000):
    if i.mnemonic.startswith(('b', 'cb')) and '#' in i.op_str:
        try:
            t = int(i.op_str.split('#')[-1], 16)
        except ValueError:
            continue
        if t in targets:
            branches.append((i.address, t))
check(branches == [], 'no branch in the code targets the patched cab limit; it is reached only by falling through')

# --- the recount and the placement check, emulated together --------------------------------------------------
RECOUNT, CHECK, PASS, REFUSE = 0x280F0B8C, 0x280F221C, 0x280F22B6, 0x280F2386
FLOW, OLDBLK, NEWTYPE, RESULT, STACK = 0x30010000, 0x30020000, 0x30020100, 0x30020200, 0x3002F000


class Dsp:
    def __init__(self, e0, segs):
        self.uc = uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
        uc.mem_map(0x28000000, 0x300000)
        uc.mem_map(0x30000000, 0x40000)
        for s in segs:
            if 0x28000000 <= s[3] < 0x28300000:
                uc.mem_write(s[3], e0[s[1]: s[1] + s[2]])
        self.calls = []
        uc.hook_add(unicorn.UC_HOOK_CODE, self.hook, begin=0x28000000, end=0x282FFFFF)

    def hook(self, uc, addr, size, _):
        if addr == REFUSE:
            self.stop = 'refused'
            uc.emu_stop()
        elif addr == PASS:
            self.stop = 'pass'
            uc.emu_stop()
        elif addr in self.ret_at:
            self.calls.append(addr)
            uc.reg_write(R.UC_ARM_REG_R0, 0)
            uc.reg_write(R.UC_ARM_REG_PC, uc.reg_read(R.UC_ARM_REG_LR) | 1)

    def flow(self, types):
        uc = self.uc
        uc.mem_write(FLOW, bytes(0x7000))
        uc.mem_write(FLOW + 0xB14, bytes([9]))
        for k, t in enumerate(types):
            rec = FLOW + 0xB40 + 0x9F4 * k
            uc.mem_write(rec + 0x24, struct.pack('<I', 1))
            uc.mem_write(rec + 0x28, bytes([t]))

    def run(self, fn, regs, until=0x30000100):
        uc = self.uc
        for reg, v in regs.items():
            uc.reg_write(reg, v)
        uc.reg_write(R.UC_ARM_REG_LR, until | 1)
        self.stop = None
        uc.emu_start(fn | 1, until, count=100000)
        return uc.reg_read(R.UC_ARM_REG_R0)

    def place(self, present, old, newt):
        """present: the block types on the DSP; old: the type of the block being replaced (one of present) or None."""
        self.ret_at = ()
        self.flow(present)
        self.run(RECOUNT, {R.UC_ARM_REG_R0: FLOW, R.UC_ARM_REG_SP: STACK})
        counts = struct.unpack('<3I', self.uc.mem_read(FLOW + 0xAE0, 12))[::-1]        # amps, cabs, IRs
        self.uc.mem_write(OLDBLK + 0x28, bytes([old or 0]))
        self.uc.mem_write(NEWTYPE, bytes([newt]))
        self.uc.mem_write(STACK, struct.pack('<I', RESULT))
        self.run(CHECK, {R.UC_ARM_REG_R0: 0x30030000, R.UC_ARM_REG_R1: FLOW, R.UC_ARM_REG_R2: OLDBLK if old else 0,
                         R.UC_ARM_REG_R3: NEWTYPE, R.UC_ARM_REG_SP: STACK})
        return counts, self.stop

    def alloc(self, busy, t):
        self.ret_at = (0x280D2F74, 0x280ED258)
        self.flow([])
        for k in busy:
            self.uc.mem_write(FLOW + 0xB40 + 0x9F4 * k + 0x24, struct.pack('<I', 1))
        a = self.run(0x280ED3EC, {R.UC_ARM_REG_R0: 0x30030000, R.UC_ARM_REG_R1: FLOW, R.UC_ARM_REG_R2: t, R.UC_ARM_REG_SP: STACK})
        return None if a == 0 else (a - FLOW - 0xB40) // 0x9F4


FX, CAB1, CAB2, AMP, AMPCAB, IR1, IR2, AMPIR = 0x01, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x21
TYPES = (FX, CAB1, CAB2, AMP, AMPCAB, IR1, IR2, AMPIR)


def rules(dual, limits):
    w = {FX: (0, 0, 0), CAB1: (0, 1, 0), CAB2: dual, AMP: (1, 0, 0), AMPCAB: (1, 1, 0), IR1: (0, 0, 1), IR2: (0, 0, 2), AMPIR: (1, 0, 1)}

    def model(present, old, newt):
        cnt = tuple(sum(w[t][k] for t in present) for k in range(3))
        after = [cnt[k] - (w[old][k] if old else 0) + w[newt][k] for k in range(3)]
        return cnt, 'pass' if all(after[k] <= limits[k] for k in range(3)) else 'refused'
    return model


cases = []
for k in range(4):
    for present in itertools.combinations_with_replacement(TYPES, k):
        for old in (None,) + tuple(sorted(set(present))):
            for newt in TYPES:
                cases.append((present, old, newt))
amps_model, cabs_model = rules((0, 2, 0), (3, 0, 2)), rules((0, 2, 0), (3, cg.CAB_LIMIT, 2))
dn, do = Dsp(e0n, sn), Dsp(e0o, so)
bad_o = [c for c in cases if do.place(*c) != amps_model(*c)]
bad_n = [c for c in cases if dn.place(*c) != cabs_model(*c)]
check(not bad_o, f'emulated on the amps image, {len(cases)} cases (up to three blocks of types {[hex(t) for t in TYPES]}, every '
      'replacement, every new type): the stock rules (a dual = two cabs, no cab allowed; amps 3, IRs 2)' + (f'; differ: {bad_o[:4]}' if bad_o else ''))
check(not bad_n, f'emulated on the cabs image, the same {len(cases)} cases: the new rules ({cg.CAB_LIMIT} cabs, '
      'three amps, two IRs per DSP; the stock weights otherwise)' + (f'; differ: {bad_n[:4]}' if bad_n else ''))
spot = {'empty, add a cab': ((), None, CAB1), 'one cab, add a second': ((CAB1,), None, CAB1),
        'two cabs, add a third': ((CAB1, CAB1), None, CAB1), 'two cabs, one -> another cab': ((CAB1, CAB1), CAB1, CAB1),
        'three amps, add a cab': ((AMP, AMP, AMP), None, CAB1), 'amp + cab + IR, add an IR': ((AMP, CAB1, IR1), None, IR1)}
print('  --   ' + '; '.join(f'{k}: {dn.place(*v)[1]}' for k, v in spot.items()))
al = {(tuple(b), t): dn.alloc(b, t) for b, t in (([], CAB1), ([0], CAB1), ([0, 1, 2, 3, 4, 5], CAB1), ([], AMP), ([], FX))}
check(al == {((), CAB1): 0, ((0,), CAB1): 1, ((0, 1, 2, 3, 4, 5), CAB1): 6, ((), AMP): 6, ((), FX): 0},
      'allocator (0x280ed3ec), emulated: a single cab takes the first free record (0 up, LITTLE), as an effect')

print('6. the DSP side')
import fw  # noqa: E402
import graphs  # noqa: E402

app = fw.App(base_path)
S = info['strings']
jt = 0x280F3EEC
harn = {}
for t in (CAB1,):
    h = jt + 2 * struct.unpack('<H', rd(jt + 2 * (t - 1), 2))[0]
    txt = dis(h, 0x30)
    harn[t] = next(S[int(x.split('#')[1], 16)] for x in txt if x.startswith('movw r7, #'))
check(dis(0x280F3EE0, 12) == ['subs r3, #1', 'cmp r3, #0x20', 'bhi.w #0x280f443e', 'tbh [pc, r3, lsl #1]'] and harn == {CAB1: 'HD2_AppCabHarnessSingle'},
      f'the container by block type (tbh at 0x280f3ee8): 0x0f -> {harn[CAB1]}')
hd = info['header']
groups = {}
for i in range(hd[9]):
    rec = struct.unpack_from('<8I', e3, hd[8] + 32 * i)
    groups.setdefault(S[rec[2]], []).append([info['models'][x]['name'] for x in struct.unpack_from('<%dI' % rec[5], e3, rec[6])])
fxs = {k: groups[f'fx.{k}'][0] for k in range(16)}
FLOW_SLOTS = [S[u32(ap.FLOW_SLOT_TAB + 4 * k)] for k in range(1, 9)]
check(all('HD2_AppCabHarnessSingle' in fxs[k] for k in range(16)), 'every DSP slot fx.0..15 accepts the single-cab container')
cab_slots = [m for m in groups.get('modelSlot', []) if set(CABS) <= set(m)]
check(len(cab_slots) >= 1, f'the single container\'s modelSlot accepts all {len(CABS)} cabs')
G = graphs.Graphs(app)
p2 = l6ia.parse(base)[2]
prims, _ = pa.sharc_prim_table(base[p2['payload_off']: p2['payload_off'] + p2['payload_len']])
sl1 = [m_ for m_ in G.members(G.root('HD2_AppCabHarnessSingle')) if m_[13] > 100]
bad, worst = [], [0, 0, 0, 0]
for c in CABS:
    root, seen, pr, todo = G.root(c), set(), set(), [G.root(c)]
    while todo:
        x = todo.pop()
        if x in seen:
            continue
        seen.add(x)
        for m_ in G.members(x):
            if 0x600000 <= m_[6] < 0x700000:
                todo.append(m_[6])
            else:
                pr.add(m_[6])
    dm, pm, sd, nmem = G.need(root)
    worst = [max(a, b) for a, b in zip(worst, (dm, pm, sd, nmem))]
    if any(dm > s[13] or pm > s[14] or sd > s[15] or nmem > s[17] for s in sl1) or [x for x in pr if x and x not in prims]:
        bad.append(c)
check(len(sl1) == 1 and not bad,
      f'every cab\'s graph (largest {worst[0]} DM, {worst[1]} PM, {worst[2]} SDRAM words, {worst[3]} members) fits the model slot '
      f'({sl1[0][13]}, {sl1[0][14]}, {sl1[0][15]}, {sl1[0][17]} members) and uses only routines in the DSP program')
n1 = G.need(G.root('HD2_AppCabHarnessSingle'))
print(f'  --   single cab container (DM, PM, SDRAM words): {n1[:3]}; two per DSP at most')

print('ALL OK' if ok else 'PROBLEMS')
sys.exit(0 if ok else 1)
