#!/usr/bin/env python3
"""dsp_load.py - measure the HX Effects' DSP load with the probe image's "Probe" block and the Mac's microphone.

usage:
  .venv/bin/python tools/dsp_load.py listen [--seconds S] [--device NAME] [--save REC.wav]
        record the unit's output from a microphone (default: the Mac's own), decode the Probe's frames, print the load
  .venv/bin/python tools/dsp_load.py measure SLOT [MODEL ...] [--seconds S] [--device NAME] [--save REC.wav]
        build a preset in SLOT with the MODELs (firmware model names, as preset_send.py models lists them) on the
        main path and the Probe after them, switch to it, listen, then put SLOT back exactly as it was and switch back
        to the preset that was loaded. No MODEL: the Probe alone (the base load).
  .venv/bin/python tools/dsp_load.py sweep SLOT [--categories amp,reverb,...] [--start N] [--limit N] [--only M1,M2] [--seconds S]
                                                               [--out FILE.jsonl]
        every model alone with the Probe after it, in SLOT (backed up once, put back at the end), heavy categories
        first, the base (the Probe alone) again every 25 models; a line of JSON a result (build/dsp_load/); stops if
        the base gives no frames after three silent models
  .venv/bin/python tools/dsp_load.py models                    the models a sweep goes through, in its order
  .venv/bin/python tools/dsp_load.py decode REC.wav            a recording made before
  .venv/bin/python tools/dsp_load.py selftest                  the C reference's frames, through a simulated path

Needs: the probe image on the unit (python build.py full -- --hostprobe; Drum Chapel's place, Delay > Mono >
"Probe"), HX Edit closed, ffmpeg (brew install ffmpeg), and the unit's output audible to the microphone (an amp or
monitor; turn it up until the bursts are clearly heard, not distorted). The Probe must be the last block, with Mode on
Load (this tool sets it): it replaces the sound with its bursts, one every 2.22 s of 10 ms tones, so a 12 s
recording holds four or five frames.

The load: the DSP's idle word (DM 0xc28c9 on the HX Effects, its HX Stomp twin at 0xc2fd5), read by the Probe every
16-sample call. Each frame carries its value at the frame's start and its lowest since the last frame (the busiest
moment). On the HX Stomp the word reads as the idle percentage of a call, 1,509 cycles a point, so a call is about
150,900 cycles. This tool prints the raw word and the load it implies under that reading; check the first readings
against an empty preset before relying on the scale.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import input_level as il  # noqa: E402

PY = sys.executable
PROBE_IMAGE = os.path.join(ROOT, 'build', 'HX_Effects_v3.80.0_NAM_Amps_Effects_HostProbe.hxf')
PROBE_MODEL = 'VIC_DelayRatchetMono'        # Drum Chapel's host; the probe image puts the Probe there
LOAD = 2                                    # the Probe's Mode Load: 6 words of 10 ms symbols, a frame 2.22 s
MAGIC_L, LSYM, LPILOT, LNWORDS = 0x5052424C, 480, 20, 6
DEVICE = 'MacBook Air Microphone'
LEVEL = 0.5                                 # the Probe's Level knob: its bursts' peak (1.0 = full scale)
CYCLES_A_POINT = 1509                       # the HX Stomp's calibration (nocaseguy, KIT_UNIT_MEASUREMENTS.md)


RECORDER = os.path.join(ROOT, 'build', 'mac_record')


def record(seconds, device, path):
    """Record from the Mac's default input with tools/mac_record.swift (built on first use), which keeps every
    sample; ffmpeg only if there is no Swift (its AVFoundation capture drops 5-10% of the buffers on this Mac, which
    breaks frames: --device then picks its input)."""
    src = os.path.join(HERE, 'mac_record.swift')
    if shutil.which('swiftc') and (not os.path.isfile(RECORDER) or os.path.getmtime(RECORDER) < os.path.getmtime(src)):
        subprocess.run(['swiftc', '-O', src, '-o', RECORDER], check=True, capture_output=True)
    if os.path.isfile(RECORDER):
        r = subprocess.run([RECORDER, str(seconds), path], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f'dsp_load.py: recording failed: {(r.stdout + r.stderr).strip()[-300:]}')
        x, rate = il.read_wav(path)
        return (x[:, 0] if x.ndim > 1 else x), rate
    if not shutil.which('ffmpeg'):
        sys.exit('dsp_load.py: ffmpeg not found (brew install ffmpeg)')
    r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'avfoundation', '-i', f':{device}',
                        '-t', str(seconds), '-ac', '1', '-ar', '48000', '-y', path], capture_output=True, text=True)
    if r.returncode or not os.path.isfile(path):
        sys.exit(f'dsp_load.py: recording from {device!r} failed: {r.stderr.strip()[-300:]}\n'
                 '(the devices: ffmpeg -f avfoundation -list_devices true -i "")')
    x, rate = il.read_wav(path)
    return (x[:, 0] if x.ndim > 1 else x), rate


def f32(u):
    return struct.unpack('<f', struct.pack('<I', u))[0]


def reading(u):
    """The idle word as a percentage, if it reads as one (float 0..100, else an integer 0..100), else None."""
    f = f32(u)
    if 0.0 <= f <= 100.0 and u != 0:
        return f
    if u <= 100:
        return float(u)
    return None


def ldecode(x, rate):
    """The Probe's Load frames (Mode Load) in a recording: [sync, magic, frames, idle now, idle lowest, sum].
    The pilot first (input_level.decode); if that finds nothing, a search for the sync word itself, for a path that
    loses the 6 kHz pilot (a laptop's microphone off-axis to a guitar speaker hears 2 and 4 kHz, hardly 6)."""
    got = [w for w in il.decode(x, rate, LSYM, LPILOT, LNWORDS) if w[1] == MAGIC_L]
    return got or sync_search(x, rate)


def sync_search(x, rate, max_wrong=3):
    """Frames found by their sync word alone: 2 and 4 kHz powers on a grid of 1/8 symbol, each candidate start's 32
    sync bits compared at once, the best start in each run of matches read out and kept if its checksum holds."""
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean()
    sps = LSYM * rate / 48000.0
    hop = sps / 8
    tn = il.Tones(x, rate)
    grid = np.arange(0, len(x) - sps, hop)
    a, b = np.round(grid + 0.2 * sps).astype(np.int64), np.round(grid + 0.8 * sps).astype(np.int64)
    p0, p1 = tn.power(il.F0, a, b), tn.power(il.F1, a, b)
    floor = {il.F0: float(np.percentile(p0, 10)) / 0.6, il.F1: float(np.percentile(p1, 10)) / 0.6}
    q0, q1 = np.maximum(p0 - 0.6 * floor[il.F0], 0), np.maximum(p1 - 0.6 * floor[il.F1], 0)
    gain = {il.F0: max(float(np.percentile(q0, 98)), 1e-30), il.F1: max(float(np.percentile(q1, 98)), 1e-30)}
    bit = (q1 / gain[il.F1] > q0 / gain[il.F0]).astype(np.int8)
    want = np.array([(il.SYNC >> (31 - j)) & 1 for j in range(32)], dtype=np.int8)
    n = len(bit) - 8 * (32 * LNWORDS)
    if n <= 0:
        return []
    idx = np.arange(n)[:, None] + 8 * np.arange(32)[None, :]
    wrong = (bit[idx] != want[None, :]).sum(axis=1)
    frames, i = [], 0
    while i < n:
        if wrong[i] > max_wrong:
            i += 1
            continue
        j = i
        while j < n and wrong[j] <= max_wrong:
            j += 1
        k = i + int(np.argmin(wrong[i:j]))
        for start in (grid[k] + d * hop / 4 for d in range(-4, 5)):
            bits, _ = il.bits_at(tn, start, sps, 32 * LNWORDS, gain, floor)
            w = il.words_of(bits)
            if len(w) == LNWORDS and w[0] == il.SYNC and w[1] == MAGIC_L and w[5] == sum(w[1:5]) & 0xFFFFFFFF:
                frames.append(w)
                break
        i = j + 8 * 32 * LNWORDS
    return frames


def report(frames, out=print):
    """Print each Load frame's idle words and the load they imply; return [(load now, load peak)] in percent."""
    if not frames:
        out('no frames decoded: is the Probe last on the path, Mode on Report, and its bursts clearly audible to the '
            'microphone (not distorted)?')
        return []
    res = []
    for w in frames:
        now, low = w[3], w[4]
        pn, pl = reading(now), reading(low)
        line = f'frame {w[2]:4d}: idle word {now:#010x} (float {f32(now):.4g}), lowest {low:#010x} (float {f32(low):.4g})'
        if pn is not None and pl is not None:
            ln, lp = 100.0 - pn, 100.0 - pl
            res.append((ln, lp))
            line += f'  ->  load {ln:5.1f}% (~{ln * CYCLES_A_POINT:,.0f} cycles), peak {lp:5.1f}%'
        out(line)
    if res:
        a = np.array(res)
        out(f'load over {len(res)} frames: mean {a[:, 0].mean():.1f}%, peak {a[:, 1].max():.1f}% '
            f'(100% = about {100 * CYCLES_A_POINT:,} cycles a 16-sample call, if the HX Stomp\'s scale holds)')
    return res


def listen(seconds, device, save=None, out=print):
    path = save or os.path.join(tempfile.mkdtemp(prefix='dsp_load-'), 'rec.wav')
    out(f'listening for {seconds} s ...')
    x, rate = record(seconds, device, path)
    pk = float(np.abs(x).max()) if len(x) else 0.0
    out(f'recorded {len(x) / rate:.1f} s, peak {20 * np.log10(max(pk, 1e-9)):.1f} dBFS' +
        ('  (clipping: turn the unit down)' if pk > 0.99 else '') + (f'; saved {path}' if save else ''))
    return report(ldecode(x, rate), out)


def ps(*args, check=True):
    r = subprocess.run([PY, os.path.join(HERE, 'preset_send.py'), *args], capture_output=True, text=True, cwd=ROOT)
    if check and r.returncode:
        raise SystemExit(f'preset_send.py {" ".join(args)} failed:\n{(r.stdout + r.stderr).strip()[-600:]}')
    return r.stdout.strip()


def measure(slot, models, seconds, device, save=None):
    if not os.path.isfile(PROBE_IMAGE):
        sys.exit(f'dsp_load.py: {os.path.relpath(PROBE_IMAGE, ROOT)} not found: python build.py full -- --hostprobe')
    if len(models) > 8:
        sys.exit('dsp_load.py: at most 8 models (the Probe takes the ninth place on the main path)')
    cur = ps('current').split()
    back_to = cur[1] if len(cur) > 1 else None
    tmp = tempfile.mkdtemp(prefix='dsp_load-')
    backup = os.path.join(tmp, 'backup')
    print(ps('read', slot, backup))
    old_name = json.load(open(backup + '.json')).get('name') or 'New Preset'
    blocks = [dict(pos=k + 1, model=m, on=True) for k, m in enumerate(models)]
    blocks.append(dict(pos=len(models) + 1, model=PROBE_MODEL, on=True, values=[0.5, LOAD, LEVEL]))
    spec = dict(name='DSP Load Test', split=1, merge=10, blocks=blocks)
    sp = os.path.join(tmp, 'spec.json')
    json.dump(spec, open(sp, 'w'))
    try:
        print(ps('build', slot, sp, '--image', PROBE_IMAGE))
        print(ps('load', slot))
        time.sleep(2.0)                                   # let the preset settle before listening
        res = listen(seconds, device, save)
    finally:
        print(ps('write', slot, backup + '.bin', old_name))
        if back_to:
            print(ps('load', back_to, check=False))
    return res


ORDER = ['amp', 'preamp', 'distortion', 'reverb', 'pitch', 'synth', 'delay', 'modulation', 'filter', 'dynamics', 'wah',
         'eq', 'cab', 'volume']
SKIP = ('Looper', 'Send', 'Return', 'FxLoop', 'FXLoop', 'ImpulseResponse', PROBE_MODEL)


def sweep_models(categories=None):
    """[(model, display, category)] of the probe image, heavy categories first; loops, sends/returns, IR blocks (they
    need an IR's MD5) and the Probe left out."""
    import patch_amp as pa
    import preset_send as ps_
    table = ps_.model_table(PROBE_IMAGE)[0]
    arc, _ = pa.load_l6ia_from_any(PROBE_IMAGE)
    pa.select_device(arc)
    info = pa.parse_entry3_full(bytes(pa.get_entry_swapped(arc, 3)))
    meta = {m['name']: m for m in info['models']}
    out = []
    for name in table:
        if not isinstance(name, str) or any(s in name for s in SKIP):
            continue
        m = meta.get(name) or {}
        cat = (m.get('meta') or {}).get('category', '?')
        if categories and cat not in categories:
            continue
        out.append((name, m.get('displayName', ''), cat))
    out.sort(key=lambda t: (ORDER.index(t[2]) if t[2] in ORDER else len(ORDER), t[0]))
    return out


def sweep(slot, seconds, device, outfile, categories=None, start=0, limit=None, base_every=25, only=None):
    """Each model alone with the Probe after it, in SLOT (backed up first, put back at the end); a line of JSON a
    result in OUTFILE. Stops when the base gives no frames after three silent models in a row."""
    models = sweep_models(categories)[start:]
    if only:
        models = [m for m in models if m[0] in only]
    if limit:
        models = models[:limit]
    tmp = tempfile.mkdtemp(prefix='dsp_load-')
    backup = os.path.join(tmp, 'backup')
    print(ps('read', slot, backup))
    old_name = json.load(open(backup + '.json')).get('name') or 'New Preset'
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    fh = open(outfile, 'a')
    quiet = lambda *a: None

    def one(blocks_models, label):
        blocks = [dict(pos=k + 1, model=m, on=True) for k, m in enumerate(blocks_models)]
        blocks.append(dict(pos=len(blocks_models) + 1, model=PROBE_MODEL, on=True, values=[0.5, LOAD, LEVEL]))
        sp = os.path.join(tmp, 'spec.json')
        json.dump(dict(name='DSP Load Test', split=1, merge=10, blocks=blocks), open(sp, 'w'))
        err = None
        for attempt in range(3):                          # a stray USB notification can upset one request
            r = subprocess.run([PY, os.path.join(HERE, 'preset_send.py'), 'build', slot, sp, '--image', PROBE_IMAGE],
                               capture_output=True, text=True, cwd=ROOT)
            if not r.returncode:
                r = subprocess.run([PY, os.path.join(HERE, 'preset_send.py'), 'load', slot], capture_output=True,
                                   text=True, cwd=ROOT)
            if not r.returncode:
                err = None
                break
            err = (r.stdout + r.stderr).strip()[-300:]
            time.sleep(3.0)
        if err:
            return dict(label=label, models=blocks_models, error=err)
        time.sleep(2.0)
        res = listen(seconds, device, None, out=quiet)
        rec = dict(label=label, models=blocks_models, t=time.strftime('%H:%M:%S'), frames=len(res),
                   load=[round(a, 2) for a, _ in res], peak=[round(b, 2) for _, b in res])
        return rec

    def base():
        return one([], 'base')

    silent, done = 0, 0
    try:
        b = base()
        fh.write(json.dumps(b) + '\n'); fh.flush()
        print(f'base: {b.get("load")} (frames {b.get("frames")})')
        if not b.get('frames'):
            raise SystemExit('the base gave no frames: is the unit\'s output audible to the microphone?')
        for k, (name, disp, cat) in enumerate(models):
            rec = one([name], name)
            rec.update(display=disp, category=cat)
            fh.write(json.dumps(rec) + '\n'); fh.flush()
            done += 1
            lo = rec.get('load') or []
            print(f'{k + start:4d} {cat:11} {disp or name:24} ' +
                  (f'error: {rec["error"][:80]}' if 'error' in rec else
                   f'load {np.median(lo):5.1f}% peak {max(rec["peak"]):5.1f}% ({rec["frames"]} frames)' if lo else 'no frames'),
                  flush=True)
            silent = silent + 1 if ('error' not in rec and not lo) else 0
            if silent >= 3 or (done % base_every == 0):
                for attempt in range(3):
                    b = base()
                    fh.write(json.dumps(b) + '\n'); fh.flush()
                    print(f'base: {b.get("load")} (frames {b.get("frames")})' + (f' error: {b["error"][:80]}' if 'error' in b else ''), flush=True)
                    if b.get('frames'):
                        break
                else:
                    raise SystemExit(f'stopped after {name}: the base gives no frames any more (unit or audio gone)')
                silent = 0
    finally:
        fh.close()
        try:
            print(ps('write', slot, backup + '.bin', old_name))
            print(ps('load', '1A', check=False))
        except SystemExit as e:
            print(f'COULD NOT RESTORE {slot}: {e} (backup kept at {backup}.bin)')
    print(f'{done} models measured; results in {outfile}')


def selftest():
    """The C reference's Probe frames, with an idle word set, through the decoder: the load comes back."""
    sys.path.insert(0, os.path.join(ROOT, 'effects', 'common'))
    import ctypes
    import kernel_rig as kr
    ref = kr.Reference(type('S', (), dict(name='hostprobe', order=['time', 'mode', 'level']))())
    st = ref.new()
    ref.lib.hostprobe_set_host(st, (ctypes.c_uint32 * 4)(0, 0, 0, 0), (ctypes.c_uint32 * 16)(*[0] * 16))
    idle = struct.unpack('<I', struct.pack('<f', 72.5))[0]
    ref.lib.hostprobe_set_idle(st, ctypes.c_uint32(idle))
    n = 16 * (((LPILOT + 32 * LNWORDS + 10) * LSYM * 5) // 16)
    out = np.zeros(n)
    kn = dict(time=0.5, mode=LOAD, level=0.25)
    for b in range(0, n, 16):
        y = ref.process(st, kn, [0.0] * 16)
        out[b:b + 16] = [f32(v) for v in y]
    rng = np.random.default_rng(5)
    rec = 0.3 * out + 0.0005 * rng.standard_normal(n)
    res = report(ldecode(rec, 48000))
    ok = len(res) >= 3 and all(abs(a - 27.5) < 1e-3 and abs(b - 27.5) < 1e-3 for a, b in res)
    print('SELFTEST OK' if ok else 'SELFTEST FAILED')
    return ok


def opt(a, name, kind=str, default=None):
    if name in a:
        i = a.index(name)
        v = kind(a[i + 1])
        del a[i:i + 2]
        return v
    return default


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        sys.exit(__doc__)
    global LEVEL
    LEVEL = opt(a, '--level', float, LEVEL)
    seconds = opt(a, '--seconds', float, 12.0)
    device = opt(a, '--device', str, DEVICE)
    save = opt(a, '--save')
    cmd = a.pop(0)
    if cmd == 'listen':
        listen(seconds, device, save)
    elif cmd == 'measure' and a:
        measure(a[0], a[1:], seconds, device, save)
    elif cmd == 'sweep' and a:
        cats = opt(a, '--categories')
        start, limit = opt(a, '--start', int, 0), opt(a, '--limit', int)
        only = opt(a, '--only')
        outfile = opt(a, '--out', str, os.path.join(ROOT, 'build', 'dsp_load', time.strftime('sweep-%Y%m%d-%H%M.jsonl')))
        sweep(a[0], seconds, device, outfile, cats.split(',') if cats else None, start, limit,
              only=set(only.split(',')) if only else None)
    elif cmd == 'models':
        for k, (n, d, c) in enumerate(sweep_models()):
            print(f'{k:4d} {c:11} {n:40} {d}')
    elif cmd == 'decode' and a:
        x, rate = il.read_wav(a[0])
        report(ldecode(x[:, 0] if x.ndim > 1 else x, rate))
    elif cmd == 'selftest':
        sys.exit(0 if selftest() else 1)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
