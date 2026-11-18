#!/usr/bin/env python3
"""grooves.py - turn a folder of MIDI drum loops into Drum Chapel's groove data (effects/drumchapel/grooves_data.h).

usage: grooves.py FOLDER [-o grooves_data.h] [--stats]

The loops are a commercial pack and the repository is public, so the output is git-ignored and must never be
committed; nothing in the repository names a file of the pack or carries its notes. Without the output the
reference, the kernel check and the image build still work, with the Classic patterns only (drumchapel.h).

Each file becomes one groove: its whole length (the End of Track, a whole number of sixteenths, at most
DRUMCHAPEL_MAX_STEPS) at sixteenth resolution, every hit quantised to the nearest sixteenth (a hit that rounds to
the end wraps to step 0); hits under velocity 40 (ghost notes) are dropped. Files group into families by a word
in their names (FAMILIES, the Groove knob's entries 1..11), each family's files in order of the number that ends
their name. A step is one byte (drumchapel.h, DC_B_*): kick, snare, hat, tom, open (a cymbal or open hat on the
hat voice, with the open decay) and two bits of tom pitch.

Note map (the pack's kit map, worked out from where each note falls in the loops):
  kick 35 36 | snare 37 38 40 | closed hat 42 44 (pedal) | open hat / cymbals 46, crash 49 57, china 52,
  splash 55, ride 51 59, ride bell 53, and 24, 54, 56 (cymbals: 24 and 54 keep time on eighths or quarters in
  the variations that use no other cymbal, as 51, 46 or 57 do in their siblings; 56 is a lone accent) |
  toms: high 48 50, mid 45 47, low 43, floor 41. Two toms on one step: the louder (on a tie the lower).
Anything else is dropped (counted in --stats).
"""
import os
import re
import struct
import sys

PPQ_STEPS = 4                          # sixteenths a quarter note
MAX_STEPS = 384                        # = drumchapel.h DRUMCHAPEL_MAX_STEPS
MAX_VARIATIONS = 20                    # the Pattern knob's 20 entries
MIN_VELOCITY = 40

# the Groove knob's entries 1..11: (display name, the word in the file names)
FAMILIES = [('Doublerino', 'Doublerino'), ('Fake 1st', 'Fake1st'), ('Proggy 13/4', 'Proggy'), ('Crazy 14/4', 'Crazy'),
            ('Antibeat', 'Antibeat'), ('Free Beat', 'FreeBeat'), ('Chaos 29/4', 'Chaos'), ('Dum Dum', 'DumDum'),
            ('Dam Dam', 'DamDam'), ('Tomapalooza', 'Tomapalooza'), ('Tomathon', 'Tomathon')]

KICK, SNARE, HAT, TOM, OPEN = 1, 2, 4, 8, 16          # = drumchapel.h DC_B_*
TOM_SHIFT = 5
NOTES = {35: KICK, 36: KICK, 37: SNARE, 38: SNARE, 40: SNARE, 42: HAT, 44: HAT}
NOTES.update({n: HAT | OPEN for n in (24, 46, 49, 51, 52, 53, 54, 55, 56, 57, 59)})
TOMS = {48: 0, 50: 0, 45: 1, 47: 1, 43: 2, 41: 3}      # pitch: 0 high, 1 mid, 2 low, 3 floor


def _vlq(b, i):
    v = 0
    while True:
        c = b[i]
        i += 1
        v = v << 7 | (c & 0x7F)
        if not c & 0x80:
            return v, i


def read_midi(path):
    """(ticks a quarter, [(tick, note, velocity)] note-ons, end tick): every track, every channel."""
    b = open(path, 'rb').read()
    if b[:4] != b'MThd':
        raise ValueError(f'{path}: not a MIDI file')
    _, ntrk, ppq = struct.unpack('>HHH', b[8:14])
    if ppq & 0x8000:
        raise ValueError(f'{path}: SMPTE time division')
    i = 8 + struct.unpack('>I', b[4:8])[0]
    notes, end = [], 0
    for _ in range(ntrk):
        if b[i:i + 4] != b'MTrk':
            raise ValueError(f'{path}: bad track header')
        j, stop = i + 8, i + 8 + struct.unpack('>I', b[i + 4:i + 8])[0]
        tick, run = 0, None
        while j < stop:
            d, j = _vlq(b, j)
            tick += d
            st = b[j]
            if st == 0xFF:
                ty = b[j + 1]
                n, j = _vlq(b, j + 2)
                j += n
                if ty == 0x2F:
                    end = max(end, tick)
                continue
            if st in (0xF0, 0xF7):
                n, j = _vlq(b, j + 1)
                j += n
                continue
            if st & 0x80:
                run = st
                j += 1
            hi = run & 0xF0
            if hi in (0xC0, 0xD0):
                j += 1
                continue
            d1, d2 = b[j], b[j + 1]
            j += 2
            if hi == 0x90 and d2 > 0:
                notes.append((tick, d1, d2))
        i = stop
    return ppq, notes, end


def convert(path, stats):
    """One file -> its steps (one byte each)."""
    ppq, notes, end = read_midi(path)
    tick16 = ppq // PPQ_STEPS
    if ppq % PPQ_STEPS:
        raise ValueError(f'{path}: {ppq} ticks a quarter is not a whole number of sixteenths')
    if not end or end % tick16:                       # no or odd End of Track: the beat after the last note
        end = (max(t for t, _, _ in notes) // ppq + 1) * ppq
    n = end // tick16
    if not 1 <= n <= MAX_STEPS:
        raise ValueError(f'{path}: {n} sixteenths (at most {MAX_STEPS})')
    steps, tom_vel = [0] * n, [0] * n
    for t, note, vel in notes:
        if vel < MIN_VELOCITY:
            stats['ghost'] = stats.get('ghost', 0) + 1
            continue
        k = (t + tick16 // 2) // tick16 % n
        stats['off'] = stats.get('off', 0) + (t % tick16 != 0)
        stats['hits'] = stats.get('hits', 0) + 1
        if note in NOTES:
            steps[k] |= NOTES[note]
        elif note in TOMS:
            p = TOMS[note]
            old = steps[k] >> TOM_SHIFT & 3 if steps[k] & TOM else -1
            if vel > tom_vel[k] or (vel == tom_vel[k] and p > old):
                steps[k] = steps[k] & ~(3 << TOM_SHIFT) | TOM | p << TOM_SHIFT
                tom_vel[k] = vel
        else:
            stats.setdefault('dropped', {})
            stats['dropped'][note] = stats['dropped'].get(note, 0) + 1
    return steps


def families(folder):
    """[[steps of each variation] per family], in FAMILIES order (an empty list for a family not found)."""
    names = sorted(f for f in os.listdir(folder) if f.lower().endswith('.mid'))
    out, used, stats = [], set(), {}
    for _, word in FAMILIES:
        mine = []
        for f in names:
            m = re.search(r'(\d+)\.mid$', f, re.I)
            if word.lower() in f.lower() and m:
                mine.append((int(m.group(1)), f))
        mine.sort()
        if len(mine) > MAX_VARIATIONS:
            raise ValueError(f'family {word}: {len(mine)} files, the Pattern knob has {MAX_VARIATIONS}')
        out.append([convert(os.path.join(folder, f), stats) for _, f in mine])
        used.update(f for _, f in mine)
    stats['unused'] = len(set(names) - used)
    return out, stats


def header(fams):
    lens = [len(v) for fam in fams for v in fam]
    steps = [s for fam in fams for v in fam for s in v]
    rows = [', '.join(str(x) for x in steps[k:k + 32]) for k in range(0, len(steps), 32)]
    return ('/* grooves_data.h - written by grooves.py from a local folder of licensed MIDI loops.\n'
            ' * NEVER COMMIT THIS FILE (it is git-ignored): the notes are the pack\'s. */\n'
            f'#define DC_GROOVE_FAMILIES {len(fams)}\n'
            f'#define DC_GROOVE_VARIATIONS {len(lens)}\n'
            f'#define DC_GROOVE_TOTAL {len(steps)}\n'
            f'static const unsigned char DC_FAMILY_N[DC_GROOVE_FAMILIES] = {{ {", ".join(str(len(f)) for f in fams)} }};\n'
            f'static const unsigned short DC_GROOVE_LEN[DC_GROOVE_VARIATIONS] = {{ {", ".join(map(str, lens))} }};\n'
            'static const unsigned char DC_GROOVE_STEPS[DC_GROOVE_TOTAL] = {\n    ' + ',\n    '.join(rows) + '\n};\n')


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        sys.exit(__doc__)
    out = a[a.index('-o') + 1] if '-o' in a else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grooves_data.h')
    fams, stats = families(a[0])
    if not any(fams):
        sys.exit(f'grooves.py: no family found in {a[0]}')
    open(out, 'w').write(header(fams))
    total = sum(len(v) for f in fams for v in f)
    print(f'grooves.py: {sum(map(len, fams))} grooves in {sum(1 for f in fams if f)} of {len(FAMILIES)} families, '
          f'{total} steps ({(total + 3) // 4} words) -> {out}')
    for (name, _), f in zip(FAMILIES, fams):
        print(f'  {name:12s} {len(f):2d} variations, {", ".join(str(len(v)) for v in f)} sixteenths' if f else f'  {name:12s} missing')
    if '--stats' in a:
        print(f'  {stats.get("hits", 0)} hits ({stats.get("off", 0)} not exactly on a sixteenth), {stats.get("ghost", 0)} ghosts dropped, '
              f'other notes dropped: {stats.get("dropped", {})}, files in no family: {stats["unused"]}')


if __name__ == '__main__':
    main()
