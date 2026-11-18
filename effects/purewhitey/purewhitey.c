#include "purewhitey.h"

#include <math.h>
#include <string.h>

static const FxParamDesc PARAMS[W_NPARAMS] = {
    { "mode",  "Mode",  FX_INTEGER,    0.0f, 7.0f, 0.0f,  "0 Repeat, 1 Random, 2 Reverse, 3 Trigger, 4 Square Trigger, 5 Square, 6 Up, 7 Down", "immediate" },
    { "time",  "Time",  FX_CONTINUOUS, 0.0f, 1.0f, 0.5f,  "20 ms .. 0.34 s, random at 1", "immediate" },
    { "func",  "Func",  FX_CONTINUOUS, 0.0f, 1.0f, 0.5f,  "per mode", "immediate" },
    { "sens",  "Sens",  FX_CONTINUOUS, 0.0f, 1.0f, 0.5f,  "attack sensitivity", "immediate" },
    { "tone",  "Tone",  FX_CONTINUOUS, 0.0f, 1.0f, 0.8f,  "", "immediate" },
    { "dry",   "Dry",   FX_CONTINUOUS, 0.0f, 1.0f, 1.0f,  "x (shown as %)", "immediate" },
    { "mix",   "Mix",   FX_CONTINUOUS, 0.0f, 1.0f, 1.0f,  "x (shown as %)", "immediate" },
    { "level", "Level", FX_CONTINUOUS, 0.0f, 1.0f, 1.0f,  "x (shown as %)", "immediate" },
};

/* Per mode (Repeat, Random, Reverse, Trigger, Square Trigger, Square, Up, Down). */
static const int REPS[8] = { 0, 1, 2, 16, 16, 4, 6, 6 };     /* passes (16: for ever; Repeat's from Func) */
static const int RMASKS[8] = { 0, 3, 0, 0, 0, 0, 0, 0 };     /* plus a random 0..this */
static const int TRIG[8] = { 0, 0, 0, -1, -1, 0, 0, 0 };     /* a new slice at each attack */
static const int SQ[8] = { 0, 0, 0, 0, 1, 1, 0, 0 };         /* the square treatment */
static const int RL[8] = { 0, 1, 0, 0, 0, 0, 0, 0 };         /* random lengths up to Time's */
static const float P2M[8] = { 0, 16777216.0f, 0, 0, 0, 0, 0, 0 };   /* x2 when a 24-bit draw < Func x this */
static const float RA[8] = { 0, 0, 0, 0, 0, 0, 0.4375f, -0.21875f };  /* speed x (Func x RA + RB) each pass */
static const float RB[8] = { 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0625f, 0.96875f };
static const float SPD[8] = { 0.5f, 0.5f, -0.25f, 0.5f, 0.5f, 0.5f, 0.5f, 0.5f };
static const float KM[8] = { 0, 0, 2.99f, 0, 0, 0, 0, 0 };   /* speed x 2^(int)(Func x this) */

void purewhitey_mode_table(uint32_t *t)
{
    int k;
    for (k = 0; k < 8; k++) {
        t[k] = (uint32_t)REPS[k];
        t[8 + k] = (uint32_t)RMASKS[k];
        t[16 + k] = (uint32_t)TRIG[k];
        t[24 + k] = (uint32_t)SQ[k];
        t[32 + k] = (uint32_t)RL[k];
        memcpy(&t[40 + k], &P2M[k], 4);
        memcpy(&t[48 + k], &RA[k], 4);
        memcpy(&t[56 + k], &SPD[k], 4);
        memcpy(&t[64 + k], &KM[k], 4);
        memcpy(&t[72 + k], &RB[k], 4);
    }
}

#define RMASK (PUREWHITEY_RING - 1)
#define QMAX2 (2.0f * 32767.0f / 32768.0f)

static void reset(void *st, float sr)
{
    PurewhiteyState *s = st;
    memset(s, 0, sizeof *s);
    s->smooth_r = (float)exp(-1.0 / (0.005 * sr));       /* the fast envelope's release */
    s->slow_k = (float)(1.0 - exp(-1.0 / (0.05 * sr)));   /* the slow envelope */
    s->sq_r = (float)exp(-1.0 / (0.01 * sr));            /* the square's envelope release */
    s->rnd = PUREWHITEY_SEED;
    s->sqf = 1.0f;
}

static unsigned next(PurewhiteyState *s)
{
    s->rnd ^= s->rnd << 13;
    s->rnd ^= s->rnd >> 17;
    s->rnd ^= s->rnd << 5;
    return s->rnd >> 8;
}

/* One 24 kHz sample of the slice: k samples from its first word. */
static float sample(const PurewhiteyState *s, int k)
{
    uint32_t wd = s->ring[(s->start + (k >> 1)) & RMASK];
    int q = (k & 1) ? (int)(int16_t)(uint16_t)(wd >> 16) : (int)(int16_t)(uint16_t)(wd & 0xFFFFu);
    return (float)q * (1.0f / 32768.0f);
}

static void process(void *st, const FxParams *p, const float *in, float *out, size_t n)
{
    PurewhiteyState *s = st;
    const FxParamDesc *d = PARAMS;
    int mode = (int)fx_param_clamp(&d[W_MODE], p->value[W_MODE]);
    float time = fx_param_clamp(&d[W_TIME], p->value[W_TIME]);
    float func = fx_param_clamp(&d[W_FUNC], p->value[W_FUNC]);
    float sens = fx_param_clamp(&d[W_SENS], p->value[W_SENS]);
    float tone = fx_param_clamp(&d[W_TONE], p->value[W_TONE]);
    float level = fx_param_clamp(&d[W_LEVEL], p->value[W_LEVEL]);
    float dl = fx_param_clamp(&d[W_DRY], p->value[W_DRY]) * level;
    float ml = fx_param_clamp(&d[W_MIX], p->value[W_MIX]) * level;
    float base = time * time * 3856.0f + 240.0f;
    float thr = (1.0f - sens) * (1.0f - sens) * 0.25f + 0.002f;
    float tk = tone * tone * 0.97f + 0.03f;
    float ramp = func * RA[mode] + RB[mode];
    float spd = ldexpf(SPD[mode], (int)(func * KM[mode]));
    unsigned p2 = (unsigned)(func * P2M[mode]);
    int reps = REPS[mode], rl = RL[mode], trig = TRIG[mode];
    size_t i;

    if (mode == 0) {                                     /* Repeat: 2 .. 16 (= for ever) passes */
        reps = 2 + (int)(func * 15.0f);
        if (reps > 16) reps = 16;
    }
    if (time >= 0.99f) {                                 /* a random length up to the whole ring */
        base = 4096.0f;
        rl = 1;
    }

    for (i = 0; i < n; i++) {
        float x = in[i], a, y, wet = 0.0f;
        int c, fire;
        if (!(fabsf(x) <= 8.0f)) x = 0.0f;

        a = fabsf(x);                                    /* the attack detector */
        s->envf = fmaxf(s->envf * s->smooth_r, a);
        s->envs += s->slow_k * (a - s->envs);
        c = s->envf > 2.0f * s->envs + thr;
        fire = c && !s->prevc;
        s->prevc = c;

        if (trig ? fire : s->stage == 0) {               /* LISTEN: choose the next slice's length */
            unsigned r = next(s);
            int lw = (int)(rl ? (float)r * (1.0f / 16777216.0f) * base : base);
            if (lw < PUREWHITEY_LMIN) lw = PUREWHITEY_LMIN;
            s->plen = lw;
            s->mn = 4 * (lw + 1);                        /* at least lw whole words are recorded */
            s->mi = 0;
            s->stage = -1;
        }

        if (s->stage > 0) {                              /* PLAY */
            int j = (int)s->pos;
            float fj = (float)j, f = s->pos - fj, v0, v1, e;
            v0 = sample(s, j);
            v1 = fj < s->lm1 ? sample(s, j + 1) : v0;    /* never past the slice */
            wet = v0 + f * (v1 - v0);
            e = fminf(s->lm1 - s->pos, s->pos) * 0.0625f;   /* the fades at both ends */
            wet = wet * fminf(e, 1.0f);
            s->pos += s->sp;
            if (s->pos >= s->lm1 || s->pos < 0.0f) {     /* a pass done */
                if (s->pos >= s->lm1) s->pos = s->pos - s->lm1;
                else s->pos += s->lm1;
                s->sp = s->sp * ramp;
                if (s->sp > 2.0f) s->sp = 2.0f;
                if (s->sp < -2.0f) s->sp = -2.0f;
                if (reps < 16) s->left--;
                if (s->left <= 0) s->stage = 0;
            }
        } else {
            float prev = s->acc;
            s->acc = x;
            if (s->ph & 1) {                             /* RECORD: the mean of two samples, 16 bits */
                float m = prev + x;
                int q;
                if (m > QMAX2) m = QMAX2;
                if (m < -QMAX2) m = -QMAX2;
                q = (int)(m * 16384.0f);
                s->pend = (s->pend >> 16) | ((uint32_t)q << 16);
                s->ring[s->w] = s->pend;                 /* complete at phase 3 */
                if (s->ph & 2) s->w = (s->w + 1) & RMASK;
            }
            s->ph = (s->ph + 1) & 3;
            if (s->stage < 0) {                          /* LISTEN: the live input, faded at both ends */
                int dd = s->mn - s->mi;
                if (s->mi < dd) dd = s->mi;
                wet = x * fminf((float)dd * 0.03125f, 1.0f);
                s->mi++;
                if (s->mi >= s->mn) {                    /* CAPTURE the last plen words recorded */
                    unsigned r = next(s);
                    s->start = (s->w - s->plen) & RMASK;
                    s->lm1 = (float)(2 * s->plen - 1);
                    s->sp = r < p2 ? spd + spd : spd;
                    s->left = reps + (int)(r & (unsigned)RMASKS[mode]);
                    s->pos = s->sp > 0.0f ? 0.0f : s->lm1;
                    s->stage = 1;
                }
            }
        }

        if (SQ[mode]) {                                  /* the square treatment */
            float h, nc;
            a = fabsf(wet);
            s->sqe = fmaxf(s->sqe * s->sq_r, a);
            h = s->sqe * 0.1f;
            nc = s->sqc;
            if (wet > h) nc = 1.0f;
            if (wet < -h) nc = -1.0f;
            if (nc > s->sqc) s->sqf = -s->sqf;           /* the octave below: toggled as the square rises */
            s->sqc = nc;
            wet = (nc + (s->sqf - nc) * func) * s->sqe * 0.7f;
        }

        s->lp += tk * (wet - s->lp);                     /* Tone */
        y = dl * x + ml * s->lp;
        if (!(fabsf(y) <= 8.0f)) y = 0.0f;              /* never pass on a bad value */
        out[i] = y;
    }
}

const FxAlgorithm fx_purewhitey = {
    "purewhitey", "Pure Whitey", sizeof(PurewhiteyState), PARAMS, W_NPARAMS, reset, process,
};
