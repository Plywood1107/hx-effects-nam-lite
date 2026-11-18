/* purewhitey.h - "Pure Whitey": a glitch short-time sampler. An original algorithm in the spirit of
 * sample-and-repeat glitch pedals (the Bananana Effects Mandala's modes); no vendor code or tables.
 * Forked from Stutter (effects/stutter) and reshaped.
 *
 * The sampler works in a cycle: LISTEN (the live input is heard on the wet path, faded in and out over
 * 32 samples, while the ring records it) for one slice length plus 4 samples, then CAPTURE the last slice
 * length of words recorded and PLAY it (the ring frozen) for the mode's number of passes, then LISTEN again.
 * The trigger modes play a slice for ever and start a new LISTEN at each pick attack instead (also during a
 * LISTEN; before the first attack the wet path is silent).
 *
 *   the ring: PUREWHITEY_RING 32-bit words of packed 16-bit samples (two a word, the low half first) at
 *   24 kHz (the mean of each pair of input samples), 8,192 samples = 0.34 s; a slice is always the last
 *   words a LISTEN wrote, so only what has been recorded is ever read.
 *   Time 0..1: a slice of Time^2 x 3,856 + 240 words (20 ms .. 0.34 s); at Time >= 0.99 a random length
 *   (at least PUREWHITEY_LMIN words) up to the whole ring each capture.
 *   playback: linear interpolation between the 24 kHz samples; each pass faded over 16 of them at both
 *   ends; speed in 24 kHz samples an output sample (0.5 = the original pitch), at most 2 (x4).
 *
 * Modes (Func per mode):
 *   0 Repeat   2 + (int)(Func x 15) passes; at 16 (Func >= 14/15) the slice loops for ever
 *   1 Random   a random length up to Time's, 1..4 passes at random, x2 speed when a draw < Func
 *   2 Reverse  2 passes backwards at x-1/2, x-1 or x-2 ((int)(Func x 2.99) octaves up)
 *   3 Trigger  a new slice from each pick attack (Sens), looped until the next
 *   4 Square Trigger  Trigger through the square treatment
 *   5 Square   4 passes through the square treatment
 *   6 Up       6 passes, the speed x (1.0625 + Func x 0.4375) after each
 *   7 Down     6 passes, the speed x (0.96875 - Func x 0.21875) after each
 * The square treatment (modes 4, 5): an envelope e (peak, 10 ms release), a comparator c = +-1 with
 * hysteresis e / 10, and a flip-flop f = +-1 toggled at each rise of c (the octave below);
 * wet = (c + Func x (f - c)) x e x 0.7.
 * Attacks: a fast envelope (5 ms release) rising above twice a slow one (50 ms) plus 0.002 + 0.25 (1 - Sens)^2.
 *
 * out = Dry x Level x in + Mix x Level x lowpass(wet), the one-pole lowpass's coefficient 0.03 + 0.97 Tone^2.
 *
 * Eight parameters, to fit the host model's knob words. Bit-exact on the SHARC port: no division, no
 * transcendental in process(), integer PRNG, constants rounded once.
 */
#ifndef PUREWHITEY_H
#define PUREWHITEY_H

#include "../common/fx.h"
#include <stdint.h>

enum { W_MODE, W_TIME, W_FUNC, W_SENS, W_TONE, W_DRY, W_MIX, W_LEVEL, W_NPARAMS };

#define PUREWHITEY_RING 4096           /* words (a power of two), two samples each */
#define PUREWHITEY_LMIN 32             /* the shortest slice, words */
#define PUREWHITEY_SEED 0x2545F491u

typedef struct {
    float smooth_r, slow_k, sq_r;       /* constants */
    float envf, envs;                   /* the attack detector */
    int prevc;
    unsigned rnd;
    int stage;                          /* -1 LISTEN, 0 idle, 1 PLAY */
    int w, ph;                          /* recording: the word, the phase 0..3 */
    uint32_t pend;                      /* the word being recorded */
    float acc;
    int mi, mn, plen;                   /* listening: elapsed, length (samples); the slice to take (words) */
    int start, left;                    /* playing: the slice's first word, passes left */
    float lm1, pos, sp;                 /* the slice's last position (24 kHz samples), position, speed */
    float sqe, sqc, sqf, lp;            /* the square treatment; the Tone lowpass */
    uint32_t ring[PUREWHITEY_RING];
} PurewhiteyState;

extern const FxAlgorithm fx_purewhitey;

/* Exposed for the SHARC port: the per-mode table, 10 rows of 8 words (passes, random passes mask, trigger,
   square, random lengths as ints; x2 chance, ramp a, speed, speed steps, ramp b as floats). */
void purewhitey_mode_table(uint32_t *t);

#endif
