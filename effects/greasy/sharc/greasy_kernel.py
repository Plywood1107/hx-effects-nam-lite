#!/usr/bin/env python3
"""greasy_kernel.py - build and check the Greasy Strangler kernel (greasy_kernel.asm) for the HX Effects SHARC.

usage: greasy_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/greasy through effects/out/libfx.so), every
            output word identical, with the register contract, the memory it may write and a cycle budget
            (effects/common/kernel_rig.py). Also holds it to an overlay's size: at most MAX_CODE instructions
            and MAX_DATA data words.

An overlay kernel: no tables, every constant an immediate, 2 slots, no ring.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402

NV, NSLOTS, SEED = 4, 2, 0x6A09E667
MAX_CODE, MAX_DATA = 430, 300
VFIELDS = ['DG', 'D', 'DT', 'LP', 'LI', 'INC', 'PH', 'G']   # DG first: the voice loops step on its access
STATE = (['NUM', 'DRV', 'RND', 'TICK', 'CNT', 'PREV', 'OK', 'DCX', 'DCY', 'LP1', 'LP2', 'ENV', 'SQ',
          'RATET', 'RATE', 'FADE', 'Z1', 'Z2'] + [f'V{k}' for k in range(NV * len(VFIELDS))])

SPEC = kr.Spec('greasy', os.path.join(HERE, 'greasy_kernel.asm'), 'GREASY_ENTRY',
               knobs=dict(octave=5, glide=6, drift=7, warble=8, fuzz=9, tone=10, dry=11, level=13),
               int_knobs={'octave'},
               order=['octave', 'glide', 'drift', 'warble', 'fuzz', 'tone', 'dry', 'level'],   # = greasy.h GS_*
               state=STATE, constants={}, nslots=NSLOTS, max_cycles=10000,
               extra_equ=[f'.equ SEED, {SEED:#x}', f'.equ VSIZE, {len(VFIELDS)}', '.equ CNT_MAX, 4096',
                          '.equ PMIN, 24', '.equ PMAX, 2400', '.equ RETARGET, 2047'] +
                         [f'.equ V_{n}, {k}' for k, n in enumerate(VFIELDS)])
SPEC.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)        # a Greasy-only placement, for the check

CASES = [
    dict(octave=1, glide=0.3, drift=0.25, warble=0.35, fuzz=0.3, tone=0.35, dry=1, level=0.5),     # the defaults
    dict(octave=2, glide=0, drift=0, warble=0, fuzz=0, tone=1, dry=0, level=1),
    dict(octave=3, glide=1, drift=1, warble=1, fuzz=1, tone=1, dry=1, level=1),                    # everything up
    dict(octave=0, glide=0.6, drift=0.5, warble=0.8, fuzz=0.7, tone=0.1, dry=0.5, level=0.8),
    dict(octave=2, glide=0.1, drift=0.2, warble=0.1, fuzz=0.2, tone=0.5, dry=0.3, level=0.3),      # loud input
    dict(octave=99, glide=9, drift=9, warble=9, fuzz=9, tone=9, dry=9, level=9),                   # out of range
    dict(octave=-9, glide=-9, drift=-9, warble=-9, fuzz=-9, tone=-9, dry=-9, level=-9),
]


def rnd_knobs(r):
    return dict(octave=r.randint(0, 3), glide=r.uniform(0, 1), drift=r.uniform(0, 1), warble=r.uniform(0, 1),
                fuzz=r.uniform(0, 1), tone=r.uniform(0, 1), dry=r.uniform(0, 1), level=r.uniform(0, 1))


def sizes(place='b2'):
    """(instructions, data words) of the kernel built for place, held to the overlay's limits."""
    *_, end, data = SPEC.assemble(place)
    code, words = end - SPEC.places[place][0], data[1] - data[0]
    print(f'[greasy] {code} instructions (at most {MAX_CODE}), {words} data words (at most {MAX_DATA})')
    assert code <= MAX_CODE and words <= MAX_DATA, 'too big for the overlay'
    return code, words


def check(seconds=1.0, place='b2'):
    sizes(place)
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    if '--check' in sys.argv[1:]:
        try:
            sizes(sys.argv[sys.argv.index('--place') + 1] if '--place' in sys.argv else 'b2')
        except AssertionError as ex:
            sys.exit(f'greasy_kernel.py: CHECK FAILED: {ex}')
    kr.main(SPEC, CASES, rnd_knobs, __doc__)
