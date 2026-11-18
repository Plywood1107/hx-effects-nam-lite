/* drumchapel.h - "Drum Chapel": a basic drum machine block. An original algorithm; no vendor code. The Acoustic
 * kit's kick and snare samples are converted locally from the user's own recordings and never committed.
 *
 * The guitar passes through at exactly unity (a non-finite input sample is replaced by 0); synthesised drums
 * are added. Four voices (kick, snare, hat, tom) play grooves of sixteenths, one byte a step (DC_B_*).
 *
 * Timing is Click's (effects/metronome): Time is one beat in seconds (0.1 .. 4.0, an HX delay's Time knob,
 * tap tempo), turned into BPM x 100 by click_bpm100; an integer accumulator gains BPM x 100 x 4 a sample and a
 * sixteenth falls when it reaches 48,000 x 6,000. Step k therefore lands on the first sample at or after
 * k x 15 / BPM s, with no drift. The first sample after reset() is step 0. Swing delays every odd sixteenth
 * until the accumulator has also passed Swing x 1/3 of a sixteenth (Swing 1: a triplet shuffle).
 *
 * Grooves: Groove 0 is Classic, the 20 one-bar patterns below (16 steps); Grooves 1..11 are families of longer
 * grooves converted from a folder of MIDI loops by grooves.py into grooves_data.h, which is git-ignored (the
 * loops are licensed) and optional: without it, or for a family it lacks, a Groove plays the Classic patterns.
 * Pattern picks the pattern (Classic) or the variation (a family: Pattern mod the family's size). The step
 * counter wraps at the groove's length (up to DRUMCHAPEL_MAX_STEPS sixteenths, the groove's own meter); a step
 * looks the groove up when it falls and continues at (step mod the new length), so a change mid-play does not
 * restart it. Every length is a multiple of 4, so the swing's odd steps stay odd.
 *
 * The bank (drumchapel_bank) is one table of words, as the kernel reads it from DDR2 (inside Blob 0):
 *   DIR    DRUMCHAPEL_GROOVES x DRUMCHAPEL_PATTERNS words, groove-major: (first step << 9) | length;
 *   STEPS  the steps, four to a word, step i in word DIR_WORDS + i / 4, bits 8 x (i % 4) up.
 *
 * One set of voice algorithms; a kit is a table of numbers (drumchapel_kit_words), five voice definitions:
 * kick, snare, closed hat, tom, open hat (a voice plays one of them: the hat voice the open one on DC_B_OPEN).
 *   tone   kick, snare and tom: a parabolic sine whose rate falls exponentially from start to end pitch
 *          (inc = (end + sweep x pe) x tune, pe *= PD); tune is 1 but for the tom, whose four pitches are
 *          DRUMCHAPEL_TUNE; the snare adds a second mode at 1.84 x its rate (M2);
 *          the hat's tone is six detuned square oscillators (the 808's metal), phases from the hit's age.
 *          The tone is multiplied by TDRIVE and clipped to +-1 (TDRIVE 40: square waves, the Bit kit).
 *   noise  xorshift32, held for HOLD samples (sample-and-hold, the Bit kit), through a one-pole lowpass
 *          (NF > 0) or the highpass beside it (NF < 0); the hat's tone goes through this filter too.
 *   env    tone and noise decay exponentially (TD, ND); after GATE samples the noise decays in about 3 ms
 *          (the Eighty kit's gated tails). A voice stops when both envelopes are under -90 dB.
 *   kit    the four voices summed -> x DRIVE -> clip +-1 -> 1.5 z - 0.5 z^3 -> x COMP -> x Level.
 * The tom plays at the Kick knob's level.
 *
 * Samples (the Acoustic kit, kit 6): a definition whose PD word is 0 is a sample (a synthesised one always has
 * PD > 0); its INC word is the sample's first index in the sample table (drumchapel_samples), SWEEP its length.
 * Acoustic's kick and snare are such definitions when samples_data.h exists (samples.py; git-ignored, the
 * recordings are the user's); without it they are Punch's synthesised kick and snare. The table: 16-bit samples
 * at 48 kHz, two to a word, sample i in word i / 2, its low half when i is even; a sample is q / 32768.
 * A sampled voice plays sample[age] x TE (TE = the knob's level at the hit, no envelope) and stops at the
 * sample's end (TE = 0). A retrigger while it sounds crossfades: the sounding hit keeps playing from its place
 * (POS2) at a level (NE) that falls linearly to 0 in 64 samples (PE = NE / 64 a sample), beside the new one.
 * Acoustic's DRIVE is low (0.25, COMP 1 / (1.5 x 0.25)): a full-scale sample passes the kit's clip and
 * 1.5 z - 0.5 z^3 shaper untouched but for 2 % (0.2 dB) at its very peak.
 *
 * Nine parameters (the host's knob words 5..11, 13, 14). Bit-exact on the SHARC port: no division, no
 * transcendental at run time, every table built once in double and rounded once, -ffp-contract=off.
 * The tables assume 48 kHz (the unit's rate) whatever reset() is given.
 */
#ifndef DRUMCHAPEL_H
#define DRUMCHAPEL_H

#include "../common/fx.h"

enum { DC_TIME, DC_PATTERN, DC_KIT, DC_KICK, DC_SNARE, DC_HAT, DC_SWING, DC_LEVEL, DC_GROOVE, DC_NPARAMS };

#define DRUMCHAPEL_VOICES 4
#define DRUMCHAPEL_DEFS 5
#define DRUMCHAPEL_STEPS 16                  /* a Classic pattern */
#define DRUMCHAPEL_PATTERNS 20               /* the Pattern knob */
#define DRUMCHAPEL_GROOVES 12                /* the Groove knob: Classic and 11 families */
#define DRUMCHAPEL_MAX_STEPS 384             /* the longest groove, sixteenths (24 bars of 4/4) */
#define DRUMCHAPEL_DIR_WORDS (DRUMCHAPEL_GROOVES * DRUMCHAPEL_PATTERNS)
#define DRUMCHAPEL_KITS 7
#define DRUMCHAPEL_SYNTH_KITS 6              /* Boom..Eighty: every voice synthesised */
#define DRUMCHAPEL_XF 64                     /* a sampled voice's retrigger crossfade, samples */
#define DRUMCHAPEL_METAL 6
#define DRUMCHAPEL_SEED 0x6D2B79F5u
#define DRUMCHAPEL_PERIOD 288000000u          /* 48,000 x 60 x 100: a sixteenth, in BPM x 100 x 4 per sample */
#define DRUMCHAPEL_SWING_MAX 96000000.0f      /* a third of the period */
#define DRUMCHAPEL_NO_GATE 0x7FFFFFFFu

enum { KICK, SNARE, HAT, TOM };                                   /* voices */
enum { DEF_KICK, DEF_SNARE, DEF_HAT, DEF_TOM, DEF_OPEN };          /* a kit's voice definitions */
enum { KIT_BOOM, KIT_PUNCH, KIT_TICK, KIT_BIT, KIT_DOOM, KIT_EIGHTY, KIT_ACOUSTIC };
enum { TOM_HIGH, TOM_MID, TOM_LOW, TOM_FLOOR };

/* A step's byte: one bit a voice (bit v = voice v), the hat open, the tom's pitch (TOM_*) in bits 5-6. */
#define DC_B_KICK 1u
#define DC_B_SNARE 2u
#define DC_B_HAT 4u
#define DC_B_TOM 8u
#define DC_B_OPEN 16u
#define DC_B_PITCH 5

/* A kit's words: kit-wide first, then each definition's DV_WORDS. Floats are stored as their bits; HOLD, GATE are integers. */
enum { DK_DRIVE, DK_COMP, DK_TDRIVE, DK_M2, DK_HOLD, DK_GATE, DK_V0 };
enum { DV_INC, DV_SWEEP, DV_PD, DV_TD, DV_ND, DV_TLEV, DV_NLEV, DV_NF, DV_WORDS };
#define DK_WORDS (DK_V0 + DRUMCHAPEL_DEFS * DV_WORDS)

typedef struct {
    float ph, ph2, pe, te, ne;             /* tone phases (0..1), pitch envelope, tone and noise envelopes */
    uint32_t age;                          /* samples since the hit */
    float lp;                              /* the noise filter */
    uint32_t def;                          /* the kit definition it plays (DEF_*) */
    float tune;                            /* its rate x (the tom's pitch; 1 otherwise) */
    uint32_t pos2;                         /* a sampled voice: the crossfading hit's place (NE its level, PE its fall) */
} DrumVoice;

typedef struct {
    uint32_t acc, step, pend, rnd, hcnt;   /* tempo phase, the step due, whether it is still to fire; noise */
    uint32_t len;                          /* the groove's length when the last step fell */
    DrumVoice v[DRUMCHAPEL_VOICES];
    /* bookkeeping the tests read (not in the SHARC port's state) */
    uint32_t fires, last_step, last_byte, hits[DRUMCHAPEL_VOICES], opens;
    uint64_t sample;
} DrumChapelState;

extern const FxAlgorithm fx_drumchapel;

/* For the tests and the SHARC port. */
const uint32_t *drumchapel_kit_words(int kit);      /* DK_WORDS words */
const uint32_t *drumchapel_bank(uint32_t *nwords);  /* the bank (above), as the kernel reads it */
int drumchapel_families(void);                      /* families in grooves_data.h (0: Classic only) */
int drumchapel_family_size(int groove);             /* variations of Groove 1..11 (0: missing); 20 for Classic */
uint32_t drumchapel_groove_len(int groove, int pattern);
uint32_t drumchapel_groove_step(int groove, int pattern, uint32_t k);   /* step k's byte */
const uint32_t *drumchapel_metal(void);             /* the six squares' phase increments (2^32 = one cycle) */
const uint32_t *drumchapel_tune(void);              /* the tom's four pitches, x its rate (float bits) */
const uint32_t *drumchapel_samples(uint32_t *nwords);   /* the sample table (above); 0 words without samples_data.h */
int drumchapel_sampled(void);                       /* 1: samples_data.h was there (Acoustic plays its samples) */
uint32_t drumchapel_sample_first(int voice);        /* KICK or SNARE: its first index in the table, and length */
uint32_t drumchapel_sample_len(int voice);
float drumchapel_sample(uint32_t i);                /* table sample i, as a float (q / 32768) */
const char *drumchapel_pattern_name(int p);
const char *drumchapel_kit_name(int kit);
extern const float drumchapel_r2, drumchapel_third, drumchapel_silent, drumchapel_gate_k, drumchapel_xf;

#endif
