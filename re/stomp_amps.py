#!/usr/bin/env python3
"""Write tools/amp_list.py: every amp the HX Stomp 3.80.0 lists (Amp category: Guitar, then Bass, in its menu
order) with the Stomp's preset id and DSP cost from its Table 1.

usage: .venv/bin/python re/stomp_amps.py        (needs firmware/HX_Stomp_v3.80.0_0x103966115.hxf)
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fw  # noqa: E402
from fw import pa  # noqa: E402

AMP_CATEGORY = 12                      # the Stomp's menu: 19 categories; 12 is "Amp" (lists Guitar, Bass)


def stomp_amps():
    S = fw.App(fw.STOMP_HXF)
    D = pa.E0_DEVICES[0x28D8FA80]
    info = pa.parse_entry3_full(fw.entry(S.img, 3))
    by_idx = {m['words'][2]: m for m in info['models']}
    t1 = {}
    for va in range(S.u32(D.TAB1_BASE_PTRS[0]), S.u32(D.TAB1_END_PTR), 12):
        r = struct.unpack('<IHHI', S.bytes(va, 12))
        t1[r[0]] = r
    out = []
    for lst, label in ((0, 'guitar'), (1, 'bass')):
        slot = 4 * AMP_CATEGORY + lst
        ptr, cnt = S.u32(D.BLIST_PTR_TAB + 4 * slot), S.u32(D.BLIST_CNT_TAB + 4 * slot)
        for k in range(cnt):
            bt, idx, _, pid = struct.unpack('<IIIH', S.bytes(ptr + 48 * k, 14))
            m = by_idx[idx]
            assert bt == 0x11 and (m.get('meta') or {}).get('category') == 'amp' and t1[idx][1] == pid
            out.append((m['name'], pid, t1[idx][3], label, m['displayName']))
    return out


if __name__ == '__main__':
    rows = stomp_amps()
    path = os.path.join(HERE, '..', 'tools', 'amp_list.py')
    with open(path, 'w') as f:
        f.write('"""Every amp the HX Stomp 3.80.0 lists, in its menu order (guitar, then bass): (model, the Stomp\'s preset id,\n'
                'its DSP cost). Written by re/stomp_amps.py from the Stomp firmware; tools/verify_amps.py checks each row\n'
                'against that firmware again."""\n\nSTOMP_AMPS = (\n')
        for name, pid, cost, label, disp in rows:
            f.write(f'    ({name!r}, {pid}, {cost}),{" " * max(1, 34 - len(name))}# {label}: {disp}\n')
        f.write(')\n')
    print(f'{len(rows)} amps ({sum(r[3] == "guitar" for r in rows)} guitar, {sum(r[3] == "bass" for r in rows)} bass) -> tools/amp_list.py')
