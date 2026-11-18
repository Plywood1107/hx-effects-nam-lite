#include "greasy.h"
#include "../geiger/geiger.h"                 /* geiger_exp */

#include <math.h>
#include <string.h>

static const FxParamDesc PARAMS[GS_NPARAMS] = {
    { "octave", "Octave", FX_INTEGER,    0.0f, 3.0f, 1.0f,  "0 -2 oct, 1 -1 oct, 2 unison, 3 +1 oct", "immediate" },
    { "glide",  "Glide",  FX_CONTINUOUS, 0.0f, 1.0f, 0.3f,  "instant .. about 1 s", "immediate" },
    { "drift",  "Drift",  FX_CONTINUOUS, 0.0f, 1.0f, 0.25f, "", "immediate" },
    { "warble", "Warble", FX_CONTINUOUS, 0.0f, 1.0f, 0.35f, "", "immediate" },
    { "fuzz",   "Fuzz",   FX_CONTINUOUS, 0.0f, 1.0f, 0.3f,  "drive 1x .. 40x into the clip", "immediate" },
    { "tone",   "Tone",   FX_CONTINUOUS, 0.0f, 1.0f, 0.35f, "", "immediate" },
    { "dry",    "Dry",    FX_CONTINUOUS, 0.0f, 1.0f, 1.0f,  "x (shown as %)", "immediate" },
    { "level",  "Level",  FX_CONTINUOUS, 0.0f, 1.0f, 0.5f,  "x (shown as %)", "immediate" },
};

/* the tracker (Corrupt's front end) */
#define K_DC_R   0.998691022f                 /* 1 - 2 pi 10 / sr */
#define K_LPA    0.0385088399f                /* 1 - exp(-2 pi 300 / sr) */
#define K_REL    0.999583423f                 /* exp(-1 / (0.05 sr)) */
#define K_HYST   0.5f
#define K_HFLOOR 0.00001f
#define K_GATE   0.002f                       /* -54 dB: quieter than this, no new note */
#define K_IN     8.0f                         /* the tracker's input is clamped to this */
#define K_2M24   5.96046448e-8f               /* 2^-24 */
/* the drone (Doom Chug's) */
#define K_GL     (-8.11172771f)               /* ln(3e-4): Glide 1 -> the rate moves 3e-4 of the way a tick (about 1.1 s) */
#define K_FADE   0.005f                       /* the fade-in, a tick: about 70 ms */
#define K_LN80   4.38202667f
#define K_NEG_W  (-0.000130899687f)           /* -2 pi / sr */
#define K_LN2    0.693147182f
#define K_R      1.52587890625e-5f            /* 1 / 65536 */
#define K_LA     1.0e-4f                      /* 0.3 Hz, a tick */
#define K_LB     2.0e-3f                      /* 6 Hz */
#define K_WALK   0.001f
#define K_DRIFT  0.5f                         /* octaves at Drift 1 */
#define K_WARB   0.16f                        /* octaves at Warble 1, on the triangle 0..0.5 */
#define K_TREM   1.2f
#define K_Z      0.6f                         /* the voice sum's scale into the clip at Fuzz 0 */
#define K_DRV    23.4f                        /* K_Z x 39: Fuzz 1 drives the sum 40x */
#define K_COMP   0.45f                        /* Level falls by this much at Fuzz 1, against the louder clip */

static const float OFFSET[GREASY_VOICES] = { 0.0f, 0.012f, 0.583333313f, 1.0f };  /* root, sharp root, fifth, octave */

typedef struct {
    GreasyState s;
    int ctl;                                  /* samples into the 16-sample tick (the kernel's call) */
} Inst;

static void reset(void *st, float sr)
{
    Inst *t = st;
    (void)sr;
    memset(t, 0, sizeof *t);
    t->s.rnd = GREASY_SEED;
}

/* One control tick: the glide, the fade-in, the walks, the LFOs and each voice's rate and gain ramp. */
static void control(GreasyState *s, float glk, float dk, float wk, float tk)
{
    float k = glk;
    int v;

    if (s->rate == 0.0f) k = 1.0f;            /* the first note: no glide up from nothing */
    s->rate += k * (s->rate_t - s->rate);
    if (s->rate > 0.0f) s->fade += K_FADE * (1.0f - s->fade);
    if ((s->tick & GREASY_RETARGET) == 0u) {
        for (v = 0; v < GREASY_VOICES; v++) {
            s->rnd ^= s->rnd << 13;           /* xorshift32 */
            s->rnd ^= s->rnd >> 17;
            s->rnd ^= s->rnd << 5;
            s->dt[v] = (float)(s->rnd >> 16) * K_R;
            s->li[v] = K_LA + K_LB * ((float)(s->rnd & 0xFFFFu) * K_R);
        }
    }
    s->tick++;

    for (v = 0; v < GREASY_VOICES; v++) {
        float tri, q;
        s->d[v] += K_WALK * (s->dt[v] - s->d[v]);
        s->lp[v] += s->li[v];
        if (s->lp[v] >= 1.0f) s->lp[v] -= 1.0f;
        tri = fabsf(s->lp[v] - 0.5f);
        q = OFFSET[v] + dk * s->d[v];
        q = q + wk * tri;
        s->inc[v] = geiger_exp(q * K_LN2) * s->rate;
        s->dg[v] = ((1.0f - tk * tri) * s->fade - s->g[v]) * 0.0625f;
    }
}

/* One sample of the tracker: on a rising edge that completes three agreeing periods, a new rate target. */
static void track(GreasyState *s, float x, unsigned num)
{
    float y, t, a, h;
    if (x > K_IN) x = K_IN;
    if (x < -K_IN) x = -K_IN;
    y = x - s->dcx + K_DC_R * s->dcy;         /* DC block */
    s->dcx = x; s->dcy = y;
    s->lp1 += K_LPA * (y - s->lp1);           /* the tracking signal */
    s->lp2 += K_LPA * (s->lp1 - s->lp2);
    t = s->lp2;
    a = fabsf(t);
    if (a > s->env) s->env = a;
    else s->env = s->env * K_REL;

    if (s->cnt < GREASY_CNT_MAX) s->cnt++;
    h = s->env * K_HYST + K_HFLOOR;
    if (s->sq > 0.0f) {
        if (t < -h) s->sq = -1.0f;
    } else if (t > h) {                       /* a rising edge: one period measured */
        int per = s->cnt, dif = per - s->prev;
        s->sq = 1.0f;
        s->cnt = 0;
        if (dif < 0) dif = -dif;
        if (per >= GREASY_PMIN && per <= GREASY_PMAX && s->env > K_GATE && dif <= (s->prev >> 4)) {
            s->ok++;
            if (s->ok >= 2) {                 /* three periods agree: the note */
                s->ok = 2;
                s->rate_t = (float)(num / (unsigned)(per + s->prev)) * K_2M24;
            }
        } else {
            s->ok = 0;
        }
        s->prev = per;
    }
}

static void process(void *st, const FxParams *p, const float *in, float *out, size_t n)
{
    Inst *it = st;
    GreasyState *s = &it->s;
    const FxParamDesc *d = PARAMS;
    unsigned num = 1u << (23 + (int)fx_param_clamp(&d[GS_OCTAVE], p->value[GS_OCTAVE]));
    float glide = fx_param_clamp(&d[GS_GLIDE], p->value[GS_GLIDE]);
    float glk = geiger_exp(glide * (2.0f - glide) * K_GL);
    float dk = fx_param_clamp(&d[GS_DRIFT], p->value[GS_DRIFT]) * K_DRIFT;
    float warble = fx_param_clamp(&d[GS_WARBLE], p->value[GS_WARBLE]);
    float wk = warble * K_WARB, tk = warble * K_TREM;
    float fuzz = fx_param_clamp(&d[GS_FUZZ], p->value[GS_FUZZ]);
    float tone = fx_param_clamp(&d[GS_TONE], p->value[GS_TONE]);
    float dry = fx_param_clamp(&d[GS_DRY], p->value[GS_DRY]);
    float level = fx_param_clamp(&d[GS_LEVEL], p->value[GS_LEVEL]);
    float drive = fuzz * fuzz * K_DRV + K_Z;
    float tone_a = 1.0f - geiger_exp(100.0f * geiger_exp(tone * K_LN80) * K_NEG_W);
    size_t i;
    int v;

    level = level * (1.0f - K_COMP * fuzz);
    for (i = 0; i < n; i++) {
        float x = in[i], z = 0.0f;
        if (!isfinite(x)) x = 0.0f;
        if (it->ctl == 0) control(s, glk, dk, wk, tk);
        it->ctl = (it->ctl + 1) & 15;
        track(s, x, num);

        for (v = 0; v < GREASY_VOICES; v++) {
            s->ph[v] += s->inc[v];
            if (s->ph[v] >= 1.0f) s->ph[v] -= 1.0f;
            s->g[v] += s->dg[v];
            z += (s->ph[v] - 0.5f) * s->g[v];
        }
        z *= drive;
        if (z > 1.0f) z = 1.0f;
        if (z < -1.0f) z = -1.0f;
        z = 1.5f * z - 0.5f * z * z * z;
        s->z1 += tone_a * (z - s->z1);
        s->z2 += tone_a * (s->z1 - s->z2);
        out[i] = x * dry + s->z2 * level;
    }
}

const FxAlgorithm fx_greasy = {
    "greasy", "Greasy Strangler", sizeof(Inst), PARAMS, GS_NPARAMS, reset, process,
};
