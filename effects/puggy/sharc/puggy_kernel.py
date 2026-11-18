#!/usr/bin/env python3
"""puggy_kernel.py - build and check the Puggy Puncher kernel (puggy_kernel.asm) for the HX Effects SHARC.

usage: puggy_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/puggy through effects/out/libfx.so), every
            output word identical, with the register contract, the memory it may write and a cycle budget;
            and hold it to the overlay's limits (code instructions, data words).
"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402
from kernel_rig import f32  # noqa: E402

NSTEPS, NWILD, NSEED, SEED0, CRATE = 11, 11, 17, 0x2545F491, 6
NSLOTS = 2
MAX_CODE, MAX_DATA = 430, 300                  # the overlay region's budget
PERIOD = int(kr.SR * 6000.0 + 0.5)             # = reset(): sr x 6000

STATE = ['STARTED', 'BACC', 'SACC', 'BEAT', 'RND', 'HOLD', 'ROLL', 'CUR', 'PREV', 'XG',
         'T1', 'T2', 'ENV', 'HI', 'FF', 'CCNT', 'HELD', 'FD', 'FS', 'LOW', 'BAND',
         'W0', 'W1', 'W2', 'W3', 'W4', 'W5']    # W0..W5: the treatments' outputs, in puggy.h PT_* order
KNAMES = ['TA', 'REL', 'HYST', 'ODRY', 'SLAM', 'FS', 'FLO', 'FD0', 'FQ', 'FG', 'FL']   # = puggy.h PK_*


def constants():
    k = (ctypes.c_float * len(KNAMES)).in_dll(kr.lib(), 'puggy_k')
    return dict(K_TMIN=f32(0.1), **{f'K_{n}': k[i] for i, n in enumerate(KNAMES)})


def tables():
    lib = kr.lib()
    lib.puggy_stepmul.restype = ctypes.c_int
    lib.puggy_wild.restype = ctypes.c_uint32
    lib.puggy_seed.restype = ctypes.c_uint32
    return (('T_MUL', [lib.puggy_stepmul(k) for k in range(NSTEPS)]),
            ('T_WILD', [lib.puggy_wild(k) for k in range(NWILD)]),
            ('T_SEED', [lib.puggy_seed(k) for k in range(NSEED)]))


def make_spec():
    spec = kr.Spec('puggy', os.path.join(HERE, 'puggy_kernel.asm'), 'PUGGY_ENTRY',
                   knobs=dict(time=5, step=6, chance=7, wild=8, hold=9, seed=10, mix=11, level=13),
                   int_knobs={'step', 'wild', 'hold', 'seed'},
                   order=['time', 'step', 'chance', 'wild', 'hold', 'seed', 'mix', 'level'],   # = puggy.h PG_*
                   state=STATE, constants=constants(), nslots=NSLOTS, tables=tables(), max_cycles=10000,
                   extra_equ=[f'.equ SEED0, {SEED0:#x}', f'.equ CRATE, {CRATE}', '.equ BPM100_NUM, 2304000000',
                              f'.equ PERIOD, {PERIOD}', f'.equ SPERIOD, {6 * PERIOD}'])
    spec.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)       # a Puggy-only placement, for the check
    return spec


SPEC = make_spec()

CASES = [
    dict(time=0.5, step=8, chance=0.5, wild=0, hold=1, seed=0, mix=1, level=1),          # the defaults
    dict(time=0.1, step=10, chance=1, wild=0, hold=1, seed=3, mix=1, level=0.8),          # fastest, every treatment
    dict(time=0.25, step=9, chance=0.8, wild=3, hold=2, seed=0, mix=0.7, level=1),        # fuzz, octave
    dict(time=0.3, step=7, chance=1, wild=1, hold=3, seed=16, mix=1, level=0.5),          # crush, filter, dotted
    dict(time=0.2, step=6, chance=0.6, wild=6, hold=1, seed=1, mix=0.9, level=1),         # chop
    dict(time=0.15, step=8, chance=1, wild=4, hold=8, seed=0, mix=1, level=1),            # octave, filter, held
    dict(time=0.4, step=10, chance=0, wild=0, hold=1, seed=0, mix=0.4, level=1),          # clean: the input
    dict(time=9.0, step=99, chance=9, wild=99, hold=99, seed=99, mix=9, level=9),         # out of range
    dict(time=-1, step=-9, chance=-1, wild=-9, hold=-9, seed=-9, mix=-1, level=-1),
]


def rnd_knobs(r):
    return dict(time=r.uniform(0.1, 0.6), step=r.randint(0, 10), chance=r.uniform(0, 1), wild=r.randint(0, 10),
                hold=r.randint(1, 8), seed=r.randint(0, 16), mix=r.uniform(0, 1), level=r.uniform(0, 1))


def sizes(place='b2'):
    """(code instructions, data words) as kernel_rig lays them out."""
    _, _, _, end, _ = SPEC.assemble(place)
    return end - SPEC.places[place][0], SPEC.data_size()


def check(seconds=1.0, place='b2'):
    code, data = sizes(place)
    print(f'[puggy] {code} instructions (limit {MAX_CODE}), {data} data words (limit {MAX_DATA})')
    assert code <= MAX_CODE, f'{code} instructions, over the overlay limit {MAX_CODE}'
    assert data <= MAX_DATA, f'{data} data words, over the overlay limit {MAX_DATA}'
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--check' in a:
        try:
            code, data = sizes(a[a.index('--place') + 1] if '--place' in a else 'b2')
        except AssertionError as ex:
            sys.exit(f'puggy_kernel.py: CHECK FAILED: {ex}')
        print(f'[puggy] {code} instructions (limit {MAX_CODE}), {data} data words (limit {MAX_DATA})')
        if code > MAX_CODE or data > MAX_DATA:
            sys.exit('puggy_kernel.py: CHECK FAILED: over the overlay limits')
    kr.main(SPEC, CASES, rnd_knobs, __doc__)
