# DSP optimisation: implementation plan

Written 2026-11-28, from the first DSP load sweep (HANDOVER, "2026-11-28: DSP load of every block"). A measuring
rig first, then five pieces of work, in this order. Each one is its own branch, and every flash needs the user's go-ahead and an image that ends
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
- **NAM A2 Lite**: 27.5 % a block (about 41,500 cycles a call), charged 30.7 %. It is in most presets and is our own
  code, but it has only been measured whole: the kernel check caps a steady call at 33,000 instructions (about 22 %),
  and the gap to 27.5 % has not been explained.
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
   per word, which should be several times faster. **NAM already does this**: its kernel runs chained DMA on EP
   channel 0 (DMAC0 0x180b, the EIEP0..CPEP0 registers 0x1820..0x1826), proven on the unit, and its check models
   the channel in ssim (`tools/sharc/nam_multi.py`, ChainDma, with timing). So:
   - the overlay swap uses **EP channel 1**, never NAM's channel 0, unless a shared scheme is proven (a preset can
     hold NAM and overlays together, and the two kernels run in turn within one audio call);
   - check that stock Entry 2 never touches channel 1 or its registers (scan for writes to the DMA register block);
   - reuse ChainDma (extended to channel 1) in the stub's ssim check, so the interleaved check covers the DMA;
   - wait for completion cheaply before the jump, and fall back to the core copy if the channel isn't idle.
4. **Two regions, if room can be found.** With two regions, the two overlays most presets hold would never swap. This
   needs about 1,100 more internal words. Look again at Block 0 and Block 2 (nocaseguy's heap move frees Block 0 room,
   but conflicts with NAM; see Phase 4), and at what compact_blob0 left.
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

## Phase 3: profile and speed up NAM A2 Lite

NAM is the heaviest block most presets hold (two NAMs are 55 % of the DSP), and it is our code, so savings here
help the most presets. The rule is the one the kernel already lives by: every instance's output stays bit for bit
the same as `nam_a2.asm` (`nam_lite.reference`) through Pipe.

1. **Profile in ssim, by stage.** Extend `nam_multi.py`'s KernelCheck to count cycles per stage of a steady call:
   input and Drive, each layer's dilated convolution (near taps from internal memory, far taps from the staging
   buffers), the head, the tone stack, the crossfade, the ring and HIST writes, the DMA set-up and every wait on
   DMA completion. Report the per-stage worst and mean for a placeholder model and a few real captures, and the
   model-load calls apart from steady ones.
2. **Profile on the unit.** The kernel has a report area for a probe (REP 0xe4860, 16 words of counters). Have NAM
   write EMUCLK deltas per stage there, and have the Probe report them (a Report-mode frame with words for REP).
   This explains the gap between ssim's ~33,000 instructions and the unit's ~41,500 cycles: DDR2 stalls, DMA waits
   or something the simulator doesn't model. Measure with the Phase 0 noise source, since a NAM's load shouldn't
   depend on the signal, and check that it doesn't.
3. **Targets, in the order the profile ranks them.** Likely candidates, to be confirmed by the numbers:
   - waits on DMA: start each far layer's transfer earlier (double-buffer the staging so the next layer's taps
     arrive while this one computes);
   - the convolution inner loops: SIMD (PEx and PEy) on both halves of each tap pair, and dual data fetches per cycle;
   - per-call overhead shared by both slots (Drive, the gain tables and the tone stack's table read once, not per
     slot);
   - the crossfade and HIST work, which only matter while a model changes.
4. **Prove each change**: the existing bit-for-bit check for every instance; `nam_multi.py --check` for 2 and 3
   slots and both stagings; then the Phase 0 sweep measures NAM alone, two NAMs, and NAM with an overlay.
5. **Re-cost NAM** (`DSP_COST`) from the new worst, through Phase 2's rule. Done when two NAMs measure clearly under
   today's 55 %, and the setup page's NAM-only and full builds both play on the unit.

## Phase 4: port nocaseguy's bit-exact rewrites

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

## Phase 5: our own rewrites of the heaviest stock blocks

Once Phases 0-4 are done, the sweep's table ranks what is left: Industrial Fuzz, the Poly pitch family and the
heaviest amps. Each rewrite follows Phase 4's proof (bit-exact in ssim against stock, then measured on the unit).
Pick targets by cycles saved times how often the block is used.

## Order and checkpoints

| Step | Branch | Needs the user |
|---|---|---|
| Phase 0 | `dsp-rig` | flash the probe image; 3D for the sweep; the amp set up at the speaker |
| Phase 2.1 (Industrial Fuzz) | `fair-costs` | flash and play it |
| Phase 1 | `overlay-swap` | flash; play the overlay combinations |
| Phase 2.2-2.5 | `fair-costs` | approve the cost table; play the heavy presets |
| Phase 3 | `nam-speed` | flash; listen to NAM captures; nearby for two-NAM presets |
| Phase 4 | `dsp-opt-port` | flash; play the affected models |
| Phase 5 | per target | flash each |

After each phase: reflash the user's own build, record the results in HANDOVER, and leave no test presets on the unit.
