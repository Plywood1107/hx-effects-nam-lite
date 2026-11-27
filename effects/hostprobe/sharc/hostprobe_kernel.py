#!/usr/bin/env python3
"""hostprobe_kernel.py - build and check the host probe (hostprobe_kernel.asm) for the HX Effects SHARC.

usage: hostprobe_kernel.py [-o out.asm] [--check] [--seconds S] [--place b2]

  --check   run it in ssim against the C reference (effects/hostprobe through effects/out/libfx.so), every output
            word identical, with the register contract, the memory it may write and a cycle budget; with a host
            call-list entry and instance struct in simulated memory whose words 6 and 7 give the block the graph asks
            for (then the memory test writes and checks its two words), and again with an empty one (it writes
            nothing there); then a long run through three whole frames (9 s) with the meter's windows in them.

The probe image (build_all.py --hostprobe) puts it on Drum Chapel's host in Drum Chapel's place, its graph member
asking for SDR_REQ SDRAM words. tools/input_level.py decodes its frames from a recording of the unit's output.
"""
import ctypes
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'common'))
import kernel_rig as kr  # noqa: E402
import ssim  # noqa: E402

# = hostprobe.h
WIN_CALLS, SYM, NPILOT, NWORDS, NGAP, NSIN = 3000, 120, 80, 34, 40, 48
NBITS = 32 * NWORDS
NSYM = NPILOT + NBITS + NGAP
SYNC, MAGIC, SDR_REQ, PAT_A, PAT_B = 0x9E3779B9, 0x50524232, 0x10000, 0xA5C3F00D, 0x5A3C0FF2
FRAME_SAMPLES = NSYM * SYM
NSLOTS = 2
MAX_CODE, MAX_DATA = 515, 452                  # the overlay region today (Drum Chapel's), which it replaces

STATE = ['PEAK', 'SQ', 'SUM', 'WCALLS', 'WIN', 'LPEAK', 'LSQ', 'LSUM', 'LWIN', 'SPOS', 'SIDX', 'PH', 'STEP', 'FRAMES',
         'CALLS', 'MSTAT', 'MBAD', 'MODE'] + [f'FR{k}' for k in range(NWORDS)]

# The host in the check: a call-list entry whose word 2 points at an instance struct
ENTRY, STRUCT = 0xB7000, 0xB7010
SDR_A = 0x380000


def host_words(block):
    entry = [0x00C0FFEE, 0x1234, STRUCT, 0x5678]
    inst = [0x10000 + k for k in range(16)]
    inst[6], inst[7] = (SDR_A, SDR_A + SDR_REQ) if block else (0, 0)
    return entry, inst


def make_spec(block=True):
    lib = kr.lib()
    lib.hostprobe_sin.restype = ctypes.c_float
    lib.hostprobe_sin.argtypes = [ctypes.c_int]
    sin = [kr.fw(lib.hostprobe_sin(k)) for k in range(NSIN)]
    spec = kr.Spec('hostprobe', os.path.join(HERE, 'hostprobe_kernel.asm'), 'HOSTPROBE_ENTRY',
                   knobs=dict(time=5, mode=6, level=13), int_knobs={'mode'}, order=['time', 'mode', 'level'],
                   state=STATE, constants={}, nslots=NSLOTS, tables=(('T_SIN', sin),), max_cycles=1500,
                   extra_equ=[f'.equ {k}, {v:#x}' for k, v in dict(
                       WIN_CALLS=WIN_CALLS, WIN_SAMPLES=16 * WIN_CALLS, SYM=SYM, NPILOT=NPILOT, NBITS=NBITS, NSYM=NSYM,
                       NSIN=NSIN, SYNC=SYNC, MAGIC=MAGIC, SDR_REQ=SDR_REQ, PAT_A=PAT_A, PAT_B=PAT_B).items()])
    spec.places['b2'] = (0xC4EF8, 0xC5554, 0xE4850)       # a probe-only placement, for the check
    entry, inst = host_words(block)
    spec.i3 = ENTRY
    spec.ext = [(ENTRY, entry), (STRUCT, inst), (SDR_A, [0]), (SDR_A + SDR_REQ - 1, [0])]
    spec.extra_writes = [(SDR_A, SDR_A + 1), (SDR_A + SDR_REQ - 1, SDR_A + SDR_REQ)] if block else []

    def ref_setup(lib_, st):
        e = (ctypes.c_uint32 * 4)(*entry)
        i = (ctypes.c_uint32 * 16)(*inst)
        lib_.hostprobe_set_host(st, e, i)
    spec.ref_setup = ref_setup
    return spec


SPEC = make_spec()

CASES = [
    dict(time=0.5, mode=0, level=0.25),          # the defaults: the report
    dict(time=0.5, mode=0, level=1.0),
    dict(time=0.5, mode=1, level=0.25),          # Pass
    dict(time=9.0, mode=7, level=9.0),           # out of range
    dict(time=-1, mode=-3, level=-1),
]


def rnd_knobs(r):
    return dict(time=r.uniform(0.1, 4), mode=r.randint(0, 1), level=r.uniform(0, 1))


def sizes(place='b2'):
    """(code instructions, data words) as kernel_rig lays them out."""
    _, _, _, end, _ = SPEC.assemble(place)
    return end - SPEC.places[place][0], SPEC.data_size()


def long_check(spec, place, frames=3.1):
    """One instance through whole frames, every word against the reference, and the memory test's words at the end."""
    src, secs, syms, end, data = spec.assemble(place)
    ref = kr.Reference(spec)
    rig = kr.Rig(spec, secs, syms, seed=9)
    kn = dict(time=0.5, mode=0, level=0.5)
    i0 = rig.inst(0)
    rig.knobs(i0, kn)
    st = ref.new()
    nblk = int(frames * FRAME_SAMPLES) // 16
    x = kr.signal(nblk * 16, 41, amp=0.4)
    for b in range(nblk):
        blk = x[16 * b:16 * b + 16]
        if rig.call(i0, blk, f'long block {b}') != ref.process(st, kn, [ssim.b2f(v) for v in blk]):
            raise AssertionError(f'long run: block {b} differs')
    got = (rig.sim.rd(SDR_A), rig.sim.rd(SDR_A + SDR_REQ - 1))
    want = (PAT_A, PAT_B) if spec.extra_writes else (0, 0)
    assert got == want, f'the memory test left {got[0]:#x}, {got[1]:#x}, not {want[0]:#x}, {want[1]:#x}'
    print(f'  long run: {nblk * 16} samples ({nblk * 16 / FRAME_SAMPLES:.1f} frames) identical; the block\'s words '
          f'{"hold the test pattern" if spec.extra_writes else "untouched"}')


def check(seconds=0.25, place='b2'):
    code, data = sizes(place)
    print(f'[hostprobe] {code} instructions (limit {MAX_CODE}), {data} data words (limit {MAX_DATA})')
    assert code <= MAX_CODE, f'{code} instructions, over the overlay limit {MAX_CODE}'
    assert data <= MAX_DATA, f'{data} data words, over the overlay limit {MAX_DATA}'
    return kr.check(SPEC, place, CASES, rnd_knobs, seconds)


if __name__ == '__main__':
    a = sys.argv[1:]
    place = a[a.index('--place') + 1] if '--place' in a else 'b2'
    if '--check' in a:
        secs = float(a[a.index('--seconds') + 1]) if '--seconds' in a else 1.0
        try:
            check(secs, place)
            print('  with no SDRAM block in the instance struct:')
            empty = make_spec(block=False)
            kr.check(empty, place, CASES[:1], rnd_knobs, secs)
            long_check(SPEC, place)
            long_check(empty, place, frames=1.05)
        except AssertionError as ex:
            sys.exit(f'hostprobe_kernel.py: CHECK FAILED: {ex}')
        print('CHECK OK')
        a.remove('--check')
    if '-o' in a:
        open(a[a.index('-o') + 1], 'w').write(SPEC.assemble(place)[0])
    if not sys.argv[1:]:
        sys.exit(__doc__)
