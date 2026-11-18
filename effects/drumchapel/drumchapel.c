#include "drumchapel.h"
#include "../metronome/metronome.h"            /* click_bpm100: Click's tempo, to the bit */

#include <math.h>
#include <string.h>

#define PI 3.14159265358979323846
#define RATE 48000.0

static const FxParamDesc PARAMS[DC_NPARAMS] = {
    { "time",    "Time",    FX_CONTINUOUS, 0.1f, 4.0f,  0.5f, "s (one beat)", "immediate (BPM rounded to 0.01)" },
    { "pattern", "Pattern", FX_INTEGER,    0.0f, 19.0f, 0.0f, "", "next hit" },
    { "kit",     "Kit",     FX_INTEGER,    0.0f, 5.0f,  0.0f, "", "immediate" },
    { "kick",    "Kick",    FX_CONTINUOUS, 0.0f, 1.0f,  0.8f, "x (shown as %)", "next hit" },
    { "snare",   "Snare",   FX_CONTINUOUS, 0.0f, 1.0f,  0.7f, "x (shown as %)", "next hit" },
    { "hat",     "Hat",     FX_CONTINUOUS, 0.0f, 1.0f,  0.5f, "x (shown as %)", "next hit" },
    { "swing",   "Swing",   FX_CONTINUOUS, 0.0f, 1.0f,  0.0f, "x 1/3 sixteenth on odd sixteenths", "immediate" },
    { "level",   "Level",   FX_CONTINUOUS, 0.0f, 1.0f,  0.5f, "x (shown as %)", "immediate" },
};

/* ------------------------------------------------------------------ patterns: one character a sixteenth */
static const struct { const char *name, *kick, *snare, *hat; } PATTERN[DRUMCHAPEL_PATTERNS] = {
    { "Rock",       "x.......x.x.....", "....x.......x...", "x.x.x.x.x.x.x.x." },
    { "Half-Time",  "x.........x.....", "........x.......", "x.x.x.x.x.x.x.x." },
    { "Four Floor", "x...x...x...x...", "....x.......x...", "x.x.x.x.x.x.x.x." },
    { "Disco",      "x...x...x...x...", "....x.......x...", "..x...x...x...x." },
    { "Shuffle",    "x.....x.x.......", "....x.......x...", "x..xx..xx..xx..x" },
    { "Motorik",    "x.x...x.x.x...x.", "....x.......x...", "xxxxxxxxxxxxxxxx" },
    { "Break",      "x.x.......xx....", "....x..x.x..x..x", "x.x.x.x.x.x.x.x." },
    { "Funk",       "x......x..x.....", "....x..x.x..x...", "xxxxxxxxxxxxxxxx" },
    { "Boom Bap",   "x......x.xx.....", "....x.......x...", "x.x.x.x.x.x.x.x." },
    { "Bossa",      "x..xx..xx..xx..x", "x..x..x...x..x..", "x.x.x.x.x.x.x.x." },
    { "One Drop",   "........x.......", "........x.......", "..x...x...x...x." },
    { "Punk",       "x...x...x...x...", "..x...x...x...x.", "x.x.x.x.x.x.x.x." },
    { "Blast",      "x.x.x.x.x.x.x.x.", ".x.x.x.x.x.x.x.x", "x.x.x.x.x.x.x.x." },
    { "Sludge",     "x.....x.........", "........x.......", "x...x...x...x..." },
    { "Trap",       "x......x..x.....", "........x.......", "xxxxxxxxxxxxxxxx" },
    { "Two-Step",   "x.........x.....", "....x.......x...", "x.x.x.x.x.x.x.x." },
    { "Gallop",     "x.xxx.xxx.xxx.xx", "....x.......x...", "x...x...x...x..." },
    { "Hats Only",  "................", "................", "x.x.x.x.x.x.x.x." },
    { "Kick Only",  "x...x...x...x...", "................", "................" },
    { "Fill",       "x.......x.......", "....x...x.x.xxxx", "x.x.x.x........." },
};

/* ------------------------------------------------------------------ kits, in physical units */
typedef struct {
    double f0, f1;            /* tone start and end pitch, Hz */
    double tp, tt, tn;        /* pitch, tone and noise time constants, s */
    double tlev, nlev;        /* tone and noise levels at the hit */
    double fc;                /* noise filter corner, Hz: > 0 lowpass, < 0 highpass, 0 none */
} VoiceDef;

typedef struct {
    const char *name;
    double drive, comp, tdrive, m2;
    unsigned hold;            /* noise sample-and-hold, samples */
    double gate;              /* s; 0 = none */
    VoiceDef v[DRUMCHAPEL_VOICES];
} KitDef;

static const KitDef KIT[DRUMCHAPEL_KITS] = {
    { "Boom", 0.5, 4.0 / 3.0, 1.0, 0.4, 1, 0.0, {          /* 808-ish */
        { 120.0, 48.0, 0.040, 0.350, 0.002, 1.00, 0.10, 3000.0 },     /* long low sine, slow fall */
        { 330.0, 238.0, 0.010, 0.050, 0.070, 0.50, 0.65, -1200.0 },   /* two modes, snappy noise */
        { 0.0, 0.0, 0.010, 0.050, 0.040, 0.55, 0.15, -7000.0 } } },   /* six squares, highpassed */
    { "Punch", 0.55, 1.0 / (1.5 * 0.55), 1.0, 0.35, 1, 0.0, {   /* 909-ish */
        { 400.0, 55.0, 0.008, 0.180, 0.004, 1.00, 0.40, -2000.0 },    /* fast sweep, a click */
        { 300.0, 200.0, 0.010, 0.060, 0.120, 0.45, 0.70, -2500.0 },   /* brighter */
        { 0.0, 0.0, 0.010, 0.010, 0.035, 0.00, 0.60, -9000.0 } } },   /* bright noise */
    { "Tick", 0.5, 4.0 / 3.0, 1.0, 0.0, 1, 0.0, {          /* CR-78-ish */
        { 90.0, 60.0, 0.020, 0.080, 0.001, 0.70, 0.05, 2000.0 },      /* soft, short */
        { 400.0, 380.0, 0.010, 0.020, 0.040, 0.25, 0.35, -3000.0 },   /* small */
        { 0.0, 0.0, 0.010, 0.010, 0.012, 0.10, 0.50, -10000.0 } } }, /* ticky */
    { "Bit", 0.5, 4.0 / 3.0, 40.0, 0.0, 6, 0.0, {          /* 8-bit: squares, noise held at 8 kHz */
        { 200.0, 55.0, 0.030, 0.150, 0.001, 0.60, 0.00, 0.0 },
        { 300.0, 220.0, 0.020, 0.060, 0.080, 0.35, 0.40, 0.0 },
        { 0.0, 0.0, 0.010, 0.010, 0.030, 0.00, 0.45, 0.0 } } },
    { "Doom", 40.0, 0.3, 1.0, 0.3, 1, 0.0, {               /* very low, very fuzzed */
        { 110.0, 30.0, 0.060, 0.600, 0.003, 1.00, 0.20, 800.0 },      /* down to 30 Hz, long */
        { 140.0, 90.0, 0.020, 0.150, 0.250, 0.60, 0.60, 1500.0 },     /* 90 Hz body, thick tail */
        { 0.0, 0.0, 0.010, 0.010, 0.060, 0.00, 0.50, 1200.0 } } },    /* dark */
    { "Eighty", 0.5, 4.0 / 3.0, 1.0, 0.5, 1, 0.150, {      /* LinnDrum-ish, gated snare */
        { 100.0, 52.0, 0.015, 0.200, 0.003, 0.90, 0.50, -3000.0 },    /* body + beater click */
        { 220.0, 180.0, 0.010, 0.080, 0.500, 0.40, 0.55, -1500.0 },   /* 180 / 331 Hz, tail cut at 150 ms */
        { 0.0, 0.0, 0.010, 0.020, 0.020, 0.15, 0.50, -8000.0 } } },   /* crisp, short */
};

/* 808 metal: 205.3, 304.4, 369.6, 522.7, 540, 800 Hz */
static const double METAL_HZ[DRUMCHAPEL_METAL] = { 205.3, 304.4, 369.6, 522.7, 540.0, 800.0 };

const float drumchapel_r2 = 1.84f;              /* the snare's second mode, x its rate */
const float drumchapel_third = (float)(1.0 / 3.0);
const float drumchapel_silent = 3.0e-5f;        /* -90 dB: a voice stops */
const float drumchapel_gate_k = 0.993079603f;    /* exp(-1 / (3 ms x 48 kHz)): the gate's release a sample */

/* ------------------------------------------------------------------ the tables, built once */
static uint32_t KW[DRUMCHAPEL_KITS][DK_WORDS], KS[DRUMCHAPEL_PATTERNS], HAT_W[DRUMCHAPEL_PATTERNS], MI[DRUMCHAPEL_METAL];
static int built;

static uint32_t fbits(double v)
{
    float f = (float)v;
    uint32_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}

static uint32_t steps(const char *s)
{
    uint32_t m = 0;
    int k;
    for (k = 0; k < DRUMCHAPEL_STEPS; k++)
        if (s[k] == 'x') m |= 1u << k;
    return m;
}

static double decay(double tau) { return exp(-1.0 / (tau * RATE)); }

static void build(void)
{
    int k, v;
    if (built) return;
    for (k = 0; k < DRUMCHAPEL_PATTERNS; k++) {
        KS[k] = steps(PATTERN[k].kick) | steps(PATTERN[k].snare) << 16;
        HAT_W[k] = steps(PATTERN[k].hat);
    }
    for (k = 0; k < DRUMCHAPEL_METAL; k++)
        MI[k] = (uint32_t)(METAL_HZ[k] / RATE * 4294967296.0 + 0.5);
    for (k = 0; k < DRUMCHAPEL_KITS; k++) {
        const KitDef *d = &KIT[k];
        uint32_t *w = KW[k];
        w[DK_DRIVE] = fbits(d->drive);
        w[DK_COMP] = fbits(d->comp);
        w[DK_TDRIVE] = fbits(d->tdrive);
        w[DK_M2] = fbits(d->m2);
        w[DK_HOLD] = d->hold;
        w[DK_GATE] = d->gate > 0.0 ? (uint32_t)(d->gate * RATE + 0.5) : DRUMCHAPEL_NO_GATE;
        for (v = 0; v < DRUMCHAPEL_VOICES; v++) {
            const VoiceDef *e = &d->v[v];
            uint32_t *p = w + DK_V0 + v * DV_WORDS;
            double a = e->fc == 0.0 ? 1.0 : 1.0 - exp(-2.0 * PI * fabs(e->fc) / RATE);
            p[DV_INC] = fbits(e->f1 / RATE);
            p[DV_SWEEP] = fbits((e->f0 - e->f1) / RATE);
            p[DV_PD] = fbits(decay(e->tp));
            p[DV_TD] = fbits(decay(e->tt));
            p[DV_ND] = fbits(decay(e->tn));
            p[DV_TLEV] = fbits(e->tlev);
            p[DV_NLEV] = fbits(e->nlev);
            p[DV_NF] = fbits(e->fc < 0.0 ? -a : a);
        }
    }
    built = 1;
}

static int clampi(int v, int n) { return v < 0 ? 0 : v >= n ? n - 1 : v; }

const uint32_t *drumchapel_kit_words(int kit) { build(); return KW[clampi(kit, DRUMCHAPEL_KITS)]; }
uint32_t drumchapel_pattern_ks(int p) { build(); return KS[clampi(p, DRUMCHAPEL_PATTERNS)]; }
uint32_t drumchapel_pattern_hat(int p) { build(); return HAT_W[clampi(p, DRUMCHAPEL_PATTERNS)]; }
const uint32_t *drumchapel_metal(void) { build(); return MI; }
const char *drumchapel_pattern_name(int p) { return PATTERN[clampi(p, DRUMCHAPEL_PATTERNS)].name; }
const char *drumchapel_kit_name(int kit) { return KIT[clampi(kit, DRUMCHAPEL_KITS)].name; }

static float wf(const uint32_t *w, int i)
{
    float f;
    memcpy(&f, &w[i], sizeof f);
    return f;
}

/* ------------------------------------------------------------------ the algorithm */
static void reset(void *st, float sr)
{
    DrumChapelState *s = st;
    (void)sr;
    build();
    memset(s, 0, sizeof *s);
    s->rnd = DRUMCHAPEL_SEED;
    s->pend = 1;                                   /* step 0 on the first sample */
}

static float sine_p(float ph)                     /* a parabola through sin(2 pi (ph - 1/2)), peak 1 */
{
    float x = ph - 0.5f, a = fabsf(x) * 16.0f;
    a = 8.0f - a;
    return x * a;
}

static float metal(uint32_t age)
{
    int k, c = 0;
    for (k = 0; k < DRUMCHAPEL_METAL; k++)
        c += (int)((age * MI[k]) >> 31);
    return (float)c * drumchapel_third - 1.0f;
}

static void hit(DrumChapelState *s, int pattern, const uint32_t *kw, const float lev[DRUMCHAPEL_VOICES])
{
    uint32_t ks = KS[pattern], m[DRUMCHAPEL_VOICES];
    int v;
    m[KICK] = ks; m[SNARE] = ks >> 16; m[HAT] = HAT_W[pattern];
    for (v = 0; v < DRUMCHAPEL_VOICES; v++) {
        const uint32_t *p = kw + DK_V0 + v * DV_WORDS;
        DrumVoice *V = &s->v[v];
        if (!(m[v] >> s->step & 1u)) continue;
        V->te = wf(p, DV_TLEV) * lev[v];
        V->ne = wf(p, DV_NLEV) * lev[v];
        V->ph = V->ph2 = V->lp = 0.0f;
        V->pe = 1.0f;
        V->age = 0;
        s->hits[v]++;
    }
}

static float voice(DrumVoice *V, int v, const uint32_t *kw, float n, float y)
{
    const uint32_t *p = kw + DK_V0 + v * DV_WORDS;
    float u, src, t, f, a;
    if (V->te < drumchapel_silent && V->ne < drumchapel_silent)
        return y;
    u = n * V->ne;
    if (v != HAT || V->te != 0.0f) {                /* a hat without metal skips it */
        if (v == HAT) {
            src = metal(V->age);
        } else {
            float inc;
            V->pe = V->pe * wf(p, DV_PD);
            f = wf(p, DV_SWEEP) * V->pe;
            inc = wf(p, DV_INC) + f;
            V->ph = V->ph + inc;
            if (V->ph >= 1.0f) V->ph = V->ph - 1.0f;
            src = sine_p(V->ph);
            if (v == SNARE) {
                f = inc * drumchapel_r2;
                V->ph2 = V->ph2 + f;
                if (V->ph2 >= 1.0f) V->ph2 = V->ph2 - 1.0f;
                f = wf(kw, DK_M2) * sine_p(V->ph2);
                src = src + f;
            }
        }
        src = src * wf(kw, DK_TDRIVE);
        if (src > 1.0f) src = 1.0f;
        if (src < -1.0f) src = -1.0f;
        t = src * V->te;
        if (v == HAT) u = u + t;                    /* the metal goes through the filter */
        else y = y + t;
    }
    a = wf(p, DV_NF);
    f = fabsf(a) * (u - V->lp);
    V->lp = V->lp + f;
    y = y + (a < 0.0f ? u - V->lp : V->lp);
    V->te = V->te * wf(p, DV_TD);
    V->age++;
    V->ne = V->ne * (V->age > kw[DK_GATE] ? drumchapel_gate_k : wf(p, DV_ND));
    return y;
}

static void process(void *st, const FxParams *pr, const float *in, float *out, size_t n)
{
    DrumChapelState *s = st;
    const FxParamDesc *d = PARAMS;
    uint32_t inc = click_bpm100(fx_param_clamp(&d[DC_TIME], pr->value[DC_TIME])) * 4u;
    int pattern = (int)fx_param_clamp(&d[DC_PATTERN], pr->value[DC_PATTERN]);
    const uint32_t *kw = KW[(int)fx_param_clamp(&d[DC_KIT], pr->value[DC_KIT])];
    float lev[DRUMCHAPEL_VOICES], level;
    uint32_t thr = (uint32_t)(fx_param_clamp(&d[DC_SWING], pr->value[DC_SWING]) * DRUMCHAPEL_SWING_MAX);
    size_t i;
    int v;

    lev[KICK] = fx_param_clamp(&d[DC_KICK], pr->value[DC_KICK]);
    lev[SNARE] = fx_param_clamp(&d[DC_SNARE], pr->value[DC_SNARE]);
    lev[HAT] = fx_param_clamp(&d[DC_HAT], pr->value[DC_HAT]);
    level = fx_param_clamp(&d[DC_LEVEL], pr->value[DC_LEVEL]);

    for (i = 0; i < n; i++) {
        float x = in[i], y = 0.0f, z, w;
        if (!isfinite(x)) x = 0.0f;
        /* the step: due at the wrap, odd steps also wait for the swing threshold */
        if (s->pend && s->acc >= ((s->step & 1u) ? thr : 0u)) {
            s->pend = 0;
            hit(s, pattern, kw, lev);
            s->fires++;
            s->last_step = s->step;
        }
        s->acc += inc;
        if (s->acc >= DRUMCHAPEL_PERIOD) {
            s->acc -= DRUMCHAPEL_PERIOD;
            s->step = (s->step + 1) & 15u;
            s->pend = 1;
        }
        /* the noise, held for HOLD samples */
        if (s->hcnt == 0) {
            s->rnd ^= s->rnd << 13;
            s->rnd ^= s->rnd >> 17;
            s->rnd ^= s->rnd << 5;
        }
        s->hcnt++;
        if (s->hcnt >= kw[DK_HOLD]) s->hcnt = 0;
        z = (float)(s->rnd >> 8) * 1.1920928955078125e-7f - 1.0f;
        for (v = 0; v < DRUMCHAPEL_VOICES; v++)
            y = voice(&s->v[v], v, kw, z, y);
        /* the kit's drive and clip, its level, Level */
        y = y * wf(kw, DK_DRIVE);
        if (y > 1.0f) y = 1.0f;
        if (y < -1.0f) y = -1.0f;
        w = 1.5f * y - 0.5f * y * y * y;
        w = w * wf(kw, DK_COMP);
        w = w * level;
        out[i] = x + w;
        s->sample++;
    }
}

const FxAlgorithm fx_drumchapel = {
    "drumchapel", "Drum Chapel", sizeof(DrumChapelState), PARAMS, DC_NPARAMS, reset, process,
};
