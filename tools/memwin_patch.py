"""The "memory window": two small patches to the HX Effects 3.80.0 application (Entry 0) that let a computer
read and write the unit's memory over USB, and keep a record of a processor fault. Diagnostic only.

Why it works while the main core is frozen: the application runs on two cores. The main one (Cortex-M4) runs the
user interface and talks to the DSP; a HardFault there ends in an endless loop (0x280d393e). The small one
(Cortex-M0, the image at 0x20000000) runs USB, and both cores see the same memory.

1. USB core, the bulk receive thread (0x2000366c). It collects each packet the host sends and passes it to the
   main core (`bl 0x20002e24` at 0x200036ae and 0x200036c8; r0 channel, r1 0, r2 length, r3 buffer). Both calls
   are redirected to a stub that looks at the packet first:
       'PEEK' addr len   ->  sends len bytes from addr back to the host (the USB write routine, 0x20000d44)
       'POKE' addr value ->  stores the word, then echoes the first 4 bytes as an acknowledgement
       anything else     ->  passed on exactly as before
   A real message starts with a 16-bit length of at most 512, so neither magic can occur in normal traffic.
   The stub sits on the USB core's source-file-name strings (0x200055e8...), which only feed its assert routine,
   and that routine is empty (`bx lr` at 0x20004354 and 0x20004358).

2. Main core, the HardFault handler (0x280d391c, reached from the vector at 0x100001b4 with r0 = the stacked
   frame). Stock: copies the frame to its own stack, then loops forever. Patched: writes a record at REC, then
   loops forever as before:
       REC+0  address of the stacked frame (r0 r1 r2 r3 r12 lr pc xpsr)     +4  CFSR (0xE000ED28)
       +8  HFSR (0xE000ED2C)      +12  MMFAR (0xE000ED34)     +16  BFAR (0xE000ED38)     +20  EXC_RETURN
   REC is another dead file-name string of the USB core (0x200054d0), zeroed in the image, so REC+0 != 0 means
   "a fault happened". (The fault status registers are private to the main core: the USB core cannot read them
   itself, which is why the handler copies them.)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l6ia  # noqa: E402
import patch_amp as pa  # noqa: E402
from thumb1 import Asm, bl_bytes  # noqa: E402

MAGIC_PEEK = struct.unpack('<I', b'PEEK')[0]
MAGIC_POKE = struct.unpack('<I', b'POKE')[0]

# USB core (Cortex-M0)
M0_IPC_SEND = 0x20002E24         # (channel, 0, length, buffer): pass a received packet to the main core
M0_USB_WRITE = 0x20000D44        # (endpoint, pointer, length): send to the host, in max-packet chunks
M0_CALL_SITES = (0x200036AE, 0x200036C8)
M0_STUB = 0x200055E8             # "../../lib/helix-common/mcu/main_m0/src/system/usbAudio.c" and the next string
M0_STUB_ROOM = 0x2000565C - M0_STUB      # up to the usbEcom.c string
EP_IN = 0x81

# main core (Cortex-M4)
M4_HARDFAULT = 0x280D391C
M4_HARDFAULT_LEN = 0x24          # the stock handler, up to the next function at 0x280d3940
M4_HARDFAULT_STOCK = bytes.fromhex('d0e90041d0e9022388b0009401910292d0e904410393d0e906230494059106920793fee7')
REC = 0x200054D0                 # "../../lib/PODPlay/mcu/src/threads/Mutex.c" in the USB core's image
REC_WORDS = 6
SCB_CFSR = 0xE000ED28


def stub():
    a = Asm(M0_STUB)
    a.push(4, 5, 'lr')
    a.cmp_i(2, 12)
    a.bcc('lo', 'pass')
    a.ldr(4, 3, 0)
    a.ldr_lit(5, 'peek')
    a.cmp_r(4, 5)
    a.bcc('eq', 'do_peek')
    a.ldr_lit(5, 'poke')
    a.cmp_r(4, 5)
    a.bcc('eq', 'do_poke')
    a.label('pass')
    a.bl(M0_IPC_SEND)
    a.pop(4, 5, 'pc')
    a.label('do_peek')
    a.ldr(1, 3, 4)
    a.ldr(2, 3, 8)
    a.movs_i(0, EP_IN)
    a.bl(M0_USB_WRITE)
    a.movs_i(0, 0)
    a.pop(4, 5, 'pc')
    a.label('do_poke')
    a.ldr(1, 3, 4)
    a.ldr(2, 3, 8)
    a.str(2, 1, 0)
    a.movs_r(1, 3)
    a.movs_i(2, 4)
    a.movs_i(0, EP_IN)
    a.bl(M0_USB_WRITE)
    a.movs_i(0, 0)
    a.pop(4, 5, 'pc')
    a.align4()
    a.word('peek', MAGIC_PEEK)
    a.word('poke', MAGIC_POKE)
    code = a.bytes()
    assert len(code) <= M0_STUB_ROOM
    return code


def hardfault():
    a = Asm(M4_HARDFAULT)
    a.ldr_lit(1, 'rec')
    a.ldr_lit(2, 'cfsr')
    a.str(0, 1, 0)
    a.ldr(3, 2, 0)
    a.str(3, 1, 4)
    a.ldr(3, 2, 4)
    a.str(3, 1, 8)
    a.ldr(3, 2, 12)
    a.str(3, 1, 12)
    a.ldr(3, 2, 16)
    a.str(3, 1, 16)
    a.mov_from_lr(3)
    a.str(3, 1, 20)
    a.label('hang')
    a.b('hang')
    a.align4()
    a.word('rec', REC)
    a.word('cfsr', SCB_CFSR)
    code = a.bytes()
    assert len(code) == M4_HARDFAULT_LEN, len(code)
    return code


def changes():
    """[(address, new bytes, what)]: everything the memory window changes in Entry 0."""
    s = stub()
    return [(M0_CALL_SITES[0], bl_bytes(M0_CALL_SITES[0], M0_STUB), 'bulk thread: full packet -> stub'),
            (M0_CALL_SITES[1], bl_bytes(M0_CALL_SITES[1], M0_STUB), 'bulk thread: short packet -> stub'),
            (M0_STUB, s, 'the stub, over dead file-name strings'),
            (REC, bytes(4 * REC_WORDS), 'the fault record, zeroed'),
            (M4_HARDFAULT, hardfault(), 'HardFault handler: record, then loop')]


def apply(e0):
    """Entry 0 (little-endian bytes) with the memory window; internal CRC redone."""
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments_any(e0)

    def fo(va, n):
        return pa._e0_vaddr_to_foff(segs, va, n)
    assert bytes(e0[fo(M4_HARDFAULT, M4_HARDFAULT_LEN):][:M4_HARDFAULT_LEN]) == M4_HARDFAULT_STOCK, 'not the stock HardFault handler'
    for site in M0_CALL_SITES:
        assert bytes(e0[fo(site, 4):][:4]) == bl_bytes(site, M0_IPC_SEND), f'{site:#x}: not the stock call'
    assert bytes(e0[fo(M0_STUB, 8):][:8]) == b'../../li' and bytes(e0[fo(REC, 8):][:8]) == b'../../li', 'not the stock strings'
    assert bytes(e0[fo(0x20004354, 2):][:2]) == b'\x70\x47' and bytes(e0[fo(0x20004358, 2):][:2]) == b'\x70\x47', \
        "the USB core's assert routines are not empty"
    for va, new, _ in changes():
        o = fo(va, len(new))
        e0[o:o + len(new)] = new
    return bytes(l6ia.fix_internal_crcs(bytes(e0)))
