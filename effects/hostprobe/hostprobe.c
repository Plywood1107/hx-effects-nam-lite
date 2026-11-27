#include "hostprobe.h"

#include <math.h>
#include <string.h>

static const FxParamDesc PARAMS[HP_NPARAMS] = {
    { "time",  "Time",  FX_CONTINUOUS, 0.1f, 4.0f, 0.5f, "s (the host's synced Time; not used)", "immediate" },
    { "mode",  "Mode",  FX_INTEGER,    0.0f, 1.0f, 0.0f, "0 Report (the data burst), 1 Pass (the input)", "immediate" },
    { "level", "Level", FX_CONTINUOUS, 0.0f, 1.0f, 0.25f, "x: the burst's peak (shown as %)", "immediate" },
};

float hostprobe_sin(int k)
{
    return (float)sin(6.283185307179586 * (double)k / (double)HOSTPROBE_NSIN);
}

static uint32_t fbits(float x)
{
    uint32_t u;
    memcpy(&u, &x, sizeof u);
    return u;
}

static void reset(void *state, float sample_rate)
{
    HostprobeState *s = state;
    (void)sample_rate;
    memset(s, 0, sizeof *s);
    for (int k = 0; k < HOSTPROBE_NSIN; k++)
        s->sintab[k] = hostprobe_sin(k);
}

void hostprobe_set_host(void *state, const uint32_t *entry4, const uint32_t *inst16)
{
    HostprobeState *s = state;
    memcpy(s->entry, entry4, sizeof s->entry);
    memcpy(s->inst, inst16, sizeof s->inst);
}

/* The memory test, then the frame: 0 sync, 1 magic, 2 frames sent, 3 calls, 4..6 the last window's peak, sum of
   squares and sum (float bits), 7 windows completed, 8 memory test state, 9 mismatches, 10..13 DM(0..3, I3),
   14..29 the instance struct's words 0..15, 30 the SDRAM words asked for, 31 samples a window, 32 0, 33 the sum of
   words 1..32. */
static void latch(HostprobeState *s)
{
    uint32_t a = s->inst[6], e = s->inst[7], n = e - a;
    if (a >= 0x200000u && e <= 0x1000000u && n >= HOSTPROBE_SDR_REQ && n <= HOSTPROBE_SDR_REQ + 0x400u) {
        if (s->mstat && (s->mem[0] != HOSTPROBE_PAT_A || s->mem[1] != HOSTPROBE_PAT_B))
            s->mbad++;
        s->mstat = 1;
        s->mem[0] = HOSTPROBE_PAT_A;
        s->mem[1] = HOSTPROBE_PAT_B;
    }
    uint32_t *f = s->frame;
    f[0] = HOSTPROBE_SYNC;
    f[1] = HOSTPROBE_MAGIC;
    f[2] = s->frames;
    f[3] = s->calls;
    f[4] = fbits(s->lpeak);
    f[5] = fbits(s->lsq);
    f[6] = fbits(s->lsum);
    f[7] = s->lwin;
    f[8] = s->mstat;
    f[9] = s->mbad;
    for (int k = 0; k < 4; k++)
        f[10 + k] = s->entry[k];
    for (int k = 0; k < 16; k++)
        f[14 + k] = s->inst[k];
    f[30] = HOSTPROBE_SDR_REQ;
    f[31] = 16u * HOSTPROBE_WIN_CALLS;
    f[32] = 0;
    uint32_t sum = 0;
    for (int k = 1; k <= 32; k++)
        sum += f[k];
    f[33] = sum;
}

static void process(void *state, const FxParams *p, const float *in, float *out, size_t frames)
{
    HostprobeState *s = state;
    int mode = (int)fx_param_clamp(&PARAMS[HP_MODE], p->value[HP_MODE]);
    float level = fx_param_clamp(&PARAMS[HP_LEVEL], p->value[HP_LEVEL]);
    for (size_t b = 0; b < frames; b += FX_DEVICE_BLOCK) {
        size_t nb = frames - b < FX_DEVICE_BLOCK ? frames - b : FX_DEVICE_BLOCK;
        const float *x = in + b;
        float *y = out + b;
        s->calls++;
        float csq = 0.0f, csum = 0.0f;
        for (size_t k = 0; k < nb; k++) {
            float a = fabsf(x[k]);
            if (a > s->peak)
                s->peak = a;
            csq = csq + x[k] * x[k];
            csum = csum + x[k];
        }
        s->sq = s->sq + csq;
        s->sum = s->sum + csum;
        if (++s->wcalls >= HOSTPROBE_WIN_CALLS) {
            s->lpeak = s->peak;
            s->lsq = s->sq;
            s->lsum = s->sum;
            s->lwin = ++s->win;
            s->peak = s->sq = s->sum = 0.0f;
            s->wcalls = 0;
        }
        for (size_t k = 0; k < nb; k++) {
            float xin = x[k];
            if (s->spos == 0) {
                if (s->sidx == 0)
                    latch(s);
                if (s->sidx < HOSTPROBE_NPILOT) {
                    s->step = 6;
                } else if (s->sidx < HOSTPROBE_NPILOT + HOSTPROBE_NBITS) {
                    int bit = s->sidx - HOSTPROBE_NPILOT;
                    uint32_t w = s->frame[bit >> 5];
                    s->step = (int)(((w >> (31 - (bit & 31))) & 1u) + 1u) * 2;
                } else {
                    s->step = 0;
                }
            }
            float v = s->step ? s->sintab[s->ph] * level : 0.0f;
            s->ph += s->step;
            if (s->ph >= HOSTPROBE_NSIN)
                s->ph -= HOSTPROBE_NSIN;
            if (++s->spos >= HOSTPROBE_SYM) {
                s->spos = 0;
                if (++s->sidx >= HOSTPROBE_NSYM) {
                    s->sidx = 0;
                    s->frames++;
                }
            }
            y[k] = mode ? xin : v;
        }
    }
}

const FxAlgorithm fx_hostprobe = {
    "hostprobe", "Probe", sizeof(HostprobeState), PARAMS, HP_NPARAMS, reset, process,
};
