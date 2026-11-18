/* test_greasy - Greasy Strangler's reference tests (no hardware, no files). */
#include "greasy.h"
#include "../common/signals.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SR 48000.0f
#define N  ((size_t)(4 * 48000))
#define HZ(inc) ((double)(inc) * 48000.0)

static int failures, checks;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static float state[1024];
#define S ((GreasyState *)(void *)state)

static void set(FxParams *p, int octave, float glide, float drift, float warble, float fuzz, float tone, float dry, float level)
{
    memset(p, 0, sizeof *p);
    p->value[GS_OCTAVE] = (float)octave; p->value[GS_GLIDE] = glide; p->value[GS_DRIFT] = drift;
    p->value[GS_WARBLE] = warble; p->value[GS_FUZZ] = fuzz; p->value[GS_TONE] = tone; p->value[GS_DRY] = dry;
    p->value[GS_LEVEL] = level;
}

static void start(void) { fx_greasy.reset(state, SR); }

static void run(const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    size_t i;
    for (i = 0; i < n; i += block)
        fx_greasy.process(state, p, in + i, out + i, n - i < block ? n - i : block);
}

static void render(const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    start();
    run(p, in, out, n, block);
}

static double cents(double f, double ref) { return 1200.0 * log(f / ref) / log(2.0); }

static double rms(const float *x, size_t n)
{
    double e = 0;
    size_t i;
    for (i = 0; i < n; i++) e += (double)x[i] * x[i];
    return sqrt(e / (double)n);
}

static double peak(const float *x, size_t n)
{
    double m = 0;
    size_t i;
    for (i = 0; i < n; i++) if (fabs(x[i]) > m) m = fabs(x[i]);
    return m;
}

/* a guitar-ish note: a decaying fundamental with some 2nd and 3rd harmonic, then silence after `len` samples */
static void note(float *x, size_t n, double hz, size_t len, double amp)
{
    size_t i;
    for (i = 0; i < n; i++) {
        double t = (double)i / SR, a = i < len ? amp * exp(-t * 1.5) : 0.0, w = 2 * 3.14159265358979 * hz * t;
        x[i] = (float)(a * (sin(w) + 0.4 * sin(2 * w + 0.3) + 0.25 * sin(3 * w + 1.1)));
    }
}

int main(void)
{
    float *x = calloc(N, sizeof *x), *y = malloc(N * sizeof *y), *z = malloc(N * sizeof *z);
    FxParams p;
    double c, a, b;
    size_t i;
    int k, bad;
    static const double hz[] = { 82.41, 110.0, 146.83, 196.0, 246.94, 329.63, 440.0 };
    static const double ratio[] = { 0.25, 0.5, 1.0, 2.0 };
    if (!x || !y || !z) return 2;

    /* nothing played: the drone is silent (and the dry signal is exactly the input) */
    set(&p, 2, 0.3f, 0.3f, 0.3f, 0.3f, 0.5f, 1, 1); render(&p, x, y, N, 16);
    CHECK(peak(y, N) == 0.0, "silence in, %g out", peak(y, N));
    CHECK(S->rate == 0.0f, "a rate with nothing played: %g Hz", HZ(S->rate));

    /* Unison: the drone's root locks to the note within a few cents, low E to high A */
    for (k = 0; k < (int)(sizeof hz / sizeof hz[0]); k++) {
        note(x, N, hz[k], N / 2, 0.5);
        set(&p, 2, 0, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2, 16);
        c = cents(HZ(S->rate), hz[k]);
        CHECK(fabs(c) < (hz[k] < 300 ? 4.0 : 8.0), "%g Hz: the drone at %g Hz (%+.1f cents)", hz[k], HZ(S->rate), c);
        CHECK(fabs(HZ(S->inc[0]) - HZ(S->rate)) < 1e-3, "%g Hz: the root voice is not at the rate", hz[k]);
        CHECK(fabs(cents(HZ(S->inc[2]), HZ(S->rate)) - 700.0) < 1.0, "%g Hz: the fifth at %g Hz", hz[k], HZ(S->inc[2]));
        CHECK(fabs(cents(HZ(S->inc[3]), HZ(S->rate)) - 1200.0) < 1.0, "%g Hz: the octave at %g Hz", hz[k], HZ(S->inc[3]));
    }

    /* a plucked string (Karplus-Strong, period L + 0.5 samples) is caught too */
    sig_pluck(x, N, SR, 82.41f, 0.6f, 3);
    set(&p, 2, 0, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2, 16);
    c = cents(HZ(S->rate), SR / (582.0 + 0.5));
    CHECK(fabs(c) < 5.0, "pluck: the drone at %g Hz (%+.1f cents)", HZ(S->rate), c);

    /* the Octave knob moves the drone by octaves */
    note(x, N, 110.0, N / 2, 0.5);
    set(&p, 2, 0, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2, 16);
    a = HZ(S->rate);
    for (k = 0; k < 4; k++) {
        set(&p, k, 0, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2, 16);
        CHECK(fabs(HZ(S->rate) / a - ratio[k]) < 1e-4 * ratio[k], "Octave %d: %g Hz against %g at Unison", k, HZ(S->rate), a);
    }

    /* it holds the note after the guitar stops: 3.5 s of silence after half a second of 110 Hz */
    note(x, N, 110.0, N / 8, 0.5);
    set(&p, 2, 0, 0, 0, 0.3f, 0.5f, 0, 1); render(&p, x, y, N, 16);
    CHECK(fabs(cents(HZ(S->rate), 110.0)) < 4.0, "after the note stops: %g Hz", HZ(S->rate));
    a = rms(y + N - 48000, 48000);
    CHECK(a > 0.05, "the drone after the note stops: rms %g", a);

    /* a note is caught only after three agreeing periods: two cycles of 200 Hz are not enough */
    memset(x, 0, N * sizeof *x);
    for (i = 0; i < 480; i++) x[1000 + i] = (float)(0.5 * sin(2 * 3.14159265358979 * 200.0 * (double)i / SR));
    set(&p, 2, 0, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 4, 16);
    CHECK(S->rate == 0.0f, "two cycles caught as a note: %g Hz", HZ(S->rate));

    /* Glide: from 110 Hz to 165 Hz. Glide 0 is on the new note 60 ms after it starts; Glide 1 is still near
       the old one, and arrives in the end */
    note(x, N / 2, 110.0, N / 2, 0.5);
    note(x + N / 2, N / 2, 165.0, N / 2, 0.5);
    set(&p, 2, 0, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2 + 2880, 16);
    CHECK(fabs(cents(HZ(S->rate), 165.0)) < 4.0, "Glide 0: %g Hz 60 ms into the new note", HZ(S->rate));
    set(&p, 2, 1, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2 + 2880, 16);
    CHECK(HZ(S->rate) < 115.0, "Glide 1: already at %g Hz 60 ms into the new note", HZ(S->rate));
    run(&p, x + N / 2 + 2880, y, N / 2 - 2880, 16);
    a = HZ(S->rate);
    CHECK(a > 150.0, "Glide 1: only %g Hz 1.9 s into the new note", a);
    set(&p, 2, 0.5f, 0, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N / 2 + 9600, 16);
    b = HZ(S->rate);
    CHECK(b > 115.0 && b < 160.0, "Glide 0.5: %g Hz 200 ms into the new note", b);

    /* Drift and Warble move the voices off their intervals; at 0 they stay put */
    note(x, N, 110.0, N, 0.5);
    set(&p, 2, 0, 1, 0, 0.3f, 0.5f, 1, 1); render(&p, x, y, N, 16);
    CHECK(cents(HZ(S->inc[0]), HZ(S->rate)) > 5.0, "Drift 1: the root only %g cents up", cents(HZ(S->inc[0]), HZ(S->rate)));
    set(&p, 2, 0, 0, 1, 0.3f, 0.5f, 1, 1); render(&p, x, y, N, 16);
    {
        double lo = 1e9, hi = 0;
        for (i = 0; i < N / 2; i += 160) {
            run(&p, x + i, y + i, 160, 16);
            if (HZ(S->inc[1]) < lo) lo = HZ(S->inc[1]);
            if (HZ(S->inc[1]) > hi) hi = HZ(S->inc[1]);
        }
        CHECK(cents(hi, lo) > 50.0, "Warble 1: the sharp root moves only %g cents", cents(hi, lo));
    }

    /* Fuzz: squarer (rms closer to the peak) at about the same level */
    note(x, N, 110.0, N, 0.5);
    set(&p, 1, 0, 0.2f, 0.2f, 0, 1, 0, 1); render(&p, x, y, N, 16);
    set(&p, 1, 0, 0.2f, 0.2f, 1, 1, 0, 1); render(&p, x, z, N, 16);
    a = rms(y + N / 2, N / 2); b = rms(z + N / 2, N / 2);
    CHECK(b / a > 0.5 && b / a < 2.0, "Fuzz 1 rms %g against Fuzz 0 rms %g", b, a);
    CHECK(b / peak(z + N / 2, N / 2) > 1.3 * a / peak(y + N / 2, N / 2), "Fuzz 1 not squarer: rms/peak %g against %g",
          b / peak(z + N / 2, N / 2), a / peak(y + N / 2, N / 2));

    /* Tone 0 is darker than Tone 1 */
    set(&p, 2, 0, 0.2f, 0.2f, 0.5f, 0, 0, 1); render(&p, x, y, N, 16);
    set(&p, 2, 0, 0.2f, 0.2f, 0.5f, 1, 0, 1); render(&p, x, z, N, 16);
    a = rms(y + N / 2, N / 2); b = rms(z + N / 2, N / 2);
    CHECK(a < 0.8 * b, "Tone 0 rms %g, Tone 1 rms %g", a, b);

    /* Dry: 1 with Level 0 is exactly the input; 0 takes the guitar out, leaving the drone alone */
    set(&p, 2, 0.3f, 0.3f, 0.3f, 0.3f, 0.5f, 1, 0); render(&p, x, y, N, 16);
    CHECK(memcmp(x, y, N * sizeof *x) == 0, "Dry 1, Level 0: not the input");
    set(&p, 2, 0.3f, 0.3f, 0.3f, 0.3f, 0.5f, 0, 0); render(&p, x, y, N, 16);
    CHECK(peak(y, N) == 0.0, "Dry 0, Level 0: %g out", peak(y, N));
    set(&p, 2, 0.3f, 0.3f, 0.3f, 0.3f, 0.5f, 1, 1); render(&p, x, y, N, 16);
    set(&p, 2, 0.3f, 0.3f, 0.3f, 0.3f, 0.5f, 0, 1); render(&p, x, z, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (fabsf(y[i] - x[i] - z[i]) > 1e-6f) bad++;
    CHECK(bad == 0, "Dry 0 is not Dry 1 less the guitar in %d samples", bad);
    CHECK(rms(z + N / 2, N / 2) > 0.05, "Dry 0: no drone");

    /* the drone fades in: quiet in the first 10 ms after the note is caught */
    note(x, N, 110.0, N, 0.5);
    set(&p, 2, 0, 0, 0, 0, 1, 0, 1); render(&p, x, y, N, 16);
    for (i = 0; i < N && y[i] == 0.0f; i++) {}
    a = peak(y + i, 480); b = peak(y + N / 2, 48000);
    CHECK(i < 4800 && a < 0.4 * b, "fade-in: starts at sample %zu, peak %g in the first 10 ms against %g", i, a, b);

    /* any block size gives the same output */
    sig_chord(x, N, SR, (const float[]){ 82.41f, 123.47f, 164.81f }, 3, 12000, 0.8f);
    set(&p, 1, 0.4f, 0.5f, 0.6f, 0.5f, 0.3f, 0.7f, 0.6f);
    render(&p, x, y, N, 16);
    for (k = 1; k <= 97; k += 48) {
        render(&p, x, z, N, (size_t)k);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "block size %d differs from 16", k);
    }

    /* hostile input and parameters stay finite */
    sig_noise(x, N, 4, 4.0f);
    x[100] = NAN; x[200] = INFINITY; x[300] = -INFINITY; x[400] = 1e30f; x[401] = -3e38f;
    set(&p, 99, 9, 9, 9, 9, 9, 9, 9); render(&p, x, y, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (!isfinite(y[i])) bad++;
    CHECK(bad == 0, "hostile high: %d bad samples", bad);
    set(&p, -9, -9, -9, -9, -9, -9, -9, -9); render(&p, x, y, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (!isfinite(y[i])) bad++;
    CHECK(bad == 0, "hostile low: %d bad samples", bad);
    for (k = 0; k < GS_NPARAMS; k++) p.value[k] = NAN;
    render(&p, x, y, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (!isfinite(y[i])) bad++;
    CHECK(bad == 0, "NaN knobs: %d bad samples", bad);
    sig_noise(x, N, 5, 1.0f);                         /* without the 1e30 spikes, the output stays modest */
    set(&p, 3, 0, 1, 1, 1, 1, 1, 1); render(&p, x, y, N, 16);
    CHECK(peak(y, N) < 3.0, "loud noise, everything up: peak %g", peak(y, N));

    printf("%d checks, %d failures\n", checks, failures);
    free(x); free(y); free(z);
    return failures ? 1 : 0;
}
