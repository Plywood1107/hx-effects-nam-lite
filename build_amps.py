#!/usr/bin/env python3
"""Build the Amps-group image: Line 6's HX Effects 3.80.0 firmware + the memory window + what lets amp blocks run
(tools/amp_patch.py, runtime_changes) + an "Amps" list under Distortion holding real amp models, with no stock block
replaced (tools/amps_group.py). Entry 3 is untouched; Entry 0 gains one data segment.

usage: .venv/bin/python build_amps.py [--set tweed|fifteen|all] [--base nam | --base-file IMAGE.hxf --base-check SCRIPT [ARG]]

Writes build/HX_Effects_v3.80.0_MemWin_Amps_<set>.hxf and build/amps_<set>_manifest.json.
--base nam   start from the NAM + Click image (build_nam_click.py --nam-host regal, the image hx-effects-nam-lite's
             `build.py nam` makes, byte for byte) instead of stock: NAM on the Regal Bass DI, Click on the mono
             Mod/Chorus Echo, then the same amp changes. Writes ..._MemWin_NAM_Click_Amps_<set>.hxf and
             build/amps_<set>_nam_manifest.json.
--base-file IMAGE.hxf --base-check SCRIPT [ARG]
             start from any other image built from the stock firmware (e.g. hx-effects-nam-lite's full build). SCRIPT
             (with ARG, e.g. its manifest) is that image's own verifier: it must end ALL OK, here and again in
             tools/verify_amps.py. Writes build/<image>_MemWin_Amps_<set>.hxf and build/amps_<set>_<image>_manifest.json.
Check the result with tools/verify_amps.py <manifest> before flashing.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import amp_patch as ap  # noqa: E402
import amps_group as ag  # noqa: E402
import l6ia  # noqa: E402
import memwin_patch as mp  # noqa: E402
import patch_amp as pa  # noqa: E402

STOCK = os.path.join(HERE, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
STOCK_MD5 = '7c2ebdf1bffb6bcc5f89dda97f91e40c'
BASES = {'nam': ('build/HX_Effects_v3.80.0_NAM_Click_NamRegal.hxf', '24b00640596d6ff2b83b472a9f2f9ff1')}
NAM_CHECK = ['tools/verify/verify_nam_click.py', 'build/nam_click_namregal_manifest.json']


def run(*args):
    r = subprocess.run([sys.executable, *args], cwd=HERE, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'build_amps.py: {args[0]} failed:\n{r.stdout}{r.stderr}')
    return r.stdout


def entry0(e0_stock, e3, amps):
    """(Entry 0 bytes, in-place changes, segment info) for the list of amp model names."""
    e0 = mp.apply(e0_stock)
    ch = ap.runtime_changes(e0, e3)
    more, seg, info = ag.plan(e0, e3, amps)
    ch += more
    return ag.add_segment(ap.entry0(e0, ch), info['seg_va'], seg), ch, info


def main():
    argv = sys.argv[1:]
    if '-h' in argv or '--help' in argv:
        sys.exit(__doc__)
    name = argv[argv.index('--set') + 1] if '--set' in argv else 'tweed'
    if name not in ag.SETS:
        sys.exit('build_amps.py: --set takes ' + ' or '.join(ag.SETS))
    if not os.path.isfile(STOCK) or hashlib.md5(open(STOCK, 'rb').read()).hexdigest() != STOCK_MD5:
        sys.exit(f'{STOCK}: missing or not the HX Effects 3.80.0 firmware (MD5 {STOCK_MD5}).')
    base = argv[argv.index('--base') + 1] if '--base' in argv else None
    if base is not None and base not in BASES:
        sys.exit('build_amps.py: --base takes ' + ' or '.join(BASES))
    build = os.path.join(HERE, 'build')
    os.makedirs(build, exist_ok=True)
    src, base_rel, base_md5, base_check = STOCK, None, None, None
    tag = f'_{base}' if base else ''
    out = os.path.join(build, f'HX_Effects_v3.80.0_MemWin{"_NAM_Click" if base else ""}_Amps_{name}.hxf')
    if base:
        base_rel, base_md5, base_check = BASES[base][0], BASES[base][1], NAM_CHECK
        src = os.path.join(HERE, base_rel)
        if not os.path.isfile(src) or hashlib.md5(open(src, 'rb').read()).hexdigest() != base_md5:
            sys.exit(f'{src}: missing or not the verified NAM + Click image (MD5 {base_md5}); run '
                     'build_effects.py, build_click.py, build_nam_click.py --nam-host regal and '
                     'tools/verify/verify_nam_click.py first.')
    elif '--base-file' in argv:
        src = os.path.abspath(argv[argv.index('--base-file') + 1])
        if '--base-check' not in argv:
            sys.exit('build_amps.py: --base-file needs --base-check SCRIPT [ARG], the image\'s own verifier')
        k = argv.index('--base-check') + 1
        base_check = [a for a in argv[k:k + 2] if not a.startswith('--')]
        base_rel = os.path.relpath(src, HERE)
        base_md5 = hashlib.md5(open(src, 'rb').read()).hexdigest()
        stem = os.path.splitext(os.path.basename(src))[0]
        tag = '_' + stem.replace('HX_Effects_v3.80.0_', '').lower()
        out = os.path.join(build, f'{stem}_MemWin_Amps_{name}.hxf')
    if base_check:
        rep = run(*base_check)
        if not rep.strip().endswith('ALL OK'):
            sys.exit(f'build_amps.py: the base image\'s verifier ({" ".join(base_check)}) did not end ALL OK')
    image = os.path.join(build, f'amps_{name}{tag}.l6ia')

    arc, _ = pa.load_l6ia_from_any(src)
    assert pa.select_device(arc) is pa.EFFECTS_DSP, 'not the HX Effects firmware'
    e3 = bytes(pa.get_entry_swapped(arc, 3))
    e0_stock = bytes(pa.get_entry_swapped(arc, 0))
    e0, ch, info = entry0(e0_stock, e3, ag.SETS[name])
    arc, _, _ = l6ia.rebuild_archive(arc, {0: e0})
    open(image, 'wb').write(arc)
    if 'ALL OK' not in run(os.path.join('tools', 'l6ia_verify.py'), image):
        sys.exit('build_amps.py: the image failed its checksum check')
    run(os.path.join('tools', 'hxf.py'), 'pack', image, out, '--donor', STOCK)
    man = dict(output=os.path.relpath(out, HERE), output_md5=hashlib.md5(open(out, 'rb').read()).hexdigest(),
               stock_md5=STOCK_MD5, base=base_rel, base_md5=base_md5, base_check=base_check,
               memwin=True, set=name, amps=ag.SETS[name], segment=info,
               entry0_growth=len(e0) - len(e0_stock),
               memwin_changes=[dict(address=va, length=len(new), what=what) for va, new, what in mp.changes()],
               amp_changes=[dict(address=va, length=len(new), what=what) for va, new, what in ch])
    json.dump(man, open(os.path.join(build, f'amps_{name}{tag}_manifest.json'), 'w'), indent=1)
    for va, new, what in ch:
        print(f'[+] {va:#010x} +{len(new):2d}  {what}')
    print(f'[+] new segment at {info["seg_va"]:#x}: {info["seg_len"]} bytes = Table 1 with {info["rows"]} rows, then '
          f'{len(info["amps"])} Amps item(s); Entry 0 grows by {len(e0) - len(e0_stock)} bytes; Entry 3 untouched')
    for a in info['amps']:
        print(f'      {a["display"]:18s} {a["model"]}: preset id {a["preset_id"]}, cost {a["cost"]}')
    print(f'\nDone: {os.path.relpath(out, HERE)}\nMD5 {man["output_md5"]}\n'
          f'Now run: .venv/bin/python tools/verify_amps.py build/amps_{name}{tag}_manifest.json')


if __name__ == '__main__':
    main()
