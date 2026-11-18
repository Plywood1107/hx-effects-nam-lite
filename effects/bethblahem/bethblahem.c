#include "bethblahem.h"
#include "../geiger/geiger.h"                 /* geiger_exp */

#include <math.h>
#include <string.h>

static const FxParamDesc PARAMS[B_NPARAMS] = {
    { "octave",  "Octave",  FX_INTEGER,    0.0f, 4.0f, 2.0f,  "octaves down: 0 .. 4 (shown as 0 .. -4 Oct)", "immediate" },
    { "glide",   "Glide",   FX_CONTINUOUS, 0.0f, 1.0f, 0.4f,  "10 ms .. 2 s", "immediate" },
    { "vibrato", "Vibrato", FX_CONTINUOUS, 0.0f, 1.0f, 0.3f,  "depth, up to +-6 %", "immediate" },
    { "rate",    "Rate",    FX_CONTINUOUS, 0.0f, 1.0f, 0.4f,  "3 .. 8 Hz", "immediate" },
    { "growl",   "Growl",   FX_CONTINUOUS, 0.0f, 1.0f, 0.5f,  "", "immediate" },
    { "sub",     "Sub",     FX_CONTINUOUS, 0.0f, 1.0f, 0.3f,  "x (shown as %)", "immediate" },
    { "dry",     "Dry",     FX_CONTINUOUS, 0.0f, 1.0f, 0.7f,  "x (shown as %)", "immediate" },
    { "level",   "Level",   FX_CONTINUOUS, 0.0f, 1.0f, 0.7f,  "x (shown as %)", "immediate" },
};

/* every constant as the float it is (48 kHz); the kernel has the same values as immediates */
#define K_XMAX   16.0f
#define K_DC_R   0.9986910223960876f              /* 1 - 2 pi 10 / sr */
#define K_LPA    0.03850883990526199f             /* 1 - exp(-2 pi 300 / sr) */
#define K_REL    0.9995834231376648f              /* exp(-1 / (0.05 sr)) */
#define K_HYST   0.5f
#define K_HFLOOR 0.00001f
#define K_TRK    0.002f                           /* periods are taken above this envelope (-54 dB) */
#define K_2M28   3.725290298461914e-09f           /* 2^-28 */
#define K_GMAX   0.0020833334419876337f           /* Glide 0: 10 ms */
#define K_LNG    (-5.2983174324035645f)           /* ln(0.005): Glide 1, 2 s */
#define K_LNR    0.9808292388916016f              /* ln(8 / 3) */
#define K_LFO    0.001f                           /* 3 Hz, a 16-sample tick */
#define K_VIB    0.06f
#define K_AMP    0.0006944444612599909f           /* the fade-in, 30 ms */
#define K_DRV    7.0f
#define K_BIAS   0.4f
#define K_OUT    0.4f
#define K_HPR    0.9992145895957947f              /* 1 - 2 pi 6 / sr */
#define K_NTWOPI (-6.2831854820251465f)
#define K_S3     (-0.1666666716337204f)
#define K_S5     0.008333333767950535f
#define K_S7     (-0.00019841270113829523f)

float bethblahem_sin(float p)
{
    float t = p - 0.5f, x, x2, r;                /* sin(2 pi p) = -sin(2 pi t), folded into |t| <= 1/4 */
    if (t > 0.25f) t = 0.5f - t;
    if (t < -0.25f) t = -0.5f - t;
    x = t * K_NTWOPI;
    x2 = x * x;
    r = x2 * K_S7 + K_S5;
    r = r * x2 + K_S3;
    r = r * x2 + 1.0f;
    return r * x;
}

static float soft(float c)
{
    if (c > 1.0f) c = 1.0f;
    if (c < -1.0f) c = -1.0f;
    return c * (1.5f - c * c * 0.5f);
}

static void reset(void *st, float sr)
{
    (void)sr;
    memset(st, 0, sizeof(BethblahemState));
}

static void process(void *st, const FxParams *p, const float *in, float *out, size_t n)
{
    BethblahemState *s = st;
    const FxParamDesc *d = PARAMS;
    int oct = (int)fx_param_clamp(&d[B_OCTAVE], p->value[B_OCTAVE]), j;
    float glk = K_GMAX * geiger_exp(fx_param_clamp(&d[B_GLIDE], p->value[B_GLIDE]) * K_LNG);
    float vdep = fx_param_clamp(&d[B_VIBRATO], p->value[B_VIBRATO]) * K_VIB;
    float linc = geiger_exp(fx_param_clamp(&d[B_RATE], p->value[B_RATE]) * K_LNR) * K_LFO;
    float grw = fx_param_clamp(&d[B_GROWL], p->value[B_GROWL]);
    float drv = 1.0f + grw * K_DRV, bias = grw * K_BIAS;
    float sub = fx_param_clamp(&d[B_SUB], p->value[B_SUB]);
    float dry = fx_param_clamp(&d[B_DRY], p->value[B_DRY]);
    float lvl = fx_param_clamp(&d[B_LEVEL], p->value[B_LEVEL]);
    float osc = 1.0f;
    size_t i;

    for (j = 0; j < oct; j++) osc *= 0.5f;

    for (i = 0; i < n; i++) {
        float x = in[i], y, t, h, v, w, z;
        if (!isfinite(x)) x = 0.0f;
        if (x > K_XMAX) x = K_XMAX;
        if (x < -K_XMAX) x = -K_XMAX;

        if (s->tick == 0) {                           /* the vibrato, every 16 samples */
            s->lfo += linc;
            if (s->lfo >= 1.0f) s->lfo -= 1.0f;
            s->vmul = 1.0f + vdep * bethblahem_sin(s->lfo);
        }
        s->tick = (s->tick + 1) & 15;

        y = x - s->dcx + K_DC_R * s->dcy;             /* the tracker, as Corrupt's */
        s->dcx = x; s->dcy = y;
        s->lp1 += K_LPA * (y - s->lp1);
        s->lp2 += K_LPA * (s->lp1 - s->lp2);
        t = s->lp2;
        if (fabsf(t) > s->env) s->env = fabsf(t);
        else s->env = s->env * K_REL;
        if (s->cnt < BETHBLAHEM_CNT_MAX) s->cnt++;
        h = s->env * K_HYST + K_HFLOOR;
        if (s->sq > 0.0f) {
            if (t < -h) s->sq = -1.0f;
        } else if (t > h) {                           /* a rising edge: one period measured */
            int per = s->cnt, pl = s->pl;
            s->sq = 1.0f;
            s->cnt = 0;
            s->pl = per;
            if (s->env > K_TRK && per >= BETHBLAHEM_PMIN && per <= BETHBLAHEM_PMAX) {
                int dd = per - pl;
                if (dd < 0) dd = -dd;
                if (dd * 16 <= pl) {                  /* two periods agree: a note */
                    unsigned q = (1u << 28) / (unsigned)per;
                    s->inct = (float)q * K_2M28;
                    s->have = 1.0f;
                }
            }
        }

        s->inc = s->inc + glk * (s->inct * osc - s->inc);     /* the hand moves */
        s->ph = s->ph + s->inc * s->vmul;
        if (s->ph >= 1.0f) {
            s->ph = s->ph - 1.0f;
            s->subf = 1.0f - s->subf;
        }
        s->amp = s->amp + K_AMP * (s->have - s->amp);

        v = bethblahem_sin(s->ph);
        v = v + sub * bethblahem_sin((s->ph + s->subf) * 0.5f);
        w = soft(v * drv + bias);
        w = v + grw * (w - v);
        z = w * lvl;
        z = z * s->amp;
        z = soft(z) * K_OUT;
        y = z - s->ox + K_HPR * s->oy;                /* no DC, nothing under 6 Hz to speak of */
        s->ox = z; s->oy = y;
        out[i] = y + dry * x;
    }
}

const FxAlgorithm fx_bethblahem = {
    "bethblahem", "Bethblahem", sizeof(BethblahemState), PARAMS, B_NPARAMS, reset, process,
};
