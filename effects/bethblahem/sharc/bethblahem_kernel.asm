// bethblahem_kernel.asm - Bethblahem (a mega-low-tuned theremin) for the HX Effects SHARC. A port of
// effects/bethblahem/bethblahem.c; bethblahem_kernel.py checks it bit for bit against that reference in
// ssim and puts the .equ block at "EQUS". Written to run as an overlay: self-contained, every constant an
// immediate, no tables.
//
// Conventions as the other kernels (effects/README.md): once per 16-sample block, I0 = the instance's
// DM block, I1 = 16 inputs, I2 = 16 outputs; R0-R15, I1-I4 and MODE1 come back unchanged; L1-L4 left
// 0; no hardware loops; DM(3, I0) never touched; only P_SLOT (12) written; state in one of NSLOTS
// claimed slots (the ST_K* words hold this call's knob values).
//
// Knob words: DM(5) Octave (int 0..4 octaves down), DM(6) Glide, DM(7) Vibrato, DM(8) Rate, DM(9) Growl,
//             DM(10) Sub, DM(11) Dry, DM(13) Level (all 0..1).

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

// EQUS

.section pm 0x0c4ef8

BETHBLAHEM_ENTRY:
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
c_take:                                 // reset(): every state word 0
    DM(P_SLOT, I0) = R11;
    DM(S_OWNER, I3) = R10;
    R13 = 0;
    I4 = MODIFY(I3, 2);
    R14 = NSTATE;
c_zero:
    DM(I4, 1) = R13;
    R14 = R14 - 1;
    IF NE JUMP c_zero;
c_have:
    DM(S_LAST, I3) = R9;

    // ---- knobs (clamped as fx_param_clamp does, finite values)
    R1 = DM(5, I0);                     // Octave 0..4 -> 2^-Octave
    R8 = 0;
    R1 = MAX(R1, R8);
    R8 = 4;
    R1 = MIN(R1, R8);
    F8 = 1.0;
    F9 = 0.5;
k_oct:
    R1 = PASS R1;
    IF EQ JUMP k_oct1;
    F8 = F8 * F9;
    R1 = R1 - 1;
    JUMP k_oct;
k_oct1:
    DM(ST_KOSC, I3) = F8;

    F0 = DM(6, I0);                     // Glide -> k = 1/480 exp(g ln 0.005)
    CALL g_cl;
    F8 = -5.2983174324035645;
    F0 = F0 * F8;
    CALL g_exp;
    F8 = 0.0020833334419876337;
    F0 = F8 * F0;
    DM(ST_KGLK, I3) = F0;

    F0 = DM(7, I0);                     // Vibrato -> its depth (F5)
    CALL g_cl;
    F8 = 0.06;
    F5 = F0 * F8;

    F0 = DM(8, I0);                     // Rate -> 3 exp(r ln 8/3) Hz, in cycles a tick (F6)
    CALL g_cl;
    F8 = 0.9808292388916016;
    F0 = F0 * F8;
    CALL g_exp;
    F8 = 0.001;
    F6 = F0 * F8;

    F0 = DM(9, I0);                     // Growl, its drive and offset
    CALL g_cl;
    DM(ST_KGRW, I3) = F0;
    F8 = 7.0;
    F8 = F0 * F8;
    F9 = 1.0;
    F8 = F9 + F8;
    DM(ST_KDRV, I3) = F8;
    F8 = 0.4;
    F8 = F0 * F8;
    DM(ST_KBIAS, I3) = F8;

    F0 = DM(10, I0);                    // Sub
    CALL g_cl;
    DM(ST_KSUB, I3) = F0;
    F0 = DM(11, I0);                    // Dry
    CALL g_cl;
    DM(ST_KDRY, I3) = F0;
    F0 = DM(13, I0);                    // Level
    CALL g_cl;
    DM(ST_KLVL, I3) = F0;

    // ---- the tick: the vibrato LFO
    F0 = DM(ST_LFO, I3);
    F0 = F0 + F6;
    F8 = 1.0;
    COMP(F0, F8);
    IF GE F0 = F0 - F8;
    DM(ST_LFO, I3) = F0;
    CALL g_sin;
    F0 = F5 * F0;
    F8 = 1.0;
    F0 = F8 + F0;
    DM(ST_VMUL, I3) = F0;

    // ---- the samples
    R6 = 16;
s_loop:
    R7 = DM(I1, 1);                     // x (F7): not finite -> 0, clamped to +-16
    R8 = 0x7F800000;
    R9 = R7 AND R8;
    COMP(R9, R8);
    IF EQ R7 = R7 - R7;
    F8 = 16.0;
    F7 = MIN(F7, F8);
    F8 = -16.0;
    F7 = MAX(F7, F8);
    // DC block
    F8 = DM(ST_DCX, I3);
    F9 = F7 - F8;
    F10 = 0.9986910223960876;
    F11 = DM(ST_DCY, I3);
    F11 = F10 * F11;
    F9 = F9 + F11;
    DM(ST_DCX, I3) = F7;
    DM(ST_DCY, I3) = F9;
    // the tracking signal t (F13)
    F10 = 0.03850883990526199;
    F11 = DM(ST_LP1, I3);
    F12 = F9 - F11;
    F12 = F10 * F12;
    F11 = F11 + F12;
    DM(ST_LP1, I3) = F11;
    F13 = DM(ST_LP2, I3);
    F12 = F11 - F13;
    F12 = F10 * F12;
    F13 = F13 + F12;
    DM(ST_LP2, I3) = F13;
    // envelope (F15)
    F14 = ABS F13;
    F15 = DM(ST_ENV, I3);
    F12 = 0.9995834231376648;
    F12 = F15 * F12;
    COMP(F14, F15);
    IF GT F12 = PASS F14;
    F15 = PASS F12;
    DM(ST_ENV, I3) = F15;
    // the period counter, saturating
    R8 = DM(ST_CNT, I3);
    R9 = CNT_MAX;
    COMP(R8, R9);
    IF LT R8 = R8 + 1;
    DM(ST_CNT, I3) = R8;
    // the comparator, with hysteresis h (F12); on a rising edge, the period
    F12 = 0.5;
    F12 = F15 * F12;
    F11 = 0.00001;
    F12 = F12 + F11;
    F11 = DM(ST_SQ, I3);
    F11 = PASS F11;
    IF LE JUMP c_low;
    F10 = -F12;
    COMP(F13, F10);
    IF GE JUMP c_done;
    F11 = -1.0;
    DM(ST_SQ, I3) = F11;
    JUMP c_done;
c_low:
    COMP(F13, F12);
    IF LE JUMP c_done;
    F11 = 1.0;
    DM(ST_SQ, I3) = F11;
    R1 = DM(ST_CNT, I3);                // the period P (R1), the one before (R2)
    R8 = 0;
    DM(ST_CNT, I3) = R8;
    R2 = DM(ST_PL, I3);
    DM(ST_PL, I3) = R1;
    F8 = 0.002;
    COMP(F15, F8);
    IF LE JUMP c_done;
    R8 = PMIN;
    COMP(R1, R8);
    IF LT JUMP c_done;
    R8 = PMAX;
    COMP(R1, R8);
    IF GT JUMP c_done;
    R8 = R1 - R2;                       // within 1/16 of the last period
    R8 = ABS R8;
    R8 = LSHIFT R8 BY 4;
    COMP(R8, R2);
    IF GT JUMP c_done;
    R0 = 0x80000000;                    // q = 2^28 / P: restoring division, 29 bits
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
    IF LT JUMP d_skip;
    R2 = R2 - R1;
    R3 = R3 + 1;
d_skip:
    R4 = R4 - 1;
    IF NE JUMP d_loop;
    F3 = FLOAT R3;
    F8 = 3.725290298461914e-09;
    F3 = F3 * F8;
    DM(ST_INCT, I3) = F3;
    F8 = 1.0;
    DM(ST_HAVE, I3) = F8;
c_done:
    // the voice: the rate glides to the held note x 2^-Octave; x the vibrato into the phase (F0)
    F8 = DM(ST_INC, I3);
    F9 = DM(ST_INCT, I3);
    F10 = DM(ST_KOSC, I3);
    F9 = F9 * F10;
    F9 = F9 - F8;
    F10 = DM(ST_KGLK, I3);
    F9 = F10 * F9;
    F8 = F8 + F9;
    DM(ST_INC, I3) = F8;
    F10 = DM(ST_VMUL, I3);
    F8 = F8 * F10;
    F0 = DM(ST_PH, I3);
    F0 = F0 + F8;
    F10 = 1.0;
    COMP(F0, F10);
    IF LT JUMP o_nw;
    F0 = F0 - F10;
    F11 = DM(ST_SUBF, I3);
    F11 = F10 - F11;
    DM(ST_SUBF, I3) = F11;
o_nw:
    DM(ST_PH, I3) = F0;
    F8 = DM(ST_AMP, I3);                // the fade-in (F14)
    F9 = DM(ST_HAVE, I3);
    F9 = F9 - F8;
    F10 = 0.0006944444612599909;
    F9 = F10 * F9;
    F14 = F8 + F9;
    DM(ST_AMP, I3) = F14;
    F11 = DM(ST_SUBF, I3);              // the sub's phase (F11)
    F11 = F0 + F11;
    F10 = 0.5;
    F11 = F11 * F10;
    CALL g_sin;
    F12 = PASS F0;
    F0 = PASS F11;
    CALL g_sin;
    F8 = DM(ST_KSUB, I3);
    F0 = F8 * F0;
    F12 = F12 + F0;                     // v
    F8 = DM(ST_KDRV, I3);               // Growl
    F0 = F12 * F8;
    F8 = DM(ST_KBIAS, I3);
    F0 = F0 + F8;
    CALL g_soft;
    F0 = F0 - F12;
    F8 = DM(ST_KGRW, I3);
    F0 = F8 * F0;
    F12 = F12 + F0;                     // w
    F8 = DM(ST_KLVL, I3);               // Level, the fade-in, the limiter
    F0 = F12 * F8;
    F0 = F0 * F14;
    CALL g_soft;
    F8 = 0.4;
    F0 = F0 * F8;
    // the output high-pass, plus Dry x the input
    F8 = DM(ST_OX, I3);
    F9 = F0 - F8;
    F10 = 0.9992145895957947;
    F11 = DM(ST_OY, I3);
    F11 = F10 * F11;
    F9 = F9 + F11;
    DM(ST_OX, I3) = F0;
    DM(ST_OY, I3) = F9;
    F8 = DM(ST_KDRY, I3);
    F8 = F8 * F7;
    F9 = F9 + F8;
    DM(I2, 1) = F9;
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

// ---- F0 = sin(2 pi F0), 0 <= F0 < 1: the phase folded into |t| <= 1/4, an odd degree-7 polynomial.
//      Uses F1-F3.
g_sin:
    F1 = 0.5;
    F0 = F0 - F1;
    F2 = 0.25;
    COMP(F0, F2);
    IF GT F0 = F1 - F0;
    F2 = -0.25;
    F3 = -0.5;
    COMP(F0, F2);
    IF LT F0 = F3 - F0;
    F1 = -6.2831854820251465;
    F0 = F0 * F1;
    F1 = F0 * F0;
    F2 = -0.00019841270113829523;
    F2 = F1 * F2;
    F3 = 0.008333333767950535;
    F2 = F2 + F3;
    F2 = F2 * F1;
    F3 = -0.1666666716337204;
    F2 = F2 + F3;
    F2 = F2 * F1;
    F3 = 1.0;
    F2 = F2 + F3;
    F0 = F2 * F0;
    RTS;

// ---- F0 = soft(F0): clamped to +-1, then F0 (1.5 - F0 F0 0.5). Uses F1, F2.
g_soft:
    F1 = 1.0;
    F0 = MIN(F0, F1);
    F1 = -1.0;
    F0 = MAX(F0, F1);
    F1 = F0 * F0;
    F2 = 0.5;
    F1 = F1 * F2;
    F2 = 1.5;
    F1 = F2 - F1;
    F0 = F0 * F1;
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
    F3 = 0.001388888922519981861115;
    F3 = F3 * F2;
    F4 = 0.008333333767950534820557;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F4 = 0.041666667908430099487305;
    F3 = F3 + F4;
    F3 = F3 * F2;
    F4 = 0.166666671633720397949219;
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
