#include "puggy.h"
#include "../metronome/metronome.h"           /* click_bpm100 */

#include <math.h>
#include <string.h>

static const FxParamDesc PARAMS[PG_NPARAMS] = {
    { "time",   "Time",   FX_CONTINUOUS, 0.1f, 4.0f, 0.5f, "s (one beat)", "immediate (BPM rounded to 0.01)" },
    { "step",   "Step",   FX_INTEGER,    0.0f, 10.0f, 8.0f,
      "0 1/2, 1 1/4., 2 1/4, 3 1/4T, 4 1/8., 5 1/8, 6 1/8T, 7 1/16., 8 1/16, 9 1/16T, 10 1/32", "immediate" },
    { "chance", "Chance", FX_CONTINUOUS, 0.0f, 1.0f, 0.5f, "probability a step is not clean", "immediate" },
    { "wild",   "Wild",   FX_INTEGER,    0.0f, 10.0f, 0.0f,
      "0 All, 1 Gentle, 2 Rhythm, 3 Mean, 4 Low, 5 Dirt, 6 Chop, 7 Octave, 8 Crush, 9 Filter, 10 Fuzz", "immediate" },
    { "hold",   "Hold",   FX_INTEGER,    1.0f, 8.0f, 1.0f, "steps a roll lasts", "immediate" },
    { "seed",   "Seed",   FX_INTEGER,    0.0f, 16.0f, 0.0f, "0 Random, 1..16 (repeats every bar)", "immediate" },
    { "mix",    "Mix",    FX_CONTINUOUS, 0.0f, 1.0f, 1.0f, "x (shown as %)", "immediate" },
    { "level",  "Level",  FX_CONTINUOUS, 0.0f, 1.0f, 1.0f, "x (shown as %)", "immediate" },
};

const float puggy_k[PUGGY_NK] = {
    0.0385088402f,      /* PK_TA:   one-pole at 300 Hz, 1 - exp(-2 pi 300 / 48000) */
    0.999583420f,       /* PK_REL:  50 ms release, exp(-1 / 2400) */
    0.5f,               /* PK_HYST: comparator hysteresis, x the envelope */
    0.5f,               /* PK_ODRY: the input under the octave square */
    0.999167014f,       /* PK_SLAM: the filter closing, 25 ms, exp(-1 / 1200) */
    0.0307667655f,      /* PK_FS:   the snap smoothed, 1 - exp(-1 / 32) */
    0.0261791911f,      /* PK_FLO:  2 sin(pi 200 / 48000): 200 Hz */
    1.0f - 0.0261791911f,   /* PK_FD0: from there to 1.0 (8 kHz) */
    0.4f,               /* PK_FQ:   damping (Q 2.5) */
    40.0f,              /* PK_FG:   fuzz gain */
    0.3f,               /* PK_FL:   fuzz level */
};

#define K(n) puggy_k[PK_##n]

/* M = 6 x steps a beat: 1/2, 1/4., 1/4, 1/4T, 1/8., 1/8, 1/8T, 1/16., 1/16, 1/16T, 1/32 */
static const int STEPMUL[PUGGY_STEPS] = { 3, 4, 6, 9, 8, 12, 18, 16, 24, 36, 48 };

#define NIB(a, b, c, d, e, f, g, h) \
    ((uint32_t)(a) | (uint32_t)(b) << 4 | (uint32_t)(c) << 8 | (uint32_t)(d) << 12 | \
     (uint32_t)(e) << 16 | (uint32_t)(f) << 20 | (uint32_t)(g) << 24 | (uint32_t)(h) << 28)
#define O PT_OCTAVE
#define C PT_CRUSH
#define M PT_MUTE
#define F PT_FILTER
#define Z PT_FUZZ
static const uint32_t WILD[PUGGY_WILDS] = {
    NIB(O, C, M, F, Z, C, M, F),            /* All */
    NIB(C, F, C, F, C, F, C, F),            /* Gentle: crush, filter */
    NIB(M, M, M, M, M, M, M, M),            /* Rhythm: mute (Chance sets how many steps stay clean) */
    NIB(Z, O, Z, O, Z, O, Z, O),            /* Mean: fuzz, octave */
    NIB(O, F, O, F, O, F, O, F),            /* Low: octave, filter */
    NIB(C, Z, C, Z, C, Z, C, Z),            /* Dirt: crush, fuzz */
    NIB(M, Z, M, C, M, Z, M, C),            /* Chop: mute, fuzz, crush */
    NIB(O, O, O, O, O, O, O, O),            /* Octave */
    NIB(C, C, C, C, C, C, C, C),            /* Crush */
    NIB(F, F, F, F, F, F, F, F),            /* Filter */
    NIB(Z, Z, Z, Z, Z, Z, Z, Z),            /* Fuzz */
};
#undef O
#undef C
#undef M
#undef F
#undef Z

static int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

int puggy_stepmul(int step) { return STEPMUL[clampi(step, 0, PUGGY_STEPS - 1)]; }
uint32_t puggy_wild(int wild) { return WILD[clampi(wild, 0, PUGGY_WILDS - 1)]; }

uint32_t puggy_seed(int seed)
{
    seed = clampi(seed, 0, PUGGY_SEEDS - 1);
    return seed ? ((uint32_t)seed * 0x9E3779B9u) ^ 0xA5A5A5A5u : 0u;
}

static void reset(void *st, float sr)
{
    PuggyState *s = st;
    memset(s, 0, sizeof *s);
    s->period = (uint32_t)(sr * 6000.0f + 0.5f);
    s->speriod = 6 * s->period;
    s->rnd = PUGGY_SEED0;
}

static void process(void *st, const FxParams *p, const float *in, float *out, size_t n)
{
    PuggyState *s = st;
    const FxParamDesc *d = PARAMS;
    uint32_t bpm = click_bpm100(fx_param_clamp(&d[PG_TIME], p->value[PG_TIME]));
    uint32_t mul = (uint32_t)puggy_stepmul((int)fx_param_clamp(&d[PG_STEP], p->value[PG_STEP]));
    uint32_t inc = bpm * mul;
    uint32_t thr = (uint32_t)(fx_param_clamp(&d[PG_CHANCE], p->value[PG_CHANCE]) * 16777216.0f);
    uint32_t wild = puggy_wild((int)fx_param_clamp(&d[PG_WILD], p->value[PG_WILD]));
    int hold = (int)fx_param_clamp(&d[PG_HOLD], p->value[PG_HOLD]);
    uint32_t seedv = puggy_seed((int)fx_param_clamp(&d[PG_SEED], p->value[PG_SEED]));
    float mix = fx_param_clamp(&d[PG_MIX], p->value[PG_MIX]);
    float level = fx_param_clamp(&d[PG_LEVEL], p->value[PG_LEVEL]);
    size_t i;

    for (i = 0; i < n; i++) {
        float x = in[i], w[PUGGY_TREATMENTS], a, h, f, hp, v, wet, y;
        int step = 0, bar = 0;
        if (!isfinite(x)) x = 0.0f;

        /* the clock */
        if (!s->started) {
            s->started = 1;
            bar = 1;
        } else {
            s->bacc += bpm;
            if (s->bacc >= s->period) {
                s->bacc -= s->period;
                s->beat = (s->beat + 1) & 3;
                bar = s->beat == 0;
            }
            if (!bar) {
                s->sacc += inc;
                if (s->sacc >= s->speriod) {
                    s->sacc -= s->speriod;
                    step = 1;
                }
            }
        }
        if (bar) {                                  /* back on the straight grid; the roll restarts */
            s->sacc = s->bacc * mul;
            s->hold = 0;
            if (seedv) s->rnd = seedv;
            step = 1;
        }
        if (step) {
            if (s->hold <= 0) {
                uint32_t r = s->rnd;
                r ^= r << 13;                       /* xorshift32 */
                r ^= r >> 17;
                r ^= r << 5;
                s->rnd = r;
                s->roll = (r >> 8) < thr ? (int)((wild >> (4 * (r & 7u))) & 15u) : PT_CLEAN;
                s->hold = hold;
            }
            s->hold--;
            s->prev = s->cur;
            s->cur = s->roll;
            s->xg = 1.0f;
            s->fd = K(FD0);
            s->steps++;
        }

        /* every treatment */
        w[PT_CLEAN] = x;

        s->t1 += K(TA) * (x - s->t1);               /* octave down */
        s->t2 += K(TA) * (s->t1 - s->t2);
        a = fabsf(s->t2);
        s->env *= K(REL);
        if (a > s->env) s->env = a;
        h = K(HYST) * s->env;
        if (s->hi) {
            if (s->t2 < -h) s->hi = 0;
        } else if (s->t2 > h) {
            s->hi = 1;
            s->ff ^= 1;
        }
        w[PT_OCTAVE] = K(ODRY) * x + (s->ff ? s->env : -s->env);

        if (++s->ccnt >= PUGGY_CRATE) {             /* crush */
            s->ccnt = 0;
            s->held = x;
        }
        v = s->held;
        if (v > 1.0f) v = 1.0f;
        else if (v < -1.0f) v = -1.0f;
        w[PT_CRUSH] = (float)(int)(v * 16.0f) * 0.0625f;

        w[PT_MUTE] = 0.0f;

        s->fd *= K(SLAM);                           /* filter slam */
        s->fs += K(FS) * (s->fd - s->fs);
        f = K(FLO) + s->fs;
        s->low += f * s->band;
        hp = x - s->low - K(FQ) * s->band;
        s->band += f * hp;
        w[PT_FILTER] = s->low;

        v = x * K(FG);                              /* fuzz */
        if (v > 1.0f) v = 1.0f;
        else if (v < -1.0f) v = -1.0f;
        w[PT_FUZZ] = v * K(FL);

        /* this step's, faded in from the last step's */
        wet = w[s->cur] + (w[s->prev] - w[s->cur]) * s->xg;
        s->xg -= PUGGY_XF;
        if (s->xg < 0.0f) s->xg = 0.0f;
        y = x + mix * (wet - x);
        y = y * level;
        if (!(fabsf(y) <= 8.0f)) {                  /* never pass on a bad value */
            s->t1 = s->t2 = s->env = s->held = s->low = s->band = 0.0f;
            y = 0.0f;
        }
        out[i] = y;
    }
}

const FxAlgorithm fx_puggy = {
    "puggy", "Puggy Puncher", sizeof(PuggyState), PARAMS, PG_NPARAMS, reset, process,
};
