# HX Effects preset builder

A page for building HX Effects presets and sending them straight to the unit over USB: pick blocks, set their knobs,
route two paths, set up snapshots, footswitches and controllers. HX Effects only.

## Where the models come from

The page reads every model, knob, range and setting name from **Line 6's firmware file for the HX Effects**
(`HX_Effects_v3.80.0_0xd97239907.hxf`, the same file the setup page asks for). The first time, it asks for the file;
it reads it in the browser (nothing is uploaded), works out this repo's three builds from it with the setup page's
recipes, and keeps the result in the browser (IndexedDB), so the file is needed once. No Line 6 data is in this
repository or on the website. **read it again** (bottom of the model list) forgets it.

`fw-reader.js` reads the firmware's model tables: each model's preset id, block type, DSP cost, category and name,
and each knob's name, range, default, display type and choice names. It is a JavaScript port of
`tools/preset_send.py model_table()` and gives the same tables (`extract_fw_tables.py` writes them from the images
in `build/` for the tests, `fw-models.js`, git-ignored).

The **Firmware** menu picks which of this repo's builds is on the unit (`build.py`), and the model list follows it:

| Firmware | Adds |
|---|---|
| Stock 3.80 | nothing: HX Effects' own models |
| NAM build | NAM A2 Lite (on mono Regal Bass DI) and Click (on mono Mod/Chorus Echo) |
| NAM + Amps build | the HX Stomp's 111 amps (Amp) and 112 preamps (Preamp), at most three per preset |
| Full build | the effects a plain `build_all.py` makes (Bolt, Rocket!, Garrrry Tank, Quality Polis, Bam Crusher, ...) |

Models added by a build are marked ★. DSP load is the firmware's own cost for each model (100 = 1%); the page
refuses a block that would take the preset over 100%, or a fourth amp/preamp.

## Running it locally

```bash
python3 -m http.server 8767 --bind 127.0.0.1                    # from the repo root: the page loads ../../web/*
```

Then open <http://127.0.0.1:8767/tools/preset-builder/> in Chrome or Edge. On the website the page sits in
`preset-builder/`, beside the setup page's `flasher.js`, `firmware-core.js` and recipes.

## Sending to the unit

**Send to unit** writes the preset straight into a slot over USB (WebUSB: Chrome or Edge, HX Edit and Line 6 Updater
closed), the way `tools/preset_send.py build` does, with `preset-core.js` (the same bytes: `check_core.py`). Every knob
reaches the unit, custom effects' own knobs included; it reads the slot back to check it (the unit now and then stores a
write with its start scrambled: the page writes again, and never loads a copy that differs), and can load it. **Read from unit**
loads a preset from the unit into the page. Everything below travels both ways:
- **Two paths**: path A and path B (the lower path), nine blocks each; drag blocks between them. Split and Merge set
  where path B leaves and rejoins path A: drag the two points on the diagram (or use the dropdowns). Click a point
  for its settings: the split's Balance A/B, and the merge's A/B Level and Pan, B Polarity and output Level.
- **Snapshots**: the four snapshot buttons above the chain pick the one you're editing (and the one the unit opens
  on); rename it in the box next to them. A block's On/Bypassed is per snapshot. Turn **Snapshot bypass** off on a
  block to keep it the same in every snapshot.
- **Footswitch** and **MIDI bypass CC** per block (several blocks may share a footswitch).
- **Knob controllers**: under each knob, Fixed, Snapshots (a value per snapshot: set it with the knob in each
  snapshot), EXP 1/2, FS1–6 (switches between Min and Max) or MIDI CC (with Min and Max).
- **IR blocks** list the IRs on the unit by name (read over USB).

**Save / Open** keep all of the above in a `.json` file. **Export .hlx** writes an HX Edit preset file (blocks, both
paths, split and merge settings, snapshot names; not snapshot states or controllers), and **Open** also takes an
`.hlx`. The .hlx frame is written by the page; blocks carry the firmware's model and knob names, which are HX Edit's.
A custom effect goes into an .hlx as the stock block it took over (mono), with its own knob values.
