/* greasy.h - "Greasy Strangler": a drone that follows the guitar. Doom Chug's four-voice drone, retuned to the
 * last note played, found by Corrupt's pitch tracker. An original algorithm; no vendor code.
 *
 * Signal path (per sample):
 *   in -> (clamped to +-8) DC block -> two one-pole lowpasses (300 Hz: the tracking signal t)
 *      -> envelope follower (instant attack, 50 ms release)
 *      -> Schmitt comparator on t (hysteresis half the envelope); at each rising edge the period P in samples
 *      -> a note is caught when three periods in a row agree (each within 1/16 of the one before, all in
 *         24 .. 2400 samples: 20 Hz .. 2 kHz) with the envelope above -54 dB; the rate target becomes
 *         2^(Octave - 2) / mean of the last two periods, as the exact integer quotient
 *         (1 << (23 + Octave)) / (P + P_before) x 2^-24 cycles a sample. It holds until the next note is caught.
 *   four naive saws (root, root a little sharp, fifth, octave) at that rate x 2^(interval + Drift x a random walk
 *      + Warble x an LFO), each voice's level also moved by its LFO (Warble)
 *      -> sum x drive (Fuzz: 0.6 + 23.4 Fuzz^2) -> soft clip (1.5 x - 0.5 x^3 on [-1, 1])
 *      -> two one-pole lowpasses (Tone, 100 Hz .. 8 kHz) -> x Level x (1 - 0.45 Fuzz) -> + Dry x the input.
 *
 * Every 16 samples (the control rate, 3 kHz): the rate glides to its target (one-pole, k = exp(g (2 - g) x ln 3e-4), g = Glide:
 * instant, 150 ms at 0.5, about 1.1 s at 1; the first note is taken at once), the drone fades in (about 70 ms) once it has a note,
 * every 2048 ticks (0.68 s) each voice gets a new random walk target and LFO speed (0.3 .. 6.3 Hz) from
 * xorshift32, and each voice's pitch and gain ramp are worked out. Before the first note the drone is silent.
 *
 * Eight parameters, to fit the host model's knob words. Bit-exact on the SHARC port: no float division (the
 * quotient is integer arithmetic), geiger_exp the only transcendental, constants rounded once.
 */
#ifndef GREASY_H
#define GREASY_H

#include "../common/fx.h"

enum { GS_OCTAVE, GS_GLIDE, GS_DRIFT, GS_WARBLE, GS_FUZZ, GS_TONE, GS_DRY, GS_LEVEL, GS_NPARAMS };

#define GREASY_VOICES 4
#define GREASY_SEED 0x6A09E667u
#define GREASY_PMIN 24                 /* periods accepted, in samples */
#define GREASY_PMAX 2400
#define GREASY_CNT_MAX 4096            /* the period counter stops here */
#define GREASY_RETARGET 2047           /* new walk targets when (tick & this) == 0 */

typedef struct {
    unsigned rnd, tick;
    int cnt, prev, ok;                                  /* the tracker: samples since the last rising edge, */
    float dcx, dcy, lp1, lp2, env, sq;                  /* the period before, periods agreeing in a row */
    float rate_t, rate, fade, z1, z2;
    float d[GREASY_VOICES], dt[GREASY_VOICES];          /* the walk, its target */
    float lp[GREASY_VOICES], li[GREASY_VOICES];         /* LFO phase, its increment */
    float inc[GREASY_VOICES], ph[GREASY_VOICES];        /* the saw */
    float g[GREASY_VOICES], dg[GREASY_VOICES];          /* gain, its ramp a sample */
} GreasyState;

extern const FxAlgorithm fx_greasy;

#endif
