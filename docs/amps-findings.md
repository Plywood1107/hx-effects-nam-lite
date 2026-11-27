# Findings

HX Effects 3.80.0 (`HX_Effects_v3.80.0_0xd97239907.hxf`, MD5 `7c2ebdf1bffb6bcc5f89dda97f91e40c`) against HX
Stomp 3.80.0 (`HX_Stomp_v3.80.0_0x103966115.hxf`). Addresses are virtual addresses in the HX Effects' Entry 0
(the ARM application) unless said otherwise. "Verified" means `re/survey.py` checks it; "from nam-lite" means it
was established in the earlier project and has not been re-derived here.

## The two firmwares

- Both are L6IA archives: the Effects has 14 entries, the Stomp 15. No entry but a 132-byte one is identical:
  they are different builds of the same code base.
- Same processor family and memory map (NXP LPC43xx): segments load at 0x10000000 and 0x20000000 (internal RAM)
  and 0x28000000 (external RAM, the main code). The Effects' Entry 0 segments: file 0x40 → 0x10000000 (0xd6f0
  bytes), 0xd73c → 0x100870e0 (0x1f78), 0xf6c0 → 0x28000000 (0x115670), 0x124d3c → 0x20000000 (0x667c).
- From nam-lite: Entry 2 is the SHARC DSP's boot stream, Entry 3 the model table (815 models, of which 224 are
  amps and preamps), Entry 4 the DSP graph library. Every DSP primitive the amps use is in the Effects' boot
  stream, with the same record sizes as the Stomp's.

## The Effects app is a debug-rich build (verified)

- It contains `DEBUG ASSERT Failed: file / line / message`, source paths (`dspManager.c`, `dspSlot.c`,
  `dspResourceManager.c`, `fsModelListUI.c`, ...), and hundreds of `INFO:` / `ATTN:` / `ALERT:` log lines,
  among them `ALERT: POOL is drained!!!`, `ALERT: memmgr_alloc IS OUT OF MEMORY!!!` and
  `ERROR: SPI[%d]: Got panic indicator! PC:0x%08X` (the ARM notices when the DSP itself panics). The Stomp app
  has none of these strings.
- **The assert routine does not stop the app.** `assert(file, line, msg)` at 0x10002068 loads the format string
  (0x1000202c) and tail-calls a veneer at 0x1000d6e8, which jumps to the logger at 0x280d2f74. The logger formats
  the line (0x28115340) and, if a flag byte is set, writes it out (0x281154d0), then returns. So a frozen screen
  is a hang or a processor fault further on, not an assert halting.
- The log sink is SEGGER RTT, a ring buffer in RAM meant for a hardware debugger (verified):
  - The logger calls `SEGGER_RTT_vprintf(1, fmt, args)` (0x1000d304), then `SEGGER_RTT_WriteString(1, "\r\n")`
    (0x1000d134) when the byte at 0x280d30f4 is set (it is 1 in the image). Logging is always on.
  - The control block `_SEGGER_RTT` is at 0x10087760 (internal RAM), set up by the init at 0x1000d020: three up and
    three down channels; channel 0 ("Terminal") has only a 4-byte buffer.
  - Channel 1, "SEGGER RTT LOG", is configured at 0x280e6d54: **a 64 KB buffer (0x10000 bytes) at 0x282ae37c**,
    flags 0. Its descriptor is at control block +0x30: name, buffer, size, **write offset at 0x1008779c**, read
    offset at 0x100877a0, flags at 0x100877a4.
  - Flags 0 is "skip when full": with no debugger reading, the read offset never moves, so the buffer keeps the
    **first** 64 KB logged since boot and every later line is dropped. A logging build has to move the read offset
    itself (or reset both offsets) to keep the latest lines instead.
  - Not yet established: whether anything in the app reads the buffer back, and how quickly it fills.
- There is also a factory self-test screen (`./src/test/sq.c`: `DSP Gain:`, `USB Test:`, `CapSenThresh:` ...).

## Two cores, and what a fault does (verified)

- The application runs on both cores of the LPC43xx. The **main core** (Cortex-M4; vector table at 0x10000000, set
  by the reset code at 0x100000e4, which also clears the bss at 0x10080270..0x100850d8 and 0x28115670..0x282be37c)
  runs the user interface and talks to the DSP. The **USB core** (Cortex-M0; its own 26 KB image at 0x20000000,
  stack top 0x2000c000, bss 0x20006800..0x20009b78) runs USB with its own small RTOS. Both see the same memory.
- **A HardFault on the main core ends in an endless loop.** The vector (0x100001b4) picks the stack in use and
  jumps to 0x280d391c, which copies the eight stacked registers to its own stack and then executes `b .` at
  0x280d393e. The NMI, MemManage, BusFault and UsageFault handlers are `bkpt; b .`. There is no watchdog reset.
  This matches the symptom exactly: the screen and switches die, the DSP keeps playing the last preset, and
  nothing is shown.
- The USB core's assert routines are empty (`bx lr` at 0x20004354 and 0x20004358), so the source-file-name
  strings in its image (0x200054d0..0x200056cb) are dead data.
- The USB core's bulk receive thread (0x2000366c, state at 0x200087a0: endpoints 0x81/0x01, 512-byte packets,
  receive buffer 0x20008bbc) reads each packet from the host a byte at a time and passes it to the main core with
  `bl 0x20002e24` (channel 3, at 0x200036ae for a full packet and 0x200036c8 for a short one). Data from the main
  core comes back through the callback at 0x200036d0, which calls the USB write routine 0x20000d44 (endpoint,
  pointer, length; it sends straight from the pointer in max-packet chunks). Endpoints are opened only here.
  `tools/flash.py` uses this same endpoint pair.

## The memory window (built, verified offline, not yet run on the unit)

`tools/memwin_patch.py`: 139 bytes changed in Entry 0, nothing else in the firmware.

- The two `bl 0x20002e24` in the bulk thread go to a 27-instruction stub written over the dead strings at
  0x200055e8. A packet starting `PEEK addr len` makes the USB core send that memory to the host; `POKE addr value`
  stores a word and echoes `POKE`; everything else is passed on as before.
- The HardFault handler at 0x280d391c now stores a record at 0x200054d0 (frame address, CFSR, HFSR, MMFAR, BFAR,
  EXC_RETURN) and then loops as before. The record area is zeroed in the image, so a non-zero first word means a
  fault has happened since power-up.
- `tools/memwin.py` is the computer side: `check`, `log` (reads the RTT log and moves the read offset up, as a
  debugger would, so the app keeps logging), `fault`, `peek`, `poke`.
- `tools/verify_memwin.py` (20 checks, ALL OK): only the listed bytes differ from stock; the code disassembles as
  written; the bulk thread, emulated with unicorn on stock and patched images, passes ordinary packets on
  identically and answers PEEK and POKE; the emulated HardFault handler writes the record and reaches its loop.
- **On the unit (2026-11-16, image MD5 3e2f8779a536fa813cddca83a6b04770): it works.** The unit booted, answered the
  flasher's normal traffic through the stub, and `memwin.py check` read the control block (id `SEGGER RTT`, buffer
  65536 bytes). No fault recorded. Still to see: USB staying alive while the main core is in its fault loop.

## What the log looks like (first read, 2026-11-16)

- 5,703 bytes from power-up to idle, so the 64 KB buffer does **not** fill during a normal boot; lines are only
  lost after a lot of activity with nobody reading.
- Errors are logged as a trace of source positions, innermost first:
  `ERROR: origin at <file>:<line>: <ERROR_NAME> (<code>)` followed by `ERROR: check at <file>:<line>` for each
  caller that passed the error up. Example from this boot (a preset saved under the NAM firmware, which stock
  cannot load): origin `helix-core-lib/HelixCore/lib/helix/src/app/appDspObject.c:1409: ERROR_INVALID_PARAMETER (-3)`,
  then checks in `appDspObject.c`, `HelixCoreInternal.c`, `HelixCore.c`, `presetSerializer.c`, ending
  `WARNING: hdiu_loadPresetFile <name> failed with error: -3`. So a block the app cannot build normally produces
  an error trace and a failed load, not a crash.
- Block creation is logged: `INFO: alloc block for LITTLE FX model called...` /
  `INFO: alloced LITTLE block 282A3528 for LITTLE FX model` (also `LITTLE IR_MONO_1024`). "LITTLE" suggests there
  is a "BIG" kind too, presumably what an amp block asks for; not yet seen.
- Also at boot: an SD/MMC driver error (`sdmmcDev.c:716`, the unit has no card), global-parameter init, setlist and
  preset loading with timings, `INFO: background model caching has BEGUN`, and the USB connection being accepted.

## Amps in the Effects app

- Block-type names in the app: `AMP`, `AMP_CAB`, `CAB_SINGLE`, `CAB_DUAL`, `AMP_IR_CAB`, `IR_CAB_SINGLE`,
  `IR_CAB_DUAL` (verified). The browser category names `Amp`, `Preamp`, `Cab`, `Amp+Cab` exist only in the Stomp
  app (verified).
- The placement check at 0x280f221c reads three per-DSP counters and refuses a block that would exceed a limit
  (verified): amp blocks at dsp+0xae8, limit 0 (`cmp r3, #0` at 0x280f2296); cab blocks at dsp+0xae4, limit 0;
  IR blocks at dsp+0xae0, limit 2. Which counter is amps and which cabs is from nam-lite's reading of the code.
- From nam-lite: the harness (the container graph a block runs in) is chosen only by the block type at block+0x28
  (jump table at 0x280f3ee0): 0x11 → `HD2_AppAmpHarness` (room for DM 0x596, PM 0x1fa words), 0x12 amp+cab,
  0x21 amp+cab+IR, 0x01..0x07 and 0x17..0x1e the mono and stereo effect harnesses (mono: DM 907, PM 334).

## The block menu (verified)

- 13 categories × 4 sub-list slots = 52 list slots (pointer table and count table, `EFFECTS_E0.BLIST_PTR_TAB` /
  `BLIST_CNT_TAB` in `tools/patch_amp.py`). Each list item is 48 bytes: block type (u32), model name index
  (u32), ..., display name at +14.
- The fourth slot of every category is empty, and some categories have two free: 19 empty slots (3, 7, 10, 11,
  15, 19, 23, 27, 31, 34, 35, 38, 39, 42, 43, 46, 47, 50, 51). Not yet established: whether the app shows a
  fourth sub-list when it is filled, and how it would be labelled.
- Table 1, the placeable blocks ({name index, preset id, 0, DSP cost}, 12 bytes a row): 465 rows at 0x28101084,
  packed up to 0x28102650, where a table of seven harness names follows. The Stomp's has 823 rows. Adding rows
  means moving the table and repointing every reference; the references have not been counted.
- Table 2 (44-byte rows, 777 of them at 0x280bd8fc) already has a row for every amp.

## Why an amp block fails (2026-11-16): the HX Effects build has no BIG blocks

Test: image MD5 db15fa36eb73886a22a0555afa7808aa (stock + memory window + Tweed Blues Brt on the mono Arbitrator
Fuzz as an amp block, amp limit 1), empty preset, Distortion > Mono > Tweed Blues Brt. On the unit: the name showed
briefly, the selection jumped to the neighbouring Swedish Chainsaw, and afterwards turning knobs made other blocks
produce modem-like noise. No HardFault was recorded; USB and the memory window kept working. The log
(build/logs/amp-tweed-1-select.log), each time the amp was reached:

    INFO: alloc block for BIG AMP model called...
    INFO: out of BIG blocks for BIG models, will attempt LITTLE block eviction...
    ALERT: flow 0 big/little slots full!!! Block type 672077888 allocation FAILED!!!
    ERROR: origin at .../helix/src/app/appDspFlow.c:2302: ERROR_NOT_ENOUGH_RESOURCES (-19)
    ERROR:    check at .../app/appDspObject.c:3497, :5070
    appDspObject_restoreBlock ERROR_NOT_ENOUGH_RESOURCES for: ... block type is 17 ... slot[0] symbol is 0x285
    ERROR:    check at HelixCoreInternal.c:6986, :3177, HelixCore.c:1114

and after that even ordinary blocks fail (`alloced LITTLE block ...` followed by `appDspFlow.c:2244:
ERROR_NOT_ENOUGH_RESOURCES`), which is the state the noises come from. (672077888 = 0x280f1840 is a pointer printed
with %d: the block-type name.)

The code (verified by `re/survey.py`): the block allocator at 0x280ed3ec takes the flow and the block type.
Types 0x10..0x12 and 0x21 (the amp types) take a "BIG" path; every other type takes the "LITTLE" path, which hands
out one of [flow+0xb14] slots of 0x9f4 bytes starting at flow+0xb40. **In this build the BIG path contains no
allocation at all**: it logs the three lines above and returns 0. There is no BIG pool and no eviction code; the
HX Effects was compiled with zero BIG blocks. So an amp-type block can never be created by this firmware,
whatever the tables say, and the failure leaves the signal flow in a broken state.

What this means for the earlier history: the application code was the same in every nam-lite amp image, so the
amp-type Tweed Blues Brt that "played" on 2026-11-12 cannot have been allocated either. Most likely the selection
failed in the same way and what was heard was the signal path without the amp (or with a neighbouring block), and
the later freezes were the same broken state ending in a HardFault. That is an inference; the 2026-11-12 run was
not logged.

Not yet known: what a BIG block is in the Stomp build (its size, what it holds beyond a LITTLE one), and therefore
whether an amp could be run in a LITTLE slot, or a BIG pool added.

## BIG and LITTLE blocks (phase 2 study, 2026-11-16; verified by `re/survey.py`)

- **The HX Stomp's allocator** is at 0x28df4d24 in its app and has the same shape. Its flow holds eight block
  records in one array: five LITTLE ones from flow+0xaf0 and three BIG ones straight after (flow+0x3cb4, +0x46a8,
  +0x509c). **All eight are the same 0x9f4-byte record with the same layout** (in-use flag at +0x24, and so on).
  An effect asks for a LITTLE record and falls back to a free BIG one; an amp asks for a BIG one and, if all three
  hold effects, the allocator moves one effect to a LITTLE record ("eviction") to free a BIG one. So on the
  application side BIG and LITTLE are not different kinds of memory: they are a quota. 5 + 3 = 8 is the Stomp's
  block limit; at most three of the eight may be amp-type.
- **The HX Effects' flow** (set up at 0x280f1060) is 0x6ec8 bytes = 0xb40 + ten 0x9f4-byte records, of which the
  caller's count (nine, the unit's block limit) are used, all LITTLE. Each record is tied to a DSP object named
  `fx.0` .. `fx.8`, which is given the container `HD2_AppFxHarnessMono` and its `modelSlot` at start-up. The
  containers are swapped per block at run time (the earlier finding: block type 0x11 selects `HD2_AppAmpHarness`).
- **What the quota is most likely protecting is DSP memory.** The containers declare (DM, PM words): effect mono
  917 / 339, effect stereo 942 / 486, amp 1438 / 511, amp+cab 1884 / 780, amp+cab+IR 1466 / 527. An amp container
  needs about one and a half times an effect container's DM. Nine effect-sized blocks are what the HX Effects'
  DSP memory was budgeted for; whether there is room for a larger container in one of the nine has not been
  established, and nothing found so far says how the DSP reserves that memory (per block in advance, or on demand).
- No other difference between BIG and LITTLE records was found in the Stomp's allocator: both get the same
  set-up call and the same fields.

**The experiment this suggests** (`build_amp.py --alloc little`, built and verified, not flashed): the two
branches in the HX Effects allocator that send amp types to the failing BIG path become nops (0x280ed3f8,
0x280ed3fc), so an amp takes an ordinary record. The record itself is right for an amp, on the Stomp's evidence.
What happens next is the open question: the app will ask the DSP for the amp container in `fx.N`, and either it
fits (the amp plays), or the DSP or the app reports an error, or something faults. The log and the fault record
will show which.

## The DSP slots fx.13 to fx.15 (2026-11-16; verified by `re/survey.py`)

Test 2 (`build_amp.py --alloc little`, image MD5 f78b8bb60a72397d61b344aaaf6f1fd5): the amp now got a block record
(`INFO: alloced LITTLE block 282A3528 for LITTLE AMP model`), and the failure moved on:

    ERROR: origin at .../PODPlay/mcu/src/dsp/dspManager.c:719: ERROR_NOT_FOUND (-21)
    ERROR:    check at .../app/appDspObject.c:2793, :3506, :5070, HelixCoreInternal.c:6986, :3177, HelixCore.c:1114

On the unit: the amp was not loaded and could be scrolled past; no noise, no freeze, no fault. The app recovered.

What failed: `appDspObject.c:2793` is the call at 0x280f3f64, which asks the block's DSP slot for the container the
block type needs (0xf1d `HD2_AppAmpHarness` for type 0x11). The lookup (0x1000a048) walks **a list of the models
the slot accepts** and did not find it. Those lists are the "group" table of Entry 3 (header words 8 and 9: 121
records of 8 words; word 2 the slot's name, words 5 and 6 the count and offset of a list of model indices). Read
from the stock HX Effects file:

- The DSP application has sixteen block slots, `fx.0` .. `fx.15`, **in both firmwares**.
- `fx.0` .. `fx.12` accept the mono and stereo effect containers and the single-cab container.
- **`fx.13`, `fx.14`, `fx.15` also accept `HD2_AppAmpHarness`, `HD2_AppAmpCabHarness`, `HD2_AppAmpCabIRHarness` and
  the dual-cab container.** These are the BIG slots, present in the HX Effects' own data.
- The HX Effects app ties its nine block records to `fx.0` .. `fx.8` (the table at 0x280f1a18 and the `movw` at
  0x280f116c). The HX Stomp app has a slot table starting `fx.13, fx.14, fx.15` (0x28e3db24): its three BIG
  records are those slots.
- Containers have lists too. `HD2_AppFxHarnessMono`'s `modelSlot` accepts 277 models, all effects.
  `HD2_AppAmpHarness`'s `modelSlot` accepts 225 models, the amps and preamps, and no effect. **So a takeover (an
  effect's identity carrying an amp's graph) can never be loaded into the amp container**, and an amp model
  cannot be loaded into the effect container by name either. That closes the takeover route for amp blocks.
- Menu items (48 bytes): +0 block type, +4 the model's name index, +8 a second name index (0xffffffff if none;
  the cab of an amp+cab item), +12 the preset id (u16, the same as in Table 1), +14 the display name.
  Table 1 is not sorted, so it is searched linearly. The HX Stomp's Table 1 gives Tweed Blues Brt preset id 37,
  which is unused on the HX Effects (ids 75..814).
- Live, over the memory window: the flow is at 0x282a29e8 on the unit; [flow+0xb10] = 9, [flow+0xb14] = 9.

**Test 3, built and verified, not flashed** (`build_real.py`, `tools/verify_real.py`): the amp under its own
identity, with **no change to Entry 3**. The Arbitrator Fuzz's Table 1 row and menu item become Tweed Blues
Brt's (name index 3290, preset id 37, type 0x11); block records 6, 7, 8 are tied to `fx.13`, `fx.14`, `fx.15`; the
allocator's amp path takes a free record among those three (emulated: effects still fill from record 0; amps take
6, 7, 8; a fourth is refused); the amp limit is 1. Still unknown until it runs: whether the HX Effects' DSP
program really provides `fx.13`..`fx.15` with their memory, as its data says.

## Test 3: the amp runs (2026-11-16)

Image MD5 c14bab01cefc88542a512b8e1bde67cf (`build_real.py`). The boot log was the same as before (no new errors:
tying records 6..8 to `fx.13`..`fx.15` and giving them the effect container at start-up worked). In an empty preset
the user selected Distortion > Mono > Tweed Blues Brt and reported that it plays. Confirmed from the unit:

- Log: `INFO: alloced LITTLE block 282A70E0 for LITTLE AMP model` then `INFO: hci_didSetModel 1 called`, the same
  success line an ordinary effect gets. 0x282a70e0 is record 6 (0x282a3528 + 6 * 0x9f4), the one tied to `fx.13`.
- Memory, read live: record 6 has +0x24 = 3 (in use), +0x28 = 0x11 (block type AMP), +0x2c = 0xf1d
  (`HD2_AppAmpHarness`), and 0xcda (name index 3290, `HD2_AmpTweedBluesBrt`) with 12 parameters further in.
- No HardFault recorded.

So the HX Effects' DSP does provide the amp-capable slots, and a real amp model runs in the amp container there.

**One failure to explain:** the first time the selection reached the amp, it failed and the app recovered:

    INFO: alloced LITTLE block 282A70E0 for LITTLE AMP model
    ERROR: origin at .../helix/src/app/appDsp.c:609: ERROR_NOT_ENOUGH_RESOURCES (-19)
    ERROR:    check at .../app/appDspObject.c:3526, :5070 ... (restoreBlock, block type 17, slot[0] symbol 0xCDA)

The next model in the list then loaded normally, and on coming back to the amp it loaded (the user saw exactly
that). Traced, below.

### The amp registry (verified in `tools/verify_real.py` and live)

`appDsp.c:609` is in the function at 0x280f9118 (context, block id, pointer to the block type). For amp types (0x11,
0x12, 0x21) it keeps a list of block ids: the list at dsp+0x6ec8, its count in the byte at dsp+0x6ecc. If the id is
already listed it returns 0. Otherwise it appends the id, increments the count, and **fails with
ERROR_NOT_ENOUGH_RESOURCES whenever the count is then not 0**: the build's maximum is zero. That explains the
behaviour exactly: the first attempt registers the id and fails; the second finds the id and succeeds. Read live
after the test: [dsp+0x6ec8] = 9 (the id in the log's `DSP_MODEL: id is 9`), [dsp+0x6ecc] = 1.

It is also a memory hazard. The list has room for one word before the count byte, and the removal code (0x280f969c)
does not shrink the list, it stores the found index into the first entry. So after the amp block is removed, the
next amp selection does not find its id, appends at index 1, which is the count byte itself, and from then on every
attempt fails and writes one more word further into the fields that follow. A power cycle clears it.

Nothing else in the build reads the list (the only other references are the start-up zeroing at 0x280f931c and the
removal). **Fix, in `build_real.py` from 2026-11-16: the function becomes `movs r0, #0; bx lr`** (image MD5
0a758a43fd45abd8d9816b893d8e62f0, verify_real.py ALL OK, not yet flashed).

### With the registry fix (image MD5 0a758a43fd45abd8d9816b893d8e62f0, 2026-11-16)

The user ran, and reported all working: the amp loads on the first try; changing the block to another effect and
back, several times; Drive and Master; a cab IR after it; bypass and back; save the preset, switch to another, and
return. The log for the whole sitting (build/logs/real-2-checks.log) has **no error line**: four
`alloced LITTLE block ... for LITTLE AMP model` (three selections and the preset recall), the preset saved
(`Sym preset ... saved with result 0`, `Raw preset ... saved with result 0`), another preset loaded and the amp
preset loaded again with its IR block. No HardFault; the registry words at dsp+0x6ec8 stayed 0.

Power cycle with the amp preset as the start-up preset (same image): boots normally; the boot log shows the preset
loading with `alloced LITTLE block 282A70E0 for LITTLE AMP model`, then its IR block, `hci_didLoadPresetFlow 0`,
175 ms, no error. A second Tweed Blues Brt in the same preset was refused, as the placement check's limit of 1
says it should be (so the amp counter at dsp+0xae8 is kept correctly).

Limit raised to 3, one per amp-capable slot (`REAL_AMP_LIMIT`, image MD5 fb6eb3816b9d69b8e32933414fc79da4,
verify_real.py ALL OK, not yet flashed).

**Three amps at once (image MD5 fb6eb3816b9d69b8e32933414fc79da4, 2026-11-16):** the unit booted with the amp preset
(amp in record 6). The user added a second and a third Tweed Blues Brt and reported all working. Log
(build/logs/real-3-checks.log): `alloced LITTLE block 282A7AD4 for LITTLE AMP model` (record 7) and
`... 282A84C8 ...` (record 8), each followed by `hci_didSetModel`; no error line; no HardFault. So all three
amp-capable slots carry an amp at the same time, and the DSP budget allowed three at a cost of 2324 each.

Not yet tested (the log of that sitting shows no preset with seven or more effects, although it was asked for):
effects in records 6..8, a full nine-block preset, snapshots, the amp on the lower path of a split, a fourth amp
being refused cleanly.

## Phase 3: an Amps group under Distortion (2026-11-16; `re/survey.py` section 10, `tools/verify_amps.py`)

**The menu.** 13 categories, each with four list slots: 52 list pointers at 0x2810021c and 52 counts at 0x2810030c.
The number of lists per category is at 0x281003e4 (Distortion 3: Mono, Stereo, Legacy) and the list names are
26-byte fields at 0x281004e8, four per category; the fourth is empty in every category. So a fourth list under
Distortion needs its pointer, its count, the category's list count 3 -> 4, and a name. Not known until it runs:
whether the screen shows a fourth list.

**Table 1** (`appDspUsageTable` in the app's strings: {name index, preset id, 0, DSP cost}, 465 rows). Every user:
the start-up routine at 0x28100b20 fills a preset-id -> name map (833 entries at 0x282a1978) and then **sorts the
table in place** by name index (0x28100a30); two binary searches (name -> cost at 0x28100bcc, name -> preset id at
0x28100d2c); a count routine (0x28100b5c) and a row routine (0x28100b64) used by the background model caching
(0x280f8dd8). Its address is in five literals and nowhere else; its end is the literal at 0x28100b54 (which is also
the address of the seven-container list that follows the stock table); its size is in four instructions. (The
"count instructions" listed in tools/patch_amp.py at 0x2808d4ca, 0x280c8032, 0x280d7046 and 0x280e6aac are line
numbers in error calls, not table sizes; hx-effects-nam-lite never changed them.)

**Room.** Entry 1 is the boot stage ("Booting", "Boot Error", runs from flash at 0x14000000 and from RAM at
0x29ff0000). Its loader (0x1400131a) reads as many segments as Entry 0's header declares; each destination is
checked by 0x14000f4c, which accepts 0x10000000..0x1001fffe, 0x10080000..0x10091ffe, 0x18000000..0x180047fe,
0x20000000..0x2000fffe and 0x28000000 upwards; the image must be at most 4 MB. Sampled live over the memory
window: the app's bss ends at 0x282be37c, where the model table (Entry 3) is loaded; more loaded data follows up
to about 0x283f0000; **from there to the boot stage's remains at 0x29ff0000 the SDRAM still holds power-up noise
after hours of use.** So a fifth segment at 0x29000000 sits in memory nothing uses.

**The image** (`build_amps.py`, not yet flashed): Table 1 moved into that segment as 465 stock rows plus one row
per amp (the HX Stomp's own preset id and cost), followed by the Amps menu items; the app's references repointed;
Distortion's fourth list filled and named "Amps"; plus the changes that let amp blocks run. Entry 3 untouched,
Arbitrator Fuzz back to stock, Entry 0 grows by 5,652 bytes. `tools/verify_amps.py` runs the app's own start-up
routine and both searches in an emulator on the stock and on the new image: all 465 stock blocks resolve to their
stock cost and preset id, the amp resolves, an unknown name still fails.

**On the unit (image MD5 4f9b9e45d4508b01269cfa8db5357767, 2026-11-16):** the flash was accepted (Entry 0 5,652
bytes larger, five segments) and the unit booted. Boot log as before, no new error; the saved amp preset loaded at
start-up, so the preset-id map built from the moved table works. Read back live: the sorted table at 0x29000000,
the Amps item at 0x290015d8, "Amps" in the name field at 0x28100536, Distortion's list count 4, and the app's own
availability mask for Distortion = 0x0f (0x282ae334 + 4 * 2: all four lists usable). The user: a fourth list
appears under Distortion, Tweed Blues Brt is in it and plays. **But the fourth list is labelled "Stereo", not
"Amps".**

Where list names are used (all through 0x28110228 -> 0x280fa7dc, which returns the 26-byte field for (category,
list); categories count from None = 0, so Distortion is 2): three screens fetch the name of the list a model is in
and compare its first letters with "Ster" and "Lega" to pick an icon or tag (0x2807ac0e, 0x2807c50c, 0x28082d32);
the model-list view (0x2807b8c0) draws three positions and fetches a name per position, stepping to the
neighbouring list with 0x2811041c (a test of the availability mask). 
**Why the fourth list read "Stereo" (found 2026-11-16, reproduced in `tools/verify_amps.py` section 5b).** The
user's description: page one Mono, Stereo, Legacy; then a second screen with "Stereo" (selectable, holding the amp)
followed by "Stereo" and "Legacy" (not selectable). The list view (drawn by 0x2807b6f4, three positions, loop at
0x2807b8c0) already slides: the position with the highlight shows the current list, earlier positions the
previous lists, later ones the next. The handler that moves to the next list (0x2809f11c) lets the highlight
position (view + 0x27) rise to "number of lists - 1", and the code that opens the view on a block's list
(0x2809f5c0, 0x2809fb22) sets it to the list index. With three lists that never exceeds 2. With four it becomes
3, a position that is not drawn, and the three drawn positions are computed as "two before, two before, one
before" the highlight: Stereo, Stereo, Legacy. Emulating the stock handler and draw loop on four lists gives
exactly that.

**Fix** (in `tools/amps_group.py`, image MD5 2e4ad70620c86144ba111e2b6ea703dc, verify_amps.py ALL OK; flashed
2026-11-17 and confirmed on the unit: the fourth list reads "Amps"): the highlight is capped at position 2 in all three places (the limit at 0x2809f172; a 7-instruction
routine, placed over a log string the allocator change leaves unused, called from the two open sites). Emulated:
the first three lists show Mono, Stereo, Legacy with the highlight moving 0, 1, 2; the fourth shows Stereo,
Legacy, Amps with the highlight on Amps; going back retraces it; three-list and two-list categories behave
exactly as on stock code.

Still open: the background model caching with one more row (no error seen in the boot log).

### Fifteen amps (2026-11-17, `build_amps.py --set fifteen`; all fifteen play on the unit)

The user's list, in the user's order, each under its own identity with the HX Stomp's preset id and DSP cost
(read from the Stomp's Table 1, 823 rows at 0x28017988; `tools/verify_amps.py` re-checks each row):

| Amp | Model | Preset id | Cost | DM / PM words, members |
|---|---|---|---|---|
| US Small Tweed | HD2_AmpUSSmallTweed | 43 | 1209 | 410 / 172, 54 |
| US Double Nrm | HD2_AmpUSDoubleNrm | 41 | 2324 | 759 / 283, 89 |
| Tweed Blues Brt | HD2_AmpTweedBluesBrt | 37 | 2324 | 846 / 265, 86 |
| WhoWatt 100 | HD2_AmpWhoWatt100 | 44 | 2629 | 901 / 325, 94 |
| Cartographer | HD2_AmpCartographer | 484 | 2550 | 951 / 324, 101 |
| Moo)))n Jump | HD2_AmpMoonJump | 667 | 2850 | 1013 / 326, 102 |
| Mandarin Rocker | HD2_AmpMandarinRocker | 618 | 2875 | 931 / 320, 99 |
| Brit 2203 | HD2_AmpBrit2203 | 787 | 2800 | 952 / 335, 104 |
| Placater Dirty | HD2_AmpPlacaterDirty | 500 | 2800 | 958 / 345, 100 |
| Brit Plexi Jump | HD2_AmpBritPlexiJump | 16 | 3092 | 1205 / 390, 111 |
| Archetype Lead | HD2_AmpArchetypeLead | 336 | 2550 | 913 / 323, 94 |
| EV Panama Red | HD2_AmpEVPanamaRed | 823 | 3700 | 1238 / 458, 135 |
| Line 6 Badonk | HD2_AmpLine6Badonk | 349 | 1625 | 615 / 197, 53 |
| Mandarin Bass 200 | HD2_AmpMandarinBass200 | 789 | 2200 | 741 / 245, 80 |
| Ampeg SVT-4 PRO | HD2_AmpSVT4Pro | 519 | 1650 | 504 / 199, 47 |

Checked offline for every one (verified):
- Its model, parameters and states are in the Effects' Entry 3, identical in number and type to the Stomp's; it
  has a Table 2 row in the Effects app; its preset id and name index are used by no stock Effects block; the
  highest preset id, 823, is inside the 833-entry preset-id map.
- Its DSP graph in the Effects' Entry 4 has the same memory need and the same set of DSP routines as in the
  Stomp's, and every routine is in the Effects' DSP program (Entry 2's routine table).
- It fits the amp container's model slot (HD2_AppAmpHarness: 1430 DM words, 506 PM words, 154 members; the same
  figures as the Stomp's container). The largest is EV Panama Red at 1238 / 458 / 135. Tweed Blues Brt, the only
  one run on the unit so far, is 846 / 265 / 86.

Not known until it runs: whether the fourteen that have never run on this unit do (they use DSP routines Tweed
Blues Brt does not), and what the unit's DSP cost budget makes of the dearest ones next to other blocks.
Table 1 has 480 rows; the new segment is 6,480 bytes; Entry 0 grows by 6,492 bytes. Image MD5
d0511e2179a37b60c048526943b7f9b8, verify_amps.py ALL OK (which now also has section 7, the DSP-side checks).

**Flashed 2026-11-17 (107 s, boots).** Read back over the memory window: no fault record; the boot log's errors
are the same set as the one-amp image's boot. The running app has filled in every Amps item: a menu item's last
word (+44, zero in the file) holds the block's DSP cost in memory, on stock items too (Kinky Boost: 509), and all
fifteen amp items hold their Table 1 cost (1209, 2324, 2324, 2629, 2550, 2850, 2875, 2800, 2800, 3092, 2550, 3700,
1625, 2200, 1650). So the app's start-up pass over the menu finds every amp in the moved table (observed). This
is the "background model caching" left open above: it works with the added rows.

**All fifteen play (user's test, 2026-11-17).** The user stepped through the list in one block, playing and turning
a knob on each: every amp loaded and played. The log for the test (build/logs/2026-11-17_amps_fifteen_test.log)
has 17 model changes, each followed by the success line (`hci_didSetModel 1`), no ERROR or WARNING line, and no
fault record. The only other lines are the `mapHCChangeEvent cannot map hdEvent->detail=21` notices that every
earlier amp log has too. So the fourteen amps that had never run on this unit do, including the largest (EV
Panama Red). Not yet tried: these amps with a full preset around them, two or three of the dearest at once,
save/recall and power cycle with an amp other than Tweed Blues Brt, snapshots, an amp on a split's lower path.

### All 111 amps (2026-11-17, `build_amps.py --set all`; working on the unit)

The user's choice after the survey below: every amp in the Amps list, no preamps, no cabs. The list is the
user's fifteen in their order, then the Stomp's other 96 in its menu order (guitar, then bass). The amp data
(model, the Stomp's preset id and cost) is in `tools/amp_list.py`, written from the Stomp firmware by
`re/stomp_amps.py` and re-checked by `tools/verify_amps.py`. Table 1 has 576 rows, the segment 12,240 bytes;
Entry 0 grows by 12,252 bytes. Image MD5 b57a9c23af2cbda5101b52c35b1d0f56, verify_amps.py ALL OK. The tweed and
fifteen images rebuild to their earlier MD5s.

- **The menu code with a 111-item list** (read, not emulated): the item count comes from 0x280fa9a4 (a 32-bit
  table read) and has eight callers. The start-up pass that writes each item's cost (0x281142e8) and the browse
  routines (0x281118cc..0x28112632) hold an item index in a byte and compare it with the count, so up to 255 items
  work; the preset-id -> item map (0x28109974) is indexed by preset id, capped at 832. No per-item bit mask or
  fixed-size item buffer was found. The Stomp's same lists hold 94 items. Not known until it runs: how the
  list screen scrolls through 111 names (the longest stock list has 44).
- **The edge of the amp container:** PV Vitriol Lead needs exactly the container's 506 PM words and 154 members
  (DM 1350 of 1430). PV VitriolCrunch (479 / 151) and EV Panama Red (458 / 135, played on the unit) are next.
  The dearest amps cost 3700 (PV Vitriol Lead, PV VitriolCrunch, EV Panama Red).

**Flashed 2026-11-17 (107 s, boots).** Read back: no fault; boot-log errors the same as the fifteen-amp boot; row
count 576 and list count 111 in memory; the start-up pass wrote the cost into the first, sixteenth and last items
(1209, 1456, 1400), so it walked the whole 111-item list.

**On the unit (user's test, 2026-11-17): "All good".** The list scrolls to the end and the amps tried play. The
log for the test (build/logs/2026-11-17_amps_all_test.log) has 111 model changes, every one followed by the
success line, no ERROR or WARNING, no fault record; the only other lines are the usual `mapHCChangeEvent ...
detail=21` notices and one block allocation (an amp in record 6, the one tied to fx.13).

## NAM + Click with the amps (2026-11-17; working on the unit)

The user asked for NAM next, chose NAM + Click (as hx-effects-nam-lite's `build.py nam`) with NAM on the mono
Regal Bass DI (Distortion > Mono). nam-lite's NAM and Click tooling is copied here unchanged from its commit
9476ace (`git archive`; nam-lite itself only read). Rebuilt here, the NAM-only, Click-only and NAM + Click images
are byte for byte nam-lite's (MD5 aaa5186b..., 407671f6..., 24b00640596d6ff2b83b472a9f2f9ff1), and
`tools/verify/verify_nam_click.py` passes.

`build_amps.py --set all --base nam` puts the memory window and the 111 amps on top of that image. Where the two
meet (all verified):
- **Entry 0.** NAM and Click change 35 + a few bytes in place: the Regal Bass DI's and the Mod/Chorus Echo's
  Table 2 names and counts, menu names, and Table 1 cost (Regal 750 -> 2300). None is a byte the memory window or
  the amps change. The Table 1 costs travel with the table into the new segment (the build copies the rows of
  the image it is given, so NAM's 2300 is in the moved table).
- **Entries 2, 3 and 4** are NAM + Click's, untouched by the amps. NAM + Click append a model and strings to
  Entry 3, add two host graphs to Entry 4, enlarge the DSP's Blob 0 buffer (0x79000 words) and move its Heap 6
  (same size, to 0x30d100), and inject two kernels. Every amp's model, parameters, graph and memory need, and
  the amp container itself, are the same as on stock.

Image `build/HX_Effects_v3.80.0_MemWin_NAM_Click_Amps_all.hxf`, MD5 e2162bcaf9d295612c24ebe1161c7df0,
`tools/verify_amps.py build/amps_all_nam_manifest.json` ALL OK (with section 0, the base, and the
amps-unchanged check). Not known until it runs: amps with the DSP's Heap 6 moved and the larger Blob 0 buffer
(never tried together), and what the DSP budget allows with NAM (cost 2300) and an amp (up to 3700) in one
preset.

**Flashed 2026-11-17 (116 s, boots).** No fault; boot-log errors identical to the 111-amp image's boot; the Amps
list (111) and the last item's cost are in memory. The start-up preset "Gtr Starter" still fails with -3, here as
on every test image: its block is a 1024 IR block (`IR_MONO_1024`, restored from User IR index 3) that fails at
appDspObject.c:1409 ERROR_INVALID_PARAMETER. So it is not a NAM block on the Regal host, as assumed earlier; most
likely it was saved when NAM sat on the 1024 IR block (nam-lite's first placement) and carries NAM's knobs. Not
investigated further.

**On the unit (user's test, 2026-11-17): "All played"**: NAM with a capture, an amp after it (including a heavy
one), and Click. The test log (build/logs/2026-11-17_nam_amps_test.log): 58 model changes, each followed by its
success line (on blocks 1, 2 and 3), allocations for an FX block (NAM), an AMP block and a TRAIL block (Click), no
ERROR or WARNING, no fault record. NAM, Click and the amps work together.

## All amps, preamps and cabs: what the firmware holds (offline survey, 2026-11-17)

Asked by the user: "could we unlock all the amps, and preamps, and cabs". What the HX Stomp lists, checked one by
one against the HX Effects firmware (all verified offline unless marked):

| Kind | Stomp lists | Block type | In the Effects' model table, Table 2, DSP routines | Container on the Effects |
|---|---|---|---|---|
| Amp | 111 (94 guitar, 17 bass) | 0x11 AMP | all 111 | HD2_AppAmpHarness (fx.13..15) |
| Preamp | 112 (94, 17, 1 mic) | 0x11 AMP | all 112 | the same: its modelSlot list of 225 holds amps and preamps |
| Cab, legacy, single | 41 | 0x0f CAB_SINGLE | all 41 | HD2_AppCabHarnessSingle (every slot accepts it) |
| Cab, legacy, dual | 41 (same models) | 0x10 CAB_DUAL | all 41 | HD2_AppCabHarnessDual (fx.13..15 only) |
| Cab, new, single | 46 | 0x1f IR_CAB_SINGLE | models and routines yes, **sound data no** | HD2_AppFxHarnessMono |
| Cab, new, dual | 46 | 0x20 IR_CAB_DUAL | **no models** ("...WithPan") | none: the app returns an error for this type |
| Amp+Cab | 111 + 111 legacy | 0x21 / 0x12 | amp models yes | AmpCabIR / AmpCab harness; not studied |

- **Amps and preamps: a data job.** Every one has its model, Table 2 row and DSP graph (same memory need as on the
  Stomp, every routine present), fits the amp container (largest 1350 DM, 506 PM, 154 members against 1430 / 506 /
  154), and its Stomp preset id is free on the Effects and below 833 (the Stomp's highest id is 832; 463 of the
  Effects' 465 stock blocks have the same id as on the Stomp). A preamp is an AMP-type block, so it takes the
  path the fifteen amps already take. Table 1 would have 465 + 223 rows.
- **Legacy cabs: probably, with new work.** The cab models carry their own data (model blobs of about 5,350 words,
  the same length as the Stomp's). The placement check (0x280f221c) counts CAB_SINGLE as one cab and CAB_DUAL as
  two against a limit of 0 (0x280f22a8). The allocator treats CAB_SINGLE as LITTLE (any block record) and CAB_DUAL
  as BIG (now records 6..8). Not studied: whether there is a cab counterpart of the amp registry, and the cab
  block's parameters (microphone, distance) in the Effects' screens.
- **New-style cabs: no.** Their models are 636-word stubs; the sound data is a 54 MB "cabpkg" package that is the
  Stomp firmware's fifteenth entry. The HX Effects firmware has fourteen entries and no such package (its whole
  image is 19.9 MB against the Stomp's 75.6 MB). The same goes for the Amp+Cab blocks that use the new cabs
  (type 0x21). Whether the Effects' flash chip could even hold the package is not known.
- **Menu room.** Thirteen categories of four lists. Distortion's fourth list is the Amps list. Free lists: one in
  each of Dynamics, Modulation, Delay, Reverb, Pitch/Synth, Filter; two in each of EQ, Wah, Impulse Response,
  Volume/Pan, Send/Return, Looper. Adding whole categories (as the Stomp has: Amp, Preamp, Cab) has not been
  studied.
- At most three amp-type blocks at once (the three amp-capable slots), amps and preamps together.

## Legacy cabs (2026-11-27; `tools/cabs_group.py`, `tools/verify_cabs.py`; singles tested on the unit)

**Current state:** the 41 legacy single cabs (type 0x0f, CAB_SINGLE) in one "Cabs" list, EQ's fourth (EQ: Mono,
Stereo, Preamps, Cabs), and **two cab blocks per DSP**: the one code change is the cab limit at 0x280f22a8,
`cmp r4, #0` -> `cmp r4, #2`. A single cab weighs one cab and runs in a LITTLE record, so nothing else changes.

**Dual cabs were built, tried on the unit and dropped** (user, 2026-11-27). They listed and played, but a dual item
names one model for both cabs (as the Stomp's items do), and the HX Effects has no screen to choose the second cab,
so a dual could only play one cab twice. A cab in each path does the job. The rest of this section is the dual-cab
design as built for that test (82 items, the recount and weight changes, the cave, a cab limit of 1), kept because
the findings about the recount, the weights and the allocator still hold.

The first plan: all 41 legacy single cabs and all 41 legacy dual cabs (0x10, CAB_DUAL) in that list; one cab block
per preset, single or dual.
New-style cabs and the Amp+Cab blocks are not included: their sound data is not in this firmware (above).

**The menu side** goes with the amps (`amps_group.plan(..., cabs=...)`, `build_amps.py --cabs all`). One Table 1
row per cab ({name index, the Stomp's preset id, 0, 720}), after the amps' and preamps' rows (465 + 111 + 112 = 688, + 41 = 729 rows);
then the 82 items after the Preamps items: the 41 singles (the Stomp's items byte for byte: type 0x0f, name index,
0xffffffff, preset id, the Stomp's name, 1, 0), then the 41 duals (the Stomp's: type 0x10, **the same model's name
index at +4 and +8**, the single's preset id; names from `tools/cab_list.py`, "Dual ...", 16 characters at most).
EQ's list count 3 -> 4, list 11's pointer and count (82), its name field (empty on stock) "Cabs". The list view's
highlight clamp (amps_group) already covers a four-list EQ. Single and dual share one row and one preset id, as
on the Stomp: the preset-id -> item map (0x28109974) only takes items whose +8 is 0xffffffff (or whose type is
0x20), so an id leads to the single item, as on the Stomp. The cab ids (45..74, 355..366, 551, 552, 589, 590) are
unused on the Effects and below 833; every cab has a Table 2 row and its model, parameters and graph here.

**Where the block types go** (all checked in the bytes):
- Container (tbh at 0x280f3ee8): 0x0f -> `HD2_AppCabHarnessSingle` (modelSlot + Mic, 0x280f4406), 0x10 ->
  `HD2_AppCabHarnessDual` (modelSlot1, modelSlot2, two Mics, 0x280f4396). Every DSP slot fx.0..15 accepts the
  single container; only fx.13..15 accept the dual one (Entry 3 groups 109..111), and since the amp work block
  records 6..8 are tied to those.
- Allocator (0x280ed3ec): 0x0f is LITTLE (first free record from 0, as an effect), 0x10..0x12 and 0x21 BIG (the
  amp path, records 6..8). Emulated in verify_cabs.py.
- Amp registry (0x280f9118): types 0x11, 0x12, 0x21 only (and "return 0" since the amp work). No cab registry.
- Menu availability (0x28113eb8): per item the DSP cost test and a few model-id rules; the only block-count rule
  is the IR category's (category 0xb, the IR count at 0x2811410e). Nothing greys a cab item in EQ (category 4 in
  that code). A second cab is therefore listed normally and refused by the placement check when chosen, like a
  fourth amp.

**The counters and the placement check.** The per-DSP counters are recounted from the block records by
0x280f0b8c (called from 0x280f21be): a jump table (tbh at 0x280f0bc4) by record type adds 1 to the amps (+0xae8)
for 0x11, 0x12, 0x21; to the cabs (+0xae4) 1 for 0x0f and 0x12, **2 for 0x10**; to the IRs (+0xae0) 1 or 2. The
placement check at 0x280f221c then tests count - old block's weights + new block's weights against a limit for
each (amps `cmp r3` at 0x280f2296, cabs `cmp r4` at 0x280f22a8, IRs `cmp r1, #2` at 0x280f22b2). The weights are
set per type in two places: the old block's (type in r5; amp r4, cab ip, IR sl) and the new one's (type in lr; amp
r3, cab r2, IR r0). Stock: a dual weighs cab 2, amp 0, and the cab limit is 0.

A dual runs in a BIG record, so it must count as one of the three amp-type blocks, or three amps and a dual pass
the check and the allocation then fails (which breaks the signal flow). And all three places must agree, since the
check subtracts the old block's weights from counts the recount made. With only the two weight sites changed, a
dual on the DSP still makes the cab count 2, so with a limit of 1 every later placement on that DSP is refused,
even an effect, and the dual can't be swapped for another cab (found by emulating both together, verify_cabs.py
section 5). The changes (`cabs_group.code_changes`):

| Address | Stock | New | |
|---|---|---|---|
| 0x280f0be8 | `a1 00` | `8d 00` | recount: type 0x10 takes type 0x12's case (amps + 1, cabs + 1) |
| 0x280f2254 | `4ff0020c a246` mov.w ip, #2; mov sl, r4 | `a246 0124 a446` mov sl, r4; movs r4, #1; mov ip, r4 | old block a dual: IR 0 (r4 is 0 there, 0x280f224e), amp 1, cab 1 |
| 0x280f2280 | `0222 1846` movs r2, #2; mov r0, r3 | `fbf796b8` b.w 0x280ed3b0 | new block a dual: to the cave |
| 0x280ed3b0 | (log string) | `0122 0123 0020 04f065bf` movs r2, #1; movs r3, #1; movs r0, #0; b.w 0x280f2284 | cab 1, amp 1, IR 0 |
| 0x280f22a8 | `002c` cmp r4, #0 | `012c` cmp r4, #1 | one cab block per DSP |

Flags: `movs r4, #1` and the cave's `movs` set flags, but nothing tests them before the `lsrs` at 0x280f2262 and
0x280f228c set them again. lr (the new type) is untouched, so 0x280f2284 (`sub.w r6, lr, #0x16`) runs as before.
Nothing else branches to 0x280f2254..59, 0x280f2280..83 or 0x280f22a8 (scanned). (The new path would also fit
without a cave, in the 12 bytes at 0x280f2278: `ite ne; movne r3, #0; moveq r3, #1; bne.w 0x280f23ee;
b 0x280f23f4`, reusing the single cab's `movs r2, #1; movs r0, #0`. Not used: the cave was the design asked for.)

**The cave** is 10 bytes at 0x280ed3b0, inside the log string "INFO: out of BIG blocks for BIG models, will
attempt LITTLE block eviction..." (0x280ed39c, 78 bytes with its NUL, up to the allocator at 0x280ed3ec), right
after amps_group's 20-byte list-view routine. The string's only reference anywhere in Entry 0 is the literal at
0x280ed4ac; its only load was `ldr r0, [pc, #0x3c]` at 0x280ed46c, which the amp work's allocator change replaced
with `movs r2, #6`. (The two `movw r3, #0xd3c8` at 0x280ce490 and 0x280ce4e8 are a 16-bit tag, not an address.)

**Emulated** (verify_cabs.py): the recount and the check together, on every combination of up to three blocks of
types 0x01, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x21, every replacement and every new type (4,200 cases): the
amps image follows the stock rules exactly, the cabs image the new ones (a dual = one amp + one cab; one cab,
three amps, two IRs). So: one single or one dual per DSP; a dual can be swapped for a single or another dual in
place; three amps refuse a dual, a dual and two amps refuse a third amp, two amps take a dual.

**Risk for the unit: the dual container's DSP memory.** `HD2_AppCabHarnessDual` needs DM 900, PM 542, SDRAM
10,240 words; the amp container, proven in fx.13..15, needs 1,438 / 511 / 2,048. A dual needs 31 more PM words
and 8,192 more SDRAM words than anything run in those slots so far; whether fx.13..15 reserve that is only known
on the unit. The single container (454 / 274 / 5,120) is well inside the mono effect container (917 / 339 /
394,240). Each cab's graph is 446 DM / 269 PM / 5,120 SDRAM words, 25 members, as on the Stomp, and uses only
routines in the DSP program.

Not done here: the preset builder (`tools/preset-builder/make_catalog.js` would need regenerating for the 82
items, with the cab blocks' Mic parameter, string 0x806, which is a sub-slot of its own), the setup page, and the
cab blocks' screens on the unit (Mic, distance and the rest: never seen on the HX Effects).

## Open questions for phase 1

1. ~~Where is the RTT buffer, how big is it, and is logging switched on by default?~~ Answered above: 64 KB at
   0x282ae37c, always on, but it stops at the first 64 KB. Still open: how fast it fills after boot.
2. ~~What do the fault handlers do?~~ Loop forever (above).
3. ~~A way to read memory or the log over USB.~~ The memory window (above). Drawing on the screen was not needed.
4. ~~Does the memory window work at all?~~ Yes. Still open: does it answer during a freeze?
5. ~~How fast does the log fill?~~ 5.7 KB per boot.
6. ~~Why does an amp block fail?~~ No BIG blocks in this build (above). **Phase 1's milestone is reached.**
7. ~~What is a BIG block in the Stomp's build?~~ A quota, not a different record (above).
8. ~~Does an amp fit an ordinary block?~~ Wrong question: ordinary slots do not accept the amp container at all.
9. ~~Do the DSP slots fx.13..fx.15 work on the HX Effects' DSP?~~ Yes: the amp runs there (above).
10. ~~Why did the first selection fail with `appDsp.c:609`?~~ The amp registry, compiled for zero amps (above).
