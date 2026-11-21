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
