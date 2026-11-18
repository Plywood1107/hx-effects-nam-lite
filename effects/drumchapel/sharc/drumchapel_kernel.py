#!/usr/bin/env python3
"""drumchapel_kernel.py - build and check the Drum Chapel kernel (drumchapel_kernel.asm) for the HX Effects SHARC.

usage: drumchapel_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/drumchapel through effects/out/libfx.so), every
            output word identical, with the register contract, the memory it may write and a cycle budget.

An overlay kernel (as Ottobit): code and data travel to the shared internal region, so everything it keeps is in
its slots; no ring, no buffer outside them. The tables (patterns, kits, the hat's six squares) and the constants
are read from the C library, so they are the reference's to the bit.
"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402
from kernel_rig import f32, fw  # noqa: E402

NPAT, NKIT, NV, NMETAL, SEED, PERIOD = 20, 6, 3, 6, 0x6D2B79F5, 288000000
NSLOTS = 2
VFIELDS = ['PH', 'PH2', 'PE', 'TE', 'NE', 'AGE', 'LP']                       # = DrumVoice
KFIELDS = ['DRIVE', 'COMP', 'TDRIVE', 'M2', 'HOLD', 'GATE']                  # = drumchapel.h DK_*, then the voices
DFIELDS = ['INC', 'SWEEP', 'PD', 'TD', 'ND', 'TLEV', 'NLEV', 'NF']           # = DV_*
DK_WORDS = len(KFIELDS) + NV * len(DFIELDS)
STATE = ['ACC', 'STEP', 'PEND', 'RND', 'HCNT'] + [f'V{k}' for k in range(NV * len(VFIELDS))]

CONSTANTS = {}                          # none in memory: immediates, or .equ words below


def tables():
    lib = kr.lib()
    lib.drumchapel_kit_words.restype = ctypes.POINTER(ctypes.c_uint32)
    lib.drumchapel_metal.restype = ctypes.POINTER(ctypes.c_uint32)
    lib.drumchapel_pattern_ks.restype = ctypes.c_uint32
    lib.drumchapel_pattern_hat.restype = ctypes.c_uint32
    ks = [lib.drumchapel_pattern_ks(p) for p in range(NPAT)]
    hat = [lib.drumchapel_pattern_hat(p) for p in range(NPAT)]
    kits = []
    for k in range(NKIT):
        w = lib.drumchapel_kit_words(k)
        kits += [w[i] for i in range(DK_WORDS)]
    metal = lib.drumchapel_metal()
    return (('T_KS', ks), ('T_HAT', [hat[2 * q] | hat[2 * q + 1] << 16 for q in range(NPAT // 2)]),
            ('T_KIT', kits), ('T_METAL', [metal[k] for k in range(NMETAL)]))


def consts():
    lib = kr.lib()
    c = {n: ctypes.c_float.in_dll(lib, f'drumchapel_{n}').value for n in ('r2', 'third', 'silent', 'gate_k')}
    return dict(K_R2=fw(c['r2']), K_THIRD=fw(c['third']), K_SILENT=fw(c['silent']), K_GATE=fw(c['gate_k']),
                K_TMIN=fw(f32(0.1)))


def make_spec():
    vs = len(VFIELDS)
    equ = [f'.equ SEED, {SEED:#x}', f'.equ PERIOD, {PERIOD}', f'.equ BPM100_NUM, 2304000000', f'.equ VW, {vs}',
           f'.equ VEND, {2 + 5 + NV * vs}', f'.equ DK_WORDS, {DK_WORDS}', f'.equ DK_V0, {len(KFIELDS)}',
           f'.equ DV_WORDS, {len(DFIELDS)}', f'.equ DMETAL, {NMETAL}']
    equ += [f'.equ VS_{n}, {k}' for k, n in enumerate(VFIELDS)]
    equ += [f'.equ DK_{n}, {k}' for k, n in enumerate(KFIELDS)]
    equ += [f'.equ DV_{n}, {k}' for k, n in enumerate(DFIELDS)]
    equ += [f'.equ {n}, {v:#x}' for n, v in consts().items()]
    spec = kr.Spec('drumchapel', os.path.join(HERE, 'drumchapel_kernel.asm'), 'DRUMCHAPEL_ENTRY',
                   knobs=dict(time=5, pattern=6, kit=7, kick=8, snare=9, hat=10, swing=11, level=13),
                   int_knobs={'pattern', 'kit'},
                   order=['time', 'pattern', 'kit', 'kick', 'snare', 'hat', 'swing', 'level'],   # = drumchapel.h DC_*
                   state=STATE, constants=CONSTANTS, nslots=NSLOTS, tables=tables(), max_cycles=7000, extra_equ=equ)
    assert spec.state['ST_V0'] == 2 + 5
    spec.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)       # a Drum-Chapel-only placement, for the check
    return spec


SPEC = make_spec()

CASES = [
    dict(time=0.5, pattern=0, kit=0, kick=0.8, snare=0.7, hat=0.5, swing=0, level=0.5),           # the defaults
    dict(time=0.1, pattern=12, kit=1, kick=1, snare=1, hat=1, swing=1, level=1),                  # fastest, everything up
    dict(time=0.25, pattern=5, kit=2, kick=0.6, snare=0.9, hat=1, swing=0.5, level=0.8),
    dict(time=0.3, pattern=7, kit=3, kick=1, snare=0.8, hat=0.9, swing=0.3, level=1),             # Bit: held noise, squares
    dict(time=0.2, pattern=6, kit=4, kick=1, snare=1, hat=1, swing=0.7, level=1),                 # Doom
    dict(time=0.15, pattern=19, kit=5, kick=0.9, snare=1, hat=0.6, swing=0.2, level=0.9),         # Eighty, the gate
    dict(time=0.12, pattern=16, kit=0, kick=1, snare=0, hat=0.3, swing=0.9, level=0.7),
    dict(time=0.1, pattern=12, kit=0, kick=1, snare=1, hat=1, swing=0.5, level=1),                # Boom: every voice, metal
    dict(time=0.4, pattern=4, kit=5, kick=0.5, snare=0.5, hat=0.5, swing=0.6, level=0),           # Level 0: the input
    dict(time=99, pattern=99, kit=99, kick=9, snare=9, hat=9, swing=9, level=9),                  # out of range
    dict(time=-9, pattern=-9, kit=-9, kick=-9, snare=-9, hat=-9, swing=-9, level=-9),
]


def rnd_knobs(r):
    return dict(time=r.uniform(0.1, 0.6), pattern=r.randint(0, NPAT - 1), kit=r.randint(0, NKIT - 1),
                kick=r.uniform(0, 1), snare=r.uniform(0, 1), hat=r.uniform(0, 1), swing=r.uniform(0, 1),
                level=r.uniform(0, 1))


def check(seconds=1.0, place='b2'):
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    kr.main(SPEC, CASES, rnd_knobs, __doc__)
