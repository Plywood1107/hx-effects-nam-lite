#!/usr/bin/env python3
"""Write host_params.json: for each stock model the firmware builds take over, its parameters as the unit numbers
them (name, slot id, type: 1 bool, 2 int, 3 float). The preset builder uses it to decide which of an effect's knobs
HX Edit can carry in a .hlx (only those whose slot id and type match a parameter of the host).

Needs the stock firmware and numpy (as the builders do):
    python3 tools/preset-builder/dump_host_params.py firmware/HX_Effects_v3.80.0_0xd97239907.hxf
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [REPO, os.path.join(REPO, 'tools')]

import patch_amp as pa  # noqa: E402
from firmware_models import takeover_hosts  # noqa: E402


def main():
    fw = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
    l6, _ = pa.load_l6ia_from_any(fw)
    e3 = pa.get_entry_swapped(l6, 3)
    info = pa.parse_entry3_full(e3)
    out = {}
    for host in sorted(takeover_hosts()):
        m = pa.find_model(info, host)
        out[host] = [{'name': p['name'], 'slot': struct.unpack_from('<5I3I', e3, p['off'])[4], 'type': p['type']}
                     for p in m['params']]
    path = os.path.join(HERE, 'host_params.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
        f.write('\n')
    print(f'Wrote {os.path.relpath(path, REPO)}: {len(out)} hosts')


if __name__ == '__main__':
    main()
