/* render_kits.c - every kit's sounds as one-shots, from the reference, for the groove editor's preview
 * (tools/groove-editor). Each sound is one step of a user groove (drumchapel.h, "The user groove bank") played
 * through the kit's whole chain at Kick, Snare, Hat and Level 1, the guitar silent, ended where it has stayed under
 * -48 dB for 20 ms (faded over those 20 ms; at most 1.5 s: a preview, the unit's tails are longer), as 16-bit 48 kHz mono .wav files <kit>_<sound>.wav, with kits.json listing them.
 * Sounds: kick, snare, hat, open (the open hat / cymbal), tom1..tom4 (high, mid, low, floor).
 *
 * usage: render_kits OUTDIR */
#include "drumchapel.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LEN (2 * 48000)

static uint32_t fb(float x) { uint32_t u; memcpy(&u, &x, 4); return u; }

static void write16(const char *path, const float *x, size_t n)
{
    FILE *f = fopen(path, "wb");
    uint32_t u;
    uint16_t h;
    if (!f) { perror(path); exit(1); }
    fwrite("RIFF", 1, 4, f); u = (uint32_t)(36 + 2 * n); fwrite(&u, 4, 1, f);
    fwrite("WAVEfmt ", 1, 8, f); u = 16; fwrite(&u, 4, 1, f);
    h = 1; fwrite(&h, 2, 1, f); h = 1; fwrite(&h, 2, 1, f);
    u = 48000; fwrite(&u, 4, 1, f); u = 96000; fwrite(&u, 4, 1, f);
    h = 2; fwrite(&h, 2, 1, f); h = 16; fwrite(&h, 2, 1, f);
    fwrite("data", 1, 4, f); u = (uint32_t)(2 * n); fwrite(&u, 4, 1, f);
    for (size_t i = 0; i < n; i++) {
        float v = x[i] > 1.0f ? 1.0f : x[i] < -1.0f ? -1.0f : x[i];
        int16_t q = (int16_t)lrintf(v * 32767.0f);
        fwrite(&q, 2, 1, f);
    }
    fclose(f);
}

int main(int argc, char **argv)
{
    static const char *snd[8] = { "kick", "snare", "hat", "open", "tom1", "tom2", "tom3", "tom4" };
    static const uint32_t byte[8] = { DC_B_KICK, DC_B_SNARE, DC_B_HAT, DC_B_HAT | DC_B_OPEN,
                                      DC_B_TOM, DC_B_TOM | 1u << DC_B_PITCH, DC_B_TOM | 2u << DC_B_PITCH, DC_B_TOM | 3u << DC_B_PITCH };
    static uint32_t w[2048];
    static float in[LEN], out[LEN];
    const char *dir = argc > 1 ? argv[1] : ".";
    char path[1024];
    FILE *js;
    snprintf(path, sizeof path, "%s/kits.json", dir);
    js = fopen(path, "w");
    if (!js) { perror(path); return 1; }
    fprintf(js, "{\"rate\": 48000, \"sounds\": [\"kick\", \"snare\", \"hat\", \"open\", \"tom1\", \"tom2\", \"tom3\", \"tom4\"], \"kits\": [");
    for (int k = 0; k < DRUMCHAPEL_KITS; k++) {
        fprintf(js, "%s\"%s\"", k ? ", " : "", drumchapel_kit_name(k));
        for (int s = 0; s < 8; s++) {
            DrumChapelState *st = malloc(fx_drumchapel.state_bytes);
            FxParams p;
            memset(w, 0, sizeof w);
            w[0] = fb(0.5f); w[1] = fb(-0.5f); w[2] = fb(5.0f); w[3] = fb(1.0f);
            w[4] = fb(0.5f);                                    /* one loop */
            w[5] = fb(16.0f / 1024.0f);
            w[DCU_DIR] = fb((float)(0u << 9 | 16u) / 2097152.0f);
            w[DCU_STEPS] = fb((float)byte[s] / 2097152.0f);    /* step 0 only */
            fx_defaults(&fx_drumchapel, &p);
            p.value[DC_TIME] = 4.0f;                            /* a sixteenth lasts 1 s: one hit in the render */
            p.value[DC_GROOVE] = (float)DRUMCHAPEL_USER_GROOVE;
            p.value[DC_KIT] = (float)k;
            p.value[DC_KICK] = p.value[DC_SNARE] = p.value[DC_HAT] = p.value[DC_LEVEL] = 1.0f;
            fx_drumchapel.reset(st, 48000.0f);
            drumchapel_set_user_slot(st, w);
            for (size_t b = 0; b < LEN; b += 16)
                fx_drumchapel.process(st, &p, in + b, out + b, 16);
            size_t n = 72000, quiet = 0;                       /* at most 1.5 s */
            for (size_t i = 0; i < 72000; i++) {               /* the end: 20 ms under -48 dB */
                if (fabsf(out[i]) < 4e-3f) { if (++quiet >= 960) { n = i + 1; break; } }
                else quiet = 0;
            }
            if (n < 960) n = 960;
            for (size_t i = 0; i < 960; i++)                    /* a 20 ms fade to the end */
                out[n - 960 + i] *= (float)(960 - i) / 960.0f;
            snprintf(path, sizeof path, "%s/%s_%s.wav", dir, drumchapel_kit_name(k), snd[s]);
            write16(path, out, n);
            free(st);
        }
    }
    fprintf(js, "]}\n");
    fclose(js);
    printf("render_kits: %d kits x 8 sounds -> %s\n", DRUMCHAPEL_KITS, dir);
    return 0;
}
