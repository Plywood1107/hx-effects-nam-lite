/* test_purewhitey - Pure Whitey's reference tests (no hardware, no files). */
#include "purewhitey.h"
#include "../common/signals.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SR 48000.0f
#define N  ((size_t)(2 * 48000))

static int failures, checks;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void set(FxParams *p, int mode, float time, float func, float sens, float tone, float dry, float mix, float level)
{
    memset(p, 0, sizeof *p);
    p->value[W_MODE] = (float)mode; p->value[W_TIME] = time; p->value[W_FUNC] = func; p->value[W_SENS] = sens;
    p->value[W_TONE] = tone; p->value[W_DRY] = dry; p->value[W_MIX] = mix; p->value[W_LEVEL] = level;
}

static PurewhiteyState st, st2;
static unsigned char play[N];
static float speed[N];
static int plens[N];

static void render(const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    size_t i;
    fx_purewhitey.reset(&st, SR);
    for (i = 0; i < n; i += block)
        fx_purewhitey.process(&st, p, in + i, out + i, n - i < block ? n - i : block);
}

/* One sample at a time, noting after each whether a slice plays, its speed and the slice being listened for. */
static void trace(const FxParams *p, const float *in, float *out, size_t n)
{
    size_t i;
    fx_purewhitey.reset(&st, SR);
    for (i = 0; i < n; i++) {
        fx_purewhitey.process(&st, p, in + i, out + i, 1);
        play[i] = (unsigned char)(st.stage > 0);
        speed[i] = st.sp;
        plens[i] = st.stage < 0 ? st.plen : 0;
    }
}

static int bounded(const float *x, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) if (!isfinite(x[i]) || fabsf(x[i]) > 8.0f) return 0;
    return 1;
}

/* Rising crossings a second of y over [a, b) (hysteresis 0.02), counting only where mask (if given) is set
   at both samples. */
static float rate(const float *y, size_t a, size_t b, const unsigned char *mask)
{
    size_t i, len = 0;
    int armed = 0, n = 0;
    for (i = a; i < b; i++) {
        if (mask && !(mask[i] && (i == a || mask[i - 1]))) { armed = 0; continue; }
        len++;
        if (y[i] < -0.02f) armed = 1;
        else if (armed && y[i] > 0.02f) { n++; armed = 0; }
    }
    return len ? (float)n * SR / (float)len : 0.0f;
}

int main(void)
{
    float *x = malloc(N * sizeof *x), *y = malloc(N * sizeof *y), *z = malloc(N * sizeof *z);
    static const float CHORD[] = { 82.41f, 123.47f, 164.81f, 207.65f, 246.94f, 329.63f };
    FxParams p;
    size_t i, k;
    int n, m, mode, b;
    float r0, r1, lo, hi;
    if (!x || !y || !z) return 2;

    CHECK(PUREWHITEY_RING * 2 / 24000.0 >= 0.3, "the ring holds under 0.3 s");

    /* Mix 0: the dry input exactly; Dry 0 and Mix 0: silence */
    sig_noise(x, N, 9, 0.5f);
    for (mode = 0; mode < 8; mode++) {
        set(&p, mode, 0.3f, 0.5f, 1, 0.5f, 1, 0, 1); render(&p, x, y, N, 16);
        CHECK(memcmp(x, y, N * sizeof *x) == 0, "mode %d Mix 0: not the input", mode);
        set(&p, mode, 0.3f, 0.5f, 1, 0.5f, 0, 0, 1); render(&p, x, y, N, 16);
        for (n = 0, i = 0; i < N; i++) n += y[i] != 0.0f;
        CHECK(n == 0, "mode %d Dry 0 Mix 0: %d samples not silent", mode, n);
    }
    /* Dry 0 kills the dry: Trigger with no attack (a steady quiet note) is silent; Dry 1 gives the input */
    sig_sine(x, N, SR, 196.0f, 0.05f);
    set(&p, 3, 0.3f, 0.5f, 0, 1, 0, 1, 1); render(&p, x, y, N, 16);
    for (n = 0, i = 0; i < N; i++) n += y[i] != 0.0f;
    CHECK(n == 0, "Trigger, no attack, Dry 0: %d samples not silent", n);
    set(&p, 3, 0.3f, 0.5f, 0, 1, 1, 1, 1); render(&p, x, y, N, 16);
    CHECK(memcmp(x, y, N * sizeof *x) == 0, "Trigger, no attack, Dry 1: not the input");

    /* Repeat, Func 1 (for ever), Time 0.3 = 587 words: LISTEN for 2,348 samples, then the slice plays back
       what was heard, and loops every 2 x 1,173 = 2,346 samples for ever */
    sig_sine(x, N, SR, 200.0f, 0.5f);
    for (i = 30000; i < N; i++) x[i] = 0.0f;
    set(&p, 0, 0.3f, 1, 0.5f, 1, 0, 1, 1); render(&p, x, y, N, 16);
    for (lo = 0.0f, i = 100; i < 2200; i++) lo = fmaxf(lo, fabsf(y[2348 + i] - x[i]));
    CHECK(lo < 0.03f, "Repeat: the first pass is %.4f from what was heard", lo);
    for (lo = 0.0f, hi = 0.0f, i = 40000; i < 40000 + 3 * 2346; i++) {
        lo = fmaxf(lo, fabsf(y[i] - y[i + 2346]));
        hi = fmaxf(hi, fabsf(y[i]));
    }
    CHECK(lo < 1e-6f && hi > 0.4f, "Repeat: not a loop of 2,346 samples (%g apart, peak %g)", lo, hi);
    /* Func 0: two passes, then a new slice (of the silence that followed) */
    set(&p, 0, 0.3f, 0, 0.5f, 1, 0, 1, 1); render(&p, x, y, N, 16);
    for (hi = 0.0f, i = 40000; i < N; i++) hi = fmaxf(hi, fabsf(y[i]));
    CHECK(hi == 0.0f, "Repeat, Func 0: still looping the old slice (%g)", hi);

    /* Reverse x-1 on a rising ramp: the output falls through each pass */
    for (i = 0; i < N; i++) x[i] = -0.5f + (float)i / 48000.0f;
    set(&p, 2, 0.3f, 0.5f, 0.5f, 1, 0, 1, 1); render(&p, x, y, N, 16);
    for (n = 0, i = 2448; i < 4548; i++) n += y[i + 1] > y[i];
    CHECK(n == 0 && y[2448] - y[4548] > 0.03f, "Reverse: rising at %d samples, fell %g", n, y[2448] - y[4548]);
    set(&p, 2, 0.3f, 0, 0.5f, 1, 0, 1, 1); trace(&p, x, y, 20000);
    CHECK(speed[3000] == -0.25f, "Reverse Func 0: speed %g, not x-1/2", speed[3000]);
    set(&p, 2, 0.3f, 1, 0.5f, 1, 0, 1, 1); trace(&p, x, y, 20000);
    CHECK(speed[3000] == -1.0f, "Reverse Func 1: speed %g, not x-2", speed[3000]);

    /* Trigger: silent before the first attack; the attack's slice loops on through silence; a new attack
       takes a new slice */
    sig_silence(x, N);
    sig_sine(x + 20000, 28000, SR, 200.0f, 0.5f);
    sig_sine(x + 50000, N - 50000, SR, 500.0f, 0.8f);
    set(&p, 3, 0.3f, 0.5f, 0.5f, 1, 0, 1, 1); render(&p, x, y, N, 16);
    for (n = 0, i = 0; i < 20000; i++) n += y[i] != 0.0f;
    CHECK(n == 0, "Trigger: %d samples before the attack", n);
    r0 = rate(y, 30000, 48000, NULL);
    r1 = rate(y, 60000, N, NULL);
    for (hi = 0.0f, i = 48500; i < 49900; i++) hi = fmaxf(hi, fabsf(y[i]));
    CHECK(r0 > 170.0f && r0 < 230.0f, "Trigger: first slice at %g Hz, not 200", r0);
    CHECK(hi > 0.3f, "Trigger: the slice stopped when the input did (%g)", hi);
    CHECK(r1 > 430.0f && r1 < 570.0f, "Trigger: second slice at %g Hz, not 500", r1);
    set(&p, 4, 0.3f, 1, 0.5f, 1, 0, 1, 1); render(&p, x, y, N, 16);
    r0 = rate(y, 30000, 48000, NULL);
    for (n = 0, i = 0; i < 20000; i++) n += y[i] != 0.0f;
    CHECK(n == 0 && r0 > 85.0f && r0 < 115.0f, "Square Trigger Func 1: %g Hz, not 100 (%d early)", r0, n);

    /* Square: Func 0 at the note, Func 1 an octave below */
    sig_sine(x, N, SR, 220.0f, 0.5f);
    set(&p, 5, 0.6f, 0, 0.5f, 1, 0, 1, 1); render(&p, x, y, N, 16);
    r0 = rate(y, 5000, N, NULL);
    set(&p, 5, 0.6f, 1, 0.5f, 1, 0, 1, 1); render(&p, x, z, N, 16);
    r1 = rate(z, 5000, N, NULL);
    CHECK(r0 > 200.0f && r0 < 240.0f && r1 > 95.0f && r1 < 125.0f, "Square: Func 0 %g Hz, Func 1 %g Hz", r0, r1);
    for (hi = 0.0f, i = 5000; i < N; i++) hi = fmaxf(hi, fabsf(z[i]));
    CHECK(hi > 0.3f && hi <= 0.7f, "Square: peak %g", hi);

    /* Up and Down: the pitch rises (falls) pass by pass */
    sig_sine(x, N, SR, 300.0f, 0.5f);
    set(&p, 0, 0.5f, 0.5f, 0.5f, 1, 0, 1, 1); trace(&p, x, y, N);
    r0 = rate(y, 0, N, play);
    set(&p, 6, 0.5f, 0.5f, 0.5f, 1, 0, 1, 1); trace(&p, x, y, N);
    r1 = rate(y, 0, N, play);
    for (hi = 0.0f, i = 0; i < N; i++) if (play[i]) hi = fmaxf(hi, speed[i]);
    CHECK(r0 > 270.0f && r0 < 330.0f, "Repeat: plays at %g Hz, not 300", r0);
    CHECK(r1 > 1.4f * r0 && hi > 1.5f && hi <= 2.0f, "Up: %g Hz (Repeat %g), top speed %g", r1, r0, hi);
    set(&p, 7, 0.5f, 0.5f, 0.5f, 1, 0, 1, 1); trace(&p, x, y, N);
    r1 = rate(y, 0, N, play);
    for (lo = 1.0f, i = 0; i < N; i++) if (play[i]) lo = fminf(lo, speed[i]);
    CHECK(r1 < 0.8f * r0 && lo < 0.3f && lo > 0.0f, "Down: %g Hz (Repeat %g), lowest speed %g", r1, r0, lo);

    /* Random: lengths vary up to Time's, x2 at Func 1 only; Time 1: random lengths up to the whole ring */
    sig_chord(x, N, SR, CHORD, 6, 960, 1.6f);
    set(&p, 1, 0.5f, 0, 0.5f, 1, 0, 1, 1); trace(&p, x, y, N);
    for (n = 0, m = 0, lo = 1.0f, hi = 0.0f, i = 1; i < N; i++) {
        if (plens[i] && plens[i] != plens[i - 1]) { n++; m += plens[i] > 1204 || plens[i] < PUREWHITEY_LMIN; }
        if (play[i]) { lo = fminf(lo, speed[i]); hi = fmaxf(hi, speed[i]); }
    }
    CHECK(n >= 5 && m == 0 && lo == 0.5f && hi == 0.5f, "Random Func 0: %d lengths, %d out of range, speeds %g..%g", n, m, lo, hi);
    set(&p, 1, 0.5f, 1, 0.5f, 1, 0, 1, 1); trace(&p, x, y, N);
    for (lo = 1.0f, i = 0; i < N; i++) if (play[i]) lo = fminf(lo, speed[i]);
    CHECK(lo == 1.0f, "Random Func 1: not always x2 (%g)", lo);
    set(&p, 2, 1, 1, 0.5f, 1, 0, 1, 1); trace(&p, x, y, N);
    for (n = 0, k = 0, i = 1; i < N; i++)
        if (plens[i] && plens[i] != plens[i - 1]) { n++; k += plens[i] > 2048; }
    CHECK(n >= 3 && k >= 1, "Time 1: %d lengths, %zu over half the ring", n, k);

    /* only recorded samples are read: a ring of garbage after reset changes nothing */
    for (mode = 0; mode < 8; mode++) {
        set(&p, mode, mode & 1 ? 1.0f : 0.7f, 0.6f, 0.8f, 0.7f, 0.5f, 1, 1);
        render(&p, x, y, N, 16);
        fx_purewhitey.reset(&st, SR);
        for (i = 0; i < PUREWHITEY_RING; i++) st.ring[i] = 0x7FFF8001u ^ (uint32_t)(i * 2654435761u);
        for (i = 0; i < N; i += 16) fx_purewhitey.process(&st, &p, x + i, z + i, 16);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "mode %d: read the ring before recording it", mode);
    }

    /* any block size gives the same output; two interleaved instances as each alone */
    set(&p, 1, 1, 0.7f, 0.6f, 0.6f, 0.8f, 0.9f, 0.9f);
    render(&p, x, y, N, 16);
    for (b = 1; b <= 97; b += 48) {
        render(&p, x, z, N, (size_t)b);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "block size %d differs from 16", b);
    }
    CHECK(bounded(y, N) && memcmp(x, y, N * sizeof *x) != 0, "chord: not bounded, or the input");
    {
        FxParams q;
        float junk[16];
        set(&q, 6, 0.4f, 0.8f, 0.6f, 0.4f, 1, 0.5f, 0.7f);
        fx_purewhitey.reset(&st, SR);
        fx_purewhitey.reset(&st2, SR);
        for (i = 0; i < N; i += 16) {
            fx_purewhitey.process(&st, &p, x + i, z + i, 16);
            fx_purewhitey.process(&st2, &q, x + i, junk, 16);
        }
        render(&p, x, y, N, 16);
        fx_purewhitey.reset(&st, SR);
        for (i = 0; i < N; i += 16) fx_purewhitey.process(&st, &p, x + i, z + i, 16);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "interleaved instances differ");
    }

    /* hostile input and parameters stay finite and bounded */
    sig_noise(x, N, 4, 4.0f);
    x[100] = NAN; x[200] = INFINITY; x[300] = -1e30f;
    for (mode = 0; mode < 8; mode++) {
        set(&p, mode, 9, 9, 9, 9, 9, 9, 9); p.value[W_MODE] = (float)mode;
        render(&p, x, y, N, 16);
        CHECK(bounded(y, N), "mode %d hostile input: output not finite and bounded", mode);
    }
    set(&p, 99, 1e30f, 1e9f, 9, 9, 9, 9, 9); render(&p, x, y, N, 16);
    CHECK(bounded(y, N), "hostile high parameters: output not finite and bounded");
    set(&p, -9, -9, -9, -9, -9, -9, -9, -9); render(&p, x, y, N, 16);
    CHECK(bounded(y, N), "hostile low parameters: output not finite and bounded");
    set(&p, 0, NAN, NAN, NAN, NAN, NAN, NAN, NAN); p.value[W_MODE] = NAN; render(&p, x, y, N, 16);
    CHECK(bounded(y, N), "NaN parameters: output not finite and bounded");

    printf("%d checks, %d failures\n", checks, failures);
    free(x); free(y); free(z);
    return failures ? 1 : 0;
}
