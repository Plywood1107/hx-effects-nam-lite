#!/usr/bin/env python3
"""check_core.py - groove-core.js against effects/drumchapel/grooves.py, byte for byte (needs Node).

usage: check_core.py

Writes a few MIDI loops of its own (odd lengths, every voice, toms on one step, ghost notes, notes off the grid,
running status) into a temporary folder, converts them with grooves.py --user and with groove-core.js, and
compares the two .wav files; then the same for random step patterns (userBank alone), and reads one back.
"""
import json
import os
import random
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'effects', 'drumchapel'))
import grooves  # noqa: E402


def vlq(n):
    b = [n & 0x7F]
    n >>= 7
    while n:
        b.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(b))


def smf(path, hits, steps, ppq=96, running=False):
    ev, t16 = [], ppq // 4
    for st, note, vel in hits:
        t = int(st * t16)
        ev += [(t, 0x99, note, vel), (t + 7, 0x89, note, 0)]
    ev.sort()
    tr, last, prev = b'', 0, None
    for t, s, n, v in ev:
        tr += vlq(t - last) + (bytes([n, v]) if running and s == prev else bytes([s, n, v]))
        last, prev = t, s
    tr += vlq(steps * t16 - last) + b'\xff\x2f\x00'
    open(path, 'wb').write(b'MThd' + struct.pack('>IHHH', 6, 0, 1, ppq) + b'MTrk' + struct.pack('>I', len(tr)) + tr)


NODE = r"""
const G = require(process.argv[1]), fs = require('fs'), path = require('path');
const dir = process.argv[2], out = process.argv[3];
const names = fs.readdirSync(dir).filter(f => /\.midi?$/i.test(f)).sort(G.naturalCompare);
const loops = names.map(f => G.convertMidi(new Uint8Array(fs.readFileSync(path.join(dir, f)))));
fs.writeFileSync(out, G.wavBytes(G.userBank(loops)));
const extra = JSON.parse(process.argv[4]);
fs.writeFileSync(out + '.json', JSON.stringify(extra.map(l => Array.from(G.userBank(l)))));
const back = G.readBank(G.userBank(extra[0]));
fs.writeFileSync(out + '.back.json', JSON.stringify(back));
"""


def main():
    r = random.Random(4)
    with tempfile.TemporaryDirectory() as d:
        smf(os.path.join(d, '01 rock.mid'), [(0, 36, 100), (4, 38, 100), (8, 36, 100), (12, 38, 100)] + [(k, 42, 90) for k in range(0, 16, 2)], 16)
        smf(os.path.join(d, '02 odd.mid'), [(0, 36, 100), (6, 38, 30), (6.4, 38, 100), (10, 45, 100), (10, 41, 100), (12, 49, 110), (13, 41, 90), (13, 48, 90)], 14, running=True)
        smf(os.path.join(d, '10 toms.mid'), [(k, [48, 45, 43, 41][k % 4], 100) for k in range(32)] + [(3, 99, 100)], 32, ppq=480)
        smf(os.path.join(d, '9 cym.mid'), [(k, n, 100) for k, n in enumerate([46, 49, 51, 52, 53, 55, 57, 59, 24, 54, 56, 44])], 12)
        py = os.path.join(d, 'py.wav')
        subprocess.run([sys.executable, os.path.join(ROOT, 'effects', 'drumchapel', 'grooves.py'), '--user', d, '-o', py],
                       check=True, capture_output=True)
        extra = [[r.randrange(128) for _ in range(n)] for n in (16, 28, 384, 44)]
        js = os.path.join(d, 'js.wav')
        subprocess.run(['node', '-e', NODE, os.path.join(HERE, 'groove-core.js'), d, js, json.dumps([extra, extra[:1], [extra[2]] * 15])],
                       check=True)
        a, b = open(py, 'rb').read(), open(js, 'rb').read()
        ok = a == b
        print(('ok  ' if ok else 'FAIL') + f' MIDI loops: grooves.py and groove-core.js write the same .wav ({len(a)} bytes)')
        got = json.load(open(js + '.json'))
        for k, loops in enumerate([extra, extra[:1], [extra[2]] * 15]):
            same = got[k] == grooves.user_bank(loops)
            ok &= same
            print(('ok  ' if same else 'FAIL') + f' {len(loops)} random loops ({sum(map(len, loops))} steps): the same samples')
        back = json.load(open(js + '.json.back.json')) if os.path.exists(js + '.json.back.json') else json.load(open(js + '.back.json'))
        same = back == extra
        ok &= same
        print(('ok  ' if same else 'FAIL') + ' readBank gives the loops back')
    print('ALL OK' if ok else 'FAILED')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
