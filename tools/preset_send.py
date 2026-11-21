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
  .venv/bin/python tools/preset_send.py build SLOT SPEC.json [--base SLOT] [--image FILE.hxf]
                                                                build a preset from SPEC and write it to SLOT
  .venv/bin/python tools/preset_send.py models [--image FILE.hxf]
                                                                the models the image lists: name, preset id, knobs

SPEC: {"name": "My Preset", "blocks": [{"pos": 1, "model": "HD2_DistRegalBassDIMono", "on": true,
       "values": [5, 0.6, ...] or {"Drive": 0.6, ...}, "footswitch": 1, "label": "NAM"}, ...]}
  model is a firmware model name (models lists them; a custom effect is listed under the stock block it took over,
  with its own knobs); values are by position or by knob name, the rest stay at the model's defaults; footswitch is
  1..6. The base preset (default: SLOT itself, else 1A) gives the snapshot, tempo and global settings; its blocks and
  footswitches are cleared first. --image is the firmware on the unit (default build/HX_Effects_v3.80.0_NAM_Amps_Effects.hxf).
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
    return struct.unpack(f'<{len(table) // 4}I', table), body


def build_blob(table, body):
    """parse_blob's inverse, encoded as HX Edit does (old-spec msgpack, float32)."""
    pk = lambda x: msgpack.packb(x, use_bin_type=False, use_single_float=True)
    return pk(b'l6-helix\0') + pk(struct.pack(f'<{len(table)}I', *table)) + pk(body)


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


def spans(blob):
    """{path: (start, end)} for every node of the preset map (containers too), in the blob's own bytes."""
    out = {}
    u = msgpack.Unpacker(raw=True, strict_map_key=False)
    u.feed(blob)
    u.unpack()
    u.unpack()
    start = u.tell()

    def end_of(o):
        v = msgpack.Unpacker(raw=True, strict_map_key=False)
        v.feed(blob[o:])
        v.unpack()
        return o + v.tell()

    def walk(o, path):
        t = blob[o]
        if t & 0xF0 == 0x80 or t in (0xDE, 0xDF):
            n, p = (t & 15, o + 1) if t & 0xF0 == 0x80 else (int.from_bytes(blob[o + 1:o + (3 if t == 0xDE else 5)], 'big'), o + (3 if t == 0xDE else 5))
            for _ in range(n):
                ke = end_of(p)
                k = msgpack.unpackb(blob[p:ke], raw=True)
                p = walk(ke, path + (k,))
        elif t & 0xF0 == 0x90 or t in (0xDC, 0xDD):
            n, p = (t & 15, o + 1) if t & 0xF0 == 0x90 else (int.from_bytes(blob[o + 1:o + (3 if t == 0xDC else 5)], 'big'), o + (3 if t == 0xDC else 5))
            for i in range(n):
                p = walk(p, path + (i,))
        else:
            p = end_of(o)
        out[path] = (o, p)
        return p
    walk(start, ())
    return out


def replace_node(blob, path, value):
    """blob with the node at path replaced by value (encoded as HX Edit does), the section table kept right."""
    o, e = spans(blob)[tuple(path)]
    new = msgpack.packb(value, use_bin_type=False, use_single_float=True)
    table, _ = parse_blob(blob)
    delta = len(new) - (e - o)
    out = blob[:o] + new + blob[e:]
    table = [x + delta if x > o else x for x in table]
    head = msgpack.packb(b'l6-helix\0', use_bin_type=False)
    tbl = msgpack.packb(struct.pack(f'<{len(table)}I', *table), use_bin_type=False)
    return head + tbl + out[len(head) + len(tbl):]


def footswitch(pos, label, colour=525824):
    """One footswitch entry turning the block at pos on and off, as the unit writes it (preset 1B)."""
    return [{10: 7, 11: {0: 1, 5: label.encode('utf-8') + b'\0', 6: colour, 7: False, 8: pos}, 12: False, 14: b'\0',
             13: False, 16: 0, 15: False}]


TRAILS_TYPES = (8, 9, 13)        # block types whose value list ends with a Trails switch (n2 = n3 + 1)
EMPTY_BLOCK = msgpack.packb({19: 8, 20: None})


def model_table(image):
    """{name: {pid, btype, params}} for the models a firmware image lists, and the same keyed by preset id (pid).
    pid: what a preset stores (Entry 0 Table 1); btype: the browser item's first byte, which a preset stores as
    block field 9; params: the model's knobs in order (Entry 3; in a built image a custom effect's host carries the
    custom effect's knobs), each {name, type (1 switch, 2 whole number, 3 decimal), default, min, max}."""
    sys.path.insert(0, os.path.dirname(HERE))
    import patch_amp as pa
    arc, _ = pa.load_l6ia_from_any(image)
    e0 = bytearray(pa.get_entry_swapped(arc, 0))
    info = pa.parse_entry3_full(bytes(pa.get_entry_swapped(arc, 3)))
    A, segs = pa.EFFECTS_E0, pa._parse_e0_segments_any(e0)
    fo = lambda va, n=4: pa._e0_vaddr_to_foff(segs, va, n)
    u32 = lambda va: struct.unpack_from('<I', e0, fo(va))[0]
    pid = {}
    for i in range(A.TAB1_CNT):
        n, p, _, _ = struct.unpack_from('<IHHI', e0, fo(A.TAB1_BASE + 12 * i, 12))
        pid[n] = p
    btype = {}
    for sl in range(52):
        lp, lc = u32(A.BLIST_PTR_TAB + 4 * sl), u32(A.BLIST_CNT_TAB + 4 * sl)
        for k in range(lc if lp else 0):
            btype[u32(lp + 48 * k + 4)] = e0[fo(lp + 48 * k, 1)]
    by_name, by_pid = {}, {}
    for m in info['models']:
        ni = m['words'][2]
        if ni in pid and ni in btype:
            e = {'name': m['name'], 'display': m['displayName'], 'pid': pid[ni], 'btype': btype[ni],
                 'params': [{k: p[k] for k in ('name', 'type', 'default', 'min', 'max')} for p in m['params']]}
            by_name[m['name']] = e
            by_pid.setdefault(pid[ni], e)
    return by_name, by_pid


def block_value(t, v):
    if isinstance(v, float) and v != v:           # some knobs have no default (NaN) in the firmware
        v = 0
    return bool(v) if t == 1 else int(round(v)) if t == 2 else float(v)


def make_block(model, values=None, on=True):
    """A block map for a model_table() entry: knob values by position (defaults where values is None or shorter),
    with a Trails switch (off) for delays/reverbs that have no DryThru-style last knob of their own."""
    ps_ = model['params']
    vals = [block_value(p['type'], p['default']) for p in ps_]
    for i, v in enumerate(values or []):
        if i < len(vals):
            vals[i] = block_value(ps_[i]['type'], v)
    n3 = len(vals)
    if model['btype'] in TRAILS_TYPES:
        if ps_ and ps_[-1]['type'] == 1 and ps_[-1]['name'] in ('DryThru', 'Trails'):
            n3 -= 1
        else:
            vals.append(bool(values[len(ps_)]) if values and len(values) > len(ps_) else False)
    return {19: 6, 20: {24: {23: False, 25: model['pid'], 26: -1}, 9: model['btype'], 10: bool(on),
                        11: {2: len(vals), 3: n3, 4: vals}, 12: {2: 0, 3: 0, 4: []}}}


def _entry_offset(blob, pos):
    """Byte offset and length of block-list entry pos (preset map key 0 -> key 22 -> [pos])."""
    loc = locate(blob)
    o = loc[(0, 22, pos, 19)][0] - 2              # the entry map header (0x82) and key 19 come first
    u = msgpack.Unpacker(raw=True, strict_map_key=False)
    u.feed(blob[o:])
    u.unpack()
    return o, u.tell()


def _replace_entry(blob, pos, new_bytes):
    table, _ = parse_blob(blob)
    o, n = _entry_offset(blob, pos)
    delta = len(new_bytes) - n
    out = blob[:o] + new_bytes + blob[o + n:]
    table = [x + delta if x > o else x for x in table]       # section ends after the entry move with it
    tbl = msgpack.packb(struct.pack(f'<{len(table)}I', *table), use_bin_type=False)
    head = msgpack.packb(b'l6-helix\0', use_bin_type=False)
    assert out[len(head):len(head) + len(tbl)][:3] == tbl[:3]
    return head + tbl + out[len(head) + len(tbl):]


def _set_snapshot_states(blob, pos, on):
    """Every snapshot's on/off for block position pos (map key 10 -> 10 -> [snap] -> 3 -> [pos] -> 1)."""
    _, body = parse_blob(blob)
    for k, snap in enumerate(body.get(10, {}).get(10, []) or []):
        st = snap.get(3) if isinstance(snap, dict) else None
        if st and pos < len(st) and isinstance(st[pos], list) and len(st[pos]) > 1 and st[pos][1] is not None:
            blob = set_in_place(blob, (10, 10, k, 3, pos, 1), bool(on))
    return blob


def add_block(blob, pos, model, values=None, on=True):
    """blob with model placed in the empty block position pos (1..9 on path A)."""
    o, n = _entry_offset(blob, pos)
    if blob[o:o + n] != EMPTY_BLOCK:
        raise SystemExit(f'block position {pos} is not empty')
    blob = _replace_entry(blob, pos, msgpack.packb(make_block(model, values, on), use_bin_type=False, use_single_float=True))
    return _set_snapshot_states(blob, pos, on)


def remove_block(blob, pos):
    """blob with block position pos emptied (snapshot states for it set on, as an empty position has them)."""
    _, body = parse_blob(blob)
    if body[0][22][pos][19] != 6:
        raise SystemExit(f'block position {pos} holds no effect block')
    return _set_snapshot_states(_replace_entry(blob, pos, EMPTY_BLOCK), pos, True)


DEFAULT_IMAGE = os.path.join(os.path.dirname(HERE), 'build', 'HX_Effects_v3.80.0_NAM_Amps_Effects.hxf')


def build_preset(base, spec, by_name):
    """A preset blob from a base blob (its blocks and footswitches cleared) and a SPEC dict (see the usage)."""
    _, body = parse_blob(base)
    blob = base
    for pos, blk in enumerate(body[0][22]):
        if blk[19] == 6:
            blob = remove_block(blob, pos)
    for j in range(len(body[3][8])):
        blob = replace_node(blob, (3, 8, j), None)
    for b in spec['blocks']:
        m = by_name.get(b['model'])
        if not m:
            raise SystemExit(f"unknown model {b['model']!r} (see: preset_send.py models)")
        vals = b.get('values')
        if isinstance(vals, dict):
            names = [p['name'] for p in m['params']]
            bad = [k for k in vals if k not in names]
            if bad:
                raise SystemExit(f"{b['model']}: no knob {bad} (knobs: {names})")
            vals = [vals.get(p['name'], p['default']) for p in m['params']]
        if not 1 <= int(b['pos']) <= 9:
            raise SystemExit('block positions are 1..9 (path A)')
        blob = add_block(blob, int(b['pos']), m, vals, b.get('on', True))
        if b.get('footswitch'):
            fs = int(b['footswitch'])
            if not 1 <= fs <= len(body[3][8]):
                raise SystemExit(f'footswitch {fs}: 1..{len(body[3][8])}')
            blob = replace_node(blob, (3, 8, fs - 1), footswitch(int(b['pos']), b.get('label') or m['display'] or m['name']))
    return blob


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
        elif a[:1] == ['models']:
            img = a[a.index('--image') + 1] if '--image' in a else DEFAULT_IMAGE
            by_name, _ = model_table(img)
            for nm, m in sorted(by_name.items(), key=lambda kv: kv[1]['pid']):
                print(f"{m['pid']:4d} {nm:36s} {m['display'][:24]:24s} " + ', '.join(p['name'] for p in m['params']))
        elif a[:1] == ['build'] and len(a) >= 3:
            n, spec = slot_index(a[1]), json.load(open(a[2]))
            img = a[a.index('--image') + 1] if '--image' in a else DEFAULT_IMAGE
            by_name, _ = model_table(img)

            def go(api):
                bases = [slot_index(a[a.index('--base') + 1])] if '--base' in a else [n, 0]
                base = None
                for bi in bases:
                    st, r = api.request(4, {107: SETLIST, 108: bi, 101: 2})
                    if isinstance(r, (bytes, bytearray)):
                        base = bytes(r)
                        break
                if base is None:
                    raise flash.FlashError('no base preset to build on (try --base 1A)')
                blob = build_preset(base, spec, by_name)
                api.preset_write(n, blob, spec.get('name', 'New Preset'))
                return blob, api.preset_read(n)
            blob, back = session(go)
            print(f"{slot_name(n)}: built {len(blob)} bytes ({len(spec['blocks'])} blocks), wrote it as "
                  f"{spec.get('name', 'New Preset')!r}; read back: " + ('IDENTICAL' if back == blob else 'DIFFERENT'))
        else:
            sys.exit(__doc__)
    except flash.FlashError as ex:
        sys.exit(f'preset_send.py: {ex}')


if __name__ == '__main__':
    main()
