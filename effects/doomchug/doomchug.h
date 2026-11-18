/* doomchug.h - "Doom Chug": a low, dark four-voice drone generator that ignores the guitar, made to be fed
 * into the glitch effects. An original algorithm; no vendor code.
 *
 * Signal path:
 *   four naive saws (root, root a little sharp, fifth, octave)
 *      -> sum -> Fuzz drive -> soft clip (1.5 x - 0.5 x^3 on [-1, 1]) -> two one-pole lowpasses (Tone)
 *      -> Level -> added to the input, which passes through untouched.
 *
 * Every 16 samples (the control rate, 3 kHz) each voice's pitch is, in octaves above low A (110 Hz):
 *   base (Key + the Pattern step + the voice's interval, gliding) + Drift x a random walk + Warble x an LFO
 * Pitch only ever goes up from the base, so nothing sounds below 110 Hz; above two octaves it folds back,
 * so nothing sounds above 440 Hz.
 * A step every 1/Rate seconds moves the pattern, gives every voice a new random target and a new LFO
 * speed (0.3 .. 6.3 Hz), and restarts a thud envelope (decaying in about 0.2 s, a fixed 0.4 deep; it was the
 * Chug knob until 2026-11-17). Warble also moves each voice's level with its LFO.
 * Fuzz drives the voice sum into the soft clip, 1x at 0 to 40x at 1 (0.6 + 23.4 Fuzz^2 times the sum), so at
 * high settings the clip squares the drone off into a fuzz wall; Level is scaled by 1 - 0.45 Fuzz so the louder
 * clipped signal comes out at about the same level.
 *
 * Eight parameters, to fit the host model's knob words. Bit-exact on the SHARC port: no division, the only
 * transcendental is geiger_exp, constants rounded once.
 */
#ifndef DOOMCHUG_H
#define DOOMCHUG_H

#include "../common/fx.h"

enum { Q_KEY, Q_PATTERN, Q_RATE, Q_DRIFT, Q_WARBLE, Q_FUZZ, Q_TONE, Q_LEVEL, Q_NPARAMS };

#define DOOMCHUG_VOICES 4
#define DOOMCHUG_PATTERNS 9                /* 0 = Off, 1..8 */
#define DOOMCHUG_SEED 0x2F6E2B1Du

typedef struct {
    int step, cnt;
    unsigned rnd;
    float sphase, env, z1, z2, tone_a;
    float base[DOOMCHUG_VOICES], d[DOOMCHUG_VOICES], dt[DOOMCHUG_VOICES];     /* pitch, walk, walk's target */
    float lp[DOOMCHUG_VOICES], li[DOOMCHUG_VOICES];                           /* LFO phase, its increment */
    float inc[DOOMCHUG_VOICES], ph[DOOMCHUG_VOICES];                          /* the saw */
    float g[DOOMCHUG_VOICES], dg[DOOMCHUG_VOICES];                            /* gain, its ramp a sample */
} DoomChugState;

extern const FxAlgorithm fx_doomchug;

/* Exposed for the tests and the SHARC port: eight 4-bit semitone steps, step 0 in the low bits. */
unsigned doomchug_pattern(int p);

#endif
