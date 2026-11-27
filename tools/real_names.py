#!/usr/bin/env python3
"""Real-world names: every block based on real gear is shown under that gear's name, e.g. Mandarin Rocker as
"Orange Rockerverb" (build.py --real-names; off by default).

The unit shows a block's name from two places in Entry 0, and these are the only bytes changed:
  - its row in Table 2 (44-byte rows, bytes 4..19: the 16-character name the unit shows for a block in a preset);
  - its item in every block-menu list it is in (48-byte items, bytes 14..39: the name in the menu, which shows
    16 characters).
The same two places patch_amp.takeover_entry0_effects changes for Bolt, Rocket! and the rest, so this is how the
unit already shows our own names. Presets store a block by its model and preset id, never by name, so they are
not affected, and a build without --real-names loads them just the same.

A block is renamed only when the image still shows the Line 6 name the table expects. Blocks our builds have
already renamed (Bolt, Rocket!, NAM A2 Lite, Click, ...) no longer show a Line 6 name, so they keep their names.
Names stay at 16 characters at most (checked).

Trademarks: the names are those of the products each model is based on, as Line 6 lists them in its HX Stomp 3.80
Owner's Manual (the "Based On" column).
They belong to their owners, who have not endorsed, sponsored or approved this project or Line 6's models.

usage: .venv/bin/python tools/real_names.py BASE.hxf     writes build/<base>_RealNames.hxf and checks it
       .venv/bin/python tools/real_names.py --js            writes tools/preset-builder/real-names.js (the same table,
                                                            for the preset builder's Real names switch)
"""
import hashlib
import os
import struct
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

STOCK = os.path.join(ROOT, 'firmware', 'HX_Effects_v3.80.0_0xd97239907.hxf')
MAX = 16

# Line 6 name (as the unit shows it) -> real-world name, from the "Based On" column of Line 6's HX Stomp 3.80
# Owner's Manual (amp, legacy cab and effect tables; checked 2026-11-27). Blocks the manual lists as Line 6
# Originals, or that already carry the real name (Ampeg, Revv, Grammatico), are not listed. Preamps share their
# amp's name, so one entry covers both.
AMPS = {
    'WhoWatt 100': 'Hiwatt DR103',
    'Soup Pro': 'Supro S6616',
    'Stone Age 185': 'Gibson EH-185',
    'Voltage Queen': 'Victoria V-Queen',
    'Tweed Blues Nrm': 'Fender Bassman N', 'Tweed Blues Brt': 'Fender Bassman B',
    'Fullerton Nrm': 'Fender 5C3 Nrm', 'Fullerton Brt': 'Fender 5C3 Brt', 'Fullerton Jump': 'Fender 5C3 Jump',
    'US Small Tweed': 'Fender Champ',
    'US Princess': 'Fender Princeton',
    'US Super Norm': 'Fender Super Nrm', 'US Super Nrm': 'Fender Super Nrm', 'US Super Vib': 'Fender Super Vib',
    'US Deluxe Nrm': 'Fender Deluxe N', 'US Deluxe Vib': 'Fender Deluxe V',
    'US Double Nrm': 'Fender Twin Nrm', 'US Double Vib': 'Fender Twin Vib',
    'Mail Order Twin': 'Silvertone 1484',
    'Divided Duo': 'Div13 JRT 9/15',
    'Interstate Zed': 'Dr Z Route 66',
    'Derailed Ingrid': 'Trainwreck Expr',
    'Jazz Rivet 120': 'Roland JC-120',
    'Essex A15': 'Vox AC15', 'Essex A30': 'Vox AC30 TB',
    'A30 Fawn Nrm': 'Vox AC30 Fawn Nm', 'A30 Fawn Brt': 'Vox AC30 Fawn Br',
    'Matchstick Ch1': 'Matchless DC30 1', 'Matchstick Ch2': 'Matchless DC30 2', 'Matchstick Jump': 'Matchless DC30 J',
    'Mandarin 80': 'Orange OR80', 'Mandarin Rocker': 'OrangeRockerverb',
    'Moo)))n Nrm': 'Sunn Model T Nrm', 'Moo)))n Brt': 'Sunn Model T Brt', 'Moo)))n Jump': 'Sunn Model T Jmp',
    'Brit J45 Nrm': 'Marshall JTM45 N', 'Brit J45 Brt': 'Marshall JTM45 B',
    'Brit Trem Nrm': 'Marshall JTM50 N', 'Brit Trem Brt': 'Marshall JTM50 B', 'Brit Trem Jump': 'Marshall JTM50 J',
    'Brit Plexi Nrm': 'Marshall Plexi N', 'Brit Plexi Brt': 'Marshall Plexi B', 'Brit Plexi Jump': 'Marshall Plexi J',
    'Brit P75 Nrm': 'Park 75 Nrm', 'Brit P75 Brt': 'Park 75 Brt',
    'Brit 2203': 'Marshall JCM2203', 'Brit 2204': 'Marshall JCM2204',
    'Placater Clean': 'Friedman Clean', 'Placater Dirty': 'Friedman BE-100',
    'Cartographer': 'Ben Adrian Carto',
    'German Xtra Blue': 'Bogner Ecstasy B', 'German Xtra Red': 'Bogner Ecstasy R',
    'German Mahadeva': 'Bogner Shiva', 'German Ubersonic': 'Bogner Uberschal',
    'Cali Texas Ch1': 'Mesa Lone Star 1', 'Cali Texas Ch2': 'Mesa Lone Star 2',
    'Cali IV Rhythm 1': 'Mesa Mk IV Rhy1', 'Cali IV Rhythm 2': 'Mesa Mk IV Rhy2', 'Cali IV Lead': 'Mesa Mk IV Lead',
    'Cali Rectifire': 'Mesa Dual Recto',
    'Archetype Clean': 'PRS Archon Clean', 'Archetype Lead': 'PRS Archon Lead',
    'ANGL Meteor': 'ENGL Fireball',
    'Solo Lead Clean': 'Soldano SLO Cln', 'Solo Lead Crunch': 'Soldano SLO Crn', 'Solo Lead OD': 'Soldano SLO OD',
    'EV Panama Blue': 'EVH 5150III Blue', 'EV Panama Red': 'EVH 5150III Red',
    'PV Panama': 'Peavey 5150',
    'PV Vitriol Clean': 'Invective Clean', 'PV VitriolCrunch': 'Invective Crunch', 'PV Vitriol Crunch': 'Invective Crunch',
    'PV Vitriol Lead': 'Invective Lead',
    'Das Benzin Mega': 'Diezel VH4 Mega', 'Das Benzin Lead': 'Diezel VH4 Lead',
    # bass, and the mic preamp
    'US Dripman Norm': 'Fender SFBassman', 'US Dripman Nrm': 'Fender SFBassman',
    'Woody Blue': 'Acoustic 360',
    'Agua Sledge': 'Aguilar Tone Hmr', 'Agua 51': 'Aguilar DB51',
    'Mandarin Bass 200': 'Orange AD200',
    'Cali Bass': 'Mesa M9 Carbine',
    'Cali 400 Ch1': 'Mesa 400+ Ch1', 'Cali 400 Ch2': 'Mesa 400+ Ch2',
    'G Cougar 800': 'GK 800RB',
    'Del Sol 300': 'Sunn Coliseum300',
    'Busy One Ch1': 'Pearce BC-1 Ch1', 'Busy One Ch2': 'Pearce BC-1 Ch2', 'Busy One Jump': 'Pearce BC-1 Jump',
    'Studio Tube Pre': 'Requisite Y7',
}
# the legacy cabs (the manual's "Legacy Cab Models" table)
CABS = {
    'Soup Pro Ellipse': 'Supro 1x6x9',
    '1x8 Small Tweed': '1x8 Fender Champ',
    '1x10 US Princess': '1x10 Princeton', '1x12 US Princess': '1x12 Princeton',
    '1x12 Field Coil': '1x12 Gibson 185',
    '1x12 Fullerton': '1x12 Fender 5C3',
    '1x12 US Deluxe': '1x12 Fender Dlx',
    '1x12 Celest 12H': '1x12 Div13 H30',
    '1x12 Blue Bell': '1x12 Vox AC15',
    '1x12 Lead 80': '1x12 Bogner CL80',
    '1x12 Cali IV': '1x12 Mesa Mk IV', '1x12 Cali EXT': '1x12 Mesa EVM12L', '1x12 Cali Ext': '1x12 Mesa EVM12L',
    '2x12 Double C12N': '2x12 Fender Twin',
    '2x12 Mail C12Q': '2x12 Silvertone',
    '2x12 Interstate': '2x12 Dr Z Z Best',
    '2x12 Jazz Rivet': '2x12 Roland JC',
    '2x12 Silver Bell': '2x12 Vox AC30TB', '2x12 Blue Bell': '2x12 Vox Fawn',
    '2x12 Match H30': '2x12 Matchls H30', '2x12 Match G25': '2x12 Matchls G25',
    '4x10 Tweed P10R': '4x10 Bassman',
    '4x12 WhoWatt 100': '4x12 Hiwatt',
    '4x12 Mandarin EM': '4x12 Orange',
    '4x12 Blackback30': '4x12 Park 75',
    '4x12 1960 T75': '4x12 Marshall',
    '4x12 Uber V30': '4x12 Bogner V30', '4x12 Uber T75': '4x12 Bogner T75',
    '4x12 Cali V30': '4x12 Mesa V30', '4X12 Cali V30': '4x12 Mesa V30',
    '4x12 XXL V30': '4x12 ENGL V30',
    '4x12 SoloLead EM': '4x12 Soldano',
    '1x12 Del Sol': '1x12 Sunn', '1x18 Del Sol': '1x18 Sunn',
    "1x15 Tuck n' Go": '1x15 Ampeg B-15', '1x15 Ampeg B-15': '1x15 Ampeg B-15',   # menu: the Stomp's name
    '1x18 Woody Blue': '1x18 Acoustic',
    '2x15 Brute': '2x15 Mesa EV',
    '6x10 Cali Power': '6x10 Mesa',
    '8x10 SV Beast': '8x10 Ampeg SVT', '8x10 Ampeg SVT E': '8x10 Ampeg SVT',
}
EFFECTS = {
    # distortion
    'Kinky Boost': 'Xotic EP Booster',
    'Deranged Master': 'Dallas Rangemstr',
    'Minotaur': 'Klon Centaur',
    'Teemah!': 'Paul C Timmy',
    'Heir Apparent': 'Prince of Tone', 'Tone Sovereign': 'King of Tone',
    'Alpaca Rouge': 'Way Huge Llama', 'Alpaca Rogue': 'Way Huge Llama',
    'Compulsive Drive': 'Fulltone OCD',
    'Dhyana Drive': 'Hermida Zendrive',
    'Horizon Drive': 'Precision Drive',
    'Valve Driver': 'Chandler TubeDrv', 'Tube Drive': 'Chandler TubeDrv',
    'Top Secret OD': 'DOD OD-250',
    'Prize Drive': 'Nobels ODR-1',
    'Scream 808': 'Ibanez TS808', 'Screamer': 'Ibanez TS',
    'Pillars': 'EQD Plumes',
    'Hedgehog D9': 'Maxon SD9',
    'Stupor OD': 'Boss SD-1',
    'Deez One Vintage': 'Boss DS-1', 'Deez One Mod': 'Boss DS-1 Keeley',
    'Ratatouille Dist': 'ProCo RAT LM308', 'Ratatoullie Dist': 'ProCo RAT LM308',
    'Vermin Dist': 'ProCo RAT', 'Classic Dist': 'ProCo RAT',
    'Vital Dist': 'EQD Life Dist', 'Vital Boost': 'EQD Life Boost',
    'KWB': 'Benadrian KWB',
    'Legendary Drive': 'Carvin VLD1',
    'Swedish Chainsaw': 'Boss HM-2',
    'Arbitrator Fuzz': 'Arbiter FuzzFace', 'Facial Fuzz': 'Arbiter FuzzFace',
    'Pocket Fuzz': 'Jordan Boss Tone',
    'Bighorn Fuzz': 'EHX Rams Head',
    'Triangle Fuzz': 'EHX Big Muff Pi', 'Fuzz Pi': 'EHX Big Muff Pi',
    'Dark Dove Fuzz': 'EHX Russian Muff',
    'Ballistic Fuzz': 'Euthymia ICBM',
    'Industrial Fuzz': 'ZVex Fuzz Fctry',
    'Tycoctavia Fuzz': 'Tycobrahe Octav', 'Octave Fuzz': 'Tycobrahe Octav',
    'Wringer Fuzz': 'Boss FZ-2 Mod',
    'Xenomorph Fuzz': 'Subdecay HarmAnt',
    'ZeroAmp Bass DI': 'Tech21 SansAmp',
    'Regal Bass DI': 'Noble Bass DI',
    'Obsidian 7000': 'Darkglass B7K',
    'Clawthorn Drive': 'Battering Ram',
    'Overdrive': 'DOD 250',
    'Heavy Dist': 'Boss Metal Zone', 'Killer Z': 'Boss MT-2',
    'Colordrive': 'Colorsound OD',
    'Buzz Saw': 'Maestro FuzzTone',
    'Jumbo Fuzz': 'Vox Tone Bender',
    'Jet Fuzz': 'Roland JetPhaser',
    'Sub Oct Fuzz': 'PAiA Roctave',
    'Bronze Master': 'Brassmaster',
    # dynamics
    'Red Squeeze': 'MXR Dyna Comp', 'Red Comp': 'MXR Dyna Comp',
    'Kinky Comp': 'Xotic SP Comp',
    'Rochester Comp': 'Ashly CLX-52',
    'LA Studio Comp': 'Teletronix LA-2A', 'Tube Comp': 'Teletronix LA-2A',
    'Blue Comp': 'Boss CS-1', 'Blue Comp Treb': 'Boss CS-1 Treble',
    'Boost Comp': 'MXR Micro Amp',
    # EQ
    '10 Band Graphic': 'MXR 10 Band EQ',
    'Cali Q Graphic': 'Mesa Mk IV GEQ',
    # modulation
    'Optical Trem': 'Fender Opto Trem', 'Opto Tremolo': 'Fender Opto Trem',
    '60s Bias Trem': 'Vox AC15 Trem', 'Bias Tremolo': 'Vox AC15 Trem',
    'Tremolo/Autopan': 'Boss PN-2',
    'Bleat Chop Trem': 'Goatkeeper',
    'Script Mod Phase': 'MXR Phase 90', 'Phaser': 'MXR Phase 90', 'Script Phase': 'MXR Script P90',
    'Pebble Phaser': 'EHX Small Stone',
    'Ubiquitous Vibe': 'Shin-ei Uni-Vibe', 'U-Vibe': 'Shin-ei Uni-Vibe',
    'Gray Flanger': 'MXR 117 Flanger',
    'Harmonic Flanger': 'A/DA Flanger', 'Jet Flanger': 'A/DA Flanger', '80A Flanger': 'A/DA Flanger',
    'Courtesan Flange': 'EHX Deluxe EM',
    '70s Chorus': 'Boss CE-1', 'Analog Chorus': 'Boss CE-1',
    'PlastiChorus': 'Arion SCH-Z Mod',
    'Trinity Chorus': 'Dytronics Tri-St', 'Tri Chorus': 'Dytronics Tri-St',
    'Bubble Vibrato': 'Boss VB-2', 'Pitch Vibrato': 'Boss VB-2',
    'Vibe Rotary': 'Fender Vibratone', 'Rotary Drum': 'Fender Vibratone',
    '122 Rotary': 'Leslie 122', '145 Rotary': 'Leslie 145', 'Rotary Drum/Horn': 'Leslie 145',
    'Triple Rotary': 'Yamaha RA-200',
    'Panned Phaser': 'Ibanez FlyingPan',
    'Dual Phaser': 'Mu-Tron Bi-Phase',
    'Dimension': 'Roland Dim D',
    'Analog Flanger': 'MXR Flanger', 'AC Flanger': 'MXR Flanger',
    # delay
    'Bucket Brigade': 'Boss DM-2', 'Analog Echo': 'Boss DM-2',
    'Adriatic Delay': 'Boss DM-2 Mod',
    'Elephant Man': 'EHX Memory Man', 'Analog w/Mod': 'EHX Memory Man',
    'Ducked Delay': 'TC 2290 Ducked', 'Dynamic': 'TC 2290',
    'Transistor Tape': 'Maestro EP-3', 'Tape Echo': 'Maestro EP-3', 'Tube Echo': 'Maestro EP-1',
    'Cosmos Echo': 'Roland RE-201', 'Multi-Head': 'Roland RE-101',
    'Echo Platter': 'Binson Echorec',
    # pitch and synth
    'Pitch Wham': 'DigiTech Whammy',
    'Twin Harmony': 'Eventide H3000', 'Smart Harmony': 'Eventide H3000',
    'Boctaver': 'Boss OC-2',
    'Bass Octaver': 'EBS OctaBass',
    'Attack Synth': 'Korg X911',
    'Synth String': 'Roland GR700',
    # filter
    'Mutant Filter': 'Mu-Tron III', 'V Tron': 'Mu-Tron III',
    'Tron Up': 'Mu-Tron III Up', 'Tron Down': 'Mu-Tron III Down',
    'Mystery Filter': 'Korg A3',
    'Asheville Pattrn': 'Moog MF-105M',
    'Seeker': 'ZVex Seek-Wah',
    'Obi Wah': 'Oberheim S&H',
    'Throbber': 'Filter Factory',
    # wah
    'UK Wah 846': 'Vox V846', 'Chrome': 'Vox V847', 'Chrome Custom': 'Vox V847 Mod',
    'Teardrop 310': 'Dunlop Fasel 310', 'Fassel': 'Cry Baby Super', 'Weeper': 'Arbiter Cry Baby',
    'Throaty': 'RMC Real McCoy 1',
    'Colorful': 'Colorsound Wah',
    'Conductor': 'Boomerang Wah',
    'Teardrop Bass Q': 'Dunlop 105Q Mod',
}
# Repeats: where two blocks are based on the same gear (mostly a model and its Legacy version), the current one
# keeps the plain name and the other gets ' B' (shortened where needed to stay within 16 characters).
REPEATS = {
    'Jet Flanger': 'A/DA Flanger B',
    'Facial Fuzz': 'Arbiter FzFace B',
    'Analog Chorus': 'Boss CE-1 B',
    'Analog Echo': 'Boss DM-2 B',
    'Pitch Vibrato': 'Boss VB-2 B',
    'Tube Drive': 'Chandler TubeD B',
    'Tri Chorus': 'Dytronics Tri B',
    'Fuzz Pi': 'EHX Big Muff B',
    'Analog w/Mod': 'EHX MemoryMan B',
    'Smart Harmony': 'Eventide H3000 B',
    'Opto Tremolo': 'Fender Opto Tr B',
    'Rotary Drum': 'Fender Vibrton B',
    'Rotary Drum/Horn': 'Leslie 145 B',
    'Red Comp': 'MXR Dyna Comp B',
    'Analog Flanger': 'MXR Flanger B',
    'Phaser': 'MXR Phase 90 B',
    'Tape Echo': 'Maestro EP-3 B',
    'V Tron': 'Mu-Tron III B',
    'Classic Dist': 'ProCo RAT B',
    'U-Vibe': 'Shin-ei Vibe B',
    'Tube Comp': 'Teletronx LA2A B',
    'Octave Fuzz': 'Tycobrahe Oct B',
    'Bias Tremolo': 'Vox AC15 Trem B',
}
EFFECTS.update(REPEATS)
# the menus' own short forms of some of these names
SHORT = {'ScriptModPhase': 'Script Mod Phase', 'Courtesan Flngr': 'Courtesan Flange', 'Compulsive Drv': 'Compulsive Drive',
         'Deranged Mastr': 'Deranged Master', 'Deez One Vintg': 'Deez One Vintage', 'ZeroAmp BassDI': 'ZeroAmp Bass DI',
         'SwedishChainsw': 'Swedish Chainsaw', 'Rotary Speaker': 'Rotary Drum/Horn'}
NAMES = {**AMPS, **CABS, **EFFECTS}
NAMES.update({k: NAMES[v] for k, v in SHORT.items()})
assert all(1 <= len(v) <= MAX and v.isascii() for v in NAMES.values()), \
    [v for v in NAMES.values() if not 1 <= len(v) <= MAX]


def _name(b):
    return bytes(b).split(b'\0', 1)[0].decode('latin1')


def tables(e0):
    """(Table 2 rows [(va, name index, name)], menu items [(va, name index, name)]) of an HX Effects Entry 0."""
    import patch_amp as pa
    A = pa.EFFECTS_E0
    segs = pa._parse_e0_segments_any(bytearray(e0))
    fo = lambda va, n=4: pa._e0_vaddr_to_foff(segs, va, n)
    u32 = lambda va: struct.unpack_from('<I', e0, fo(va))[0]
    t2 = u32(A.TAB2_BASE_PTR)
    assert t2 == A.TAB2_BASE, f'Table 2 is at {t2:#x}, not the stock {A.TAB2_BASE:#x}'
    rows = []
    for i in range(A.TAB2_CNT):
        va = t2 + 44 * i
        rows.append((va, u32(va), _name(e0[fo(va + 4, 16): fo(va + 4, 16) + 16])))
    items = []
    for slot in range(52):
        lptr, lcnt = u32(A.BLIST_PTR_TAB + 4 * slot), u32(A.BLIST_CNT_TAB + 4 * slot)
        for k in range(lcnt if lptr else 0):
            va = lptr + 48 * k
            items.append((va, u32(va + 4), _name(e0[fo(va + 14, 26): fo(va + 14, 26) + 26])))
    return rows, items


def plan(e0):
    """{name index: (Line 6 name, real name)} for every block in this image that still shows a Line 6 name the
    table lists. A block in a menu goes by its menu name: Table 2's names are often cut short ('Mandarin Bass 20')
    and several cab rows carry another cab's name ('4x12 SoloLead EM' for 1x12 Cali IV, Cali EXT and the Del Sols);
    the cabs' menu names are the HX Stomp's. Table 2's name counts only for a block in no menu."""
    rows, items = tables(e0)
    menu = {}
    for _, idx, nm in items:
        menu.setdefault(idx, set()).add(nm)
    out = {}
    for idx, names in menu.items():
        listed = {NAMES[n] for n in names if n in NAMES}
        assert len(listed) <= 1, f'name index {idx}: menus {names} give two real names'
        if listed and names <= set(NAMES):        # every menu that lists it shows a Line 6 name
            out[idx] = (sorted(names)[0], listed.pop())
    for _, idx, nm in rows:
        if idx not in menu and nm in NAMES:
            out[idx] = (nm, NAMES[nm])
    return out


def patch_e0(e0):
    """(Entry 0 with the real names, the plan, the changed byte spans)."""
    import l6ia
    import patch_amp as pa
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments_any(e0)
    fo = lambda va, n: pa._e0_vaddr_to_foff(segs, va, n)
    p = plan(bytes(e0))
    rows, items = tables(bytes(e0))
    spans = []
    for va, idx, _ in rows:
        if idx in p:
            o = fo(va + 4, 16)
            e0[o:o + 16] = p[idx][1].encode('latin1').ljust(16, b'\0')
            spans.append((o, 16))
    for va, idx, _ in items:
        if idx in p:
            o = fo(va + 14, 26)
            e0[o:o + 26] = p[idx][1].encode('latin1').ljust(26, b'\0')
            spans.append((o, 26))
    return bytes(l6ia.fix_internal_crcs(bytes(e0))), p, spans


def check_image(old_arc, new_arc, p, spans):
    import l6ia
    import patch_amp as pa
    msgs, ok = [], True
    po, pn = l6ia.parse(old_arc), l6ia.parse(new_arc)
    raw = lambda img, q, k: img[q[k]['payload_off']: q[k]['payload_off'] + q[k]['payload_len']]
    diff = [k for k in range(len(po)) if raw(old_arc, po, k) != raw(new_arc, pn, k)]
    o0, n0 = bytes(pa.get_entry_swapped(old_arc, 0)), bytes(pa.get_entry_swapped(new_arc, 0))
    allowed = set(range(0, 0x34))
    for o, n in spans:
        allowed |= set(range(o, o + n))
    d0 = [i for i in range(len(o0)) if o0[i] != n0[i]] if len(o0) == len(n0) else None
    rows, items = tables(n0)
    shown = {}
    for _, idx, nm in rows + items:
        if idx in p:
            shown.setdefault(idx, set()).add(nm)
    # a listed Line 6 name left in a menu, or in Table 2 for a block in no menu (Table 2 rows of blocks that are in
    # a menu can carry another block's name: see plan)
    in_menu = {idx for _, idx, _ in items}
    still_l6 = sorted({nm for _, _, nm in items if NAMES.get(nm, nm) != nm} |
                      {nm for _, idx, nm in rows if NAMES.get(nm, nm) != nm and idx not in in_menu})
    # no two different blocks share a real name (a model's mono and stereo versions, and an amp and its preamp,
    # share their Line 6 name too; the menus' short forms count as their full names)
    who = {}
    for _, idx, nm in items:
        if idx in p:
            who.setdefault(p[idx][1], set()).add(SHORT.get(p[idx][0], p[idx][0]))
    shared = sorted(f'{r} ({", ".join(sorted(s))})' for r, s in who.items() if len(s) > 1)
    for c, m in ((diff == [0], 'only Entry 0 differs'),
                 (d0 is not None and set(d0) <= allowed, 'Entry 0: only block names (Table 2 and the menus) and the header'),
                 (all(shown[i] == {p[i][1]} for i in p), f'{len(p)} blocks now show their real names, in Table 2 and every menu'),
                 (not still_l6, 'no listed Line 6 name is left' + (f': {still_l6}' if still_l6 else '')),
                 (all(len(v) <= MAX for _, v in p.values()), f'every name fits in {MAX} characters'),
                 (not shared, 'no two different blocks show the same name' + (f': {shared}' if shared else ''))):
        msgs.append(('  ok   ' if c else '  FAIL ') + m)
        ok &= bool(c)
    return ok, msgs


def write_js():
    import json
    out = os.path.join(ROOT, 'tools', 'preset-builder', 'real-names.js')
    from cab_list import STOMP_CABS
    names = {k: v for k, v in NAMES.items() if k != v}
    cabs = {m: d for m, _, _, d in STOMP_CABS}
    open(out, 'w').write('// real-names.js - written by tools/real_names.py --js. Do not edit by hand.\n'
                         '// REAL_NAMES: Line 6 name -> the real gear\'s name, as build.py --real-names shows them on the unit (16\n'
                         '// characters at most). CAB_MENU_NAMES: each cab\'s name in the unit\'s Cabs menu (tools/cab_list.py): the\n'
                         '// firmware\'s model data gives 1x12 Cali IV, Cali EXT and both Del Sols the name "4x12 SoloLead EM".\n'
                         f'window.REAL_NAMES = {json.dumps(names, ensure_ascii=True, sort_keys=True)};\n'
                         f'window.CAB_MENU_NAMES = {json.dumps(cabs, ensure_ascii=True, sort_keys=True)};\n')
    print(f'{os.path.relpath(out, ROOT)}: {len(names)} names')


def main():
    if sys.argv[1:] == ['--js']:
        return write_js()
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        sys.exit(__doc__)
    import l6ia
    import patch_amp as pa
    base = os.path.abspath(sys.argv[1])
    arc, _ = pa.load_l6ia_from_any(base)
    assert pa.select_device(arc) is pa.EFFECTS_DSP, 'not an HX Effects image'
    e0n, p, spans = patch_e0(bytes(pa.get_entry_swapped(arc, 0)))
    out_arc, _, _ = l6ia.rebuild_archive(arc, {0: e0n})
    stem = os.path.splitext(os.path.basename(base))[0]
    image = os.path.join(ROOT, 'build', f'{stem}_RealNames.l6ia')
    out = os.path.join(ROOT, 'build', f'{stem}_RealNames.hxf')
    open(image, 'wb').write(out_arc)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'hxf.py'), 'pack', image, out, '--donor', STOCK],
                   check=True, capture_output=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'l6ia_verify.py'), image], capture_output=True, text=True)
    ok, msgs = check_image(arc, pa.load_l6ia_from_any(out)[0], p, spans)
    ok &= 'ALL OK' in r.stdout
    r0, i0 = tables(bytes(pa.get_entry_swapped(arc, 0)))
    unused = sorted(set(NAMES) - {nm for _, _, nm in r0 + i0})     # e.g. the amps in a NAM build
    print(('  ok   ' if 'ALL OK' in r.stdout else '  FAIL ') + 'every archive checksum holds (l6ia_verify)')
    print('\n'.join(msgs))
    for a, b in sorted(set(p.values()), key=lambda ab: ab[0].lower()):
        print(f'    {a:18} -> {b}')
    if unused:
        print(f'  (not in this build: {", ".join(unused)})')
    print(f'\n{os.path.relpath(out, ROOT)}\nMD5 {hashlib.md5(open(out, "rb").read()).hexdigest()}\n' + ('ALL OK' if ok else 'PROBLEMS'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
