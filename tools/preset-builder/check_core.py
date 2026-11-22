#!/usr/bin/env python3
"""check_core.py - preset-core.js builds byte for byte what tools/preset_send.py builds.

usage: .venv/bin/python tools/preset-builder/check_core.py PRESET.bin... [--n N] [--build full]
Random specs (any model of the build, random knob values, both paths, IR blocks, footswitches, snapshots) are built on
each base preset by both, with node running preset-core.js; any difference is printed. Base presets: blobs read from
the unit (preset_send.py read). Needs node and fw-models.js (extract_fw_tables.py).
"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), ''))
sys.path.insert(0, os.path.dirname(HERE))
import preset_send as ps  # noqa: E402

NODE = r"""
global.window = {}; require(process.argv[2]); const P = require(process.argv[3]); const fs = require('fs');
const jobs = JSON.parse(fs.readFileSync(process.argv[4], 'utf8')), models = window.FW_MODELS.builds[jobs.build];
const out = jobs.items.map(j => { try { return Buffer.from(P.build(new Uint8Array(Buffer.from(j.base, 'hex')), j.spec, models, j.irs)).toString('hex'); }
  catch (e) { return 'ERR ' + e.message; } });
fs.writeFileSync(process.argv[5], JSON.stringify(out));
"""


def fin(x, d):
    return d if x != x else x


def rand_spec(rng, by_name, irs, nsnap):
    names = [n for n, m in by_name.items() if m['btype'] != ps.IR_TYPE]
    ir_models = [n for n, m in by_name.items() if m['btype'] == ps.IR_TYPE]
    positions = rng.sample(list(ps.PATH_A) + list(ps.PATH_B), rng.randint(1, 6))
    blocks, fss = [], rng.sample(range(1, 7), 6)
    for pos in positions:
        if ir_models and irs and rng.random() < 0.2:
            nm = rng.choice(ir_models)
        else:
            nm = rng.choice(names)
        m = by_name[nm]
        vals = []
        for p in m['params']:
            lo, hi = fin(p['min'], 0), fin(p['max'], 10)
            vals.append(rng.random() < 0.5 if p['type'] == 1 else rng.randint(int(lo), int(max(lo, hi))) if p['type'] == 2
                        else round(rng.uniform(lo, hi if hi > lo else lo + 1), 4))
        if m['btype'] == ps.IR_TYPE:
            vals[0] = rng.choice(sorted(irs))
        b = {'pos': pos, 'model': nm, 'values': vals if rng.random() < 0.7 else
             {p['name']: v for p, v in zip(m['params'], vals) if rng.random() < 0.5}, 'on': rng.random() < 0.7}
        if rng.random() < 0.5:
            b['footswitch'] = rng.randint(1, 6)
            if rng.random() < 0.5:
                b['label'] = 'Lbl %d' % pos
        if rng.random() < 0.2:
            b['midi_bypass'] = rng.randint(4, 90)
        if rng.random() < 0.2:
            b['snapshot_bypass'] = False
        blocks.append(b)
    spec = {'blocks': blocks}
    ctl = []
    for b in blocks:
        m = by_name[b['model']]
        if m['params'] and rng.random() < 0.4:
            ki = rng.randrange(len(m['params']))
            p = m['params'][ki]
            c = {'pos': b['pos'], 'knob': p['name'] if rng.random() < 0.5 else ki,
                 'source': rng.choice(['exp1', 'exp2', 'midi'] + [f'fs{n}' for n in range(1, 7)])}
            if c['source'] == 'midi':
                c['cc'] = rng.randint(4, 90)
            if rng.random() < 0.5 and p['type'] == 3:
                lo, hi = fin(p['min'], 0), fin(p['max'], 10)
                c['min'], c['max'] = round(rng.uniform(lo, hi), 3), round(rng.uniform(lo, hi), 3)
            if c['source'].startswith('fs') and rng.random() < 0.5:
                c['label'] = 'K%d' % b['pos']
            ctl.append(c)
    if ctl:
        spec['controls'] = ctl
    if rng.random() < 0.3:
        spec['split'], spec['merge'] = rng.randint(0, 5), rng.randint(6, 10)
    if rng.random() < 0.7:
        sn = {'current': rng.randint(1, nsnap)}
        if rng.random() < 0.5:
            sn['names'] = ['S%d' % k for k in range(nsnap)]
        sn['states'] = {str(b['pos']): [rng.random() < 0.5 for _ in range(nsnap)] for b in blocks if rng.random() < 0.5}
        kn = []
        for b in blocks:
            m = by_name[b['model']]
            if m['params'] and rng.random() < 0.6:
                ki = rng.randrange(len(m['params']))
                p = m['params'][ki]
                lo, hi = fin(p['min'], 0), fin(p['max'], 10)
                vals = [rng.random() < 0.5 if p['type'] == 1 else rng.randint(int(lo), int(max(lo, hi)))
                        if p['type'] == 2 else round(rng.uniform(lo, hi if hi > lo else lo + 1), 4) for _ in range(nsnap)]
                kn.append({'pos': b['pos'], 'knob': p['name'] if rng.random() < 0.5 else ki, 'values': vals})
        sn['knobs'] = kn
        spec['snapshots'] = sn
    return spec


def main():
    a = sys.argv[1:]
    n = int(a[a.index('--n') + 1]) if '--n' in a else 30
    build = a[a.index('--build') + 1] if '--build' in a else 'full'
    bases = [x for x in a if x.endswith('.bin')]
    image = {'full': ps.DEFAULT_IMAGE}.get(build) or os.path.join(os.path.dirname(os.path.dirname(HERE)), 'build',
                                                                    {'nam': 'HX_Effects_v3.80.0_NAM.hxf', 'amps': 'HX_Effects_v3.80.0_NAM_Amps.hxf'}[build])
    by_name, _ = ps.model_table(image)
    irs = {25: '37a0365e97506b9a618a04e8bcb15ea9', 26: 'f99ebfa6c7a52c298636ad8c0039c3cd'}
    rng = random.Random(1)
    items, want = [], []
    for base_path in bases:
        base = open(base_path, 'rb').read()
        nsnap = len(ps.parse_blob(base)[1][10][10])
        for _ in range(n):
            spec = rand_spec(rng, by_name, irs, nsnap)
            try:
                want.append(ps.build_preset(base, spec, by_name, irs).hex())
            except SystemExit as e:
                want.append('ERR ' + str(e))
            items.append({'base': base.hex(), 'spec': spec, 'irs': {str(k): v for k, v in irs.items()}})
    tmp = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'check_core')
    json.dump({'build': build, 'items': items}, open(tmp + '.in.json', 'w'))
    subprocess.run(['node', '-e', NODE, '-', os.path.join(HERE, 'fw-models.js'), os.path.join(HERE, 'preset-core.js'),
                    tmp + '.in.json', tmp + '.out.json'], check=True)
    got = json.load(open(tmp + '.out.json'))
    agree = lambda g, w: g == w or (g.startswith('ERR') and w.startswith('ERR'))   # both refuse the spec
    same = sum(agree(g, w) for g, w in zip(got, want))
    errs = sum(w.startswith('ERR') for w in want)
    print(f'{same} of {len(want)} agree: identical bytes, or both refuse the spec ({errs} refused)')
    shown = 0
    for i, (g, w) in enumerate(zip(got, want)):
        if not agree(g, w) and shown < 5:
            shown += 1
            if g.startswith('ERR') or w.startswith('ERR'):
                print(f'  #{i}: python {w[:120]!r} / js {g[:120]!r}')
            else:
                k = next(j for j in range(min(len(g), len(w))) if g[j] != w[j]) if len(g) != len(w) or g != w else 0
                print(f'  #{i}: first difference at byte {k // 2}: py {w[k - 20:k + 20]} js {g[k - 20:k + 20]}')
    sys.exit(0 if same == len(want) else 1)


if __name__ == '__main__':
    main()
