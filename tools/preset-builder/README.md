# HX Effects preset builder

A small offline page for building HX Effects `.hlx` presets: pick blocks, edit parameters, export a file
that HX Edit can import. HX Effects only (device 2162693, HX Edit's `default_preset_hfx.hlx` template).

The **Firmware** menu picks which of this repo's builds is on the unit (`build.py`), and the model list follows it:

| Firmware | Adds |
|---|---|
| Stock 3.80 | nothing: HX Effects' own models |
| NAM build | NAM A2 Lite (on mono Regal Bass DI) and Click (on mono Mod/Chorus Echo) |
| NAM + Amps build | the HX Stomp's 111 amps (Amp) and 112 preamps (Preamp), at most three per preset |
| Full build | the effects a plain `build_all.py` makes (Bolt, Rocket!, Garrrry Tank, Quality Polis, Bam Crusher, ...) |

Models added by a build are marked ★. The model data comes from your own HX Edit install and is never committed
(Line 6 data); the firmware models are read from the build scripts (`firmware_models.py`), so the list follows them:

```bash
.venv/bin/python tools/preset-builder/extract_hx_data.py      # hx-data.js: HX Edit's model list (gitignored)
.venv/bin/python tools/preset-builder/extract_fw_tables.py    # fw-models.js: each build's firmware model table (gitignored)
python3 -m http.server 8767 --bind 127.0.0.1                    # from the repo root: the page loads ../../web/flasher.js
```

Then open <http://127.0.0.1:8767/tools/preset-builder/> in Chrome or Edge. Re-run the extractors after updating HX
Edit or changing the builds (fw-models.js needs the built images in build/ and Line 6's file in firmware/).

## Sending to the unit

**Send to unit** writes the preset straight into a slot over USB (WebUSB: Chrome or Edge, HX Edit and Line 6 Updater
closed), the way `tools/preset_send.py build` does, with `preset-core.js` (the same bytes: `check_core.py`). Every knob
reaches the unit, custom effects' own knobs included; it reads the slot back to check it, and can load it. The
preset's snapshot names and settings come from the slot it replaces (an empty slot uses 1A's). **Read from unit**
loads a preset from the unit into the page (main path; lower-path blocks are not shown yet). Each block can have a
bypass footswitch (several blocks may share one). Models HX Edit 3.82 knows but the unit's 3.80 firmware doesn't
(Transient Shaper, Shuffling/Euclidean Delay, ...) can't be sent.

## How the custom effects travel

Each custom effect keeps the identity of the stock block it took over (mono only), and HX Edit only knows that stock
block. So the `.hlx` stores the host: `@model` is the host, `@stereo` false, and the host's parameters. A knob reaches
the unit only where the host has a parameter with the same slot id and type (and a range that holds the knob's),
which the unit uses to address parameters; the page marks every other knob **unit only**: it starts at the
unit's default and is set on the unit. On import, a mono host block in a build that takes it over comes back as
the custom effect. The slot ids come from the stock firmware, in `host_params.json`; regenerate it after adding an
effect on a new host (`dump_host_params.py <stock .hxf>`, needs numpy).

Amps and preamps keep their own HX Stomp identities, which HX Edit knows. HX Edit can't edit NAM, the amps or the
effects once they are on the unit (README: "code −8200").

The rest of this section is about the .hlx route; Send to unit doesn't need it.

Limits: one chain of nine blocks on path A of `dsp0` (path B blocks are skipped on import), no snapshots or
controller assignments, no cabs. Importing a preset from another device keeps the blocks the chosen build has and
skips the rest. DSP load for the firmware models is their build cost scaled as HX Edit's amp figures are
(1000 cost = 10%).
