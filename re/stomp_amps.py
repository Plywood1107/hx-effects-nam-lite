#!/usr/bin/env python3
"""Write tools/amp_list.py and tools/preamp_list.py: every amp and every preamp the HX Stomp 3.80.0 lists (its Amp
category: Guitar, Bass; its Preamp category: Guitar, Bass, Mic; each in its menu order) with the Stomp's preset id
and DSP cost from its Table 1.

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
PREAMP_CATEGORY = 13                   # 13 is "Preamp" (lists Guitar, Bass, Mic)
LISTS = {AMP_CATEGORY: ('guitar', 'bass'), PREAMP_CATEGORY: ('guitar', 'bass', 'mic')}
KIND = {AMP_CATEGORY: 'amp', PREAMP_CATEGORY: 'preamp'}


def stomp_models(category=AMP_CATEGORY):
    """[(model, preset id, cost, list label, display name)] for one of the Stomp's amp-type categories."""
    S = fw.App(fw.STOMP_HXF)
    D = pa.E0_DEVICES[0x28D8FA80]
    info = pa.parse_entry3_full(fw.entry(S.img, 3))
    by_idx = {m['words'][2]: m for m in info['models']}
    t1 = {}
    for va in range(S.u32(D.TAB1_BASE_PTRS[0]), S.u32(D.TAB1_END_PTR), 12):
        r = struct.unpack('<IHHI', S.bytes(va, 12))
        t1[r[0]] = r
    out = []
    for lst, label in enumerate(LISTS[category]):
        slot = 4 * category + lst
        ptr, cnt = S.u32(D.BLIST_PTR_TAB + 4 * slot), S.u32(D.BLIST_CNT_TAB + 4 * slot)
        for k in range(cnt):
            bt, idx, _, pid = struct.unpack('<IIIH', S.bytes(ptr + 48 * k, 14))
            m = by_idx[idx]
            assert bt == 0x11 and (m.get('meta') or {}).get('category') == KIND[category] and t1[idx][1] == pid, m['name']
            out.append((m['name'], pid, t1[idx][3], label, m['displayName']))
    return out


def stomp_amps():
    return stomp_models(AMP_CATEGORY)


def write(path, var, what, rows):
    with open(path, 'w') as f:
        f.write(f'"""Every {what} the HX Stomp 3.80.0 lists, in its menu order ({", then ".join(sorted({r[3] for r in rows}, key=[r[3] for r in rows].index))}): '
                '(model, the Stomp\'s preset id,\nits DSP cost). Written by re/stomp_amps.py from the Stomp firmware; '
                'tools/verify_amps.py checks each row\nagainst that firmware again."""\n\n' + f'{var} = (\n')
        for name, pid, cost, label, disp in rows:
            f.write(f'    ({name!r}, {pid}, {cost}),{" " * max(1, 34 - len(name))}# {label}: {disp}\n')
        f.write(')\n')


if __name__ == '__main__':
    tools = os.path.join(HERE, '..', 'tools')
    amps = stomp_models(AMP_CATEGORY)
    write(os.path.join(tools, 'amp_list.py'), 'STOMP_AMPS', 'amp', amps)
    print(f'{len(amps)} amps ({sum(r[3] == "guitar" for r in amps)} guitar, {sum(r[3] == "bass" for r in amps)} bass) -> tools/amp_list.py')
    pre = stomp_models(PREAMP_CATEGORY)
    write(os.path.join(tools, 'preamp_list.py'), 'STOMP_PREAMPS', 'preamp', pre)
    print(f'{len(pre)} preamps ({", ".join(f"{sum(r[3] == x for r in pre)} {x}" for x in LISTS[PREAMP_CATEGORY])}) -> tools/preamp_list.py')
