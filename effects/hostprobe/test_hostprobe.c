/* test_hostprobe.c - the probe's frames decode to what it measured and what the host gave it. */
#include "hostprobe.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

#define FRAME (HOSTPROBE_NSYM * HOSTPROBE_SYM)

static void run(void *st, float mode, float level, const float *in, float *out, size_t n)
{
    FxParams p;
    fx_defaults(&fx_hostprobe, &p);
    p.value[HP_MODE] = mode;
    p.value[HP_LEVEL] = level;
    for (size_t b = 0; b < n; b += 16)
        fx_hostprobe.process(st, &p, in + b, out + b, 16);
}

/* The frame in out[0 .. FRAME): each symbol's tone found by correlating with the three tones; the bits put back. */
static int decode(const float *y, float level, uint32_t *words)
{
    memset(words, 0, 4 * HOSTPROBE_NWORDS);
    for (int s = 0; s < HOSTPROBE_NSYM; s++) {
        const float *x = y + s * HOSTPROBE_SYM;
        double e[4] = { 0 };
        for (int i = 0; i < HOSTPROBE_SYM; i++)
            e[0] += fabs(x[i]);
        int best = 0;
        double bm = 0;
        for (int t = 1; t <= 3; t++) {
            double c = 0, q = 0;
            int step = t == 1 ? 2 : t == 2 ? 4 : 6;
            for (int i = 0; i < HOSTPROBE_SYM; i++) {
                c += x[i] * sin(6.283185307179586 * step * i / 48.0);
                q += x[i] * cos(6.283185307179586 * step * i / 48.0);
            }
            e[t] = c * c + q * q;
            if (e[t] > bm) { bm = e[t]; best = t; }
        }
        int want = s < HOSTPROBE_NPILOT ? 3 : s < HOSTPROBE_NPILOT + HOSTPROBE_NBITS ? -1 : 0;
        if (want == 0) {
            if (e[0] != 0) return printf("  symbol %d: not silent\n", s), 0;
        } else if (want == 3) {
            if (best != 3) return printf("  symbol %d: not the pilot\n", s), 0;
        } else {
            if (best != 1 && best != 2) return printf("  symbol %d: no bit\n", s), 0;
            int b = s - HOSTPROBE_NPILOT;
            if (best == 2) words[b >> 5] |= 1u << (31 - (b & 31));
        }
        for (int i = 0; i < HOSTPROBE_SYM; i++)
            if (fabsf(x[i]) > level * 1.0001f) return printf("  symbol %d: above Level\n", s), 0;
    }
    return 1;
}

static float u2f(uint32_t u)
{
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

int main(void)
{
    void *st = malloc(fx_hostprobe.state_bytes);
    size_t n = (size_t)FRAME * 3 + 16 * HOSTPROBE_WIN_CALLS;
    n = (n + 15) & ~(size_t)15;
    float *in = malloc(n * sizeof *in), *out = malloc(n * sizeof *out);
    const double amp = 0.3, f0 = 200.0;
    for (size_t i = 0; i < n; i++)
        in[i] = (float)(amp * sin(6.283185307179586 * f0 * (double)i / 48000.0) + 0.001);

    /* a block of the size asked for */
    uint32_t entry[4] = { 0x11, 0x22, 0xb7010, 0x44 }, inst[16];
    for (int k = 0; k < 16; k++) inst[k] = 0x1000u + (uint32_t)k;
    inst[6] = 0x300000;
    inst[7] = 0x300000 + HOSTPROBE_SDR_REQ;
    fx_hostprobe.reset(st, 48000.0f);
    hostprobe_set_host(st, entry, inst);
    run(st, 0, 0.25f, in, out, n);

    uint32_t w[HOSTPROBE_NWORDS];
    CHECK(decode(out, 0.25f, w), "frame 0 decodes");
    CHECK(w[0] == HOSTPROBE_SYNC && w[1] == HOSTPROBE_MAGIC && w[2] == 0 && w[3] == 1, "frame 0 header %08x %08x %u %u", w[0], w[1], w[2], w[3]);
    CHECK(w[7] == 0 && w[4] == 0, "frame 0 has no window yet");
    CHECK(w[8] == 1 && w[9] == 0, "memory test written: %u %u", w[8], w[9]);
    CHECK(w[10] == 0x11 && w[12] == 0xb7010 && w[14] == 0x1000 && w[20] == 0x300000 && w[21] == 0x310000, "host words");
    CHECK(w[30] == 0 && w[31] == 48000 && w[32] == 0, "idle words (none set) and the window");
    uint32_t sum = 0;
    for (int k = 1; k <= 32; k++) sum += w[k];
    CHECK(w[33] == sum, "checksum");

    /* frame 2 starts after the first window: its meter values against the signal's own */
    CHECK(decode(out + 2 * FRAME, 0.25f, w), "frame 2 decodes");
    CHECK(w[2] == 2 && w[3] == 2 * FRAME / 16 + 1, "frame 2 counts %u %u", w[2], w[3]);
    CHECK(w[7] >= 1, "a window completed (%u)", w[7]);
    {
        uint32_t lw = w[7];
        size_t a = (size_t)(lw - 1) * 48000, e = a + 48000;
        double pk = 0, sq = 0, sm = 0;
        for (size_t i = a; i < e; i++) {
            double x = in[i];
            if (fabs(x) > pk) pk = fabs(x);
            sq += x * x;
            sm += x;
        }
        CHECK(u2f(w[4]) == (float)pk, "peak %.9g, the window's %.9g", u2f(w[4]), pk);
        CHECK(fabs(u2f(w[5]) / sq - 1) < 2e-5, "sum of squares %.9g, the window's %.9g", u2f(w[5]), sq);
        CHECK(fabs(u2f(w[6]) - sm) < 1e-3, "sum %.9g, the window's %.9g", u2f(w[6]), sm);
        double rms = sqrt(u2f(w[5]) / 48000.0 - pow(u2f(w[6]) / 48000.0, 2));
        CHECK(fabs(20 * log10(rms / (amp / sqrt(2.0)))) < 0.001, "rms %.6f dB off", 20 * log10(rms / (amp / sqrt(2.0))));
        CHECK(w[8] == 1 && w[9] == 0, "memory test still good");
    }

    /* Pass: the input, exactly */
    fx_hostprobe.reset(st, 48000.0f);
    run(st, 1, 0.25f, in, out, 16 * 4000);
    CHECK(memcmp(in, out, 16 * 4000 * sizeof *in) == 0, "Pass sends the input");

    /* blocks the test must not touch */
    uint32_t bad[][2] = { { 0, 0 }, { 0x300000, 0x300000 + HOSTPROBE_SDR_REQ - 1 }, { 0x300000, 0x300000 + HOSTPROBE_SDR_REQ + 0x401 },
                          { 0x1000, 0x1000 + HOSTPROBE_SDR_REQ }, { 0xff8000, 0xff8000 + HOSTPROBE_SDR_REQ }, { 0x310000, 0x300000 } };
    for (size_t k = 0; k < sizeof bad / sizeof bad[0]; k++) {
        inst[6] = bad[k][0];
        inst[7] = bad[k][1];
        fx_hostprobe.reset(st, 48000.0f);
        hostprobe_set_host(st, entry, inst);
        run(st, 0, 0.5f, in, out, FRAME);
        CHECK(decode(out, 0.5f, w) && w[8] == 0 && w[9] == 0, "block %#x..%#x left alone", bad[k][0], bad[k][1]);
    }
    /* a block at the top of the range accepted */
    inst[6] = 0x300000;
    inst[7] = 0x300000 + HOSTPROBE_SDR_REQ + 0x400;
    fx_hostprobe.reset(st, 48000.0f);
    hostprobe_set_host(st, entry, inst);
    run(st, 0, 1.0f, in, out, FRAME);
    CHECK(decode(out, 1.0f, w) && w[8] == 1, "a block 0x400 larger is tested");

    /* the idle word: frame 1 reports the lowest value seen since frame 0 latched (word 30) and the value at its own
       start (word 32); the lowest is then reset */
    fx_hostprobe.reset(st, 48000.0f);
    hostprobe_set_host(st, entry, inst);
    hostprobe_set_idle(st, 0x500);
    run(st, 0, 0.25f, in, out, FRAME / 2);              /* frame 0 latches 0x500; then 0x500 */
    hostprobe_set_idle(st, 0x300);
    run(st, 0, 0.25f, in + FRAME / 2, out + FRAME / 2, 16 * 8);
    hostprobe_set_idle(st, 0x700);
    run(st, 0, 0.25f, in + FRAME / 2 + 128, out + FRAME / 2 + 128, FRAME + FRAME / 2 - 128);
    CHECK(decode(out, 0.25f, w) && w[30] == 0x500 && w[32] == 0x500, "frame 0 idle words %x %x", w[30], w[32]);
    CHECK(decode(out + FRAME, 0.25f, w) && w[30] == 0x300 && w[32] == 0x700, "frame 1 idle words %x %x", w[30], w[32]);

    /* Mode Load: frames of HOSTPROBE_LNSYM symbols of HOSTPROBE_LSYM samples, six words */
    {
        HostprobeState *hs = st;
        const size_t LF = (size_t)HOSTPROBE_LNSYM * HOSTPROBE_LSYM;
        fx_hostprobe.reset(st, 48000.0f);
        hostprobe_set_host(st, entry, inst);
        hostprobe_set_idle(st, 0x40);
        run(st, 2, 0.5f, in, out, 16 * 4);                  /* frame 0 latched at the first sample */
        CHECK(hs->fsym == HOSTPROBE_LSYM && hs->fnsym == HOSTPROBE_LNSYM && hs->frame[1] == HOSTPROBE_MAGIC_L &&
              hs->frame[3] == 0x40 && hs->frame[4] == 0x40 && hs->frame[5] == HOSTPROBE_MAGIC_L + 0x40 + 0x40,
              "load frame 0: %x %x %x %x", hs->frame[1], hs->frame[3], hs->frame[4], hs->frame[5]);
        hostprobe_set_idle(st, 0x20);
        run(st, 2, 0.5f, in, out, 16 * 4);
        hostprobe_set_idle(st, 0x90);
        run(st, 2, 0.5f, in, out, LF - 16 * 8);             /* to the end of frame 0 exactly */
        CHECK(hs->frames == 1 && hs->sidx == 0 && hs->spos == 0, "a load frame is %zu samples", LF);
        run(st, 2, 0.5f, in, out, 16);                      /* frame 1 latches */
        CHECK(hs->frame[2] == 1 && hs->frame[3] == 0x90 && hs->frame[4] == 0x20 &&
              hs->frame[5] == HOSTPROBE_MAGIC_L + 1 + 0x90 + 0x20, "load frame 1: %x %x %x", hs->frame[2], hs->frame[3], hs->frame[4]);
        float mx = 0.0f;
        for (size_t i = 0; i < 16; i++) mx = fmaxf(mx, fabsf(out[i]));
        CHECK(mx > 0.0f && mx <= 0.5f * 1.0001f, "load mode plays its tones at Level (%g)", (double)mx);
    }

    printf("hostprobe: %d checks, %d failures\n", checks, fails);
    free(st);
    free(in);
    free(out);
    return fails != 0;
}
