# Reference effects (C99)

Portable reference implementations of custom effects, an offline WAV renderer and tests. They are
the specification for hand-written SHARC kernels; they are not compiled for the unit. Nothing here
touches firmware. See `docs/baseline-audit.md` for what is known about the real primitive ABI.

```
cd effects
make test        # every test; no hardware, no audio files needed
make demo        # out/fixtures/*.wav (generated signals), out/geiger/*.wav, out/metronome/*.wav
out/fxrender geiger in.wav out.wav gain=18 rate=4000 bits=5 curve=3   # any WAV, any settings
out/fxrender describe geiger          # the parameter descriptor (= geiger/params.json)
```

`out/` is git-ignored. Test signals are generated from code (`common/signals.c`: impulse, step, sines,
sweep, seeded noise, Karplus-Strong plucks and a strummed E chord); no recorded audio is committed.

## API (`common/fx.h`)

An algorithm is an `FxAlgorithm`: a parameter descriptor table, `state_bytes`, `reset()` and
`process()`. All state lives in the caller's block; no allocation, I/O or mutable globals in
processing (read-only tables built once are allowed). `process()` must give the same output for any
block size, and only finite output. The renderer calls it in 16-sample blocks, as the unit does.

## Geiger (`geiger/`)

Sample-rate reduction, bit-depth quantisation and a 16-curve waveshaper table: an original algorithm
in the spirit of wavetable-distortion pedals.

```
in -> DC block -> Gain -> [Anti-Alias: 2 one-pole lowpasses at 0.4 x Rate] -> sample-and-hold at Rate
   -> quantise to Bits -> Curve (65-point table, linear interpolation) -> Tone lowpass (200 Hz..20 kHz)
   -> DC block -> Output -> Mix with the dry input
```

Eight parameters, to fit the host model's eight knob words: Gain (0..36 dB), Sample Rate
(250..48,000 Hz), Bit Depth (1..16), Curve (0..15), Tone (0..1), Output (-36..+12 dB), Mix (0..1, shown as %),
Anti-Alias (off/on). Gain, Output and Mix are smoothed per sample (5 ms one-pole); the rest act at once.
The curves: linear, soft, hard, sinefold, trifold, fullwave, halfwave, steps, asym, cheby3, cheby5, sine,
root, spline, ring, gate.

The tests (`geiger/test_geiger.c`) check: every curve finite, within ±1, the 64-segment table within 0.045 of its
function (0.06 for the two with corners or an infinite slope) and different from every other curve;
the quantiser's level count; Mix 0 is exactly the dry input; identical output across runs and block
sizes 1/16/37/4096; two interleaved instances equal each alone; finite, bounded output at every curve's
extremes, with NaN/Inf/1e30 input and with random (and NaN) knob values each block; the sample-and-hold
rate; the anti-alias mode cutting a known alias by more than 6 dB; the three variants different from
dry and each other; and `golden.txt` metrics within 1e-4 (recorded on macOS/clang; re-record with
`make golden` after an intended change).

### Geiger on the SHARC (`geiger/sharc/`)

`geiger_kernel.asm`, a hand port of `geiger.c` with Click's conventions (slots, I1-I3 restored, DM(3)
left alone). `geiger_kernel.py --check` (part of `make sharc-check`) requires every output word to equal
the C reference's: the three variants, all 16 curves, the extremes, Mix 0, out-of-range knobs, two
interleaved instances with every knob moving, and re-creation. The curve tables are read from the C
library, so they are the reference's to the bit. about 370 instructions, about 1,320 data words (mostly the
16 x 65 curve tables, sized to fit beside NAM and Click); worst 2,528 cycles per 16-sample call.

Knob words: DM(5) Gain dB, DM(6) Rate Hz, DM(7) Bits, DM(8) Curve, DM(9) Tone 0..1, DM(10) Output dB,
DM(11) Mix 0..1, DM(13) Anti-Alias (12 is the slot word).

## Commander (`commander/`)

A square-wave octave fuzz: an original algorithm in the spirit of comparator/divider octave fuzz pedals.

```
in -> DC block -> 2 one-pole lowpasses at 300 Hz (the tracking signal t) -> envelope (instant attack, 50 ms release)
   -> Schmitt comparator on t, hysteresis 50 % of the envelope: the square at the note (Fuzz)
   -> /2 on each rising edge (Sub -1 Oct), /2 again (Sub -2 Oct); |t| > envelope/2: twice the note (Octave Up)
   -> mix x min(4 x envelope, 1) x gate (smoothed; opens above Gate) -> Tone (2 one-poles, 100 Hz..10 kHz)
   -> Output, plus Dry x the input
```

Eight parameters: Fuzz, Sub -1 Oct, Sub -2 Oct, Octave Up (0..1, shown as %), Tone (0..1), Gate (list:
Off, -84..-30 dB in 6 dB steps), Dry (list: 0..100 % in 10 % steps), Output (-36..+12 dB). The voice levels,
Dry and Output are smoothed per sample (5 ms). The tracking filter and hysteresis were chosen on plucked
test notes (Karplus-Strong, low E to high B): 300 Hz / 50 % measures every period right, where 800 Hz /
15 % jumped octaves on the low strings.

Tests (`commander/test_commander.c`): each voice alone on a 110 Hz note puts its octave on top (27.5,
55, 110, 220 Hz); the -1 octave tracks a plucked note; silence with the gate on is exactly silent; Dry
100 % with the voices off is exactly the input; identical output for block sizes 1/16/49/97; finite and
bounded with NaN/Inf/1e30 input and out-of-range knobs; the gate steps are 6 dB apart.

### Commander on the SHARC (`commander/sharc/`)

`commander_kernel.asm` (Click's and Geiger's conventions). `commander_kernel.py --check` runs it in ssim
against the C reference, word for word, through `common/kernel_rig.py` (the shared builder and rig for the
newer kernels: data layout, the reference via ctypes, register contract, allowed writes, cycle budget).
About 370 instructions, about 320 data words (8 slots); worst about 3,440 cycles per 16-sample call.

Knob words: DM(5) Fuzz, DM(6) Sub -1, DM(7) Sub -2, DM(8) Octave Up, DM(9) Tone, DM(10) Output dB,
DM(11) Gate (int 0..10), DM(13) Dry (int 0..10).

## Corrupt (`corrupt/`)

A monophonic pitch-tracking square synth: an original algorithm in the spirit of PLL synth pedals.

```
the same front end as Commander (DC block, 300 Hz tracking lowpasses, envelope, Schmitt comparator: Square)
   -> the period P (samples between rising edges); if 16 <= P <= 2400: rate target = (Harmonic << (22 + Root)) / P
      as an exact integer quotient, x 2^-24 cycles a sample, at most 0.5
   -> Glide (one-pole on the rate, k = exp(Glide x ln 1e-4)) -> phase accumulator: Master square, and Sub (toggled
      each cycle: an octave below Master)
   -> mix x min(4 x envelope, 1) x gate (-66 dB, smoothed) -> Tone (2 one-poles) -> DC block -> Output
```

Eight parameters: Square, Master, Sub (0..1, shown as %), Glide (0..1), Tone (0..1), Output (-36..+12 dB),
Root (list: -2 Oct, -1 Oct, Unison, +1 Oct), Harmonic (list: 1x..8x the note). The quotient is integer
arithmetic so the SHARC (no divide instruction; a 29-step restoring division) gets the same rate to the bit.

Tests (`corrupt/test_corrupt.c`): on a 110 Hz note, Master at each Root and at Harmonic 3 lands on the
expected frequency (27.5 / 55 / 110 / 220 / 330 Hz), Sub an octave below, Square at the note; a plucked low E
is tracked; Glide 1 is still away from a new note 50 ms after a jump where Glide 0 is on it; silence is
exactly silent; block sizes; hostile input and knobs; the top of the range capped.

### Corrupt on the SHARC (`corrupt/sharc/`)

`corrupt_kernel.asm`, checked by `corrupt_kernel.py --check` as Commander's. About 405 instructions,
about 300 data words; worst about 3,550 cycles per call.

Knob words: DM(5) Square, DM(6) Master, DM(7) Sub, DM(8) Glide, DM(9) Tone, DM(10) Output dB,
DM(11) Root (int 0..3), DM(13) Harmonic (int 1..8).

## The next six (`ottobit/`, `stutter/`, `syntax/`, `grains/`, `sequence/`, `warp/`)

Written 2026-11-04 (on `main` since 2026-11-11): C reference, tests, and a SHARC kernel each, bit for
bit against the reference in ssim. **Ottobit** is in the default image and works on the unit, as an
overlay (`docs/baseline-audit.md`, "Finding more memory"). **Syntax** was built into a test image and
dropped: it locked the unit's interface when knobs were turned beside Geiger or Ottobit (audio carried
on; cause unknown). Stutter, Grains, Sequence and Warp are not in an image.
Each kernel's header comment lists its knob words. Every one keeps the conventions of the kernels above;
the rings of the buffer effects sit at `RING0` (DDR2 on the unit, set by the image build).

| Effect | What it is | Kernel | Cycles per call (mean / worst) |
|---|---|---|---|
| **Ottobit** | sequenced crusher: stutter ring -> sample-and-hold -> Bits -> Chamberlin lowpass (Q 2); 6-step patterns of power-of-two rate and filter multipliers; xorshift32 stutters loop a quarter step | 439 instructions, 2,048-word ring a slot (zeroed on claim) | 2,450 / 8,760 (the claim) |
| **Stutter** | triggered repeater: Clock / Transient / Both, Chance, Length 20..500 ms (Random halves it), Repeats 1..16, Speed 1x, 2x, 0.5x, Rev, Rev 2x or random; 32-sample edge fades, 64-sample crossfade | 414 instructions, 32,768-word ring a slot (never zeroed: a slice only reads what was recorded) | 1,700 / 2,080 |
| **Syntax** | drive -> soft clip -> single-sideband frequency shift (Hilbert pair of 4 + 4 allpasses, a renormalised rotating phasor), shift 0..1000 Hz x an 8-step pattern of -2..2, Glide, Tone | 426 instructions, no ring | 5,420 / 5,670 |
| **Grains** | granular: 4 voices (Density 1..4), Size a list of 10..200 ms with exact reciprocals, Pitch -12..+12, Spray up to 0.5 s, Scatter (octave jumps), Reverse, Feedback | 412 instructions, 65,536-word ring a slot (never zeroed) | 3,110 / 4,450 |
| **Sequence** | Corrupt's tracker -> an arpeggiator: 8-step semitone patterns (2^(k/12) table), Octave, Wave square / saw / triangle / pulse, Glide, envelope and gate | 446 instructions, no ring | 2,900 / 3,330 |
| **Warp** | two-head rotating-delay pitch shifter (2,048-sample window), -12..+24, modulated by a triangle LFO blended with glided random steps (Chaos), Feedback into the shifter | 390 instructions, 4,096-word ring a slot (zeroed on claim) | 2,830 / 15,240 (the claim) |

Two things learned on the way:
- R*n* and F*n* are one register: an integer index kept in R9 dies at `F9 = FLOAT R9`. Use it first, or keep
  it in a register the float code does not touch.
- The C reference must flush denormals as the SHARC does: `fx_set_ftz(1)` (FPCR.FZ on arm64, FTZ/DAZ on
  x86-64); the kernel checks call it, so a value that underflows agrees to the bit too. Only around each
  reference call: left on, it changed an image build's own float arithmetic (Image B rebuilt with a
  different MD5 until `kernel_rig.Reference` switched it off again after every call).

## Click (`metronome/`)

A metronome as an ordinary **preset block**: it lives in a preset, takes one block, and follows the
block's bypass/footswitch. Not a global metronome. The guitar passes at exactly unity gain; a
synthesised click is added.

Six parameters: Time (one beat, 0.1..4.0 s = 15..600 BPM, as an HX delay's Time knob delivers it,
synced to tap tempo or not; turned into BPM to 0.01 by integer division), Beats/Bar (2..5: 2/4,
3/4, 4/4, 5/4), Accent (0..12 dB on beat 1; 0 dB = no accent, same sound as other beats), Sound
(click, wood, beep), Level (0..1, shown as % on the unit, linear, peak 1.0), Subdivision (1..4 per beat: quarters, eighths,
triplets, sixteenths; subdivision clicks are lower and about 8 dB quieter).

- **Timing is exact.** The tempo phase is an integer: it gains BPM x 100 x subdivision per sample and
  ticks at sample rate x 6000, so tick k lands on the first sample at or after k x 60 / BPM s, for
  ever. No floating-point drift (tested over 10 minutes at 20, 60, 120, 137.5 and 300 BPM).
- **Bar position:** the first sample after `reset()` is beat 1, accented ("restart on enable"). Whether
  the unit re-creates or resets a block when it is enabled is not known yet; if it does not, the block
  will resume its running count instead. Tempo changes keep the phase within the beat.
- **Voices:** sine partials from a quadrature oscillator (no tables, no samples), exponential decay
  (click 3 ms, wood 12 ms with a second partial at 2.71x) or a 40 ms gate with 5 ms release (beep).
  A new tick replaces a sounding voice; no voice lasts more than 200 ms.
- **Not in V1:** HX tap tempo, preset tempo or MIDI clock (needs evidence of how stock tempo-synced
  blocks get their tempo), compound meters such as 6/8, and a separate click output.

The tests (`metronome/test_metronome.c`, the brief's acceptance tests 1-4): exact tick count and every
tick within one sample of its ideal time for 10 minutes at five tempos; downbeat at sample 0 and the
accent/beat/subdivision pattern in all 16 meter x subdivision combinations; Level 0 gives exactly the
input, otherwise output = input + click (within 1e-6) with a peak of at most 1.0 and the guitar
untouched between clicks; random knob changes (including NaN) and resets for two minutes give only
finite, bounded output, no two ticks closer than the fastest possible interval, and no voice longer
than 200 ms; two interleaved instances equal each alone; identical output for block sizes 1/16/37/4096.

### Click on the SHARC (`metronome/sharc/`)

**Works on the unit (2026-11-03):** `build_click.py` → Delay > Mono > "Click" (the mono Mod/Chorus
Echo's slot): all knobs shown and working, footswitch bypass working, timing and sounds as in the
reference. That image has no NAM block; `build_nam_click.py` makes one with both (works on the unit,
2026-11-04: Click's kernel at Block 3 addresses, `click_kernel.py --check --place b3`).

**Tempo from the delay's own Time knob (works on the unit, 2026-11-03: tap tempo, global BPM, ms mode):** Click now uses Mod/Chorus
Echo's Time, note-value and Tempo Sync parameters. HX shows Time in ms, or as a note value when synced
(pressing the knob toggles it), and synced it follows tap tempo and the global BPM; the default is
synced, 1/4. Stock delays work out the synced time in their DSP parameter map (nodes 0x2a and 0x54);
Click's map copies those two nodes exactly (`verify_click.py` compares them with the stock map) and
sends the result, the beat length in seconds, to word 5. The kernel turns it into BPM x 100 by an
integer shift-and-subtract division (no float divide on the SHARC), still bit-identical to the C
reference.

`click_kernel.asm` is a hand-written port of `metronome.c` for the HX Effects' SHARC, assembled with
`tools/sharc/sasm.py`. `click_kernel.py --check` (or `make sharc-check`) runs it in `tools/sharc/ssim.py`
and calls the C reference through `out/libfx.so`, and requires **every output word to be identical**:
six fixed settings (including Level 0 and out-of-range knobs) and two interleaved instances with all
knobs moving every 100 ms. Each call is also held to the register contract the NAM kernel's rig uses
(R0-R15, the alternate registers, the DAG registers and MODE1 unchanged; no loop or PC stack left),
and every memory write must land in the output buffer, the instance's state words or the save area.

Measured: bit-identical; 351 instructions; worst 1,483 and mean about 650 cycles per 16-sample call,
under 1 % of the roughly 150,000 a call has at 450 MHz.

For the match to be exact the reference avoids anything the port can't reproduce: constants are
computed in double and rounded once (the port's tables are generated the same way), Accent is whole dB
(a 13-entry table), the beep's release is a fixed per-sample
step, and the C build uses `-ffp-contract=off` (no fused multiply-add).

The port's own ABI, which the firmware gives it (`build_click.py`): knob words DM(5) Tempo (float
BPM), DM(6) Beats/Bar (int), DM(7) Accent (int dB), DM(8) Sound (int), DM(9) Level (float 0..1),
DM(10) Subdivision (int). What the hardware builds taught (2026-11-03):

- **Put I1-I3 back on exit.** The NAM kernel does (restoring B1-B3 reloads them). Returning with
  I1/I2 advanced past the buffers froze the unit's knobs and footswitches while audio carried on.
  The check now requires every index register to come back unchanged; the old kernel fails it.
- **DM(3) is not a usable bypass flag.** Probe builds showed it non-zero the whole time the block is
  on, unchanged by the footswitch (stock 0x822's kernel passes audio through while it is non-zero,
  so it means something else for a block like this). The kernel ignores it and never writes it.
- **Don't host a non-IR effect on an IR block.** HX draws an IR block's own page layout: knob 1 is
  the IR selector (it scrolled the stored IRs whatever its label), some knobs never appear, and
  anything but an IR number on knob 1 froze the controls. Click now takes over the mono
  Mod/Chorus Echo delay, which gets ordinary knob pages (`build_click.py`).
- **Leave the instance block alone.** Click writes only DM(12) (its slot number, as NAM's word 12)
  and keeps its state in one of 8 slots in Block 3, claimed per block as NAM claims its slots
  (fresh or taken-over blocks claim a free slot, else one idle for 64 calls, and start from beat 1;
  a ninth simultaneous block passes its input through).
- **Level is built on NAM's ChVol record.** On a chorus's "Mix" record its value never reached the
  kernel. Tempo is a float knob too (20.0..300.0, one decimal shown): as a 281-entry list (stock lists have at most
  21) the page holding it was not drawn.

## Doom Chug (`doomchug/`)

**In the default image and working on the unit (2026-11-10)**, on the mono Pocket Fuzz. The Chug knob
does almost nothing audible there except lower the level: not investigated (the thud decays in about
0.15 s, so at low Rate it mostly turns the drone down between steps).

A low, dark four-voice drone generator that ignores the guitar, made to feed the glitch effects. Saws on root, sharp root, fifth and octave; every pitch stays between 110 Hz (low A) and 440 Hz. Each step (Rate, 0.05 to 8 a second) moves the Pattern, gives each voice a new random pitch target and LFO speed, and restarts the Chug thud. Knobs: Key, Pattern, Rate, Drift, Warble, Chug, Tone, Level; the input passes through untouched. A resident kernel, not an overlay, because it is meant to run beside Ottobit and a swap costs about 28,000 cycles on the unit. 360 instructions, 77 data words, one slot (a second block passes through), every constant an immediate; worst 2,743 cycles a call in ssim. `doomchug_kernel.py --check` (part of `make sharc-check`) requires every output word to equal the C reference's; `test_doomchug.c` checks pitch range, patterns, block sizes and hostile input.

Knob words: DM(5) Key (int 0..11), DM(6) Pattern (int 0..8), DM(7) Rate, DM(8) Drift, DM(9) Warble,
DM(10) Chug, DM(11) Tone (all 0..1), DM(13) Level (0..1).

## Drum Chapel (`drumchapel/`)

A drum machine block (an overlay on the mono Ratchet, tempo-synced; HANDOVER.md, "Five new overlay effects"). The
guitar passes at exactly unity; four voices are added: kick, snare, hat and tom, synthesised but for the Acoustic
kit's sampled kick and snare. Click's timing: an
integer phase, so every sixteenth lands on its exact sample for ever; the first sample after reset is step 0.

**Grooves.** Groove 0, **Classic**, is the 20 original one-bar patterns (Rock, Half-Time, ... Fill). Grooves 1..11
are families of longer grooves converted from a folder of MIDI drum loops by `drumchapel/grooves.py FOLDER`, which
writes `drumchapel/grooves_data.h`. That pack is licensed and this repository is public, so the file is git-ignored
and must never be committed; no committed file names a loop or carries its notes. Without it (a fresh clone), the
reference, tests, kernel check and image build all still work and every Groove plays the Classic patterns (as does
a family the folder lacks). The converter quantises every hit to the nearest sixteenth, keeps each loop's whole
length and meter (up to 384 sixteenths), drops ghost notes (velocity under 40) and maps the kit's notes to the
voices (its docstring has the map: cymbals and open hats play the hat voice with the open decay; four tom pitches).

**Knobs.** Time (the host delay's, synced to tap tempo), Groove (list: Classic + 11 families), Pattern ("1".."20":
the Classic pattern, or the family's variation, Pattern mod its size), Kit (Boom, Punch, Tick, Bit, Doom, Eighty, Acoustic),
Kick (also the toms' level), Snare, Hat, Swing (odd sixteenths late by up to a third), Level. Knob words: DM(5) Time
s/beat, DM(6) Pattern (int 0..19), DM(7) Kit (int 0..6), DM(8) Kick, DM(9) Snare, DM(10) Hat, DM(11) Swing,
DM(13) Level (0..1), DM(14) Groove (int 0..11).

**Playing a groove.** The step counter wraps at the groove's length. A step looks its groove up when it falls and
continues at (step mod the new length), so Groove or Pattern changes mid-play never restart the count or move the
timing. Every length is a multiple of four, so the swing's odd steps stay odd.

**The bank** (`drumchapel_bank()`, the same words in the reference, the check and the image): 240 directory words
(Groove x Pattern: first step << 9 | length), then the steps four to a word, one byte each: bit 0 kick, 1 snare,
2 hat, 3 tom, 4 open (the hat voice plays the kit's open-hat definition), bits 5-6 the tom's pitch (high, mid, low,
floor: x1, x0.8, x0.64, x0.5 the kit's tom rate). 3,247 words with the converted pack, 320 with Classic only. On
the unit it sits inside Blob 0 in DDR2, right after Geiger's curves, and the kernel reads it only when a step falls
(the directory word and one step word): it is never copied into the overlay region.

**Kits.** Each kit is five voice definitions (kick, snare, closed hat, tom, open hat) plus its drive and clip, in
`drumchapel.c`: Boom's toms long sines, Punch's swept with a tick, Tick's bongo-like, Bit's falling squares, Doom's
tuned way down (floor ~28 Hz) and through its fuzz, Eighty's synth-drum sweeps, gated like its snare.

**Acoustic** (kit 6) plays recorded samples for its kick and snare; its hat, tom and open hat are synthesised (a
little metal under the hat's noise, a short-drop tom with a dark skin noise; its open hat, which also plays every
cymbal of the grooves, is the closed hat a little open: the same tone, 1.75 x its decay, 0.7 x its level, so the
crash and ride on every eighth stay short, with no sustained wash). The samples come from
the user's own bounces (single hits, possibly of a commercial drum instrument), converted locally by
`drumchapel/samples.py KICK SNARE` into `drumchapel/samples_data.h`, which is **git-ignored and must never be
committed** (the repository is public); no committed file holds a sample. Without it Acoustic's kick and snare are
Punch's synthesised ones and everything still builds and checks. The converter (numpy): mono (the channels' mean),
48 kHz through a fixed Kaiser-windowed sinc, the start at the quietest sample in the millisecond before the onset
(30 % of the peak), the end 5 ms before the high band (first difference, 10 ms windows) next rises 6 dB over its
quietest point (the next hit in the bounce), a raised-cosine fade over the last 30 %, both normalised to full scale,
16 bits. With the user's two files: kick 10,844 samples (226 ms; the bounce's next kick starts at 238 ms, so a
longer tail was not there to keep), snare 10,999 (229 ms, from its onset 25.4 ms in, cut before a noise burst at
260 ms). 48 kHz was kept: both together are 10,922 words, well inside the Blob 0 buffer, so a lower rate would buy
nothing. The table: 16-bit samples, two to a word (sample i in word i / 2, its low half when i is even; the snare
starts on a word), `drumchapel_samples()`.

A sampled definition is marked by its PD word being 0 (a synthesised one always has PD > 0); its INC word is the
sample's first index, SWEEP its length. A hit plays the sample from its start at the knob's level (Kick or Snare, no
envelope); the voice stops at the sample's end. A retrigger while it sounds crossfades: the sounding hit keeps
playing from where it was, its level falling linearly to 0 over 64 samples (1.3 ms), beside the new one; the largest
output step across a kick retrigger is then smaller than inside a hit (0.09 against a plain restart's 0.68).
Acoustic's chain is nearly transparent: DRIVE 0.25 and COMP 1 / (1.5 x 0.25), so a full-scale sample at Level 1
comes out at its own level, reduced by the 1.5 z - 0.5 z^3 shaper by at most 2 % (0.2 dB) at its very peak; only
stacked hits are limited (the ceiling is COMP x Level: about 2 x Level where kick, snare and tom meet at full
knobs). At the default knobs its rms is like the other kits' (0.15).

**Tests** (`drumchapel/test_drumchapel.c`): Click's exact timing over ten minutes at six tempos; every Classic
pattern's hits; swing; unity pass-through; the kits' character; block sizes and interleaved instances; hostile
input and knobs; Classic **bit for bit as before the grooves** (hashes of all 20 patterns x 6 kits at two
settings, recorded with the three-voice version); the bank's directory; every groove stepped past its length (each
step its count mod the length, the hits its byte says, the wrap); a 29/4 groove for ten minutes; Groove and Pattern
changes mid-play (the count continues, no step moves in time); the four tom pitches falling in every kit and silent
at Kick 0; the open hat outlasting the closed one. The tests that need toms or open hats write their own short
grooves into the bank, so they run without the converted data too. Acoustic: with the samples, its kick and snare
output equals the stored sample x the knob, sample for sample through the kit's chain, at two levels; silence after
the sample's end; retriggers (on the next step, runs of them, a groove) crossfading exactly as specified, and no
larger step than inside a hit; the chain within 2.1 % of the sample; without them, its kick and snare definitions
are Punch's word for word. Every groove runs in Acoustic (steps, hits, a bounded output). The Classic hashes cover
the six synthesised kits, unchanged.

### Drum Chapel on the SHARC (`drumchapel/sharc/`)

`drumchapel_kernel.asm`, checked by `drumchapel_kernel.py --check` (part of `make sharc-check`): every output word
equal to the reference's for 13 fixed settings plus cases picked from the bank (grooves with each tom pitch and
with open hats in their first steps), two instances with every knob moving, a re-created block; then a long run
through a whole 13/4 groove past its wrap with Groove, Pattern and Kit changed mid-play. The bank is loaded into the
simulator at `BANK_CHECK` (kernel_rig's `spec.ext`); the image build puts it in Blob 0 and assembles the kernel
for that address (`place_bank`). The Acoustic samples sit right after the bank (`T_SAMP`; in the check too, loaded
beside it); `place_bank` places both. Cases in Acoustic cover retriggers at 1,200 samples, each voice's end, Kick
and Hat at 0, a groove with toms, and Kit changes into and out of Acoustic in the moving-knob and long runs. 515
instructions, 452 data words (2 slots), worst 6,821 cycles per 16-sample call in ssim (ssim does not model DDR2
latency); before Acoustic 451, 398, 6,620 (the three-voice version: 409, 296, 5,345). A sounding sampled voice reads
one DDR2 word a sample, two while a retrigger crossfades (at most four a sample with kick and snare both fading).
