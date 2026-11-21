"""What this repo's firmware builds add, for the preset builder: read from the build scripts themselves, so the
builder follows them (no numpy, no firmware needed).

Builds, in order (build.py): nam = NAM A2 Lite + Click; amps = nam + the HX Stomp's amps and preamps; full = amps +
the effects build_all.py makes by default. Each custom effect keeps the identity of the stock model it takes over
(mono version only), so a preset stores it as that host; amps and preamps keep their own HX Stomp identities.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [REPO, os.path.join(REPO, 'tools')]

import build_all as ba  # noqa: E402
import build_click as bc  # noqa: E402
import build_effects as be  # noqa: E402
from nam_host import NAM_HOSTS, NAM_LIST_SLOTS  # noqa: E402
from amp_list import STOMP_AMPS  # noqa: E402
from preamp_list import STOMP_PREAMPS  # noqa: E402

BUILDS = ('stock', 'nam', 'amps', 'full')
NAM_HOST = NAM_HOSTS['regal']          # build.py uses --nam-host regal for every mode
FULL_EFFECTS = ('geiger',) + tuple(ba.DEFAULT_EXTRAS)   # what a plain build_all.py adds beside NAM and Click

# build-script knob kinds -> HelixControls display types (fw_* are defined in extract_hx_data.py)
KIND_DISPLAY = {'knob': 'generic_knob', 'percent': 'percent', 'db': 'fw_db', 'hz': 'fw_hz'}


def _nam_params():
    """patch_amp.NAM_PARAMS without importing patch_amp (it needs numpy): a plain literal."""
    src = open(os.path.join(REPO, 'tools', 'patch_amp.py')).read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == 'NAM_PARAMS':
            return ast.literal_eval(node.value)
    raise SystemExit('NAM_PARAMS not found in tools/patch_amp.py')


def _base(symbol):
    """HX Edit 3.x names a model once, with @stereo; the firmware names the mono version '...Mono'."""
    return symbol[:-4] if symbol.endswith('Mono') else symbol


def takeover_hosts():
    return {NAM_HOST, bc.TAKEOVER} | {ba.EFFECTS[k]['takeover'] for k in FULL_EFFECTS}


def _knob(slot, name, value_type, lo, hi, default, display=None, labels=None):
    p = {'symbolicID': f'slot{slot}', 'slot': slot, 'name': name, 'valueType': value_type,
         'min': lo, 'max': hi, 'default': default}
    if display:
        p['displayType'] = display
    if labels:
        p['labels'] = labels
    return p


def _spec_knob(t):
    slot, _pid, _m, _p, disp, _short, kind, rng, dflt = t
    if kind == ba.LIST:
        keys = sorted(rng)
        return _knob(slot, disp, 0, keys[0], keys[-1], dflt, labels={str(k): v for k, v in rng.items()})
    if kind == ba.BOOL:
        return _knob(slot, disp, 2, False, True, bool(dflt), labels={'0': rng[0], '1': rng[1]})
    return _knob(slot, disp, 1, rng[0], rng[1], dflt, display=KIND_DISPLAY[kind])


def _sync_knobs(spec, hx, host):
    """Time + the knobs + SyncSelect1/TempoSync1, numbered as build_all.sync_knob_params / build_click do."""
    knobs = [t for t in spec if t[0] != 1]
    n = len(knobs) + 1
    tm = next(p for p in hx[host]['params'] if p['symbolicID'] == 'Time')
    sel = next(p for p in hx[host]['params'] if p['symbolicID'] == 'SyncSelect1')
    return ([_knob(1, 'Time', 1, 0.1, 4.0, 0.5, display=tm.get('displayType_stereo') or tm['displayType'])]
            + [_spec_knob(t) for t in knobs]
            + [_knob(n + 1, 'Note Sync', 0, 1, 19, 6, display=sel['displayType']),
               _knob(n + 2, 'Tempo Sync', 2, False, True, True, display='off_on')])


def _nam_knobs(hx):
    out = []
    for slot, mname, pname, _pid, disp, dflt in _nam_params():
        if pname == 'Index':   # nam_host.nam_off_ir: Model is a list of User IR slots 1..21
            out.append(_knob(slot, 'Model', 0, 1, NAM_LIST_SLOTS, 1,
                             labels={str(k): str(k) for k in range(1, NAM_LIST_SLOTS + 1)}))
            continue
        t = next(p for p in hx[_base(mname)]['params'] if p['symbolicID'] == pname)
        out.append(_knob(slot, disp or t['name'], t['valueType'], t['min'], t['max'],
                         t['default'] if dflt is None else dflt, display=t.get('displayType')))
    return out


def custom_models(hx):
    """The custom effects as builder models. `hx` maps HX Edit model id -> its .models record."""
    defs = [('nam', be.NAME, be.DISPLAY, NAM_HOST, be.DSP_COST, _nam_knobs(hx)),
            ('nam', bc.NAME, bc.DISPLAY, bc.TAKEOVER, bc.DSP_COST,
             _sync_knobs(bc.CLICK_PARAMS, hx, _base(bc.TAKEOVER)))]
    for k in FULL_EFFECTS:
        e = ba.EFFECTS[k]
        knobs = (_sync_knobs(e['params'], hx, _base(e['takeover'])) if e.get('sync')
                 else [_spec_knob(t) for t in e['params']])
        defs.append(('full', e['name'], e['display'], e['takeover'], e['cost'], knobs))
    out = []
    for build, name, display, host, cost, knobs in defs:
        h = hx[_base(host)]
        out.append({'id': name, 'name': display, 'category': h['category'], 'mono': True, 'stereo': False,
                    'fw': {'build': build, 'host': _base(host), 'hostSymbol': host, 'cost': cost},
                    'params': knobs + [{'symbolicID': '@enabled', 'name': 'Enabled', 'valueType': 2,
                                        'min': False, 'max': True, 'default': True}]})
    return out


def amp_builds():
    """HX Edit model id -> the build that adds it (amps and preamps arrive with 'amps')."""
    return {m: 'amps' for m, _id, _cost in STOMP_AMPS + STOMP_PREAMPS}
