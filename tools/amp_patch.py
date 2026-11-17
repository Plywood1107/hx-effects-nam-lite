"""The smallest change that puts one of Line 6's dormant amps in the HX Effects' block menu, for the crash hunt.

One stock block (the host) is made to carry the amp, as a *takeover*. This is a test set-up, not the intended
design: the goal is an Amps group under the Distortion category that overwrites nothing (docs/plan.md, phase 3).

Entry 3, the model table: five words of the host's 14-word descriptor are pointed at the amp's own, existing data:
    word 6  number of states        word 10  states table
    word 7  number of parameters    word 11  parameter table        word 13  DSP graph (blob) index
Nothing is added or moved; the amp's tables and graph are already in the firmware. The host keeps its identity
(name index, model id) and its metadata, so it still files under Distortion > Mono.

Entry 0, the application:
    Table 1 row of the host        DSP cost -> Line 6's cost for the amp (from the HX Stomp's Table 1)
    Table 2 row of the host        short name, and the three parameter counts
    block-menu items of the host   display name, and block type -> 0x11 (AMP), so the app builds the block in its
                                   amp container (HD2_AppAmpHarness) instead of the effect container
    0x280f2296                     `cmp r3, #0` -> `cmp r3, #1`: the placement check's limit on amp blocks per DSP
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

BTYPE_AMP = 0x11
AMP_LIMIT_VA, AMP_LIMIT_STOCK, AMP_LIMIT_ONE = 0x280F2296, bytes.fromhex('002b'), bytes.fromhex('012b')
E3_WORDS = (6, 7, 10, 11, 13)

# Experiment (docs/findings.md, "BIG and LITTLE blocks"): the block allocator at 0x280ed3ec sends amp block types
# (0x10..0x12, 0x21) down a BIG path that, in this build, only logs and fails. The two branches to it become nops,
# so every type takes the LITTLE path and an amp gets an ordinary block slot. The slot records are the same size
# and layout for BIG and LITTLE in the HX Stomp's build; what is not known is whether the DSP has the memory for
# the larger amp container.
ALLOC_LITTLE = ((0x280ED3F8, bytes.fromhex('2ed9'), bytes.fromhex('00bf'), 'allocator: `bls` to the BIG path (types 0x10..0x12) -> nop'),
                (0x280ED3FC, bytes.fromhex('2ed0'), bytes.fromhex('00bf'), 'allocator: `beq` to the BIG path (type 0x21) -> nop'))


def alloc_little_changes(e0):
    segs = pa._parse_e0_segments_any(bytearray(e0))
    out = []
    for va, old, new, what in ALLOC_LITTLE:
        o = pa._e0_vaddr_to_foff(segs, va, 2)
        assert bytes(e0[o:o + 2]) == old, f'{va:#x}: not the stock allocator'
        out.append((va, new, what))
    return out

# test set-ups: 'tweed' is the combination that worked once on 2026-11-12; 'tweed12' puts the same amp on a
# block that already has 12 knobs (the user's question: does a matching knob count matter?)
SETUPS = {
    'tweed': dict(amp='HD2_AmpTweedBluesBrt', host='HD2_DistArbitratorFuzzMono', display='Tweed Blues Brt', cost=2324),
    'tweed12': dict(amp='HD2_AmpTweedBluesBrt', host='HD2_Compressor3BandCompMono', display='Tweed Blues Brt', cost=2324),
}


def entry3(e3, amp, host):
    """Entry 3 with the host's descriptor carrying the amp's states, parameters and graph.
    Returns (bytes, info for the manifest)."""
    info = pa.parse_entry3_full(e3)
    a, h = pa.find_model(info, amp), pa.find_model(info, host)
    words = list(h['words'])
    for k in E3_WORDS:
        words[k] = a['words'][k]
    out = bytearray(e3)
    struct.pack_into('<14I', out, h['off'], *words)
    return bytes(l6ia.fix_internal_crcs(bytes(out))), dict(
        host_model=h['model_id'], host_name_idx=h['words'][2], amp_model=a['model_id'], descriptor_off=h['off'],
        host_params=h['words'][7], n_params=a['words'][7], n_states=a['words'][6], blob=a['words'][13])


def entry0_changes(e0, name_idx, display, cost, n_params):
    """[(address, new bytes, what)] for the host with that name index."""
    A = pa.EFFECTS_E0
    segs = pa._parse_e0_segments_any(bytearray(e0))

    def rd(va, n):
        o = pa._e0_vaddr_to_foff(segs, va, n)
        return bytes(e0[o:o + n])

    def u32(va):
        return struct.unpack('<I', rd(va, 4))[0]
    out = []
    rows = [A.TAB1_BASE + 12 * i for i in range(A.TAB1_CNT) if u32(A.TAB1_BASE + 12 * i) == name_idx]
    assert len(rows) == 1, 'the host must have exactly one Table 1 row'
    out.append((rows[0] + 8, struct.pack('<I', cost), f'Table 1: DSP cost {u32(rows[0] + 8)} -> {cost}'))
    rows = [A.TAB2_BASE + 44 * i for i in range(A.TAB2_CNT) if u32(A.TAB2_BASE + 44 * i) == name_idx]
    assert len(rows) == 1, 'the host must have exactly one Table 2 row'
    out.append((rows[0] + 4, display.encode('latin1')[:16].ljust(16, b'\0'), 'Table 2: short name'))
    old = struct.unpack('<3I', rd(rows[0] + 24, 12))
    out.append((rows[0] + 24, struct.pack('<3I', n_params, n_params, n_params), f'Table 2: parameter counts {old} -> {n_params}'))
    items = []
    for slot in range(52):
        ptr, cnt = u32(A.BLIST_PTR_TAB + 4 * slot), u32(A.BLIST_CNT_TAB + 4 * slot)
        for k in range(cnt if ptr else 0):
            if u32(ptr + 48 * k + 4) == name_idx:
                items.append((slot, ptr + 48 * k))
    assert items, 'the host is in no block-menu list'
    for slot, va in items:
        out.append((va, struct.pack('<I', BTYPE_AMP), f'menu list {slot}: block type {u32(va):#x} -> {BTYPE_AMP:#x} (AMP)'))
        out.append((va + 14, display.encode('latin1')[:25].ljust(26, b'\0'), f'menu list {slot}: display name'))
    assert rd(AMP_LIMIT_VA, 2) == AMP_LIMIT_STOCK, 'the amp limit is not the stock cmp r3, #0'
    out.append((AMP_LIMIT_VA, AMP_LIMIT_ONE, 'placement check: amp blocks per DSP 0 -> 1 (cmp r3, #1)'))
    return out


def entry0(e0, changes):
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments_any(e0)
    for va, new, _ in changes:
        o = pa._e0_vaddr_to_foff(segs, va, len(new))
        e0[o:o + len(new)] = new
    return bytes(l6ia.fix_internal_crcs(bytes(e0)))


# ---------------------------------------------------------------------------------------------------------------
# The amp under its own identity (docs/findings.md, "The DSP slots fx.13 to fx.15"). No Entry 3 change at all.
#
# What stock already has: the amp model itself (HD2_AmpTweedBluesBrt) with its Table 2 row; three DSP slots,
# fx.13..fx.15, whose list of allowed containers includes HD2_AppAmpHarness; and that container's modelSlot, whose
# list of allowed models includes the amp (but not any effect, which is why a takeover could never load there).
# What the application lacks, and this adds:
#   Table 1          the host's row becomes the amp's: {amp name index, the amp's preset id on the HX Stomp, 0, cost}
#   block menu       the host's item becomes the amp's: type 0x11, name index, preset id, display name
#   0x280f2296       amp blocks per DSP 0 -> 3 (the placement check): one per amp-capable slot
#   0x280f1a30..38   block records 6, 7, 8 are tied to the DSP slots fx.13, fx.14, fx.15 instead of fx.6, fx.7, fx.8
#   0x280ed45e..71   the allocator's BIG path (stock: log and fail) becomes "take a free record among 6, 7, 8",
#                    by entering the LITTLE loop at 0x280ed422 with r3 = record 6, r2 = 6, r1 = the record count
# Effects still take the first free record from 0 up, so they only reach the amp-capable three when 0..5 are full.
REAL = {'tweed': dict(amp='HD2_AmpTweedBluesBrt', host='HD2_DistArbitratorFuzzMono', display='Tweed Blues Brt', cost=2324,
                      preset_id=37)}
FLOW_SLOT_TAB = 0x280F1A18            # word k (k = 1..8): the DSP slot symbol of block record k (record 0: movw at 0x280f116c)
BIG_RECORDS = (6, 7, 8)
BIG_SLOTS = ('fx.13', 'fx.14', 'fx.15')
REAL_AMP_LIMIT = len(BIG_SLOTS)       # was 1 in the first real-identity images (2026-11-16); the user's second amp was refused
ALLOC_BIG_VA = 0x280ED45E
ALLOC_BIG_STOCK = bytes.fromhex('104853f8228010494246e5f784fd0f48e5f781fd')     # 0x280ed45e..0x280ed471
ALLOC_BIG_NEW = (bytes.fromhex('53f82280')      # ldr.w  r8, [r3, r2, lsl #2]   the block type's name, for the log
                 + bytes.fromhex('96f8141b')    # ldrb.w r1, [r6, #0xb14]       the flow's record count (9)
                 + bytes.fromhex('44f2f863')    # movw   r3, #0x46f8            0xb40 + 6 * 0x9f4
                 + bytes.fromhex('3344')        # add    r3, r6                 record 6
                 + bytes.fromhex('0622')        # movs   r2, #6
                 + bytes.fromhex('d8e7')        # b      0x280ed422             the LITTLE loop
                 + bytes.fromhex('00bf'))       # nop


# The amp registry (docs/findings.md, "The amp registry"). 0x280f9118(ctx, block id, &block type) keeps a list of the
# ids of amp-type blocks at dsp+0x6ec8, count at dsp+0x6ecc, and is compiled for a maximum of zero: it appends the id,
# then fails with appDsp.c:609 ERROR_NOT_ENOUGH_RESOURCES whenever the count is not 0. The list has room for one
# word before the count byte, and the removal code (0x280f969c) does not shrink it, so a later amp writes its id
# over the count and then over whatever follows. Nothing else in this build reads the list. The function becomes
# "return 0": no registry.
REGISTRY_VA, REGISTRY_STOCK, REGISTRY_NEW = 0x280F9118, bytes.fromhex('4b1c06d0'), bytes.fromhex('00207047')


def real_changes(e0, e3, amp, host, display, cost, preset_id):
    """[(address, new bytes, what)] to list `amp` under its own identity in place of `host`'s row and menu item."""
    A = pa.EFFECTS_E0
    info = pa.parse_entry3_full(e3)
    S = info['strings']
    a_idx, h_idx = pa.find_model(info, amp)['words'][2], pa.find_model(info, host)['words'][2]
    segs = pa._parse_e0_segments_any(bytearray(e0))

    def rd(va, n):
        o = pa._e0_vaddr_to_foff(segs, va, n)
        return bytes(e0[o:o + n])

    def u32(va):
        return struct.unpack('<I', rd(va, 4))[0]
    out = []
    t1 = [struct.unpack('<IHHI', rd(A.TAB1_BASE + 12 * i, 12)) for i in range(A.TAB1_CNT)]
    rows = [i for i, r in enumerate(t1) if r[0] == h_idx]
    assert len(rows) == 1 and not [r for r in t1 if r[0] == a_idx or r[1] == preset_id], 'Table 1 is not as expected'
    out.append((A.TAB1_BASE + 12 * rows[0], struct.pack('<IHHI', a_idx, preset_id, 0, cost),
                f'Table 1 row {rows[0]}: {host} (preset id {t1[rows[0]][1]}) -> {amp}, preset id {preset_id}, cost {cost}'))
    assert [1 for i in range(A.TAB2_CNT) if u32(A.TAB2_BASE + 44 * i) == a_idx], 'the amp has no Table 2 row'
    items = [(slot, u32(A.BLIST_PTR_TAB + 4 * slot) + 48 * k) for slot in range(52) if u32(A.BLIST_PTR_TAB + 4 * slot)
             for k in range(u32(A.BLIST_CNT_TAB + 4 * slot)) if u32(u32(A.BLIST_PTR_TAB + 4 * slot) + 48 * k + 4) == h_idx]
    assert len(items) == 1, 'the host must be in exactly one menu list'
    slot, va = items[0]
    old = rd(va, 48)
    assert old[8:12] == b'\xff\xff\xff\xff' and struct.unpack_from('<H', old, 12)[0] == t1[rows[0]][1]
    new = struct.pack('<IIIH', BTYPE_AMP, a_idx, 0xFFFFFFFF, preset_id) + display.encode('latin1')[:25].ljust(26, b'\0') + old[40:]
    out.append((va, new, f'menu list {slot}: the item becomes {display!r}: type {BTYPE_AMP:#x}, name index {a_idx}, preset id {preset_id}'))
    return out + runtime_changes(e0, e3)


def runtime_changes(e0, e3):
    """[(address, new bytes, what)]: what lets the application run amp blocks at all, whichever amps are listed."""
    S = pa.parse_entry3_full(e3)['strings']
    segs = pa._parse_e0_segments_any(bytearray(e0))

    def rd(va, n):
        o = pa._e0_vaddr_to_foff(segs, va, n)
        return bytes(e0[o:o + n])

    def u32(va):
        return struct.unpack('<I', rd(va, 4))[0]
    out = []
    assert rd(AMP_LIMIT_VA, 2) == AMP_LIMIT_STOCK
    out.append((AMP_LIMIT_VA, bytes([REAL_AMP_LIMIT, 0x2B]),
                f'placement check: amp blocks per DSP 0 -> {REAL_AMP_LIMIT} (cmp r3, #{REAL_AMP_LIMIT}): one per amp-capable slot'))
    for rec, name in zip(BIG_RECORDS, BIG_SLOTS):
        va = FLOW_SLOT_TAB + 4 * rec
        assert S[u32(va)] == f'fx.{rec}', 'the flow slot table is not as expected'
        out.append((va, struct.pack('<I', S.index(name)), f'flow set-up: block record {rec} uses DSP slot {name} instead of fx.{rec}'))
    assert rd(REGISTRY_VA, 4) == REGISTRY_STOCK, 'not the stock amp registry'
    out.append((REGISTRY_VA, REGISTRY_NEW, 'amp registry: `movs r0, #0; bx lr` (was: append the id, then fail unless the list is empty)'))
    assert rd(ALLOC_BIG_VA, len(ALLOC_BIG_STOCK)) == ALLOC_BIG_STOCK, 'not the stock allocator'
    out.append((ALLOC_BIG_VA, ALLOC_BIG_NEW, 'allocator: amp types take a free record among 6, 7, 8 (was: log and fail)'))
    return out
