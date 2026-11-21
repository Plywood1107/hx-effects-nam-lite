#!/usr/bin/env python3
"""ir_upload.py - put a .wav (an IR, or a NAM capture converted by nam2ir.py) into a User IR slot on the HX Effects
over USB, without HX Edit.

usage:
  .venv/bin/python tools/ir_upload.py list                     the User IR slots: number, name, MD5 of the samples
  .venv/bin/python tools/ir_upload.py put SLOT FILE.wav [NAME]  write FILE into slot SLOT (1-128), then read it back
  .venv/bin/python tools/ir_upload.py rename SLOT NAME
  .venv/bin/python tools/ir_upload.py copy FROM TO              copy a slot (name and samples) to another slot
  .venv/bin/python tools/ir_upload.py delete SLOT               clear a slot
  .venv/bin/python tools/ir_upload.py get SLOT FILE.wav         save a slot's samples as a .wav

Close HX Edit first: it holds the unit's USB interface.

The protocol was taken from a capture of HX Edit 3.80 importing one IR (tools/usb/capture_hxedit.sh, 2026-11-21).
It uses the same message channel as tools/flash.py (port 0x1001 -> 0x03ef), with a different service:
  - select service 2: "01 00 02 00 01 00 00 00 02" (the unit answers with service 5);
  - then messages [u16 1][u16 type][u32 length][msgpack]; type 2 is a request {102: id, 100: op, 101: args} and the
    unit answers {102: id, 103: status, 104: result}; a slow request answers status 1 first, then a type-4 message
    {105: 1, 106: {102: id, 103: 0, 104: ...}} when done. Ids start at 1000.
  More ops from a second capture (HX Edit renaming, copying and deleting, 2026-11-21):
  - op 10 rename {112: index, 109: name}: answers "working" (1), then done;
  - op 12 info {112: index}: {112, 113 checksum, 109 name, 114, 115, 123, 124, 125} (the import fields, no samples);
  - op 11 samples {112: index, 101: 2}: the samples as one raw string, in a message of type 10240, not 2;
  - copy is HX Edit's own: op 12 + op 11 from one slot, then op 9 into the other;
  - op 15 delete {112: index}: done at once (status 0);
  - HX Edit brackets edits with op 255 {} before and op 254 {} after; the unit does without them.
  - op 13 {101: 2}: the User IR list, [{112: index, 109: name, 104: MD5 of the samples (hex), ...}];
  - op 9: import {112: index (slot - 1), 113: checksum, 109: name, 114: 1, 115: 3, 123: False,
    124: False, 125: 0, 110: the samples as little-endian float32}; the checksum is the samples' little-endian 32-bit
    words summed mod 2^32. With a wrong one the unit answers 'working' (status 1), renames the slot and keeps no
    samples (its list shows no MD5), and never finishes; all strings and the samples as old-spec raw (str16
    or str32, never str8 or bin: the unit refuses those with {111: -3}). HX Edit sent the .wav's data chunk unchanged
    (2,048 mono float32 samples at 48 kHz for a NAM capture).
"""
import hashlib
import os
import struct
import sys
import time

import msgpack

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flash  # noqa: E402

SELECT_API = bytes.fromhex('010002000100000002')
OP_IR_LIST, OP_IR_IMPORT = 13, 9
SLOTS = 128


class Api:
    def __init__(self, ch):
        self.ch, self.next_id = ch, 1000

    def open(self):
        self.ch.send(SELECT_API)
        r = self.ch.recv(9)
        if r[:2] != b'\0\0' or struct.unpack_from('<I', r, 4)[0] != 1:
            raise flash.FlashError(f'unexpected service answer {r.hex()}')

    def _msg(self, timeout=30.0):
        a, typ, n = struct.unpack('<HHI', self.ch.recv(8, timeout))
        return typ, msgpack.unpackb(self.ch.recv(n, timeout), raw=True, strict_map_key=False)   # strings stay bytes: samples are a string too

    def request(self, op, args, timeout=30.0, accept_working=False):
        rid = self.next_id
        self.next_id += 1
        body = msgpack.packb({102: rid, 100: op, 101: args}, use_bin_type=False)   # the unit speaks the old msgpack spec (no str8, no bin)
        self.ch.send(struct.pack('<HHI', 1, 2, len(body)) + body)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            typ, v = self._msg(timeout)
            if typ != 4 and isinstance(v, dict) and v.get(102) == rid:      # type 2, or 10240 for the samples
                if v.get(103) == 1:                          # accepted, still working
                    if accept_working:
                        return 1, None
                    continue
                return v.get(103), v.get(104)
            if typ == 4 and isinstance(v, dict) and isinstance(v.get(106), dict) and v[106].get(102) == rid:
                return v[106].get(103), v[106].get(104)
            # anything else (status pushes) is not ours
        raise flash.FlashError(f'no answer to request {op}')

    def ir_list(self):
        st, res = self.request(OP_IR_LIST, {101: 2})
        if st != 0:
            raise flash.FlashError(f'IR list refused (status {st})')
        return [(e[112] + 1, txt(e.get(109, b'')), txt(e.get(104, b''))) for e in res]

    def ir_info(self, slot):
        if not any(e[0] == slot and e[2] for e in self.ir_list()):
            raise flash.FlashError(f'slot {slot} is empty')
        st, res = self.request(12, {112: slot - 1})
        if st != 0:
            raise flash.FlashError(f'slot {slot}: info refused (status {st})')
        return res

    def ir_samples(self, slot):
        if not any(e[0] == slot and e[2] for e in self.ir_list()):
            raise flash.FlashError(f'slot {slot} is empty')        # the unit never answers for an empty slot
        st, res = self.request(11, {112: slot - 1, 101: 2})
        if st != 0:
            raise flash.FlashError(f'slot {slot}: samples refused (status {st})')
        return bytes(res)

    def ir_rename(self, slot, name, timeout=30.0):
        st, res = self.request(10, {112: slot - 1, 109: name.encode('utf-8') + b'\0'}, accept_working=True)
        if st not in (0, 1):
            raise flash.FlashError(f'slot {slot}: rename refused (status {st})')
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = next((e for e in self.ir_list() if e[0] == slot), None)
            if got and got[1] == name:
                return got
            time.sleep(0.3)
        raise flash.FlashError(f'slot {slot} was not renamed')

    def ir_delete(self, slot, timeout=30.0):
        st, res = self.request(15, {112: slot - 1})
        if st != 0:
            raise flash.FlashError(f'slot {slot}: delete refused (status {st})')
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = next((e for e in self.ir_list() if e[0] == slot), None)
            if got is None or not got[2]:
                return
            time.sleep(0.3)
        raise flash.FlashError(f'slot {slot} was not cleared')

    def ir_copy(self, src, dst):
        name = txt(self.ir_info(src)[109])
        return self.ir_put(dst, self.ir_samples(src), name)

    def ir_put(self, slot, samples, name, timeout=30.0):
        """Send it, then wait until the slot's list entry shows these samples' MD5 (the unit's 'done' message only
        goes to a client subscribed for notifications, so the list is the check)."""
        st, res = self.request(OP_IR_IMPORT, {112: slot - 1, 113: word_sum(samples), 109: name.encode('utf-8') + b'\0',
                                              114: 1, 115: 3, 123: False, 124: False, 125: 0, 110: samples},
                               accept_working=True)
        if st not in (0, 1):
            raise flash.FlashError(f'import refused (status {st}, {res})')
        want, end = hashlib.md5(samples).hexdigest(), time.monotonic() + timeout
        while time.monotonic() < end:
            got = next((e for e in self.ir_list() if e[0] == slot), None)
            if got and got[2] == want:
                return got
            time.sleep(0.5)
        raise flash.FlashError(f'slot {slot} did not end up holding the samples (MD5 {want})')


def txt(b):
    """A string from the unit (raw bytes, NUL-terminated) as text."""
    return bytes(b).split(b'\0')[0].decode('utf-8', 'replace') if isinstance(b, (bytes, bytearray)) else str(b or '')


def word_sum(samples):
    """Field 113: the samples' little-endian 32-bit words, summed mod 2^32."""
    return sum(struct.unpack(f'<{len(samples) // 4}I', samples[:len(samples) // 4 * 4])) & 0xffffffff


def wav_samples(path):
    """The data chunk of a mono 32-bit float .wav (as nam2ir.py writes and HX Edit sends)."""
    raw = open(path, 'rb').read()
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise SystemExit(f'{path}: not a .wav file')
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        cid, n = raw[pos:pos + 4], struct.unpack_from('<I', raw, pos + 4)[0]
        if cid == b'fmt ':
            fmt = struct.unpack_from('<HHIIHH', raw, pos + 8)
        elif cid == b'data':
            data = raw[pos + 8:pos + 8 + n]
        pos += 8 + n + (n & 1)
    if not fmt or data is None:
        raise SystemExit(f'{path}: no fmt or data chunk')
    tag, ch, rate, _, _, bits = fmt
    if (tag, ch, rate, bits) != (3, 1, 48000, 32):
        raise SystemExit(f'{path}: {ch} ch, {rate} Hz, {bits}-bit (format {tag}); this tool sends 48 kHz mono 32-bit float '
                         f'.wav files only (what nam2ir.py writes)')
    return data


def session(fn):
    mode, d = flash.which_mode()
    if mode != 'main':
        raise flash.FlashError('no HX Effects running its main app on USB' if mode is None else f'the unit is in {mode} mode')
    flash.claim(d)
    try:
        ch = flash.Channel(d)
        ch.open()
        api = Api(ch)
        try:
            api.open()
            return fn(api)
        finally:
            ch.close()                     # always: a channel left open stops the next connect for a while
    finally:
        flash.release(d)


def main():
    a = sys.argv[1:]
    try:
        if a[:1] == ['list']:
            for slot, name, md5 in session(lambda api: api.ir_list()):
                print(f'{slot:3d}  {name:40s} {md5}')
        elif a[:1] == ['put'] and len(a) in (3, 4):
            slot = int(a[1])
            if not 1 <= slot <= SLOTS:
                raise SystemExit(f'slot {slot}: must be 1..{SLOTS}')
            samples = wav_samples(a[2])
            name = a[3] if len(a) == 4 else os.path.splitext(os.path.basename(a[2]))[0]

            def put(api):
                api.ir_put(slot, samples, name)
                return api.ir_list()   # read back once more
            lst = session(put)
            got = next((e for e in lst if e[0] == slot), None)
            want = hashlib.md5(samples).hexdigest()
            ok = got is not None and got[1] == name and got[2] == want
            print(f'slot {slot}: {got[1] if got else "(empty)"}  {got[2] if got else ""}')
            print('OK: the slot holds exactly these samples' if ok else f'MISMATCH: expected {name!r} {want}')
            sys.exit(0 if ok else 1)
        elif a[:1] == ['rename'] and len(a) == 3:
            print(session(lambda api: api.ir_rename(int(a[1]), a[2])))
        elif a[:1] == ['copy'] and len(a) == 3:
            print(session(lambda api: api.ir_copy(int(a[1]), int(a[2]))))
        elif a[:1] == ['delete'] and len(a) == 2:
            session(lambda api: api.ir_delete(int(a[1])))
            print(f'slot {a[1]} cleared')
        elif a[:1] == ['get'] and len(a) == 3:
            data = session(lambda api: api.ir_samples(int(a[1])))
            open(a[2], 'wb').write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' +
                                   struct.pack('<IHHIIHH', 16, 3, 1, 48000, 192000, 4, 32) + b'data' +
                                   struct.pack('<I', len(data)) + data)
            print(f'slot {a[1]}: {len(data)} bytes -> {a[2]} (MD5 {hashlib.md5(data).hexdigest()})')
        else:
            sys.exit(__doc__)
    except flash.FlashError as ex:
        sys.exit(f'ir_upload.py: {ex}')


if __name__ == '__main__':
    main()
