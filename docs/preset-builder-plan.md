# Preset builder: plan (branch `preset-builder`)

Status 2026-11-21. Pick up from here on any machine.

**Since 2026-11-22** the page reads its models from the person's own firmware file (`fw-reader.js`, see
`tools/preset-builder/README.md`). `extract_hx_data.py`, `firmware_models.py`, `host_params.json` and
`dump_host_params.py` below are gone; the rest of this plan is kept as the history.

## Goal

A simple web page for building **HX Effects** presets, and nothing else: no HX Stomp, no Helix. It's a separate
project, not an HX Edit add-on. It must support everything this repo's firmware builds add: NAM, Click, the
HX Stomp amps and preamps, and the custom effects. **Every knob has to work.**

## Where it is now

All of this is in `tools/preset-builder/` (see its README for details):

- `index.html` is the page. It has nine blocks on one chain, a model browser, parameter editing, and `.hlx` export
  and import. The **Firmware** menu (Stock / NAM / NAM + Amps / Full) picks which models appear. It enforces the
  three-amp limit and shows DSP load.
- `extract_hx_data.py` writes `hx-data.js`, the stock model list read from a local HX Edit install. That file is
  gitignored because it's Line 6 data, so regenerate it on each machine (below).
- `firmware_models.py` reads the custom models and knobs straight from the build scripts (`build_all.py`,
  `build_click.py`, `build_effects.py`, `patch_amp.py`, `amp_list.py`, `preamp_list.py`).
- `host_params.json` lists, for each stock model a custom effect takes over, the parameter slot ids and types
  read from the stock 3.80 firmware. `dump_host_params.py <stock .hxf>` regenerates it and needs numpy.
- `docs/hxedit-preset-format.md` holds the `.hlx` format notes.

Tested in a browser: model counts for each build, export and re-import, the amp limit, switching builds, and no
console errors. Not tested on the unit at all.

### The problem with the current approach

A `.hlx` file has to go through HX Edit. A custom effect is saved under the identity of the stock block it took
over, so HX Edit only passes on the knobs whose slot id and type match a stock parameter. Only NAM Input and Mid,
Click Time and Level, and Geiger Tone get through. The page marks every other knob **unit only**. Amps and preamps
are fine, because HX Edit knows them.

## The plan: send presets to the unit directly over USB

Drop HX Edit from the path. The page writes the preset straight to the unit, addressing each knob by its slot id,
so every knob works. The USB groundwork already exists. `tools/ir_upload.py` and `web/flasher.js` (WebUSB) use
the same channel (HANDOVER, "2026-11-21: User IR slots over USB"):

- Port 0x1001 → 0x03ef. Select service 2 by sending `010002000100000002`.
- Messages are `[u16 1][u16 type][u32 len]` followed by msgpack. Requests are `{102 id, 100 op, 101 args}`;
  answers are `{102, 103 status, 104 result}`.
- **Old-spec msgpack only** (str16/str32, no str8 or bin).
- Known ops: 13 IR list, 9 IR import, 10 rename, 12 info, 11 samples, 15 delete, 255/254 edit brackets.

**The preset ops are captured and decoded (2026-11-21)**: list, read, load, set a knob live, block on/off, save,
write to a slot, rename. See `docs/hxedit-preset-format.md`, "On the wire". Steps 1 and 2 below are done; next is
step 3. A preset blob is msgpack with each block's **model id** and its **knob values by position**, so custom
models' knobs can all be written directly.

### Step 1: capture HX Edit handling presets (needs the unit)

HX Edit is used only once here, to see what it sends. Close HX Edit and Line 6 Updater first, and connect the unit.

```bash
cp -R "/Applications/Line6/HX Edit.app" ~/HXEditLog.app && codesign -f -s - --deep ~/HXEditLog.app
```

```bash
HX_EDIT=~/HXEditLog.app tools/usb/capture_hxedit.sh
```

In HX Edit, doing one thing at a time:

1. Let it connect and load the preset list.
2. Click a different preset to load it.
3. Move one knob on one block. Note the block, knob and value.
4. Turn one block off and on.
5. Save the preset to a spare slot. Note the slot.
6. Import any `.hlx` into another spare slot. Note the slot.
7. Rename a preset.
8. Quit.

The log goes to `usblog/<time>-hxedit.txt`, which isn't committed. Write down what you did and when, so each action
can be matched to its messages. Back up your presets in HX Edit before step 5.

### Step 2: decode

- `tools/usb/decode.py` splits the transport messages but doesn't decode the service-2 msgpack. Add that, using
  the same rules as `ir_upload.py`.
- Find the ops for: preset list, read preset, write preset, load preset, set parameter, and bypass. Record what
  each takes and returns, especially how blocks and parameters are numbered. The expectation is model ids and
  slot ids as in the firmware's Entry 3, matching `host_params.json`. Confirm it.
- Write the findings into HANDOVER (a new dated section) and `docs/hxedit-preset-format.md`.

### Step 3: a Python tool first (started 2026-11-21: `tools/preset_send.py`)

Done and tested on the unit: `list`, `current`, `read` (blob + readable JSON), `write` (read back identical; a
one-knob change written to 22D, read back, then the original restored), `rename`, `load`, `knob` (live), `bypass`
(live). Findings: the unit answers a type-6 request as type 2 when the client hasn't done HX Edit's start-up
requests, so match answers by id only (one id counter); write, rename and load answer "working" (1) and their
"done" never comes without a subscription, so check by reading back. HX Edit writes some ints with a fixed size
(0 as int16 `d1 0000`), so re-encoding a whole blob isn't byte-identical: `set_in_place()` changes one value
keeping its type. **Building presets works (2026-11-21):** `preset_send.py build SLOT spec.json` clears a base preset's blocks and
footswitches, adds blocks by firmware model name with knob values by position or name, assigns footswitches, writes
and reads back. Tested on the unit: 23A/23B "API Test" with NAM A2 Lite (Model 5, Input 0.6 …) and Bam Crusher
(all eight knobs, most of them "unit only" before), on FS1/FS2: knobs and footswitches right (user). `models` lists
what an image offers. Details: `docs/hxedit-preset-format.md`, "Building presets".

**Amps, IR blocks, the lower path and snapshots work too (2026-11-22):** `build` specs take amps (any of the 223),
IR blocks (the slot's MD5 is looked up on the unit), positions 12..20 on the lower path, "split"/"merge", and
"snapshots" (names, current, per-block on/off, per-snapshot knob values). 24B "Builder Test" on the unit (user: looks
ok). Lesson: always write the split/merge places (see the format notes).

**Controllers (2026-11-22):** footswitches (several blocks per switch), footswitch → knob, EXP pedals 1/2 → knob,
MIDI CC → knob, MIDI bypass, snapshot bypass. Two encodings froze the unit (shared switch with equal field 10 and
field 7 False; snapshot bypass off with per-snapshot states); both are fixed and 29A "Controls Test 2" works (user:
switches and snapshots; no EXP pedal or MIDI controller to try those). See the format notes.

**Step 4 so far:** `preset-core.js` (the builder in JavaScript) builds the same bytes as preset_send.py
(`check_core.py`: hundreds of random presets on real bases); `extract_fw_tables.py` writes fw-models.js (git-ignored)
with each build's model table.

**The page sends and reads (2026-11-22, tested by the user in Chrome):** Send to unit / Read from unit, a footswitch per
block; web/flasher.js has the preset requests (list, read, write, load, current). 654 model choices map to the
firmware (knob names matched loosely: HX Edit and the firmware spell some differently; custom effects by position);
every model round-trips page -> preset -> page in the browser. Next: page controls for the lower path, snapshots and
knob controllers (the builder already has them), and capturing preset delete.

Original plan for this step:

Write `tools/preset_send.py`, in the style of `ir_upload.py`. It should list presets, read one into JSON, write one
from the builder's JSON to a slot, and set one parameter live. Test it on the unit:

- Read a stock preset, write it back unchanged, and check it's identical.
- Then write a preset with NAM plus a custom effect, setting knobs that are currently "unit only".
- Check on the unit that the knobs took.

### Step 4: in the page

- Add a WebUSB "Connect" and "Send to slot …" (and "Read from unit") to `index.html`, using the code from
  `web/flasher.js`. This needs Chrome or Edge.
- Store custom blocks natively: their own knobs by slot id, with no host mapping. Remove the **unit only** badges
  and the `hostParamFor` mapping once sending works.
- Keep `.hlx` export as a backup format, or drop it. Decide once sending works.

### Step 5: tidy up

- Update the README and HANDOVER.
- Decide whether the builder belongs on the hosted setup page (`web/`, gh-pages) or stays a local tool.

## Safety rules

- **Only send ops seen in a capture.** A wrong request can kill the unit's USB channel until a power cycle with
  USB unplugged. Op 11/12 on an empty IR slot is the known case.
- Never ask op 11/12 for an empty IR slot.
- Never use the unit while HX Edit or Line 6 Updater is open.
- Back up presets before writing any. Write to spare slots first.
- Never commit Line 6 files: firmware, `.hxf`, `hx-data.js`, or captures that contain preset dumps.

## Open questions

- Are block positions 0–8 right for HX Effects' nine blocks? This is assumed, not confirmed.
- Does the unit check a preset's DSP load and amp count, or does it accept too much and then glitch?
- Does writing a preset need the 255/254 edit brackets, like the IR ops?

## Setting up on another machine

```bash
git fetch && git checkout preset-builder
```

```bash
python3 tools/preset-builder/extract_hx_data.py "/Applications/Line6/HX Edit.app"
```

```bash
python3 -m http.server 8766 --bind 127.0.0.1 -d tools/preset-builder
```

Then open <http://127.0.0.1:8766/>. The extractor needs HX Edit installed, using macOS paths. On Windows, pass the
install folder and check the paths in `extract_hx_data.py`. numpy is only needed for `dump_host_params.py`, and
`uv run --with numpy` works for that.
