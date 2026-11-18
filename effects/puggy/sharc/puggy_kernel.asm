// puggy_kernel.asm - Puggy Puncher (a tempo-synced slot machine of treatments) for the HX Effects SHARC.
// A port of effects/puggy/puggy.c; puggy_kernel.py checks it bit for bit against that reference in ssim
// and puts the .equ block, constants and tables at "EQUS". Meant to run as an overlay.
//
// Conventions as the other kernels (effects/README.md): once per 16-sample block, I0 = the instance's
// DM block, I1 = 16 inputs, I2 = 16 outputs; R0-R15, I1-I4 and MODE1 come back unchanged; L1-L4 left
// 0; no hardware loops; DM(3, I0) never touched; only P_SLOT (12) written; state in one of NSLOTS
// claimed slots. No ring.
//
// Knob words: DM(5) Time s/beat (float 0.1..4, as Click's), DM(6) Step (int 0..10), DM(7) Chance 0..1,
//             DM(8) Wild (int 0..10), DM(9) Hold (int 1..8), DM(10) Seed (int 0..16), DM(11) Mix 0..1,
//             DM(13) Level 0..1.
// In the sample loop: R0 BPM x 100, R1 the step increment, R2 M, R3 Chance x 2^24, R4 the Wild word,
// R5 Hold, R6 the count, F7 x, R12 the bar's seed (0: Random), F13 Mix, F14 Level; R8-R11, R15 scratch.

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

// EQUS

.section pm 0x0c4ef8

PUGGY_ENTRY:
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
    R13 = SEED0;                        // reset(): the generator's seed
    DM(ST_RND, I3) = R13;
c_have:
    DM(S_LAST, I3) = R9;

    // ---- knobs (clamped as fx_param_clamp does, finite values)
    F0 = DM(5, I0);                     // Time 0.1..4 s -> BPM x 100 (R0), as click_bpm100
    F8 = DM(K_TMIN);
    F0 = MAX(F0, F8);
    F8 = 4.0;
    F0 = MIN(F0, F8);
    F8 = 384000.0;                      // eighth-samples at 48 kHz
    F0 = F0 * F8;
    F8 = 0.5;
    F0 = F0 + F8;
    R9 = TRUNC F0;                      // p
    R10 = LSHIFT R9 BY -1;              // (NUM + p/2) / p, unsigned, shift-and-subtract
    R8 = BPM100_NUM;
    R8 = R8 + R10;
    R10 = 0;
    R0 = 0;
    R11 = 32;
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

    R2 = DM(6, I0);                     // Step 0..10 -> M (R2), the increment (R1)
    R8 = 0;
    R2 = MAX(R2, R8);
    R8 = 10;
    R2 = MIN(R2, R8);
    I4 = R2;
    R2 = DM(T_MUL, I4);
    R1 = R0 * R2 (UUI);

    F15 = DM(7, I0);                    // Chance 0..1 -> x 2^24, truncated (R3)
    CALL g_cl;
    F8 = 16777216.0;
    F15 = F15 * F8;
    R3 = TRUNC F15;

    R4 = DM(8, I0);                     // Wild 0..10 -> its word (R4)
    R8 = 0;
    R4 = MAX(R4, R8);
    R8 = 10;
    R4 = MIN(R4, R8);
    I4 = R4;
    R4 = DM(T_WILD, I4);

    R5 = DM(9, I0);                     // Hold 1..8 (R5)
    R8 = 1;
    R5 = MAX(R5, R8);
    R8 = 8;
    R5 = MIN(R5, R8);

    R12 = DM(10, I0);                   // Seed 0..16 -> the bar's seed (R12)
    R8 = 0;
    R12 = MAX(R12, R8);
    R8 = 16;
    R12 = MIN(R12, R8);
    I4 = R12;
    R12 = DM(T_SEED, I4);

    F15 = DM(11, I0);                   // Mix (F13)
    CALL g_cl;
    F13 = PASS F15;
    F15 = DM(13, I0);                   // Level (F14)
    CALL g_cl;
    F14 = PASS F15;

    R6 = 16;
s_loop:
    F7 = DM(I1, 1);                     // x

    // ---- the clock: a bar (and a step) on the first sample, then the beat and step accumulators
    R8 = DM(ST_STARTED, I3);
    R8 = PASS R8;
    IF EQ JUMP a_first;
    R8 = DM(ST_BACC, I3);
    R8 = R8 + R0;
    R9 = PERIOD;
    COMP(R8, R9);
    IF GE JUMP a_beat;
    DM(ST_BACC, I3) = R8;
a_sacc:
    R8 = DM(ST_SACC, I3);
    R8 = R8 + R1;
    R9 = SPERIOD;
    COMP(R8, R9);
    IF LT JUMP a_nos;
    R8 = R8 - R9;
    DM(ST_SACC, I3) = R8;
    JUMP a_step;
a_nos:
    DM(ST_SACC, I3) = R8;
    JUMP a_treat;
a_beat:
    R8 = R8 - R9;
    DM(ST_BACC, I3) = R8;
    R8 = DM(ST_BEAT, I3);
    R8 = R8 + 1;
    R9 = 3;
    R8 = R8 AND R9;
    DM(ST_BEAT, I3) = R8;
    IF NE JUMP a_sacc;
a_first:
    R8 = 1;
    DM(ST_STARTED, I3) = R8;
    // ---- a bar: the step phase back on the straight grid, the roll restarts, Seed reseeds
    R8 = DM(ST_BACC, I3);
    R8 = R8 * R2 (UUI);
    DM(ST_SACC, I3) = R8;
    R8 = 0;
    DM(ST_HOLD, I3) = R8;
    R12 = PASS R12;
    IF NE DM(ST_RND, I3) = R12;

    // ---- a step: roll unless held; this step's treatment, the crossfade, the filter slams open
a_step:
    R8 = DM(ST_HOLD, I3);
    R8 = PASS R8;
    IF GT JUMP a_held;
    R9 = DM(ST_RND, I3);                // xorshift32
    R10 = LSHIFT R9 BY 13;
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY -17;
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY 5;
    R9 = R9 XOR R10;
    DM(ST_RND, I3) = R9;
    R10 = LSHIFT R9 BY -8;
    R11 = 0;                            // clean, unless under Chance
    COMP(R10, R3);
    IF GE JUMP a_set;
    R10 = 7;                            // the Wild word's nibble (r & 7)
    R10 = R9 AND R10;
    R10 = LSHIFT R10 BY 2;
    R10 = -R10;
    R11 = LSHIFT R4 BY R10;
    R10 = 15;
    R11 = R11 AND R10;
a_set:
    DM(ST_ROLL, I3) = R11;
    R8 = PASS R5;
a_held:
    R8 = R8 - 1;
    DM(ST_HOLD, I3) = R8;
    R8 = DM(ST_CUR, I3);
    DM(ST_PREV, I3) = R8;
    R8 = DM(ST_ROLL, I3);
    DM(ST_CUR, I3) = R8;
    F8 = 1.0;
    DM(ST_XG, I3) = F8;
    F8 = DM(K_FD0);
    DM(ST_FD, I3) = F8;

    // ---- every treatment, into W0..W5 (W3, mute, stays 0)
a_treat:
    DM(ST_W0, I3) = F7;                 // clean

    F8 = DM(ST_T1, I3);                 // octave: two one-poles
    F9 = F7 - F8;
    F10 = DM(K_TA);
    F9 = F10 * F9;
    F8 = F8 + F9;
    DM(ST_T1, I3) = F8;
    F9 = DM(ST_T2, I3);
    F8 = F8 - F9;
    F8 = F10 * F8;
    F9 = F9 + F8;                       // t2
    DM(ST_T2, I3) = F9;
    F8 = ABS F9;                        // the envelope (F10)
    F10 = DM(ST_ENV, I3);
    F11 = DM(K_REL);
    F10 = F10 * F11;
    F10 = MAX(F10, F8);
    DM(ST_ENV, I3) = F10;
    F11 = DM(K_HYST);                   // the comparator, hysteresis h (F11)
    F11 = F11 * F10;
    R8 = DM(ST_HI, I3);
    R8 = PASS R8;
    IF EQ JUMP o_lo;
    F11 = -F11;
    COMP(F9, F11);
    IF GE JUMP o_sq;
    R8 = 0;
    DM(ST_HI, I3) = R8;
    JUMP o_sq;
o_lo:
    COMP(F9, F11);
    IF LE JUMP o_sq;
    R8 = 1;
    DM(ST_HI, I3) = R8;
    R8 = DM(ST_FF, I3);                 // a rising edge: the flip-flop toggles
    R8 = BTGL R8 BY 0;
    DM(ST_FF, I3) = R8;
o_sq:
    R8 = DM(ST_FF, I3);
    R8 = PASS R8;
    IF EQ F10 = -F10;
    F11 = DM(K_ODRY);
    F11 = F11 * F7;
    F11 = F11 + F10;
    DM(ST_W1, I3) = F11;

    R8 = DM(ST_CCNT, I3);               // crush: hold every CRATE samples
    R8 = R8 + 1;
    R9 = CRATE;
    COMP(R8, R9);
    IF LT JUMP c_cnt;
    R8 = 0;
    DM(ST_HELD, I3) = F7;
c_cnt:
    DM(ST_CCNT, I3) = R8;
    F8 = DM(ST_HELD, I3);               // within +-1, x 16 truncated, / 16
    F9 = 1.0;
    F8 = CLIP F8 BY F9;
    F9 = 16.0;
    F8 = F8 * F9;
    R8 = TRUNC F8;
    F8 = FLOAT R8;
    F9 = 0.0625;
    F8 = F8 * F9;
    DM(ST_W2, I3) = F8;

    F8 = DM(ST_FD, I3);                 // filter slam: the coefficient closes, smoothed (F8 = f)
    F9 = DM(K_SLAM);
    F8 = F8 * F9;
    DM(ST_FD, I3) = F8;
    F9 = DM(ST_FS, I3);
    F8 = F8 - F9;
    F10 = DM(K_FS);
    F8 = F10 * F8;
    F9 = F9 + F8;
    DM(ST_FS, I3) = F9;
    F8 = DM(K_FLO);
    F8 = F8 + F9;
    F9 = DM(ST_LOW, I3);                // Chamberlin
    F10 = DM(ST_BAND, I3);
    F11 = F8 * F10;
    F9 = F9 + F11;
    DM(ST_LOW, I3) = F9;
    DM(ST_W4, I3) = F9;
    F11 = F7 - F9;
    F15 = DM(K_FQ);
    F15 = F15 * F10;
    F11 = F11 - F15;
    F11 = F8 * F11;
    F10 = F10 + F11;
    DM(ST_BAND, I3) = F10;

    F8 = DM(K_FG);                      // fuzz
    F8 = F7 * F8;
    F9 = 1.0;
    F8 = CLIP F8 BY F9;
    F9 = DM(K_FL);
    F8 = F8 * F9;
    DM(ST_W5, I3) = F8;

    // ---- this step's (F8), faded in from the last step's (F9); Mix, Level
    R9 = I3;
    R8 = DM(ST_PREV, I3);
    R8 = R8 + R9;
    I4 = R8;
    F10 = DM(ST_W0, I4);
    R8 = DM(ST_CUR, I3);                // (R8 is F8: this one last)
    R8 = R8 + R9;
    I4 = R8;
    F8 = DM(ST_W0, I4);
    F9 = F10 - F8;
    F10 = DM(ST_XG, I3);
    F9 = F9 * F10;
    F8 = F8 + F9;                       // wet
    F11 = 0.03125;
    F10 = F10 - F11;
    F11 = 0.0;
    F10 = MAX(F10, F11);
    DM(ST_XG, I3) = F10;
    F8 = F8 - F7;
    F8 = F13 * F8;
    F8 = F7 + F8;
    F8 = F8 * F14;
    // never pass on a bad value
    F9 = ABS F8;
    F10 = 8.0;
    COMP(F9, F10);
    IF LE JUMP s_out;
    R8 = 0;
    DM(ST_T1, I3) = R8;
    DM(ST_T2, I3) = R8;
    DM(ST_ENV, I3) = R8;
    DM(ST_HELD, I3) = R8;
    DM(ST_LOW, I3) = R8;
    DM(ST_BAND, I3) = R8;
s_out:
    DM(I2, 1) = R8;
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

// ---- F15 clamped to 0..1. Uses F8.
g_cl:
    F8 = 0.0;
    F15 = MAX(F15, F8);
    F8 = 1.0;
    F15 = MIN(F15, F8);
    RTS;
