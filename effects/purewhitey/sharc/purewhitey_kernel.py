#!/usr/bin/env python3
"""purewhitey_kernel.py - build and check the Pure Whitey kernel (purewhitey_kernel.asm) for the HX Effects SHARC.

usage: purewhitey_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/purewhitey through effects/out/libfx.so), every
            output word identical, with the register contract, the memory it may write (its slot and the
            RING_N-word ring at RING0, filled with noise first: the kernel must never read a sample it has not
            recorded) and a cycle budget.

RING0 is where the ring goes: DDR2 on the unit (set by the image build, make_spec(ring0)); any free address
in the check. One slot: a second Pure Whitey block passes its input through.
"""
import ctypes
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402
from kernel_rig import f32, SR  # noqa: E402

RING_N, LMIN, SEED = 4096, 32, 0x2545F491          # = purewhitey.h PUREWHITEY_RING, _LMIN, _SEED
NSLOTS = 1
RING0 = 0x380000                     # the check's; the image build sets the unit's (DDR2)

STATE = ['TRIG', 'NTRIG', 'RL', 'BASE', 'THR', 'TK', 'SPD', 'RAMP', 'REPS', 'RMASK', 'P2', 'SQ', 'SQM', 'DL', 'ML',
         'ENVF', 'ENVS', 'PREVC', 'RND', 'STAGE', 'W', 'PH', 'PEND', 'ACC', 'MI', 'MN', 'PLEN',
         'START', 'LEFT', 'LM1', 'POS', 'SP', 'SQE', 'SQC', 'SQF', 'LP']

CONSTANTS = dict(
    K_SMR=f32(math.exp(-1.0 / (0.005 * SR))), K_SLOWK=f32(1.0 - math.exp(-1.0 / (0.05 * SR))),
    K_SQR=f32(math.exp(-1.0 / (0.01 * SR))), K_QMAX2=2.0 * 32767.0 / 32768.0,
    K_099=f32(0.99), K_0002=f32(0.002), K_097=f32(0.97), K_003=f32(0.03), K_01=f32(0.1), K_07=f32(0.7))


def tables():
    """The per-mode table, from the C library: 10 rows of 8 (purewhitey.h)."""
    t = (ctypes.c_uint32 * 80)()
    kr.lib().purewhitey_mode_table(t)
    return (('T_MODE', list(t)),)


def make_spec(ring0=RING0):
    spec = kr.Spec('purewhitey', os.path.join(HERE, 'purewhitey_kernel.asm'), 'PUREWHITEY_ENTRY',
                   knobs=dict(mode=5, time=6, func=7, sens=8, tone=9, dry=10, mix=11, level=13),
                   int_knobs={'mode'},
                   order=['mode', 'time', 'func', 'sens', 'tone', 'dry', 'mix', 'level'],   # = purewhitey.h W_*
                   state=STATE, constants=CONSTANTS, nslots=NSLOTS, max_cycles=6000,
                   tables=tables(),
                   extra_equ=[f'.equ RING0, {ring0:#x}', f'.equ RING_N, {RING_N}', f'.equ RING_MASK, {RING_N - 1}',
                              f'.equ LMIN, {LMIN}', f'.equ SEED, {SEED:#x}'])
    spec.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)       # a Pure-Whitey-only placement, for the check
    spec.extra_writes = [(ring0, ring0 + RING_N)]
    spec.garbage = [(ring0, ring0 + RING_N)]              # the check fills the ring with noise first
    return spec


SPEC = make_spec()

CASES = [
    dict(mode=0, time=0.5, func=0.5, sens=0.5, tone=0.8, dry=1, mix=1, level=1),           # the defaults
    dict(mode=0, time=0.1, func=1, sens=0.5, tone=1, dry=0, mix=1, level=1),               # Repeat for ever
    dict(mode=1, time=0.6, func=0.5, sens=0.5, tone=0.6, dry=0.5, mix=1, level=0.8),       # Random
    dict(mode=1, time=1, func=1, sens=0.3, tone=0.3, dry=0, mix=0.9, level=1),
    dict(mode=2, time=0.0, func=0.2, sens=0.5, tone=1, dry=0.3, mix=1, level=1),           # Reverse x-1/2
    dict(mode=2, time=0.4, func=0.5, sens=0.5, tone=0.9, dry=0, mix=1, level=1),           # x-1
    dict(mode=2, time=1, func=0.9, sens=0.5, tone=0.7, dry=0.6, mix=0.7, level=0.9),       # x-2, random lengths
    dict(mode=3, time=0.2, func=0.5, sens=0.9, tone=0.8, dry=0, mix=1, level=1),           # Trigger
    dict(mode=4, time=0.3, func=1, sens=0.7, tone=0.5, dry=0.2, mix=1, level=1),           # Square Trigger
    dict(mode=5, time=0.5, func=0.0, sens=0.5, tone=0.4, dry=0, mix=1, level=1),           # Square
    dict(mode=5, time=0.15, func=0.6, sens=0.5, tone=1, dry=0.5, mix=0.5, level=0.7),
    dict(mode=6, time=0.25, func=1, sens=0.5, tone=1, dry=0, mix=1, level=1),              # Up
    dict(mode=7, time=0.2, func=0.7, sens=0.5, tone=0.8, dry=0, mix=1, level=1),           # Down
    dict(mode=99, time=9, func=9, sens=9, tone=9, dry=9, mix=9, level=9),                  # out of range
    dict(mode=-9, time=-9, func=-9, sens=-9, tone=-9, dry=-9, mix=-9, level=-9),
]


def rnd_knobs(r):
    return dict(mode=r.randint(0, 7), time=r.choice([r.uniform(0, 1), 1.0]), func=r.uniform(0, 1),
                sens=r.uniform(0, 1), tone=r.uniform(0, 1), dry=r.uniform(0, 1), mix=r.uniform(0, 1),
                level=r.uniform(0, 1))


def check(seconds=1.0, place='b2'):
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    kr.main(SPEC, CASES, rnd_knobs, __doc__)
