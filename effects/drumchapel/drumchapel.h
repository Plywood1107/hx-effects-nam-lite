/* drumchapel.h - "Drum Chapel": a basic drum machine block. An original algorithm; no vendor code or samples.
 *
 * The guitar passes through at exactly unity (a non-finite input sample is replaced by 0); synthesised drums
 * are added. Three voices (kick, snare, hat) play 16-step patterns (sixteenths of a 4/4 bar), one bit a step.
 *
 * Timing is Click's (effects/metronome): Time is one beat in seconds (0.1 .. 4.0, an HX delay's Time knob,
 * tap tempo), turned into BPM x 100 by click_bpm100; an integer accumulator gains BPM x 100 x 4 a sample and a
 * sixteenth falls when it reaches 48,000 x 6,000. Step k therefore lands on the first sample at or after
 * k x 15 / BPM s, with no drift. The first sample after reset() is step 0 of the bar. Swing delays every odd
 * sixteenth until the accumulator has also passed Swing x 1/3 of a sixteenth (Swing 1: a triplet shuffle).
 *
 * One set of voice algorithms; a kit is a table of numbers (drumchapel_kit_words):
 *   tone   kick and snare: a parabolic sine whose rate falls exponentially from start to end pitch
 *          (inc = end + sweep x pe, pe *= PD); the snare adds a second mode at 1.84 x its rate (M2);
 *          the hat's tone is six detuned square oscillators (the 808's metal), phases from the hit's age.
 *          The tone is multiplied by TDRIVE and clipped to +-1 (TDRIVE 40: square waves, the Bit kit).
 *   noise  xorshift32, held for HOLD samples (sample-and-hold, the Bit kit), through a one-pole lowpass
 *          (NF > 0) or the highpass beside it (NF < 0); the hat's tone goes through this filter too.
 *   env    tone and noise decay exponentially (TD, ND); after GATE samples the noise decays in about 3 ms
 *          (the Eighty kit's gated snare tail). A voice stops when both envelopes are under -90 dB.
 *   kit    the three voices summed -> x DRIVE -> clip +-1 -> 1.5 z - 0.5 z^3 -> x COMP -> x Level.
 *
 * Eight parameters (the host model's eight knob words). Bit-exact on the SHARC port: no division, no
 * transcendental at run time, every table built once in double and rounded once, -ffp-contract=off.
 * The tables assume 48 kHz (the unit's rate) whatever reset() is given.
 */
#ifndef DRUMCHAPEL_H
#define DRUMCHAPEL_H

#include "../common/fx.h"

enum { DC_TIME, DC_PATTERN, DC_KIT, DC_KICK, DC_SNARE, DC_HAT, DC_SWING, DC_LEVEL, DC_NPARAMS };

#define DRUMCHAPEL_VOICES 3
#define DRUMCHAPEL_STEPS 16
#define DRUMCHAPEL_PATTERNS 20
#define DRUMCHAPEL_KITS 6
#define DRUMCHAPEL_METAL 6
#define DRUMCHAPEL_SEED 0x6D2B79F5u
#define DRUMCHAPEL_PERIOD 288000000u          /* 48,000 x 60 x 100: a sixteenth, in BPM x 100 x 4 per sample */
#define DRUMCHAPEL_SWING_MAX 96000000.0f      /* a third of the period */
#define DRUMCHAPEL_NO_GATE 0x7FFFFFFFu

enum { KICK, SNARE, HAT };
enum { KIT_BOOM, KIT_PUNCH, KIT_TICK, KIT_BIT, KIT_DOOM, KIT_EIGHTY };

/* A kit's words: kit-wide first, then each voice's DV_WORDS. Floats are stored as their bits; HOLD, GATE are integers. */
enum { DK_DRIVE, DK_COMP, DK_TDRIVE, DK_M2, DK_HOLD, DK_GATE, DK_V0 };
enum { DV_INC, DV_SWEEP, DV_PD, DV_TD, DV_ND, DV_TLEV, DV_NLEV, DV_NF, DV_WORDS };
#define DK_WORDS (DK_V0 + DRUMCHAPEL_VOICES * DV_WORDS)

typedef struct {
    float ph, ph2, pe, te, ne;             /* tone phases (0..1), pitch envelope, tone and noise envelopes */
    uint32_t age;                          /* samples since the hit */
    float lp;                              /* the noise filter */
} DrumVoice;

typedef struct {
    uint32_t acc, step, pend, rnd, hcnt;   /* tempo phase, the step due, whether it is still to fire; noise */
    DrumVoice v[DRUMCHAPEL_VOICES];
    /* bookkeeping the tests read (not in the SHARC port's state) */
    uint32_t fires, last_step, hits[DRUMCHAPEL_VOICES];
    uint64_t sample;
} DrumChapelState;

extern const FxAlgorithm fx_drumchapel;

/* For the tests and the SHARC port. */
const uint32_t *drumchapel_kit_words(int kit);      /* DK_WORDS words */
uint32_t drumchapel_pattern_ks(int p);              /* kick steps | snare steps << 16 (bit k = step k) */
uint32_t drumchapel_pattern_hat(int p);             /* hat steps */
const uint32_t *drumchapel_metal(void);             /* the six squares' phase increments (2^32 = one cycle) */
const char *drumchapel_pattern_name(int p);
const char *drumchapel_kit_name(int kit);
extern const float drumchapel_r2, drumchapel_third, drumchapel_silent, drumchapel_gate_k;

#endif
