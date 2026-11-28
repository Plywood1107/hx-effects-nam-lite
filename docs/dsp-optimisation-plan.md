# DSP optimisation: implementation plan

Written 2026-11-28, from the first DSP load sweep (HANDOVER, "2026-11-28: DSP load of every block"). Four pieces of
work, in this order. Each one is its own branch, and every flash needs the user's go-ahead and an image that ends
"verified ALL OK".

## What the sweep showed

- Stock blocks use about **0.70 x their Table 1 charge** (+0.4 %, r = 0.91). A preset charged at 100 % runs at about
  86 % of the DSP. Our reading of PV Vitriol Lead (35.6 %) matches nocaseguy's Stomp figure (53,503 cycles = 35.5 %).
- **Overlay effects**: about 3-4 % alone, but two in a preset pay about 33 % for swapping code in on every call
  (~25 cycles a word copied from DDR2, ~1,100 words a swap). They are charged 12-17 %, which is too much alone and
  too little in pairs.
- **Over-charged stock blocks**: Feedbacker 5 % vs 29 %, the Poly pitch family 28-32 % vs 48-53 %, 80A Flanger 7 vs
  23, Tone Sovereign stereo 20 vs 38, Grammatico LG and Fullerton 21-23 vs 37-39.
- **Under-charged**: Industrial Fuzz 42 % mono and 49 % stereo, vs 13 % and 23 %.
- **Limits of the first sweep**: the input was unplugged (no signal, factory knobs). The Probe is an overlay, so it
  can't measure an overlay alone. Killer Z, Bronze Master and 3 OSC Synth gave no frames.

## Phase 0: a better measuring rig (needed by the other phases)

1. **Resident Probe.** Build a probe image in which the Probe kernel is resident, not an overlay, so it causes no swaps.
   First check the room: Block 3 has only a few dozen words free in the full build, so the probe image will need to
   leave out resident effects (Geiger, Commander, Corrupt) to fit the Probe's 426 instructions. `build_all.py
   --with ...` already chooses the set; add a `resident` flag for hostprobe and run the stub's fit check.
2. **A signal source on the unit.** Add a Mode 3, Noise, to the Probe: white noise at -12 dBFS out, input ignored. A
   preset is then Probe (Noise) -> block under test -> Probe (Load). Two instances of a resident kernel cost no swap.
   The Mac needs no cable, and both Probes are in the base reading.
3. **Knob corners.** `dsp_load.py sweep --corners`: factory knobs with and without noise, then all max, all min, and
   two seeded random sets, from the model's Entry 3 knob list (as nocaseguy did). Store every point. A model's figure
   is its worst point.
4. **Checks**: the C test and the kernel check for Mode Noise; the selftest still decodes; on the unit, the base reading
   with two Probes is steady and the NAM calibration (+27.5 %) repeats.
5. **Re-run** the sweep with noise and corners (about 3 h a pass at 12 s a point; a corner pass is longer). Run the two
   distortions and the synth that gave no frames, and the overlays alone and in pairs.

## Phase 1: a cheaper overlay swap (the biggest win)

The stub (`effects/common/ovl_stub_kernel.py`, `o_swap`) already skips the copy when the wanted effect is in the
region. The cost is the copy itself: the outgoing slots back to DDR2, then the incoming code and data, one word at
a time through the core, which stalls on every DDR2 read.

1. **Measure the swap on the unit** with the resident Probe: Ottobit alone, Ottobit + Doom Chug, and each pair. Fit the
   cycles per word, and split code, data and slot words.
2. **Shrink what is copied.**
   - Copy only the data words a kernel writes. Constant tables are copied in at every swap; give each member a
     constant part that stays in DDR2 and is read in place (reading data from DDR2 works; only running 48-bit code
     from DDR2 froze the unit), if the kernel reads it rarely enough. Measure each kernel's reads of each table first.
   - Put shared code (Greasy and Bethblahem both carry Corrupt's tracker and Doom Chug's drone) in one copy.
   - Every word saved is about 25 cycles, so each kernel's size becomes worth trimming.
3. **External-port DMA for the copy.** On the ADSP-2146x, EP DMA can move DDR2 to internal memory without a core stall
   per word, which should be several times faster. Before writing any code, check:
   - that stock Entry 2 never uses the EP DMA channels or their registers (scan for writes to the DMA register block),
     so we don't collide with Line 6's transfers;
   - what ssim models (if it doesn't model DMA, add the transfer as an instant copy and keep the stub's check);
   - how to wait for completion cheaply before the jump.
   Fall back to the core copy if the channel isn't idle.
4. **Two regions, if room can be found.** With two regions, the two overlays most presets hold would never swap. This
   needs about 1,100 more internal words. Look again at Block 0 and Block 2 (nocaseguy's heap move frees Block 0 room,
   but conflicts with NAM; see Phase 3), and at what compact_blob0 left.
5. **Re-cost the overlays** (`build_all.py` OVL_COST) from the new swap cost: the kernel's own worst plus the swap,
   since a fixed charge must assume the worst case.
6. **Acceptance**: the stub's interleaved check passes; on the unit, the measured pair cost drops; Commander + Doom
   Chug + Drum Chapel + Pure Whitey (the preset that locked the DSP on 2026-11-18) plays; every overlay still plays
   alone.

## Phase 2: fairer block costs

1. **Safety fix first, on its own**: raise Industrial Fuzz's charge (mono and stereo) to what it measures, once Phase 0
   confirms the reading with a signal. This goes into the default build, since it only refuses presets that would
   overload the DSP.
2. **The rule.** New charge = worst measured cycles (Phase 0, noise and corners) x (1 + margin) / cycles per unit, with
   the cycles per unit and margin fitted to Line 6's own charges so a full preset keeps today's ~14 % of headroom.
   Only lower a charge where the gap is large (say more than 5 points), and never below the worst point plus margin.
3. **`tools/fair_costs.py` and `build.py --fair-costs`.** It patches the cost word of every Table 1 row the model
   has, from a committed table of our own measurements (no Line 6 data in git). Checks: only cost words change; the
   table's models all exist; no cost goes up except the ones listed as under-charged.
4. **Test on the unit**: build the heaviest presets the new costs admit (several Poly blocks, Feedbacker + amps, NAM
   + the cheapened blocks), play each for minutes with a signal, and watch for dropouts, lockups and SPI errors.
5. **Setup page and preset builder**: a "Fair DSP costs" checkbox (`REAL_NAMES_OK`-style rules for which builds offer
   it), recipes, and the builder's DSP total using the same table. README and release notes.

## Phase 3: port nocaseguy's bit-exact rewrites

His `dsp-opt-patch-list` is GPL-3.0-or-later, like this repo, so it can be ported with credit (NOTICE and README).
For HX Stomp Entry 2 it has 59 groups. On the HX Effects, 2 sit at the same place, about 25 exist as exact copies
at a shifted address, and about 32 aren't found. He measured 13 % lower worst-case load across 263 models on the
Stomp. It has never run on an HX Effects.

1. **Port tool** (`tools/dsp_opt_port.py`, our own code; his `patch.json` read as data). For each group found at the
   same place or at one exact shift, move his new units by the shift. Then check every absolute address in the new
   units (jumps, calls, data addresses): each must point inside the group or to a place that moved by the same shift,
   or the group is refused. Keep his hash check and read back as in his `apply.py`.
2. **`--heaps none` only**: his buffer move uses Block 2's tail, which NAM A2 Lite needs.
3. **Prove each group offline**: run the stock routine and the rewrite in ssim on generated inputs, and compare memory
   and registers, as he did on the chip.
4. **Measure** the affected models before and after with the Phase 0 sweep, then feed the new figures into Phase 2's
   table. His rewrites don't change dsp_cost by themselves.
5. **On the unit**: play every affected model; then soak a full preset. The 32 groups not found are later work, by
   hand, routine by routine.

## Phase 4: our own rewrites of the heaviest blocks

Once Phases 0-3 are done, the sweep's table ranks what is left: Industrial Fuzz, the Poly pitch family and the
heaviest amps. Each rewrite follows Phase 3's proof (bit-exact in ssim against stock, then measured on the unit).
Pick targets by cycles saved times how often the block is used.

## Order and checkpoints

| Step | Branch | Needs the user |
|---|---|---|
| Phase 0 | `dsp-rig` | flash the probe image; 3D for the sweep; the amp set up at the speaker |
| Phase 2.1 (Industrial Fuzz) | `fair-costs` | flash and play it |
| Phase 1 | `overlay-swap` | flash; play the overlay combinations |
| Phase 2.2-2.5 | `fair-costs` | approve the cost table; play the heavy presets |
| Phase 3 | `dsp-opt-port` | flash; play the affected models |
| Phase 4 | per target | flash each |

After each phase: reflash the user's own build, record the results in HANDOVER, and leave no test presets on the unit.
