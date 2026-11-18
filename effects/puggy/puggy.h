/* puggy.h - "Puggy Puncher": a tempo-synced slot machine. On every step it rolls a random treatment for
 * the guitar for that step. An original algorithm; no vendor code.
 *
 * Timing is Click's (effects/metronome): Time is one beat in seconds (an HX delay's Time knob, synced to
 * tap tempo or not), turned into BPM x 100 by click_bpm100's integer division. Two exact integer
 * accumulators run from it, so nothing drifts:
 *   the beat:  gains BPM x 100 a sample, a beat at sr x 6000 (Click's tick); four beats are a bar;
 *   the step:  gains BPM x 100 x M a sample (M = 6 x steps a beat, from the Step list), a step at sr x 36000.
 * Step k therefore lands on the first sample at or after k step lengths. At every bar the step accumulator
 * is set to what it would hold on the straight grid (beat phase x M) and a step fires: for straight and
 * triplet values that is a step anyway, so the grid is unchanged; dotted values restart on the bar (3+3+2).
 * The first sample after reset() is the start of a bar.
 *
 * On a step, unless a roll is being held: xorshift32; if the top 24 bits are under Chance x 2^24 the step
 * gets a treatment from the Wild set (8 nibbles, picked by the low 3 bits), else it is clean. A roll lasts
 * Hold steps (the hold restarts at every bar). Seed 1..16 reseeds the generator at reset and at every bar,
 * so each bar repeats exactly; Seed 0 (Random) seeds once at reset and runs on.
 *
 * Treatments (all run every sample; the output crossfades from the previous step's to this step's over
 * 32 samples at every step edge):
 *   0 clean   the input
 *   1 octave  two one-poles at 300 Hz -> envelope (instant attack, 50 ms release) -> Schmitt comparator
 *             (hysteresis half the envelope) toggling a flip-flop on each rising edge: a square an octave
 *             down, at the envelope's level, plus half the input
 *   2 crush   sample-and-hold every 6 samples (8 kHz), then truncated to 1/16 steps
 *   3 mute    silence
 *   4 filter  Chamberlin low-pass (damping 0.4) whose coefficient snaps open (8 kHz) on every step and
 *             closes towards 200 Hz (time constant 25 ms; the snap itself smoothed over about 32 samples)
 *   5 fuzz    x 40, hard clipped at +-1, x 0.3
 * then  y = Level x (x + Mix x (wet - x)): Chance 0 at Level 1 is exactly the input whatever Mix is.
 *
 * Bit-exact on the SHARC port (sharc/puggy_kernel.asm): integer timing, no division but click_bpm100's
 * integer one, constants rounded once (puggy_k, which the port reads), -ffp-contract=off.
 */
#ifndef PUGGY_H
#define PUGGY_H

#include "../common/fx.h"

enum { PG_TIME, PG_STEP, PG_CHANCE, PG_WILD, PG_HOLD, PG_SEED, PG_MIX, PG_LEVEL, PG_NPARAMS };
enum { PT_CLEAN, PT_OCTAVE, PT_CRUSH, PT_MUTE, PT_FILTER, PT_FUZZ, PUGGY_TREATMENTS };

#define PUGGY_STEPS 11                     /* Step list: 1/2 .. 1/32 */
#define PUGGY_WILDS 11                     /* Wild list */
#define PUGGY_SEEDS 17                     /* Seed list: Random, 1..16 */
#define PUGGY_SEED0 0x2545F491u            /* the generator's seed at reset */
#define PUGGY_XF    0.03125f               /* the crossfade: 32 samples */
#define PUGGY_CRATE 6                      /* crush: hold every 6 samples */

/* Constants rounded once; the SHARC port reads this table. */
enum { PK_TA, PK_REL, PK_HYST, PK_ODRY, PK_SLAM, PK_FS, PK_FLO, PK_FD0, PK_FQ, PK_FG, PK_FL, PUGGY_NK };
extern const float puggy_k[PUGGY_NK];

typedef struct {
    uint32_t period, speriod;              /* sr x 6000 (a beat at 1 BPM x 100), x 6 (a step at M = 1) */
    uint32_t bacc, sacc;                   /* beat and step phases */
    int started, beat;                     /* beat in the bar, 0..3 */
    uint32_t rnd;
    int hold, roll;                        /* steps left of the held roll; the roll */
    int cur, prev;                         /* this step's treatment, the last step's */
    float xg;                              /* crossfade weight of prev, 1 -> 0 */
    float t1, t2, env;                     /* octave: tracking lowpasses, envelope */
    int hi, ff;                            /* comparator state, flip-flop */
    int ccnt;                              /* crush */
    float held;
    float fd, fs, low, band;               /* filter: coefficient above the floor, smoothed; SVF state */
    uint32_t steps;                        /* bookkeeping the tests read */
} PuggyState;

extern const FxAlgorithm fx_puggy;

/* Exposed for the tests and the SHARC port. */
int puggy_stepmul(int step);               /* M: 6 x steps a beat */
uint32_t puggy_wild(int wild);             /* eight treatment nibbles, entry 0 in the low bits */
uint32_t puggy_seed(int seed);             /* 0 for Random, else the bar's seed */

#endif
