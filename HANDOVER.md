# Handover: NAM A2 Lite on the Line 6 HX Effects

Working state as of 2026‑11‑17 (first written 2026‑11‑01). `python3 build.py nam|amps|full` builds, verifies
and prints the MD5 of one of three images, each with NAM on the mono Regal Bass DI and Click on the mono
Mod/Chorus Echo:

| Mode | Contents | Pipeline | Output | MD5 |
|---|---|---|---|---|
| `nam` | NAM + Click | `build_nam_click.py --nam-host regal` | `build/HX_Effects_v3.80.0_NAM.hxf` | `24b00640…` |
| `amps` | + Line 6's 111 HX Stomp amps (Distortion → Amps) and 112 preamps (EQ → Preamps) | the above, then `build_amps.py --set all --preamps all --base-file …` | `…_NAM_Amps.hxf` | `0dcbad07…` |
| `full` | + Geiger, Commander, Corrupt, Ottobit, Doom Chug | `build_all.py`, then `build_amps.py` | `…_NAM_Amps_Effects.hxf` | `a27dfeda…` |

All three were played on the unit on 2026‑11‑17 (amps and full first without preamps, `e2162bca…` / `edd48969…`,
kept as the recovery position below; then full + preamps, `a27dfeda…`, which is what's on the unit now; the
`amps` + preamps image `0dcbad07…` is verified but was not flashed). The MD5s above are for build.py's output,
whose last step was run directly with `build_amps.py` on the existing bases; a full `build.py` run with preamps
has not been done. The amp images carry the
USB memory window (`tools/memwin.py`) for reading the unit's log. The README (rewritten 2026‑11‑17 in
0e59a43, then edited by the user on GitHub in ede738a: their own intro and voice, keep it) covers only these three builds and the install; everything else lives here and in `docs/`. The older
builders (`build_effects.py` NAM in the IR category, `build_click.py`, `build_all.py --with …`) still work and
are described below. A USB flasher installs any image without Line 6 Updater.
This note is for picking the project up in Claude Code (or anywhere) without re‑deriving anything;
the dated sections further down record how things were found.

**Recovery position (2026‑11‑17).** Git tag `three-builds-2026-11-17` (moved to commit 0585afb, with the preamps)
is the code for the current builds: nam `24b00640…`, amps `0dcbad07…` (verified, not flashed), full `a27dfeda…`
(on the unit). The earlier no-preamps images (amps `e2162bca…`, full `edd48969…`) come from commit 128daa7. A clean
`build.py` rebuild from either was not run: the images were made step by step with the same code. Copies of the three images
and the stock firmware, with `MD5SUMS` and a `README.txt` (flash and rebuild steps), are in
`~/hx-effects-images/2026-11-17/`, outside the repo (Line 6 derivatives: never commit or share). To get back: flash
the wanted copy (`echo flash | .venv/bin/python tools/flash.py flash ~/hx-effects-images/2026-11-17/<file>`), or
`git checkout three-builds-2026-11-17` (or 128daa7 for the no-preamps images) and `python build.py nam|amps|full`. Unit won't boot: hold > at power-on,
Line 6 Updater, the stock file. Back up presets and IRs in HX Edit before any new image.

## What exists

- **Repo:** `/Users/scott/hx-effects-nam-lite` → <https://github.com/scottlynn73/hx-effects-nam-lite>
  (standalone, GPL‑3.0, no Line 6 files tracked; `.gitignore` excludes `firmware/`, `build/`, `*.hxf`,
  `*.l6ia`, `.venv/`, `.DS_Store`, `usblog/`). Everything is on `main`, SSH remote, up to date with GitHub
  on 2026‑11‑17 (ede738a); the local branch `amps` is merged and can be deleted. Pushing from Claude's shell sometimes fails:
  then push from your own terminal.
- **Amps development repo:** `~/hx-effects-stomp` (local git only, no remote): where the amps were worked out
  test by test, with the plan, findings and logs (`docs/plan.md`, `docs/findings.md`). Its tools were copied here
  unchanged; `docs/amps-findings.md` is its findings file.
- **Upstream + scratch work:** `~/hx-stomp-nam-lite` (clone of
  <https://github.com/nocaseguy/hx-stomp-nam-lite> with all the edits applied by `apply_effects*.py`,
  plus the bisection scripts, `*_parts/` entry dumps, `stomp_e2.txt`/`effects_e2.txt`, `*_ddr.txt`).
  Not needed to build; useful if the offsets ever have to be re‑mapped.
- **build.py:** the three modes above (table). NAM's host is chosen by `nam_host.py`, shared by build_all.py and
  build_nam_click.py (`--nam-host`, which writes a manifest for verify_nam_click.py). `--quick` reuses a base image
  already built; `-- …` passes options to the base builder. Venv needs `numpy unicorn==2.1.4 capstone==5.0.9 pyusb
  libusb-package` (unicorn/capstone for verify_amps.py's emulation checks).
- **Base images by hand:** `cd /Users/scott/hx-effects-nam-lite && source .venv/bin/activate`, then
  `python3 build_all.py` (all‑in‑one without amps, MD5 `7b291b5f27ad8bb7c121c15528dbc5d2`; check
  it with `python3 tools/verify/verify_all.py`) or `python3 build_effects.py` (NAM only, MD5
  `aaa5186b41f8db6f7a05487355706bb1` since the 2300 cost; verify_all compares against it, so rebuild it
  after any change to NAM). Both read `firmware/HX_Effects_v3.80.0_0xd97239907.hxf` (MD5
  `7c2ebdf1bffb6bcc5f89dda97f91e40c`) and refuse anything else.
- **Flash:** HX Edit and Line 6 Updater closed, then
  `echo flash | .venv/bin/python tools/flash.py flash build/<image>.hxf` (~2 min, ends `BOOTED` /
  `BOOT FAILED`, exit 0/1). `flash.py info` is read‑only. Needs `pip install pyusb libusb-package` in
  the venv; always the `.venv` Python (system Python has no numpy). Line 6 Updater → Choose File
  still works too. `BOOTED` only means the main app answers on USB: a frozen UI passed it once, so
  after any new kind of change check the screen and footswitches as well.
- **Result on the unit (NAM‑only image):** block under **IR → Single → "NAM A2 Lite"** (takes over the
  1024‑sample IR block's identity; the 2048 IR block is intact, but the unit won't put it in a preset
  beside NAM). In the all‑in‑one image NAM is under Distortion → Mono instead (see below). The standalone build was flashed and booted on
  2026‑11‑03, with both Line 6 Updater and `flash.py`. Knobs: Model (User IR slot), Input, Bass, Mid,
  Treble, Presence, Ch Vol, Polarity. Strip title "NAM / IR_2048". Two NAM blocks + a few effects
  fit in one preset (declared DSP cost 2300 since 2026‑11‑10, was 2700). Sounds right (confirmed by ear after the EQ fixes below).
- **Recovery:** hold the **>** (right arrow) button while powering on → fail‑safe update mode → Updater
  → Choose File → stock `.hxf`. Verified against Line 6's reset‑procedures KB page.

## The port, in one screen

All device logic lives in the copied upstream tools, keyed off Entry 0's code segment load address
(`0x28000000` = HX Effects, via `select_device()` in `tools/patch_amp.py`; `NAM_DEVICE=effects` env for
the kernel):

| Piece | HX Stomp (upstream) | HX Effects (ours) |
|---|---|---|
| Entry 2: Blob 0 buffer size word | split across `w[37192..37193]`, `0x77aac` | whole word `w[37370]`, `0x76a2c` → `0x78000` |
| Entry 2: Heap 6 (start, end, clear) | `w[41966, 41971, 41975]`, `0x293eac..0x2ab243` | `w[42147, 42152, 42156]`, `0x292e2c..0x2a8df6` (end exclusive) → moved to `0x30d100..0x3230ca` |
| Primitive table @ `0x200000` | 282 records | 281 (no `0x2aab`); resolved by ID at build time; `0x9c75` @ `0x200588` |
| Hook record template | hardcoded fn addrs | copied from primitive `0x822`'s record (fns shifted −0x39) |
| Kernel PM home | `0xc4ef8` (Block 2 tail) | same (Block 2 layout identical) |
| Kernel IR store | `IR_FLAG 0x2ab56e`, `IR_TOP 0x2abded` | `0x2a912c`, `0x2a99ab` |
| Kernel working memory | host‑allocated SDRAM via instance struct (`--sdram-words 0x5000`) | **fixed DDR2** `0x294400 + 0x5000 × P_SLOT` (region freed by the Heap 6 move); `--sdram-words 0`; asm swap in `nam_multi.py::_kernel_src()` |
| Host graph | Clarity amp composite `0x6001a9` (3 members) | **IR block** composite `0x6000e9` (8 members), member 1 (`0x271c` convolution) → `0x9c75` |
| Other members' inits | n/a | copied from the IR blob, with overrides: member 3 pid 2 = 19.9 (low cut off), member 4 pid 2 = 20100 (high cut off), member 5 pid 1 = −120 dB (dry off), pid 2 = 0 dB (wet) |
| Entry 3 | new model appended | new model appended, then its descriptor fields (0,1,6,7,10,11,13) copied over `HD2_ImpulseResponse1024Mono`'s |
| Entry 0 | tables relocated, new rows, new folder | **nothing relocated**: 1024 IR's Table 1 cost, Table 2 counts/short name, browser item name, and the "Impulse Response" title string, all in place |

Entry 0 map (HX Effects 3.80.0, segment at `0x28000000`): Table 1 (12‑byte rows) `0x28101084` ×465,
base ptrs at `0x28100b1c/b58/b70/c64/df0`, the two "end" ptrs `0x28100b54/b80` also point at a 7‑entry
harness table at `0x28102650`; count getter `movw #465` at `0x28100b5c` (the other four `movw #465` are
`sq.c` line numbers, not counts). Table 2 (44‑byte rows, sorted by name idx) `0x280bd8fc` ×777, ptr
`0x280bd8f8`, counts `movw #777` at `0x2807b2be/0x280bd85c/0x280ed796`. Browser lists: ptrs `0x281001fc`
(we used `0x2810021c` = Distortion onward), counts `+0xf0`, 13 categories × 4, IR = cat 9 (our index),
subfolder counts `0x281003dc`/`0x281003e4`, names `0x28100074`/`0x281004e8`. `btype` per item is a block‑type enum
(IR = 0x13/0x14/0x15), not a category.

## The all‑in‑one image now (2026‑11‑11)

`python3 build_all.py` with no options:

| Block | Browser | Replaces | Kernel | On the unit |
|---|---|---|---|---|
| NAM A2 Lite | Distortion → Mono | mono Regal Bass DI | Block 2 tail + Block 3, 2 slots, primitive 0x9c75 | works; Model = User IR slots 1..21 |
| Click | Delay → Mono | mono Mod/Chorus Echo | Block 3 top, 0x0128 | works |
| Geiger | Distortion → Mono | mono Megaphone | Block 3, 0x012e, curves in Blob 0 | works |
| Commander | Distortion → Mono | mono Xenomorph Fuzz | Block 3, shared kernel with Corrupt, 0x0100 | works |
| Corrupt | Distortion → Legacy | Octave Fuzz | (shared), 0x0838 | works |
| Ottobit | Distortion → Mono | mono Bitcrusher | overlay, stub on 0x2392, rings in DDR2 | works |
| Doom Chug | Distortion → Mono | mono Pocket Fuzz | Block 3 resident, 0x238f, 1 slot | works; Chug knob barely audible |

Options: `--with none | commander | commander,corrupt | commander,corrupt,ottobit |
commander,corrupt,ottobit,syntax` for other sets, `--nam-host ir` for NAM on the 1024 IR (suffix
`_NamIR`, MD5 `d372b440…` with the default set), `--meter` for the cycle-meter build, `--probe` for the
memory probe, `--no-check` to skip the simulator checks. Room left: about 2 KB of Entry 2 and a few dozen
words of Block 3 (cursor 0xe7c10 against a limit of 0xe7c2f), so no further resident kernel fits.

Why NAM moved: in the IR category, the unit would not list any other IR block beside a NAM block, in
either order, though a second NAM was fine. Most likely an app rule allowing one IR block type per
preset (NAM inherited btype 0x13, the 2048 IR is 0x14); the check itself was not found. On the Regal
Bass DI NAM keeps its IR‑block audio graph and still reads captures from the User IR store with no IR
block in the preset (tested on the unit 2026‑11‑10). IR Select's `dynamicList` display exists only on IR
blocks, so Model became an ordinary list, and stock lists stop at 21 entries. The graph's cut filters
stay in, parked at 19.9 Hz and 20.1 kHz (Q 0.707), with the mix at wet 0 dB, dry off.

Known and left alone: with one NAM in each path of a split, the bottom path is much quieter (the user
called it an edge case; both slots match the reference in the simulator). Doom Chug's Chug knob does
almost nothing audible except lower the level (not investigated; its pulse decays in about 0.15 s, so at
low Rate it mostly turns the drone down between steps). A Fuzz‑on‑Chug plus Sub redesign was proposed and
shelved.

## Custom effects (on `main` since 2026-11-04)

- **Click** (preset-block metronome) **works on the unit**: `python3 build_click.py` →
  `build/HX_Effects_v3.80.0_Click.hxf`, then `tools/flash.py flash` it. It takes over the **mono
  Mod/Chorus Echo** delay (Delay > Mono > "Click"); this image has **no NAM**. Knobs: Time (the delay's
  own, ms or note value, **synced to tap tempo / global BPM**, default synced 1/4), Beats/Bar, Accent,
  Sound, Level, Subdivision; footswitch bypass works. Tempo sync = the stock delay's map nodes 0x2a/0x54
  copied into Click's map; the kernel gets the beat length in seconds.
- Code: C99 reference + tests in `effects/` (`make -C effects test`), SHARC kernel in
  `effects/metronome/sharc/` (`make -C effects sharc-check`: bit-exact against the C reference in ssim),
  image read-back check `tools/verify/verify_click.py`. Geiger: C reference + tests in `effects/geiger/`,
  SHARC kernel in `effects/geiger/sharc/` (also in `make -C effects sharc-check`; its tables come from the
  C library, which the tooling rebuilds before loading). Baseline audit: `docs/baseline-audit.md`.
- **NAM + Click + Geiger** (`python3 build_all.py --with none` → `build/HX_Effects_v3.80.0_All.hxf`, verified offline
  with `tools/verify/verify_all.py` and `build/all_manifest.json`; **works on the unit**, 2026-11-04). Geiger
  (bit crusher, 8 knobs) takes over the mono Megaphone on primitive 0x012e; NAM runs 2 slots (frees Block 3
  for Geiger: data 0xe73d0..0xe78f6, code 48-bit 0xe50a4..0xe5215); the Blob 0 buffer is 0x7a000 words so
  NAM's DDR2 slots start at 0x296400. Geiger's curve tables are 64 steps (16 x 65 words) to fit.
  The NAM simulator check needed one rig fix: a test block without a slot must not fill the simulated
  IR store (the real slots end below it, now asserted).
- Hard-won rules for any custom kernel (details in `effects/README.md`):
  1. Restore **I1–I3** on exit (NAM does via B1–B3). Leaving I1/I2 advanced froze knobs and footswitches.
  2. **DM(3) of the instance block is not ours**: non-zero whenever the block is on; never write it,
     and don't treat it as bypass. Write nothing in the instance block except your slot word (12);
     keep state in your own slots (NAM's scheme).
  3. **Don't host a non-IR effect on an IR block.** HX draws IR pages (knob 1 = IR selector). A delay
     host gets ordinary pages, and its bypass works.
  4. Knob records: floats on Clarity's records (Bass, ChVol…) reach the kernel; a chorus "Mix" record
     did not. Lists must stay short (stock max 21 entries); a 281-entry list broke page drawing.
- **NAM + Click in one image** (**works on the unit**, 2026-11-04):
  `python3 build_nam_click.py` → `build/HX_Effects_v3.80.0_NAM_Click.hxf`; check it with
  `python3 tools/verify/verify_nam_click.py` (needs the NAM-only and Click-only images built first).
  NAM as before (1024 IR, primitive 0x9c75, Block 2 tail); Click on primitive 0x0128 (zero uses in stock
  graphs) with code/data in the top of Block 3 (data 0xe7c20.., code 48-bit 0xe5390..0xe54fa; the stock
  boot stream stops at 0xe47d2 and the stacks are in Block 2). Two host graphs need a bigger Blob 0 buffer:
  0x79000 words (0x21c400..0x295400), so NAM's DDR2 slots move up to 0x295400 (`NAM_SDR_BASE`) — the
  one NAM instruction that differs from the NAM-only image.
- **Commander and Corrupt** (merged to `main` 2026-11-04; **both images work on the unit**: they boot
  and both effects sound right): `python3 build_all.py --with commander` → `build/HX_Effects_v3.80.0_All_Commander.hxf`
  (NAM + Click + Geiger + Commander on the mono Xenomorph Fuzz, primitive 0x0100) and
  `--with commander,corrupt` → `..._All_Commander_Corrupt.hxf` (+ Corrupt on Octave Fuzz, Distortion >
  Legacy, primitive 0x0838); check with `python3 tools/verify/verify_all.py build/all_commander[_corrupt]_manifest.json`.
  C references and tests in `effects/commander`, `effects/corrupt`; kernels bit-exact in ssim
  (`effects/common/kernel_rig.py` is the shared builder/rig). Memory: NAM `--far-d 17` frees ~1,600
  Block 3 words; the binding limit is now **Entry 2's 512 KiB partition** (zero-fill LDR records save
  ~5.3 KB; the five-kernel image has 812 bytes left, with Commander and Corrupt merged into one kernel,
  `effects/corrupt/sharc/commander_corrupt_kernel.asm`). Details: `docs/baseline-audit.md`.
- **The next six** (on `main` since 2026-11-11; written on a branch from 2026-11-04): Ottobit, Stutter, Syntax, Grains, Sequence and Warp each
  have a C reference, tests and a SHARC kernel checked bit for bit (`effects/README.md`, "The next six";
  `make -C effects test sharc-check`). Ottobit is in the default image. Syntax was tried (`--with ...,syntax`)
  and dropped: it locked the unit's interface on knob turns beside Geiger or Ottobit, cause unknown. Stutter,
  Grains, Sequence and Warp are not in an image: they would have to be overlays.
  The route found (`docs/baseline-audit.md`, "Finding more memory"): overlays. Their code and data travel inside
  Blob 0, and a resident stub copies the code into internal memory through the normal-word view and calls it; probe 4
  proved that copy and call on the unit. Running 48-bit code directly from DDR2 froze the unit. Swapping different code
  into one region every call also worked (probe 5). **Ottobit runs this way on the unit** (`build_all.py --with commander,corrupt,ottobit`, MD5 `0d403adc...`). `BOOTED` from flash.py only means the main app answers on USB. Each new effect still needs a stock block to replace
  (ask the user which).

## Why the takeover approach

Anything that adds a *new listed* model fails the boot self‑test (`"Boot Failure res = -21"`): the
app resolves listed items through a path ending in an 8‑entry deprecated‑model table at `0x280fb8f4`
and returns −21 when nothing matches. Bisected exhaustively (E1–E16): compaction OK, relocation OK (once
the harness‑table pointers were understood), rows alone OK, any listed new model → −21, even a pure
duplicate of the IR block, any preset id, any btype. Taking over an existing model's identity sidesteps
it entirely. Cost: HX Edit can't edit the block (code −8200, its 5‑knob definition vs our 8), and the
1024 IR block is gone.

Other failures seen on the way and their causes: −33 = Heap 6 end word off by one (exclusive vs
inclusive); silent splash hang = Table 1 walk running to the old end pointer; "boxy" = IR graph's cut
filters at their static 1 kHz; "two signals" = wet/dry sum at −3/−3 dB; "dry only" = mix pair swapped;
"no low end" = cut frequencies swapped.

## The USB flasher, in one screen

Taken from a capture of Line 6 Updater 1.28 flashing this build (`tools/usb/capture.sh` injects
`usblog.dylib` with `DYLD_INSERT_LIBRARIES`; the Updater has no hardened runtime; `decode.py` reads the
log). `flash.py replay <hxf> <log>` reproduces the Updater's traffic byte for byte. The log is in
`usblog/` (git‑ignored: it contains firmware bytes).

1. Main app (`0e41:4245`, class 0xef, device‑info name `F15Main`): update‑port handshake, cmd 01/03/02,
   close. It restarts into the NXP ROM DFU loader (`1fc9:000c`).
2. DFU 1.1: the `.hxf`'s kind‑5 region (83,472‑byte updater app) in 2048‑byte DNLOAD blocks + GETSTATUS,
   then a zero‑length DNLOAD. The unit comes back as `0e41:4245` class 0 (`F15Updater` v0.09.5a).
3. Updater app: cmd 04 per image (status), then per L6IA entry: 05 begin (id, words, entry‑header
   Fletcher pair), 06 start, 07 chunks of 4096 words (index, chunk Fletcher pair, LE data), 09 end; then
   0a finish. About 100 s, limited by the unit (~200 kB/s).
4. Boot check: the main app answers `F15Main` on its device‑info port. This does not yet tell a clean
   boot from one stopped at "Boot Failure"; look at the screen too.

Transport: 16‑byte header (u16 len‑after‑8, kind 0x28 connect / 0x18 stream, ports 0x1001→0x03ef,
u8 seq, BE u16 flags 02/04/08/10, u32 ack = peer base + bytes received), ≤496‑byte payloads, 512‑byte
window, heartbeat every 1 s (the unit times out at 4 s).

**Image 4 is always flagged (status 5).** The updater app's partition table (in the DFU app, file
offset ~0xf8dc) declares image 4's partition as 0x5000 sectors (10 MiB) and flags any image whose header
length exceeds that. Stock 3.80.0's image 4 is already 12.4 MB (the HX Stomp's too); ours is 14.3 MB.
The physical gap to image 5's header (sector 0x11005) is 0x7bfe sectors (15.5 MiB), which the build's
`E4_MAX` stays under. Not damage. One unproven assumption: nothing else uses the sectors between
stock's end and ours (not in the partition table; presets and IRs live elsewhere; nothing broken so far).

## Things that were tried and are still in the scratch tree (not in the standalone repo)

- `NAM_E0_PART`, `NAM_SKIP`, `NAM_NO_SWAP`, `NAM_NO_EXTRA`, `NAM_DUP_IR`, `NAM_REPLACE_1024`,
  `NAM_LIST_ONLY_MOVE`, `NAM_E2_PART`, `NAM_SKIP_E0`, `NAM_SDRAM`, `NAM_PID`: bisection env switches in
  `~/hx-stomp-nam-lite/tools/patch_amp.py` and `build.py`. Harmless; could be stripped.
- `add_model_entry0_effects()`: the superseded "new model + folder" Entry 0 path. Dead code now.
- `apply_effects.py` … `apply_effects4.py`: the edit scripts that turned upstream into the Effects
  version, in order. Re‑runnable on a fresh upstream clone (part 2 needs the Effects MD5 as argument;
  then the small follow‑up edits from the chat: Blob0 byte‑order assert, Heap 6 `0x3230ca`, harness
  pointers, `P_SLOT`‑based fixed SDRAM, mix/cut overrides, `strip_title`).

## 2026-11-21: tuner sharps, DSP costs, renames, setup page

- **Tuner sharps** (`tools/tuner_sharps.py`, run by `build.py` unless `--flat-tuner`; user: looks right on the unit).
  Letters are text from 12 pointers at 0x280a43c0 (now C C D D E F F G G A A B). The sign the HX Effects shows is a
  6x19 1-bit scribble-strip icon (set 10, index 11, at 0x280986d8; used only by the tuner), now a '#'. Entry 8's
  Tuner_Flat (the Stomp-style picture) is redrawn too but is not what this unit's tuner shows.
- **Per-effect overlay DSP costs** (`build_all.py` OVL_COST: Drum Chapel 1550, Ottobit 1300, Pure Whitey 1100,
  Greasy/Bethblahem/Puggy 1000, Doom Chug 900). A flat 700 let Commander + Doom Chug + Drum Chapel + Pure Whitey
  crash the unit (2026-11-18); a flat 2300 was too strict (user).
- **Display names** (user, 2026-11-21): Geiger "Bolt, Rocket!", Commander "Garrrry Tank", Corrupt "Quality Polis",
  Ottobit "Bam Crusher". Display only: the HD2_ model names and the code's names stay, so presets keep working.
- **8 snapshots: not feasible.** snapshotModel keeps 4 fixed 0x26c-byte records with `cmp #4` loops at about a dozen
  sites; preset storage, the footswitch UI and HX Edit all assume 4.
- **Setup page** (`web/`, branch `setup-page`): a browser page that makes NAM / NAM + Amps / full from the user's
  stock file with a recipe (`tools/recipe.py make BUILD.hxf web/recipe-<mode>.bin` after every release build; the
  page checks the result's MD5), installs it over WebUSB (`web/flasher.js`, same bytes as `flash.py`) or via Updater,
  converts .nam captures (level-matched), and has a Rescue section that reflashes stock. Unit image now `06fee4c9`
  (full), flashed with flash.py. Hosted at https://scottlynn73.github.io/hx-effects-nam-lite/ (branch gh-pages; since 2026-11-23
  made by `tools/deploy_pages.sh`: web/ plus the preset builder in preset-builder/, then `git push origin gh-pages`). Install and Rescue from the page tested on the unit by the user (2026-11-21).
- **Drum data** (`grooves_data.h`, `samples_data.h`) is committed now (user: none of it is private).

## 2026-11-21: User IR slots over USB (tools/ir_upload.py, the setup page's step 4)

From two captures of HX Edit (`tools/usb/capture_hxedit.sh`: it runs HX Edit with the logger, which needs a copy of
HX Edit.app ad-hoc re-signed without the hardened runtime, `HX_EDIT=<copy>`; the logger is built universal against
HX Edit's own libusb). Same channel as flash.py (port 0x1001 -> 0x03ef); select service 2 with
`010002000100000002`; then [u16 1][u16 type][u32 n] msgpack, requests {102 id, 100 op, 101 args}, answers
{102, 103 status, 104 result}. **Old-spec msgpack only** (str16/str32 raw, no str8/bin: refused with {111: -3}).
- op 13 {101: 2}: IR list [{112 index, 109 name, 104 MD5 of the samples}].
- op 9 import {112 index, 113 sum of the samples' LE 32-bit words, 109 name, 114 1, 115 3, 123 F, 124 F, 125 0,
  110 samples (the .wav data chunk)}: answers 1 "working"; the "done" message only reaches a subscribed client, so
  the tools wait for the list to show the MD5. A wrong 113 renames the slot and keeps no samples.
- op 10 rename {112, 109}; op 15 delete {112}; op 12 info {112}; op 11 samples {112, 101: 2} (answered in a
  message of type 10240). Copy = 12 + 11 from one slot, 9 into the other (HX Edit does it that way).
- **Never ask op 11/12 for an empty slot**: the unit never answers and its USB message channel stays dead until a
  power cycle with USB unplugged (2026-11-21). Both tools check the list first.
- Tested on the unit: put/rename/copy/delete/get (Python), and the page's code (web/flasher.js) from Node with the
  `usb` package's WebUSB and from Chrome (user).

## Open / next

1. ~~Verify the standalone build on the unit~~ — done 2026‑11‑03 (flashed twice, boots). Still worth a
   look: the "NAM / IR_2048" strip title.
2. ~~Add the DSP‑cost tuning note to the README~~ — done (README; `DSP_COST` lowered to the measured 2300
   on 2026‑11‑10).
3. ~~Strip the bisection switches from `tools/patch_amp.py`~~ — done 2026‑11‑03: all `NAM_*` env switches
   (except `NAM_DEVICE`) and the dead `add_model_entry0_effects()` removed; the build output is byte‑identical
   (MD5 `a27780d3ff57612ebd2484a4cc4a9f7e`). The HX Stomp `add-model` path is kept.
4. ~~Upstream issue/PR with the findings~~ — not doing (user, 2026‑11‑17).
5. ~~Edge tests~~ (Model change while playing with two blocks, every heavy effect in one preset, power cycle
   with NAM in the startup preset) — done by the user (2026‑11‑17).
6. ~~NAM's footswitch bypass~~ — checked by the user, works (2026‑11‑17).
7. ~~Model knob reaches only User IR slots 1..21~~ — fine as it is (user, 2026‑11‑17); don't pursue.
8. ~~**Doom Chug's Chug knob → Fuzz**~~ — done 2026‑11‑17, works on the unit (user: "it works"; log clean). The
   knob (sixth, word 10) is now Fuzz, default 0.3: drive = 0.6 + 23.4 Fuzz² on the voice sum into the existing
   clip (1x .. 40x), Level x (1 − 0.45 Fuzz); the thud stays at a fixed 0.4 (K_THUD). C ref + tests
   (effects/doomchug), kernel bit-exact in ssim (390,400 samples). To fit between NAM and Click the kernel's six
   4-instruction pointer steps became `MODIFY(I4, VSIZE)` / `I4 = MODIFY(I3, ST_V0)`: 350 instructions (was 368
   after the change; smaller than before it), worst 2,466 cycles a call. Full + preamps image with it:
   e549c1579fb5830a56b71d38ff2b722c (build_all.py --no-check, then build_amps --preamps all); base full image
   132df9c738fcded23204d5a70803f9db.
9. ~~More overlay effects (Stutter, Grains, Sequence, Warp)~~ — not doing (user, 2026‑11‑17). Stutter's code
   lives on as the base for item 12.
10. **User IR upload without HX Edit** (user asked 2026‑11‑13; later, user 2026‑11‑17). A `tools/ir_upload.py` that writes `.wav`
    files (and `.nam`, converting on the way) into numbered User IR slots over USB, e.g. a folder of `01 …wav`
    .. `19 …wav` into slots 1..19. Plan: capture HX Edit importing one IR with `tools/usb/usblog.dylib`
    (DYLD_INSERT_LIBRARIES, as for Line 6 Updater; HX Edit may have a hardened runtime, then another capture
    route is needed), decode it with `tools/usb/decode.py` (expected: the same 16‑byte message framing as the
    flasher, port 0x1001 -> 0x03ef, unconfirmed), then replay it as flash.py does and check the slot reads back.
11. ~~Level-match captures~~ — done 2026‑11‑13: `nam2ir.py --match [DB]` (default −18) scales the head's output
    scale (the last weight; the head is linear) so the capture plays at DB on a fixed test signal (strummed E‑A‑D
    chord, 1 s, −10 dBFS peak, times the kernel's input trim), K‑weighted per BS.1770. `tools/sharc/nam_level.py`
    runs the network in numpy (float64), checked against nam_a2.asm in ssim to 1.3e‑6 on a high-gain capture; ssim
    itself is too slow (over 50 M instructions for 0.5 s). A set of 19 user captures measured −29.1 .. −11.0 dB
    before matching. Only the output-scale word changes; the rest of the stream is identical.
12. **Pure Whitey** (the user's name, was "Mandala-style glitch block"; user wants it, 2026‑11‑17; to do, nothing built; 11 characters). Modelled on the Bananana Effects
    Mandala, a mini short-time sampler: modes Repeat, Random, Reverse, Trigger, Square Trigger, Square, Up, Down;
    Time (repeat length, random at full), Func (speed x1/x2, reverse x½/x1/x2, octave-down mix in the Square modes),
    latch/momentary (use the unit's own momentary footswitch setting), Kill Dry. No circuit to copy: built from the
    descriptions, tuned by ear. Plan: extend `effects/stutter/` (already does Repeat/Random/Reverse/Trigger, speeds,
    random length; C ref + bit-exact kernel, never in an image) with Corrupt's square tracker for the Square modes and
    a pitch sweep for Up/Down (Warp's technique), plus a Dry knob. Runs as an overlay like Ottobit (no resident room).
    To check first: DDR2 room for Stutter's 32,768-word ring (about 31K words were free above NAM's slots; recheck
    with the amps images), the overlay swap cost beside Ottobit (~19 % DSP), and which stock block to give up (ask;
    avoid tempo-sync hosts like Bleat Chop Trem, given Syntax's unexplained locks). Simulator first, then a test
    image from `build.py full`; ask before flashing.
13. **Greasy Strangler** (user wants it, 2026‑11‑17; to do, nothing built; the user's name for it). A drone that
    follows the guitar: Doom Chug's four-voice drone (root, sharp root, fifth, octave; Drift/Warble) tuned to the
    last note played, via Corrupt's pitch tracker, holding that note until a new one is detected, with a glide
    between notes and a mix with the dry guitar. No audio buffer needed. Doom Chug and Commander/Corrupt are
    resident with no room left, so it runs as an overlay like Ottobit (its own copies of the tracker and drone
    code). Needs a stock block to replace (ask) and a check that "Greasy Strangler" (16 characters) fits the
    browser name and the footswitch scribble strip, or a short form for the strip. C ref + tests + bit-exact
    kernel, then a test image from `build.py full`; ask before flashing.
14. **Drum Chapel** (the user's name; was "Drums", then "Beat It Rocket"; user wants it, 2026‑11‑17; to do, nothing built; 11 characters). A basic drum-machine block built on Click's timing
    (exact rational accumulator, tap tempo via the host delay's Time, bar and 16th-note counting): synthesised kick
    (sine with fast pitch drop + decay, Click's Rotor), snare (filtered noise burst + short tone), hi-hat (short
    high-passed noise; xorshift noise as in Doom Chug). Patterns as 16-step bit grids per voice (as Doom Chug's
    patterns), a Pattern list of up to ~20 (rock, half-time, four-on-the-floor, shuffle, motorik, ...), stock lists
    stop at 21. Knobs (8 words): Time, Pattern, Kit, Kick, Snare, Hat, Swing, Level (Kit replaces Decay/Tone: each
    kit sets its own decays and tone). Kits (user asked for several drum-machine sounds), all synthesised from one
    set of voices with a table of settings per kit, so each extra kit is data, not code:
    - **Boom** (808-style): long low sine kick with a slow pitch fall, snappy noise snare, metallic hat from six
      detuned square oscillators;
    - **Punch** (909-style): short tight kick with a fast sweep and click, brighter snare, bright noise hat;
    - **Tick** (CR-78 / old preset-box style): soft short kick, small snare, ticky high hat;
    - **Bit** (8-bit): square-wave kick and snare tone, noise at a low sample rate, crushed hat;
    - **Doom** (user: "super low tuned and fuzzed out", 2026‑11‑17): every voice tuned way down (kick sweeping
      to ~30 Hz with a long decay, snare body ~90 Hz with a thick noise tail, hat dark and low-passed), then the
      whole kit through heavy fuzz: high gain (~40x) into a hard-ish clip, level-compensated, so hits smear into
      a distorted wall. Shares the drive code with the other kits (they use little or none); the clip shape may
      reuse what item 8's Chug fuzz ends up with;
    - **Eighty** (LinnDrum-style, user asked 2026‑11‑17): the real ones play recorded drums, so this is the
      closest synthesis: kick with a body tone plus a beater click, snare with two tuned body modes (~180 and
      ~330 Hz) plus band-passed noise, crisp short hat, and a gated-reverb-style snare tail (a noise tail cut off
      sharply after ~150 ms: no buffer). Expect "80s drum machine", not samples.
    Labels on the unit stay generic (no product names). Extra code over the plain version: the six-oscillator hat,
    the per-kit drive and the sample-rate hold for Bit; the rest is table data. Separate block, Click
    unchanged: Click is resident with no room in the full build, so Drum Chapel runs as an overlay like Ottobit. Host
    must be a tempo-sync delay (ask which), copying Click's sync map nodes 0x2a/0x54. Unknown: whether enabling the
    block restarts it at beat 1 (metronome.h notes the same open question); test on the unit. C ref + tests +
    bit-exact kernel, then a test image from `build.py full`; ask before flashing.
15. **Bethblahem** (the user's name; a mega low tuned theremin; user wants it, 2026‑11‑17; to do, nothing built;
    11 characters; stock names as long as "Tweed Blues Brt" show on the scribble strip, so it should fit). Corrupt's pitch tracker drives a sine voice that glides between notes (Glide knob) with theremin
    vibrato (Vibrato depth and Rate), transposed far down: Octave knob 0 to −4 (low E at 82 Hz → ~5 Hz at −4, so
    the useful bottom is about −2 to −3, 10–20 Hz fundamentals). A pure sine that low is inaudible on most rigs, so
    a Growl knob adds harmonics (soft clip / wavefold of the sine) so the pitch is heard through a guitar cab or
    small speakers, plus a sub-octave mix and a Dry mix. Holds the last note while the tracker has nothing (as
    Greasy Strangler, item 13; the two can share tracker and hold code). No buffer; overlay like Ottobit; needs a
    stock block (ask). Watch: tracker lag on low notes; a 10 Hz sine at full level moves speaker cones hard, so
    keep a high-pass / level limit option. C ref + tests + bit-exact kernel, test image from `build.py full`;
    ask before flashing.
16. **Puggy Puncher** (the user's name; a "slot machine" glitch; user wants it, 2026‑11‑17; to do, nothing built;
    13 characters). On each step (Step knob: beat, 8th, 16th, synced via the host delay's Time like Click, with
    Click's exact timing) it rolls a random treatment for that step: clean, octave down (Corrupt-style square
    sub), bit crush / sample-rate hold (Geiger/Ottobit-style), mute, filter slam (resonant low-pass snapped shut),
    fuzz (hard clip). Knobs (8 words): Time, Step, Chance (how often a step changes from clean), a mask or Wildness
    choosing which treatments can come up, Hold (repeat the last roll for N steps), Mix, Level, and a Seed/pattern
    list so a good run can be repeated. 32-sample crossfades at step edges to avoid clicks. No buffer (unless a
    short "repeat this step" stutter is added later: then a small ring); overlay like Ottobit; host must be a
    tempo-sync delay (ask which; Drum Chapel, item 14, needs one too). C ref + tests + bit-exact kernel, test image from
    `build.py full`; ask before flashing.
17. ~~**Reclaim memory**~~ — skipped (user, 2026‑11‑17): Entry 2 has 2,096 bytes free and Block 3 a few dozen words, so a resident ~400-instruction effect (~2.5 KB of Entry 2 + ~600 Block 3 words) would need a big restructure; items 12–16 are built as overlays like Ottobit instead (two overlays in one preset cost ~28,000 cycles a swap). The MODIFY trick finds only ~3 instructions in the resident kernels (Commander/Corrupt). Original notes: Goal: room for one or
    more of the new effects to be resident instead of overlays, so two of them in one preset don't pay the
    ~28,000-cycle swap (~19 % DSP) each call. Limits today: Block 3 has ~20‑30 words spare (cursor 0xe7c10 vs
    0xe7c2f) and Entry 2's 512 KiB partition ~2 KB. Candidates: build Geiger's curve tables (1,040 words, now in
    Blob 0) and any other kernel tables at start-up from a short generator instead of storing them; share common
    routines between kernels (noise, clamp, one-pole filters, Click's timing accumulator, Corrupt's tracker, used
    by items 13, 14, 15, 16); more zero-fill LDR records; see what else in Block 3 / Entry 2 is ours and
    compressible (`docs/baseline-audit.md`, "Finding more memory"). Every change must keep the existing effects
    bit-exact in ssim and the images' behaviour unchanged (rebuild and compare against the known MD5s where the
    bytes should not move). Hidden-model scan done 2026‑11‑17: no hidden effects beyond amps, preamps, cabs,
    harness/mic internals and sub-parts, so new sounds all need our own code.
18. ~~**Master volume**~~ — dropped by the user (2026‑11‑17) after the findings below; don't pursue unless asked. (It worked in a test image; a Global Settings item was planned.) The HX Effects has
    the Stomp's App-model parameter `masterVolume` (HelixFx_App slot 46, 0..1, default 1.0), reached as **global
    parameter 157 (0x9d)**: its live record is at 0x2819eed8 (table 0x2819eda4, 44-byte records for global ids
    150..164; only 157 is used; record: model 0x1023, type 3, value at +8, slot 0x2e at +0x1c, default at +0x28).
    Setter 0x280e98d4(?, id, &{type byte, value}), getter 0x280e98b8. Three writers force it, so changing the
    Entry 3 / Entry 4 defaults alone does nothing (tested at 0.5 and 0.1: no change):
    - 0x280a6914, the HX Effects' start-up routine: 157 = 0.0 at 0x280a693c (start-up mute), then 157 = 1.0 at
      0x280a6ae8 (`mov.w r3, #0x3f800000`) when start-up is done;
    - 0x280c744c, applying the saved global DSP settings: walks ids 150..165 and gives 157 a fixed 1.0
      (`mov.w sb, #0x3f800000` at 0x280c7460) instead of the saved value; so the value IS in the saved settings.
    `tools/mastervol_test.py BASE VALUE --force` changes both constants and both defaults (VALUE must be an ARM
    immediate: 0.125, 0.25, 0.5 ...). Image 64b6d1efaedf602aca60ea35df154aa9 (full + preamps, 0.125): flashed,
    boots, no fault, live value 0.125 over the memory window; user: "Much quieter". So masterVolume reaches the
    DSP's output. Taper (linear or curved) not measured. Next: choose the control (a Global Settings item that is
    saved and restored, an expression pedal, a fixed per-build level, or a knob/footswitch combination); for a
    saved setting, the two forced writes become "use the saved value" and something must set it.
    Planned before it was dropped (an offline study, nothing built): Global Settings UI = ./src/app/fsGlobalsView.c;
    pages 0x280a3ee8 (rows 0x280a3f00, 3 knobs a row), item lists per page (Ins/Outs 0x280a3c30 = 2,3,4 | 5,0,0),
    item records: ids 0x280a3b9c, labels 0x280a3c60, ring max/min 0x280a3da4 / 0x280a3e34; hidden item 1 "Input /
    Pad" could become "Master / Vol" on Ins/Outs row 2; the value formatter 0x280a7544 handles ids <= 0x87 only;
    the setter skips the save flag for 157 (0x280e94c0); boot: 0x280a67b0 -> 0x280c744c (forced 1.0) -> 0x280a6914.

**Hosts chosen by the user (2026‑11‑17)** for items 12–16, all built as overlays (item 17 skipped), each taking
over the MONO version only: Pure Whitey → Tycoctavia Fuzz (Distortion), Greasy Strangler → Boctaver (Pitch/Synth),
Bethblahem → Twin Harmony (Pitch/Synth), Drum Chapel → Ratchet (Delay, tempo sync), Puggy Puncher → Sweep Echo
(Delay, tempo sync). Overlays share one Block 3 region sized by the largest member, so keep each new kernel no
bigger than Ottobit's (code 660, data 316 words); Pure Whitey's ring must fit the DDR2 left above NAM's slots.

## Five new overlay effects (2026‑11‑17; all five play on the unit, 2026‑11‑18)

`python3 build_all.py` now builds NAM, Click, Geiger, Commander, Corrupt and seven overlays: Ottobit, Doom Chug (an
overlay since this change, to free Block 3 for the stub) and the five below. Each has a C reference + tests and a
SHARC kernel checked bit for bit in ssim (effects/<dir>, `make -C effects test`, `<dir>/sharc/<dir>_kernel.py --check`).

| Effect | Dir | Host (mono) | Primitive | Code / data / worst cycles | Notes |
|---|---|---|---|---|---|
| Pure Whitey | purewhitey | Tycoctavia Fuzz | 0x2aac | 421 / 151 / 2,547 | Mandala-style sampler, 8 modes; 1 slot; 4,096-word ring (16-bit pairs at 24 kHz = 0.34 s) in DDR2 |
| Greasy Strangler | greasy | Boctaver | 0x2ab6 | 398 / 128 / 2,788 | Corrupt's tracker + Doom Chug's drone; holds the last note |
| Drum Chapel | drumchapel | Ratchet (tempo sync) | 0x23ac | 515 / 452 / 6,821 | Click's timing; Classic (20 patterns) + 11 converted groove families, 4 voices, 7 kits (Boom, Punch, Tick, Bit, Doom, Eighty, Acoustic: sampled kick and snare); was 451 / 398 / 6,620 before Acoustic, 409 / 296 / 5,345 before the grooves |
| Bethblahem | bethblahem | Twin Harmony | 0x0833 | 399 / 80 / 3,535 | low theremin, Octave 0..-4, Growl, Sub; 6 Hz high-pass + limiter |
| Puggy Puncher | puggy | Sweep Echo (tempo sync) | 0x045e | 377 / 133 / 2,627 | slot-machine glitch per step; Seed repeats a bar |

Build changes (build_all.py): `--with` takes any set (corrupt needs commander, one effect per host); OVERLAYS lists
the overlay effects, RING_OVERLAYS those with a DDR2 ring (rings above NAM's slots, in order); with more overlays
than Ottobit the Blob 0 buffer takes all DDR2 left below DDR2_LIMIT (0x2a8df6). `sync_knob_params` gives an effect on
a tempo-synced delay Click's Time + SyncSelect1/TempoSync1 (slots 1, n+1, n+2) and build_click.click_host_blob.
`compact_blob0` removes the dead composite-table copies that patch_amp.clone_composite_in_blob0 leaves behind
(~3,150 words per added host graph; ~28,600 words with this set); it runs before each added graph when there are
more than two overlays, so older builds are byte-identical. New primitives were picked as ids in the Entry 2
primitive table that appear nowhere in stock Blob 0 (the proven ones pass the same test); 0x0104, 0x0105, 0x012c,
0x012d, 0x0130, 0x0205.. remain. verify_all.py takes the category from the host, the sync knobs, and the rings.
Risks on the unit: the compacted Blob 0 layout (passes sharc_blob0_check) and seven overlays swapping in one stub.

On the unit (2026‑11‑18): all five play; the compacted Blob 0 and seven overlays in one stub boot and run. The one
fault was that **Drum Chapel ignored its footswitch**: Ratchet's metadata says `followEnable` and `loadBypassed`
(type `special`), as the stock generators (3 Note Generator, 4 OSC Generator) and Stutter Edit/Poly Sustain have: the
unit keeps such a block running and hands the DSP its on/off state, so a drum generator kept playing. Dropping the
Entry 3 fields alone (image 15fd1c5d…) changed nothing: the ARM has its own copy, **Entry 0 Table 2 word 36** (byte
36 of the 44-byte row), 1 for exactly the 15 followEnable models and 0 for the other 762. Drum Chapel now has both
cleared (EFFECTS `meta_drop`/`meta_type`; patch_amp.add_model_entry3 `meta_drop`, takeover_entry0_effects
`follow_enable`; verify_all checks both for every effect). Image d4e82c58… (full + preamps) differs from 15fd1c5d…
in that one byte. **That did not fix it either** (on the unit, 2026‑11‑18). What did (user confirmed the footswitch
works): (1) the browser item's first byte is the **block type**, which the takeover keeps: 0x08 an ordinary delay,
0x18 Ratchet/Tesselator/Poly Sustain/Feedback Sim/Poly Pitch, 0x17 the synth generators, 0x16 loopers, 0x13..0x15
IRs; Drum Chapel's is now 0x08. (2) The app also names its special delays in code (`movw rX, #0x789` for Mono
Ratchet at 0x280bd8de, 0x280f41c0, 0x280f612c, next to Tesselator, Poly Sustain...); those three now compare with
0xffff, and the routine at 0x280bd8a4 needs both (type 8 *and* not on the list). `tools/special_delay_patch.py`
(`patch_e0`), called by build_all for EFFECTS `plain_delay`; verify_all checks both. The Entry 3 and Table 2 changes
stay (harmless, consistent). **For any future host, check its block type and whether its name index is in those
lists.**

**Drum Chapel grooves (2026‑11‑18, not yet on the unit).** A new knob **Groove** (instance word 14, display slot 2;
Pattern became a plain "1".."20" list in slot 3): 0 = Classic (the 20 patterns, bit for bit as before, the
default), 1..11 = families of longer grooves (Doublerino, Fake 1st, Proggy 13/4, Crazy 14/4, Antibeat, Free Beat,
Chaos 29/4, Dum Dum, Dam Dam, Tomapalooza, Tomathon) converted from a commercial MIDI loop pack by
`effects/drumchapel/grooves.py FOLDER` into `effects/drumchapel/grooves_data.h`. It is committed (the user lifted the never-commit rule on 2026-11-21). Without it every
Groove plays Classic and everything still builds and checks. Each groove keeps its full length and meter (up to 384
sixteenths), quantised to sixteenths; the step counter wraps at its length, and a Groove/Pattern change continues at
(step mod the new length). A fourth voice, Tom (four pitches, at the Kick knob's level, designed per kit), and an
open-hat/cymbal decay on the hat voice. The pattern data is a read-only bank in DDR2 inside Blob 0, right after
Geiger's curves (3,247 words with the pack, 320 without; manifest `overlay.grooves`), read by the kernel only when a
step falls (two words a sixteenth), never swapped into the overlay region; build_all places it before laying out the
overlay payload and assembles the kernel for its address (`drumchapel_kernel.place_bank`), verify_all checks the
words in Blob 0. Details: `effects/README.md`, "Drum Chapel". verify_all now expects each effect's own instance
words (Drum Chapel's map writes 5..11, 13 and 14). Risks for the unit test: the first overlay that reads DDR2 it
did not write (overlay DDR2 access itself is proven by Ottobit's and Pure Whitey's rings) and the first use of word
14 by an overlay host (NAM uses 15 on its own host); 9 knobs on a Ratchet host (8 before); list labels up to 11
characters ("Proggy 13/4", "Tomapalooza"); Drum Chapel's swap is 678 + 398 = 1,076 words (was 615 + 296), and its
398 data words are now the overlay region's largest (Ottobit's 316 before). Image: `build.py full --quick` ->
`build/HX_Effects_v3.80.0_NAM_Amps_Effects.hxf`, MD5 09732d36f865985d41f4ee0d818bea8d, verified ALL OK (bank at DDR2
0x294839), with the pack converted. With the footswitch fix (`plain_delay`, 14 Entry 0 bytes on top of that image):
MD5 4eb77e0466f794be9f21db06f188454f, verified ALL OK, flashed 2026‑11‑18; the user played the grooves: "sounds good".

**Drum Chapel's Acoustic kit (2026‑11‑18; image d1b14ce7 flashed, the user played it: "sounds good").** Kit 6, **Acoustic**: its kick and snare play
recorded samples, its hat, tom and open hat are synthesised (the open hat, which plays every crash/ride/china of the
grooves, is its closed hat a little open: same tone, 1.75 x the decay, 0.7 x the level; the first version's long
wash sounded bad on the renders). The samples are the user's own bounces (a kick and a snare from their Logic
folder, possibly of a commercial drum plugin), converted by `effects/drumchapel/samples.py KICK SNARE`
into `effects/drumchapel/samples_data.h`, which is committed (never-commit rule lifted 2026-11-21); without it Acoustic plays Punch's synthesised kick and snare and everything builds and checks
(verified in a scratch copy). Trim: the first hit only, from a near-zero sample just before the onset, to 5 ms before
the high band rises again, with a raised-cosine fade over the last 30 %: kick 226 ms (the bounce's next kick starts at
238 ms), snare 229 ms from its onset 25.4 ms in (a noise burst follows at 260 ms); mono, 48 kHz (fixed Kaiser sinc),
same peak, 16 bits two to a word: 10,922 words, a read-only table in Blob 0 right after the groove bank (manifest
`overlay.samples`; verify_all checks its address, T_SAMP and its words), never swapped. Blob 0 is 0x7df45 of its
0x7f000 words (4,283 free; 15,355 before). A sampled voice reads one DDR2 word a sample (two during a 64-sample
retrigger crossfade); Acoustic's DRIVE 0.25 keeps the samples clean (at most 0.2 dB off at a full-scale peak).
Kernel 515 instructions / 452 data / worst 6,821 cycles in ssim (was 451 / 398 / 6,620); the swap is 774 + 452 =
1,226 words (was 678 + 398) and the shared overlay region grew with it (the other overlays' code re-assembles at the
moved address, their data address is unchanged). Details: `effects/README.md`, "Drum Chapel". Image: `build.py full
--quick` -> `build/HX_Effects_v3.80.0_NAM_Amps_Effects.hxf`, MD5 d1b14ce704589e687c6909b1f512a26e, verified ALL OK.
Risks for the unit test: per-sample DDR2 reads from an overlay (up to four a sample: kick and snare both
crossfading, ~64 a call; ssim does not model DDR2 latency, Pure Whitey's ring is the nearest proven case), the larger
swap per call, and Acoustic's output, which can reach about 2 x Level where kick, snare and tom meet at full knobs.

## 2026-11-27: Part A, Drum Chapel's user grooves and the groove editor (branch `user-grooves`)

- **The plan, after the host probe** (branch `probe-build`: a block gets the SDRAM its graph member asks for):
  grooves are read straight from their IR slot (no SDRAM); the Acoustic kit's five voices become 8-bit mu-law at
  24 kHz in Blob 0 (user's choice after an ear test: `effects/drumchapel/formats_demo.py` renders kick, snare and a
  beat as 16-bit/48 kHz, mu-law/48 kHz and mu-law/24 kHz), decoded as they play; a user kit from slots 121-127 is
  copied into the block's own SDRAM block (next). Slot numbers: grooves 128, kit 121-127 (user, 2026-11-27).
- **User grooves: done in the reference and the kernel.** Groove 12 = User reads User IR slot 128 (format:
  `effects/README.md`, "User grooves"). `grooves.py --user FOLDER` writes the slot's .wav from MIDI loops.
- **The groove editor** (`tools/groove-editor/`, linked from the top of the setup page; on the site at
  groove-editor/ via `tools/deploy_pages.sh`): a step grid (any N/4 or N/8 meter, bars, up to 20 patterns, the
  unit's eight sounds: kick, snare, closed and open hat, four toms, with its one-hat/one-tom rules), preview with each
  kit's sounds as the reference makes them (`make -C effects kit-sounds` renders the 56 one-shots into
  `tools/groove-editor/sounds/`), your own hits for previewing, MIDI import (`groove-core.js`, byte for byte
  `grooves.py`: `tools/groove-editor/check_core.py`), .json save/open, the slot's .wav, and Send to unit (slot 128
  over WebUSB, as the setup page sends IRs). Twenty starting points in `beats.js`, written for this project and
  named for their feel (rock, metal, punk, breakbeat, a toms fill, a few odd meters): no MIDI or audio from anyone.
- **Test image** (`build.py full --quick`, kept as `build/HX_Effects_v3.80.0_NAM_Amps_Effects_UserGrooves.hxf`):
  MD5 4722479f79bbc85860c3b5cd94edba83, verified ALL OK; flashed 2026-11-27, booted, no fault. Tested on the unit
  2026-11-27: the editor's Send to unit writes slot 128 and Drum Chapel's User groove plays the patterns as sent.
- **The Acoustic kit, five sampled voices (2026-11-27).** The hits are Naked Drums by Wilkinson Audio (CC BY 4.0,
  the user's pick over Big Rusty Drums; committed with credit by the user's decision, an exception to "no third-party
  samples": README copyright notice and Thanks, samples_data.h's header). Snare 2, tom 3, the hardest hits, close mics
  mixed with overheads; lengths kick 350 / snare 400 / hat 120 / tom 500 / open hat 800 ms (user); 8-bit mu-law at
  24 kHz, 13,020 words in Blob 0; gains 1.2 (hats 0.6). Reference: 16.16 position and step per voice, interpolated,
  the tom at four steps, a 64-sample crossfade on every hit (the closed hat chokes the open hat); 239 checks pass.
  Kernel: bit for bit on 438,400 samples; the seven kits moved from the overlay data to DDR2 (T_DKIT, after the
  samples; a call copies its kit into T_KIT), a decode cache per hit. Figures: 737 instructions / 254 data words /
  worst 9,830 cycles (was 515 / 452 / 6,821): the check's own 9,000 limit fails until the user decides Drum Chapel's
  cost (by build_all's rule about 300 + words copied). The first build before the kit move did not fit (the overlay
  region's data 128 words over, before Click); the image with the move: see below.
- **Test image** (`build.py full --quick`, kept as `build/HX_Effects_v3.80.0_NAM_Amps_Effects_AcousticKit.hxf`):
  MD5 489fb38678d0ff0b1455b4c4608d5617, verified ALL OK; the overlay members' swap words, Drum Chapel 1107 code +
  254 data (was 774 + 452). Flashed 2026-11-27, booted, no HardFault; the kit played on the unit, but Nonlinear froze
  it (the bug below, fixed on main and merged in at fe995d6).
- **Release image** (`build.py full` at fe995d6, kept as `build/HX_Effects_v3.80.0_NAM_Amps_Effects_AcousticKit_Fix.hxf`):
  MD5 bda07f1eae1f58a32e889eb5ad20a8ce, verified ALL OK; flashed 2026-11-27, booted, no HardFault.
  `web/recipe-full.bin` is made from it (`tools/recipe.py apply` reproduces the MD5). Released as v1.1.0.
- Still to do: Drum Chapel's cost (build_all's rule gives about 1,650 from 1,361 words; the image still declares 1,550), user kits, the preset
  builder's catalogue (regenerate fw-catalog.js from the new full build for Groove's User entry).
## 2026-11-27: Nonlinear froze the DSP (fixed: Drum Chapel's hook moved from 0x23ac to 0x104)

- **The bug** (in every full image with Drum Chapel, v1.0.0 included): selecting Reverb → Nonlinear, even alone in a
  preset, made the DSP panic (`SPI[0]: Got panic indicator! PC:0x00000000` / `0xFFFFFFFF`, then endless SPIComm
  errors; ARM fine, no HardFault). Logs: build/logs/*-freeze.log. Stock 3.80 plays Nonlinear.
- **Ruled out** (offline, verified): DSP memory overlap (the run-time PM heap H1 ends at 0xe3c81, 3,023 words below
  our Block 3 kernels), the moved Heap 6 (Simple Delay and Heliosphere use it and play), Nonlinear's graph, model,
  blob and primitive records (identical to stock), fixed addresses in its code. On the unit: Searchlights, Hot Springs,
  HX Room and Euclidean Delay (sharing some of its routines) play; the release without Drum Chapel plays Nonlinear.
- **The cause:** Drum Chapel hooked primitive 0x23ac. In stock, 0x23ac and 0x23ab are two modes of one routine
  (same shared function 0x60c08d); 0x23ab is used only by Nonlinear (sub-composite 0x6000c3). Replacing 0x23ac's
  record broke 0x23ab's use at run time (mechanism not traced). Only 8 unused primitives share no code with a used
  one: 0x87, 0x104, 0x105, 0x20f, 0x261a, 0x271d, 0x2aa8/0x2aaa (the last two used by the root graph). Drum Chapel now
  uses **0x104**. Image MD5 f18a5714defd3a6c43472d753e2fffde, verified ALL OK; on the unit 2026-11-27: Nonlinear
  alone, Drum Chapel alone and both together play. web/recipe-full.bin regenerated from it (applies to that MD5).
- **Still to check:** our other hooks also share routines with stock ones (Click and Geiger with 0x102/0x127, Puggy
  with 0x216, Bethblahem with 0x832, Corrupt with 0x814, Ottobit with 0x23aa, Greasy with 0x225); no problem seen,
  but the stock blocks using those routines should be tried with nothing else in the preset.
## 2026-11-27: input calibration, documentation only (branch `input-calibration`)

`STOMP_DBU = 11.5` (the dBu that reaches 0 dBFS, from users' measurements of a Helix Floor and an HX Stomp) stays as
it is: measuring it on the HX Effects needs a multimeter, which the user doesn't have, so Part C was cut to
documentation (user, 2026-11-27). Line 6 publishes no maximum input level for the HX Effects. The comment in
`tools/sharc/nam_lite.py` now says the figure is unmeasured here, that it assumes Input Level = Instrument, NAM's
definition of input_level_dbu, and how to measure it later (the probe image's meter, branch `probe-build`, with
`tools/input_level.py --volts`); `web/nam2ir-core.js` points at it; the README says what Input at 5.0 means. No
value, kernel or image changed.

## Don'ts

- Don't change the MD5 check to force another firmware through; every offset above is for 3.80.0.
- Don't commit anything from `firmware/` or `build/`; both are Line 6's firmware (the `.l6ia` too).
- Don't flash while HX Edit or Line 6 Updater is open (they hold the USB interface).
- Don't `sudo` anything in the home folder again (that's what broke `~/.config/git` and the venv).

## Meter results (2026-11-10)

Measured on the unit with the `--meter` image (cycles of about 150,000 a call): Ottobit alone 4,100-6,100;
Syntax alone 10,200-12,300; with Commander or Geiger unchanged; Syntax with Ottobit swapping 38,900-41,000.
One swap is about 28,000 cycles for about 1,100 words moved. The interface lock-ups with Syntax are
unexplained: Syntax + Geiger locks with no swap and no change in Syntax's time. The metered block must be
last in the chain or later blocks garble the beeps.

Build notes from that work: the overlay payload goes before the last model's table copy, so it stays right
before the final composite table whatever order the models come in. NAM's `DSP_COST` is in every image, so
the older proven MD5s (899f6904 NAM+Click+Geiger, a486dbed +Commander, e0a3f744 +Corrupt, 27b6dbf1 first
Doom Chug image) are 2700 builds. Rebuilt now they should differ only in that cost and Entry 0's checksum
(checked for the default image).

## Stock amps: working (2026-11-17, on `main` since aa3d5b4)

Solved in a separate repo (`~/hx-effects-stomp`, local only) and brought back here. The earlier attempts below
failed for five separate reasons, none of them guessed then: the block allocator sends amp types to a BIG path
that the HX Effects build left empty; only the DSP slots fx.13..fx.15 accept the amp containers, and the app tied
no block records to them; an amp registry was compiled for zero amps (the first selection failed, the next
overwrote memory); the placement limit was 0; and an amp-container model slot accepts only amps, so a takeover
of an effect block could never load. All five are fixed in `tools/amp_patch.py` (`runtime_changes`). Amps are
added under their own identities, with Table 1 moved into a fifth Entry 0 segment at 0x29000000 and an "Amps"
list under Distortion (`tools/amps_group.py`), so no stock block is replaced. The full story with addresses:
`docs/amps-findings.md`.

`build.py amps|full` end with `build_amps.py --set all --base-file <image> --base-check <its verifier>` and
`tools/verify_amps.py`; `build.py nam` stops before the amps. Each copies its final image to a plain name in build/.
Limits: three amps and preamps per preset together (placement limit patched to 3; the DSP has three amp slots,
fx.13..fx.15; preamps are amp-type blocks, 0x11). No cabs (the user dropped them: legacy cabs need the cab limit and unstudied
screens, new-style cabs need the Stomp's 54 MB cab package, absent here). The images keep the USB memory window
(`tools/memwin.py`). On the unit (2026-11-17): the NAM + Click + amps image (MD5 e2162bcaf9d295612c24ebe1161c7df0,
what `build.py amps` made before the preamps) played NAM, an amp after it and Click; all 111 amps loaded on the
stock-based image. The full + amps image (MD5 edd48969de189b3686bcb8bdfc5f2e93) was flashed on 2026-11-17 and boots: no fault, the same boot-log lines as the NAM + amps image; the user's test the same day: "All played" (the effects, NAM and amps). Its log: 367 model changes, all successful, presets saved, no fault. New in this log only: 34 lines `UNKNOWN FOOTSWITCH MODE 11` + `app.c:1624 ERROR_INVALID_PARAMETER` in one burst after a model change; the message is in the HX Effects' own footswitch code (not in the Stomp's); cause not looked into.

**Preamps (2026-11-17, user asked):** `build_amps.py --preamps all` adds every preamp the HX Stomp lists (112:
94 guitar, 17 bass, 1 mic "Studio Tube Pre"; `tools/preamp_list.py`, written by `re/stomp_amps.py` from the Stomp's
Preamp category 13) as an "EQ → Preamps" list: Distortion already has the four lists the menu allows, so the
preamps take EQ's third list slot (stock EQ has 2 lists and an unused third slot already named "Legacy", renamed).
Their Table 1 rows follow the amps' in the same segment (689 rows), their items follow the Amps items. Same
container and type (0x11) as the amps, so the three-per-preset limit covers both; names are the Stomp's (each the
same as its amp). Every preamp fits the amp container (largest 1350 DM / 506 PM / 154 members). verify_amps.py checks
it all (rows against the Stomp's Table 1, the EQ menu, the three-list EQ view emulated, DSP fit); the amps-only
image still comes out byte-identical (e2162bca). On the unit: full + preamps (a27dfedaff7a803b7f92ccae6b3b8b60)
flashed 2026-11-17, boots, no fault, boot errors unchanged; user: "All played"; log 69 model changes, all
successful, zero errors. The Stomp firmware is now also in this repo's (ignored) firmware/ for the cross-check.

## Stock amps: tried and dropped (2026-11-11 to 13)

The firmware holds all 224 of Line 6's amp and preamp models with every DSP primitive they need, but no Table 1
row, so the app never lists them. What was tried, all as takeovers of stock mono distortions (the amp's own
parameters, states and graph blob; no new code):

- **As effect blocks** (inside FxHarnessMono 0x600005, placeholder 0x6000c4: DM 907, PM 334): US Small Tweed (DM 410)
  and Agua 51 (629) played; Divided Duo (816), Line 6 2204 Mod (833), Tweed Blues (846) and Moo)))n Jump (1013) were
  silent and locked the interface. US Small Tweed was in the committed default (8107954).
- **As amp blocks:** the harness is chosen only by the block type at block+0x28 (tbh at 0x280f3ee0; 0x11 ->
  HD2_AppAmpHarness, placeholder DM 0x596, PM 0x1fa). The placement check at 0x280f221c refuses amp blocks above a
  per-DSP limit of 0 (`cmp r3,#0` at 0x280f2296); patched to 1 (`01 2b`) with the browser item type set to 0x11.
  Tweed Blues Brt on the Arbitrator Fuzz (image a3b295be) played, saved, recalled and bypassed on 2026-11-12.
  Every other amp then locked the screen the moment it was reached in the browser (the previous block stays shown):
  EV Panama Red, Archetype Lead (on Valve Driver, Industrial Fuzz), US Double Nrm (on Hedgehog D9 and on the
  Arbitrator itself, alone). Not size, link count, knob names, host block, amp count or the moved effects. Finally the
  byte-identical a3b295be crashed on Tweed Blues too, in an empty preset: something on the unit (settings/presets
  surviving a flash?) changed after the first success. Unresolved; the user dropped the idea. A global-settings reset
  and a retest of a3b295be was the next suggested step.
- Costs: the HX Stomp 3.80 Table 1 (Stomp Entry 0, rows from offset 0x28657, unaligned) has every amp's cost; the
  two units agree on all 463 shared models (about 75 units per Benvesco percent).

The code (STOCK_AMPS, `patch_amp.effects_allow_amps`, browser btype, verify checks) was removed; the effect-block
version is in commit 8107954 (the amp-block version was never committed). Its US Small Tweed default is reverted: the default image is the
no-amp one again (7b291b5f…).

