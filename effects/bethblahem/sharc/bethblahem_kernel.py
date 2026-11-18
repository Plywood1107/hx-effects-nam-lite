#!/usr/bin/env python3
"""bethblahem_kernel.py - build and check the Bethblahem kernel (bethblahem_kernel.asm) for the HX Effects SHARC.

usage: bethblahem_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/bethblahem through effects/out/libfx.so), every
            output word identical, with the register contract, the memory it may write and a cycle budget
            (effects/common/kernel_rig.py).

An overlay kernel: at most 430 instructions and 300 data words (checked here), 2 slots, no ring, every
constant an immediate in the .asm.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402

NSLOTS, MAX_CODE, MAX_DATA = 2, 430, 300
STATE = ['DCX', 'DCY', 'LP1', 'LP2', 'ENV', 'SQ', 'CNT', 'PL', 'INCT', 'HAVE', 'INC', 'PH', 'SUBF', 'LFO', 'VMUL',
         'AMP', 'OX', 'OY',
         'KOSC', 'KGLK', 'KGRW', 'KDRV', 'KBIAS', 'KSUB', 'KDRY', 'KLVL']    # this call's knob values

SPEC = kr.Spec('bethblahem', os.path.join(HERE, 'bethblahem_kernel.asm'), 'BETHBLAHEM_ENTRY',
               knobs=dict(octave=5, glide=6, vibrato=7, rate=8, growl=9, sub=10, dry=11, level=13),
               int_knobs={'octave'},
               order=['octave', 'glide', 'vibrato', 'rate', 'growl', 'sub', 'dry', 'level'],   # = bethblahem.h B_*
               state=STATE, constants={}, nslots=NSLOTS, max_cycles=10000,
               extra_equ=['.equ CNT_MAX, 4096', '.equ PMIN, 16', '.equ PMAX, 2400'])
SPEC.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)        # a Bethblahem-only placement, for the check

CASES = [
    dict(octave=2, glide=0.4, vibrato=0.3, rate=0.4, growl=0.5, sub=0.3, dry=0.7, level=0.7),     # the defaults
    dict(octave=0, glide=0, vibrato=0, rate=0, growl=0, sub=0, dry=0, level=1),
    dict(octave=4, glide=1, vibrato=1, rate=1, growl=1, sub=1, dry=1, level=1),                   # everything up
    dict(octave=1, glide=0.1, vibrato=0.8, rate=0.7, growl=0.2, sub=0.6, dry=0.3, level=0.9),
    dict(octave=3, glide=0.6, vibrato=0.5, rate=0.2, growl=0.9, sub=0.0, dry=0.5, level=0.5),     # loud input
    dict(octave=99, glide=9, vibrato=9, rate=9, growl=9, sub=9, dry=9, level=9),                 # out of range
    dict(octave=-9, glide=-9, vibrato=-9, rate=-9, growl=-9, sub=-9, dry=-9, level=-9),
    dict(octave=2, glide=0.0, vibrato=0.0, rate=0.5, growl=0.7, sub=0.5, dry=0, level=0.8),       # synth only
]


def rnd_knobs(r):
    return dict(octave=r.randint(0, 4), glide=r.uniform(0, 1), vibrato=r.uniform(0, 1), rate=r.uniform(0, 1),
                growl=r.uniform(0, 1), sub=r.uniform(0, 1), dry=r.uniform(0, 1), level=r.uniform(0, 1))


def sizes(place='b2'):
    _, _, _, end, _ = SPEC.assemble(place)
    return end - SPEC.places[place][0], SPEC.data_size()


def check(seconds=1.0, place='b2'):
    code, data = sizes(place)
    print(f'overlay: {code} instructions (at most {MAX_CODE}), {data} data words (at most {MAX_DATA})')
    assert code <= MAX_CODE and data <= MAX_DATA, 'too big for the overlay'
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    if '--check' in sys.argv:
        code, data = sizes()
        print(f'overlay: {code} instructions (at most {MAX_CODE}), {data} data words (at most {MAX_DATA})')
        if code > MAX_CODE or data > MAX_DATA:
            sys.exit('bethblahem_kernel.py: CHECK FAILED: too big for the overlay')
    kr.main(SPEC, CASES, rnd_knobs, __doc__)
