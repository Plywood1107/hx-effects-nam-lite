"""Read-only access to the two firmwares for reverse engineering: entries, the ARM app's segments, strings,
Thumb disassembly. Nothing here writes a firmware file.

    from fw import effects, stomp          # App objects for each firmware's Entry 0 (the ARM application)
    effects.dis(0x280f221c, 0x40)          # capstone instructions at a virtual address
    effects.cstr(0x1000202c)               # the C string at an address
    effects.u32(0x1000d6ec)                # a little-endian word
    effects.find(b'SEGGER RTT')            # virtual addresses of a byte string
    effects.strings(5)                     # (address, text) of every printable run

Memory map (both units, an NXP LPC43xx): 0x10000000 and 0x20000000 internal RAM, 0x28000000 external RAM where
the main code is copied at boot.
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import capstone  # noqa: E402
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402

EFFECTS_HXF = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
STOMP_HXF = os.path.join(ROOT, 'firmware', 'HX_Stomp_v3.80.0_0x103966115.hxf')
_md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)


def load(path):
    """The firmware's L6IA archive (bytes)."""
    img, _ = pa.load_l6ia_from_any(path)
    return img


def entry(img, k):
    """Entry k of an archive, byte-swapped to little-endian words as the units use it."""
    return bytes(pa.get_entry_swapped(img, k))


class App:
    """An Entry 0: the ARM application, as (file offset, size, load address) segments."""

    def __init__(self, path):
        self.path = path
        self.img = load(path)
        self.b = entry(self.img, 0)
        self.segs = [(s[1], s[2], s[3]) for s in pa._parse_e0_segments_any(bytearray(self.b))]

    def off(self, va):
        for o, n, base in self.segs:
            if base <= va < base + n:
                return o + va - base
        return None

    def va(self, off):
        for o, n, base in self.segs:
            if o <= off < o + n:
                return base + off - o
        return None

    def u32(self, va):
        return struct.unpack_from('<I', self.b, self.off(va))[0]

    def u16(self, va):
        return struct.unpack_from('<H', self.b, self.off(va))[0]

    def bytes(self, va, n):
        o = self.off(va)
        return self.b[o:o + n]

    def cstr(self, va):
        o = self.off(va)
        if o is None:
            return None
        return self.b[o:self.b.find(b'\0', o)].decode('latin1')

    def dis(self, va, n=0x80):
        return list(_md.disasm(self.bytes(va, n), va))

    def show(self, va, n=0x80):
        for i in self.dis(va, n):
            print(f'{i.address:#010x}  {i.mnemonic:8s} {i.op_str}')

    def find(self, needle):
        return [self.va(m.start()) for m in re.finditer(re.escape(needle), self.b) if self.va(m.start()) is not None]

    def strings(self, n=4):
        return [(self.va(m.start()), m.group().decode()) for m in re.finditer(rb'[\x20-\x7e]{%d,}' % n, self.b)
                if self.va(m.start()) is not None]

    def refs(self, va):
        """Addresses of 32-bit words equal to va (literal pools, tables); va|1 for Thumb function pointers too."""
        out = []
        for v in (va, va | 1):
            out += self.find(struct.pack('<I', v))
        return sorted(set(out))


class _Lazy:
    def __init__(self, path):
        self._path, self._app = path, None

    def __getattr__(self, k):
        if self._app is None:
            self._app = App(self._path)
        return getattr(self._app, k)


effects = _Lazy(EFFECTS_HXF)
stomp = _Lazy(STOMP_HXF)
