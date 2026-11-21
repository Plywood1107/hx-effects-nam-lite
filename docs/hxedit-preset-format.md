# HX Edit 3.82 – reverse engineering notes

Target: `/Applications/Line6/HX Edit.app` (com.line6.hxedit, 3.8.2), universal Mach-O (arm64 + x86_64), 95 MB.
Binary SHA-256 (arm64 slice per REA): `92d22d28d89936795108ca9a20f73de2364d00f3eaf06953fbd0d7562eccb119`
Symbols are NOT stripped – full mangled C++ names available (43,985 procedures, 7,946 strings).

## Tooling
- REA `rea-agents@4.0.1`, run locally with Hopper as the backend.
- REA expects Hopper in `/Applications`; it's in `~/Applications`, so set:
  `export HOPPER_LAUNCHER_PATH="$HOME/Applications/Hopper Disassembler.app/Contents/MacOS/hopper"`
- Ghidra backend not configured (needs `GHIDRA_INSTALL_DIR` + Java).

## Transport: USB bulk via bundled libusb
- `Contents/MacOS/libusb-1.0.0.dylib` bundled; app also links IOKit.
- `L6HelixDevice::connectWithObjHelperLibUsb` @ 0x10003fd70
  - libusb_init → get_device_list → match device descriptor → get_config_descriptor
  - Picks endpoints by walking the descriptor: bulk = `bmAttributes & 3 == 2`, direction from bit 0x80
  - libusb_open → libusb_claim_interface
  - `L6HelixDevice::GetBulkMtuFromDriver()` → MTU
  - Creates `L6UsbBulkMsgChannel(router, handle, device, ...)`, `initialize(…, 0x3ff)`
  - Registers with a message router: `_McBspMessaging_GetRouter`, `_MsgRouter_AddChannel`,
    `_MsgRouter_AddRoutingEntry(router, addr << 8, 0xff, 1, …)` → logical addressing on top of USB
  - Creates up to three `L6HelixMsgPort` instances (separate logical ports)
- `L6UsbBulkMsgChannel_OSX::Open` @ 0x1004f38f4: starts a periodic timer, waits for channel state 3, issues a device→host read.
- `L6UsbBulkMsgChannel_OSX::HandleQueueOutPkt` @ 0x1004f3ce0 (host→device send):
  - Copies message segments into a buffer
  - **Pads length up to a multiple of 4 bytes**
  - libusb transfer type 2 (bulk), **timeout 0x1388 = 5000 ms**

Other entry points worth decompiling:
- 0x1004f3fa4 `HandleDeviceToHostCompletion` (receive path / framing)
- 0x1004f40a4 `HandleInPacketDone`
- 0x10061ed80 `L6LibUsbControlEndpointItf::ControlRequest` (control-endpoint mode)
- `L6HelixMsgPort` methods, `McBspMessaging` / `MsgRouter` / `MsgPacket` (message format)
- `FindDfuDescriptor` / `ProbeDfuConfiguration` = firmware update (DFU) path – avoid poking at this on real hardware.

## Message layer (from objdump, no Hopper) – partial, parked
Each USB bulk packet = 8-byte transport header + payload, padded to a multiple of 4.
`MsgTransportHeader_Pack` @ 0x10083a8c0 (two little-endian u32 words):
- word0 bits 28–31: header type (1 or 2, see below)
- word0 bits 26–27: always 2 (set in `MsgPort_PrepareTransportHeader`; likely a version)
- word0 bits 0–15: length of what follows the 8-byte header
- word1 low u16: source address (port +0x28 = node byte << 8 | port byte; ports 0x80–0xEE dynamically allocated)
- word1 high u16: destination address (port +0x2a, set by `MsgPort_SetRemote`)
Uses:
- Datagram send (`MsgPort_Datagram_Send`): type 1, length = payload length, no sub-header
- Stream send (`SendNextPacketTask`): an extra stream sub-header follows. Type 1 + 8-byte sub-header,
  or type 2 + 12-byte sub-header. The sub-header holds a sequence byte (<<8), a flags byte (<<24) and a 32-bit value
  that's probably an ack/window. Not decoded further.
- Payloads appear to be msgpack (msgpack-c is linked).
Not needed for an offline preset builder.

## Preset building (no USB needed)
`.hlx` = JSON: `{version:6, schema:"L6Preset", data:{meta, device, device_version, tone:{dsp0, dsp1, global, snapshot0..7}}}`.
Each dspN has split/join/inputA/B/outputA/B; blocks are added alongside with `@model`, `@position`, `@enabled` + params.
- `*.models` (amp, cab, delay, …): full model definitions – symbolicID, display name, category, DSP `load`,
  default cab links, and per-param `min`/`max`/`default`/`displayType`
- `HelixControls.json`: per-parameter display formatting/units/step

Block entries (`dspN.blockK`, K = order): `@model`, `@position` (0–7), `@path` (0 = A), `@type`, `@enabled`,
`@no_snapshot_bypass`, then every param from the model by symbolicID (including `@stereo`, `@trails`, `@mic`, `@bypassvolume`).
`@type` comes from `BlockTypeFromCategory(eCategory, b1, b2)` @ 0x1001fc12c (read with objdump):
- amp (cat 1): 1, or 3 when it has a linked cab (`@cab: "cabN"` → `dspN.cabN`)
- preamp (13): 1
- cab (2, 19): 2, or 4 for dual cab
- IR (16): 5 · looper (15): 6
- everything else: 0, or 7 when b1 is set. b1 is true exactly for models with a `@trails` param (delays, reverbs, some send/returns)
HX Effects (`default_preset_hfx.hlx`): one DSP, so everything is in `dsp0` (`dsp1` stays `{}`), global
`@topology0: "A"`, inputs/outputs are `HelixFx_AppDSPFlowInput`/`Output`; the unit's limit is nine blocks
(see `docs/amps-findings.md`), so the builder uses positions 0–8.
Device IDs: 2162689 Helix Floor (template), 2162693 HX Effects (template), 2162694 HX Stomp (template).
Inferred from model `devices` lists, not confirmed: 2162690 Rack, 2162692 LT, 2162699 Stomp XL, 2162944/2162945 Native.

## Data files (Contents/Resources) – plain text
- `HX_ModelCatalog.json` – categories → models (id, name, image)
- `Helix.sym` – JSON: model symbol (e.g. `HD2_AmpCali400Ch1`) → ordered parameter names
- `default_preset*.hlx`, `empty_preset.hlx` – JSON preset templates
- `*.models`, `HelixControls.json`, UI layout `.xml` files
- Binary: `HelixModelDefs.bin`, `HX_ModelCatalog.bin`

## On the wire: presets over USB (capture 2026-11-21, `usblog/20261121-224242-hxedit.txt`)

Same channel and rules as the IR ops (HANDOVER, "User IR slots over USB": port 0x1001 → 0x03ef, service 2,
`[u16 1][u16 type][u32 n]` + **old-spec msgpack**). Type 2 = requests; **type 6 = "live" requests** (their own id
counter, from 1000); type 4 = notifications {105: kind, 106: data}. What the user did, and what HX Edit sent:

| Action | Request | Answer |
|---|---|---|
| preset list | t2 op 1 {107: setlist 0, 101: 2} | [{index: {109 name, 123, 124, 125}}] |
| read a preset (backup) | t2 op 4 {107: 0, 108: index, 101: 2} | the preset blob (~3.4 KB) |
| current preset | t6 op 23 | {107, 108, 109 name, 117, 83, 92} |
| current preset's blob | t6 op 22 | the blob |
| load preset (1C clicked) | t6 op 20 {107: 0, 108: 2} | 1 then done; notifications |
| move a knob (Elephant Man Level → −10.1 dB) | t6 op 30 {98: 6, 29: True, 26: 0, 28: 5, 119: −10.1} | echo; one per step of the drag |
| block off / on | t6 op 41 {98: 6, 59: False / True} | 0 |
| save current to its slot (1C) | t6 op 71 {107: 0, 108: 2, 109: 'Warbler'} | 0; notification 5 gives a new id (116) |
| import an .hlx to 22D | t2 255; t2 op 8 {107: 0, 108: 87, 109: name, 123: F, 124: F, 125: 0, 110: blob}; t2 254 | 1 then done |
| rename (22D) | t2 op 6 {107: 0, 108: 87, 109: 'my new preset'} | 1 then done |

Preset index = (bank − 1) × 4 + (A 0, B 1, C 2, D 3): 1C = 2, 22D = 87. Block numbers (98) look like the blob's
block list position (Elephant Man was 98: 6 and the 7th entry); knob numbers (28) are positions in the model's
parameter list (Level is Elephant Man's 6th).

**The blob** (what op 4 returns and op 8 takes; HX Edit made it from the `.hlx` itself): `"l6-helix\0"` (msgpack
fixstr), a 48-byte raw string (12 LE u32 section offsets), then one msgpack map:
- 0: {21: 0, 22: [blocks]}: each block {19: kind (6 = effect, 8 = empty, 0 = input, 1 = output, 2 = split/merge?),
  20: {9: ?, 10: **on**, 11: {2: n, 3: m, 4: [**knob values, in the model's parameter order**]}, 12: {…},
  24: {23: False, 25: **model id**, 26: −1}}}. Model ids are the firmware's (Entry 3), e.g. 431, 420, 476.
- 3: {8: [footswitch assignments, with block names and colours]}; 5: global/preset settings (tempo 16: 160.7…);
  7: {35, 36: 'F15', 37: build id}; 10: snapshots (4: name, 5: tempo, per-block on/off and knob values).

So a preset addresses knobs **by position**, not by HX Edit's names. That is the point for the builder: our custom
models' own knobs are just positions in their Entry 3 parameter lists, so a blob written straight to the unit can
set every one of them; no `.hlx` and no HX Edit in the way.

Not captured yet: saving to a *different* slot (save-as), deleting a preset, snapshots, IR/amp blocks in a blob.

### Building presets (2026-11-21, `tools/preset_send.py build`, tested on the unit)

Worked out from all 91 presets on the unit (read with op 4; not committed: they're the user's):
- **A block** is `{19: 6, 20: {24: {23: False, 25: preset id, 26: -1}, 9: block type, 10: on, 11: {2: n, 3: m,
  4: [values]}, 12: {2: 0, 3: 0, 4: []}}`. Plain msgpack (old spec, float32) reproduces all 460 blocks byte for byte.
  An empty position is `{19: 8, 20: None}`.
- **preset id** = Entry 0 Table 1's id for the model's name index (e.g. NAM's host Regal Bass DI Mono = 799);
  **block type** = the model's browser item byte 0 (1 most effects, 8 delays/reverbs, 17 amps, 19 IR, 23 synths,
  24 Ratchet-style); **values** = the model's Entry 3 parameters in order, typed 1 bool / 2 int / 3 float. In a
  built image a custom effect's host model carries the custom effect's own parameters, so they are its knobs.
- Block types 8, 9, 13 end their values with a Trails switch: the model's own last parameter when it is DryThru/
  Trails, else one more bool. There, m = n − 1; elsewhere m = n.
- **The 12-word table** after "l6-helix" holds section positions (ends of the top-level values and the map start); on
  a change of size, every entry after the change moves by the same amount.
- **Snapshots** (key 10 → 10 → [snapshot] → 3 → [position] → [None, on]) keep each position's on/off; a new block
  gets its state in every snapshot.
- **Footswitches** (key 3 → 8 → [switch 0..5]) are `[{10: 7, 11: {0: 1, 5: label, 6: LED colour, 7: False,
  8: block position}, 12: False, 14: '', 13: False, 16: 0, 15: False}]` as the unit writes them, or None. A preset
  imported from .hlx carried `10: 0` entries with an extra key that the unit did not honour on a rebuilt preset.
- Not covered yet: IR and cab blocks (more fields; a hash key 27), amps, path B, snapshot-specific knob values,
  controller (expression) assignments.
