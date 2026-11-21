#!/usr/bin/env python3
"""preset_send.py - read, write and play with HX Effects presets over USB, without HX Edit.

usage:
  .venv/bin/python tools/preset_send.py list                    the presets: index, bank/slot (1A..), name
  .venv/bin/python tools/preset_send.py current                 the loaded preset
  .venv/bin/python tools/preset_send.py read SLOT FILE          save a preset's blob (FILE.bin) and a readable
                                                                dump of it (FILE.json)
  .venv/bin/python tools/preset_send.py write SLOT FILE.bin [NAME]
                                                                write a blob into a slot, then read it back
  .venv/bin/python tools/preset_send.py rename SLOT NAME
  .venv/bin/python tools/preset_send.py load SLOT               switch the unit to that preset
  .venv/bin/python tools/preset_send.py knob BLOCK KNOB VALUE   set a knob on the loaded preset, live
  .venv/bin/python tools/preset_send.py bypass BLOCK on|off     turn a block of the loaded preset on or off
SLOT is an index (0..127) or bank/slot like 22D. Close HX Edit first.

Every request here was seen in a capture of HX Edit (docs/hxedit-preset-format.md, "On the wire"); nothing else is
sent. Same channel as tools/ir_upload.py (service 2, old-spec msgpack), plus "live" requests framed as type 6 with
their own ids. Floats go as float32, as HX Edit sends them.
"""
import hashlib
import json
import os
import struct
import sys
import time

import msgpack

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flash  # noqa: E402
import ir_upload as iu  # noqa: E402

SETLIST = 0
PRESETS = 128


def slot_index(s):
    """'22D' -> 87, '5' -> 5."""
    s = str(s).strip().upper()
    if s[-1:] in 'ABCD' and s[:-1].isdigit():
        n = (int(s[:-1]) - 1) * 4 + 'ABCD'.index(s[-1])
    else:
        n = int(s)
    if not 0 <= n < PRESETS:
        raise SystemExit(f'preset {s}: out of range')
    return n


def slot_name(n):
    return f'{n // 4 + 1}{"ABCD"[n % 4]}'


class Api(iu.Api):
    """ir_upload's channel and service, with type-6 ("live") requests and float32 floats."""

    def __init__(self, ch):
        super().__init__(ch)
        self.rid = 1000          # one counter for both types: the unit may answer a type-6 request as type 2

    def request(self, op, args, timeout=30.0, accept_working=False, typ=2):
        rid = self.rid
        self.rid += 1
        body = msgpack.packb({102: rid, 100: op, 101: args}, use_bin_type=False, use_single_float=True)
        self.ch.send(struct.pack('<HHI', 1, typ, len(body)) + body)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            mtyp, v = self._msg(timeout)
            if mtyp == 4 and isinstance(v, dict) and isinstance(v.get(106), dict) and v[106].get(102) == rid:
                return v[106].get(103), v[106].get(104)
            if mtyp != 4 and isinstance(v, dict) and v.get(102) == rid:
                if v.get(103) == 1 and not accept_working:
                    continue                                 # "working": wait for the done notification
                return v.get(103), v.get(104)
        raise flash.FlashError(f'no answer to request {op}')

    def preset_list(self):
        st, res = self.request(1, {107: SETLIST, 101: 2})
        if st != 0:
            raise flash.FlashError(f'preset list refused ({st})')
        out = []
        for e in res:
            (k, v), = e.items()
            out.append((k, iu.txt(v.get(109, b''))))
        return out

    def preset_read(self, n):
        st, res = self.request(4, {107: SETLIST, 108: n, 101: 2})
        if st != 0 or not isinstance(res, (bytes, bytearray)):
            raise flash.FlashError(f'preset {slot_name(n)}: read refused ({st})')
        return bytes(res)

    def preset_write(self, n, blob, name):
        self.request(255, {})
        try:
            st, res = self.request(8, {107: SETLIST, 108: n, 109: name.encode('utf-8') + b'\0', 123: False,
                                       124: False, 125: 0, 110: blob}, accept_working=True)
        finally:
            self.request(254, {})
        if st not in (0, 1):          # 1: "working"; the done notification only reaches a subscribed client
            raise flash.FlashError(f'preset {slot_name(n)}: write refused ({st}, {res})')
        time.sleep(0.5)

    def preset_rename(self, n, name):
        st, res = self.request(6, {107: SETLIST, 108: n, 109: name.encode('utf-8') + b'\0'}, accept_working=True)
        if st not in (0, 1):
            raise flash.FlashError(f'preset {slot_name(n)}: rename refused ({st})')

    def current(self):
        st, res = self.request(23, None, typ=6)
        if st != 0:
            raise flash.FlashError(f'current preset refused ({st})')
        return res[108], iu.txt(res.get(109, b''))

    def load(self, n):
        st, res = self.request(20, {107: SETLIST, 108: n}, typ=6, accept_working=True)
        if st not in (0, 1):
            raise flash.FlashError(f'load {slot_name(n)} refused ({st})')

    def knob(self, block, knob, value):
        st, res = self.request(30, {98: block, 29: True, 26: 0, 28: knob, 119: value}, typ=6)
        if st != 0:
            raise flash.FlashError(f'block {block} knob {knob}: refused ({st})')
        return res

    def bypass(self, block, on):
        st, res = self.request(41, {98: block, 59: bool(on)}, typ=6)
        if st != 0:
            raise flash.FlashError(f'block {block}: on/off refused ({st})')


def parse_blob(blob):
    """The blob's parts: 'l6-helix', the 12 section offsets, and the preset map."""
    u = msgpack.Unpacker(raw=True, strict_map_key=False)
    u.feed(blob)
    magic, table, body = next(u), next(u), next(u)
    if magic.rstrip(b'\0') != b'l6-helix':
        raise SystemExit('not a preset blob')
    return struct.unpack('<12I', table), body


def build_blob(table, body):
    """parse_blob's inverse, encoded as HX Edit does (old-spec msgpack, float32)."""
    pk = lambda x: msgpack.packb(x, use_bin_type=False, use_single_float=True)
    return pk(b'l6-helix\0') + pk(struct.pack('<12I', *table)) + pk(body)


def locate(blob):
    """{path tuple: (offset, type byte)} for every scalar in the preset map, so a value can be changed in place with
    the type and size HX Edit chose (it writes some ints as int16 even when 0, so re-encoding is not byte-identical)."""
    out, pos = {}, [0]

    def rd(n):
        o = pos[0]
        pos[0] += n
        return blob[o:o + n]

    def be(n):
        return int.from_bytes(rd(n), 'big')

    def walk(path):
        o, t = pos[0], blob[pos[0]]
        pos[0] += 1
        if t < 0x80 or t >= 0xE0 or t in (0xC0, 0xC2, 0xC3):
            out[path] = (o, t)
        elif t & 0xF0 == 0x80 or t in (0xDE, 0xDF):
            n = t & 15 if t & 0xF0 == 0x80 else be(2 if t == 0xDE else 4)
            for _ in range(n):
                ko = pos[0]
                walk(('key',))
                k = msgpack.unpackb(blob[ko:pos[0]], raw=True)
                walk(path + (k,))
        elif t & 0xF0 == 0x90 or t in (0xDC, 0xDD):
            n = t & 15 if t & 0xF0 == 0x90 else be(2 if t == 0xDC else 4)
            for i in range(n):
                walk(path + (i,))
        elif t & 0xE0 == 0xA0 or t in (0xD9, 0xDA, 0xDB, 0xC4, 0xC5, 0xC6):
            n = t & 31 if t & 0xE0 == 0xA0 else be({0xD9: 1, 0xDA: 2, 0xDB: 4, 0xC4: 1, 0xC5: 2, 0xC6: 4}[t])
            out[path] = (o, t)
            pos[0] += n
        else:
            size = {0xCA: 4, 0xCB: 8, 0xCC: 1, 0xCD: 2, 0xCE: 4, 0xCF: 8, 0xD0: 1, 0xD1: 2, 0xD2: 4, 0xD3: 8}.get(t)
            if size is None:
                raise SystemExit(f'preset blob: msgpack type 0x{t:02x} at {o}')
            out[path] = (o, t)
            pos[0] += size
    walk(())                                     # 'l6-helix'
    walk(())                                     # the offset table
    start = pos[0]
    walk(())
    assert pos[0] == len(blob), 'trailing bytes after the preset map'
    return {p: v for p, v in out.items() if p and p[0] != 'key' and v[0] >= start}


def set_in_place(blob, path, value):
    """blob with the scalar at path replaced, keeping its msgpack type and size."""
    off, t = locate(blob)[tuple(path)]
    b = bytearray(blob)
    if t == 0xCA:
        b[off + 1:off + 5] = struct.pack('>f', float(value))
    elif t == 0xCB:
        b[off + 1:off + 9] = struct.pack('>d', float(value))
    elif t in (0xC2, 0xC3):
        b[off] = 0xC3 if value else 0xC2
    elif t in (0xD0, 0xD1, 0xD2):
        b[off + 1:off + 1 + {0xD0: 1, 0xD1: 2, 0xD2: 4}[t]] = int(value).to_bytes({0xD0: 1, 0xD1: 2, 0xD2: 4}[t], 'big', signed=True)
    elif t in (0xCC, 0xCD, 0xCE):
        b[off + 1:off + 1 + {0xCC: 1, 0xCD: 2, 0xCE: 4}[t]] = int(value).to_bytes({0xCC: 1, 0xCD: 2, 0xCE: 4}[t], 'big')
    elif t < 0x80 and 0 <= int(value) < 0x80:
        b[off] = int(value)
    else:
        raise SystemExit(f'{path}: cannot change a value of msgpack type 0x{t:02x} in place to {value!r}')
    return bytes(b)


def readable(x):
    if isinstance(x, (bytes, bytearray)):
        b = bytes(x)
        return b.split(b'\0')[0].decode('utf-8', 'replace') if len(b) < 200 else f'<{len(b)} bytes>'
    if isinstance(x, dict):
        return {str(k): readable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [readable(v) for v in x]
    return x


def session(fn):
    mode, d = flash.which_mode()
    if mode != 'main':
        raise flash.FlashError('no HX Effects running its main app on USB' if mode is None else f'the unit is in {mode} mode')
    flash.claim(d)
    try:
        ch = flash.Channel(d)
        ch.open()
        try:
            api = Api(ch)
            api.open()
            return fn(api)
        finally:
            ch.close()
    finally:
        flash.release(d)


def main():
    a = sys.argv[1:]
    try:
        if a[:1] == ['list']:
            for n, name in session(lambda api: api.preset_list()):
                print(f'{n:3d} {slot_name(n):>4}  {name}')
        elif a[:1] == ['current']:
            n, name = session(lambda api: api.current())
            print(f'{n} {slot_name(n)}  {name}')
        elif a[:1] == ['read'] and len(a) == 3:
            n = slot_index(a[1])
            blob = session(lambda api: api.preset_read(n))
            stem = os.path.splitext(a[2])[0]
            open(stem + '.bin', 'wb').write(blob)
            table, body = parse_blob(blob)
            json.dump({'slot': slot_name(n), 'table': table, 'preset': readable(body)}, open(stem + '.json', 'w'), indent=1)
            print(f'{slot_name(n)}: {len(blob)} bytes, MD5 {hashlib.md5(blob).hexdigest()} -> {stem}.bin, {stem}.json')
        elif a[:1] == ['write'] and len(a) in (3, 4):
            n, blob = slot_index(a[1]), open(a[2], 'rb').read()
            parse_blob(blob)
            names = dict(session(lambda api: api.preset_list()))
            name = a[3] if len(a) == 4 else names.get(n, 'New Preset')

            def go(api):
                api.preset_write(n, blob, name)
                return api.preset_read(n), dict(api.preset_list()).get(n)
            back, got_name = session(go)
            same = back == blob
            print(f'{slot_name(n)}: wrote {len(blob)} bytes as {name!r}; read back {len(back)} bytes, name {got_name!r}: '
                  + ('IDENTICAL' if same else f'DIFFERENT (MD5 {hashlib.md5(back).hexdigest()} vs {hashlib.md5(blob).hexdigest()})'))
        elif a[:1] == ['rename'] and len(a) == 3:
            n = slot_index(a[1])
            session(lambda api: api.preset_rename(n, a[2]))
            print(f'{slot_name(n)} renamed to {a[2]!r}')
        elif a[:1] == ['load'] and len(a) == 2:
            n = slot_index(a[1])
            session(lambda api: api.load(n))
            print(f'loaded {slot_name(n)}')
        elif a[:1] == ['knob'] and len(a) == 4:
            v = a[3]
            val = (v.lower() == 'true') if v.lower() in ('true', 'false') else (float(v) if '.' in v or 'e' in v.lower() else int(v))
            print(session(lambda api: api.knob(int(a[1]), int(a[2]), val)))
        elif a[:1] == ['bypass'] and len(a) == 3 and a[2] in ('on', 'off'):
            session(lambda api: api.bypass(int(a[1]), a[2] == 'on'))
            print(f'block {a[1]} {a[2]}')
        else:
            sys.exit(__doc__)
    except flash.FlashError as ex:
        sys.exit(f'preset_send.py: {ex}')


if __name__ == '__main__':
    main()
