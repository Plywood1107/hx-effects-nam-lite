/* test_puggy - Puggy Puncher's reference tests (no hardware, no files). */
#include "puggy.h"
#include "../common/signals.h"
#include "../metronome/metronome.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SR 48000.0f
#define N  ((size_t)(8 * 48000))
#define MAXSTEPS 200000

static int failures, checks;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void set(FxParams *p, float time, int step, float chance, int wild, int hold, int seed, float mix, float level)
{
    memset(p, 0, sizeof *p);
    p->value[PG_TIME] = time; p->value[PG_STEP] = (float)step; p->value[PG_CHANCE] = chance;
    p->value[PG_WILD] = (float)wild; p->value[PG_HOLD] = (float)hold; p->value[PG_SEED] = (float)seed;
    p->value[PG_MIX] = mix; p->value[PG_LEVEL] = level;
}

static PuggyState st;
static size_t at[MAXSTEPS];                  /* the sample each step fired on */
static int roll[MAXSTEPS];                   /* and its treatment */
static size_t nsteps;

static void render(const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    size_t i;
    fx_puggy.reset(&st, SR);
    for (i = 0; i < n; i += block)
        fx_puggy.process(&st, p, in + i, out + i, n - i < block ? n - i : block);
}

/* One sample at a time, logging every step. */
static void render_log(const FxParams *p, const float *in, float *out, size_t n)
{
    size_t i;
    uint32_t seen = 0;
    nsteps = 0;
    fx_puggy.reset(&st, SR);
    for (i = 0; i < n; i++) {
        fx_puggy.process(&st, p, in + i, out + i, 1);
        if (st.steps != seen) {
            seen = st.steps;
            if (nsteps < MAXSTEPS) { at[nsteps] = i; roll[nsteps] = st.cur; nsteps++; }
        }
    }
}

static double goertzel(const float *x, size_t n, double hz)
{
    double w = 2 * 3.14159265358979323846 * hz / SR, c = 2 * cos(w), s1 = 0, s2 = 0, s;
    size_t i;
    for (i = 0; i < n; i++) { s = x[i] + c * s1 - s2; s2 = s1; s1 = s; }
    return sqrt(s1 * s1 + s2 * s2 - c * s1 * s2) * 2 / (double)n;
}

static double diff_rms(const float *x, size_t n)
{
    double e = 0;
    size_t i;
    for (i = 1; i < n; i++) e += (double)(x[i] - x[i - 1]) * (x[i] - x[i - 1]);
    return sqrt(e / (double)(n - 1));
}

static float max_jump(const float *x, size_t n)
{
    float m = 0;
    size_t i;
    for (i = 1; i < n; i++) if (fabsf(x[i] - x[i - 1]) > m) m = fabsf(x[i] - x[i - 1]);
    return m;
}

static int bounded(const float *x, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) if (!isfinite(x[i]) || fabsf(x[i]) > 8.0f) return 0;
    return 1;
}

int main(void)
{
    float *x = malloc(N * sizeof *x), *y = malloc(N * sizeof *y), *z = malloc(N * sizeof *z);
    static const float TIMES[] = { 0.5f, 0.436364f, 0.1f, 1.7f, 0.2857f };
    static const int GRID[] = { 2, 3, 5, 6, 8, 9, 10 };          /* straight and triplet values */
    static const float CHORD[] = { 82.41f, 123.47f, 164.81f, 207.65f, 246.94f, 329.63f };
    FxParams p;
    size_t i, k, n2 = 60 * 48000;
    float *xl, *yl;
    int t, g, w, b, bad;
    if (!x || !y || !z) return 2;
    xl = calloc(n2, sizeof *xl); yl = malloc(n2 * sizeof *yl);
    if (!xl || !yl) return 2;

    /* the tables: M is 6 x steps a beat, every Wild nibble a real treatment, seeds distinct and non-zero */
    CHECK(puggy_stepmul(0) == 3 && puggy_stepmul(2) == 6 && puggy_stepmul(8) == 24 && puggy_stepmul(10) == 48, "Step table");
    for (w = 0; w < PUGGY_WILDS; w++)
        for (k = 0; k < 8; k++) {
            uint32_t v = (puggy_wild(w) >> (4 * k)) & 15u;
            CHECK(v >= 1 && v < PUGGY_TREATMENTS, "Wild %d entry %d is %u", w, (int)k, v);
        }
    CHECK(puggy_seed(0) == 0, "Seed 0 is not Random");
    for (t = 1; t < PUGGY_SEEDS; t++) {
        CHECK(puggy_seed(t) != 0, "seed %d is zero", t);
        for (g = 1; g < t; g++) CHECK(puggy_seed(t) != puggy_seed(g), "seeds %d and %d equal", t, g);
    }

    /* steps land exactly on the grid: step k on the first sample at or after k step lengths, for a minute,
       at five tempos and every straight and triplet value; the first sample is a step */
    for (t = 0; t < 5; t++)
        for (g = 0; g < 7; g++) {
            uint32_t inc = click_bpm100(TIMES[t]) * (uint32_t)puggy_stepmul(GRID[g]);
            uint64_t T6 = 6ull * 288000000ull;
            set(&p, TIMES[t], GRID[g], 0.5f, 0, 1, 0, 1, 1);
            render_log(&p, xl, yl, n2);
            bad = 0;
            for (k = 0; k < nsteps; k++) {
                uint64_t want = k ? (k * T6 + inc - 1) / inc : 0;
                if (at[k] != want) bad++;
            }
            CHECK(bad == 0 && nsteps == (size_t)(((uint64_t)(n2 - 1) * inc) / T6 + 1),
                  "time %g step %d: %d steps off the grid, %d steps", TIMES[t], GRID[g], bad, (int)nsteps);
        }
    /* dotted values restart on the bar: 1/4. at 120 BPM is 3 + 3 + 2 eighths */
    set(&p, 0.5f, 1, 0.5f, 0, 1, 0, 1, 1);
    render_log(&p, xl, yl, 5 * 96000);
    CHECK(nsteps == 15 && at[0] == 0 && at[1] == 36000 && at[2] == 72000 && at[3] == 96000 && at[4] == 132000,
          "1/4.: %d steps at %d %d %d %d", (int)nsteps, (int)at[1], (int)at[2], (int)at[3], (int)at[4]);

    /* Chance 0: exactly the input, whatever Mix and Wild */
    sig_noise(x, N, 9, 0.5f);
    for (w = 0; w < PUGGY_WILDS; w += 3) {
        set(&p, 0.3f, 8, 0, w, 1, 0, 0.7f, 1); render(&p, x, y, N, 16);
        CHECK(memcmp(x, y, N * sizeof *x) == 0, "Chance 0, Wild %d: not the input", w);
    }
    /* Mix 0 too */
    set(&p, 0.3f, 8, 1, 0, 1, 0, 0, 1); render(&p, x, y, N, 16);
    CHECK(memcmp(x, y, N * sizeof *x) == 0, "Mix 0: not the input");

    /* Chance 1: never clean; Chance 0.5: about half */
    sig_chord(x, N, SR, CHORD, 6, 960, 1.0f);
    for (w = 0; w < PUGGY_WILDS; w++) {
        set(&p, 0.25f, 10, 1, w, 1, 0, 1, 1); render_log(&p, x, y, N);
        for (k = 0, bad = 0; k < nsteps; k++) if (roll[k] == PT_CLEAN) bad++;
        CHECK(bad == 0 && nsteps > 100, "Chance 1, Wild %d: %d clean steps of %d", w, bad, (int)nsteps);
    }
    set(&p, 0.1f, 10, 0.5f, 0, 1, 0, 1, 1); render_log(&p, x, y, N);
    for (k = 0, bad = 0; k < nsteps; k++) if (roll[k] == PT_CLEAN) bad++;
    CHECK(bad > 0.42 * (double)nsteps && bad < 0.58 * (double)nsteps, "Chance 0.5: %d clean steps of %d", bad, (int)nsteps);
    /* All brings every treatment */
    {
        int seen[PUGGY_TREATMENTS] = { 0 };
        for (k = 0; k < nsteps; k++) seen[roll[k]]++;
        for (t = 0; t < PUGGY_TREATMENTS; t++) CHECK(seen[t] > 0, "All never rolled treatment %d", t);
    }

    /* each treatment does its thing (Chance 1, one treatment, Mix 1) */
    sig_sine(x, N, SR, 220.0f, 0.5f);
    set(&p, 0.5f, 8, 1, 2, 1, 0, 1, 1); render(&p, x, y, N, 16);            /* Rhythm: mute */
    for (i = 32, bad = 0; i < N; i++) if (y[i] != 0.0f) bad++;
    CHECK(bad == 0, "mute: %d samples not silent", bad);

    set(&p, 0.5f, 8, 1, 7, 1, 0, 1, 1); render(&p, x, y, N, 16);            /* Octave */
    {
        double sub = goertzel(y + N / 2, N / 2, 110.0), dry = goertzel(x + N / 2, N / 2, 110.0);
        CHECK(sub > 0.2 && dry < 0.01, "octave: 110 Hz at %g (input %g)", sub, dry);
    }
    sig_pluck(x, N, SR, 146.83f, 0.8f, 3);
    render(&p, x, y, N, 16);
    {
        double sub = goertzel(y + 4800, 48000, 73.415), dry = goertzel(x + 4800, 48000, 73.415);
        CHECK(sub > 5 * dry && sub > 0.02, "octave on a plucked D: 73 Hz at %g (input %g)", sub, dry);
    }

    sig_sine(x, N, SR, 220.0f, 0.7f);
    set(&p, 0.5f, 8, 1, 8, 1, 0, 1, 1); render(&p, x, y, N, 16);            /* Crush */
    for (i = 32, bad = 0; i < N; i++) {
        float q = y[i] * 16.0f;
        if (fabsf(q - roundf(q)) > 1e-4f) bad++;
    }
    for (i = 1024, g = 0; i < N; i++) if (y[i] != y[i - 1]) g++;
    CHECK(bad == 0, "crush: %d samples off the 1/16 grid", bad);
    CHECK(g <= (int)(N / PUGGY_CRATE) + 2 && g > 1000, "crush: %d changes (held every %d samples)", g, PUGGY_CRATE);

    sig_noise(x, N, 5, 0.5f);
    set(&p, 0.5f, 8, 1, 9, 1, 0, 1, 1); render(&p, x, y, N, 16);            /* Filter */
    {
        double a = diff_rms(y, N), c = diff_rms(x, N);
        CHECK(a < 0.25 * c, "filter: high end at %g of the input's", a / c);
    }
    set(&p, 2.0f, 0, 1, 9, 1, 0, 1, 1); render(&p, x, y, N, 16);            /* closes over a long step */
    {
        double open = diff_rms(y + 192000 + 64, 480), shut = diff_rms(y + 192000 + 96000, 4800);   /* steps 4 s apart */
        CHECK(shut < 0.1 * open, "filter: shut %g, open %g", shut, open);
    }

    sig_sine(x, N, SR, 110.0f, 0.5f);
    set(&p, 0.5f, 8, 1, 10, 1, 0, 1, 1); render(&p, x, y, N, 16);           /* Fuzz */
    for (i = 32, g = 0; i < N; i++) if (fabsf(fabsf(y[i]) - 0.3f) < 1e-5f) g++;
    CHECK(g > (int)(0.9 * (double)N), "fuzz: only %d of %d samples on the rails", g, (int)N);

    /* Seed N: every bar repeats; Random: bars differ; two seeds differ */
    sig_chord(x, N, SR, CHORD, 6, 960, 1.0f);
    set(&p, 0.25f, 8, 0.5f, 0, 1, 5, 1, 1); render_log(&p, x, y, N);         /* 16 steps a bar */
    for (k = 16, bad = 0; k < nsteps; k++) if (roll[k] != roll[k % 16]) bad++;
    CHECK(bad == 0 && nsteps > 100, "Seed 5: %d steps differ from the first bar", bad);
    memcpy(z, y, N * sizeof *y);
    {
        int first[16];
        for (k = 0; k < 16; k++) first[k] = roll[k];
        set(&p, 0.25f, 8, 0.5f, 0, 1, 6, 1, 1); render_log(&p, x, y, N);
        for (k = 0, bad = 0; k < 16; k++) if (roll[k] != first[k]) bad++;
        CHECK(bad > 0, "Seeds 5 and 6 give the same bar");
    }
    set(&p, 0.25f, 8, 0.5f, 0, 1, 5, 1, 1); render(&p, x, y, N, 37);
    CHECK(memcmp(y, z, N * sizeof *y) == 0, "Seed 5 does not repeat from reset");
    set(&p, 0.25f, 8, 0.5f, 0, 1, 0, 1, 1); render_log(&p, x, y, N);
    for (k = 16, bad = 0; k < nsteps; k++) if (roll[k] != roll[k % 16]) bad++;
    CHECK(bad > 0, "Random: every bar the same");

    /* Hold 4 repeats each roll for four steps (from the bar); Hold 1 does not */
    set(&p, 0.25f, 8, 0.5f, 0, 4, 0, 1, 1); render_log(&p, x, y, N);
    for (k = 0, bad = 0, g = 0; k < nsteps; k++) {
        if (roll[k] != roll[k - k % 4]) bad++;
        if (k % 4 == 0 && k >= 4 && roll[k] != roll[k - 4]) g++;
    }
    CHECK(bad == 0 && g > 10, "Hold 4: %d steps break a roll, %d new rolls", bad, g);
    set(&p, 0.25f, 8, 0.5f, 0, 1, 0, 1, 1); render_log(&p, x, y, N);
    for (k = 0, bad = 0; k < nsteps; k++) if (roll[k] != roll[k - k % 4]) bad++;
    CHECK(bad > 0, "Hold 1 holds");

    /* no clicks at step edges: on a 110 Hz tone the sample-to-sample change stays small for the treatments
       that have no edges of their own (mute, filter); the tone itself changes by up to 0.0072 a sample */
    sig_sine(x, N, SR, 110.0f, 0.5f);
    set(&p, 0.3f, 8, 0.5f, 2, 1, 0, 1, 1); render(&p, x, y, N, 16);
    CHECK(max_jump(y, N) < 0.025f, "mute edges: jump %g", max_jump(y, N));
    set(&p, 0.3f, 8, 0.5f, 9, 1, 0, 1, 1); render(&p, x, y, N, 16);
    CHECK(max_jump(y, N) < 0.03f, "filter edges: jump %g", max_jump(y, N));
    set(&p, 0.3f, 8, 1, 9, 1, 0, 1, 1); render(&p, x, y, N, 16);
    CHECK(max_jump(y, N) < 0.03f, "filter re-opening: jump %g", max_jump(y, N));
    /* and everything else crossfades: a step edge adds no jump of its own (the edge sample is still the last step's) */
    sig_chord(x, N, SR, CHORD, 6, 960, 1.0f);
    set(&p, 0.3f, 8, 0.7f, 0, 1, 0, 1, 1); render_log(&p, x, y, N);
    {
        float edge = 0, inside = max_jump(y, N);
        for (k = 1; k < nsteps; k++) {
            float j = fabsf(y[at[k]] - y[at[k] - 1]);
            if (j > edge) edge = j;
        }
        CHECK(edge <= inside, "step edges: jump %g (inside the steps %g)", edge, inside);
    }

    /* any block size gives the same output */
    set(&p, 0.37f, 9, 0.8f, 0, 2, 0, 0.8f, 0.9f);
    render(&p, x, y, N, 16);
    for (b = 1; b <= 97; b += 48) {
        render(&p, x, z, N, (size_t)b);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "block size %d differs from 16", b);
    }
    CHECK(bounded(y, N), "chord: output not finite and bounded");

    /* hostile input and parameters stay finite and bounded */
    sig_noise(x, N, 4, 4.0f);
    x[100] = NAN; x[200] = INFINITY; x[300] = -1e30f; x[5000] = 1e30f;
    set(&p, 1e9f, 99, 9, 99, 99, 99, 9, 9); render(&p, x, y, N, 16);
    CHECK(bounded(y, N), "hostile high: output not finite and bounded");
    set(&p, -5, -3, -9, -9, -9, -9, -9, -9); render(&p, x, y, N, 16);
    CHECK(bounded(y, N), "hostile low: output not finite and bounded");
    for (k = 0; k < PG_NPARAMS; k++) p.value[k] = NAN;
    render(&p, x, y, N, 16);
    CHECK(bounded(y, N), "NaN knobs: output not finite and bounded");

    printf("%d checks, %d failures\n", checks, failures);
    free(x); free(y); free(z); free(xl); free(yl);
    return failures ? 1 : 0;
}
