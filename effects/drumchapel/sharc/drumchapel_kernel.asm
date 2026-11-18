// drumchapel_kernel.asm - Drum Chapel (a basic drum machine block) for the HX Effects SHARC. A port of
// effects/drumchapel/drumchapel.c; drumchapel_kernel.py checks it bit for bit against that reference in ssim
// and puts the .equ block, constants and tables at "EQUS".
//
// Conventions as the other kernels (effects/README.md): once per 16-sample block, I0 = the instance's
// DM block, I1 = 16 inputs, I2 = 16 outputs; R0-R15, I1-I4 and MODE1 come back unchanged; L1-L4 left
// 0; no hardware loops; DM(3, I0) never touched; only P_SLOT (12) written; state in one of NSLOTS
// claimed slots (no buffer anywhere else). Each voice's state: VW words from ST_V0, fields VS_*; a kit's
// words from T_KIT + kit x DK_WORDS, fields DK_* and, per definition, DV_* (VS_DEF: the offset of the one a
// voice plays, from its kit's first word).
//
// Knob words: DM(5) Time s/beat, DM(6) Pattern (int 0..19), DM(7) Kit (int 0..5), DM(8) Kick 0..1,
//             DM(9) Snare 0..1, DM(10) Hat 0..1, DM(11) Swing 0..1, DM(13) Level 0..1, DM(14) Groove (int 0..11).
//
// The grooves are a read-only bank in DDR2 (inside Blob 0, at T_DIR; drumchapel.h): a directory word per
// Groove x Pattern, (first step << 9) | length, then the steps, four bytes to a word from T_STEPS. Read only
// when a step falls: the directory word and the step's word, two reads a sixteenth.
//
// A call: the knobs; the tempo for the 16 samples (at most one step falls in a call: a sixteenth is at
// least 1,200 samples, swing delays one by at most a third), and that step's byte from the bank; then each
// sample: the step's hits, the noise, the four voices, the kit's drive and clip, Level, and the input added.

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

// EQUS

.section pm 0x0c4ef8

DRUMCHAPEL_ENTRY:
    DM(SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
    DM(SAVE + 1) = R0;
    DM(SAVE + 2) = R1;
    DM(SAVE + 3) = R2;
    DM(SAVE + 4) = R3;
    DM(SAVE + 5) = R4;
    DM(SAVE + 6) = R5;
    DM(SAVE + 7) = R6;
    DM(SAVE + 8) = R7;
    DM(SAVE + 9) = R8;
    DM(SAVE + 10) = R9;
    DM(SAVE + 11) = R10;
    DM(SAVE + 12) = R11;
    DM(SAVE + 13) = R12;
    DM(SAVE + 14) = R13;
    DM(SAVE + 15) = R14;
    DM(SAVE + 16) = R15;
    DM(SAVE + 17) = I4;
    DM(SAVE + 18) = I3;
    DM(SAVE + 19) = I1;
    DM(SAVE + 20) = I2;
    L1 = 0; L2 = 0; L3 = 0; L4 = 0;

    // ---- this instance's slot (I3), as Click
    R9 = DM(G_CALLS);
    R9 = R9 + 1;
    DM(G_CALLS) = R9;
    R10 = I0;
    R11 = DM(P_SLOT, I0);
    R11 = PASS R11;
    IF EQ JUMP c_claim;
    R12 = T_SLOTBASE - 1;
    R12 = R12 + R11;
    I4 = R12;
    R12 = DM(0, I4);
    I3 = R12;
    R13 = DM(S_OWNER, I3);
    COMP(R13, R10);
    IF EQ JUMP c_have;
c_claim:
    R11 = 1;
    R14 = NSLOTS;
    I4 = T_SLOTBASE;
c_free:
    R12 = DM(I4, 1);
    I3 = R12;
    R13 = DM(S_OWNER, I3);
    R13 = PASS R13;
    IF EQ JUMP c_take;
    R11 = R11 + 1;
    R14 = R14 - 1;
    IF NE JUMP c_free;
    R11 = 1;
    R14 = NSLOTS;
    I4 = T_SLOTBASE;
c_stale:
    R12 = DM(I4, 1);
    I3 = R12;
    R13 = DM(S_LAST, I3);
    R13 = R9 - R13;
    R15 = STALE;
    COMP(R13, R15);
    IF GT JUMP c_take;
    R11 = R11 + 1;
    R14 = R14 - 1;
    IF NE JUMP c_stale;
    JUMP k_pass;
c_take:
    DM(P_SLOT, I0) = R11;
    DM(S_OWNER, I3) = R10;
    R13 = 0;
    I4 = MODIFY(I3, 2);
    R14 = NSTATE;
c_zero:
    DM(I4, 1) = R13;
    R14 = R14 - 1;
    IF NE JUMP c_zero;
    R13 = SEED;                         // reset(): the noise's seed; step 0 due on the first sample
    DM(ST_RND, I3) = R13;
    R13 = 1;
    DM(ST_PEND, I3) = R13;
    R13 = 16;                           // a Classic bar until the first step reads its groove
    DM(ST_LEN, I3) = R13;
c_have:
    DM(S_LAST, I3) = R9;

    // ---- knobs (clamped as fx_param_clamp does, finite values)
    F0 = DM(5, I0);                     // Time 0.1..4 s -> BPM x 100 (click_bpm100) x 4 = inc (R0)
    R8 = K_TMIN;
    F0 = MAX(F0, F8);
    F8 = 4.0;
    F0 = MIN(F0, F8);
    F8 = 384000.0;
    F0 = F0 * F8;
    F8 = 0.5;
    F0 = F0 + F8;
    R9 = TRUNC F0;                      // p, eighth-samples
    R10 = LSHIFT R9 BY -1;              // (NUM + p/2) / p, unsigned shift-and-subtract; the quotient
    R8 = BPM100_NUM;                    // (at most 60,000) has 16 bits, so the top 16 bits of the
    R8 = R8 + R10;                      // dividend start as the remainder (under p: p >= 38,400)
    R10 = LSHIFT R8 BY -16;
    R8 = LSHIFT R8 BY 16;
    R0 = 0;
    R11 = 16;
k_div:
    R10 = LSHIFT R10 BY 1;
    R12 = LSHIFT R8 BY -31;
    R10 = R10 OR R12;
    R8 = LSHIFT R8 BY 1;
    R0 = LSHIFT R0 BY 1;
    COMPU(R10, R9);
    IF LT JUMP k_divn;
    R10 = R10 - R9;
    R0 = R0 + 1;
k_divn:
    R11 = R11 - 1;
    IF NE JUMP k_div;
    R0 = LSHIFT R0 BY 2;

    F15 = DM(11, I0);                   // Swing -> the odd steps' threshold (R1)
    CALL g_cl;
    F8 = 96000000.0;
    F15 = F15 * F8;
    R1 = TRUNC F15;

    R5 = DM(7, I0);                     // Kit 0..5 -> its words (R5)
    R8 = 0;
    R5 = MAX(R5, R8);
    R8 = 5;
    R5 = MIN(R5, R8);
    R8 = DK_WORDS;
    R5 = R5 * R8 (UUI);
    R8 = T_KIT;
    R5 = R5 + R8;

    F15 = DM(13, I0);                   // Level (F4)
    CALL g_cl;
    F4 = PASS F15;

    R9 = DM(14, I0);                    // Groove 0..11, Pattern 0..19 -> their directory word's address (R14)
    R8 = 0;
    R9 = MAX(R9, R8);
    R8 = 11;
    R9 = MIN(R9, R8);
    R8 = 20;
    R9 = R9 * R8 (UUI);
    R14 = DM(6, I0);
    R8 = 0;
    R14 = MAX(R14, R8);
    R8 = 19;
    R14 = MIN(R14, R8);
    R14 = R14 + R9;
    R8 = T_DIR;
    R14 = R14 + R8;

    // ---- the tempo for this call: which sample (if any) a step fires on, and its byte -> R2 = count << 8 | byte
    R8 = DM(ST_ACC, I3);
    R9 = DM(ST_STEP, I3);
    R10 = DM(ST_PEND, I3);
    R13 = DM(ST_LEN, I3);
    R2 = 0;
    R12 = PERIOD;
    R6 = 16;
p_loop:
    R10 = PASS R10;
    IF EQ JUMP p_adv;
    R11 = 1;
    R11 = R11 AND R9;
    IF NE R11 = PASS R1;                // odd steps wait for the swing
    COMPU(R8, R11);
    IF LT JUMP p_adv;
    I4 = R14;                           // the step falls: its groove's length (R13) and first step,
    R11 = DM(0, I4);                    // (DDR2) the directory word
    R10 = 511;
    R13 = R11 AND R10;
    R11 = LSHIFT R11 BY -9;
p_mod:                                  // the step mod the length (a groove changed mid-play continues there)
    COMP(R9, R13);
    IF LT JUMP p_byte;
    R9 = R9 - R13;
    JUMP p_mod;
p_byte:
    R11 = R11 + R9;                     // its byte: the step's index in the bank -> word, byte in it
    R3 = LSHIFT R11 BY -2;
    R10 = T_STEPS;
    R3 = R3 + R10;
    I4 = R3;
    R3 = DM(0, I4);                     // (DDR2) four steps
    R10 = 3;
    R11 = R11 AND R10;
    R11 = LSHIFT R11 BY 3;
    R11 = -R11;
    R3 = LSHIFT R3 BY R11;
    R10 = 255;
    R3 = R3 AND R10;
    R2 = LSHIFT R6 BY 8;
    R2 = R2 OR R3;
    R10 = 0;
p_adv:
    R8 = R8 + R0;
    COMP(R8, R12);
    IF LT JUMP p_next;
    R8 = R8 - R12;
    R9 = R9 + 1;                        // the next step, wrapping at the groove's length
    COMP(R9, R13);
    IF GE R9 = R9 - R9;
    R10 = 1;
p_next:
    R6 = R6 - 1;
    IF NE JUMP p_loop;
    DM(ST_ACC, I3) = R8;
    DM(ST_STEP, I3) = R9;
    DM(ST_PEND, I3) = R10;
    DM(ST_LEN, I3) = R13;

    // ---- the samples
    R0 = R2;
    R6 = 16;
s_loop:
    R8 = LSHIFT R0 BY -8;
    COMP(R8, R6);
    IF NE JUMP s_noise;

    // ---- the step's hits (R11 = its byte: bit v = voice v; the hat open; the tom's pitch in bits 5-6)
    F15 = DM(8, I0);                    // the voices' knobs: F7 kick, F1 snare, F12 hat; the tom the kick's
    CALL g_cl;
    F7 = PASS F15;
    F15 = DM(9, I0);
    CALL g_cl;
    F1 = PASS F15;
    F15 = DM(10, I0);
    CALL g_cl;
    F12 = PASS F15;
    R11 = 255;
    R11 = R0 AND R11;
    R14 = DO_HAT;                       // the hat's definition (R14): closed, or open
    R9 = B_OPEN;
    R9 = R11 AND R9;
    IF EQ JUMP h_closed;
    R14 = DO_OPEN;
h_closed:
    R9 = LSHIFT R11 BY -5;              // (B_PITCH) the tom's rate x (F15), from its pitch
    R10 = 3;
    R9 = R9 AND R10;
    R10 = T_TUNE;
    R9 = R9 + R10;
    I4 = R9;
    F15 = DM(0, I4);
    MODIFY(I3, ST_V0);
    R13 = 0;
h_loop:
    R8 = 1;
    R8 = R8 AND R11;
    IF EQ JUMP h_next;
    R9 = DV_WORDS;                      // its definition: DK_V0 + voice x DV_WORDS, the hat's R14
    R9 = R9 * R13 (UUI);
    R10 = DK_V0;
    R9 = R9 + R10;
    R10 = 2;
    COMP(R13, R10);
    IF EQ R9 = PASS R14;
    F2 = 1.0;                           // its rate x: 1, the tom's F15
    R10 = 3;
    COMP(R13, R10);
    IF EQ F2 = PASS F15;
    DM(VS_DEF, I3) = R9;
    DM(VS_TUNE, I3) = F2;
    R9 = R9 + R5;
    I4 = R9;
    F8 = DM(DV_TLEV, I4);
    F8 = F8 * F7, F9 = DM(DV_NLEV, I4);
    F9 = F9 * F7, DM(VS_TE, I3) = F8;
    R8 = R8 - R8, DM(VS_NE, I3) = F9;
    DM(VS_PH, I3) = R8;
    DM(VS_PH2, I3) = R8;
    DM(VS_AGE, I3) = R8;
    DM(VS_LP, I3) = R8;
    F8 = 1.0;
    DM(VS_PE, I3) = F8;
h_next:
    R11 = LSHIFT R11 BY -1;
    F8 = PASS F7;                       // the levels turn: kick, snare, hat, then the kick's for the tom
    F7 = PASS F1;
    F1 = PASS F12;
    F12 = PASS F8;
    MODIFY(I3, VW);
    R13 = R13 + 1;
    R10 = 4;
    COMP(R13, R10);
    IF LT JUMP h_loop;
    MODIFY(I3, -VEND);

    // ---- the noise (F2), held for HOLD samples
s_noise:
    I4 = R5;
    R8 = DM(ST_HCNT, I3);
    R8 = PASS R8, R9 = DM(ST_RND, I3);
    IF NE JUMP n_hold;
    R10 = LSHIFT R9 BY 13;              // xorshift32
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY -17;
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY 5;
    R9 = R9 XOR R10;
    DM(ST_RND, I3) = R9;
n_hold:
    R8 = R8 + 1;
    R10 = DM(DK_HOLD, I4);
    COMP(R8, R10);
    IF GE R8 = R8 - R8;
    DM(ST_HCNT, I3) = R8;
    R9 = LSHIFT R9 BY -8;
    R10 = -23;
    F2 = FLOAT R9 BY R10;
    F8 = 1.0;
    F2 = F2 - F8;

    // ---- the voices: F3 = their sum; R13 = the voice, I3 its state, I4 its definition's words
    F14 = DM(DK_TDRIVE, I4);
    R15 = DM(DK_GATE, I4);
    MODIFY(I3, ST_V0);
    R3 = 0;
    R13 = 0;
    R7 = K_SILENT;
v_loop:
    F8 = DM(VS_TE, I3);
    F9 = DM(VS_NE, I3);
    F10 = MAX(F8, F9);
    COMP(F10, F7);
    IF LT JUMP v_next;                  // silent: the voice has stopped
    R10 = DM(VS_DEF, I3);
    R10 = R10 + R5;
    I4 = R10;
    F12 = F2 * F9;                      // u, the filter's input
    R10 = 2;
    COMP(R13, R10);
    IF EQ JUMP v_metal;
    F8 = DM(VS_PE, I3);                 // kick, snare: the pitch envelope, the rate (F8), the phase
    F9 = DM(DV_PD, I4);
    F8 = F8 * F9, F9 = DM(DV_SWEEP, I4);
    F8 = F9 * F8, DM(VS_PE, I3) = F8;
    F9 = DM(DV_INC, I4);
    F8 = F9 + F8, F9 = DM(VS_TUNE, I3);
    F8 = F8 * F9, F9 = DM(VS_PH, I3);   // x tune: x 1 (exactly the same) but for the tom
    F9 = F9 + F8;
    F10 = 1.0;
    COMP(F9, F10);
    IF GE F9 = F9 - F10;
    DM(VS_PH, I3) = F9;
    CALL g_sin;
    R10 = 1;
    COMP(R13, R10);
    IF NE JUMP v_shape;
    F1 = PASS F9;                       // snare: the second mode
    R10 = K_R2;
    F8 = F8 * F10, F9 = DM(VS_PH2, I3);
    F9 = F9 + F8;
    F10 = 1.0;
    COMP(F9, F10);
    IF GE F9 = F9 - F10;
    DM(VS_PH2, I3) = F9;
    CALL g_sin;
    F10 = DM(DK_M2 - DK_V0 - DV_WORDS, I4);
    F9 = F10 * F9;
    F9 = F1 + F9;
    JUMP v_shape;
v_metal:
    F8 = PASS F8;                       // hat: no metal (TLEV 0), nothing to add
    IF EQ JUMP v_filt;
    R8 = DM(VS_AGE, I3);                // six squares, phase = age x increment
    R1 = I4;
    I4 = T_METAL;
    R9 = 0;
    R10 = DMETAL;
v_m:
    R11 = DM(I4, 1);
    R11 = R11 * R8 (UUI);
    R11 = LSHIFT R11 BY -31;
    R9 = R9 + R11;
    R10 = R10 - 1;
    IF NE JUMP v_m;
    I4 = R1;
    F9 = FLOAT R9;
    R10 = K_THIRD;
    F9 = F9 * F10;
    F10 = 1.0;
    F9 = F9 - F10;
v_shape:
    F9 = F9 * F14;                      // x TDRIVE, clipped, x the tone envelope
    F10 = 1.0;
    F9 = CLIP F9 BY F10, F10 = DM(VS_TE, I3);
    F9 = F9 * F10;
    R10 = 2;
    COMP(R13, R10);
    IF NE JUMP v_tone;
    F12 = F12 + F9;                     // the metal goes through the filter
    JUMP v_filt;
v_tone:
    F3 = F3 + F9;
v_filt:
    F8 = DM(DV_NF, I4);                 // the one-pole: its lowpass (NF > 0) or highpass (NF < 0)
    F9 = DM(VS_LP, I3);
    F10 = F12 - F9;
    F11 = ABS F8;
    F10 = F11 * F10;
    F9 = F9 + F10;
    F8 = PASS F8, DM(VS_LP, I3) = F9;
    IF LT F9 = F12 - F9;
    F3 = F3 + F9, F8 = DM(VS_TE, I3);   // the envelopes; after GATE samples the noise's release
    F9 = DM(DV_TD, I4);
    F8 = F8 * F9, R10 = DM(VS_AGE, I3);
    R10 = R10 + 1, DM(VS_TE, I3) = F8;
    COMP(R10, R15), DM(VS_AGE, I3) = R10;
    F9 = DM(DV_ND, I4);
    R11 = K_GATE;
    IF GT F9 = PASS F11;
    F10 = DM(VS_NE, I3);
    F10 = F10 * F9;
    DM(VS_NE, I3) = F10;
v_next:
    MODIFY(I3, VW);
    R13 = R13 + 1;
    R10 = 4;
    COMP(R13, R10);
    IF LT JUMP v_loop;
    MODIFY(I3, -VEND);

    // ---- the kit's drive, clip and level, Level, the input added
    I4 = R5;
    F8 = DM(DK_DRIVE, I4);
    F3 = F3 * F8;
    F8 = 1.0;
    F3 = CLIP F3 BY F8;
    F8 = 1.5;
    F8 = F8 * F3;
    F9 = 0.5;
    F9 = F9 * F3;
    F9 = F9 * F3;
    F9 = F9 * F3;
    F3 = F8 - F9, F8 = DM(DK_COMP, I4);
    F3 = F3 * F8, R7 = DM(I1, 1);       // x; not finite -> 0
    F3 = F3 * F4;
    R8 = 0x7F800000;
    R9 = R7 AND R8;
    COMP(R9, R8);
    IF EQ R7 = R7 - R7;
    F7 = F7 + F3;
    DM(I2, 1) = F7;
    R6 = R6 - 1;
    IF NE JUMP s_loop;
    JUMP k_exit;

k_pass:                                 // no slot free: pass the input through
    R6 = 16;
k_pw:
    R7 = DM(I1, 1);
    DM(I2, 1) = R7;
    R6 = R6 - 1;
    IF NE JUMP k_pw;

k_exit:
    R0 = DM(SAVE + 1);
    R1 = DM(SAVE + 2);
    R2 = DM(SAVE + 3);
    R3 = DM(SAVE + 4);
    R4 = DM(SAVE + 5);
    R5 = DM(SAVE + 6);
    R6 = DM(SAVE + 7);
    R7 = DM(SAVE + 8);
    R8 = DM(SAVE + 9);
    R9 = DM(SAVE + 10);
    R10 = DM(SAVE + 11);
    R11 = DM(SAVE + 12);
    R12 = DM(SAVE + 13);
    R13 = DM(SAVE + 14);
    R14 = DM(SAVE + 15);
    R15 = DM(SAVE + 16);
    I4 = DM(SAVE + 17);
    I3 = DM(SAVE + 18);
    I1 = DM(SAVE + 19);
    I2 = DM(SAVE + 20);
    MODE1 = DM(SAVE + 0);
    NOP;
    RTS (LR);

// ---- F9 = the parabolic sine of the phase F9 (sine_p). Uses F10, F11.
g_sin:
    F10 = 0.5;
    F9 = F9 - F10;
    F10 = ABS F9;
    F11 = 16.0;
    F10 = F10 * F11;
    F11 = 8.0;
    F10 = F11 - F10;
    F9 = F9 * F10;
    RTS;

// ---- F15 clamped to 0..1. Uses F8.
g_cl:
    F8 = 0.0;
    F15 = MAX(F15, F8);
    F8 = 1.0;
    F15 = MIN(F15, F8);
    RTS;
