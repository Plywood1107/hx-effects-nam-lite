"""A "Cabs" list under EQ holding Line 6's legacy single cabs (block type 0x0f, CAB_SINGLE), the 41 the HX Stomp
lists, under their own identities (docs/amps-findings.md, "Legacy cabs").

The menu side goes with the amps (tools/amps_group.py, plan(..., cabs=...)): one Table 1 row per cab, appended after
the amps' and preamps' rows in the moved table ({name index, the Stomp's preset id, 0, 720}), and 41 menu items in
EQ's fourth list, "Cabs".

No dual cabs (0x10, CAB_DUAL): the HX Effects has no screen to choose a dual's second cab, so a dual item could only
play one cab twice (tried on the unit, 2026-11-27); a cab in each path does the same job. The user's choice: drop
them and allow two single cabs per DSP.

The code side (code_changes): one change. The placement check (0x280f221c) tests the per-DSP cab count (recounted
from the block records by 0x280f0b8c, at +0xae4) minus the old block's weight plus the new one's against a limit;
stock allows none. A single cab weighs 1 cab, no amp, no IR, and runs in a LITTLE record (any of them, as an effect),
so the amp limit and records are untouched:

    0x280f22a8   cab blocks per DSP 0 -> 2 (`cmp r4, #2`)

The stock weights for a dual (two cabs, no amp) stay: a dual can't be chosen from the menu, and one arriving in a
preset would count as both cabs.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_amp as pa  # noqa: E402
from cab_list import STOMP_CABS  # noqa: E402

BTYPE_SINGLE = 0x0F
CAT_EQ, CABS_LIST = 2, 3                 # EQ: Mono, Stereo, Preamps (tools/amps_group.py), then Cabs
GROUP_NAME = 'Cabs'
DISPLAY_MAX = 16                         # menu names stop at 16 characters
CAB_LIMIT = 2                            # cab blocks per DSP (user, 2026-11-27)
# model -> (the HX Stomp's preset id, DSP cost, display name)
CABS = {n: (pid, cost, disp) for n, pid, cost, disp in STOMP_CABS}
SETS = {'none': [], 'all': [n for n, *_ in STOMP_CABS]}

CAB_LIMIT_VA, CAB_LIMIT_STOCK = 0x280F22A8, bytes.fromhex('002c')     # cmp r4, #0
CAB_LIMIT_NEW = bytes([CAB_LIMIT, 0x2c])                              # cmp r4, #2


def item(btype, idx, idx2, pid, display):
    """A 48-byte menu item, laid out as the HX Stomp's cab items."""
    assert len(display) <= DISPLAY_MAX, display
    return struct.pack('<IIIH', btype, idx, idx2, pid) + display.encode('latin1').ljust(26, b'\0') + struct.pack('<II', 1, 0)


def code_changes(e0):
    """[(address, new bytes, what)]: up to CAB_LIMIT single cab blocks per DSP."""
    segs = pa._parse_e0_segments_any(bytearray(e0))
    o = pa._e0_vaddr_to_foff(segs, CAB_LIMIT_VA, 2)
    assert bytes(e0[o:o + 2]) == CAB_LIMIT_STOCK, 'the cab limit is not stock (cmp r4, #0)'
    return [(CAB_LIMIT_VA, CAB_LIMIT_NEW, f'placement check: cab blocks per DSP 0 -> {CAB_LIMIT} (cmp r4, #{CAB_LIMIT})')]
