/* test_bethblahem - Bethblahem's reference tests (no hardware, no files). */
#include "bethblahem.h"
#include "../common/signals.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SR 48000.0f
#define N  ((size_t)(4 * 48000))
#define HZ(inc) ((inc) * 48000.0f)
#define PI 3.14159265358979323846

static int failures, checks;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void set(FxParams *p, int octave, float glide, float vib, float rate, float growl, float sub, float dry, float level)
{
    memset(p, 0, sizeof *p);
    p->value[B_OCTAVE] = (float)octave; p->value[B_GLIDE] = glide; p->value[B_VIBRATO] = vib;
    p->value[B_RATE] = rate; p->value[B_GROWL] = growl; p->value[B_SUB] = sub; p->value[B_DRY] = dry;
    p->value[B_LEVEL] = level;
}

static void run(BethblahemState *s, const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    size_t i;
    for (i = 0; i < n; i += block)
        fx_bethblahem.process(s, p, in + i, out + i, n - i < block ? n - i : block);
}

static void render(BethblahemState *s, const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    fx_bethblahem.reset(s, SR);
    run(s, p, in, out, n, block);
}

/* the amplitude of the component at hz (a single-bin DFT) */
static double tone_amp(const float *x, size_t n, double hz)
{
    double re = 0, im = 0, w = 2 * PI * hz / SR;
    size_t i;
    for (i = 0; i < n; i++) {
        re += x[i] * cos(w * (double)i);
        im -= x[i] * sin(w * (double)i);
    }
    return 2 * sqrt(re * re + im * im) / (double)n;
}

static double rms(const float *x, size_t n)
{
    double e = 0;
    size_t i;
    for (i = 0; i < n; i++) e += (double)x[i] * x[i];
    return sqrt(e / (double)n);
}

/* harmonics 2..10 against the fundamental, in energy */
static double harmonic_ratio(const float *x, size_t n, double f0)
{
    double a1 = tone_amp(x, n, f0), e = 0;
    int k;
    for (k = 2; k <= 10; k++) {
        double a = tone_amp(x, n, f0 * k);
        e += a * a;
    }
    return e / (a1 * a1);
}

int main(void)
{
    float *x = calloc(N, sizeof *x), *y = malloc(N * sizeof *y), *z = malloc(N * sizeof *z);
    BethblahemState s;
    FxParams p;
    Rng r;
    double a, b, f0, m;
    float lo, hi, v;
    size_t i;
    int k, bad, cross;
    if (!x || !y || !z) return 2;

    /* the voice's sine: within 2e-4 of sin(2 pi p), never past 1 */
    for (i = 0, bad = 0; i < 100000; i++) {
        float ph = (float)i / 100000.0f, e = bethblahem_sin(ph);
        if (fabs(e - sin(2 * PI * ph)) > 2e-4 || fabsf(e) > 1.0f) bad++;
    }
    CHECK(bad == 0, "sine: %d points off", bad);

    /* silence: nothing at all, before any note */
    set(&p, 2, 0.4f, 0.3f, 0.4f, 0.5f, 0.3f, 0.7f, 0.7f); render(&s, &p, x, y, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (y[i] != 0.0f) bad++;
    CHECK(bad == 0, "silence gives %d non-zero samples", bad);

    /* a 110 Hz note lands Octave octaves down */
    sig_sine(x, N, SR, 110.0f, 0.5f);
    for (k = 0; k <= 4; k++) {
        float want = 110.0f / (float)(1 << k);
        set(&p, k, 0, 0, 0.5f, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);
        CHECK(fabsf(HZ(s.inc) - want) < 0.005f * want, "Octave %d: %g Hz, want %g", k, HZ(s.inc), want);
    }
    /* and the output is at that pitch: Octave 1, 55 Hz -> about 27.5 rising zero crossings in 0.5 s */
    set(&p, 1, 0, 0, 0.5f, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);
    for (i = 24000, cross = 0; i < 48000; i++) if (y[i - 1] < 0.0f && y[i] >= 0.0f) cross++;
    CHECK(cross >= 27 && cross <= 28, "Octave 1: %d rising crossings in 0.5 s", cross);

    /* a plucked low E (82.4 Hz) is tracked: -2 Oct, 20.6 Hz */
    sig_pluck(x, N, SR, 82.41f, 0.6f, 3);
    set(&p, 2, 0, 0, 0.5f, 0, 0, 0, 1); render(&s, &p, x, y, 24000, 16);
    CHECK(fabsf(HZ(s.inc) - 20.6f) < 0.25f, "plucked E: %g Hz, want 20.6", HZ(s.inc));

    /* it holds the last note when the guitar stops, and keeps sounding */
    sig_sine(x, N, SR, 110.0f, 0.5f);
    for (i = 48000; i < N; i++) x[i] = 0.0f;
    set(&p, 0, 0.2f, 0, 0.5f, 0, 0, 0, 1); render(&s, &p, x, y, N, 16);
    CHECK(fabsf(HZ(s.inc) - 110.0f) < 0.6f, "held: %g Hz after 3 s of silence", HZ(s.inc));
    CHECK(rms(y + N - 24000, 24000) > 0.1, "held: rms %g after 3 s of silence", rms(y + N - 24000, 24000));
    /* Octave still moves the held note */
    set(&p, 3, 0, 0, 0.5f, 0, 0, 0, 1); run(&s, &p, x + N - 24000, z, 24000, 16);
    CHECK(fabsf(HZ(s.inc) - 13.75f) < 0.1f, "held, Octave 3: %g Hz", HZ(s.inc));

    /* Glide: 100 ms after 110 Hz -> 165 Hz, Glide 0 is there and Glide 1 has barely moved */
    sig_sine(x, 48000, SR, 110.0f, 0.5f);
    sig_sine(x + 48000, 48000, SR, 165.0f, 0.5f);
    set(&p, 0, 0, 0, 0.5f, 0, 0, 0, 1); render(&s, &p, x, y, 48000 + 4800, 16);
    CHECK(fabsf(HZ(s.inc) - 165.0f) < 1.5f, "Glide 0: %g Hz 100 ms after the change", HZ(s.inc));
    set(&p, 0, 0, 0, 0.5f, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);
    a = HZ(s.inc);
    set(&p, 0, 1, 0, 0.5f, 0, 0, 0, 1); run(&s, &p, x + 48000, y, 4800, 16);
    b = HZ(s.inc);
    CHECK(fabs(a - 110.0) < 0.5 && b > a + 0.5 && b < 115.0, "Glide 1: %g Hz -> %g Hz 100 ms after the change", a, b);
    run(&s, &p, x + 52800, y, 43200, 16);
    CHECK(HZ(s.inc) > 125.0f && HZ(s.inc) < 160.0f, "Glide 1: %g Hz 1 s after the change", HZ(s.inc));

    /* Vibrato: Rate 0 is 3 Hz, Rate 1 is 8 Hz; depth 1 is +-6 %, depth 0 none */
    sig_sine(x, N, SR, 110.0f, 0.5f);
    for (k = 0; k <= 1; k++) {
        fx_bethblahem.reset(&s, SR);
        set(&p, 1, 0, 1, (float)k, 0, 0, 0, 1);
        lo = 2.0f; hi = 0.0f; cross = 0;
        for (i = 0; i < 2 * 48000; i += 16) {
            float prev = s.vmul - 1.0f;
            fx_bethblahem.process(&s, &p, x + i, y + i, 16);
            if (i && prev < 0.0f && s.vmul - 1.0f >= 0.0f) cross++;
            if (s.vmul < lo) lo = s.vmul;
            if (s.vmul > hi) hi = s.vmul;
        }
        CHECK(cross == (k ? 15 : 5), "Rate %d: %d vibrato cycles in 2 s", k, cross);
        CHECK(hi > 1.0595f && hi < 1.0601f && lo < 0.9405f && lo > 0.9399f, "Vibrato 1: %g .. %g", lo, hi);
    }
    set(&p, 1, 0, 0, 1, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);
    CHECK(s.vmul == 1.0f, "Vibrato 0: %g", s.vmul);

    /* Growl adds harmonics: -2 Oct (27.5 Hz), Level 0.5 */
    set(&p, 2, 0, 0, 0.5f, 0, 0, 0, 0.5f); render(&s, &p, x, y, 2 * 48000, 16);
    f0 = HZ(s.inc);
    a = harmonic_ratio(y + 48000, 48000, f0);
    set(&p, 2, 0, 0, 0.5f, 1, 0, 0, 0.5f); render(&s, &p, x, y, 2 * 48000, 16);
    b = harmonic_ratio(y + 48000, 48000, f0);
    CHECK(a < 0.005 && b > 0.1, "Growl 0: harmonics %g of the fundamental, Growl 1: %g", a, b);

    /* Sub adds an octave below: -1 Oct (55 Hz), the sub at 27.5 Hz */
    set(&p, 1, 0, 0, 0.5f, 0, 0, 0, 0.5f); render(&s, &p, x, y, 2 * 48000, 16);
    f0 = HZ(s.inc);
    a = tone_amp(y + 48000, 48000, f0 * 0.5);
    set(&p, 1, 0, 0, 0.5f, 0, 1, 0, 0.5f); render(&s, &p, x, y, 2 * 48000, 16);
    b = tone_amp(y + 48000, 48000, f0 * 0.5);
    CHECK(b > 0.1 && b > 30 * a, "Sub: %g at f/2 with Sub 0, %g with Sub 1", a, b);

    /* no DC on the output, with Growl's offset and the note held (the mean over whole cycles) */
    for (i = 48000; i < N; i++) x[i] = 0.0f;
    set(&p, 2, 0, 0, 0.5f, 1, 0, 0, 1); render(&s, &p, x, y, N, 16);
    f0 = HZ(s.inc);
    k = (int)floor(40 * 48000 / f0 + 0.5);              /* 40 cycles */
    for (i = N - (size_t)k, m = 0; i < N; i++) m += y[i];
    m /= k;
    CHECK(fabs(m) < 1e-3 && rms(y + N - k, (size_t)k) > 0.05, "DC: mean %g, rms %g", m, rms(y + N - k, (size_t)k));

    /* the synth part is bounded, with every knob moving and loud input */
    sig_noise(x, N, 7, 3.0f);
    for (i = 0; i < N; i += 9600) sig_pluck(x + i, 4800, SR, 41.2f * (float)(1 + i / 9600 % 6), 2.0f, i);
    rng_seed(&r, 11);
    fx_bethblahem.reset(&s, SR);
    for (i = 0, bad = 0; i < N; i += 16) {
        size_t j;
        if (i % 4800 == 0)
            set(&p, (int)(rng_u32(&r) % 5), 0.5f + 0.5f * rng_uniform(&r), 0.5f + 0.5f * rng_uniform(&r),
                0.5f + 0.5f * rng_uniform(&r), 0.5f + 0.5f * rng_uniform(&r), 0.5f + 0.5f * rng_uniform(&r),
                0.5f + 0.5f * rng_uniform(&r), 1.0f);
        fx_bethblahem.process(&s, &p, x + i, y + i, 16);
        for (j = i; j < i + 16; j++) {
            float xc = x[j] > 16.0f ? 16.0f : x[j] < -16.0f ? -16.0f : x[j];
            if (!(fabsf(y[j] - p.value[B_DRY] * xc) <= 0.8f)) bad++;
        }
    }
    CHECK(bad == 0, "bounded: %d samples with the synth past 0.8", bad);

    /* Dry 0 and Level 0: nothing; Dry 1 and Level 0: exactly the input */
    sig_noise(x, N, 9, 0.5f);
    set(&p, 2, 0.4f, 0.3f, 0.4f, 0.5f, 0.3f, 0, 0); render(&s, &p, x, y, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (y[i] != 0.0f) bad++;
    CHECK(bad == 0, "Dry 0, Level 0: %d non-zero samples", bad);
    set(&p, 2, 0.4f, 0.3f, 0.4f, 0.5f, 0.3f, 1, 0); render(&s, &p, x, y, N, 16);
    for (i = 0, bad = 0; i < N; i++) if (y[i] != x[i]) bad++;
    CHECK(bad == 0, "Dry 1, Level 0: %d samples not the input", bad);
    /* Dry 0 with the synth on: the guitar is gone (Dry 1's output less the input) */
    sig_pluck(x, N, SR, 98.0f, 0.6f, 8);
    set(&p, 2, 0.4f, 0.3f, 0.4f, 0.5f, 0.3f, 0, 1); render(&s, &p, x, y, N, 16);
    set(&p, 2, 0.4f, 0.3f, 0.4f, 0.5f, 0.3f, 1, 1); render(&s, &p, x, z, N, 16);
    for (i = 0, a = 0; i < N; i++) if (fabs((double)z[i] - x[i] - y[i]) > a) a = fabs((double)z[i] - x[i] - y[i]);
    CHECK(a < 1e-6 && rms(y, N) > 0.05, "Dry 0: %g away from Dry 1 less the input", a);

    /* any block size gives the same output */
    sig_pluck(x, N, SR, 110.0f, 0.6f, 5);
    set(&p, 2, 0.5f, 0.7f, 0.3f, 0.6f, 0.5f, 0.5f, 0.8f);
    render(&s, &p, x, y, N, 16);
    for (k = 1; k <= 97; k += 36) {
        render(&s, &p, x, z, N, (size_t)k);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "block size %d differs from 16", k);
    }

    /* hostile input and parameters stay finite and bounded */
    sig_noise(x, N, 4, 4.0f);
    x[100] = NAN; x[200] = INFINITY; x[300] = -INFINITY; x[400] = 1e30f; x[500] = -1e30f;
    for (k = 0; k < 3; k++) {
        v = k == 0 ? 99.0f : k == 1 ? -99.0f : NAN;
        set(&p, 0, v, v, v, v, v, v, v);
        p.value[B_OCTAVE] = v;
        render(&s, &p, x, y, N, 16);
        for (i = 0, bad = 0; i < N; i++) if (!isfinite(y[i]) || fabsf(y[i]) > 16.8f) bad++;
        CHECK(bad == 0, "hostile %d: %d bad samples", k, bad);
    }

    printf("%d checks, %d failures\n", checks, failures);
    free(x); free(y); free(z);
    return failures ? 1 : 0;
}
