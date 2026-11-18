/* bethblahem.h - "Bethblahem": a mega-low-tuned theremin. An original algorithm; no vendor code.
 *
 * Signal path (per sample):
 *   in -> (not finite: 0; clamped to +-16)
 *      -> Corrupt's tracker: DC block, two one-pole lowpasses (300 Hz: the tracking signal t), envelope
 *         (instant attack, 50 ms release), Schmitt comparator on t, the period P between its rising edges
 *      -> a period is taken when the envelope is over -54 dB, 16 <= P <= 2400 and it is within 1/16 of the
 *         period before it; then the held rate becomes the exact integer quotient 2^28 / P, x 2^-28
 *         cycles a sample. Nothing else changes it: the last note is held for ever.
 *      -> x 2^-Octave (0..4 octaves down) -> Glide: a one-pole on the rate, 10 ms .. 2 s
 *      -> x the vibrato (a sine LFO at Rate, 3..8 Hz, depth up to +-6 %), updated every 16 samples
 *      -> a phase accumulator: a sine (an odd degree-7 polynomial on a folded phase) and, from the same
 *         phase and a flag toggled on each cycle, a sine an octave below it (Sub)
 *      -> v = sine + Sub x sub sine; Growl: v + Growl x (soft(v x (1 + 7 Growl) + 0.4 Growl) - v)
 *         (soft: clamp to +-1, then 1.5 c - 0.5 c^3: odd harmonics, and even ones from the offset)
 *      -> x Level x a fade-in (30 ms, from the first note taken) -> the limiter 0.4 x soft(): at most 0.4
 *      -> a fixed 6 Hz one-pole high-pass (DC and the subsonic) -> plus Dry x the input -> out
 *
 * The synth part of the output is bounded by 0.8 whatever comes in. Eight parameters, to fit the host
 * model's knob words. Bit-exact on the SHARC port: no float division, geiger_exp the only transcendental,
 * every constant a float literal (48 kHz).
 */
#ifndef BETHBLAHEM_H
#define BETHBLAHEM_H

#include "../common/fx.h"

enum { B_OCTAVE, B_GLIDE, B_VIBRATO, B_RATE, B_GROWL, B_SUB, B_DRY, B_LEVEL, B_NPARAMS };

#define BETHBLAHEM_PMIN 16                /* periods accepted, in samples */
#define BETHBLAHEM_PMAX 2400
#define BETHBLAHEM_CNT_MAX 4096           /* the period counter stops here */

typedef struct {
    float dcx, dcy, lp1, lp2, env, sq;                  /* the tracker */
    int cnt, pl;                                        /* samples since the last rising edge, the last period */
    float inct, have;                                   /* the held rate (unison), 1 once a note was taken */
    float inc, ph, subf, lfo, vmul, amp;                /* the voice */
    float ox, oy;                                       /* the output high-pass */
    int tick;                                           /* 0..15: the vibrato moves at 0 */
} BethblahemState;

extern const FxAlgorithm fx_bethblahem;

/* Exposed for the tests: sin(2 pi p) for 0 <= p < 1, as the voice computes it. */
float bethblahem_sin(float p);

#endif
