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

SPEC: {"name": "My Preset", "split": 1, "merge": 10, "blocks": [{"pos": 1, "model": "HD2_DistRegalBassDIMono", "on": true,
       "values": [5, 0.6, ...] or {"Drive": 0.6, ...}, "footswitch": 1, "label": "NAM"}, ...]}
  model is a firmware model name (models lists them; a custom effect is listed under the stock block it took over,
  with its own knobs); values are by position or by knob name, the rest stay at the model's defaults; footswitch is
  1..6. pos is 1..9 on the main path, 12..20 on the lower path (between the split and the merge, whose places
  "split"/"merge" set, 0..10). "split_values": [Balance A, Balance B] (0..1, 0.5 centre) and "merge_values": [A Level,
  A Pan, B Level, B Pan, B Polarity, Level] (dB -60..12, pans 0..1, polarity true = inverted) set the split and merge. An IR block's first knob is its User IR slot, which must hold an IR. The base preset (default: SLOT itself, else 1A) gives the snapshot, tempo and global settings; its blocks and
  footswitches are cleared first.
  "snapshots": {"current": 1, "names": ["Clean", "Drive", ...], "states": {"2": [true, true, false, true]},
                "knobs": [{"pos": 1, "knob": "Drive", "values": [0.1, 0.2, 0.3, 0.4]}, ...]}
  sets the snapshots: states turns a block on or off per snapshot; knobs gives a knob a value per snapshot.
  "controls": [{"pos": 2, "knob": "Gain", "source": "exp1", "min": 0.2, "max": 0.8},
               {"pos": 2, "knob": "Level", "source": "fs2", "min": 0.3, "max": 0.7, "label": "Level"},
               {"pos": 2, "knob": "Tone", "source": "midi", "cc": 21}]
  puts knobs on EXP pedals 1/2, footswitches 1..6 (switching between min and max) or MIDI CCs. A block can also have
  "footswitch": 1 (one per block; several blocks may share a switch), "midi_bypass": CC and "snapshot_bypass": false. --image is the firmware on the unit (default build/HX_Effects_v3.80.0_NAM_Amps_Effects.hxf).
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

    def wait_done(self, rid, seconds):
        """Wait for the unit's "done" notification for request rid. Notifications come on their own connection
        (self.notes: host port 0x1002, unit port 0x03f0, service 4), as HX Edit opens it; False if none came in time."""
        ch = getattr(self, 'notes', None) or self.ch
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if len(ch.rx) < 8:
                ch._pump(20)
                continue
            a, mtyp, n = struct.unpack('<HHI', ch.recv(8, 30.0))
            v = msgpack.unpackb(ch.recv(n, 30.0), raw=True, strict_map_key=False)
            if mtyp == 4 and isinstance(v, dict) and isinstance(v.get(106), dict) and v[106].get(102) == rid:
                return True
        return False

    def preset_write(self, n, blob, name):
        if len(name.encode('utf-8')) > 16:
            raise flash.FlashError(f'preset name {name!r}: at most 16 bytes')
        self.request(255, {})
        try:
            rid = self.rid
            st, res = self.request(8, {107: SETLIST, 108: n, 109: name.encode('utf-8') + b'\0', 123: False,
                                       124: False, 125: 0, 110: blob}, accept_working=True)
            # 1 = "working": the unit stores the file after answering. HX Edit sends the closing 254 only after the
            # done notification (capture 2026-11-21); closing at once left slots with a scrambled start (2026-11-22).
            if st == 1:
                self.last_done = self.wait_done(rid, 5.0)
        finally:
            self.request(254, {})
        if st not in (0, 1):
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
    # 11 -> 7 True: the switch toggles its block on its own; False made the preset's switches act as an either/or group
    # (FS Test A/B, 2026-11-22). HX Edit writes True for bypass switches.
    return [{10: 7, 11: {0: 1, 5: label.encode('utf-8') + b'\0', 6: colour, 7: True, 8: pos}, 12: False, 14: b'\0',
             13: False, 16: 0, 15: False}]


def fs_knob(pos, ki, label, colour=462860):
    """A footswitch entry that switches a knob between its controller's min and max (preset 25C)."""
    return {10: 0, 11: {0: 2, 5: label.encode('utf-8') + b'\0', 6: colour, 7: False, 8: pos, 2: 0,
                        9: {28: 0, 29: ki, 41: False}}, 12: False, 14: b'\0', 13: False, 16: 0, 15: False}


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
    t1 = u32(A.TAB1_BASE_PTRS[0])                    # the live table: the amps build moves and grows it
    t1_cnt = max(pa._decode_thumb_movw(bytes(e0[fo(va, 4):][:4]))[1] for va in A.TAB1_CNT_INSNS)   # 688 with amps
    for i in range(t1_cnt):
        try:
            n, p, _, _ = struct.unpack_from('<IHHI', e0, fo(t1 + 12 * i, 12))
        except Exception:
            break
        if p > 0x1000 or n > 0x10000:
            break
        pid.setdefault(n, p)
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
                 'params': [knob(p) for p in m['params']]}
            by_name[m['name']] = e
            by_pid.setdefault(pid[ni], e)
    return by_name, by_pid


def knob(p):
    """A model parameter as {name, type, default, min, max}. Entry 3 keeps a switch's or whole number's default,
    min and max as integers in the same words as a decimal's floats (parse_entry3_full reads them all as floats, so
    6 came out as 8.4e-45): read those back as the integers they are."""
    out = {'name': p['name'], 'type': p['type']}
    for k in ('default', 'min', 'max'):
        v = p[k]
        if p['type'] in (1, 2):
            v = struct.unpack('<i', struct.pack('<f', v))[0]
            v = bool(v) if p['type'] == 1 else v
        out[k] = v
    return out


def block_value(t, v):
    if isinstance(v, float) and v != v:           # some knobs have no default (NaN) in the firmware
        v = 0
    return bool(v) if t == 1 else int(round(v)) if t == 2 else float(v)


IR_TYPE = 19                     # IR blocks: no field 12, and field 27 = the MD5 (hex) of the IR in their slot


def make_block(model, values=None, on=True, ir_md5=None):
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
    blk = {24: {23: False, 25: model['pid'], 26: -1}, 9: model['btype'], 10: bool(on), 11: {2: len(vals), 3: n3, 4: vals}}
    if model['btype'] == IR_TYPE:
        if not ir_md5:
            raise SystemExit(f"{model['name']}: an IR block needs the MD5 of the IR in its slot (ir_upload.py list)")
        blk[27] = ir_md5.encode() if isinstance(ir_md5, str) else ir_md5
    else:
        blk[12] = {2: 0, 3: 0, 4: []}
    return {19: 6, 20: blk}


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


PATH_A, PATH_B = range(1, 10), range(12, 21)     # block positions; 0 input, 10 output, 11 split, 21 merge


def set_path_b(blob, used):
    """Split (position 11) and merge (21) flag 18: on when the lower path holds a block; map 0 key 21 likewise."""
    for path in ((0, 22, 11, 20, 18), (0, 22, 21, 20, 18)):
        blob = set_in_place(blob, path, bool(used))
    return set_in_place(blob, (0, 21), 1 if used else 0)


def add_block(blob, pos, model, values=None, on=True, ir_md5=None):
    """blob with model placed in the empty block position pos (1..9 path A, 12..20 path B)."""
    if pos not in PATH_A and pos not in PATH_B:
        raise SystemExit(f'block position {pos}: 1..9 (main path) or 12..20 (lower path)')
    o, n = _entry_offset(blob, pos)
    if blob[o:o + n] != EMPTY_BLOCK:
        raise SystemExit(f'block position {pos} is not empty')
    blob = _replace_entry(blob, pos, msgpack.packb(make_block(model, values, on, ir_md5), use_bin_type=False,
                                                   use_single_float=True))
    if pos in PATH_B:
        blob = set_path_b(blob, True)
    return _set_snapshot_states(blob, pos, on)


def remove_block(blob, pos):
    """blob with block position pos emptied (snapshot states for it set on, as an empty position has them)."""
    _, body = parse_blob(blob)
    if body[0][22][pos][19] != 6:
        raise SystemExit(f'block position {pos} holds no effect block')
    blob = _set_snapshot_states(_replace_entry(blob, pos, EMPTY_BLOCK), pos, True)
    _, body = parse_blob(blob)
    if pos in PATH_B and not any(body[0][22][p][19] == 6 for p in PATH_B):
        blob = set_path_b(blob, False)
    return blob


DEFAULT_IMAGE = os.path.join(os.path.dirname(HERE), 'build', 'HX_Effects_v3.80.0_NAM_Amps_Effects.hxf')


# Controller sources: section 4's list index, and the id inside each entry (presets 24A, 25C made in HX Edit)
SOURCES = {'exp1': 1, 'exp2': 2, **{f'fs{n}': n + 2 for n in range(1, 7)}, 'midi': 9, 'snapshots': 10}
EMPTY_SLOT = [False, 64, None]   # an unused snapshot value slot


def _knob_range(p):
    """A knob's full range as HX Edit writes it in a controller entry (decimals as floats, whole numbers as ints)."""
    return (float(p['min']), float(p['max'])) if p['type'] == 3 else (int(p['min']), int(p['max'])) if p['type'] == 2 \
        else (False, True)


def apply_controls(blob, spec, by_name):
    """Snapshots, controller assignments, footswitches, MIDI bypass and snapshot bypass from spec (see the usage).
    Everything of the base is cleared first (it pointed at its blocks). Layout (presets 24A and 25C):
      section 4 [source] = [entry, ...], newest first; source 1/2 EXP pedals, 3..8 footswitches 1..6, 9 MIDI CC,
        10 snapshots. A knob entry: {0: id, 1: {0: source, 1: CC (4 when not MIDI), 2: min, 3: max, 4: 0,
        5: block position, 6: {28: 0, 29: knob number, 41: False}, 7: 0, 13: False}}. A MIDI bypass entry:
        {0: id, 1: {0: 9, 1: CC, 2: None, 3: None, 4: 2, 5: position, 9: 5, 10: 300, 11: True, 12: 0}}.
      ids are unique in the preset. Every knob entry (any source) has a value slot in every snapshot:
        snapshot 2 [slot] = [False, id, value]; key 10 -> 8 counts them.
      section 3 -> 8 [footswitch] = [entry, ...]: bypass entries (footswitch()) and knob entries (fs_knob()).
      key 10 -> 13 [position] = snapshot bypass (True: snapshots switch the block)."""
    _, body = parse_blob(blob)
    snaps = body[10][10]
    n = len(snaps)
    nslots = len(snaps[0][2])
    blob = replace_node(blob, (4,), [None] * len(body[4]))
    for k in range(n):
        blob = replace_node(blob, (10, 10, k, 2), [list(EMPTY_SLOT) for _ in snaps[k][2]])
    if isinstance(body[10].get(13), list):
        for pos in range(len(body[10][13])):
            blob = set_in_place(blob, (10, 13, pos), True)
    blocks = {int(b['pos']): b for b in spec['blocks']}
    sp = spec.get('snapshots') or {}
    cur = int(sp.get('current', 1)) - 1
    if not 0 <= cur < n:
        raise SystemExit(f'snapshots.current: 1..{n}')
    for k, name in enumerate(sp.get('names', [])[:n]):
        blob = replace_node(blob, (10, 10, k, 4), name.encode('utf-8') + b'\0')
    for pos, states in (sp.get('states') or {}).items():
        pos = int(pos)
        if pos in blocks and blocks[pos].get('snapshot_bypass') is False:
            # snapshots don't switch this block, so it has one state in all of them (HX Edit's 25C); different states
            # per snapshot with snapshot bypass off froze the unit at load (28A, 2026-11-22)
            raise SystemExit(f'snapshots.states[{pos}]: the block has snapshot_bypass false, so snapshots do not switch it')
        if pos not in blocks or len(states) != n:
            raise SystemExit(f'snapshots.states[{pos}]: a block position from blocks, with {n} on/off values')
        for k in range(n):
            blob = set_in_place(blob, (10, 10, k, 3, pos, 1), bool(states[k]))
        blob = set_in_place(blob, (0, 22, pos, 20, 10), bool(states[cur]))

    def knob_of(pos, knob, where):
        if pos not in blocks:
            raise SystemExit(f'{where}: no block at {pos}')
        m = by_name[blocks[pos]['model']]
        names = [p['name'] for p in m['params']]
        if isinstance(knob, str) and knob not in names:
            raise SystemExit(f"{where}: {blocks[pos]['model']} has no knob {knob!r} (knobs: {names})")
        ki = names.index(knob) if isinstance(knob, str) else int(knob)
        return ki, m['params'][ki]

    lists = {}                                   # source -> [entries], in assignment order
    fs = {}                                      # footswitch -> [entries], in assignment order
    next_id = [0]

    def new_id():
        next_id[0] += 1
        return next_id[0] - 1
    for b in spec['blocks']:                     # bypass assignments
        pos = int(b['pos'])
        if b.get('midi_bypass') is not None:
            lists.setdefault(SOURCES['midi'], []).append(
                {0: new_id(), 1: {0: SOURCES['midi'], 1: int(b['midi_bypass']), 2: None, 3: None, 4: 2, 5: pos, 9: 5,
                                  10: 300, 11: True, 12: 0}})
        if b.get('snapshot_bypass') is False and isinstance(body[10].get(13), list):
            blob = set_in_place(blob, (10, 13, pos), False)
        sws = [b['footswitch']] if isinstance(b.get('footswitch'), int) else b.get('footswitch') or []
        if len(sws) > 1:     # HX Edit gives a block one bypass switch; two (FS1 and FS3) froze the unit (25D, 2026-11-22)
            raise SystemExit(f"block {pos}: one footswitch per block (several blocks may share a footswitch)")
        for f_ in sws:
            if not 1 <= int(f_) <= len(body[3][8]):
                raise SystemExit(f'footswitch {f_}: 1..{len(body[3][8])}')
            m = by_name[b['model']]
            fs.setdefault(int(f_), []).append(footswitch(pos, b.get('label') or m['display'] or m['name'])[0])
    knobs = []                                   # (source, pos, ki, p, min, max, cc, per-snapshot values, label)
    for kn in sp.get('knobs', []):
        ki, p = knob_of(int(kn['pos']), kn['knob'], 'snapshots.knobs')
        if len(kn['values']) != n:
            raise SystemExit(f"snapshots.knobs {kn['knob']}: {n} values, one per snapshot")
        rng = _knob_range(p)
        knobs.append(('snapshots', int(kn['pos']), ki, p, rng[0], rng[1], 4, [block_value(p['type'], v) for v in kn['values']], None))
    for c in spec.get('controls', []):
        src = c.get('source')
        if src not in SOURCES or src == 'snapshots':
            raise SystemExit(f"controls: source {src!r} is one of exp1, exp2, fs1..fs6, midi (snapshots go in 'snapshots')")
        ki, p = knob_of(int(c['pos']), c['knob'], 'controls')
        rng = _knob_range(p)
        lo = block_value(p['type'], c['min']) if 'min' in c else rng[0]
        hi = block_value(p['type'], c['max']) if 'max' in c else rng[1]
        if src == 'midi' and c.get('cc') is None:
            raise SystemExit('controls: a midi control needs "cc"')
        knobs.append((src, int(c['pos']), ki, p, lo, hi, int(c['cc']) if src == 'midi' else 4, None, c.get('label')))
    if len(knobs) > nslots:
        raise SystemExit(f'at most {nslots} controlled knobs in a preset')
    for slot, (src, pos, ki, p, lo, hi, cc, vals, label) in enumerate(knobs):
        cid = new_id()
        if vals is None:                         # the knob's value in the block, in every snapshot
            _, cur_body = parse_blob(blob)
            v = cur_body[0][22][pos][20][11][4][ki]
            vals = [v] * n
        else:
            blob = set_in_place(blob, (0, 22, pos, 20, 11, 4, ki), vals[cur])
        for k in range(n):
            blob = replace_node(blob, (10, 10, k, 2, slot), [False, cid, vals[k]])
        lists.setdefault(SOURCES[src], []).append(
            {0: cid, 1: {0: SOURCES[src], 1: cc, 2: lo, 3: hi, 4: 0, 5: pos, 6: {28: 0, 29: ki, 41: False}, 7: 0, 13: False}})
        if src.startswith('fs'):
            fs.setdefault(int(src[2:]), []).append(fs_knob(pos, ki, label or p['name']))
    for source, entries in lists.items():
        blob = replace_node(blob, (4, source), list(reversed(entries)))     # newest first, as HX Edit lists them
    for f_, entries in fs.items():
        # several blocks on one switch: HX Edit numbers the switch's entries in field 10, the first assigned 7, the next
        # 6 (25C, made in HX Edit). With every entry 7 (and field 7 False) the unit froze at load (25D, 27D).
        # Field 10, in assignment order (HX Edit, 2026-11-22): the first entry 7 if it turns a block on/off, 0 if it
        # moves a knob; every later one counts down from 7 (after a knob) or 6 (after an on/off). Two knob entries
        # both left at 0 froze the unit when it was asked for its state, and at start-up.
        c = 7
        for k, e in enumerate(entries):
            if k == 0 and e[11][0] != 1:
                e[10] = 0
            else:
                e[10], c = c, c - 1
        blob = replace_node(blob, (3, 8, f_ - 1), list(reversed(entries)))
    blob = set_in_place(blob, (10, 8), len(knobs))
    return set_in_place(blob, (10, 6), cur)


def build_preset(base, spec, by_name, ir_md5s=None):
    """A preset blob from a base blob (its blocks and footswitches cleared) and a SPEC dict (see the usage).
    ir_md5s: {IR slot: MD5 hex} of the unit's User IRs, for IR blocks (their first knob is the slot)."""
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
        md5 = None
        if m['btype'] == IR_TYPE:
            slot = int((vals or [m['params'][0]['default']])[0])
            md5 = (ir_md5s or {}).get(slot)
            if not md5:
                raise SystemExit(f"{b['model']} at {b['pos']}: User IR slot {slot} is empty on the unit")
        blob = add_block(blob, int(b['pos']), m, vals, b.get('on', True), md5)
    blob = apply_controls(blob, spec, by_name)
    # where the split and merge sit: always set, never taken from the base. 1 and 10 is the usual layout (66 of 91
    # presets on the unit); a base with 0 and 0 (HX Edit wrote one) left the unit's block diagram empty (2026-11-22).
    for key, path, default in (('split', (0, 22, 11, 20, 15, 13), 1), ('merge', (0, 22, 21, 20, 17, 13), 10)):
        blob = set_in_place(blob, path, int(spec.get(key, default)))
    # the split's knobs [Balance A, Balance B] and the merge mixer's [A Level, A Pan, B Level, B Pan, B Polarity, Level]
    for key, path in (('split_values', (0, 22, 11, 20, 15, 7, 4)), ('merge_values', (0, 22, 21, 20, 17, 7, 4))):
        for i, v in enumerate(spec.get(key) or []):
            if v is not None:
                blob = set_in_place(blob, path + (i,), v)
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
        # Two connections, as HX Edit opens them: requests (service 2) and notifications (service 4). Without the
        # notification connection the unit took only about 16 preset writes per power-on (2026-11-22).
        ch = flash.Channel(d)
        notes = flash.Channel(d, 0x1002, 0x03f0)
        flash.Channel.link(ch, notes)
        ch.open()
        try:
            notes.open()
            notes.send(bytes.fromhex('010004000100000004'))
            r = notes.recv(9)
            if r[:2] != b'\0\0':
                raise flash.FlashError(f'unexpected notification service answer {r.hex()}')
            api = Api(ch)
            api.notes = notes
            api.open()
            return fn(api)
        finally:
            notes.close()
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
                irs = {sl: md5 for sl, _, md5 in api.ir_list() if md5} if any(
                    by_name.get(b['model'], {}).get('btype') == IR_TYPE for b in spec['blocks']) else {}
                blob = build_preset(base, spec, by_name, irs)
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
