/* render_formats.c - the Acoustic kit's kick and snare as they would play in each sample format (formats_demo.py
 * writes the encoded samples into out/dc_formats.h and runs this). For each of 16-bit 48 kHz (the kit now), 8-bit
 * mu-law 48 kHz and 8-bit mu-law 24 kHz (interpolated to 48 kHz, as the kernel would play it): each hit alone and
 * a two-bar beat at 120 BPM, as .wav files; and each format's error against the 16-bit sample. */
#include "drumchapel.h"
#include "../common/wav.h"
#include "../out/dc_formats.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STEP 6000                              /* a sixteenth at 120 BPM, 48 kHz */
#define BEAT_N (STEP * 32 + 24000)

typedef struct { const char *name; float *s; uint32_t n; } Hit;

/* the hit at 48 kHz in format f: 0 the 16-bit table, 1 mu-law 48 kHz, 2 mu-law 24 kHz interpolated */
static Hit play(int voice, int f)
{
    uint32_t n0 = drumchapel_sample_len(voice), first = drumchapel_sample_first(voice);
    Hit h = { 0, malloc((n0 + 2) * sizeof(float)), n0 };
    if (f == 0) {
        for (uint32_t i = 0; i < n0; i++) h.s[i] = drumchapel_sample(first + i);
    } else if (f == 1) {
        const unsigned char *u = voice == 0 ? U48_KICK : U48_SNARE;
        for (uint32_t i = 0; i < n0; i++) h.s[i] = drumchapel_ulaw(u[i]);
    } else {
        const unsigned char *u = voice == 0 ? U24_KICK : U24_SNARE;
        uint32_t n24 = voice == 0 ? U24_KICK_N : U24_SNARE_N;
        float *s24 = malloc(n24 * sizeof(float));
        for (uint32_t i = 0; i < n24; i++) s24[i] = drumchapel_ulaw(u[i]);
        h.n = 2 * n24;
        for (uint32_t i = 0; i < h.n && i < n0 + 2; i++) h.s[i] = drumchapel_interp(s24, n24, i * 0x8000u);
        if (h.n > n0 + 2) h.n = n0 + 2;
        free(s24);
    }
    return h;
}

int main(int argc, char **argv)
{
    const char *dir = argc > 1 ? argv[1] : ".";
    if (!drumchapel_sampled()) {
        fprintf(stderr, "render_formats: no samples_data.h\n");
        return 1;
    }
    static const char *fmt[3] = { "1_16bit_48k", "2_mulaw_48k", "3_mulaw_24k" };
    static const char *vname[2] = { "kick", "snare" };
    static const int kick[] = { 0, 8, 10, 16, 24, 26, 30 }, snare[] = { 4, 12, 20, 28 };
    char path[1024];
    Hit ref[2];
    for (int v = 0; v < 2; v++) ref[v] = play(v, 0);
    for (int f = 0; f < 3; f++) {
        Hit h[2];
        for (int v = 0; v < 2; v++) {
            h[v] = play(v, f);
            snprintf(path, sizeof path, "%s/%s_%s.wav", dir, vname[v], fmt[f]);
            float *pad = calloc(h[v].n + 24000, sizeof(float));
            for (uint32_t i = 0; i < h[v].n; i++) pad[i] = 0.8f * h[v].s[i];
            wav_write(path, pad, h[v].n + 24000, 48000);
            free(pad);
            double e = 0, p = 0;
            for (uint32_t i = 0; i < ref[v].n; i++) {
                double d = (i < h[v].n ? h[v].s[i] : 0) - ref[v].s[i];
                e += d * d;
                p += (double)ref[v].s[i] * ref[v].s[i];
            }
            printf("%-12s %-5s error %6.1f dB under the signal\n", fmt[f], vname[v], f ? 10 * log10(p / e) : INFINITY);
        }
        float *beat = calloc(BEAT_N, sizeof(float));
        for (size_t k = 0; k < sizeof kick / sizeof kick[0]; k++)
            for (uint32_t i = 0; i < h[0].n; i++) beat[kick[k] * STEP + i] += 0.5f * h[0].s[i];
        for (size_t k = 0; k < sizeof snare / sizeof snare[0]; k++)
            for (uint32_t i = 0; i < h[1].n; i++) beat[snare[k] * STEP + i] += 0.45f * h[1].s[i];
        snprintf(path, sizeof path, "%s/beat_%s.wav", dir, fmt[f]);
        wav_write(path, beat, BEAT_N, 48000);
        free(beat);
        free(h[0].s);
        free(h[1].s);
    }
    printf("written to %s\n", dir);
    return 0;
}
