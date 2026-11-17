"""A very small Thumb-1 encoder for the patches' hand-written stubs (Cortex-M0 safe: 16-bit forms and BL only).

    a = Asm(0x200055e8)
    a.push(4, 5, 'lr'); a.cmp_i(2, 12); a.bcc('lo', 'pass'); ...; a.label('pass'); a.bl(0x20002e24)
    code = a.bytes()

Labels may be used before they are defined. Literals: a.ldr_lit(rt, 'name') with a.word('name', value) placed
after the code (word-aligned). Everything is checked again by disassembling the result (tools/verify_memwin.py).
"""
import struct

COND = {'eq': 0, 'ne': 1, 'hs': 2, 'lo': 3, 'mi': 4, 'pl': 5, 'vs': 6, 'vc': 7, 'hi': 8, 'ls': 9, 'ge': 10, 'lt': 11,
        'gt': 12, 'le': 13}


class Asm:
    def __init__(self, base):
        self.base = base
        self.items = []          # (kind, args) in order; each fixed size
        self.labels = {}
        self.size = 0

    def _add(self, n, fn):
        self.items.append((self.base + self.size, n, fn))
        self.size += n

    def here(self):
        return self.base + self.size

    def label(self, name):
        assert name not in self.labels
        self.labels[name] = self.here()

    def _h(self, v):
        self._add(2, lambda pc, v=v: struct.pack('<H', v))

    @staticmethod
    def _low(*regs):
        for r in regs:
            assert 0 <= r <= 7, 'low registers only'

    def push(self, *regs):
        m = sum(1 << r for r in regs if r != 'lr')
        self._h(0xB400 | (0x100 if 'lr' in regs else 0) | m)

    def pop(self, *regs):
        m = sum(1 << r for r in regs if r != 'pc')
        self._h(0xBC00 | (0x100 if 'pc' in regs else 0) | m)

    def cmp_i(self, rn, imm):
        self._low(rn)
        assert 0 <= imm <= 255
        self._h(0x2800 | rn << 8 | imm)

    def cmp_r(self, rn, rm):
        self._low(rn, rm)
        self._h(0x4280 | rm << 3 | rn)

    def movs_i(self, rd, imm):
        self._low(rd)
        assert 0 <= imm <= 255
        self._h(0x2000 | rd << 8 | imm)

    def movs_r(self, rd, rm):                  # lsls rd, rm, #0
        self._low(rd, rm)
        self._h(rm << 3 | rd)

    def mov_from_lr(self, rd):
        self._low(rd)
        self._h(0x4600 | 14 << 3 | rd)

    def ldr(self, rt, rn, off=0):
        self._low(rt, rn)
        assert off % 4 == 0 and 0 <= off <= 124
        self._h(0x6800 | (off // 4) << 6 | rn << 3 | rt)

    def str(self, rt, rn, off=0):
        self._low(rt, rn)
        assert off % 4 == 0 and 0 <= off <= 124
        self._h(0x6000 | (off // 4) << 6 | rn << 3 | rt)

    def ldr_lit(self, rt, name):
        self._low(rt)

        def enc(pc, rt=rt, name=name):
            off = self.labels[name] - ((pc + 4) & ~3)
            assert off % 4 == 0 and 0 <= off <= 1020, (name, off)
            return struct.pack('<H', 0x4800 | rt << 8 | off // 4)
        self._add(2, enc)

    def bcc(self, cond, name):
        def enc(pc, cond=cond, name=name):
            off = self.labels[name] - (pc + 4)
            assert off % 2 == 0 and -256 <= off <= 254, (name, off)
            return struct.pack('<H', 0xD000 | COND[cond] << 8 | (off >> 1) & 0xFF)
        self._add(2, enc)

    def b(self, name):
        def enc(pc, name=name):
            off = self.labels[name] - (pc + 4)
            assert off % 2 == 0 and -2048 <= off <= 2046, (name, off)
            return struct.pack('<H', 0xE000 | (off >> 1) & 0x7FF)
        self._add(2, enc)

    def bl(self, target):
        def enc(pc, target=target):
            off = target - (pc + 4)
            assert off % 2 == 0 and -(1 << 24) <= off < (1 << 24), hex(target)
            s = (off >> 24) & 1
            i1, i2 = (off >> 23) & 1, (off >> 22) & 1
            j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
            hi = 0xF000 | s << 10 | (off >> 12) & 0x3FF
            lo = 0xD000 | j1 << 13 | j2 << 11 | (off >> 1) & 0x7FF
            return struct.pack('<HH', hi, lo)
        self._add(4, enc)

    def align4(self):
        if self.size % 4:
            self._h(0x46C0)                     # nop (mov r8, r8)

    def word(self, name, value):
        assert self.size % 4 == 0, 'align4() first'
        self.label(name)
        self._add(4, lambda pc, value=value: struct.pack('<I', value))

    def bytes(self):
        out = b''
        for pc, n, fn in self.items:
            b = fn(pc)
            assert len(b) == n
            out += b
        return out


def bl_bytes(at, target):
    a = Asm(at)
    a.bl(target)
    return a.bytes()
