/* test_drumchapel - Drum Chapel's reference tests (no hardware, no files). */
#include "drumchapel.h"
#include "../metronome/metronome.h"
#include "../common/signals.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SR 48000.0f
#define N  ((size_t)(4 * 48000))

static int failures, checks;

#define CHECK(cond, ...) do { checks++; if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void set(FxParams *p, float time, int pattern, int kit, float kick, float snare, float hat, float swing, float level)
{
    memset(p, 0, sizeof *p);
    p->value[DC_TIME] = time; p->value[DC_PATTERN] = (float)pattern; p->value[DC_KIT] = (float)kit;
    p->value[DC_KICK] = kick; p->value[DC_SNARE] = snare; p->value[DC_HAT] = hat;
    p->value[DC_SWING] = swing; p->value[DC_LEVEL] = level;
}

static void render(DrumChapelState *s, const FxParams *p, const float *in, float *out, size_t n, size_t block)
{
    size_t i;
    fx_drumchapel.reset(s, SR);
    for (i = 0; i < n; i += block)
        fx_drumchapel.process(s, p, in + i, out + i, n - i < block ? n - i : block);
}

static double rms(const float *x, size_t n)
{
    double e = 0;
    size_t i;
    for (i = 0; i < n; i++) e += (double)x[i] * x[i];
    return n ? sqrt(e / (double)n) : 0.0;
}

static double peak(const float *x, size_t n)
{
    double m = 0;
    size_t i;
    for (i = 0; i < n; i++) if (fabs(x[i]) > m) m = fabs(x[i]);
    return m;
}

static double zcr(const float *x, size_t n)               /* sign changes a sample */
{
    size_t i, c = 0;
    for (i = 1; i < n; i++) if ((x[i] < 0.0f) != (x[i - 1] < 0.0f)) c++;
    return n > 1 ? (double)c / (double)(n - 1) : 0.0;
}

static double bright(const float *x, size_t n)            /* rms of the first difference / rms: a centroid proxy */
{
    double e = 0, d = 0;
    size_t i;
    for (i = 1; i < n; i++) { e += (double)x[i] * x[i]; d += (double)(x[i] - x[i - 1]) * (x[i] - x[i - 1]); }
    return e > 0 ? sqrt(d / e) : 0.0;
}

#define MS(t) ((size_t)((t) * 48))

/* The samples at which steps fire, n samples at block size 1. */
static size_t fire_times(const FxParams *p, uint32_t *t, uint32_t *stepv, size_t max, size_t n)
{
    static float in[1], out[1];
    DrumChapelState s;
    size_t i, k = 0;
    fx_drumchapel.reset(&s, SR);
    for (i = 0; i < n; i++) {
        uint32_t f = s.fires;
        fx_drumchapel.process(&s, p, in, out, 1);
        if (s.fires != f && k < max) { t[k] = (uint32_t)i; stepv[k] = s.last_step; k++; }
    }
    return k;
}

int main(void)
{
    float *x = calloc(N, sizeof *x), *y = malloc(N * sizeof *y), *z = malloc(N * sizeof *z);
    static uint32_t ta[20000], sa[20000], tb[20000], sb[20000];
    DrumChapelState s, s2;
    FxParams p, q;
    size_t i, n, k;
    int kit, pat, v, bad;
    double feat[DRUMCHAPEL_KITS][4];
    if (!x || !y || !z) return 2;

    /* patterns: names short, step words as the tables say */
    for (pat = 0; pat < DRUMCHAPEL_PATTERNS; pat++)
        CHECK(strlen(drumchapel_pattern_name(pat)) <= 10, "pattern name %s", drumchapel_pattern_name(pat));
    CHECK(drumchapel_pattern_ks(0) == (0x0501u | 0x1010u << 16) && drumchapel_pattern_hat(0) == 0x5555u,
          "Rock is %#x / %#x", drumchapel_pattern_ks(0), drumchapel_pattern_hat(0));

    /* 1. timing exactly Click's at four sixteenths a beat: the same samples, for ten minutes, at five tempos */
    {
        static const float times[] = { 3.0f, 1.0f, 0.5f, 0.4379562f, 0.2f, 0.1f };
        const size_t L = (size_t)(600 * 48000);
        static float b1[16], b2[16];
        for (k = 0; k < sizeof times / sizeof times[0]; k++) {
            MetronomeState m;
            FxParams mp;
            uint32_t inc = click_bpm100(times[k]) * 4u, ticks = 0;
            size_t mism = 0, late = 0;
            memset(&mp, 0, sizeof mp);
            mp.value[M_TIME] = times[k]; mp.value[M_METER] = 4; mp.value[M_ACCENT] = 0; mp.value[M_SOUND] = 0;
            mp.value[M_LEVEL] = 0.5f; mp.value[M_SUBDIV] = 4;
            set(&p, times[k], 0, 0, 1, 1, 1, 0, 0.5f);
            fx_metronome.reset(&m, SR);
            fx_drumchapel.reset(&s, SR);
            for (i = 0; i < L; i += 16) {
                size_t j;
                for (j = 0; j < 16; j++) {      /* one sample at a time: when each tick and step falls */
                    uint32_t a = m.ticks, b = s.fires;
                    fx_metronome.process(&m, &mp, b1 + j, b2 + j, 1);
                    fx_drumchapel.process(&s, &p, b1 + j, b2 + j, 1);
                    if ((m.ticks != a) != (s.fires != b)) mism++;
                    if (s.fires != b) {
                        /* step f at the first sample n with n x inc >= f x period */
                        uint64_t f = s.fires - 1, nn = i + j;
                        if (!(nn * inc >= f * DRUMCHAPEL_PERIOD && (nn == 0 || (nn - 1) * inc < f * DRUMCHAPEL_PERIOD))) late++;
                        if ((s.fires - 1) % 16u != s.last_step) late++;
                        ticks++;
                    }
                }
            }
            CHECK(mism == 0 && late == 0 && ticks == m.ticks && ticks >= 800,
                  "Time %g: %zu samples differ from Click, %zu misplaced, %u steps, Click %u ticks", times[k], mism, late, ticks, m.ticks);
        }
    }

    /* 2. every pattern's hits land on its steps: two bars, each voice's hits counted per step */
    for (pat = 0; pat < DRUMCHAPEL_PATTERNS; pat++) {
        uint32_t ks = drumchapel_pattern_ks(pat), hw = drumchapel_pattern_hat(pat), m[3];
        static float in1[1], out1[1];
        int wrong = 0;
        m[KICK] = ks & 0xFFFFu; m[SNARE] = ks >> 16; m[HAT] = hw;
        set(&p, 0.25f, pat, 0, 1, 1, 1, 0, 0.5f);
        fx_drumchapel.reset(&s, SR);
        for (i = 0; i < 2 * 16 * 3000; i++) {
            uint32_t f = s.fires, h[3];
            for (v = 0; v < 3; v++) h[v] = s.hits[v];
            fx_drumchapel.process(&s, &p, in1, out1, 1);
            if (s.fires != f) {
                if (s.last_step != (uint32_t)((s.fires - 1) % 16)) wrong++;
                for (v = 0; v < 3; v++)
                    if ((s.hits[v] != h[v]) != (int)(m[v] >> s.last_step & 1u)) wrong++;
            } else {
                for (v = 0; v < 3; v++) if (s.hits[v] != h[v]) wrong++;
            }
        }
        CHECK(wrong == 0 && s.fires == 32, "pattern %s: %d wrong, %u steps", drumchapel_pattern_name(pat), wrong, s.fires);
    }
    /* the first sample is step 0 of the bar, and the kick sounds there */
    set(&p, 0.5f, 0, 0, 1, 1, 1, 0, 1); render(&s, &p, x, y, 4800, 16);
    CHECK(s.hits[KICK] == 1 && peak(y, 480) > 0.2, "downbeat: %u kicks, peak %g", s.hits[KICK], peak(y, 480));

    /* 3. swing: odd sixteenths move by Swing x 1/3 of a sixteenth, even ones stay */
    set(&p, 0.5f, 0, 0, 1, 1, 1, 0, 0.5f); q = p; q.value[DC_SWING] = 1.0f;
    n = fire_times(&p, ta, sa, 64, 48000 * 8);
    k = fire_times(&q, tb, sb, 64, 48000 * 8);
    bad = n != k || n < 60;
    for (i = 0; i < n && i < k; i++) {
        double d = (double)tb[i] - (double)ta[i], want = (sa[i] & 1u) ? 6000.0 / 3.0 : 0.0;   /* a sixteenth is 6000 samples */
        if (sa[i] != sb[i] || fabs(d - want) > 1.0) bad++;
    }
    CHECK(!bad, "swing 1: %zu / %zu steps, %d wrong", n, k, bad);
    q.value[DC_SWING] = 0.5f;
    k = fire_times(&q, tb, sb, 64, 48000 * 8);
    CHECK(k == n && tb[1] - ta[1] >= 999 && tb[1] - ta[1] <= 1001 && tb[2] == ta[2], "swing 0.5 moves step 1 by %d", (int)(tb[1] - ta[1]));

    /* 4. the guitar passes at exactly unity: Level 0, or every voice at 0 */
    sig_noise(x, N, 9, 0.5f);
    set(&p, 0.3f, 6, 4, 1, 1, 1, 0.3f, 0); render(&s, &p, x, y, N, 16);
    CHECK(memcmp(x, y, N * sizeof *x) == 0, "Level 0: not the input");
    set(&p, 0.3f, 6, 4, 0, 0, 0, 0.3f, 1); render(&s, &p, x, y, N, 16);
    CHECK(memcmp(x, y, N * sizeof *x) == 0, "voices at 0: not the input");
    /* and the drums do not depend on it */
    set(&p, 0.3f, 6, 1, 1, 1, 1, 0.3f, 1); render(&s, &p, x, y, N, 16);
    memset(z, 0, N * sizeof *z);
    {
        float *w = malloc(N * sizeof *w);
        if (!w) return 2;
        render(&s, &p, z, w, N, 16);
        for (i = 0, bad = 0; i < N; i++) if (fabsf((y[i] - x[i]) - w[i]) > 1e-6f) bad++;
        CHECK(bad == 0, "the drums depend on the input in %d samples", bad);
        free(w);
    }
    memset(x, 0, N * sizeof *x);

    /* 5. the kits: each different, Doom the lowest and the most saturated */
    for (kit = 0; kit < DRUMCHAPEL_KITS; kit++) {
        set(&p, 0.5f, 0, kit, 0.8f, 0.7f, 0.5f, 0, 1); render(&s, &p, x, y, 96000, 16);
        feat[kit][0] = rms(y, 96000);
        feat[kit][1] = peak(y, 96000) / feat[kit][0];                    /* crest factor */
        feat[kit][2] = bright(y, 96000);
        set(&p, 1.0f, 18, kit, 1, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);   /* one kick */
        feat[kit][3] = zcr(y + MS(60), MS(300)) * 48000.0 / 2.0;               /* its pitch, Hz */
        printf("  %-6s rms %.3f crest %.2f bright %.3f kick %.1f Hz\n", drumchapel_kit_name(kit),
               feat[kit][0], feat[kit][1], feat[kit][2], feat[kit][3]);
    }
    for (kit = 0; kit < DRUMCHAPEL_KITS; kit++) {
        int other;
        set(&p, 0.5f, 0, kit, 0.8f, 0.7f, 0.5f, 0, 1); render(&s, &p, x, y, 96000, 16);
        for (other = kit + 1; other < DRUMCHAPEL_KITS; other++) {
            double e = 0;
            set(&q, 0.5f, 0, other, 0.8f, 0.7f, 0.5f, 0, 1); render(&s2, &q, x, z, 96000, 16);
            for (i = 0; i < 96000; i++) e += (double)(y[i] - z[i]) * (y[i] - z[i]);
            e = sqrt(e / 96000.0);
            CHECK(e > 0.3 * (feat[kit][0] < feat[other][0] ? feat[kit][0] : feat[other][0]),
                  "%s and %s sound alike (difference rms %g)", drumchapel_kit_name(kit), drumchapel_kit_name(other), e);
        }
        if (kit != KIT_DOOM) {
            CHECK(feat[KIT_DOOM][3] < feat[kit][3] - 10.0, "Doom's kick (%g Hz) not under %s's (%g Hz)",
                  feat[KIT_DOOM][3], drumchapel_kit_name(kit), feat[kit][3]);
            CHECK(feat[KIT_DOOM][1] < 0.8 * feat[kit][1], "Doom's crest factor %g not under %s's %g",
                  feat[KIT_DOOM][1], drumchapel_kit_name(kit), feat[kit][1]);
        }
        CHECK(feat[kit][0] > 0.05 && feat[kit][0] < 0.6, "%s: rms %g", drumchapel_kit_name(kit), feat[kit][0]);
    }
    CHECK(feat[KIT_DOOM][3] < 40.0, "Doom's kick at %g Hz", feat[KIT_DOOM][3]);
    CHECK(feat[KIT_DOOM][0] < 3.0 * feat[KIT_BOOM][0], "Doom not level-compensated: rms %g against Boom's %g",
          feat[KIT_DOOM][0], feat[KIT_BOOM][0]);
    /* Boom's kick rings longer than Punch's and Tick's */
    {
        double tail[DRUMCHAPEL_KITS];
        for (kit = 0; kit < DRUMCHAPEL_KITS; kit++) {
            set(&p, 1.0f, 18, kit, 1, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);
            tail[kit] = rms(y + MS(300), MS(200)) / rms(y, MS(50));
        }
        CHECK(tail[KIT_BOOM] > 2.0 * tail[KIT_PUNCH] && tail[KIT_BOOM] > 2.0 * tail[KIT_TICK],
              "kick tails: Boom %g, Punch %g, Tick %g", tail[KIT_BOOM], tail[KIT_PUNCH], tail[KIT_TICK]);
    }
    /* hats: Bit's is held noise, Doom's is dark, Tick's and Punch's bright */
    {
        double zc[DRUMCHAPEL_KITS], br[DRUMCHAPEL_KITS];
        for (kit = 0; kit < DRUMCHAPEL_KITS; kit++) {
            set(&p, 1.0f, 17, kit, 0, 0, 1, 0, 1); render(&s, &p, x, y, 48000, 16);
            zc[kit] = zcr(y, MS(15));
            br[kit] = bright(y, MS(15));
        }
        CHECK(zc[KIT_BIT] < 0.15 && zc[KIT_PUNCH] > 0.4, "hat sign changes: Bit %g, Punch %g", zc[KIT_BIT], zc[KIT_PUNCH]);
        CHECK(br[KIT_DOOM] < 0.6 * br[KIT_TICK] && br[KIT_DOOM] < 0.6 * br[KIT_PUNCH], "hat brightness: Doom %g, Tick %g, Punch %g",
              br[KIT_DOOM], br[KIT_TICK], br[KIT_PUNCH]);
    }
    /* Eighty's snare tail is cut at 150 ms; Boom's dies away */
    {
        double cut[2];
        int ks[2] = { KIT_EIGHTY, KIT_BOOM };
        for (k = 0; k < 2; k++) {
            set(&p, 1.0f, 10, ks[k], 0, 1, 0, 0, 1); render(&s, &p, x, y, 3 * 48000, 16);   /* One Drop: snare on step 8 */
            n = 8 * 12000;                                                                 /* step 8 at Time 1 s */
            cut[k] = rms(y + n + MS(170), MS(80)) / rms(y + n + MS(100), MS(40));
        }
        CHECK(cut[0] < 0.25, "Eighty's snare tail goes on: %g", cut[0]);
        printf("  snare tail after 170 ms / at 100 ms: Eighty %.3f, Boom %.3f\n", cut[0], cut[1]);
    }

    /* 6. any block size gives the same output; two interleaved instances equal each alone */
    sig_noise(x, N, 3, 0.3f);
    set(&p, 0.37f, 7, 5, 0.9f, 0.6f, 0.7f, 0.4f, 0.8f);
    render(&s, &p, x, y, N, 16);
    for (k = 1; k <= 4096; k = k == 1 ? 37 : k == 37 ? 4096 : 9999) {
        render(&s, &p, x, z, N, k);
        CHECK(memcmp(y, z, N * sizeof *y) == 0, "block size %zu differs from 16", k);
    }
    set(&q, 0.21f, 12, 3, 1, 1, 1, 1, 1);
    {
        float *w = malloc(N * sizeof *w), *u = malloc(N * sizeof *u);
        if (!w || !u) return 2;
        render(&s2, &q, x, w, N, 16);
        fx_drumchapel.reset(&s, SR); fx_drumchapel.reset(&s2, SR);
        for (i = 0; i < N; i += 16) {
            fx_drumchapel.process(&s, &p, x + i, z + i, 16);
            fx_drumchapel.process(&s2, &q, x + i, u + i, 16);
        }
        CHECK(memcmp(y, z, N * sizeof *y) == 0 && memcmp(w, u, N * sizeof *w) == 0, "interleaved instances differ");
        free(w); free(u);
    }

    /* 7. hostile input and knobs: finite, and the drums bounded */
    sig_noise(x, N, 4, 4.0f);
    x[100] = NAN; x[200] = INFINITY; x[300] = -INFINITY; x[400] = 1e30f;
    for (kit = -1; kit < 3; kit++) {
        float hv = kit == -1 ? 1e9f : kit == 0 ? -1e9f : kit == 1 ? NAN : 0.5f;
        set(&p, hv, (int)hv, (int)hv, hv, hv, hv, hv, hv);
        if (kit == 1) for (i = 0; i < 8; i++) p.value[i] = NAN;
        render(&s, &p, x, y, N, 16);
        for (i = 0, bad = 0; i < N; i++) {
            float in = isfinite(x[i]) ? x[i] : 0.0f;
            if (!isfinite(y[i]) || fabsf(y[i] - in) > 1.5f) bad++;
        }
        CHECK(bad == 0, "hostile case %d: %d bad samples", kit, bad);
    }
    /* every knob moving at random every 10 ms, through every kit */
    {
        unsigned r = 12345;
        fx_drumchapel.reset(&s, SR);
        for (i = 0, bad = 0; i < N; i += 16) {
            if (i % 480 == 0) {
                for (k = 0; k < 8; k++) { r = r * 1103515245u + 12345u; p.value[k] = (float)(r >> 8) / 16777216.0f * 1.4f - 0.2f; }
                p.value[DC_TIME] = 0.05f + p.value[DC_TIME] * 3.0f;
                p.value[DC_PATTERN] *= 20.0f; p.value[DC_KIT] *= 6.0f;
            }
            fx_drumchapel.process(&s, &p, x + i, y + i, 16);
            for (k = 0; k < 16; k++) {
                float in = isfinite(x[i + k]) ? x[i + k] : 0.0f;
                if (!isfinite(y[i + k]) || fabsf(y[i + k] - in) > 1.5f) bad++;
            }
        }
        CHECK(bad == 0, "moving knobs: %d bad samples", bad);
    }

    printf("%d checks, %d failures\n", checks, failures);
    free(x); free(y); free(z);
    return failures ? 1 : 0;
}
