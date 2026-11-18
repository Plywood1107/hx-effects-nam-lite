#include "drumchapel.h"
#include "../metronome/metronome.h"            /* click_bpm100: Click's tempo, to the bit */

#include <math.h>
#include <string.h>

/* the converted grooves (grooves.py): optional and never committed */
#if defined(__has_include)
#if __has_include("grooves_data.h")
#include "grooves_data.h"
#endif
#endif
#ifndef DC_GROOVE_FAMILIES
#define DC_GROOVE_FAMILIES 0
#define DC_GROOVE_TOTAL 0
#endif

#define PI 3.14159265358979323846
#define RATE 48000.0

static const FxParamDesc PARAMS[DC_NPARAMS] = {
    { "time",    "Time",    FX_CONTINUOUS, 0.1f, 4.0f,  0.5f, "s (one beat)", "immediate (BPM rounded to 0.01)" },
    { "pattern", "Pattern", FX_INTEGER,    0.0f, 19.0f, 0.0f, "", "next step" },
    { "kit",     "Kit",     FX_INTEGER,    0.0f, 5.0f,  0.0f, "", "immediate" },
    { "kick",    "Kick",    FX_CONTINUOUS, 0.0f, 1.0f,  0.8f, "x (shown as %)", "next hit" },
    { "snare",   "Snare",   FX_CONTINUOUS, 0.0f, 1.0f,  0.7f, "x (shown as %)", "next hit" },
    { "hat",     "Hat",     FX_CONTINUOUS, 0.0f, 1.0f,  0.5f, "x (shown as %)", "next hit" },
    { "swing",   "Swing",   FX_CONTINUOUS, 0.0f, 1.0f,  0.0f, "x 1/3 sixteenth on odd sixteenths", "immediate" },
    { "level",   "Level",   FX_CONTINUOUS, 0.0f, 1.0f,  0.5f, "x (shown as %)", "immediate" },
    { "groove",  "Groove",  FX_INTEGER,    0.0f, 11.0f, 0.0f, "", "next step" },
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
    VoiceDef v[DRUMCHAPEL_DEFS];   /* kick, snare, closed hat, tom (its high pitch), open hat */
} KitDef;

static const KitDef KIT[DRUMCHAPEL_KITS] = {
    { "Boom", 0.5, 4.0 / 3.0, 1.0, 0.4, 1, 0.0, {          /* 808-ish */
        { 120.0, 48.0, 0.040, 0.350, 0.002, 1.00, 0.10, 3000.0 },     /* long low sine, slow fall */
        { 330.0, 238.0, 0.010, 0.050, 0.070, 0.50, 0.65, -1200.0 },   /* two modes, snappy noise */
        { 0.0, 0.0, 0.010, 0.050, 0.040, 0.55, 0.15, -7000.0 },       /* six squares, highpassed */
        { 200.0, 150.0, 0.030, 0.300, 0.004, 0.90, 0.05, 3000.0 },    /* a long sine tom */
        { 0.0, 0.0, 0.010, 0.300, 0.300, 0.55, 0.20, -6000.0 } } },   /* the squares left ringing */
    { "Punch", 0.55, 1.0 / (1.5 * 0.55), 1.0, 0.35, 1, 0.0, {   /* 909-ish */
        { 400.0, 55.0, 0.008, 0.180, 0.004, 1.00, 0.40, -2000.0 },    /* fast sweep, a click */
        { 300.0, 200.0, 0.010, 0.060, 0.120, 0.45, 0.70, -2500.0 },   /* brighter */
        { 0.0, 0.0, 0.010, 0.010, 0.035, 0.00, 0.60, -9000.0 },       /* bright noise */
        { 260.0, 170.0, 0.020, 0.200, 0.010, 0.85, 0.20, -1500.0 },   /* a swept tom with a tick */
        { 0.0, 0.0, 0.010, 0.010, 0.300, 0.00, 0.55, -8000.0 } } },   /* a long noise wash */
    { "Tick", 0.5, 4.0 / 3.0, 1.0, 0.0, 1, 0.0, {          /* CR-78-ish */
        { 90.0, 60.0, 0.020, 0.080, 0.001, 0.70, 0.05, 2000.0 },      /* soft, short */
        { 400.0, 380.0, 0.010, 0.020, 0.040, 0.25, 0.35, -3000.0 },   /* small */
        { 0.0, 0.0, 0.010, 0.010, 0.012, 0.10, 0.50, -10000.0 },      /* ticky */
        { 320.0, 300.0, 0.010, 0.120, 0.002, 0.60, 0.05, 2000.0 },    /* a bongo-like tom */
        { 0.0, 0.0, 0.010, 0.010, 0.150, 0.10, 0.45, -9000.0 } } },   /* a short cymbal */
    { "Bit", 0.5, 4.0 / 3.0, 40.0, 0.0, 6, 0.0, {          /* 8-bit: squares, noise held at 8 kHz */
        { 200.0, 55.0, 0.030, 0.150, 0.001, 0.60, 0.00, 0.0 },
        { 300.0, 220.0, 0.020, 0.060, 0.080, 0.35, 0.40, 0.0 },
        { 0.0, 0.0, 0.010, 0.010, 0.030, 0.00, 0.45, 0.0 },
        { 330.0, 110.0, 0.050, 0.150, 0.001, 0.50, 0.00, 0.0 },       /* a falling square */
        { 0.0, 0.0, 0.010, 0.010, 0.200, 0.00, 0.40, 0.0 } } },
    { "Doom", 40.0, 0.3, 1.0, 0.3, 1, 0.0, {               /* very low, very fuzzed */
        { 110.0, 30.0, 0.060, 0.600, 0.003, 1.00, 0.20, 800.0 },      /* down to 30 Hz, long */
        { 140.0, 90.0, 0.020, 0.150, 0.250, 0.60, 0.60, 1500.0 },     /* 90 Hz body, thick tail */
        { 0.0, 0.0, 0.010, 0.010, 0.060, 0.00, 0.50, 1200.0 },        /* dark */
        { 130.0, 55.0, 0.080, 0.500, 0.150, 1.00, 0.25, 900.0 },      /* toms tuned way down (floor ~28 Hz) */
        { 0.0, 0.0, 0.010, 0.010, 0.450, 0.00, 0.50, 1500.0 } } },    /* a dark roar */
    { "Eighty", 0.5, 4.0 / 3.0, 1.0, 0.5, 1, 0.150, {      /* LinnDrum-ish, gated snare (and toms, cymbals) */
        { 100.0, 52.0, 0.015, 0.200, 0.003, 0.90, 0.50, -3000.0 },    /* body + beater click */
        { 220.0, 180.0, 0.010, 0.080, 0.500, 0.40, 0.55, -1500.0 },   /* 180 / 331 Hz, tail cut at 150 ms */
        { 0.0, 0.0, 0.010, 0.020, 0.020, 0.15, 0.50, -8000.0 },       /* crisp, short */
        { 500.0, 140.0, 0.060, 0.250, 0.010, 0.90, 0.30, -2000.0 },   /* a synth-drum sweep */
        { 0.0, 0.0, 0.010, 0.060, 0.350, 0.20, 0.50, -7000.0 } } },
};

/* 808 metal: 205.3, 304.4, 369.6, 522.7, 540, 800 Hz */
static const double METAL_HZ[DRUMCHAPEL_METAL] = { 205.3, 304.4, 369.6, 522.7, 540.0, 800.0 };
/* the tom's pitches: high, mid, low, floor (x the kit's tom rate) */
static const double TUNE_X[4] = { 1.0, 0.8, 0.64, 0.5 };

const float drumchapel_r2 = 1.84f;              /* the snare's second mode, x its rate */
const float drumchapel_third = (float)(1.0 / 3.0);
const float drumchapel_silent = 3.0e-5f;        /* -90 dB: a voice stops */
const float drumchapel_gate_k = 0.993079603f;    /* exp(-1 / (3 ms x 48 kHz)): the gate's release a sample */

/* ------------------------------------------------------------------ the tables, built once */
#define CLASSIC_STEPS (DRUMCHAPEL_PATTERNS * DRUMCHAPEL_STEPS)
#define BANK_WORDS (DRUMCHAPEL_DIR_WORDS + (CLASSIC_STEPS + DC_GROOVE_TOTAL + 3) / 4)

static uint32_t KW[DRUMCHAPEL_KITS][DK_WORDS], MI[DRUMCHAPEL_METAL], TUNE[4], BANK[BANK_WORDS];
static float TUNE_F[4];
static int built;

static uint32_t fbits(double v)
{
    float f = (float)v;
    uint32_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}

static double decay(double tau) { return exp(-1.0 / (tau * RATE)); }

static void put_step(uint32_t i, uint32_t b)
{
    BANK[DRUMCHAPEL_DIR_WORDS + i / 4] |= (b & 0xFFu) << (8 * (i % 4));
}

static void build(void)
{
    int k, v, g, p;
    uint32_t at;
    if (built) return;
    /* the bank: Classic's 20 bars, then every converted groove; the directory */
    memset(BANK, 0, sizeof BANK);
    for (p = 0; p < DRUMCHAPEL_PATTERNS; p++)
        for (k = 0; k < DRUMCHAPEL_STEPS; k++)
            put_step((uint32_t)(p * DRUMCHAPEL_STEPS + k), (PATTERN[p].kick[k] == 'x' ? DC_B_KICK : 0u) |
                     (PATTERN[p].snare[k] == 'x' ? DC_B_SNARE : 0u) | (PATTERN[p].hat[k] == 'x' ? DC_B_HAT : 0u));
    for (g = 0; g < DRUMCHAPEL_GROOVES; g++)
        for (p = 0; p < DRUMCHAPEL_PATTERNS; p++)
            BANK[g * DRUMCHAPEL_PATTERNS + p] = (uint32_t)(p * DRUMCHAPEL_STEPS) << 9 | DRUMCHAPEL_STEPS;
#if DC_GROOVE_FAMILIES
    {
        int f, n = 0;
        uint32_t i;
        uint32_t first[DC_GROOVE_VARIATIONS];
        at = CLASSIC_STEPS;
        for (k = 0; k < DC_GROOVE_VARIATIONS; k++) {
            first[k] = at;
            for (i = 0; i < DC_GROOVE_LEN[k]; i++)
                put_step(at + i, DC_GROOVE_STEPS[at - CLASSIC_STEPS + i]);
            at += DC_GROOVE_LEN[k];
        }
        for (f = 0; f < DC_GROOVE_FAMILIES && f + 1 < DRUMCHAPEL_GROOVES; f++) {
            if (DC_FAMILY_N[f])
                for (p = 0; p < DRUMCHAPEL_PATTERNS; p++) {
                    int var = n + p % DC_FAMILY_N[f];
                    BANK[(f + 1) * DRUMCHAPEL_PATTERNS + p] = first[var] << 9 | DC_GROOVE_LEN[var];
                }
            n += DC_FAMILY_N[f];
        }
    }
#endif
    (void)at;
    for (k = 0; k < DRUMCHAPEL_METAL; k++)
        MI[k] = (uint32_t)(METAL_HZ[k] / RATE * 4294967296.0 + 0.5);
    for (k = 0; k < 4; k++) {
        TUNE[k] = fbits(TUNE_X[k]);
        TUNE_F[k] = (float)TUNE_X[k];
    }
    for (k = 0; k < DRUMCHAPEL_KITS; k++) {
        const KitDef *d = &KIT[k];
        uint32_t *w = KW[k];
        w[DK_DRIVE] = fbits(d->drive);
        w[DK_COMP] = fbits(d->comp);
        w[DK_TDRIVE] = fbits(d->tdrive);
        w[DK_M2] = fbits(d->m2);
        w[DK_HOLD] = d->hold;
        w[DK_GATE] = d->gate > 0.0 ? (uint32_t)(d->gate * RATE + 0.5) : DRUMCHAPEL_NO_GATE;
        for (v = 0; v < DRUMCHAPEL_DEFS; v++) {
            const VoiceDef *e = &d->v[v];
            uint32_t *q = w + DK_V0 + v * DV_WORDS;
            double a = e->fc == 0.0 ? 1.0 : 1.0 - exp(-2.0 * PI * fabs(e->fc) / RATE);
            q[DV_INC] = fbits(e->f1 / RATE);
            q[DV_SWEEP] = fbits((e->f0 - e->f1) / RATE);
            q[DV_PD] = fbits(decay(e->tp));
            q[DV_TD] = fbits(decay(e->tt));
            q[DV_ND] = fbits(decay(e->tn));
            q[DV_TLEV] = fbits(e->tlev);
            q[DV_NLEV] = fbits(e->nlev);
            q[DV_NF] = fbits(e->fc < 0.0 ? -a : a);
        }
    }
    built = 1;
}

static int clampi(int v, int n) { return v < 0 ? 0 : v >= n ? n - 1 : v; }

const uint32_t *drumchapel_kit_words(int kit) { build(); return KW[clampi(kit, DRUMCHAPEL_KITS)]; }
const uint32_t *drumchapel_bank(uint32_t *nwords) { build(); if (nwords) *nwords = BANK_WORDS; return BANK; }
int drumchapel_families(void)
{
    int f, n = 0;
#if DC_GROOVE_FAMILIES
    for (f = 0; f < DC_GROOVE_FAMILIES; f++) n += DC_FAMILY_N[f] != 0;
#else
    (void)f;
#endif
    return n;
}
int drumchapel_family_size(int groove)
{
    groove = clampi(groove, DRUMCHAPEL_GROOVES);
#if DC_GROOVE_FAMILIES
    if (groove > 0 && groove <= DC_GROOVE_FAMILIES) return DC_FAMILY_N[groove - 1];
#endif
    return groove == 0 ? DRUMCHAPEL_PATTERNS : 0;
}
uint32_t drumchapel_groove_len(int groove, int pattern)
{
    build();
    return BANK[clampi(groove, DRUMCHAPEL_GROOVES) * DRUMCHAPEL_PATTERNS + clampi(pattern, DRUMCHAPEL_PATTERNS)] & 511u;
}
static uint32_t step_byte(uint32_t dir, uint32_t k)
{
    uint32_t i = (dir >> 9) + k;
    return BANK[DRUMCHAPEL_DIR_WORDS + i / 4] >> (8 * (i % 4)) & 0xFFu;
}
uint32_t drumchapel_groove_step(int groove, int pattern, uint32_t k)
{
    uint32_t d;
    build();
    d = BANK[clampi(groove, DRUMCHAPEL_GROOVES) * DRUMCHAPEL_PATTERNS + clampi(pattern, DRUMCHAPEL_PATTERNS)];
    return step_byte(d, k % (d & 511u));
}
const uint32_t *drumchapel_metal(void) { build(); return MI; }
const uint32_t *drumchapel_tune(void) { build(); return TUNE; }
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
    s->len = DRUMCHAPEL_STEPS;
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

static void hit(DrumChapelState *s, uint32_t b, const uint32_t *kw, const float lev[DRUMCHAPEL_VOICES])
{
    int v;
    for (v = 0; v < DRUMCHAPEL_VOICES; v++) {
        DrumVoice *V = &s->v[v];
        uint32_t def = (uint32_t)v;
        const uint32_t *p;
        if (!(b >> v & 1u)) continue;
        if (v == HAT && (b & DC_B_OPEN)) { def = DEF_OPEN; s->opens++; }
        p = kw + DK_V0 + def * DV_WORDS;
        V->te = wf(p, DV_TLEV) * lev[v];
        V->ne = wf(p, DV_NLEV) * lev[v];
        V->ph = V->ph2 = V->lp = 0.0f;
        V->pe = 1.0f;
        V->age = 0;
        V->def = def;
        V->tune = v == TOM ? TUNE_F[b >> DC_B_PITCH & 3u] : 1.0f;
        s->hits[v]++;
    }
}

static float voice(DrumVoice *V, int v, const uint32_t *kw, float n, float y)
{
    const uint32_t *p = kw + DK_V0 + V->def * DV_WORDS;
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
            inc = inc * V->tune;                    /* x 1 (exactly the same) but for the tom */
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
    int groove = (int)fx_param_clamp(&d[DC_GROOVE], pr->value[DC_GROOVE]);
    uint32_t dir = BANK[groove * DRUMCHAPEL_PATTERNS + pattern];
    const uint32_t *kw = KW[(int)fx_param_clamp(&d[DC_KIT], pr->value[DC_KIT])];
    float lev[DRUMCHAPEL_VOICES], level;
    uint32_t thr = (uint32_t)(fx_param_clamp(&d[DC_SWING], pr->value[DC_SWING]) * DRUMCHAPEL_SWING_MAX);
    size_t i;
    int v;

    lev[KICK] = fx_param_clamp(&d[DC_KICK], pr->value[DC_KICK]);
    lev[SNARE] = fx_param_clamp(&d[DC_SNARE], pr->value[DC_SNARE]);
    lev[HAT] = fx_param_clamp(&d[DC_HAT], pr->value[DC_HAT]);
    lev[TOM] = lev[KICK];                           /* the toms at the Kick knob's level */
    level = fx_param_clamp(&d[DC_LEVEL], pr->value[DC_LEVEL]);

    for (i = 0; i < n; i++) {
        float x = in[i], y = 0.0f, z, w;
        if (!isfinite(x)) x = 0.0f;
        /* the step: due at the wrap, odd steps also wait for the swing threshold; it continues at
           (step mod the groove's length) whatever groove it was counted in */
        if (s->pend && s->acc >= ((s->step & 1u) ? thr : 0u)) {
            uint32_t b;
            s->pend = 0;
            s->len = dir & 511u;
            while (s->step >= s->len) s->step -= s->len;
            b = step_byte(dir, s->step);
            hit(s, b, kw, lev);
            s->fires++;
            s->last_step = s->step;
            s->last_byte = b;
        }
        s->acc += inc;
        if (s->acc >= DRUMCHAPEL_PERIOD) {
            s->acc -= DRUMCHAPEL_PERIOD;
            s->step = s->step + 1;
            if (s->step >= s->len) s->step = 0;
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
