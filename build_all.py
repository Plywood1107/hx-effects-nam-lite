#!/usr/bin/env python3
"""Build HX Effects firmware 3.80.0 with NAM A2 Lite and the custom effects in one image (the all-in-one image).

usage: python3 build_all.py [HX_Effects_v3.80.0_0xd97239907.hxf] [-o out.hxf] [--with LIST|none] [--nam-host regal|ir] [--no-check]

NAM sits on the mono Regal Bass DI (Distortion > Mono, --nam-host regal, the default since 2026-11-11), not the
1024 IR, so a real IR block can share its preset; Model is a list of User IR slots 1..21. --nam-host ir puts
it back on the 1024 IR (IR > Single, Model 1..128 with the IR names; no other IR block beside it), suffix _NamIR.

With no --with this builds the default image: --with commander,corrupt,ottobit,doomchug (the DEFAULT_EXTRAS
below), build/HX_Effects_v3.80.0_All_Commander_Corrupt_Ottobit_Doomchug.hxf. --with none builds NAM, Click
and Geiger alone, build/HX_Effects_v3.80.0_All.hxf.

  NAM A2 Lite   as build_nam_click.py, but with 2 slots (two NAM blocks at once; a third passes its
                input through) instead of 3, which frees Block 3 for Geiger, and its DDR2 blocks at
                0x296400 (the Blob 0 buffer holds three host graphs: 0x7a000 words). Where it is listed: see --nam-host.
  Click         as build_nam_click.py (Delay > Mono, the mono Mod/Chorus Echo's slot), primitive 0x0128,
                in the top of Block 3.
  Geiger        bit crusher / sample-rate reducer / 16-curve waveshaper (effects/geiger), taking over
                the mono Megaphone (Distortion > Mono > "Geiger"; the stereo Megaphone stays), primitive
                0x012e (zero uses in the stock graphs), code and data in the Block 3 space between
                NAM's slots and Click's data.

  --with commander          adds Commander (square-wave octave fuzz, effects/commander) on the mono
                            Xenomorph Fuzz (Distortion > Mono), primitive 0x0100;
  --with commander,corrupt  and Corrupt (pitch-tracking square synth, effects/corrupt) on Octave Fuzz
                            (Distortion > Legacy), primitive 0x0838;
  ...,ottobit               and Ottobit (sequenced crusher, effects/ottobit) on the mono Bitcrusher, primitive
                            0x2392, as an overlay: code and data inside Blob 0, a resident stub copies them in;
  ...,ottobit,doomchug      and Doom Chug (drone generator, effects/doomchug) on the mono Pocket Fuzz, primitive
                            0x238f, resident in Block 3 (the default set);
  ...,ottobit,syntax        Syntax instead of Doom Chug, on the same Pocket Fuzz slot (dropped: knob turns
                            locked the unit's interface beside Geiger or Ottobit).
  --meter                   the overlays report their cycle cost by sound (diagnostic image).
                With either, NAM keeps 2 slots but puts its d >= 17 rings in DDR2 too (nam_multi.py
                --far-d 17), which frees Block 3 for the extra kernels; the Blob 0 buffer grows to
                0x7b000 words (five host graphs) and NAM's DDR2 slots move up to 0x297400. Geiger,
                Commander and Corrupt are packed in that order between NAM's Block 3 end and Click's data.
                Output build/HX_Effects_v3.80.0_All_Commander[_Corrupt].hxf, manifest
                build/all_commander[_corrupt]_manifest.json.

Each kernel is checked in the simulator first unless --no-check (NAM bit for bit against nam_a2.asm with
2 slots, Click and Geiger bit for bit against their C references at their addresses), and the build
asserts no byte of internal memory is used by two of them.
"""
import hashlib
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, 'tools')
for p in ('tools', 'tools/sharc', 'effects/metronome/sharc', 'effects/geiger/sharc', 'effects/common',
          'effects/commander/sharc', 'effects/corrupt/sharc', 'effects/probe/sharc', 'effects/ottobit/sharc', 'effects/syntax/sharc', 'effects/doomchug/sharc',
          'effects/purewhitey/sharc', 'effects/greasy/sharc', 'effects/drumchapel/sharc', 'effects/drumchapel', 'effects/bethblahem/sharc',
          'effects/puggy/sharc'):
    sys.path.insert(0, os.path.join(HERE, p))

import build_click as bc  # noqa: E402
import build_effects as be  # noqa: E402
import build_nam_click as bnc  # noqa: E402
import grooves as dc_grooves  # noqa: E402  (Drum Chapel's family names; the groove data is grooves_data.h)

STOCK_MD5 = '7c2ebdf1bffb6bcc5f89dda97f91e40c'
NAM_PRIM, CLICK_PRIM, GEIGER_PRIM = 0x9c75, 0x0128, 0x012e
NAM_SLOTS = 2

GEIGER_TAKEOVER = 'HD2_DistMegaphoneMono'
# Display names (what the unit shows) were changed by the user on 2026-11-21: Geiger -> "Bolt, Rocket!", Commander ->
# "Garrrry Tank", Corrupt -> "Quality Polis", Ottobit -> "Bam Crusher". The internal model names (HD2_Dist...) and
# the code's names stay, so presets that already use these blocks keep working.
GEIGER_NAME, GEIGER_DISPLAY = 'HD2_DistGeiger', 'Bolt, Rocket!'
GEIGER_COST = 500                      # measured worst 2,528 of ~150,000 cycles per call (1.7 %), x3
CURVE_NAMES = ['Linear', 'Soft', 'Hard', 'Sine Fold', 'Tri Fold', 'Full Wave', 'Half Wave', 'Steps',
               'Asym', 'Cheby 3', 'Cheby 5', 'Sine', 'Root', 'Spline', 'Ring', 'Gate']
LIST, BOOL = 'list', 'bool'
GEIGER_PARAMS = (   # slot, pid (instance word), template model, template param, display, short, kind, range, default
    (1, 5,  'HD2_AmpLine6Clarity', 'Drive', 'Gain', 'Gain', 'db', (0.0, 36.0), 6.0),
    (2, 6,  'HD2_AmpLine6Clarity', 'Bass', 'Sample Rate', 'Rate', 'hz', (250.0, 48000.0), 12000.0),
    (3, 7,  'HD2_DelayMultiPassMono', 'Pattern', 'Bit Depth', 'Bits', LIST,
     {b: (f'{b} bit' if b == 1 else f'{b} bits') for b in range(1, 17)}, 8),
    (4, 8,  'HD2_FM4SynthOMatic', 'Wave', 'Curve', 'Curve', LIST, dict(enumerate(CURVE_NAMES)), 0),
    (5, 9,  'HD2_AmpLine6Clarity', 'Treble', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.8),
    (6, 10, 'HD2_AmpLine6Clarity', 'Presence', 'Output', 'Output', 'db', (-36.0, 12.0), -6.0),
    (7, 11, 'HD2_AmpLine6Clarity', 'Mid', 'Mix', 'Mix', 'percent', (0.0, 1.0), 1.0),
    (8, 13, 'HD2_AmpLine6Clarity', 'HumSwitch', 'Anti-Alias', 'AntiAls', BOOL, ('Off', 'On'), 0),
)


COMMANDER_TAKEOVER, CORRUPT_TAKEOVER = 'HD2_DistXenomorphFuzzMono', 'HD2_DM4OctaveFuzz'
COMMANDER_PARAMS = (   # as GEIGER_PARAMS; the kernel reads words 5..11 and 13 (effects/commander/sharc)
    (1, 5,  'HD2_AmpLine6Clarity', 'Drive', 'Fuzz', 'Fuzz', 'percent', (0.0, 1.0), 0.7),
    (2, 6,  'HD2_AmpLine6Clarity', 'Bass', 'Sub -1 Oct', 'Sub1', 'percent', (0.0, 1.0), 0.5),
    (3, 7,  'HD2_AmpLine6Clarity', 'Mid', 'Sub -2 Oct', 'Sub2', 'percent', (0.0, 1.0), 0.0),
    (4, 8,  'HD2_AmpLine6Clarity', 'Treble', 'Octave Up', 'OctUp', 'percent', (0.0, 1.0), 0.0),
    (5, 9,  'HD2_AmpLine6Clarity', 'Presence', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.5),
    (6, 10, 'HD2_AmpLine6Clarity', 'ChVol', 'Output', 'Output', 'db', (-36.0, 12.0), -6.0),
    (7, 11, 'HD2_TremoloPatternMono', 'Step1', 'Gate', 'Gate', LIST,
     {k: ('Off' if k == 0 else f'{6 * k - 90} dB') for k in range(11)}, 3),
    (8, 13, 'HD2_DelayCrissCrossMono', 'Shape', 'Dry', 'Dry', LIST, {k: f'{10 * k}%' for k in range(11)}, 0),
)
CORRUPT_PARAMS = (
    (1, 5,  'HD2_AmpLine6Clarity', 'Drive', 'Square', 'Square', 'percent', (0.0, 1.0), 0.0),
    (2, 6,  'HD2_AmpLine6Clarity', 'Bass', 'Master', 'Master', 'percent', (0.0, 1.0), 0.8),
    (3, 7,  'HD2_AmpLine6Clarity', 'Mid', 'Sub', 'Sub', 'percent', (0.0, 1.0), 0.4),
    (4, 8,  'HD2_AmpLine6Clarity', 'Treble', 'Glide', 'Glide', 'knob', (0.0, 1.0), 0.2),
    (5, 9,  'HD2_AmpLine6Clarity', 'Presence', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.6),
    (6, 10, 'HD2_AmpLine6Clarity', 'ChVol', 'Output', 'Output', 'db', (-36.0, 12.0), -6.0),
    (7, 11, 'HD2_DelayMultiPassMono', 'Pattern', 'Root', 'Root', LIST, {0: '-2 Oct', 1: '-1 Oct', 2: 'Unison', 3: '+1 Oct'}, 2),
    (8, 13, 'HD2_FM4SynthOMatic', 'Wave', 'Harmonic', 'Harm', LIST,
     {1: '1x Root', 2: '2x Octave', 3: '3x Fifth', 4: '4x 2 Oct', 5: '5x Third', 6: '6x Fifth', 7: '7x Flat 7', 8: '8x 3 Oct'}, 1),
)
OTTOBIT_PARAMS = (     # as GEIGER_PARAMS; the kernel reads words 5..11 and 13 (effects/ottobit/sharc)
    (1, 5,  'HD2_AmpLine6Clarity', 'Drive', 'Sample Rate', 'Rate', 'hz', (250.0, 48000.0), 8000.0),
    (2, 6,  'HD2_DelayMultiPassMono', 'Pattern', 'Bit Depth', 'Bits', LIST,
     {b: (f'{b} bit' if b == 1 else f'{b} bits') for b in range(1, 17)}, 6),
    (3, 7,  'HD2_AmpLine6Clarity', 'Bass', 'Filter', 'Filter', 'knob', (0.0, 1.0), 0.7),
    (4, 8,  'HD2_FM4SynthOMatic', 'Wave', 'Pattern', 'Pattern', LIST, {0: 'Off', **{k: str(k) for k in range(1, 9)}}, 1),
    (5, 9,  'HD2_AmpLine6Clarity', 'Treble', 'Speed', 'Speed', 'hz', (0.5, 16.0), 4.0),
    (6, 10, 'HD2_AmpLine6Clarity', 'Mid', 'Stutter', 'Stutter', 'percent', (0.0, 1.0), 0.2),
    (7, 11, 'HD2_AmpLine6Clarity', 'Presence', 'Output', 'Output', 'db', (-36.0, 12.0), -6.0),
    (8, 13, 'HD2_AmpLine6Clarity', 'ChVol', 'Mix', 'Mix', 'percent', (0.0, 1.0), 1.0),
)
SYNTAX_PARAMS = (      # as GEIGER_PARAMS; the kernel reads words 5..11 and 13 (effects/syntax/sharc)
    (1, 5,  'HD2_AmpLine6Clarity', 'Drive', 'Drive', 'Drive', 'db', (0.0, 36.0), 12.0),
    (2, 6,  'HD2_AmpLine6Clarity', 'Bass', 'Shift', 'Shift', 'hz', (1.0, 1000.0), 150.0),
    (3, 7,  'HD2_FM4SynthOMatic', 'Wave', 'Pattern', 'Pattern', LIST, {0: 'Off', **{k: str(k) for k in range(1, 9)}}, 1),
    (4, 8,  'HD2_AmpLine6Clarity', 'Mid', 'Speed', 'Speed', 'hz', (0.5, 16.0), 4.0),
    (5, 9,  'HD2_AmpLine6Clarity', 'Treble', 'Glide', 'Glide', 'knob', (0.0, 1.0), 0.2),
    (6, 10, 'HD2_AmpLine6Clarity', 'Presence', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.7),
    (7, 11, 'HD2_AmpLine6Clarity', 'ChVol', 'Output', 'Output', 'db', (-36.0, 12.0), -6.0),
    (8, 13, 'HD2_AmpLine6Clarity', 'Sag', 'Mix', 'Mix', 'percent', (0.0, 1.0), 1.0),
)
DOOMCHUG_KEYS = ['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#']
DOOMCHUG_PARAMS = (    # as GEIGER_PARAMS; the kernel reads words 5..11 and 13 (effects/doomchug/sharc)
    (1, 5,  'HD2_DelayMultiPassMono', 'Pattern', 'Key', 'Key', LIST, dict(enumerate(DOOMCHUG_KEYS)), 0),
    (2, 6,  'HD2_FM4SynthOMatic', 'Wave', 'Pattern', 'Pattern', LIST, {0: 'Off', **{k: str(k) for k in range(1, 9)}}, 1),
    (3, 7,  'HD2_AmpLine6Clarity', 'Drive', 'Rate', 'Rate', 'knob', (0.0, 1.0), 0.5),
    (4, 8,  'HD2_AmpLine6Clarity', 'Bass', 'Drift', 'Drift', 'knob', (0.0, 1.0), 0.35),
    (5, 9,  'HD2_AmpLine6Clarity', 'Mid', 'Warble', 'Warble', 'knob', (0.0, 1.0), 0.5),
    (6, 10, 'HD2_AmpLine6Clarity', 'Treble', 'Fuzz', 'Fuzz', 'knob', (0.0, 1.0), 0.3),
    (7, 11, 'HD2_AmpLine6Clarity', 'Presence', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.25),
    (8, 13, 'HD2_AmpLine6Clarity', 'ChVol', 'Level', 'Level', 'percent', (0.0, 1.0), 0.5),
)
BETHBLAHEM_PARAMS = (    # the kernel reads words 5..11 and 13 (effects/bethblahem/sharc); Octave ints 0..4 = octaves down
    (1, 5,  'HD2_DelayMultiPassMono', 'Pattern', 'Octave', 'Octave', LIST,
     {0: '0 Oct', 1: '-1 Oct', 2: '-2 Oct', 3: '-3 Oct', 4: '-4 Oct'}, 2),
    (2, 6,  'HD2_AmpLine6Clarity', 'Drive',    'Glide',   'Glide',   'knob',    (0.0, 1.0), 0.4),
    (3, 7,  'HD2_AmpLine6Clarity', 'Bass',     'Vibrato', 'Vibrato', 'knob',    (0.0, 1.0), 0.3),
    (4, 8,  'HD2_AmpLine6Clarity', 'Mid',      'Rate',    'Rate',    'knob',    (0.0, 1.0), 0.4),
    (5, 9,  'HD2_AmpLine6Clarity', 'Treble',   'Growl',   'Growl',   'knob',    (0.0, 1.0), 0.5),
    (6, 10, 'HD2_AmpLine6Clarity', 'Presence', 'Sub',     'Sub',     'percent', (0.0, 1.0), 0.3),
    (7, 11, 'HD2_AmpLine6Clarity', 'Sag',      'Dry',     'Dry',     'percent', (0.0, 1.0), 0.7),
    (8, 13, 'HD2_AmpLine6Clarity', 'ChVol',    'Level',   'Level',   'percent', (0.0, 1.0), 0.7),
)
PUGGY_STEPS = ['1/2', '1/4.', '1/4', '1/4T', '1/8.', '1/8', '1/8T', '1/16.', '1/16', '1/16T', '1/32']
PUGGY_WILDS = ['All', 'Gentle', 'Rhythm', 'Mean', 'Low', 'Dirt', 'Chop', 'Octave', 'Crush', 'Filter', 'Fuzz']
PUGGY_PARAMS = (    # slot 1 is Time with the tempo-sync pair (sync_knob_params); the kernel reads words 5..11 and 13
    (2, 6,  'HD2_DelayMultiPassMono', 'Pattern', 'Step', 'Step', LIST, dict(enumerate(PUGGY_STEPS)), 8),
    (3, 7,  'HD2_AmpLine6Clarity', 'Drive', 'Chance', 'Chance', 'percent', (0.0, 1.0), 0.5),
    (4, 8,  'HD2_FM4SynthOMatic', 'Wave', 'Wild', 'Wild', LIST, dict(enumerate(PUGGY_WILDS)), 0),
    (5, 9,  'HD2_TremoloPatternMono', 'Step1', 'Hold', 'Hold', LIST, {k: ('1 step' if k == 1 else f'{k} steps') for k in range(1, 9)}, 1),
    (6, 10, 'HD2_DelayCrissCrossMono', 'Shape', 'Seed', 'Seed', LIST, {0: 'Random', **{k: str(k) for k in range(1, 17)}}, 0),
    (7, 11, 'HD2_AmpLine6Clarity', 'Bass', 'Mix', 'Mix', 'percent', (0.0, 1.0), 1.0),
    (8, 13, 'HD2_AmpLine6Clarity', 'ChVol', 'Level', 'Level', 'percent', (0.0, 1.0), 1.0),
)
GREASY_PARAMS = (    # the kernel reads words 5..11 and 13 (effects/greasy/sharc)
    (1, 5,  'HD2_DelayMultiPassMono', 'Pattern', 'Octave', 'Octave', LIST, {0: '-2 Oct', 1: '-1 Oct', 2: 'Unison', 3: '+1 Oct'}, 1),
    (2, 6,  'HD2_AmpLine6Clarity', 'Drive', 'Glide', 'Glide', 'knob', (0.0, 1.0), 0.3),
    (3, 7,  'HD2_AmpLine6Clarity', 'Bass', 'Drift', 'Drift', 'knob', (0.0, 1.0), 0.25),
    (4, 8,  'HD2_AmpLine6Clarity', 'Mid', 'Warble', 'Warble', 'knob', (0.0, 1.0), 0.35),
    (5, 9,  'HD2_AmpLine6Clarity', 'Treble', 'Fuzz', 'Fuzz', 'knob', (0.0, 1.0), 0.3),
    (6, 10, 'HD2_AmpLine6Clarity', 'Presence', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.35),
    (7, 11, 'HD2_AmpLine6Clarity', 'Sag', 'Dry', 'Dry', 'percent', (0.0, 1.0), 1.0),
    (8, 13, 'HD2_AmpLine6Clarity', 'ChVol', 'Level', 'Level', 'percent', (0.0, 1.0), 0.5),
)
DRUMCHAPEL_PATTERNS = ['Rock', 'Half-Time', 'Four Floor', 'Disco', 'Shuffle', 'Motorik', 'Break', 'Funk', 'Boom Bap',
                       'Bossa', 'One Drop', 'Punk', 'Blast', 'Sludge', 'Trap', 'Two-Step', 'Gallop', 'Hats Only',
                       'Kick Only', 'Fill']
DRUMCHAPEL_KITS = ['Boom', 'Punch', 'Tick', 'Bit', 'Doom', 'Eighty', 'Acoustic']   # Acoustic: sampled kick and snare
# (effects/drumchapel/samples.py; samples_data.h, Punch's synthesised ones without it)
# Groove 0 plays the 20 patterns above; 1..11 the families converted by effects/drumchapel/grooves.py (Classic when
# its git-ignored output is missing), Pattern then the variation (mod the family's size)
DRUMCHAPEL_GROOVES = ['Classic'] + [name for name, _ in dc_grooves.FAMILIES]
DRUMCHAPEL_PARAMS = (   # slot 1 is Time with the tempo-sync pair (sync_knob_params); the kernel reads words 5..11, 13, 14
    (2, 14, 'HD2_TremoloPatternMono', 'Step1', 'Groove', 'Groove', LIST, dict(enumerate(DRUMCHAPEL_GROOVES)), 0),
    (3, 6,  'HD2_DelayMultiPassMono', 'Pattern', 'Pattern', 'Pattern', LIST, {k: str(k + 1) for k in range(20)}, 0),
    (4, 7,  'HD2_FM4SynthOMatic', 'Wave', 'Kit', 'Kit', LIST, dict(enumerate(DRUMCHAPEL_KITS)), 0),
    (5, 8,  'HD2_AmpLine6Clarity', 'Bass', 'Kick', 'Kick', 'percent', (0.0, 1.0), 0.8),
    (6, 9,  'HD2_AmpLine6Clarity', 'Mid', 'Snare', 'Snare', 'percent', (0.0, 1.0), 0.7),
    (7, 10, 'HD2_AmpLine6Clarity', 'Treble', 'Hat', 'Hat', 'percent', (0.0, 1.0), 0.5),
    (8, 11, 'HD2_AmpLine6Clarity', 'Presence', 'Swing', 'Swing', 'percent', (0.0, 1.0), 0.0),
    (9, 13, 'HD2_AmpLine6Clarity', 'ChVol', 'Level', 'Level', 'percent', (0.0, 1.0), 0.5),
)
assert len(DRUMCHAPEL_GROOVES) == 12 and len(DRUMCHAPEL_KITS) == 7
PUREWHITEY_PARAMS = (  # the kernel reads words 5..11 and 13 (effects/purewhitey/sharc); one slot, a 4,096-word ring in DDR2
    (1, 5,  'HD2_FM4SynthOMatic', 'Wave', 'Mode', 'Mode', LIST,
     {0: 'Repeat', 1: 'Random', 2: 'Reverse', 3: 'Trigger', 4: 'Sq Trigger', 5: 'Square', 6: 'Up', 7: 'Down'}, 0),
    (2, 6,  'HD2_AmpLine6Clarity', 'Drive', 'Time', 'Time', 'knob', (0.0, 1.0), 0.5),
    (3, 7,  'HD2_AmpLine6Clarity', 'Bass', 'Func', 'Func', 'knob', (0.0, 1.0), 0.5),
    (4, 8,  'HD2_AmpLine6Clarity', 'Mid', 'Sens', 'Sens', 'knob', (0.0, 1.0), 0.5),
    (5, 9,  'HD2_AmpLine6Clarity', 'Treble', 'Tone', 'Tone', 'knob', (0.0, 1.0), 0.8),
    (6, 10, 'HD2_AmpLine6Clarity', 'Presence', 'Dry', 'Dry', 'percent', (0.0, 1.0), 1.0),
    (7, 11, 'HD2_AmpLine6Clarity', 'Sag', 'Mix', 'Mix', 'percent', (0.0, 1.0), 1.0),
    (8, 13, 'HD2_AmpLine6Clarity', 'ChVol', 'Level', 'Level', 'percent', (0.0, 1.0), 1.0),
)
# the Block 3 kernels after NAM, in packing order: model, name, display, Entry 0 cost, primitive, knobs, entry symbol
EFFECTS = {
    'geiger': dict(takeover=GEIGER_TAKEOVER, name=GEIGER_NAME, display=GEIGER_DISPLAY, cost=GEIGER_COST, prim=GEIGER_PRIM,
                   params=GEIGER_PARAMS, entry='GEIGER_ENTRY'),
    'commander': dict(takeover=COMMANDER_TAKEOVER, name='HD2_DistCommander', display='Garrrry Tank', cost=700, prim=0x0100,
                      params=COMMANDER_PARAMS, entry='COMMANDER_ENTRY'),   # measured worst 3,441 cycles of ~150,000 (2.3 %)
    'corrupt': dict(takeover=CORRUPT_TAKEOVER, name='HD2_DistCorrupt', display='Quality Polis', cost=700, prim=0x0838,
                    params=CORRUPT_PARAMS, entry='CORRUPT_ENTRY'),         # measured worst 3,545
    # an overlay: the code and data travel inside Blob 0; only its stub is in the boot stream (ovl_stub_kernel.py)
    'ottobit': dict(takeover='HD2_DistBitcrusherMono', name='HD2_DistOttobit', display='Bam Crusher', cost=700, prim=0x2392,
                    params=OTTOBIT_PARAMS, entry='OVL_ENTRY_OTTOBIT'),   # measured mean 2,450 cycles of ~150,000
    'syntax': dict(takeover='HD2_DistPocketFuzzMono', name='HD2_DistSyntax', display='Syntax', cost=1200, prim=0x238F,
                   params=SYNTAX_PARAMS, entry='OVL_ENTRY_SYNTAX'),   # measured worst 5,670
    # an overlay since 2026-11-17 (it was resident, to run beside Ottobit without a swap; the five new overlays needed its room)
    'doomchug': dict(takeover='HD2_DistPocketFuzzMono', name='HD2_DistDoomChug', display='Doom Chug', cost=500, prim=0x238F,
                     params=DOOMCHUG_PARAMS, entry='OVL_ENTRY_DOOMCHUG'),
    # the new overlays (2026-11-17), each on a host the user chose, mono version only
    'bethblahem': dict(takeover='HD2_PitchTwinHarmonyMono', name='HD2_PitchBethblahem', display='Bethblahem', cost=700, prim=0x0833,
                       params=BETHBLAHEM_PARAMS, entry='OVL_ENTRY_BETHBLAHEM'),   # measured worst 3,535 cycles in ssim
    'puggy': dict(takeover='HD2_DelaySweepEchoMono', name='HD2_DelayPuggyPuncher', display='Puggy Puncher', cost=700, prim=0x045E,
                  params=PUGGY_PARAMS, entry='OVL_ENTRY_PUGGY', sync=True),   # tempo-synced like Click; worst 2,627 cycles in ssim
    'greasy': dict(takeover='VIC_PitchBoctaverMono', name='HD2_PitchGreasyStrangler', display='Greasy Strangler', short='Greasy Strangler',
                   cost=700, prim=0x2AB6, params=GREASY_PARAMS, entry='OVL_ENTRY_GREASY'),   # worst 2,788 cycles in ssim
    'drumchapel': dict(takeover='VIC_DelayRatchetMono', name='HD2_DelayDrumChapel', display='Drum Chapel', cost=700, prim=0x0104,   # not 0x23ac: that slot shares its routine with
                       # 0x23ab (another mode of one function), which only Nonlinear uses; hooking it froze Nonlinear (2026-11-27)
                      
                       params=DRUMCHAPEL_PARAMS, entry='OVL_ENTRY_DRUMCHAPEL', sync=True,
                       # Ratchet is 'followEnable' (the unit keeps the block running and hands it the on/off state):
                       # dropped here and cleared in its Entry 0 Table 2 row (word 36), so the footswitch bypasses
                       # Drum Chapel like any other delay (the Entry 3 field alone did not, 2026-11-18)
                       meta_drop=('followEnable', 'loadBypassed'), meta_type='digital',
                       plain_delay=True),   # block type 0x18 -> 0x08 and off the app's special-delay list (tools/special_delay_patch.py); what made the footswitch work on the unit   # Click's timing; grooves bank in Blob 0
    'purewhitey': dict(takeover='HD2_DistTycoctaviaFuzzMono', name='HD2_DistPureWhitey', display='Pure Whitey', cost=700, prim=0x2AAC,
                       params=PUREWHITEY_PARAMS, entry='OVL_ENTRY_PUREWHITEY'),   # worst 2,547 cycles in ssim; ring in DDR2
    # --probe: a diagnostic on Geiger's host instead of Geiger (effects/probe/sharc/probe_kernel.asm)
    'probe': dict(takeover=GEIGER_TAKEOVER, name='HD2_DistProbe', display='Probe', cost=300, prim=GEIGER_PRIM,
                  params=GEIGER_PARAMS, entry='PROBE_ENTRY'),
}
BLOB0_WORDS_5 = 0x7B000                # five host graphs
BLOB0_WORDS_OVL = 0x7E000              # six host graphs and the overlay payload (Ottobit alone)
# The overlays (one shared internal region, swapped in by ovl_stub_kernel); those with a DDR2 ring take RING_N x NSLOTS words
# each, above NAM's slots, in this order. With more overlays than Ottobit, Blob 0's buffer takes all the DDR2 left below
# DDR2_LIMIT (the old Heap 6 end, under the User IR store at 0x2a912c) after NAM's slots and the rings.
OVERLAYS = ('ottobit', 'syntax', 'doomchug', 'purewhitey', 'greasy', 'drumchapel', 'bethblahem', 'puggy')
# The cost the unit is told for each overlay effect (Entry 0 Table 1; NAM's DSP_COST scale). Alone an overlay needs
# only its kernel (a few %), but with two or more in a preset each is copied in on every call: about 25 cycles a word
# (meter, 2026-11-10: ~28,000 cycles for ~1,100 words, ~19 % of a call). At a flat 700 the unit let Commander + Doom
# Chug + Drum Chapel + Pure Whitey into one preset and the DSP locked up (2026-11-18); a flat 2,300 was too strict
# (user). So: about 300 for the kernel plus 1 per word copied in (code + data, this build's manifest), to the 50.
OVL_COST = dict(ottobit=1300, syntax=1300, doomchug=900, bethblahem=1000, puggy=1000, greasy=1000, drumchapel=1550,
                purewhitey=1100)
for _k in OVERLAYS:
    EFFECTS[_k]['cost'] = OVL_COST[_k]
RING_OVERLAYS = ('ottobit', 'purewhitey')
DDR2_LIMIT = 0x2A8DF6
GEIGER_CURVES_WORDS = 16 * 65
NAM_FAR_D_EXTRA = 17                   # NAM's layout when the extra kernels are in


class Kernel:
    """One Block 3 kernel behind one interface: Geiger's own module, or a kernel_rig Spec."""

    def __init__(self, key):
        self.key = key
        if key == 'geiger':
            import geiger_kernel as m
            self.places = m.PLACES
            self._asm = m.assemble
            self._check = lambda sec, pl: m.check(sec, pl)
        elif key == 'ovl_stub':
            import ovl_stub_kernel as m
            self.places = m.SPEC.places
            self._asm = m.SPEC.assemble
            self._check = lambda sec, pl: m.check(sec, pl)
        elif key == 'commander_corrupt':                 # both in one kernel, two entry points
            import commander_corrupt_kernel as m
            self.places = m.SPEC.places
            self._asm = m.SPEC.assemble
            self._check = lambda sec, pl: m.check(sec, pl)
        else:
            m = __import__(f'{key}_kernel')
            self.places = m.SPEC.places
            self._asm = m.SPEC.assemble
            self._check = lambda sec, pl: m.check(sec, pl)
        self.place = None

    def measure(self, data0):
        """(data end, instructions) with the data at data0."""
        self.places['probe'] = (0xC4EF8, 0xC5554, data0)
        _, secs, _, end, data = self._asm('probe')
        return data[1], end - 0xC4EF8

    def set_place(self, code48, code48_end, data0):
        self.place = f'b3{self.key[0]}' if self.key == 'geiger' else 'b3'
        self.places[self.place] = (code48, code48_end, data0)

    def assemble(self):
        return self._asm(self.place)

    def check(self, seconds):
        return self._check(seconds, self.place)


def append_blob0(e4, words):   # (unused: words past the last structure froze the unit)
    """Entry 4 with `words` appended to Blob 0 (the blobs after it move up; stock blobs stay)."""
    w4 = list(struct.unpack('<%dI' % (len(e4) // 4), e4))
    nblobs, dir_off = w4[2], w4[3]
    b0_len, b0_off = w4[dir_off], w4[dir_off + 1]
    end = b0_off + b0_len
    assert w4[4] == b0_off and all(w4[dir_off + 2 * k + 1] + w4[dir_off + 2 * k] <= dir_off or
                                   w4[dir_off + 2 * k + 1] >= end for k in range(1, nblobs))
    for k in range(1, nblobs):
        if w4[dir_off + 2 * k + 1] >= end:
            w4[dir_off + 2 * k + 1] += len(words)
    w4[dir_off] = b0_len + len(words)
    w4 = w4[:end] + list(words) + w4[end:]
    w4[5] = len(w4)
    return struct.pack('<%dI' % len(w4), *w4), b0_len


def compact_blob0(pa, e4, stock_len):
    """Entry 4 with Blob 0's dead composite tables removed. patch_amp.clone_composite_in_blob0 appends, per added host
    graph, a whole new copy of the composite table (~3,150 words) before the new composite, and the old copy stays
    behind unused; with a dozen added graphs that is most of the DDR2 the overlays need. This keeps Blob 0's stock part
    (up to stock_len) as it is and rewrites everything after it as one table (the live one) followed by every added
    composite, each relocated as clone_composite_in_blob0 relocates it. The blobs after Blob 0 move with its new length."""
    w4 = list(struct.unpack('<%dI' % (len(e4) // 4), e4))
    nblobs, d = w4[2], w4[3]
    pairs = [(w4[d + 2 * k], w4[d + 2 * k + 1]) for k in range(nblobs)]
    b0 = list(w4[pairs[0][1]: pairs[0][1] + pairs[0][0]])
    n, ctab = b0[0xf], b0[0x10]
    tab = b0[ctab: ctab + 7 * n]
    added = [i for i in range(n) if tab[7 * i + 3] >= stock_len]
    assert added and all(tab[7 * i + 3] < stock_len for i in range(n) if i not in added)
    new = b0[:stock_len]
    new_ctab = len(new)
    new += [0] * (7 * n)
    for i in added:
        h = tab[7 * i: 7 * i + 7]
        start, end = h[3], h[5] + 4 * h[4]
        sl = b0[start:end]
        delta = len(new) - start
        for m in range(h[2]):
            rb = 20 * m
            c_rel = sl[rb + 2] - start
            for j in range(sl[rb + 1] >> 1):
                if start <= sl[c_rel + 3 * j + 1] <= end:
                    sl[c_rel + 3 * j + 1] += delta
            for col in (2, 8, 10, 12):
                if start <= sl[rb + col] <= end:
                    sl[rb + col] += delta
        tab[7 * i + 3] = h[3] + delta
        tab[7 * i + 5] = h[5] + delta
        new += sl
    new[new_ctab: new_ctab + 7 * n] = tab
    new[0x10] = new_ctab
    err = pa.sharc_blob0_check(new, pa.DEV.BLOB0_MAX_WORDS)
    assert err is None, err
    rest = [list(w4[off: off + ln]) for ln, off in pairs[1:]]
    order = sorted(range(nblobs), key=lambda k: pairs[k][1])
    assert order[0] != 0 and pairs[0][1] == d + 2 * nblobs, 'Blob 0 is not right after the directory'
    head = w4[:d]
    cur = d + 2 * nblobs
    newpairs = [None] * nblobs
    body = []
    for k in order:
        words = new if k == 0 else rest[k - 1]
        if pairs[k][1] < d:                              # a stock blob before the directory: unchanged
            newpairs[k] = pairs[k]
            continue
        newpairs[k] = (len(words), cur)
        body += words
        cur += len(words)
    out = head + [x for pr in newpairs for x in pr] + body
    out[4] = newpairs[0][1]
    out[5] = len(out)
    print(f'[+] Entry 4: Blob 0 compacted from {len(b0):#x} to {len(new):#x} words ({len(added)} added composites, '
          f'one table)')
    return struct.pack('<%dI' % len(out), *out)


def b3_normal(a48):
    """The first normal (32-bit) word at or after 48-bit address a48 in Block 3."""
    return 0xE0000 + ((a48 - 0xE0000) * 3 + 1) // 2


def b3_code48(normal):
    """The first even 48-bit address at or after normal word `normal` in Block 3."""
    return 0xE0000 + (((normal - 0xE0000) * 2 + 2) // 3 + 1 & ~1)


def ldr_l32(pa, addr, words, zero_fill):
    """LDR blocks loading `words` at `addr`: one INIT_L32, or, with zero_fill, runs of 8+ zero words as
    ZERO_LDATA blocks (tag 1: a 3-word header, no payload; the stock boot stream has 81 of them) and the
    rest as INIT_L32. Entry 2 must stay within its 512 KiB partition."""
    if not zero_fill:
        return pa.pack_init_l32(addr, words)
    out, i, n = [], 0, len(words)
    while i < n:
        j = i
        while j < n and words[j] == 0:
            j += 1
        if j - i >= 8 or (j == n and j > i):
            out += [1, j - i, addr + i]
            i = j
            continue
        k = i
        while k < n:                                  # up to the next run of 8+ zeros
            if words[k] == 0:
                z = k
                while z < n and words[z] == 0:
                    z += 1
                if z - k >= 8 or z == n:
                    break
                k = z
            else:
                k += 1
        out += pa.pack_init_l32(addr + i, words[i:k])
        i = k
    return out


def f2u(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def knob_params(pa, e3, info, spec):
    """Per knob the template's record (type, state) with our range, default and display metadata."""
    out = []
    for slot, pid, mname, pname, disp, short, kind, rng, dflt in spec:
        m = pa.find_model(info, mname)
        p = next(p for p in m['params'] if p['name'] == pname)
        raw = list(struct.unpack_from('<5I3I', e3, p['off']))
        raw[4] = slot
        meta = [('displayName', 7, disp), ('displayNameShort', 7, short)]
        if kind == LIST:
            assert p['type'] == 2 and len(rng) <= 21, f'{mname}.{pname}: not an int, or a list longer than stock'
            raw[5], raw[6], raw[7] = min(rng), max(rng), dflt
            meta = [('displayType', 7, 'list')] + meta + [(str(k), 7, v) for k, v in sorted(rng.items())]
        elif kind == BOOL:
            assert p['type'] == 1, f'{mname}.{pname} is not a bool'
            raw[5], raw[6], raw[7] = 0, 0, dflt
            meta += [('false', 7, rng[0]), ('true', 7, rng[1])]
        else:
            assert p['type'] == 3, f'{mname}.{pname} is not a float'
            raw[5], raw[6], raw[7] = f2u(rng[0]), f2u(rng[1]), f2u(dflt)
            meta = [('displayType', 7, kind)] + meta
        out.append({'slot': slot, 'pid': pid, 'role': 'direct', 'name': pname, 'type': p['type'],
                    'op': pa.NAM_INPUT_OP[p['type']], 'raw': raw, 'meta': meta,
                    'state': bc._state_of(pa, e3, info, m, pname), 'default_word': raw[7]})
    assert [p['slot'] for p in out] == list(range(1, len(out) + 1))
    assert len({p['name'] for p in out}) == len(out), 'two knobs share a parameter name'
    return out


from nam_host import NAM_HOSTS, NAM_LIST_SLOTS, nam_off_ir  # noqa: E402,F401  (shared with build_nam_click.py)


def sync_knob_params(pa, e3, info, spec):
    """An effect on a tempo-synced delay host, as Click: slot 1 is Time with the delay's tempo-sync pair (its
    SyncSelect1 and TempoSync1, copied from Mod/Chorus Echo as build_click.py does, appended after the knobs), and
    build_click.click_host_blob computes the beat length in seconds into word 5. `spec` holds the other knobs, slots 2..n,
    in knob_params' form; slot 1 in it, if present, is ignored (Time is the delay's own)."""
    knobs = [t for t in spec if t[0] != 1]
    n = len(knobs) + 1
    sel, syn = n + 1, n + 2
    saved = bc.SYNC_PARAMS, bc.CLICK_PARAMS
    bc.SYNC_PARAMS = ((1, 'Time', 'time', (0.1, 4.0, 0.5), {'coupledIndex': str(sel), 'toggleSelectIndex': str(syn)}),
                      (sel, 'SyncSelect1', 'select', (1, 19, 6), {'coupledIndex': '1', 'toggleSelectIndex': str(syn)}),
                      (syn, 'TempoSync1', 'sync', (0, 0, 1), {}))
    bc.CLICK_PARAMS = tuple(knobs)
    try:
        out = bc.click_params(pa, e3, info)
    finally:
        bc.SYNC_PARAMS, bc.CLICK_PARAMS = saved
    assert [p['slot'] for p in out] == list(range(1, syn + 1)) and out[0]['role'] == 'time'
    return out


DEFAULT_EXTRAS = ('commander', 'corrupt', 'ottobit', 'doomchug', 'purewhitey', 'greasy', 'drumchapel', 'bethblahem', 'puggy')   # what a plain build_all.py builds


def main():
    argv = sys.argv[1:]
    if '-h' in argv or '--help' in argv:
        sys.exit(__doc__)
    probe = '--probe' in argv
    with_arg = argv[argv.index('--with') + 1] if '--with' in argv else None
    extras = [] if with_arg == 'none' or (probe and with_arg is None) else \
        with_arg.split(',') if with_arg else list(DEFAULT_EXTRAS)
    known = [k for k in EFFECTS if k not in ('geiger', 'probe')]
    if any(k not in known for k in extras) or len(set(extras)) != len(extras) or ('corrupt' in extras and 'commander' not in extras) \
            or sum(EFFECTS[k]['takeover'] == t for k in extras for t in {EFFECTS[x]['takeover'] for x in extras}) != len(extras):
        sys.exit('build_all.py: --with takes none or a list of ' + ', '.join(known) + ' (corrupt needs commander; one effect per host)')
    extras = [k for k in known if k in extras]           # the order the kernels and models are built in
    overlays = [k for k in extras if k in OVERLAYS]      # sharing one internal region
    overlay = bool(overlays)
    if probe and extras:
        sys.exit('build_all.py: --probe goes alone')
    first = 'probe' if probe else 'geiger'
    fx = [first] + extras                                # the models after NAM and Click
    # the Block 3 kernels after NAM, in packing order: Commander and Corrupt together share one kernel
    blocks = [first] + (['commander_corrupt'] if 'corrupt' in extras else [k for k in extras[:1] if k not in OVERLAYS])
    if overlay:
        blocks += ['ovl_stub']                           # the overlays' shared region, then their resident stub
    entries_of = {k: [k] for k in blocks}
    entries_of['commander_corrupt'] = ['commander', 'corrupt']
    entries_of['ovl_stub'] = overlays
    stock = os.path.abspath(argv.pop(0)) if argv and not argv[0].startswith('-') else \
        os.path.join(HERE, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
    if not os.path.isfile(stock) or hashlib.md5(open(stock, 'rb').read()).hexdigest() != STOCK_MD5:
        sys.exit(f'{stock}: missing or not the HX Effects 3.80.0 firmware (MD5 {STOCK_MD5}).')
    meter = '--meter' in argv                            # the overlays report their real cycle cost by sound
    host_arg = argv[argv.index('--nam-host') + 1] if '--nam-host' in argv else 'regal'
    if host_arg not in NAM_HOSTS:
        sys.exit('build_all.py: --nam-host takes ' + ' or '.join(NAM_HOSTS))
    nam_host = NAM_HOSTS[host_arg]
    nam_takeover = nam_host or be.TAKEOVER
    suffix = '_Probe' if probe else ''.join('_' + k.capitalize() for k in extras) + ('_Meter' if meter else '') + \
        ('' if nam_host else '_NamIR')
    out = os.path.abspath(argv[argv.index('-o') + 1]) if '-o' in argv else \
        os.path.join(HERE, 'build', f'HX_Effects_v3.80.0_All{suffix}.hxf')
    build = os.path.join(HERE, 'build')
    os.makedirs(build, exist_ok=True)
    nam_asm = os.path.join(build, 'nam_lite_2slots.asm' if not extras else f'nam_lite_2slots_fd{NAM_FAR_D_EXTRA}.asm')
    image = os.path.join(build, f'all{suffix.lower()}.l6ia')
    manifest_path = os.path.join(build, f'all{suffix.lower()}_manifest.json')
    OVL_MODS = {k: __import__(f'{k}_kernel') for k in overlays}
    ring_words = sum(OVL_MODS[k].RING_N * OVL_MODS[k].NSLOTS for k in overlays if k in RING_OVERLAYS)
    if overlays and overlays != ['ottobit'] and overlays != ['ottobit', 'syntax']:
        blob0_words = (DDR2_LIMIT - ring_words - NAM_SLOTS * 0x5000 - bnc.BLOB0_BASE) & ~0xFFF
    else:
        blob0_words = BLOB0_WORDS_OVL if overlay else BLOB0_WORDS_5 if extras else bnc.BLOB0_WORDS_ALL
    sdr_base = bnc.BLOB0_BASE + blob0_words            # NAM's DDR2 slots just above the Blob 0 buffer
    env = dict(os.environ, NAM_DEVICE='effects', NAM_SDR_BASE=hex(sdr_base))
    ring0 = sdr_base + NAM_SLOTS * 0x5000                # the overlays' rings, above NAM's slots
    rings = {}
    if overlay:
        import geiger_kernel
        import ovl_stub_kernel
        geiger_kernel.EXT_CURVES = 0x3F0000              # for the check; the real address once Blob 0 is laid out
        at = ring0
        for k in overlays:
            if k in RING_OVERLAYS:
                OVL_MODS[k].SPEC = OVL_MODS[k].make_spec(at)
                rings[k] = at
                at += OVL_MODS[k].RING_N * OVL_MODS[k].NSLOTS
        assert at <= DDR2_LIMIT, f'the rings run past the free DDR2 ({at:#x} > {DDR2_LIMIT:#x})'
    check = '--no-check' not in argv
    run = bnc.run

    # 1. the kernels: NAM, then Geiger (and the extras) packed between NAM's Block 3 end and Click's data
    far = ['--far-d', str(NAM_FAR_D_EXTRA)] if extras else []
    log = run(sys.executable, be.KERNEL, '-o', nam_asm, '--slots', str(NAM_SLOTS), *far, *(['--check'] if check else []), env=env)
    m = re.search(r'block 3: (0x[0-9a-f]+)\.\.(0x[0-9a-f]+)', log)
    nam_b3 = (int(m.group(1), 16), int(m.group(2), 16))
    import click_kernel
    click_data0 = click_kernel.PLACES['b3'][2]
    code48_limit = 0xE0000 + (click_data0 - 0xE0000) * 2 // 3
    ks = {k: Kernel(k) for k in blocks}
    ovk = {k: Kernel(k) for k in overlays}
    cursor = (nam_b3[1] + 0xF) & ~0xF
    if overlay:                                          # the stub is measured with as many members as it will have
        ovl_stub_kernel.configure(meter=meter, members=[dict(name=k.upper(), src_code=0x3E0000, n_code=660, src_data=0x3E1000,
                                                             n_data=300, slots_off=200, kernel=0xE5000, pattern_word=8) for k in overlays])
    for k in blocks:
        if k == 'ovl_stub':                              # the shared region: the largest data, then the largest code
            sizes = [ovk[m].measure(cursor) for m in overlays]
            o_data_end, o_code_n = max(x[0] for x in sizes), max(x[1] for x in sizes)
            o_code48 = b3_code48(o_data_end)
            for m in overlays:
                ovk[m].set_place(o_code48, code48_limit, cursor)
            o_region = (cursor, o_data_end, o_code48, o_code_n + (o_code_n & 1))
            ovl_stub_kernel.MEMBERS[:] = [(m.upper(), OVL_MODS[m].SPEC, 'b3', f'{m.upper()}_ENTRY', OVL_MODS[m]) for m in overlays]
            cursor = (b3_normal(o_code48 + o_region[3]) + 0xF) & ~0xF
        data_end, n_code = ks[k].measure(cursor)
        code48 = b3_code48(data_end)
        ks[k].set_place(code48, code48_limit, cursor)
        cursor = (b3_normal(code48 + n_code + (n_code & 1)) + 0xF) & ~0xF   # code loads in pairs
    if cursor > click_data0 + 0xF:
        sys.exit(f'build_all.py: {", ".join(blocks)} do not fit between NAM ({nam_b3[1]:#x}) and Click ({click_data0:#x}): '
                 f'they need to {cursor:#x}')
    if check:
        r = subprocess.run(['make', '-s', '-C', os.path.join(HERE, 'effects'), 'out/libfx.so'], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f'build_all.py: could not build effects/out/libfx.so:\n{r.stderr}')
        run(sys.executable, os.path.join(HERE, 'effects', 'metronome', 'sharc', 'click_kernel.py'), '--check', '--place', 'b3')
        for k in blocks:
            try:
                ks[k].check(0.25)
            except AssertionError as ex:
                sys.exit(f'build_all.py: {k} check failed: {ex}')

    os.environ['NAM_DEVICE'] = 'effects'
    import l6ia
    import patch_amp as pa
    import sasm

    l6ia_bytes, _ = pa.load_l6ia_from_any(stock)
    assert pa.select_device(l6ia_bytes) is pa.EFFECTS_DSP
    D = pa.EFFECTS_DSP
    assert D.HEAP6[0] - D.BLOB0_WORDS == bnc.BLOB0_BASE
    assert sdr_base + NAM_SLOTS * 0x5000 <= D.HEAP6[1]
    D.BLOB0_MAX_WORDS = blob0_words
    e0 = pa.get_entry_swapped(l6ia_bytes, 0)
    e3 = pa.get_entry_swapped(l6ia_bytes, 3)
    e4 = pa.get_entry_swapped(l6ia_bytes, 4)
    info = pa.parse_entry3_full(e3)
    clone = pa.find_model(info, be.CLONE)
    targets = {'nam': pa.find_model(info, nam_takeover), 'click': pa.find_model(info, bc.TAKEOVER)}
    params = {'nam': nam_off_ir(pa.nam_params(e3, info)) if nam_host else pa.nam_params(e3, info), 'click': bc.click_params(pa, e3, info)}
    for k in fx:
        targets[k] = pa.find_model(info, EFFECTS[k]['takeover'])
        params[k] = (sync_knob_params if EFFECTS[k].get('sync') else knob_params)(pa, e3, info, EFFECTS[k]['params'])

    # 2. Entry 4: the host graphs (copies of the 2048 IR block's), each on its own primitive
    w4s = struct.unpack('<%dI' % (len(e4) // 4), e4)
    stock_b0_len = w4s[w4s[3]]
    e4n, b_n, c_n = pa.add_model_entry4(e4, clone['blob_index'], params['nam'], 0, prim_id=NAM_PRIM)
    e4n, b_c, c_c = pa.add_model_entry4(e4n, clone['blob_index'], params['click'], 0, blob_fn=bc.click_host_blob, prim_id=CLICK_PRIM)
    blobs, comps = {'nam': b_n, 'click': b_c}, {'nam': c_n, 'click': c_c}
    for k in fx:
        pad = ()
        if len(overlays) > 2:                  # drop the dead table copies before each new one (compact_blob0)
            e4n = compact_blob0(pa, e4n, stock_b0_len)
        if overlay and k == fx[-1]:            # inside Blob 0, before the last model's own table copy
            w4 = struct.unpack('<%dI' % (len(e4n) // 4), e4n)
            b0_len = w4[w4[3]]
            curves = geiger_kernel.tables()
            assert len(curves) == GEIGER_CURVES_WORDS
            base = bnc.BLOB0_BASE + b0_len
            dc_bank, dc_samp = [], []
            if 'drumchapel' in overlays:                # Drum Chapel's grooves and samples (read-only), after the curves
                dc = OVL_MODS['drumchapel']
                dc_bank, dc_samp = dc.bank(), dc.samples()
                dc_at = base + len(curves)
                dc_samp_at = dc.place_bank(dc.SPEC, dc_at)   # the same spec object ovl_stub_kernel.MEMBERS holds
                assert dc_samp_at == dc_at + len(dc_bank)
                print(f'[+] Drum Chapel grooves: {dc.families()} of 11 families converted'
                      f'{"" if dc.families() else " (no grooves_data.h: the Groove knob plays Classic everywhere)"}; '
                      f'bank {len(dc_bank)} words at DDR2 {dc_at:#x}')
                print(f'[+] Drum Chapel samples: ' + (f'{len(dc_samp)} words at DDR2 {dc_samp_at:#x} (the Acoustic kit\'s kick and snare)'
                      if dc_samp else 'none (no samples_data.h: the Acoustic kit plays Punch\'s synthesised kick and snare)'))
            o_words, ovl = ovl_stub_kernel.layout([m[:4] for m in ovl_stub_kernel.MEMBERS],
                                                  base + len(curves) + len(dc_bank) + len(dc_samp))
            pad = curves + dc_bank + dc_samp + o_words
            geiger_kernel.EXT_CURVES = base
            ovl_stub_kernel.configure(**ovl)
            print(f'[+] Entry 4: inside Blob 0 at DDR2 {base:#x}: Geiger\'s curves ({len(curves)} words), '
                  f'{f"Drum Chapel grooves ({len(dc_bank)} words), " if dc_bank else ""}'
                  f'{f"Drum Chapel samples ({len(dc_samp)} words), " if dc_samp else ""}the overlays '
                  f'({", ".join(f"{m["name"]} {m["n_code"]}+{m["n_data"]}" for m in ovl["members"])}); rings at {ring0:#x}')
        if k == 'probe':        # the magic word and the routine inside Blob 0, before the probe's own table copy
            import probe_kernel
            w4 = struct.unpack('<%dI' % (len(e4n) // 4), e4n)
            b0_len = w4[w4[3]]
            probe_kernel.EXT['tail'] = (b0_len + 1) & ~1
            _, _, p_syms, _, _ = ks['probe'].assemble()
            pad = [0] * (probe_kernel.EXT['tail'] - b0_len) + probe_kernel.tail_words(p_syms)
        e4n, blobs[k], comps[k] = pa.add_model_entry4(e4n, clone['blob_index'], params[k], 0, prim_id=EFFECTS[k]['prim'],
                                                      b0_pad=pad, **({'blob_fn': bc.click_host_blob} if EFFECTS[k].get('sync') else {}))
    print('[+] Entry 4: ' + ', '.join(f'{k} blob {blobs[k]} on {comps[k]:#x}' for k in blobs))
    w4 = struct.unpack('<%dI' % (len(e4n) // 4), e4n)
    print(f'[+] Entry 4: Blob 0 {w4[w4[3]]:#x} words of its {blob0_words:#x}-word buffer ({blob0_words - w4[w4[3]]} free)')
    if probe:                                            # where the probe's words landed, checked
        w4 = struct.unpack('<%dI' % (len(e4n) // 4), e4n)
        d = w4[3]
        b0 = list(w4[w4[d + 1]: w4[d + 1] + w4[d]])
        t = probe_kernel.EXT['tail']
        assert len(b0) <= blob0_words, f'Blob 0 {len(b0):#x} words, its buffer {blob0_words:#x}'
        assert pa.sharc_blob0_check(b0, blob0_words) is None
        assert b0[t] == probe_kernel.MAGIC and b0[t: t + len(probe_kernel.tail_words(p_syms))] == probe_kernel.tail_words(p_syms)
        assert b0[0x10] > t, 'the probe words are not before the last composite table'
        print(f'[+] Entry 4: Blob 0 {len(b0):#x} words, the probe words inside it at {t:#x} (table at {b0[0x10]:#x}): '
              f'magic at DDR2 {probe_kernel.magic_addr():#x}')
        if check:
            probe_kernel.check(0.25, ks['probe'].place)

    # 3. Entry 2: Blob 0's buffer and Heap 6
    entries = l6ia.parse(l6ia_bytes)
    e2_raw = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    e2_raw, _ = pa.expand_sharc_blob0_buffer(e2_raw)

    # 4. Entry 3: the models, descriptors copied over their targets
    e3n, id_n, _ = pa.add_model_entry3(e3, targets['nam'] if nam_host else clone, be.NAME, be.DISPLAY, b_n, params['nam'])
    e3n, id_c, _ = pa.add_model_entry3(e3n, targets['click'], bc.NAME, bc.DISPLAY, b_c, params['click'],
                                       meta_set={'displayNameShort': bc.SHORT, 'displayParamCount': str(len(params['click']) - 2)})
    ids = {'nam': id_n, 'click': id_c}
    for k in fx:
        e3n, ids[k], _ = pa.add_model_entry3(e3n, targets[k], EFFECTS[k]['name'], EFFECTS[k]['display'], blobs[k], params[k],
                                             meta_set={**({'displayParamCount': str(len(params[k]) - 2)} if EFFECTS[k].get('sync') else {}),
                                                       **({'type': EFFECTS[k]['meta_type']} if 'meta_type' in EFFECTS[k] else {})},
                                             meta_drop=EFFECTS[k].get('meta_drop', ()))
    e3n = bytearray(e3n)
    ms = pa.parse_entry3_full(bytes(e3n))['models']
    for key, new_id in ids.items():
        d_new = struct.unpack_from('<14I', e3n, ms[new_id]['off'])
        d_tgt = list(struct.unpack_from('<14I', e3n, ms[targets[key]['model_id']]['off']))
        for k in (0, 1, 6, 7, 10, 11, 13):
            d_tgt[k] = d_new[k]
        struct.pack_into('<14I', e3n, ms[targets[key]['model_id']]['off'], *d_tgt)
    e3n = bytes(e3n)
    chk = pa.parse_entry3_full(e3n)['models']
    displays = {'nam': be.DISPLAY, 'click': bc.DISPLAY, **{k: EFFECTS[k]['display'] for k in fx}}
    for key, disp in displays.items():
        t = chk[targets[key]['model_id']]
        assert t['displayName'] == disp and t['blob_index'] == blobs[key] and len(t['params']) == len(params[key]), key
    print('[+] Entry 3: ' + '; '.join(f'{targets[k]["name"]} -> {displays[k]}' for k in displays))

    # 5. Entry 0
    e0n, *_ = pa.takeover_entry0_effects(e0, targets['nam']['words'][2], be.DISPLAY, short_name=be.SHORT,
                                         dsp_cost=be.DSP_COST, n_params=len(params['nam']), strip_title=None if nam_host else be.STRIP_TITLE)
    e0n, *_ = pa.takeover_entry0_effects(e0n, targets['click']['words'][2], bc.DISPLAY, short_name=bc.SHORT,
                                         dsp_cost=bc.DSP_COST, n_params=len(params['click']), strip_title=None,
                                         n_display=len(params['click']) - 2)
    for k in fx:
        e0n, pid, _, hits = pa.takeover_entry0_effects(e0n, targets[k]['words'][2], EFFECTS[k]['display'],
                                                       short_name=EFFECTS[k].get('short', EFFECTS[k]['display']), dsp_cost=EFFECTS[k]['cost'],
                                                       n_params=len(params[k]), strip_title=None,
                                                       n_display=len(params[k]) - 2 if EFFECTS[k].get('sync') else None,
                                                       follow_enable=False if 'followEnable' in EFFECTS[k].get('meta_drop', ()) else None)
        print(f'[+] Entry 0: {EFFECTS[k]["display"]} preset_id {pid}, browser slots {hits}, dsp_cost {EFFECTS[k]["cost"]}')
        if EFFECTS[k].get('plain_delay'):           # a 'special' delay host (Ratchet): an ordinary delay, so its footswitch bypasses it
            import special_delay_patch as sdp
            e0n, sites = sdp.patch_e0(e0n)
            print(f'[+] Entry 0: {EFFECTS[k]["display"]} is an ordinary delay (block type 0x08; name compares at '
                  f'{", ".join(hex(va) for va, _ in sites[:3])} retargeted)')
    l6ia_bytes, _, _ = l6ia.rebuild_archive(l6ia_bytes, {0: e0n, 2: l6ia.swap32(e2_raw), 3: e3n, 4: e4n})

    # 6. Entry 2: the kernels, no shared byte, one hook each
    entries = l6ia.parse(l6ia_bytes)
    e2_raw = l6ia_bytes[entries[2]['payload_off']: entries[2]['payload_off'] + entries[2]['payload_len']]
    used_pm_end, hooked = pa._scan_e2_injected(e2_raw)
    assert used_pm_end <= 0x0c4ef8 and not hooked, 'Entry 2 already has injected code'
    n_secs, n_syms = sasm.assemble(open(nam_asm).read(), os.path.basename(nam_asm))
    _, c_secs, c_syms, c_end, c_data = click_kernel.assemble(place='b3')
    kernels = {'NAM': (n_secs, n_syms['CUSTOM_AMP_ENTRY'], NAM_PRIM),
               'Click': (c_secs, c_syms['CLICK_ENTRY'], CLICK_PRIM)}
    placed = {}
    for b in blocks:
        _, secs, syms, end, data = ks[b].assemble()
        for j, k in enumerate(entries_of[b]):            # a shared kernel's code and data go in once
            kernels[EFFECTS[k]['display']] = (secs if j == 0 else [], syms[EFFECTS[k]['entry']], EFFECTS[k]['prim'])
            placed[k] = (end, data, b)
    regions = {who: [(*bnc.byte_range(s.kind, s.addr, len(s.words)), f'{who} {s.kind} {s.addr:#x}+{len(s.words)}')
                     for s in secs] for who, (secs, _, _) in kernels.items()}
    regions['NAM'].append((*bnc.byte_range('dm', nam_b3[0], nam_b3[1] - nam_b3[0]), f'NAM Block 3 {nam_b3[0]:#x}..{nam_b3[1]:#x}'))
    if overlay:                                          # not in the boot stream, but the shared region is taken
        regions['the overlay region'] = [(*bnc.byte_range('dm', o_region[0], o_region[1] - o_region[0]), f'overlay data {o_region[0]:#x}'),
                                         (*bnc.byte_range('pm', o_region[2], o_region[3]), f'overlay code {o_region[2]:#x}')]
    owners = list(regions)
    for i, a in enumerate(owners):
        for b in owners[i + 1:]:
            for x in regions[a]:
                for y in regions[b]:
                    if x[0] == y[0] and x[1] < y[2] and y[1] < x[2]:
                        sys.exit(f'build_all.py: memory overlap: {x[3]} and {y[3]}')
    for reg in regions.values():
        for blk, lo, hi, what in reg:
            assert hi <= 0x20000, f'{what} runs past its block'
    print(f'[+] memory: NAM Block 3 {nam_b3[0]:#x}..{nam_b3[1]:#x}; ' +
          '; '.join(f'{placed[k][2]} data {placed[k][1][0]:#x}..{placed[k][1][1]:#x}, '
                    f'code {ks[placed[k][2]].places[ks[placed[k][2]].place][0]:#x}..{placed[k][0]:#x}' for k in fx if entries_of[placed[k][2]][0] == k) +
          f'; Click data {c_data[0]:#x}.., code {click_kernel.PLACES["b3"][0]:#x}..{c_end:#x}: no byte shared')
    ldr = []
    for secs, _, _ in kernels.values():
        for s in secs:
            ldr += pa.pack_init_l48(s.addr, s.words) if s.kind == 'pm' else ldr_l32(pa, s.addr, s.words, bool(extras))
    if probe:                                            # the overlay test region: free, below Click's data
        assert bnc.byte_range('dm', probe_kernel.normal_of(probe_kernel.REG), probe_kernel.NWORDS)[2] <= bnc.byte_range('dm', click_data0, 1)[1]
    table, _ = pa.sharc_prim_table(e2_raw)
    template = pa.sharc_prim_record(e2_raw, 0x822)
    for who, (_, entry, prim) in kernels.items():
        assert prim in table, f'primitive {prim:#x} not in the table'
        ldr += pa.pack_init_l32(table[prim], [prim] + list(template[1:5]) + [entry, 0x91, 0x0d])
        print(f'[+] Entry 2: {who} at PM {entry:#x} via {prim:#06x} @ {table[prim]:#x}')
    e2_new = pa.inject_sharc_ldr_blocks(e2_raw, ldr)
    print(f'[+] Entry 2: {len(e2_new)} bytes of the 524288-byte partition ({524288 - len(e2_new)} free)')
    l6ia_bytes, _, _ = l6ia.rebuild_archive(l6ia_bytes, {2: l6ia.swap32(e2_new)})
    open(image, 'wb').write(l6ia_bytes)

    # 7. verify and pack
    if 'ALL OK' not in run(sys.executable, os.path.join(TOOLS, 'l6ia_verify.py'), image):
        sys.exit('build_all.py: the image failed its checksum check')
    run(sys.executable, os.path.join(TOOLS, 'hxf.py'), 'pack', image, out, '--donor', stock)
    import json
    manifest = dict(input=os.path.basename(stock), input_md5=STOCK_MD5,
                    output=os.path.relpath(out, HERE), output_md5=hashlib.md5(open(out, 'rb').read()).hexdigest(),
                    nam=dict(model=nam_takeover, moved=bool(nam_host), primitive=NAM_PRIM, slots=NAM_SLOTS, block3=list(nam_b3),
                             sdram_base=sdr_base, dsp_cost=be.DSP_COST, **({'far_d': NAM_FAR_D_EXTRA} if extras else {})),
                    click=dict(model=bc.TAKEOVER, primitive=CLICK_PRIM, place=list(click_kernel.PLACES['b3']), dsp_cost=bc.DSP_COST))
    for k in fx:
        b = placed[k][2]
        manifest[k] = dict(model=EFFECTS[k]['takeover'], primitive=EFFECTS[k]['prim'], place=list(ks[b].places[ks[b].place]),
                           data=list(placed[k][1]), dsp_cost=EFFECTS[k]['cost'], **({'kernel': b} if b != k else {}))
    if extras:
        manifest['extras'] = extras
    if overlay:
        manifest['overlay'] = dict(ovl, meter=meter, ring0=ring0, rings=rings, curves=geiger_kernel.EXT_CURVES,
                                   **({'grooves': dict(bank=dc_at, words=len(dc_bank), families=OVL_MODS['drumchapel'].families()),
                                       'samples': dict(addr=dc_samp_at, words=len(dc_samp), sampled=OVL_MODS['drumchapel'].sampled())}
                                      if 'drumchapel' in overlays else {}),
                                   place=list(ovk[overlays[0]].places['b3']), names=overlays)
    manifest.update(blob0_words=blob0_words, checked=check)
    json.dump(manifest, open(manifest_path, 'w'), indent=1)
    print(f'[+] manifest {os.path.relpath(manifest_path, HERE)}')
    print(f'\nDone: {out}\nFlash: python3 tools/flash.py flash {os.path.relpath(out, HERE)}')


if __name__ == '__main__':
    main()
