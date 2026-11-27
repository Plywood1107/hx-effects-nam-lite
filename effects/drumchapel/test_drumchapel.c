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

/* Classic before the grooves (Groove 0 must sound exactly as it did): FNV-1a of every output word, recorded with the
   three-voice version (git be3ced3) for [setting][pattern][kit]; setting 0: Time 0.37, Kick 0.9, Snare 0.6, Hat 0.7,
   Swing 0.4, Level 0.8, 3 s; setting 1: Time 0.2, all 1, Swing 0, 2 s; input sig_noise(seed 3, 0.3). */
static const uint32_t OLD[2][20][6] = {
  {
    { 0x18678238u, 0x1d7d1eb6u, 0x4dd8374du, 0x60516ba7u, 0x0c295bb3u, 0x42773405u, },
    { 0x53f64e4eu, 0x64a7b7e9u, 0x67060b06u, 0x3c22a967u, 0x6fa4c8f9u, 0x0c2f2956u, },
    { 0x9de99de7u, 0x40d02454u, 0x2e55306du, 0x5caa0d50u, 0x65baa448u, 0xa9855141u, },
    { 0xce1b7604u, 0x550f6a8cu, 0x1ccd2102u, 0xb69b3f42u, 0x1d8ce3e9u, 0x504cfc99u, },
    { 0xca22bfb7u, 0x4ce8ee3cu, 0x0a140870u, 0x3199e40cu, 0x3f7f8118u, 0x3fad49e7u, },
    { 0x3aa691edu, 0x246d6bd3u, 0xb58d34d8u, 0x259436efu, 0x874e93c1u, 0x08d21cf7u, },
    { 0x27c1554au, 0x418314b0u, 0xac775db2u, 0x94ebd823u, 0xa0cafedau, 0xea788792u, },
    { 0x0d6554beu, 0x22decbb3u, 0x63e42ee0u, 0x864c150fu, 0xbdb3294fu, 0x18a1be7bu, },
    { 0xb15f5490u, 0xe75ce973u, 0x130be5ffu, 0xdb21edd7u, 0x58ad3ec2u, 0x9b68d377u, },
    { 0x539013feu, 0x42f9ac7du, 0xa4041fadu, 0xe1c41c0bu, 0xf7d28f98u, 0xcb06833bu, },
    { 0xfea999ecu, 0xe34c9960u, 0x190af176u, 0xf98c184eu, 0xba10c236u, 0xca79ce00u, },
    { 0xe451b551u, 0x157b34a3u, 0x16d31449u, 0x890a862eu, 0x96a80d29u, 0xd5a73876u, },
    { 0x1e70d2e0u, 0xe57da250u, 0xb33cf1c9u, 0x9fa92eb6u, 0xf765b1fdu, 0x57337a6bu, },
    { 0xb37b208cu, 0x5aea4aa2u, 0xc8c7087au, 0xb2254608u, 0xc8294f48u, 0xecfcfeabu, },
    { 0xd07af29fu, 0x221fe9a2u, 0x48f7ddd3u, 0xcad2a111u, 0x480b8a3au, 0x53a26511u, },
    { 0x969a3f3fu, 0x5d7eab03u, 0xcb3a17e3u, 0x57a8c3f7u, 0x121a6a93u, 0x76aff265u, },
    { 0x52ce3574u, 0xc0e57e90u, 0x4683ae24u, 0x02ee837bu, 0x9f38c5fbu, 0x806cdbe8u, },
    { 0x9799a095u, 0x4dd00195u, 0x224b7793u, 0x84526ed3u, 0xc2c6f691u, 0xd676d5c1u, },
    { 0x433908eeu, 0xa9db0e28u, 0x19c8d29cu, 0x2a0ac0b6u, 0x5c7cd2fcu, 0xeeb53f0du, },
    { 0x9aceb4d0u, 0x25a56c71u, 0x9ddf7da4u, 0x2a6b06a8u, 0x49246170u, 0x9dfa6b10u, },
  }, {
    { 0xe33ab80du, 0x0c18e2b7u, 0xac159b33u, 0xa401e276u, 0x424dd2f0u, 0xfa1d5b41u, },
    { 0x6111ce08u, 0xf2307373u, 0xef563014u, 0xf6ee8218u, 0x9cfd5ab4u, 0x8cd98a30u, },
    { 0xe5d3653eu, 0x68b506ceu, 0x6e8f81deu, 0x37067917u, 0xde8244b4u, 0x92e5c9dbu, },
    { 0xf2011598u, 0xa095ff8au, 0xfbab3aacu, 0x0444e9fdu, 0xa8c4a1d9u, 0x4d0d0b3eu, },
    { 0x04601f7du, 0x549187adu, 0xbdfa1756u, 0x96e6be14u, 0x2ac6b60cu, 0x923c60a3u, },
    { 0xf6e932c3u, 0xa6171b58u, 0x74814688u, 0x76c187f8u, 0xb5e535eau, 0x0caceefdu, },
    { 0x042b7adbu, 0x28f4d507u, 0xf4c1f043u, 0x913ea3f5u, 0x6ecc3ca6u, 0xf7031735u, },
    { 0x4394d718u, 0xd5ad5142u, 0x78f182a9u, 0x7dc218e7u, 0x3a283b3fu, 0x31275430u, },
    { 0x0b7168ecu, 0x367f5e4cu, 0x97d10b79u, 0xba39b087u, 0x567c700au, 0x15522317u, },
    { 0xa0d19ec4u, 0xaaa15ba1u, 0x31c73c99u, 0xb3c01d98u, 0x2b0c965fu, 0x0952d89du, },
    { 0x4be57609u, 0x5fa69ebbu, 0xf70daa26u, 0xb16ed8bcu, 0xd6aba63eu, 0x0edc0e2du, },
    { 0xbfa0c3abu, 0xfba97d1cu, 0x938cbb52u, 0x3e5050e9u, 0x2d3cfab9u, 0xeb3d0131u, },
    { 0x21e09f2au, 0xa284c5eau, 0x4fdfb406u, 0xaf5b1ab7u, 0xcdfa816fu, 0x22e67e86u, },
    { 0x61963abcu, 0xab53fc67u, 0xc4eeaa86u, 0xc08a819eu, 0xf82b0f25u, 0x3fbc944au, },
    { 0xe95a7118u, 0xf5424d09u, 0x75488238u, 0xb5d17630u, 0x07a986a6u, 0x773137b7u, },
    { 0x1432ff10u, 0x66d0357bu, 0xdb06b22au, 0xa382a98eu, 0xcfe4e7c3u, 0xafdfcafau, },
    { 0x5e53cfa0u, 0xa80ba960u, 0xc6530acbu, 0x9a5b3ed2u, 0x33891e9fu, 0x1f8cfb0bu, },
    { 0x48951e55u, 0x18d86844u, 0xaef859d7u, 0xf783d172u, 0x6b1baef5u, 0xdaeed9c6u, },
    { 0xe6201602u, 0x3a3f97f4u, 0x2e173aebu, 0x9bd54730u, 0x4e173864u, 0x909b1767u, },
    { 0x5d5722a4u, 0x5f0ab276u, 0x14a3c7b4u, 0x01728aa2u, 0xb4734e1du, 0x59fa3ff5u, },
  }
};

static uint32_t fnv(const float *y, size_t n)
{
    uint32_t h = 2166136261u, u;
    size_t i;
    int b;
    for (i = 0; i < n; i++) {
        memcpy(&u, &y[i], 4);
        for (b = 0; b < 4; b++) { h ^= (u >> (8 * b)) & 255u; h *= 16777619u; }
    }
    return h;
}

/* The tests' own grooves, written into the bank in place (the bank is the reference's static table; restored by
   unpoke). A groove of `len` steps starting at step 0 of the bank (the Classic area), its bytes `b` (repeated). */
static uint32_t SAVED[8192];
static uint32_t bank_n;

static void poke(int groove, int pattern, uint32_t len, const uint32_t *b, uint32_t nb)
{
    uint32_t *bank = (uint32_t *)drumchapel_bank(&bank_n), i;
    if (bank_n <= sizeof SAVED / sizeof SAVED[0]) memcpy(SAVED, bank, bank_n * 4);
    bank[groove * DRUMCHAPEL_PATTERNS + pattern] = 0u << 9 | len;
    for (i = 0; i < len; i++) {
        uint32_t *w = &bank[DRUMCHAPEL_DIR_WORDS + i / 4];
        *w = (*w & ~(0xFFu << (8 * (i % 4)))) | (b[i % nb] & 0xFFu) << (8 * (i % 4));
    }
}

static void unpoke(void)
{
    memcpy((uint32_t *)drumchapel_bank(NULL), SAVED, bank_n * 4);
}

static void setg(FxParams *p, float time, int groove, int pattern, int kit, float kick, float snare, float hat)
{
    memset(p, 0, sizeof *p);
    p->value[DC_TIME] = time; p->value[DC_GROOVE] = (float)groove; p->value[DC_PATTERN] = (float)pattern;
    p->value[DC_KIT] = (float)kit; p->value[DC_KICK] = kick; p->value[DC_SNARE] = snare; p->value[DC_HAT] = hat;
    p->value[DC_LEVEL] = 1.0f;
}

/* Run a groove for `nsteps` steps at block size 16 (at most one step falls in a block); every step must be
   (its count mod the length), with the hits its byte says. Returns the number of wrong steps. */
static int walk(const FxParams *p, int groove, int pattern, uint32_t nsteps)
{
    static float in[16], out[16];
    DrumChapelState s;
    uint32_t len = drumchapel_groove_len(groove, pattern), f = 0, wraps = 0;
    int wrong = 0, v;
    fx_drumchapel.reset(&s, SR);
    while (s.fires < nsteps) {
        uint32_t h[DRUMCHAPEL_VOICES], o = s.opens;
        for (v = 0; v < DRUMCHAPEL_VOICES; v++) h[v] = s.hits[v];
        fx_drumchapel.process(&s, p, in, out, 16);
        if (s.fires == f) continue;
        if (s.fires != f + 1) wrong++;
        f = s.fires;
        if (s.last_step != (f - 1) % len || s.last_byte != drumchapel_groove_step(groove, pattern, s.last_step)) wrong++;
        if (s.last_step == 0 && f > 1) wraps++;
        for (v = 0; v < DRUMCHAPEL_VOICES; v++)
            if ((s.hits[v] != h[v]) != (int)(s.last_byte >> v & 1u)) wrong++;
        if ((s.opens != o) != ((s.last_byte & (DC_B_HAT | DC_B_OPEN)) == (DC_B_HAT | DC_B_OPEN))) wrong++;
    }
    if (wraps != (nsteps - 1) / len) wrong++;
    return wrong;
}

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

static float kwf(const uint32_t *kw, int i)
{
    float f;
    memcpy(&f, &kw[i], sizeof f);
    return f;
}

/* The kit's chain on a voice sum y (drive, clip, shaper, comp, Level), as process() does it, for the exact checks. */
static float chain(const uint32_t *kw, float y, float level)
{
    float w;
    y = y * kwf(kw, DK_DRIVE);
    if (y > 1.0f) y = 1.0f;
    if (y < -1.0f) y = -1.0f;
    w = 1.5f * y - 0.5f * y * y * y;
    w = w * kwf(kw, DK_COMP);
    w = w * level;
    return 0.0f + w;
}

/* An independent model of Acoustic's sampled voices (drumchapel.h, "Samples"): `steps` (bytes, 16 steps, repeated) at
   Time t, no swing, the knobs lev[] (kick, snare, hat; the tom the kick's), Level `level`, the guitar silent. Each
   voice keeps its hit (definition, 16.16 position and step, level) and the one fading out; the output must be their
   sum through the kit's chain, sample for sample. Returns the samples that differ. Needs every voice it hits sampled. */
typedef struct { uint32_t def, pos, inc, def2, pos2, inc2; float te, ne, pe; } ModelVoice;

static float model_at(uint32_t def, uint32_t pos)
{
    uint32_t first = drumchapel_sample_first((int)def), len = drumchapel_sample_len((int)def), i = pos >> 16;
    float a = drumchapel_sample(first + i), b = i + 1 < len ? drumchapel_sample(first + i + 1) : 0.0f;
    float f = (float)(pos & 0xFFFFu) / 65536.0f;
    return a + (b - a) * f;
}

static int exact_hits(const uint32_t *steps, float t, const float lev[3], float level, float *x, float *y, size_t n)
{
    const uint32_t *kw = drumchapel_kit_words(KIT_ACOUSTIC), *ts = drumchapel_tune_step();
    uint32_t inc = click_bpm100(t) * 4u, acc = 0, step = 0;
    ModelVoice m[DRUMCHAPEL_VOICES];
    DrumChapelState s;
    FxParams p;
    size_t i;
    int bad = 0, pend = 1, v;
    memset(m, 0, sizeof m);
    poke(11, 19, 16, steps, 16);
    setg(&p, t, 11, 19, KIT_ACOUSTIC, lev[0], lev[1], lev[2]);
    p.value[DC_LEVEL] = level;
    memset(x, 0, n * sizeof *x);
    render(&s, &p, x, y, n, 16);
    for (i = 0; i < n; i++) {
        float sum = 0.0f;
        if (pend) {                                    /* the step (no swing), as the reference counts them */
            uint32_t b = steps[step];
            pend = 0;
            for (v = 0; v < DRUMCHAPEL_VOICES; v++) {
                ModelVoice *M = &m[v];
                uint32_t def = (uint32_t)v;
                if (!(b >> v & 1u)) continue;
                if (v == HAT && (b & DC_B_OPEN)) def = DEF_OPEN;
                M->def2 = M->def; M->pos2 = M->pos; M->inc2 = M->inc; M->ne = M->te; M->pe = M->te * drumchapel_xf;
                M->def = def; M->pos = 0; M->inc = v == TOM ? ts[b >> DC_B_PITCH & 3u] : 0x8000u;
                M->te = kwf(kw, DK_V0 + (int)def * DV_WORDS + DV_TLEV) * lev[v == TOM ? 0 : v];
            }
        }
        acc += inc;
        if (acc >= DRUMCHAPEL_PERIOD) { acc -= DRUMCHAPEL_PERIOD; step = (step + 1) % 16; pend = 1; }
        for (v = 0; v < DRUMCHAPEL_VOICES; v++) {
            ModelVoice *M = &m[v];
            if (M->te < drumchapel_silent && M->ne < drumchapel_silent) continue;
            if ((M->pos >> 16) < drumchapel_sample_len((int)M->def)) { sum = sum + model_at(M->def, M->pos) * M->te; M->pos += M->inc; }
            else M->te = 0.0f;
            if (M->ne > 0.0f && (M->pos2 >> 16) < drumchapel_sample_len((int)M->def2)) {
                sum = sum + model_at(M->def2, M->pos2) * M->ne; M->pos2 += M->inc2; M->ne = M->ne - M->pe;
            } else M->ne = 0.0f;
        }
        if (y[i] != chain(kw, sum, level)) bad++;
    }
    unpoke();
    return bad;
}

static void acoustic(float *x, float *y)
{
    static const char *dn[DRUMCHAPEL_DEFS] = { "kick", "snare", "hat", "tom", "open hat" };
    static const uint32_t hitb[DRUMCHAPEL_DEFS] = { DC_B_KICK, DC_B_SNARE, DC_B_HAT, DC_B_TOM, DC_B_HAT | DC_B_OPEN };
    const uint32_t *ac = drumchapel_kit_words(KIT_ACOUSTIC), *pu = drumchapel_kit_words(KIT_PUNCH), *ts = drumchapel_tune_step();
    const float full[3] = { 1, 1, 1 }, some[3] = { 0.3f, 0.45f, 0.7f };
    DrumChapelState s;
    FxParams p;
    size_t i, n = 4 * 48000;
    int v, g, pat, bad, all = 1;
    uint32_t nw, at = 0;
    double pk1 = 0, pkd = 0;
    CHECK(strcmp(drumchapel_kit_name(KIT_ACOUSTIC), "Acoustic") == 0, "kit 6 is %s", drumchapel_kit_name(KIT_ACOUSTIC));
    CHECK(ts[0] == 0x8000u && ts[1] == 26214u && ts[2] == 20972u && ts[3] == 16384u, "the tom's steps %u %u %u %u", ts[0], ts[1], ts[2], ts[3]);
    drumchapel_samples(&nw);
    /* each definition: a sample (PD 0, its bytes after the last one's, peak at full scale, ending at 0), or, without
       a hit, its synthesised definition (the kick and snare Punch's) */
    for (v = 0; v < DRUMCHAPEL_DEFS; v++) {
        const uint32_t *q = ac + DK_V0 + v * DV_WORDS;
        uint32_t k, len = drumchapel_sample_len(v), first = drumchapel_sample_first(v);
        double pk = 0;
        if (!len) {
            all = 0;
            CHECK(q[DV_PD] != 0 && (v > DEF_SNARE || memcmp(q, pu + DK_V0 + v * DV_WORDS, DV_WORDS * 4) == 0),
                  "Acoustic %s without a hit is not its synthesised definition", dn[v]);
            printf("  Acoustic %s: no hit in samples_data.h, synthesised\n", dn[v]);
            continue;
        }
        CHECK(q[DV_PD] == 0 && first == q[DV_INC] && len == q[DV_SWEEP] && first == at && (first + len + 3) / 4 <= nw && len > 2400,
              "Acoustic %s: PD %#x, first %u, %u samples, table %u words", dn[v], q[DV_PD], first, len, nw);
        for (k = 0; k < len; k++) if (fabs(drumchapel_sample(first + k)) > pk) pk = fabs(drumchapel_sample(first + k));
        CHECK(pk > 0.97 && drumchapel_sample(first + len - 1) == 0.0f, "%s sample: peak %g, last %g", dn[v], pk,
              drumchapel_sample(first + len - 1));
        printf("  Acoustic %s: %u samples at 24 kHz (%.0f ms), gain %g\n", dn[v], len, len / 24.0, kwf(q, DV_TLEV));
        at += len;
    }
    CHECK(nw == (at + 3) / 4, "the table: %u words for %u samples", nw, at);
    /* the mu-law decoder: G.711's 256 values, odd about 0, 0 at codes 0xFF and 0x7F */
    for (v = 0, bad = 0; v < 256; v++) {
        float a = drumchapel_ulaw((uint8_t)v), b = drumchapel_ulaw((uint8_t)(v ^ 0x80));
        bad += a != -b || fabsf(a) > 32124.0f / 32768.0f || (v < 127 && !(fabsf(a) > fabsf(drumchapel_ulaw((uint8_t)(v + 1)))));
    }
    CHECK(bad == 0 && drumchapel_ulaw(0xFF) == 0.0f && drumchapel_ulaw(0) == -32124.0f / 32768.0f, "mu-law decoder: %d bad codes", bad);
    if (all) {
        /* each voice alone: the sample interpolated (24 -> 48 kHz) x its gain x the knob, through the chain, then
           silence after its end; at another level; retriggered (the next step at Time 0.1, runs, a fast groove) */
        for (v = 0; v < DRUMCHAPEL_DEFS; v++) {
            uint32_t b[16] = { 0 }, two[16] = { 0 }, many[16] = { 0 }, k;
            size_t end = 2 * (size_t)drumchapel_sample_len(v);
            static const uint8_t mk[16] = { 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 1 };
            b[0] = two[0] = two[1] = hitb[v];
            for (k = 0; k < 16; k++) many[k] = mk[k] ? hitb[v] : 0;
            bad = exact_hits(b, 1.0f, full, 1.0f, x, y, n);
            CHECK(bad == 0, "%s: %d samples are not the sample x its level", dn[v], bad);
            for (i = end, bad = 0; i < 4 * 12000 * 4 && i < n; i++) bad += y[i] != 0.0f;
            CHECK(bad == 0 && peak(y, 480) > 0.01, "%s: %d samples sound after its end (%zu)", dn[v], bad, end);
            bad = exact_hits(b, 0.5f, some, 0.45f, x, y, n);
            bad += exact_hits(b, 0.1f, full, 1.0f, x, y, n);
            bad += exact_hits(two, 0.1f, full, 1.0f, x, y, n);
            bad += exact_hits(many, 0.1f, some, 0.8f, x, y, n);
            bad += exact_hits(many, 0.37f, full, 1.0f, x, y, n);
            CHECK(bad == 0, "%s at other levels and retriggered: %d samples differ", dn[v], bad);
        }
        /* the tom at its four pitches: each its step, lasting len / pitch; toms of every pitch one after another */
        for (v = 0; v < 4; v++) {
            uint32_t b[16] = { DC_B_TOM | (uint32_t)v << DC_B_PITCH };
            size_t want = ((size_t)drumchapel_sample_len(DEF_TOM) * 65536 + ts[v] - 1) / ts[v], last = 0;
            bad = exact_hits(b, 2.0f, full, 1.0f, x, y, n);
            for (i = 0; i < n; i++) if (y[i] != 0.0f) last = i;
            CHECK(bad == 0 && last + 1 >= want * 97 / 100 && last < want, "tom pitch %d: %d samples differ, it sounds %zu samples (%zu)", v, bad, last + 1, want);
        }
        {
            uint32_t b[16];
            for (v = 0; v < 16; v++) b[v] = DC_B_TOM | (uint32_t)(v % 4) << DC_B_PITCH | (v % 3 == 0 ? DC_B_KICK : 0u);
            CHECK(exact_hits(b, 0.13f, full, 1.0f, x, y, n) == 0, "toms of every pitch in a run differ");
        }
        /* the choke: the closed hat on the next step cuts the ringing open hat in 64 samples; after them only the
           closed hat sounds (the output as for the closed hat alone) */
        {
            uint32_t oc[16] = { DC_B_HAT | DC_B_OPEN, DC_B_HAT }, c[16] = { 0, DC_B_HAT };
            static float y2[48000];
            size_t at1 = 6000;                                   /* a sixteenth at Time 0.5 */
            double before = 0;
            bad = exact_hits(oc, 0.5f, full, 1.0f, x, y, n);
            CHECK(bad == 0, "open then closed hat: %d samples differ", bad);
            memcpy(y2, y, sizeof y2);
            exact_hits(c, 0.5f, full, 1.0f, x, y, n);
            for (i = at1 + 64, bad = 0; i < 48000; i++) bad += y2[i] != y[i];
            for (i = at1 - 600; i < at1; i++) before += fabs(y2[i]);
            CHECK(bad == 0 && before > 1.0, "the closed hat chokes the open one: %d samples differ after 64 (open before: %g)", bad, before);
            for (i = at1, bad = 0; i < at1 + 64; i++) bad += y2[i] == y[i];
            CHECK(bad < 4, "the choke is a crossfade, not a cut (%d samples equal inside it)", bad);
            CHECK(exact_hits((const uint32_t[16]){ DC_B_HAT, DC_B_HAT | DC_B_OPEN, DC_B_HAT | DC_B_OPEN, DC_B_HAT }, 0.1f, full, 1.0f, x, y, n) == 0,
                  "open and closed hats in turn differ");
        }
        /* everything at once, the fast grooves */
        {
            uint32_t b[16];
            for (v = 0; v < 16; v++) b[v] = (uint32_t)((v * 37 + 11) % 128);
            bad = exact_hits(b, 0.1f, full, 1.0f, x, y, n);
            bad += exact_hits(b, 0.21f, some, 0.6f, x, y, n);
            CHECK(bad == 0, "every voice at once: %d samples differ", bad);
        }
        /* the chain is clean: the kick alone, out / (knob x gain) within 3 % of the interpolated sample (the shaper at
           its peak) */
        {
            uint32_t b[16] = { DC_B_KICK };
            const float k8[3] = { 0.8f, 0, 0 };
            double worst = 0;
            exact_hits(b, 1.0f, k8, 1.0f, x, y, n);
            for (i = 0; i < 2 * (size_t)drumchapel_sample_len(DEF_KICK); i++) {
                double e = fabs(y[i] / (0.8 * kwf(ac, DK_V0 + DV_TLEV)) - model_at(DEF_KICK, (uint32_t)i * 0x8000u));
                if (e > worst) worst = e;
            }
            CHECK(worst < 0.03, "the chain changes the kick by up to %g", worst);
        }
        /* a retrigger is click-free: the largest step across it is no larger than inside a hit */
        {
            uint32_t b[16] = { 1, 1 };
            size_t at1 = 1200;
            double jump = 0, inside = 0;
            exact_hits(b, 0.1f, full, 1.0f, x, y, 2400 * 2);
            for (i = at1; i < at1 + 200; i++) if (fabs(y[i] - y[i - 1]) > jump) jump = fabs(y[i] - y[i - 1]);
            for (i = 1; i < 1200; i++) if (fabs(y[i] - y[i - 1]) > inside) inside = fabs(y[i] - y[i - 1]);
            printf("  kick retrigger: largest step %.3f across it, %.3f inside a hit\n", jump, inside);
            CHECK(jump <= inside * 1.05, "kick retrigger steps by %g (inside a hit: %g)", jump, inside);
        }
    }
    /* every groove runs in Acoustic: the steps and hits as their bytes say, the output finite and under the ceiling
       (COMP x Level: Acoustic's low drive leaves its peaks to Level) */
    for (g = 0, bad = 0; g < DRUMCHAPEL_GROOVES; g++) {
        int fs = drumchapel_family_size(g);
        for (pat = 0; pat < (fs ? fs : (g ? 0 : 20)); pat++) {
            uint32_t len = drumchapel_groove_len(g, pat);
            size_t m = (size_t)(len + 4) * 1200;
            setg(&p, 0.1f, g, pat, KIT_ACOUSTIC, 1, 1, 1);
            p.value[DC_SWING] = (float)(pat % 3) * 0.5f;
            bad += walk(&p, g, pat, len + 3);
            if (m > 4 * 48000) m = 4 * 48000;
            render(&s, &p, x, y, m, 16);
            for (i = 0; i < m; i++) if (!isfinite(y[i]) || fabsf(y[i]) > kwf(ac, DK_COMP)) bad++;   /* the shaper's ceiling */
            if (peak(y, m) > pk1) pk1 = peak(y, m);
            setg(&p, 0.1f, g, pat, KIT_ACOUSTIC, 0.8f, 0.7f, 0.5f);
            render(&s, &p, x, y, m, 16);
            if (peak(y, m) > pkd) pkd = peak(y, m);
        }
    }
    CHECK(bad == 0, "grooves in Acoustic: %d wrong steps or samples", bad);
    printf("  Acoustic, every groove at Level 1: peak %.3f (Kick, Snare, Hat 1), %.3f (0.8, 0.7, 0.5)\n", pk1, pkd);
    {   /* as loud as the other kits (their rms 0.10 .. 0.30 in 5.) */
        double r2, pk2;
        set(&p, 0.5f, 0, KIT_ACOUSTIC, 0.8f, 0.7f, 0.5f, 0, 1); render(&s, &p, x, y, 96000, 16);
        r2 = rms(y, 96000); pk2 = peak(y, 96000);
        printf("  Acoustic rms %.3f peak %.3f (Rock, the default knobs, Level 1)\n", r2, pk2);
        CHECK(r2 > 0.1 && r2 < 0.35, "Acoustic: rms %g", r2);
    }
    /* it sounds, and its voices are at the knobs' levels: 0 silences them */
    set(&p, 0.5f, 0, KIT_ACOUSTIC, 1, 1, 0, 0, 1); render(&s, &p, x, y, n, 16);
    CHECK(peak(y, n) > 0.5 && s.hits[KICK] > 0 && s.hits[SNARE] > 0, "Acoustic Rock: peak %g", peak(y, n));
    set(&p, 0.5f, 0, KIT_ACOUSTIC, 0, 0, 0, 0, 1); render(&s, &p, x, y, n, 16);
    CHECK(peak(y, n) == 0.0, "Acoustic with Kick, Snare, Hat at 0: peak %g", peak(y, n));
}


/* ------------------------------------------------------------------ the user groove bank (Groove = User) */
static uint32_t fb(float x) { uint32_t u; memcpy(&u, &x, 4); return u; }

/* A User IR slot holding `n` loops (lens[k] steps each, bytes from steps[], all loops one after another), as
   grooves.py --user writes it. */
static void pack_user(uint32_t *w, const uint32_t *lens, int n, const uint8_t *steps)
{
    uint32_t total = 0, i;
    int k;
    memset(w, 0, 2048 * 4);
    for (k = 0; k < n; k++) total += lens[k];
    w[0] = fb(0.5f); w[1] = fb(-0.5f); w[2] = fb(5.0f); w[3] = fb(1.0f);
    w[4] = fb((float)n / 2.0f);
    w[5] = fb((float)total / 1024.0f);
    for (k = 0, i = 0; k < n; k++) {
        w[DCU_DIR + k] = fb((float)(i << 9 | lens[k]) / 2097152.0f);
        i += lens[k];
    }
    for (i = 0; i < total; i += 3) {
        uint32_t v = steps[i] | (i + 1 < total ? (uint32_t)steps[i + 1] << 8 : 0u) | (i + 2 < total ? (uint32_t)steps[i + 2] << 16 : 0u);
        w[DCU_STEPS + i / 3] = fb((float)v / 2097152.0f);
    }
}

/* Groove = User for `nsteps` steps: each step (count mod its loop's length) with the byte the loop has there. */
static int walk_user(const FxParams *p, const uint32_t *slot, uint32_t first, uint32_t len, const uint8_t *steps, uint32_t nsteps)
{
    static float in[16], out[16];
    DrumChapelState s;
    uint32_t f = 0;
    int wrong = 0, v;
    fx_drumchapel.reset(&s, SR);
    drumchapel_set_user_slot(&s, slot);
    while (s.fires < nsteps) {
        uint32_t h[DRUMCHAPEL_VOICES];
        for (v = 0; v < DRUMCHAPEL_VOICES; v++) h[v] = s.hits[v];
        fx_drumchapel.process(&s, p, in, out, 16);
        if (s.fires == f) continue;
        f = s.fires;
        if (s.last_step != (f - 1) % len || s.last_byte != steps[first + s.last_step]) wrong++;
        for (v = 0; v < DRUMCHAPEL_VOICES; v++)
            if ((s.hits[v] != h[v]) != (int)(s.last_byte >> v & 1u)) wrong++;
    }
    return wrong;
}

/* 4 s of Groove g, Pattern pat with the slot (or none): the output's hash */
static uint32_t hash_run(int g, int pat, const uint32_t *slot)
{
    static float in[N], out[N];
    FxParams p;
    DrumChapelState s;
    setg(&p, 0.3f, g, pat, KIT_PUNCH, 0.9f, 0.8f, 0.6f);
    fx_drumchapel.reset(&s, SR);
    drumchapel_set_user_slot(&s, slot);
    render(&s, &p, in, out, N, 16);
    return fnv(out, N);
}

static void user_grooves(void)
{
    static uint32_t w[2048], bad[2048];
    static uint8_t st[DCU_MAX_STEPS];
    static const uint32_t lens[3] = { 16, 28, 44 };
    FxParams p;
    uint32_t i, first[3] = { 0, 16, 44 };
    int k, pat, wrong = 0;
    uint32_t seed = 12345;
    for (i = 0; i < DCU_MAX_STEPS; i++) { seed = seed * 1103515245u + 12345u; st[i] = (uint8_t)(seed >> 24 & 0x7Fu); }
    pack_user(w, lens, 3, st);
    /* every Pattern plays loop (Pattern mod 3), step by step, wrapping at its length */
    for (pat = 0; pat < DRUMCHAPEL_PATTERNS; pat++) {
        setg(&p, 0.1f, DRUMCHAPEL_USER_GROOVE, pat, 0, 1, 1, 1);
        wrong += walk_user(&p, w, first[pat % 3], lens[pat % 3], st, lens[pat % 3] * 2 + 3);
    }
    CHECK(wrong == 0, "user grooves: %d wrong steps over 20 patterns", wrong);

    /* Classic exactly, whenever the slot is not a groove bank */
    {
        int bad_n = 0, cases = 0;
        uint32_t want[3];
        for (k = 0; k < 3; k++) want[k] = hash_run(0, 5 * k, NULL);
        for (k = 0; k < 3; k++) bad_n += hash_run(DRUMCHAPEL_USER_GROOVE, 5 * k, NULL) != want[k], cases++;
        static const int field[] = { 0, 1, 2, 3, 4, 4, 4, 5, 5, 5 };
        static const float val[] = { 0.25f, -1.0f, 3.0f, 2.0f, 0.0f, 10.5f, 0.75f, 0.0f, 7.0f, 1.0f / 1024.0f };
        for (i = 0; i < sizeof field / sizeof field[0]; i++) {
            memcpy(bad, w, sizeof w);
            bad[field[i]] = fb(val[i]);
            for (k = 0; k < 3; k++) bad_n += hash_run(DRUMCHAPEL_USER_GROOVE, 5 * k, bad) != want[k], cases++;
        }
        CHECK(bad_n == 0, "user grooves: %d of %d runs with an empty slot or a wrong header differ from Classic", bad_n, cases);
    }
    /* a pattern whose directory value is not a groove inside the steps plays Classic; the others stay the user's */
    {
        static const float dv[] = { (float)(0u << 9 | 6u), (float)(0u << 9 | 0u), (float)(80u << 9 | 16u), (float)(0u << 9 | 388u), -1.0f, 9.0f };
        int bad_n = 0;
        for (i = 0; i < sizeof dv / sizeof dv[0]; i++) {
            memcpy(bad, w, sizeof w);
            bad[DCU_DIR + 0] = fb(dv[i] / 2097152.0f);
            if (dv[i] < 0 || dv[i] >= 8.0f * 2097152.0f) bad[DCU_DIR + 0] = fb(dv[i]);
            bad_n += hash_run(DRUMCHAPEL_USER_GROOVE, 0, bad) != hash_run(0, 0, NULL);
            bad_n += hash_run(DRUMCHAPEL_USER_GROOVE, 1, bad) != hash_run(DRUMCHAPEL_USER_GROOVE, 1, w);
        }
        CHECK(bad_n == 0, "user grooves: %d runs wrong with a bad directory value", bad_n);
    }
    /* a step sample that is not a value 0 <= v < 8 plays nothing there */
    {
        static const float sv[] = { -0.5f, 8.0f, 1e30f };
        uint8_t st2[DCU_MAX_STEPS];
        int bad_n = 0;
        for (i = 0; i < 3; i++) {
            memcpy(bad, w, sizeof w);
            memcpy(st2, st, sizeof st2);
            bad[DCU_STEPS + 1] = fb(sv[i]);
            st2[3] = st2[4] = st2[5] = 0;
            setg(&p, 0.1f, DRUMCHAPEL_USER_GROOVE, 0, 0, 1, 1, 1);
            bad_n += walk_user(&p, bad, 0, 16, st2, 40);
        }
        uint32_t nanb = 0x7FC00000u;
        memcpy(bad, w, sizeof w);
        bad[DCU_STEPS + 1] = nanb;
        memcpy(st2, st, sizeof st2);
        st2[3] = st2[4] = st2[5] = 0;
        bad_n += walk_user(&p, bad, 0, 16, st2, 40);
        CHECK(bad_n == 0, "user grooves: %d wrong steps with a step sample out of range", bad_n);
    }
    /* the fullest bank: 20 loops, 6,056 steps, its last loop's last step read from the slot's last samples */
    {
        static uint32_t big[2048];
        uint32_t L[20], f0 = 0;
        for (k = 0; k < 20; k++) L[k] = k < 15 ? 384 : (k < 19 ? 64 : DCU_MAX_STEPS - 15 * 384 - 4 * 64 - (DCU_MAX_STEPS - 15 * 384 - 4 * 64) % 4);
        for (k = 0; k < 20; k++) f0 += L[k];
        pack_user(big, L, 20, st);
        CHECK(big[2047] == 0 && f0 <= DCU_MAX_STEPS, "the fullest bank fits: %u steps, sample 2047 %#x", f0, big[2047]);
        setg(&p, 0.1f, DRUMCHAPEL_USER_GROOVE, 19, 0, 1, 1, 1);
        CHECK(walk_user(&p, big, f0 - L[19], L[19], st, L[19] + 5) == 0, "the fullest bank's last loop (%u steps) plays", L[19]);
    }
    printf("  user grooves: 20 patterns, fallbacks to Classic, out-of-range values\n");
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
    {
        uint32_t km = 0, sm = 0, hm = 0;
        for (k = 0; k < 16; k++) {
            uint32_t b = drumchapel_groove_step(0, 0, (uint32_t)k);
            km |= (b & 1u) << k; sm |= (b >> 1 & 1u) << k; hm |= (b >> 2 & 1u) << k;
        }
        CHECK(km == 0x0501u && sm == 0x1010u && hm == 0x5555u && drumchapel_groove_len(0, 0) == 16,
              "Rock is %#x / %#x / %#x", km, sm, hm);
    }

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
        uint32_t m[3] = { 0, 0, 0 };
        static float in1[1], out1[1];
        int wrong = 0;
        for (k = 0; k < 16; k++)
            for (v = 0; v < 3; v++) m[v] |= (drumchapel_groove_step(0, pat, (uint32_t)k) >> v & 1u) << k;
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

    /* 5. the synthesised kits: each different, Doom the lowest and the most saturated (Acoustic: 14.) */
    for (kit = 0; kit < DRUMCHAPEL_SYNTH_KITS; kit++) {
        set(&p, 0.5f, 0, kit, 0.8f, 0.7f, 0.5f, 0, 1); render(&s, &p, x, y, 96000, 16);
        feat[kit][0] = rms(y, 96000);
        feat[kit][1] = peak(y, 96000) / feat[kit][0];                    /* crest factor */
        feat[kit][2] = bright(y, 96000);
        set(&p, 1.0f, 18, kit, 1, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);   /* one kick */
        feat[kit][3] = zcr(y + MS(60), MS(300)) * 48000.0 / 2.0;               /* its pitch, Hz */
        printf("  %-6s rms %.3f crest %.2f bright %.3f kick %.1f Hz\n", drumchapel_kit_name(kit),
               feat[kit][0], feat[kit][1], feat[kit][2], feat[kit][3]);
    }
    for (kit = 0; kit < DRUMCHAPEL_SYNTH_KITS; kit++) {
        int other;
        set(&p, 0.5f, 0, kit, 0.8f, 0.7f, 0.5f, 0, 1); render(&s, &p, x, y, 96000, 16);
        for (other = kit + 1; other < DRUMCHAPEL_SYNTH_KITS; other++) {
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
        for (kit = 0; kit < DRUMCHAPEL_SYNTH_KITS; kit++) {
            set(&p, 1.0f, 18, kit, 1, 0, 0, 0, 1); render(&s, &p, x, y, 48000, 16);
            tail[kit] = rms(y + MS(300), MS(200)) / rms(y, MS(50));
        }
        CHECK(tail[KIT_BOOM] > 2.0 * tail[KIT_PUNCH] && tail[KIT_BOOM] > 2.0 * tail[KIT_TICK],
              "kick tails: Boom %g, Punch %g, Tick %g", tail[KIT_BOOM], tail[KIT_PUNCH], tail[KIT_TICK]);
    }
    /* hats: Bit's is held noise, Doom's is dark, Tick's and Punch's bright */
    {
        double zc[DRUMCHAPEL_KITS], br[DRUMCHAPEL_KITS];
        for (kit = 0; kit < DRUMCHAPEL_SYNTH_KITS; kit++) {
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
        p.value[DC_GROOVE] = hv;
        if (kit == 1) for (i = 0; i < DC_NPARAMS; i++) p.value[i] = NAN;
        float lim = kit == -1 ? kwf(drumchapel_kit_words(KIT_ACOUSTIC), DK_COMP) : 1.5f;   /* -1: Kit clamps to Acoustic,
                                                    whose low drive leaves stacked hits to its ceiling, COMP x Level */
        render(&s, &p, x, y, N, 16);
        for (i = 0, bad = 0; i < N; i++) {
            float in = isfinite(x[i]) ? x[i] : 0.0f;
            if (!isfinite(y[i]) || fabsf(y[i] - in) > lim) bad++;
        }
        CHECK(bad == 0, "hostile case %d: %d bad samples", kit, bad);
    }
    /* every knob moving at random every 10 ms, through every kit */
    {
        unsigned r = 12345;
        fx_drumchapel.reset(&s, SR);
        for (i = 0, bad = 0; i < N; i += 16) {
            if (i % 480 == 0) {
                for (k = 0; k < DC_NPARAMS; k++) { r = r * 1103515245u + 12345u; p.value[k] = (float)(r >> 8) / 16777216.0f * 1.4f - 0.2f; }
                p.value[DC_TIME] = 0.05f + p.value[DC_TIME] * 3.0f;
                p.value[DC_PATTERN] *= 20.0f; p.value[DC_KIT] *= 7.0f; p.value[DC_GROOVE] *= 12.0f;
            }
            fx_drumchapel.process(&s, &p, x + i, y + i, 16);
            for (k = 0; k < 16; k++) {
                float in = isfinite(x[i + k]) ? x[i + k] : 0.0f;
                if (!isfinite(y[i + k]) || fabsf(y[i + k] - in) > 1.5f) bad++;
            }
        }
        CHECK(bad == 0, "moving knobs: %d bad samples", bad);
    }


    /* 8. Classic (Groove 0) exactly as before the grooves, every pattern and (synthesised) kit at two settings */
    {
        static const float S[2][7] = { { 0.37f, 0.9f, 0.6f, 0.7f, 0.4f, 0.8f, 3 }, { 0.2f, 1, 1, 1, 0, 1, 2 } };
        int set_, diff = 0;
        sig_noise(x, N, 3, 0.3f);
        for (set_ = 0; set_ < 2; set_++)
            for (pat = 0; pat < 20; pat++)
                for (kit = 0; kit < DRUMCHAPEL_SYNTH_KITS; kit++) {
                    n = (size_t)(S[set_][6] * 48000);
                    set(&p, S[set_][0], pat, kit, S[set_][1], S[set_][2], S[set_][3], S[set_][4], S[set_][5]);
                    render(&s, &p, x, y, n, 16);
                    if (fnv(y, n) != OLD[set_][pat][kit]) diff++;
                }
        CHECK(diff == 0, "Classic differs from the three-voice version in %d of 240 renders", diff);
        memset(x, 0, N * sizeof *x);
    }

    /* 9. the bank: its directory, Classic, the families (Pattern = variation mod the family's size) */
    {
        uint32_t nw, total, g, bad9 = 0;
        const uint32_t *bank = drumchapel_bank(&nw);
        total = (nw - DRUMCHAPEL_DIR_WORDS) * 4;
        for (g = 0; g < DRUMCHAPEL_GROOVES; g++) {
            int fs = drumchapel_family_size((int)g);
            for (pat = 0; pat < DRUMCHAPEL_PATTERNS; pat++) {
                uint32_t d = bank[g * DRUMCHAPEL_PATTERNS + pat], len = d & 511u, first = d >> 9;
                if (len < 16 || len > DRUMCHAPEL_MAX_STEPS || len % 4 || first + len > total) bad9++;
                if (g == 0 && d != ((uint32_t)pat * 16u << 9 | 16u)) bad9++;
                if (g > 0 && fs == 0 && d != bank[pat]) bad9++;                       /* missing: Classic */
                if (g > 0 && fs > 0 && (fs > 20 || d != bank[g * DRUMCHAPEL_PATTERNS + pat % fs])) bad9++;
                if (g > 0 && fs > 0 && pat < fs && d == bank[pat]) bad9++;            /* a family's own steps */
            }
        }
        CHECK(bad9 == 0, "bank directory: %u bad entries", bad9);
        printf("  bank: %u words (%u directory), %d of 11 families converted%s\n", nw, DRUMCHAPEL_DIR_WORDS,
               drumchapel_families(), drumchapel_families() ? "" : " (grooves_data.h missing: Classic only)");
    }

    /* 10. every groove: each step is (count mod length), its hits as its byte says, the wrap at the length */
    {
        int g, bad10 = 0, ng = 0;
        for (g = 0; g < DRUMCHAPEL_GROOVES; g++) {
            int fs = drumchapel_family_size(g);
            for (pat = 0; pat < (fs ? fs : (g ? 0 : 20)); pat++) {
                uint32_t len = drumchapel_groove_len(g, pat);
                setg(&p, 0.1f, g, pat, 0, 1, 1, 1);
                p.value[DC_SWING] = (float)(pat % 3) * 0.5f;
                bad10 += walk(&p, g, pat, len + len / 2 + 3);
                ng++;
            }
        }
        CHECK(bad10 == 0, "grooves: %d wrong steps over %d grooves", bad10, ng);
    }

    /* 11. a long groove of an odd meter (29/4, 116 sixteenths) for ten minutes: every step on its sample, count mod 116 */
    {
        static const uint32_t bytes[5] = { 1, 4, 2 | 4, 8 | 2 << DC_B_PITCH, 4 | 16 };
        static float b1[16], b2[16];
        uint32_t inc = click_bpm100(0.4379562f) * 4u;
        size_t late = 0;
        poke(11, 19, 116, bytes, 5);
        setg(&p, 0.4379562f, 11, 19, 2, 1, 1, 1);
        fx_drumchapel.reset(&s, SR);
        for (i = 0; i < (size_t)(600 * 48000); i += 16) {
            size_t j;
            for (j = 0; j < 16; j++) {
                uint32_t b = s.fires;
                fx_drumchapel.process(&s, &p, b1 + j, b2 + j, 1);
                if (s.fires != b) {
                    uint64_t f = s.fires - 1, nn = i + j;
                    if (!(nn * inc >= f * DRUMCHAPEL_PERIOD && (nn == 0 || (nn - 1) * inc < f * DRUMCHAPEL_PERIOD))) late++;
                    if (f % 116u != s.last_step || s.last_byte != bytes[s.last_step % 5]) late++;
                }
            }
        }
        CHECK(late == 0 && s.fires > 5000, "29/4 groove, ten minutes: %zu wrong of %u steps", late, s.fires);
        unpoke();
    }

    /* 12. Groove and Pattern changes mid-play: the step continues (mod the new length), the timing never moves */
    {
        static const uint32_t bytes[1] = { 1 };
        static float in1[16], out1[16];
        static uint32_t ts[400], tr[400];
        DrumChapelState r;
        FxParams a, b;
        uint32_t prev = 0, at38 = 99, bad12 = 0;
        poke(11, 19, 116, bytes, 1);
        setg(&a, 0.25f, 0, 3, 0, 1, 1, 1);          /* Classic, 16 steps */
        setg(&b, 0.25f, 11, 19, 0, 1, 1, 1);        /* 116 steps */
        fx_drumchapel.reset(&s, SR);
        fx_drumchapel.reset(&r, SR);
        /* s: Classic for steps 1..37, the long groove for 38..141, Classic again; r: Classic throughout */
        for (i = 0; s.fires < 400; i += 16) {
            uint32_t f = s.fires, g = r.fires;
            fx_drumchapel.process(&s, s.fires < 37 ? &a : s.fires < 141 ? &b : &a, in1, out1, 16);
            fx_drumchapel.process(&r, &a, in1, out1, 16);
            if (r.fires != g && r.fires <= 400) tr[r.fires - 1] = (uint32_t)i;
            if (s.fires == f) continue;
            ts[s.fires - 1] = (uint32_t)i;
            if (s.fires == 38) at38 = s.last_step;
            else if (s.fires > 1 && s.last_step != (prev + 1) % (s.fires >= 39 && s.fires <= 141 ? 116u : 16u)) bad12++;
            prev = s.last_step;
        }
        /* step 37 of Classic is 36 mod 16 = 4, so the long groove starts at 5; its step 108 (fire 141) hands Classic 109 mod 16 */
        CHECK(at38 == 5 && bad12 == 0, "groove change: the long groove started at step %u, %u steps wrong", at38, bad12);
        for (k = 0, bad = 0; k < 400; k++) bad += ts[k] != tr[k];
        CHECK(bad == 0, "a groove change moved %d steps in time", bad);
        unpoke();
        /* a Pattern change inside a family (Classic when the family is missing) keeps the count too */
        setg(&a, 0.2f, 1, 0, 0, 1, 1, 1);
        b = a; b.value[DC_PATTERN] = 1;
        fx_drumchapel.reset(&s, SR);
        for (prev = 0, bad12 = 0; s.fires < 3 * 16 + 9;) {
            uint32_t f = s.fires;
            fx_drumchapel.process(&s, s.fires < 21 ? &a : &b, in1, out1, 16);
            if (s.fires == f) continue;
            if (s.fires > 1 && s.last_step != (prev + 1) % drumchapel_groove_len(1, s.fires <= 21 ? 0 : 1)) bad12++;
            prev = s.last_step;
        }
        CHECK(bad12 == 0, "pattern change: %u wrong steps", bad12);
    }

    /* 13. toms: four pitches, high to floor at the kit's ratios, at the Kick knob's level; open hats ring on */
    {
        double hz[4];
        int t, kt;
        for (kt = 0; kt < DRUMCHAPEL_KITS; kt++) {
            for (t = 0; t < 4; t++) {
                uint32_t b = DC_B_TOM | (uint32_t)t << DC_B_PITCH;
                poke(11, 19, 16, &b, 1);
                setg(&p, 4.0f, 11, 19, kt, 1, 0, 0);         /* one tom hit (Time 4 s: the next a second later) */
                render(&s, &p, x, y, MS(1000), 16);
                /* Doom's fuzz and noise: wait for the noise to die */
                hz[t] = (kt == KIT_DOOM ? zcr(y + MS(400), MS(500)) : zcr(y + MS(40), MS(200))) * 48000.0 / 2.0;
                CHECK(s.hits[TOM] == 1 && s.hits[KICK] == 0 && peak(y, MS(400)) > 0.05, "%s tom %d: %u hits, peak %g",
                      drumchapel_kit_name(kt), t, s.hits[TOM], peak(y, MS(400)));
                setg(&p, 4.0f, 11, 19, kt, 0, 1, 1);         /* Kick 0: the toms silent */
                render(&s, &p, x, y, MS(400), 16);
                CHECK(peak(y, MS(400)) == 0.0, "%s tom %d sounds with Kick at 0", drumchapel_kit_name(kt), t);
                unpoke();
            }
            printf("  %-6s toms %.0f / %.0f / %.0f / %.0f Hz\n", drumchapel_kit_name(kt), hz[0], hz[1], hz[2], hz[3]);
            if (kt != KIT_BIT && !(kt == KIT_ACOUSTIC && drumchapel_sample_len(DEF_TOM)))   /* a sampled tom: its steps, in 14. */
                CHECK(hz[0] > hz[1] && hz[1] > hz[2] && hz[2] > hz[3] && fabs(hz[3] / hz[0] - 0.5) < 0.12,
                      "%s toms not falling: %g %g %g %g", drumchapel_kit_name(kt), hz[0], hz[1], hz[2], hz[3]);
        }
        /* the open hat (any cymbal) outlasts the closed one, in every kit */
        for (kt = 0; kt < DRUMCHAPEL_KITS; kt++) {
            double e[2];
            for (t = 0; t < 2; t++) {
                uint32_t b = DC_B_HAT | (t ? DC_B_OPEN : 0u);
                poke(11, 19, 16, &b, 1);
                setg(&p, 4.0f, 11, 19, kt, 1, 1, 1);
                render(&s, &p, x, y, MS(400), 16);
                e[t] = kt == KIT_DOOM ? rms(y + MS(300), MS(60)) : rms(y + MS(80), MS(60));   /* Doom: past the clipping */
                CHECK(s.hits[HAT] == 1 && s.opens == (uint32_t)t, "%s hat %d: %u hits, %u open", drumchapel_kit_name(kt), t, s.hits[HAT], s.opens);
                unpoke();
            }
            /* Acoustic's open hat is its closed one a little open (1.75 x the decay, 0.7 x the level): no long wash */
            if (kt == KIT_ACOUSTIC)
                CHECK(e[1] > 1.5 * e[0] && e[1] < 4.0 * e[0] && e[1] > 1e-3, "Acoustic: open hat %g some way into the hit, closed %g", e[1], e[0]);
            else
                CHECK(e[1] > 4.0 * e[0] && e[1] > 1e-3, "%s: open hat %g some way into the hit, closed %g", drumchapel_kit_name(kt), e[1], e[0]);
        }
    }

    /* 14. Acoustic: its five voices play the samples (each its synthesised one without a hit in samples_data.h) */
    acoustic(x, y);

    /* 15. the user groove bank in an IR slot (Groove = User) */
    user_grooves();

    printf("%d checks, %d failures\n", checks, failures);
    free(x); free(y); free(z);
    return failures ? 1 : 0;
}
