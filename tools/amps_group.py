"""An "Amps" group under the Distortion category, with amps under their own identities and no stock block replaced.

Two things the application needs for each amp, and where they come from here:

1. A row in Table 1, the table of placeable blocks ({name index, preset id, 0, DSP cost}). Stock has 465 rows packed
   between other data, so the table is moved: a copy of the 465 stock rows followed by the amps' rows lives in a new
   data segment, and the application's references are pointed at it. Every reference (re/survey.py, section 10):
       0x28100b1c, 0x28100b58, 0x28100b70, 0x28100c64, 0x28100df0   literal: the table's address
       0x28100b54   literal: the table's end, where the start-up routine (0x28100b20) stops building its
                    preset-id -> name map before it sorts the table by name index in place
       0x28100b44   the sort's last index (count - 1);  0x28100bce, 0x28100d38  the two binary searches' last index
       0x28100b5c   the row count
   (0x28100b80, the list of seven containers that happens to follow the stock table, is left alone.)

2. An item in a menu list (48 bytes: block type, name index, 0xffffffff, preset id, display name). The menu is 13
   categories of 4 lists; Distortion uses three (Mono, Stereo, Legacy). Its fourth list gets the amps:
       0x28100228   list pointer (BLIST_PTR_TAB[3])      0x28100318   item count (BLIST_CNT_TAB[3])
       0x281003e4   Distortion's number of lists, 3 -> 4  0x28100536   the fourth list's name, "Amps"

The new segment is appended to Entry 0 (a fifth segment; the boot stage, Entry 1, loads any number of segments and
accepts SDRAM destinations: its loop at 0x1400131a and range check at 0x14000f4c). It loads at SEG_VA, in SDRAM that
the running unit never touches (sampled over the memory window: still power-up noise after hours of use).

3. The list view (./src/app/fsModelListUI.c, drawn by 0x2807b6f4) shows three list names at a time and already
   slides: the position holding the highlight shows the current list, positions before it the previous lists,
   positions after it the next ones. But the highlight position (view + 0x27) is allowed to reach "number of lists
   - 1", which Line 6 never exceeded 2 with: with a fourth list it becomes 3, a position that is never drawn, and
   the three that are drawn come out as "Stereo, Stereo, Legacy" (seen on the unit, 2026-11-16). The highlight is
   capped at position 2 wherever it is set:
       0x2809f172   moving to the next list: the limit `number of lists - 1` becomes 2
       0x2809f5c0, 0x2809fb22   opening the view on the list a block is already in: `position = list index`
                    becomes a call to a 20-byte routine that stores min(list index, 2)
   The routine sits on a log string that the allocator change (amp_patch.runtime_changes) leaves unused:
   "INFO: out of BIG blocks for BIG models, ..." at 0x280ed39c.

Each amp's preset id and DSP cost are the HX Stomp's own for that amp (its Table 1), so a preset stores the same
id the Stomp would.

4. With cabs (tools/cabs_group.py): their rows follow the preamps' in the same table, and their items (the single
   cabs) follow the Preamps items, as EQ's fourth list, "Cabs". With no cabs, nothing changes.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amp_patch as ap  # noqa: E402
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

SEG_VA = 0x29000000
T1_BASE_LITS = (0x28100B1C, 0x28100B58, 0x28100B70, 0x28100C64, 0x28100DF0)
T1_END_LIT = 0x28100B54
T1_LAST_SITES = ((0x28100B44, 1), (0x28100BCE, 12), (0x28100D38, 12))        # (address, register): mov.w rX, #count-1
T1_COUNT_SITE = (0x28100B5C, 0)                                              # movw r0, #count
PRESET_MAP_ENTRIES = 0xD04 // 4          # the start-up routine's preset-id -> name map (0x282a1978): ids must be below
CAT_DISTORTION, AMPS_LIST = 0, 3
GROUP_NAME = 'Amps'
CAT_EQ, PREAMPS_LIST = 2, 2              # EQ has two lists (Mono, Stereo); the preamps are its third
PREAMP_GROUP_NAME = 'Preamps'
SUBCAT_NAME_LEN = 26

SEL_LIMIT_VA, SEL_LIMIT_STOCK, SEL_LIMIT_NEW = 0x2809F172, bytes.fromhex('013b'), bytes.fromhex('0223')   # subs r3, #1 -> movs r3, #2
SEL_SET_SITES = (0x2809F5C0, 0x2809FB22)
SEL_SET_STOCK = bytes.fromhex('84f82730')                 # strb.w r3, [r4, #0x27]
SEL_CLAMP_VA = 0x280ED39C                                 # over the unused "INFO: out of BIG blocks..." string
SEL_CLAMP_STOCK_HEAD = b'INFO: out of BIG blocks for BIG models'
SEL_CLAMP = (bytes.fromhex('9c46')                        # mov    ip, r3
             + bytes.fromhex('bcf1020f')                  # cmp.w  ip, #2
             + bytes.fromhex('88bf')                      # it     hi
             + bytes.fromhex('4ff0020c')                  # movhi.w ip, #2
             + bytes.fromhex('84f827c0')                  # strb.w ip, [r4, #0x27]
             + bytes.fromhex('0b2d')                      # cmp    r5, #0xb     (the flags the first call site goes on to test)
             + bytes.fromhex('7047'))                     # bx     lr

# amp -> (the HX Stomp's preset id, DSP cost); tools/verify_amps.py checks these against the Stomp's firmware
AMPS = {'HD2_AmpUSSmallTweed': (43, 1209), 'HD2_AmpUSDoubleNrm': (41, 2324), 'HD2_AmpTweedBluesBrt': (37, 2324),
        'HD2_AmpWhoWatt100': (44, 2629), 'HD2_AmpCartographer': (484, 2550), 'HD2_AmpMoonJump': (667, 2850),
        'HD2_AmpMandarinRocker': (618, 2875), 'HD2_AmpBrit2203': (787, 2800), 'HD2_AmpPlacaterDirty': (500, 2800),
        'HD2_AmpBritPlexiJump': (16, 3092), 'HD2_AmpArchetypeLead': (336, 2550), 'HD2_AmpEVPanamaRed': (823, 3700),
        'HD2_AmpLine6Badonk': (349, 1625), 'HD2_AmpMandarinBass200': (789, 2200), 'HD2_AmpSVT4Pro': (519, 1650)}
# 'fifteen': the user's list, in the user's order (2026-11-12; "Bassman" there is Tweed Blues Brt)
FIFTEEN = list(AMPS)
# 'all': those fifteen first, then every other amp the HX Stomp lists, in its order (guitar, then bass)
from amp_list import STOMP_AMPS  # noqa: E402
for _name, _pid, _cost in STOMP_AMPS:
    assert AMPS.setdefault(_name, (_pid, _cost)) == (_pid, _cost), _name
SETS = {'tweed': ['HD2_AmpTweedBluesBrt'], 'fifteen': FIFTEEN,
        'all': FIFTEEN + [n for n, _, _ in STOMP_AMPS if n not in FIFTEEN]}
# preamp -> (the HX Stomp's preset id, DSP cost): every preamp the Stomp lists, in its order (guitar, bass, mic)
from preamp_list import STOMP_PREAMPS  # noqa: E402
PREAMPS = {n: (pid, cost) for n, pid, cost in STOMP_PREAMPS}
PRE_SETS = {'none': [], 'all': [n for n, _, _ in STOMP_PREAMPS]}
COSTS = {**AMPS, **PREAMPS}


def movw(rd, imm):
    """Thumb-2 `movw rd, #imm16` (encoding T3)."""
    assert 0 <= imm <= 0xFFFF and 0 <= rd <= 14
    return struct.pack('<HH', 0xF240 | (imm >> 11 & 1) << 10 | imm >> 12, (imm >> 8 & 7) << 12 | rd << 8 | imm & 0xFF)


def plan(e0, e3, amps, preamps=(), cabs=()):
    """(in-place changes [(address, bytes, what)], segment bytes, info) for a list of amp model names and (optional)
    lists of preamp and cab model names. The amps go in Distortion's fourth list, the preamps in EQ's third, the
    single cabs in EQ's fourth. The cabs' code changes are cabs_group.code_changes."""
    import cabs_group as cg
    A = pa.EFFECTS_E0
    info = pa.parse_entry3_full(e3)
    segs = pa._parse_e0_segments_any(bytearray(e0))

    def rd(va, n):
        o = pa._e0_vaddr_to_foff(segs, va, n)
        return bytes(e0[o:o + n])

    def u32(va):
        return struct.unpack('<I', rd(va, 4))[0]
    stock_rows = rd(A.TAB1_BASE, 12 * A.TAB1_CNT)
    used_ids = {struct.unpack_from('<H', stock_rows, 12 * i + 4)[0] for i in range(A.TAB1_CNT)}
    used_names = {struct.unpack_from('<I', stock_rows, 12 * i)[0] for i in range(A.TAB1_CNT)}
    rows, items, listed = b'', b'', []
    for name in list(amps) + list(preamps):
        m = pa.find_model(info, name)
        kind = 'amp' if name in amps else 'preamp'
        pid, cost = (AMPS if kind == 'amp' else PREAMPS)[name]
        idx = m['words'][2]
        assert idx not in used_names and pid not in used_ids and pid < PRESET_MAP_ENTRIES, name
        assert (m.get('meta') or {}).get('category') == kind, f'{name} is not an {kind} model'
        assert [1 for i in range(A.TAB2_CNT) if u32(A.TAB2_BASE + 44 * i) == idx], f'{name} has no Table 2 row'
        used_names.add(idx)
        used_ids.add(pid)
        disp = m['displayName']
        rows += struct.pack('<IHHI', idx, pid, 0, cost)
        items += struct.pack('<IIIH', ap.BTYPE_AMP, idx, 0xFFFFFFFF, pid) + disp.encode('latin1')[:25].ljust(26, b'\0') + \
            struct.pack('<II', 1, 0)
        listed.append(dict(model=name, name_idx=idx, preset_id=pid, cost=cost, display=disp, kind=kind))
    assert not cabs or preamps, 'the Cabs list is EQ\'s fourth: it needs the Preamps list'
    for name in cabs:
        m = pa.find_model(info, name)
        pid, cost, sdisp = cg.CABS[name]
        idx = m['words'][2]
        assert idx not in used_names and pid not in used_ids and pid < PRESET_MAP_ENTRIES, name
        assert (m.get('meta') or {}).get('category') == 'cab', f'{name} is not a cab model'
        assert [1 for i in range(A.TAB2_CNT) if u32(A.TAB2_BASE + 44 * i) == idx], f'{name} has no Table 2 row'
        used_names.add(idx)
        used_ids.add(pid)
        rows += struct.pack('<IHHI', idx, pid, 0, cost)
        items += cg.item(cg.BTYPE_SINGLE, idx, 0xFFFFFFFF, pid, sdisp)
        listed.append(dict(model=name, name_idx=idx, preset_id=pid, cost=cost, display=sdisp, kind='cab'))
    count = A.TAB1_CNT + len(amps) + len(preamps) + len(cabs)
    t1_va = SEG_VA
    items_va = SEG_VA + 12 * count
    seg = stock_rows + rows + items
    assert len(seg) % 4 == 0

    ch = []
    for lit in T1_BASE_LITS:
        assert u32(lit) == A.TAB1_BASE
        ch.append((lit, struct.pack('<I', t1_va), 'Table 1 address'))
    assert u32(T1_END_LIT) == A.TAB1_BASE + 12 * A.TAB1_CNT
    ch.append((T1_END_LIT, struct.pack('<I', t1_va + 12 * count), 'Table 1 end (start-up routine)'))
    for va, reg in T1_LAST_SITES:
        ch.append((va, movw(reg, count - 1), f'last row index {A.TAB1_CNT - 1} -> {count - 1}'))
    ch.append((T1_COUNT_SITE[0], movw(T1_COUNT_SITE[1], count), f'row count {A.TAB1_CNT} -> {count}'))
    slot = 4 * CAT_DISTORTION + AMPS_LIST
    assert u32(A.BLIST_PTR_TAB + 4 * slot) == 0 and u32(A.BLIST_CNT_TAB + 4 * slot) == 0, 'the fourth list is not empty'
    ch.append((A.BLIST_PTR_TAB + 4 * slot, struct.pack('<I', items_va), f'menu list {slot}: the Amps items'))
    ch.append((A.BLIST_CNT_TAB + 4 * slot, struct.pack('<I', len(amps)), f'menu list {slot}: {len(amps)} item(s)'))
    assert u32(A.SUBCAT_CNT + 4 * CAT_DISTORTION) == 3
    ch.append((A.SUBCAT_CNT + 4 * CAT_DISTORTION, struct.pack('<I', 4), 'Distortion: 3 lists -> 4'))
    name_va = A.SUBCAT_NAMES + SUBCAT_NAME_LEN * (4 * CAT_DISTORTION + AMPS_LIST)
    assert rd(name_va, SUBCAT_NAME_LEN) == bytes(SUBCAT_NAME_LEN) and rd(name_va - SUBCAT_NAME_LEN, 7) == b'Legacy\0'
    ch.append((name_va, GROUP_NAME.encode().ljust(SUBCAT_NAME_LEN, b'\0'), f'the fourth list\'s name: {GROUP_NAME!r}'))
    if preamps:
        slot = 4 * CAT_EQ + PREAMPS_LIST
        assert u32(A.BLIST_PTR_TAB + 4 * slot) == 0 and u32(A.BLIST_CNT_TAB + 4 * slot) == 0, 'EQ\'s third list is not empty'
        ch.append((A.BLIST_PTR_TAB + 4 * slot, struct.pack('<I', items_va + 48 * len(amps)), f'menu list {slot}: the Preamps items'))
        ch.append((A.BLIST_CNT_TAB + 4 * slot, struct.pack('<I', len(preamps)), f'menu list {slot}: {len(preamps)} item(s)'))
        assert u32(A.SUBCAT_CNT + 4 * CAT_EQ) == 2
        neq = 4 if cabs else 3
        ch.append((A.SUBCAT_CNT + 4 * CAT_EQ, struct.pack('<I', neq), f'EQ: 2 lists -> {neq}'))
        pname_va = A.SUBCAT_NAMES + SUBCAT_NAME_LEN * slot
        # stock EQ already names an unused third list "Legacy" (its list count is 2, so it is never shown)
        assert rd(pname_va, SUBCAT_NAME_LEN) == b'Legacy'.ljust(SUBCAT_NAME_LEN, b'\0') and rd(pname_va - SUBCAT_NAME_LEN, 7) == b'Stereo\0'
        ch.append((pname_va, PREAMP_GROUP_NAME.encode().ljust(SUBCAT_NAME_LEN, b'\0'), f'EQ\'s third list\'s name: {PREAMP_GROUP_NAME!r}'))
    if cabs:
        assert (cg.CAT_EQ, cg.CABS_LIST) == (CAT_EQ, PREAMPS_LIST + 1)
        slot = 4 * CAT_EQ + cg.CABS_LIST
        cabs_va = items_va + 48 * (len(amps) + len(preamps))
        assert u32(A.BLIST_PTR_TAB + 4 * slot) == 0 and u32(A.BLIST_CNT_TAB + 4 * slot) == 0, 'EQ\'s fourth list is not empty'
        ch.append((A.BLIST_PTR_TAB + 4 * slot, struct.pack('<I', cabs_va), f'menu list {slot}: the Cabs items'))
        ch.append((A.BLIST_CNT_TAB + 4 * slot, struct.pack('<I', len(cabs)), f'menu list {slot}: {len(cabs)} single cab item(s)'))
        cname_va = A.SUBCAT_NAMES + SUBCAT_NAME_LEN * slot
        assert rd(cname_va, SUBCAT_NAME_LEN) == bytes(SUBCAT_NAME_LEN), 'EQ\'s fourth list name is not empty'
        ch.append((cname_va, cg.GROUP_NAME.encode().ljust(SUBCAT_NAME_LEN, b'\0'), f'EQ\'s fourth list\'s name: {cg.GROUP_NAME!r}'))
    from thumb1 import bl_bytes
    assert rd(SEL_LIMIT_VA, 2) == SEL_LIMIT_STOCK
    ch.append((SEL_LIMIT_VA, SEL_LIMIT_NEW, 'list view: the highlight stops at the third position (was: number of lists - 1)'))
    assert rd(SEL_CLAMP_VA, len(SEL_CLAMP_STOCK_HEAD)) == SEL_CLAMP_STOCK_HEAD
    assert rd(ap.ALLOC_BIG_VA, len(ap.ALLOC_BIG_STOCK)) == ap.ALLOC_BIG_STOCK, 'plan() is given Entry 0 before the amp changes'
    ch.append((SEL_CLAMP_VA, SEL_CLAMP, 'list view: routine "highlight = min(list index, 2)", over an unused log string'))
    for site in SEL_SET_SITES:
        assert rd(site, 4) == SEL_SET_STOCK
        ch.append((site, bl_bytes(site, SEL_CLAMP_VA), 'list view: opening on a block\'s list goes through that routine'))
    info_ = dict(seg_va=SEG_VA, seg_len=len(seg), table1_va=t1_va, rows=count, items_va=items_va,
                 amps=[x for x in listed if x['kind'] == 'amp'])
    if preamps:
        info_.update(preamps_va=items_va + 48 * len(amps), preamps=[x for x in listed if x['kind'] == 'preamp'])
    if cabs:
        info_.update(cabs_va=cabs_va, cabs=[x for x in listed if x['kind'] == 'cab'])
    return ch, seg, info_


def add_segment(e0, va, data):
    """Entry 0 with one more segment (loaded at va) appended; header size and count updated, CRC redone."""
    e0 = bytearray(e0)
    magic, size, _, ver, nsegs = struct.unpack_from('<5I', e0, 0)
    assert magic == 0x230B0C5E and ver == 2 and size == len(e0) and len(data) % 4 == 0
    segs = pa._parse_e0_segments_any(e0)
    assert segs[-1][4] == size and not any(s[3] <= va < s[3] + s[2] for s in segs)
    e0 += struct.pack('<3I', len(data), va, size + 12 + len(data)) + data
    struct.pack_into('<I', e0, 4, len(e0))
    struct.pack_into('<I', e0, 16, nsegs + 1)
    out = bytes(l6ia.fix_internal_crcs(bytes(e0)))
    assert len(out) <= 0x400000, 'the boot stage refuses images over 4 MB'
    return out
