#!/usr/bin/env python3
"""memwin.py - talk to the memory window (tools/memwin_patch.py) on an HX Effects over USB.

usage:
  .venv/bin/python tools/memwin.py check                 does the unit answer? (reads the log's control block)
  .venv/bin/python tools/memwin.py log [--follow] [-o FILE]
                                                         print the app's log (SEGGER RTT channel 1) and empty it,
                                                         so the app can log again; --follow keeps reading
  .venv/bin/python tools/memwin.py fault                 the HardFault record, if a fault has happened
  .venv/bin/python tools/memwin.py peek ADDR [N]         hex dump of N bytes (default 64)
  .venv/bin/python tools/memwin.py poke ADDR VALUE       store one 32-bit word (careful)
  .venv/bin/python tools/memwin.py selftest              the log reader against a simulated unit (no USB)

Close HX Edit first: it holds the unit's USB interface. The window works while the unit's screen is frozen,
because USB runs on the unit's second processor core.

Why the log has to be emptied: the app's log buffer (64 KB at 0x282ae37c) is made for a hardware debugger that
reads it continuously. With nobody reading, it fills once after power-up and every later line is dropped. `log`
plays the debugger: it reads from the read offset to the write offset, then moves the read offset up.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

EP_OUT, EP_IN = 0x01, 0x81
CHUNK = 444                      # not a multiple of the 64- or 512-byte packet size: every answer ends short
RTT_CB = 0x10087760              # _SEGGER_RTT: 16-byte id, 2 counts, then 24-byte channel descriptors
RTT_UP1 = RTT_CB + 0x18 + 24     # channel 1 (up): name, buffer, size, write offset, read offset, flags
LOG_BUF, LOG_SIZE = 0x282AE37C, 0x10000
REC = 0x200054D0                 # the HardFault record (memwin_patch.py)
CFSR_BITS = [(0, 'IACCVIOL: instruction access violation'), (1, 'DACCVIOL: data access violation'), (3, 'MUNSTKERR'),
             (4, 'MSTKERR'), (7, 'MMARVALID: MMFAR holds the address'), (8, 'IBUSERR: instruction bus error'),
             (9, 'PRECISERR: precise data bus error'), (10, 'IMPRECISERR: imprecise data bus error'), (11, 'UNSTKERR'),
             (12, 'STKERR'), (15, 'BFARVALID: BFAR holds the address'), (16, 'UNDEFINSTR: undefined instruction'),
             (17, 'INVSTATE: invalid state (e.g. a jump to an even address)'), (18, 'INVPC'), (19, 'NOCP'),
             (24, 'UNALIGNED'), (25, 'DIVBYZERO')]


class NoAnswer(Exception):
    pass


class Usb:
    """The real unit."""

    def __init__(self):
        import flash
        self.flash = flash
        self.dev = flash.find(flash.VID, flash.PID)
        if self.dev is None:
            raise SystemExit('no HX Effects found on USB (is it on, connected, and in its normal mode?)')
        flash.claim(self.dev)
        try:                                       # drop anything left in the pipe
            while True:
                self.dev.read(EP_IN, 512, timeout=30)
        except Exception:
            pass

    def close(self):
        self.flash.release(self.dev)

    def _answer(self, n, timeout=1500):
        try:
            return bytes(self.dev.read(EP_IN, 512 * ((n + 511) // 512 or 1), timeout=timeout))
        except Exception as ex:
            if 'timed out' in str(ex).lower() or 'timeout' in type(ex).__name__.lower():
                raise NoAnswer()
            raise

    def peek_once(self, addr, n):
        self.dev.write(EP_OUT, struct.pack('<4sII', b'PEEK', addr, n), timeout=2000)
        b = self._answer(n)
        if len(b) != n:
            raise SystemExit(f'peek {addr:#x}: asked for {n} bytes, got {len(b)}')
        return b

    def poke(self, addr, value):
        assert addr % 4 == 0, 'poke needs a word-aligned address'
        self.dev.write(EP_OUT, struct.pack('<4sII', b'POKE', addr, value & 0xFFFFFFFF), timeout=2000)
        if self._answer(4) != b'POKE':
            raise SystemExit(f'poke {addr:#x}: no acknowledgement')


class Fake:
    """A simulated unit for selftest: memory as a dict of byte arrays."""

    def __init__(self):
        self.mem = {}

    def map(self, addr, data):
        self.mem[addr] = bytearray(data)

    def _find(self, addr, n):
        for base, b in self.mem.items():
            if base <= addr and addr + n <= base + len(b):
                return b, addr - base
        raise KeyError(hex(addr))

    def peek_once(self, addr, n):
        b, o = self._find(addr, n)
        return bytes(b[o:o + n])

    def poke(self, addr, value):
        b, o = self._find(addr, 4)
        struct.pack_into('<I', b, o, value & 0xFFFFFFFF)

    def close(self):
        pass


def peek(u, addr, n):
    out = b''
    while len(out) < n:
        out += u.peek_once(addr + len(out), min(CHUNK, n - len(out)))
    return out


def words(u, addr, n):
    return struct.unpack('<%dI' % n, peek(u, addr, 4 * n))


def log_channel(u):
    """(write offset, read offset) after checking the channel is the one we know."""
    name, buf, size, wr, rd, flags = words(u, RTT_UP1, 6)
    if (buf, size) != (LOG_BUF, LOG_SIZE):
        raise SystemExit(f'the log channel is not set up as expected (buffer {buf:#x}, size {size:#x}); is the app fully started?')
    if wr >= size or rd >= size:
        raise SystemExit(f'log offsets out of range (write {wr:#x}, read {rd:#x})')
    return wr, rd


def log_read(u):
    """The unread log bytes; moves the read offset up to the write offset."""
    wr, rd = log_channel(u)
    if wr == rd:
        return b''
    data = peek(u, LOG_BUF + rd, wr - rd) if wr > rd else peek(u, LOG_BUF + rd, LOG_SIZE - rd) + peek(u, LOG_BUF, wr)
    u.poke(RTT_UP1 + 16, wr)
    return data


def cmd_check(u):
    ident = peek(u, RTT_CB, 16)
    wr, rd = log_channel(u)
    print(f'the unit answers. Log control block id: {ident.split(bytes(1))[0].decode("latin1")!r}; '
          f'log buffer {LOG_SIZE} bytes, write offset {wr}, read offset {rd} '
          f'({(wr - rd) % LOG_SIZE} bytes unread{", buffer full: later lines are being dropped" if (wr + 1) % LOG_SIZE == rd else ""})')
    rec = words(u, REC, 6)
    print('fault record: ' + ('none' if rec[0] == 0 else f'a HardFault is recorded (frame at {rec[0]:#x}); run "fault"'))


def cmd_log(u, follow, outfile):
    f = open(outfile, 'ab') if outfile else None
    try:
        while True:
            data = log_read(u)
            if data:
                sys.stdout.write(data.decode('latin1').replace('\r\n', '\n'))
                sys.stdout.flush()
                if f:
                    f.write(data)
                    f.flush()
            if not follow:
                break
            time.sleep(0.1 if data else 0.25)
    except KeyboardInterrupt:
        pass
    finally:
        if f:
            f.close()


def cmd_fault(u):
    frame, cfsr, hfsr, mmfar, bfar, exc = words(u, REC, 6)
    if frame == 0:
        print('no HardFault recorded since power-up')
        return
    r0, r1, r2, r3, r12, lr, pc, xpsr = words(u, frame, 8)
    print(f'HardFault recorded.\n  pc   {pc:#010x}   (the instruction that faulted, or the one after)\n  lr   {lr:#010x}   (where it was called from)')
    print(f'  r0 {r0:#010x}  r1 {r1:#010x}  r2 {r2:#010x}  r3 {r3:#010x}  r12 {r12:#010x}  xpsr {xpsr:#010x}')
    print(f'  CFSR {cfsr:#010x}  HFSR {hfsr:#010x}  MMFAR {mmfar:#010x}  BFAR {bfar:#010x}  EXC_RETURN {exc:#010x}  frame {frame:#010x}')
    for bit, text in CFSR_BITS:
        if cfsr >> bit & 1:
            print(f'    {text}')
    if hfsr >> 30 & 1:
        print('    HFSR FORCED: another fault escalated to HardFault')
    if hfsr >> 31 & 1:
        print('    HFSR DEBUGEVT: a breakpoint instruction with no debugger (the other fault handlers are "bkpt; loop")')
    print('  stack above the frame (return addresses are odd numbers 0x1000.... or 0x28......):')
    st = words(u, frame + 32, 48)
    for i in range(0, 48, 8):
        print('   ' + ' '.join(f'{w:08x}' for w in st[i:i + 8]))


def cmd_peek(u, addr, n):
    data = peek(u, addr, n)
    for i in range(0, len(data), 16):
        row = data[i:i + 16]
        print(f'{addr + i:08x}  {row.hex(" "):47s}  {"".join(chr(c) if 32 <= c < 127 else "." for c in row)}')


def selftest():
    u = Fake()
    u.map(RTT_CB, bytes(0x18 + 24 * 3))
    u.map(LOG_BUF, bytes(LOG_SIZE))
    struct.pack_into('<6I', u.mem[RTT_CB], 0x18 + 24, 0x280E6D44, LOG_BUF, LOG_SIZE, 0, 0, 0)
    ok = True

    def app_write(s):                          # as SEGGER RTT in skip mode: all or nothing
        _, _, _, wr, rd, _ = struct.unpack_from('<6I', u.mem[RTT_CB], 0x18 + 24)
        free = (rd - wr - 1) % LOG_SIZE
        if len(s) > free:
            return False
        for c in s:
            u.mem[LOG_BUF][wr] = c
            wr = (wr + 1) % LOG_SIZE
        struct.pack_into('<I', u.mem[RTT_CB], 0x18 + 24 + 12, wr)
        return True

    sent = b''
    got = b''
    line = 0
    for round_ in range(40):                   # 40 rounds of ~3 KB: goes round the 64 KB buffer twice
        for _ in range(100):
            s = b'INFO: line %d of the test log\r\n' % line
            line += 1
            assert app_write(s)
            sent += s
        got += log_read(u)
    ok &= got == sent
    print(('  ok   ' if got == sent else '  FAIL ') + f'{len(sent)} bytes written in 40 rounds, twice round the buffer: read back exactly')
    while app_write(b'x' * 100) or app_write(b'x'):     # fill it to the last byte: the app now drops lines
        pass
    full = not app_write(b'dropped line\r\n')
    n = len(log_read(u))
    again = app_write(b'after emptying\r\n')
    ok &= full and again and log_read(u) == b'after emptying\r\n'
    print(('  ok   ' if full and again else '  FAIL ') + f'a full buffer drops lines; after reading its {n} bytes the app can log again')
    print('ALL OK' if ok else 'PROBLEMS')
    return ok


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        sys.exit(__doc__)
    if a[0] == 'selftest':
        sys.exit(0 if selftest() else 1)
    u = Usb()
    try:
        if a[0] == 'check':
            cmd_check(u)
        elif a[0] == 'log':
            cmd_log(u, '--follow' in a, a[a.index('-o') + 1] if '-o' in a else None)
        elif a[0] == 'fault':
            cmd_fault(u)
        elif a[0] == 'peek':
            cmd_peek(u, int(a[1], 0), int(a[2], 0) if len(a) > 2 else 64)
        elif a[0] == 'poke':
            u.poke(int(a[1], 0), int(a[2], 0))
            print(f'{int(a[1], 0):#x} <- {int(a[2], 0):#x}')
        else:
            sys.exit(__doc__)
    except NoAnswer:
        sys.exit('the unit did not answer. Is the memory-window image on it? (A stock or NAM image ignores these commands.)')
    finally:
        u.close()


if __name__ == '__main__':
    main()
