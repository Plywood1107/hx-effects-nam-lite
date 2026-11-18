// greasy_kernel.asm - Greasy Strangler (a drone that follows the guitar) for the HX Effects SHARC. A port of
// effects/greasy/greasy.c; greasy_kernel.py checks it bit for bit against that reference in ssim and puts the
// .equ block and the data at "EQUS". Self-contained, for an overlay: Corrupt's tracker and Doom Chug's drone
// are copied in, every constant an immediate.
//
// Conventions as the other kernels (effects/README.md): once per 16-sample block, I0 = the instance's DM
// block, I1 = 16 inputs, I2 = 16 outputs; R0-R15, I1-I4 and MODE1 come back unchanged; L1-L4 left 0; no
// hardware loops; DM(3, I0) never touched; only P_SLOT (12) written; state in one of NSLOTS claimed slots.
// Each voice's state: VSIZE words from ST_V0, fields V_*. One call = one control tick + 16 samples.
//
// Knob words: DM(5) Octave (int 0..3: -2 oct, -1 oct, unison, +1 oct), DM(6) Glide, DM(7) Drift, DM(8) Warble,
//             DM(9) Fuzz, DM(10) Tone, DM(11) Dry, DM(13) Level (all 0..1).

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

// EQUS

.section pm 0x0c4ef8

GREASY_ENTRY:
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

    // ---- this instance's slot (I3), as Corrupt
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
c_claim:                                // the first slot free or idle for STALE calls; else pass through
    R11 = 1;
    R14 = NSLOTS;
    I4 = T_SLOTBASE;
    R15 = STALE;
c_find:
    R12 = DM(I4, 1);
    I3 = R12;
    R13 = DM(S_OWNER, I3);
    R13 = PASS R13;
    IF EQ JUMP c_take;
    R13 = DM(S_LAST, I3);
    R13 = R9 - R13;
    COMP(R13, R15);
    IF GT JUMP c_take;
    R11 = R11 + 1;
    R14 = R14 - 1;
    IF NE JUMP c_find;
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
    R13 = SEED;                         // reset()
    DM(ST_RND, I3) = R13;
c_have:
    DM(S_LAST, I3) = R9;

    // ---- knobs for the tick (clamped as fx_param_clamp does, finite values)
    R2 = DM(5, I0);                     // Octave 0..3 -> num = 2^23 << octave
    R8 = 0;
    R2 = MAX(R2, R8);
    R8 = 3;
    R2 = MIN(R2, R8);
    R8 = 0x800000;
    R3 = LSHIFT R8 BY R2;
    DM(ST_NUM, I3) = R3;

    F0 = DM(7, I0);                     // Drift -> dk (F7)
    CALL g_cl;
    F8 = 0.5;
    F7 = F0 * F8;

    F0 = DM(8, I0);                     // Warble -> wk (F12), tk (F13)
    CALL g_cl;
    F8 = 0.16;
    F12 = F0 * F8;
    F8 = 1.2;
    F13 = F0 * F8;

    F0 = DM(6, I0);                     // Glide g -> k = exp(g (2 - g) ln 3e-4) (F0)
    CALL g_cl;
    F8 = 2.0;
    F8 = F8 - F0;
    F0 = F0 * F8;
    F8 = -8.11172771;
    F0 = F0 * F8;
    CALL g_exp;

    // ---- the tick: the glide (the first note taken at once) -> rate (F1)
    F1 = DM(ST_RATE, I3);
    F8 = DM(ST_RATET, I3);
    F9 = F8 - F1, F14 = DM(ST_FADE, I3);
    F9 = F0 * F9;
    F9 = F1 + F9;
    F1 = PASS F1;
    IF EQ F9 = PASS F8;
    F1 = PASS F9, DM(ST_RATE, I3) = F9;
    IF LE JUMP t_fade;                  // the fade-in, once there is a note (F14)
    F8 = 1.0;
    F8 = F8 - F14;
    F9 = 0.005;
    F8 = F9 * F8;
    F14 = F14 + F8;
    DM(ST_FADE, I3) = F14;
t_fade:
    R9 = DM(ST_TICK, I3);               // every 2048 ticks: new walk targets and LFO speeds
    R10 = R9 + 1;
    DM(ST_TICK, I3) = R10;
    R10 = RETARGET;
    R9 = R9 AND R10;
    IF NE JUMP t_keep;
    I4 = MODIFY(I3, ST_V0);
    R9 = DM(ST_RND, I3);
    R11 = 4;
    F15 = 0.0000152587890625;
    R8 = 0xFFFF;
    F2 = 0.002;
    F3 = 0.0001;
t_v:
    R10 = LSHIFT R9 BY 13;              // xorshift32
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY -17;
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY 5;
    R9 = R9 XOR R10;
    R10 = LSHIFT R9 BY -16;
    F10 = FLOAT R10;
    F10 = F10 * F15;
    R0 = R9 AND R8, DM(V_DT, I4) = F10;
    F0 = FLOAT R0;
    F0 = F0 * F15;
    F0 = F2 * F0;
    F0 = F3 + F0;
    R11 = R11 - 1, DM(V_LI, I4) = F0;
    MODIFY(I4, VSIZE);
    IF NE JUMP t_v;
    DM(ST_RND, I3) = R9;
t_keep:
    I4 = MODIFY(I3, ST_V0);             // each voice: root, sharp root, fifth, octave
    F15 = 0.0;
    CALL v_ctl;
    F15 = 0.012;
    CALL v_ctl;
    F15 = 0.583333313;
    CALL v_ctl;
    F15 = 1.0;
    CALL v_ctl;

    // ---- knobs for the samples: drive (ST_DRV), Level (F12), Dry (F13), tone_a (F14)
    F0 = DM(9, I0);                     // Fuzz -> drive 0.6 + 23.4 f^2, Level x (1 - 0.45 f)
    CALL g_cl;
    F8 = F0 * F0;
    F9 = 23.4;
    F8 = F8 * F9;
    F9 = 0.6;
    F8 = F8 + F9;
    DM(ST_DRV, I3) = F8;
    F8 = 0.45;
    F8 = F8 * F0;
    F9 = 1.0;
    F9 = F9 - F8;
    F0 = DM(13, I0);
    CALL g_cl;
    F12 = F0 * F9;
    F0 = DM(11, I0);
    CALL g_cl;
    F13 = PASS F0;
    F0 = DM(10, I0);                    // Tone 0..1 -> 100 exp(t ln 80) Hz -> tone_a
    CALL g_cl;
    F8 = 4.38202667;
    F0 = F0 * F8;
    CALL g_exp;
    F8 = 100.0;
    F0 = F8 * F0;
    F8 = -0.000130899687;
    F0 = F0 * F8;
    CALL g_exp;
    F8 = 1.0;
    F14 = F8 - F0;

    // ---- the samples
    R6 = 16;
s_loop:
    R7 = DM(I1, 1);                     // x (F7), 0 if not finite
    R8 = 0x7F800000;
    R9 = R7 AND R8, F11 = DM(ST_DCX, I3);
    COMP(R9, R8), F10 = DM(ST_DCY, I3);
    IF EQ R7 = R7 - R7;
    // the tracker: input clamped to +-8, DC block
    F8 = 8.0;
    F9 = MIN(F7, F8);
    F8 = -8.0;
    F9 = MAX(F9, F8);
    F11 = F9 - F11, DM(ST_DCX, I3) = F9;
    F8 = 0.998691022;
    F10 = F8 * F10;
    F9 = F11 + F10, F15 = DM(ST_LP2, I3);
    // the tracking signal t (F15)
    F10 = 0.0385088399;
    F11 = DM(ST_LP1, I3);
    F8 = F9 - F11, DM(ST_DCY, I3) = F9;
    F8 = F10 * F8;
    F11 = F11 + F8;
    F8 = F11 - F15, DM(ST_LP1, I3) = F11;
    F8 = F10 * F8;
    F15 = F15 + F8, F10 = DM(ST_ENV, I3);
    // envelope (F9)
    F9 = ABS F15, DM(ST_LP2, I3) = F15;
    F8 = 0.999583423;
    F8 = F10 * F8, R11 = DM(ST_CNT, I3);
    COMP(F9, F10);
    IF LE F9 = PASS F8;
    // the period counter, saturating (R11)
    R10 = CNT_MAX;
    COMP(R11, R10), DM(ST_ENV, I3) = F9;
    IF LT R11 = R11 + 1;
    // the comparator, hysteresis h (F10)
    F10 = 0.5;
    F10 = F9 * F10, DM(ST_CNT, I3) = R11;
    F4 = 0.00001;
    F10 = F10 + F4, F8 = DM(ST_SQ, I3);
    F8 = PASS F8;
    IF LE JUMP c_low;
    F10 = -F10;
    COMP(F15, F10);
    IF GE JUMP c_done;
    F8 = -1.0;
    DM(ST_SQ, I3) = F8;
    JUMP c_done;
c_low:
    COMP(F15, F10);
    IF LE JUMP c_done;
    F8 = 1.0;                           // a rising edge: the period P (R1), the one before (R2)
    R1 = PASS R11, DM(ST_SQ, I3) = F8;
    R8 = 0;
    R2 = DM(ST_PREV, I3);
    R3 = R1 - R2, DM(ST_CNT, I3) = R8;  // agreeing within 1/16, in range, loud enough?
    R3 = ABS R3, DM(ST_PREV, I3) = R1;
    R4 = ASHIFT R2 BY -4;
    COMP(R3, R4);
    IF GT JUMP e_bad;
    R8 = PMIN;
    COMP(R1, R8);
    IF LT JUMP e_bad;
    R8 = PMAX;
    COMP(R1, R8), R5 = DM(ST_OK, I3);
    IF GT JUMP e_bad;
    F8 = 0.002;
    COMP(F9, F8);
    IF LE JUMP e_bad;
    R5 = R5 + 1;
    R8 = 2;
    R5 = MIN(R5, R8);
    COMP(R5, R8), DM(ST_OK, I3) = R5;
    IF LT JUMP c_done;
    // three in a row: rate target = num / (P + P before) x 2^-24, by restoring division, 29 bits (num < 2^29)
    R1 = R1 + R2, R0 = DM(ST_NUM, I3);
    R0 = LSHIFT R0 BY 3;
    R2 = 0;
    R3 = 0;
    R4 = 29;
d_loop:
    R2 = LSHIFT R2 BY 1;
    R0 = PASS R0;
    IF LT R2 = R2 + 1;
    R0 = LSHIFT R0 BY 1;
    R3 = LSHIFT R3 BY 1;
    COMP(R2, R1);
    IF GE R2 = R2 - R1;
    IF GE R3 = R3 + 1;
    R4 = R4 - 1;
    IF NE JUMP d_loop;
    F3 = FLOAT R3;
    F8 = 5.96046448e-8;
    F3 = F3 * F8;
    DM(ST_RATET, I3) = F3;
    JUMP c_done;
e_bad:
    R5 = 0;
    DM(ST_OK, I3) = R5;
c_done:
    // the four saws (F5 = z)
    I4 = MODIFY(I3, ST_V0);             // (V_DG is field 0: read with the step to the next voice)
    F5 = 0.0;
    R10 = 4;
s_v:
    F4 = DM(I4, VSIZE);
    F8 = DM(V_PH - VSIZE, I4);
    F9 = DM(V_INC - VSIZE, I4);
    F8 = F8 + F9, F11 = DM(V_G - VSIZE, I4);
    F9 = 1.0;
    COMP(F8, F9);
    IF GE F8 = F8 - F9;
    F11 = F11 + F4, DM(V_PH - VSIZE, I4) = F8;
    F9 = 0.5;
    F8 = F8 - F9, DM(V_G - VSIZE, I4) = F11;
    F8 = F8 * F11;
    F5 = F5 + F8;
    R10 = R10 - 1, F9 = DM(ST_DRV, I3);
    IF NE JUMP s_v;
    // drive (F9), soft clip
    F5 = F5 * F9, F11 = DM(ST_Z1, I3);
    F8 = 1.0;
    F5 = MIN(F5, F8);
    F8 = -1.0;
    F5 = MAX(F5, F8);
    F8 = 1.5;
    F8 = F8 * F5;
    F10 = 0.5;
    F10 = F10 * F5;
    F10 = F10 * F5;
    F10 = F10 * F5;
    F5 = F8 - F10;
    // two one-poles, Level, plus Dry x the input
    F10 = F5 - F11, F9 = DM(ST_Z2, I3);
    F10 = F14 * F10;
    F11 = F11 + F10;
    F8 = F11 - F9, DM(ST_Z1, I3) = F11;
    F8 = F14 * F8;
    F9 = F9 + F8;
    F8 = F9 * F12, DM(ST_Z2, I3) = F9;
    F7 = F7 * F13;
    F7 = F7 + F8;
    R6 = R6 - 1, DM(I2, 1) = F7;
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

// ---- one voice's tick: F15 = its interval, F1 = the rate, F7 dk, F12 wk, F13 tk, F14 fade; state at I4,
//      which moves to the next voice. Uses F0, F2-F4 (g_exp), F8-F11, F15.
v_ctl:
    F9 = DM(V_D, I4);                   // the walk (F9 = d)
    F10 = DM(V_DT, I4);
    F11 = 0.001;
    F10 = F10 - F9, F8 = DM(V_LP, I4);
    F10 = F11 * F10, F0 = DM(V_LI, I4);
    F9 = F9 + F10;
    F8 = F8 + F0, DM(V_D, I4) = F9;     // the LFO, a triangle 0..0.5 (F10)
    F11 = 1.0;
    COMP(F8, F11);
    IF GE F8 = F8 - F11;
    F11 = 0.5;
    F10 = F8 - F11, DM(V_LP, I4) = F8;
    F10 = ABS F10, F8 = DM(V_G, I4);
    F9 = F7 * F9;                       // q = interval + dk d + wk tri, in octaves
    F15 = F15 + F9;
    F11 = F12 * F10;
    F15 = F15 + F11;
    F0 = 0.693147182;
    F0 = F15 * F0;
    CALL g_exp;
    F0 = F0 * F1;
    F9 = F13 * F10, DM(V_INC, I4) = F0; // the gain ramp (F8 = g)
    F11 = 1.0;
    F11 = F11 - F9;
    F11 = F11 * F14;
    F11 = F11 - F8;
    F9 = 0.0625;
    F11 = F11 * F9;
    DM(I4, VSIZE) = F11;                // V_DG (field 0), and on to the next voice
    RTS;

// ---- F0 clamped to 0..1. Uses F8.
g_cl:
    F8 = 0.0;
    F0 = MAX(F0, F8);
    F8 = 1.0;
    F0 = MIN(F0, F8);
    RTS;

// ---- F0 = geiger_exp(F0): Taylor degree 6 of z = y/16 (Horner), squared four times. Uses F2, F3, F4.
g_exp:
    F2 = 0.0625;
    F2 = F0 * F2;
    F3 = 0.00138888892;
    F3 = F3 * F2;
    F4 = 0.00833333377;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F4 = 0.0416666679;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F4 = 0.166666672;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F4 = 0.5;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F4 = 1.0;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F3 = F3 + F4;
    F3 = F3 * F3;
    F3 = F3 * F3;
    F3 = F3 * F3;
    F0 = F3 * F3;
    RTS;
