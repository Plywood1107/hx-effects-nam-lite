/* hostprobe.h - "Probe": a diagnostic block that reports what the host gives it, and the input's level, as a data
 * burst on its audio output. Not an effect: it lives only in the probe image (build_all.py --hostprobe).
 *
 * Two questions (HANDOVER.md, "2026-11-26: the host probe"):
 *  - Memory: the block's graph member asks the host for HOSTPROBE_SDR_REQ words of SDRAM. Does the instance struct
 *    (DM(2, I3), words 6 and 7: the instance's SDRAM block start and end, as the HX Stomp's NAM used them) then hold
 *    a block of that size, and does a word written there stay put?
 *  - Input level: the peak, sum of squares and sum of the input over each second (HOSTPROBE_WIN_CALLS calls of 16
 *    samples), for tools/input_level.py to turn into dBFS.
 *  - DSP load (frame version PRB3): the DSP's own idle word, DM HOSTPROBE_IDLE_ADDR (the HX Stomp's 0xc2fd5, found in
 *    the HX Effects at the two places that read it), read every call: frame word 30 holds the frame's lowest value
 *    (its busiest moment), word 32 the value at the frame's start. tools/dsp_load.py turns them into load.
 *
 * Per call: the meter takes the 16 inputs first (peak = the largest |x|; the call's sums of x^2 and x, in order,
 * then added to the window's); after HOSTPROBE_WIN_CALLS calls the window is latched and starts again. Then the
 * transmitter makes the 16 outputs. It sends frames for ever, each HOSTPROBE_NSYM symbols of HOSTPROBE_SYM samples
 * (2.5 ms): HOSTPROBE_NPILOT symbols of a 6 kHz pilot, then HOSTPROBE_NWORDS 32-bit words most significant bit
 * first, a 0 bit as 2 kHz and a 1 bit as 4 kHz, then HOSTPROBE_NGAP symbols of silence. Each tone is Level x a
 * 48-point sine table stepped 6, 2 or 4 points a sample, continuous in phase. At the first sample of a frame the
 * block runs its memory test and fills the frame (hostprobe.c, latch(): the word list). Mode Pass sends the input
 * through instead (the frames still run, unheard). Time (the host delay's synced Time) is not used.
 *
 * The memory test touches the block only when words 6 and 7 look like the block asked for: start >= 0x200000
 * (external memory), end <= 0x1000000, and end - start between HOSTPROBE_SDR_REQ and HOSTPROBE_SDR_REQ + 0x400.
 * Then it checks the two words it wrote at the previous frame (the first word and the last, HOSTPROBE_PAT_A and
 * _B), counts a mismatch, and writes them again. The reference models those two words as memory nothing else
 * writes.
 */
#ifndef HOSTPROBE_H
#define HOSTPROBE_H

#include "../common/fx.h"

enum { HP_TIME, HP_MODE, HP_LEVEL, HP_NPARAMS };
enum { HP_REPORT, HP_PASS, HP_LOAD };

#define HOSTPROBE_WIN_CALLS 3000          /* calls a meter window: 48,000 samples, 1 s */
#define HOSTPROBE_SYM 120                 /* samples a symbol */
#define HOSTPROBE_NPILOT 80
#define HOSTPROBE_NWORDS 34               /* the sync word, 32 report words, their sum */
#define HOSTPROBE_NBITS (32 * HOSTPROBE_NWORDS)
#define HOSTPROBE_NGAP 40
#define HOSTPROBE_NSYM (HOSTPROBE_NPILOT + HOSTPROBE_NBITS + HOSTPROBE_NGAP)
#define HOSTPROBE_NSIN 48
#define HOSTPROBE_SYNC 0x9E3779B9u
#define HOSTPROBE_MAGIC 0x50524233u       /* "PRB3": the frame's version (words 30 and 32: the idle word) */
#define HOSTPROBE_IDLE_ADDR 0xC28C9u      /* the DSP's idle word (DM), HX Effects 3.80.0 */
/* Mode Load (2): a short frame of long symbols for a microphone across a room (2.5 ms bits smear in a room's
   echo): 20 symbols of pilot, 6 words (sync, HOSTPROBE_MAGIC_L, frames sent, the idle word now, its lowest
   since the last frame, the sum of words 1..4), 10 of silence, each symbol 480 samples (10 ms): 2.22 s a frame. */
#define HOSTPROBE_LSYM 480
#define HOSTPROBE_LPILOT 20
#define HOSTPROBE_LNWORDS 6
#define HOSTPROBE_LNBITS (32 * HOSTPROBE_LNWORDS)
#define HOSTPROBE_LNGAP 10
#define HOSTPROBE_LNSYM (HOSTPROBE_LPILOT + HOSTPROBE_LNBITS + HOSTPROBE_LNGAP)
#define HOSTPROBE_MAGIC_L 0x5052424Cu     /* "PRBL" */
#define HOSTPROBE_SDR_REQ 0x10000u        /* SDRAM words the graph member asks for (build_all.py) */
#define HOSTPROBE_PAT_A 0xA5C3F00Du
#define HOSTPROBE_PAT_B 0x5A3C0FF2u

typedef struct {
    uint32_t entry[4];                    /* the host's view (hostprobe_set_host): DM(0..3, I3) */
    uint32_t inst[16];                    /* DM(0..15, DM(2, I3)) */
    float sintab[HOSTPROBE_NSIN];
    float peak, sq, sum;                  /* the meter's open window */
    int wcalls;
    uint32_t win;                         /* windows completed */
    float lpeak, lsq, lsum;               /* the last complete window */
    uint32_t lwin;
    int spos, sidx, ph, step;             /* the transmitter */
    int fsym, fpil, fpb, fnsym;           /* this frame's symbol length, pilot, pilot + bits, symbols (set by latch) */
    uint32_t frames, calls;
    uint32_t mstat, mbad;                 /* the memory test: 1 once written; mismatches seen */
    uint32_t mem[2];                      /* the block's first and last word, as the test left them */
    uint32_t idle, idlemin;               /* the idle word (the host's, hostprobe_set_idle); its lowest this frame */
    uint32_t frame[HOSTPROBE_NWORDS];
} HostprobeState;

extern const FxAlgorithm fx_hostprobe;

/* The words the kernel reads from the host (the reference cannot): the call-list entry and the instance struct. */
void hostprobe_set_host(void *state, const uint32_t *entry4, const uint32_t *inst16);
/* The DSP's idle word as the kernel reads it at DM HOSTPROBE_IDLE_ADDR each call (the reference cannot). */
void hostprobe_set_idle(void *state, uint32_t idle);
/* sin(2 pi k / 48), as the table holds it. */
float hostprobe_sin(int k);

#endif
