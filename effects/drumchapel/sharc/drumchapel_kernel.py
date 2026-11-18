#!/usr/bin/env python3
"""drumchapel_kernel.py - build and check the Drum Chapel kernel (drumchapel_kernel.asm) for the HX Effects SHARC.

usage: drumchapel_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/drumchapel through effects/out/libfx.so), every
            output word identical, with the register contract, the memory it may write and a cycle budget;
            then a long run through whole grooves (the wrap at their length) with Groove and Pattern changed
            mid-play.

An overlay kernel (as Ottobit): code and data travel to the shared internal region, so everything it keeps is in
its slots; no ring, no buffer outside them. The tables (kits, the hat's six squares, the tom's pitches) and the
constants are read from the C library, so they are the reference's to the bit.

The grooves are a read-only bank (drumchapel_bank: the directory, then the steps) that the kernel reads from
T_DIR: on the unit inside Blob 0 in DDR2 (build_all.py places it and calls place_bank), in the check at
BANK_CHECK, loaded into the simulator from the C library (spec.ext). It holds the converted grooves when
effects/drumchapel/grooves_data.h exists (grooves.py), else the Classic patterns only.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402
from kernel_rig import f32, fw  # noqa: E402

NPAT, NGROOVE, NKIT, NV, NDEF, NMETAL, SEED, PERIOD = 20, 12, 6, 4, 5, 6, 0x6D2B79F5, 288000000
DIR_WORDS = NGROOVE * NPAT
NSLOTS = 2
BANK_CHECK = 0x3A0000                   # the bank's address in the check; the image build sets the unit's (DDR2)
VFIELDS = ['PH', 'PH2', 'PE', 'TE', 'NE', 'AGE', 'LP', 'DEF', 'TUNE']        # = DrumVoice
KFIELDS = ['DRIVE', 'COMP', 'TDRIVE', 'M2', 'HOLD', 'GATE']                  # = drumchapel.h DK_*, then the definitions
DFIELDS = ['INC', 'SWEEP', 'PD', 'TD', 'ND', 'TLEV', 'NLEV', 'NF']           # = DV_*
DK_WORDS = len(KFIELDS) + NDEF * len(DFIELDS)
STATE = ['ACC', 'STEP', 'PEND', 'RND', 'HCNT', 'LEN'] + [f'V{k}' for k in range(NV * len(VFIELDS))]
B_TOM, B_OPEN, B_PITCH = 8, 16, 5        # = drumchapel.h DC_B_*

CONSTANTS = {}                          # none in memory: immediates, or .equ words below


def bank():
    """The bank's words, from the C library (the reference reads the same table)."""
    lib = kr.lib()
    lib.drumchapel_bank.restype = ctypes.POINTER(ctypes.c_uint32)
    n = ctypes.c_uint32()
    p = lib.drumchapel_bank(ctypes.byref(n))
    return [p[k] for k in range(n.value)]


def families():
    lib = kr.lib()
    return lib.drumchapel_families()


def tables():
    lib = kr.lib()
    lib.drumchapel_kit_words.restype = ctypes.POINTER(ctypes.c_uint32)
    lib.drumchapel_metal.restype = ctypes.POINTER(ctypes.c_uint32)
    lib.drumchapel_tune.restype = ctypes.POINTER(ctypes.c_uint32)
    kits = []
    for k in range(NKIT):
        w = lib.drumchapel_kit_words(k)
        kits += [w[i] for i in range(DK_WORDS)]
    metal, tune = lib.drumchapel_metal(), lib.drumchapel_tune()
    return (('T_KIT', kits), ('T_METAL', [metal[k] for k in range(NMETAL)]), ('T_TUNE', [tune[k] for k in range(4)]))


def consts():
    lib = kr.lib()
    c = {n: ctypes.c_float.in_dll(lib, f'drumchapel_{n}').value for n in ('r2', 'third', 'silent', 'gate_k')}
    return dict(K_R2=fw(c['r2']), K_THIRD=fw(c['third']), K_SILENT=fw(c['silent']), K_GATE=fw(c['gate_k']),
                K_TMIN=fw(f32(0.1)))


def place_bank(spec, addr):
    """The bank at `addr` (its directory first): the kernel's T_DIR / T_STEPS, and the words the check loads there."""
    spec.extra_equ = [e for e in spec.extra_equ if not e.startswith(('.equ T_DIR,', '.equ T_STEPS,'))]
    spec.extra_equ += [f'.equ T_DIR, {addr:#x}', f'.equ T_STEPS, {addr + DIR_WORDS:#x}']
    spec.bank_addr = addr
    spec.ext = [(addr, bank())]


def make_spec(bank_addr=BANK_CHECK):
    vs = len(VFIELDS)
    equ = [f'.equ SEED, {SEED:#x}', f'.equ PERIOD, {PERIOD}', f'.equ BPM100_NUM, 2304000000', f'.equ VW, {vs}',
           f'.equ VEND, {2 + len(STATE)}', f'.equ DK_WORDS, {DK_WORDS}', f'.equ DK_V0, {len(KFIELDS)}',
           f'.equ DV_WORDS, {len(DFIELDS)}', f'.equ DMETAL, {NMETAL}', f'.equ B_OPEN, {B_OPEN}',
           f'.equ DO_HAT, {len(KFIELDS) + 2 * len(DFIELDS)}', f'.equ DO_OPEN, {len(KFIELDS) + 4 * len(DFIELDS)}']
    equ += [f'.equ VS_{n}, {k}' for k, n in enumerate(VFIELDS)]
    equ += [f'.equ DK_{n}, {k}' for k, n in enumerate(KFIELDS)]
    equ += [f'.equ DV_{n}, {k}' for k, n in enumerate(DFIELDS)]
    equ += [f'.equ {n}, {v:#x}' for n, v in consts().items()]
    spec = kr.Spec('drumchapel', os.path.join(HERE, 'drumchapel_kernel.asm'), 'DRUMCHAPEL_ENTRY',
                   knobs=dict(time=5, pattern=6, kit=7, kick=8, snare=9, hat=10, swing=11, level=13, groove=14),
                   int_knobs={'pattern', 'kit', 'groove'},
                   order=['time', 'pattern', 'kit', 'kick', 'snare', 'hat', 'swing', 'level', 'groove'],   # = drumchapel.h DC_*
                   state=STATE, constants=CONSTANTS, nslots=NSLOTS, tables=tables(), max_cycles=9000, extra_equ=equ)
    assert spec.state['ST_V0'] == 2 + 6
    spec.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)       # a Drum-Chapel-only placement, for the check
    place_bank(spec, bank_addr)
    return spec


SPEC = make_spec()


def _find(pred, first=10):
    """(groove, pattern) of the first variation whose first steps hold a byte pred() likes, or None (Classic only)."""
    b = bank()
    for g in range(1, NGROOVE):
        for p in range(NPAT):
            d = b[g * NPAT + p]
            if d == b[p]:
                continue
            for k in range(min(first, d & 511)):
                i = (d >> 9) + k
                if pred(b[DIR_WORDS + i // 4] >> (8 * (i % 4)) & 0xFF):
                    return g, p
    return None


def _groove_cases():
    """Cases from the bank (no note data here): grooves with toms of each pitch, and open hats, in their first steps."""
    out = []
    for t in range(4):
        gp = _find(lambda b, t=t: b & B_TOM and (b >> B_PITCH & 3) == t)
        if gp:
            out.append(dict(time=0.1, groove=gp[0], pattern=gp[1], kit=t + 1, kick=1, snare=0.8, hat=0.7, swing=0.2 * t, level=1))
    gp = _find(lambda b: b & B_OPEN)
    if gp:
        out.append(dict(time=0.1, groove=gp[0], pattern=gp[1], kit=0, kick=0.7, snare=0.7, hat=1, swing=0, level=1))
        out.append(dict(time=0.12, groove=gp[0], pattern=gp[1], kit=5, kick=1, snare=1, hat=1, swing=0.5, level=0.9))
    return out


CASES = [
    dict(time=0.5, pattern=0, kit=0, kick=0.8, snare=0.7, hat=0.5, swing=0, level=0.5, groove=0),           # the defaults
    dict(time=0.1, pattern=12, kit=1, kick=1, snare=1, hat=1, swing=1, level=1, groove=0),                  # fastest, everything up
    dict(time=0.25, pattern=5, kit=2, kick=0.6, snare=0.9, hat=1, swing=0.5, level=0.8, groove=0),
    dict(time=0.3, pattern=7, kit=3, kick=1, snare=0.8, hat=0.9, swing=0.3, level=1, groove=0),             # Bit: held noise, squares
    dict(time=0.2, pattern=6, kit=4, kick=1, snare=1, hat=1, swing=0.7, level=1, groove=0),                 # Doom
    dict(time=0.15, pattern=19, kit=5, kick=0.9, snare=1, hat=0.6, swing=0.2, level=0.9, groove=0),         # Eighty, the gate
    dict(time=0.12, pattern=16, kit=0, kick=1, snare=0, hat=0.3, swing=0.9, level=0.7, groove=0),
    dict(time=0.1, pattern=12, kit=0, kick=1, snare=1, hat=1, swing=0.5, level=1, groove=0),                # Boom: every voice, metal
    dict(time=0.4, pattern=4, kit=5, kick=0.5, snare=0.5, hat=0.5, swing=0.6, level=0, groove=0),           # Level 0: the input
    dict(time=99, pattern=99, kit=99, kick=9, snare=9, hat=9, swing=9, level=9, groove=99),                 # out of range
    dict(time=-9, pattern=-9, kit=-9, kick=-9, snare=-9, hat=-9, swing=-9, level=-9, groove=-9),
    dict(time=0.1, pattern=3, kit=4, kick=1, snare=1, hat=1, swing=0, level=1, groove=10),                  # a family (or Classic)
    dict(time=0.1, pattern=17, kit=1, kick=1, snare=1, hat=1, swing=0.4, level=1, groove=3),
] + _groove_cases()


def rnd_knobs(r):
    return dict(time=r.uniform(0.1, 0.6), pattern=r.randint(0, NPAT - 1), kit=r.randint(0, NKIT - 1),
                kick=r.uniform(0, 1), snare=r.uniform(0, 1), hat=r.uniform(0, 1), swing=r.uniform(0, 1),
                level=r.uniform(0, 1), groove=r.randint(0, NGROOVE - 1))


def check_long(spec, place, steps=None):
    """Whole grooves in ssim: the shortest groove not in 4/4 (or Classic) played past its length at the fastest tempo
    (the wrap), then 40 more steps with Groove, Pattern and Kit changed mid-play at odd moments, against the reference
    word for word."""
    src, secs, syms, end, data = spec.assemble(place)
    ref, rig = kr.Reference(spec), kr.Rig(spec, secs, syms, seed=3)
    b = bank()
    lens = {(g, p): b[g * NPAT + p] & 511 for g in range(NGROOVE) for p in range(NPAT)}
    odd = [gp for gp, n in sorted(lens.items(), key=lambda x: x[1]) if n % 16]       # a meter that is not 4/4
    g0, p0 = odd[0] if odd else (0, 0)
    n = lens[(g0, p0)]
    kn = dict(time=0.1, groove=g0, pattern=p0, kit=4, kick=1, snare=1, hat=1, swing=0.3, level=1)
    nblk = (steps or n + 44) * 1200 // 16                                         # a sixteenth at Time 0.1: 1,200 samples
    r = random.Random(9)
    sched = sorted(r.sample(range((n + 4) * 1200 // 16, nblk), 6))                # after the wrap
    i0 = rig.inst(0)
    rig.knobs(i0, kn)
    st = ref.new()
    x = kr.signal(nblk * 16, 41)
    for blk in range(nblk):
        if blk in sched:                                                           # a change mid-play
            kn = dict(kn, groove=r.randint(0, NGROOVE - 1), pattern=r.randint(0, NPAT - 1), kit=r.randint(0, NKIT - 1))
            rig.knobs(i0, kn)
        w = x[16 * blk:16 * blk + 16]
        if rig.call(i0, w, f'long block {blk}') != ref.process(st, kn, [kr.ssim.b2f(v) for v in w]):
            raise AssertionError(f'long run: block {blk} ({kn}) differs')
    print(f'  groove {g0} pattern {p0} ({n} sixteenths) played {nblk * 16 // 1200} steps, with {len(sched)} Groove/Pattern/Kit '
          f'changes mid-play: {nblk * 16} samples identical; worst {max(rig.cycles)} cycles')
    assert max(rig.cycles) <= spec.max_cycles


def check(seconds=1.0, place='b2'):
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    print(f'bank: {len(bank())} words, {families()} of 11 families converted' +
          ('' if families() else ' (no grooves_data.h: Classic only)'))
    kr.main(SPEC, CASES, rnd_knobs, __doc__)
    if '--check' in sys.argv:
        place = sys.argv[sys.argv.index('--place') + 1] if '--place' in sys.argv else 'b2'
        try:
            check_long(SPEC, place)
        except AssertionError as ex:
            sys.exit(f'drumchapel_kernel.py: LONG CHECK FAILED: {ex}')
        print('LONG CHECK OK')
