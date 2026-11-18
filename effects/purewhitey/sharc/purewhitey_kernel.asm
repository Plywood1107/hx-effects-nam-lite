// purewhitey_kernel.asm - Pure Whitey (glitch short-time sampler) for the HX Effects SHARC. A port of
// effects/purewhitey/purewhitey.c; purewhitey_kernel.py checks it bit for bit against that reference in
// ssim and puts the .equ block, constants and tables at "EQUS".
//
// Conventions as the other kernels (effects/README.md): once per 16-sample block, I0 = the instance's
// DM block, I1 = 16 inputs, I2 = 16 outputs; R5-R15, I1, I2, I4 and MODE1 come back unchanged (R0-R4, I3
// are not used); L1, L2, L4 left 0; no hardware loops; DM(3, I0) never touched; only P_SLOT (12) written;
// the state in the one slot at SLOTS (a second block passes its input through); the ring (RING_N words,
// two 16-bit samples each) at RING0, never zeroed: a slice never reaches past what has been recorded
// (each LISTEN records the whole slice before it is played).
//
// Knob words: DM(5) Mode (int 0..7), DM(6) Time, DM(7) Func, DM(8) Sens, DM(9) Tone, DM(10) Dry,
//             DM(11) Mix, DM(13) Level (all 0..1).

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

// EQUS

.section pm 0x0c4ef8

PUREWHITEY_ENTRY:
    DM(SAVE + 0) = MODE1;
    BIT CLR MODE1 PEYEN | BDCST9;
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
    DM(SAVE + 19) = I1;
    DM(SAVE + 20) = I2;
    L1 = 0; L2 = 0; L4 = 0;

    // ---- the one slot, as Doom Chug: ours, or free, re-created in place or abandoned; else pass through
    R9 = DM(G_CALLS);
    R9 = R9 + 1;
    DM(G_CALLS) = R9;
    R10 = I0;
    R13 = DM(SLOTS + S_OWNER);
    COMP(R13, R10);
    IF NE JUMP c_claim;
    R11 = DM(P_SLOT, I0);
    R11 = PASS R11;
    IF NE JUMP c_have;
    JUMP c_take;
c_claim:
    R13 = PASS R13;
    IF EQ JUMP c_take;
    R13 = DM(SLOTS + S_LAST);
    R13 = R9 - R13;
    R15 = STALE;
    COMP(R13, R15);
    IF LE JUMP k_pass;
c_take:
    R11 = 1;
    DM(P_SLOT, I0) = R11;
    DM(SLOTS + S_OWNER) = R10;
    R13 = 0;
    I4 = SLOTS + 2;
    R14 = NSTATE;
c_zero:
    DM(I4, 1) = R13;
    R14 = R14 - 1;
    IF NE JUMP c_zero;
    R13 = SEED;                         // reset()
    DM(SLOTS + ST_RND) = R13;
    F13 = 1.0;
    DM(SLOTS + ST_SQF) = F13;
c_have:
    DM(SLOTS + S_LAST) = R9;

    // ---- knobs (clamped as fx_param_clamp does, finite values); I4 = this Mode's column of T_MODE
    R5 = DM(5, I0);                     // Mode 0..7 (R5)
    R14 = 0;
    R5 = MAX(R5, R14);
    R14 = 7;
    R5 = MIN(R5, R14);
    R14 = T_MODE;
    R14 = R5 + R14;
    I4 = R14;
    F8 = DM(7, I0);                     // Func (F12)
    CALL g_cl;
    F12 = PASS F8;
    DM(SLOTS + ST_SQM) = F12;
    R13 = DM(0, I4);                    // passes: the table's; Repeat: 2 + (int)(Func x 15), at most 16
    R5 = PASS R5;
    IF NE JUMP k_r;
    F9 = 15.0;
    F9 = F12 * F9;
    R13 = TRUNC F9;
    R14 = 2;
    R13 = R13 + R14;
    R14 = 16;
    R13 = MIN(R13, R14);
k_r:
    DM(SLOTS + ST_REPS) = R13;
    R13 = DM(8, I4);
    DM(SLOTS + ST_RMASK) = R13;
    R13 = DM(16, I4);
    DM(SLOTS + ST_TRIG) = R13;
    R13 = NOT R13;
    DM(SLOTS + ST_NTRIG) = R13;
    R13 = DM(24, I4);
    DM(SLOTS + ST_SQ) = R13;
    F9 = DM(40, I4);                    // x2 threshold: Func x P2M
    F9 = F12 * F9;
    R13 = TRUNC F9;
    DM(SLOTS + ST_P2) = R13;
    F9 = DM(48, I4);                    // ramp: Func x RA + RB
    F9 = F12 * F9;
    F10 = DM(72, I4);
    F9 = F9 + F10;
    DM(SLOTS + ST_RAMP) = F9;
    F9 = DM(64, I4);                    // speed: SPD x 2^(int)(Func x KM)
    F9 = F12 * F9;
    R13 = TRUNC F9;
    F9 = DM(56, I4);
    F9 = SCALB F9 BY R13;
    DM(SLOTS + ST_SPD) = F9;

    F8 = DM(6, I0);                     // Time -> base = t^2 x 3856 + 240 words; at 0.99 4096, random
    CALL g_cl;
    F9 = F8 * F8;
    F10 = 3856.0;
    F9 = F9 * F10;
    F10 = 240.0;
    F9 = F9 + F10;
    R13 = DM(32, I4);
    F10 = DM(K_099);
    COMP(F8, F10);
    IF LT JUMP k_t;
    F9 = 4096.0;
    R13 = 1;
k_t:
    DM(SLOTS + ST_BASE) = F9;
    DM(SLOTS + ST_RL) = R13;

    F8 = DM(8, I0);                     // Sens -> thr = (1 - s)^2 x 0.25 + 0.002
    CALL g_cl;
    F9 = 1.0;
    F8 = F9 - F8;
    F8 = F8 * F8;
    F9 = 0.25;
    F8 = F8 * F9;
    F9 = DM(K_0002);
    F8 = F8 + F9;
    DM(SLOTS + ST_THR) = F8;

    F8 = DM(9, I0);                     // Tone -> k = t^2 x 0.97 + 0.03
    CALL g_cl;
    F8 = F8 * F8;
    F9 = DM(K_097);
    F8 = F8 * F9;
    F9 = DM(K_003);
    F8 = F8 + F9;
    DM(SLOTS + ST_TK) = F8;

    F8 = DM(13, I0);                    // Level (F12) -> Dry x Level, Mix x Level
    CALL g_cl;
    F12 = PASS F8;
    F8 = DM(10, I0);
    CALL g_cl;
    F8 = F8 * F12;
    DM(SLOTS + ST_DL) = F8;
    F8 = DM(11, I0);
    CALL g_cl;
    F8 = F8 * F12;
    DM(SLOTS + ST_ML) = F8;

    R6 = 16;
s_loop:
    F7 = DM(I1, 1);                     // x, 0 unless |x| <= 8
    F9 = 8.0;
    F8 = ABS F7;
    COMP(F8, F9);
    IF GT R7 = R7 XOR R7;
    F8 = ABS F7;                        // a

    // ---- the attack detector: fire (R9) on a rising edge of envf > 2 envs + thr
    F9 = DM(SLOTS + ST_ENVF);
    F10 = DM(K_SMR);
    F9 = F9 * F10;
    F10 = MAX(F9, F8);
    DM(SLOTS + ST_ENVF) = F10;
    F11 = DM(SLOTS + ST_ENVS);
    F12 = F8 - F11;
    F13 = DM(K_SLOWK);
    F12 = F13 * F12;
    F11 = F11 + F12;
    DM(SLOTS + ST_ENVS) = F11;
    F12 = F11 + F11;
    F13 = DM(SLOTS + ST_THR);
    F12 = F12 + F13;
    R11 = 0;
    COMP(F10, F12);
    IF GT R11 = R11 + 1;
    R9 = DM(SLOTS + ST_PREVC);
    DM(SLOTS + ST_PREVC) = R11;
    R9 = NOT R9;
    R9 = R11 AND R9;

    // ---- LISTEN begins: trigger modes on an attack, the others when idle (stage 0)
    R10 = DM(SLOTS + ST_STAGE);
    R12 = DM(SLOTS + ST_TRIG);
    R12 = R12 AND R9;
    R13 = DM(SLOTS + ST_NTRIG);
    R10 = PASS R10;
    IF EQ R12 = R12 OR R13;
    R12 = PASS R12;
    IF EQ JUMP l_done;
    CALL g_next;
    F9 = DM(SLOTS + ST_BASE);           // the slice's length: base, or a random fraction of it
    R10 = DM(SLOTS + ST_RL);
    R10 = PASS R10;
    IF EQ JUMP l_fix;
    R11 = -24;
    F8 = FLOAT R8 BY R11;
    F9 = F8 * F9;
l_fix:
    R10 = TRUNC F9;
    R11 = LMIN;
    R10 = MAX(R10, R11);
    DM(SLOTS + ST_PLEN) = R10;
    R10 = R10 + 1;                      // listen 4 (plen + 1) samples: at least plen whole words
    R10 = LSHIFT R10 BY 2;
    DM(SLOTS + ST_MN) = R10;
    R10 = 0;
    DM(SLOTS + ST_MI) = R10;
    R10 = -1;
    DM(SLOTS + ST_STAGE) = R10;
l_done:

    F5 = 0.0;                           // wet (F5); R10 = the stage
    R10 = PASS R10;
    IF LE JUMP r_rec;

    // ---- PLAY
    F8 = DM(SLOTS + ST_POS);
    R15 = TRUNC F8;                     // j
    F9 = FLOAT R15;
    F10 = F8 - F9;                      // f
    CALL g_smp;
    F12 = PASS F14;                     // v0
    F11 = DM(SLOTS + ST_LM1);
    COMP(F9, F11);
    IF GE JUMP p_one;
    R15 = R15 + 1;
    CALL g_smp;                         // v1
p_one:
    F14 = F14 - F12;
    F14 = F10 * F14;
    F5 = F12 + F14;
    F14 = F11 - F8;                     // the fades: min(pos, lm1 - pos) / 16, at most 1
    F14 = MIN(F14, F8);
    F12 = 0.0625;
    F14 = F14 * F12;
    F12 = 1.0;
    F14 = MIN(F14, F12);
    F5 = F5 * F14;
    F12 = DM(SLOTS + ST_SP);            // advance; at either end a pass is done
    F8 = F8 + F12;
    F14 = F8 - F11;
    IF GE JUMP p_hi;
    F8 = PASS F8;
    IF GE JUMP p_adv;
    F8 = F8 + F11;
    JUMP p_pass;
p_hi:
    F8 = PASS F14;
p_pass:
    F14 = DM(SLOTS + ST_RAMP);
    F12 = F12 * F14;
    F14 = 2.0;
    F12 = CLIP F12 BY F14;
    DM(SLOTS + ST_SP) = F12;
    R11 = DM(SLOTS + ST_REPS);
    R12 = 16;
    COMP(R11, R12);
    R10 = DM(SLOTS + ST_LEFT);
    IF LT R10 = R10 - 1;
    DM(SLOTS + ST_LEFT) = R10;
    R10 = PASS R10;
    IF GT JUMP p_adv;
    R10 = 0;
    DM(SLOTS + ST_STAGE) = R10;
p_adv:
    DM(SLOTS + ST_POS) = F8;
    JUMP o_sq;

    // ---- RECORD: the mean of two samples, 16 bits, two a word (written at each odd phase, kept at 3)
r_rec:
    R11 = DM(SLOTS + ST_PH);
    F8 = DM(SLOTS + ST_ACC);
    DM(SLOTS + ST_ACC) = F7;
    BTST R11 BY 0;
    IF SZ JUMP r_ph;
    F8 = F8 + F7;                       // the pair's sum, x 2^14
    F9 = DM(K_QMAX2);
    F8 = CLIP F8 BY F9;
    R12 = 14;
    R8 = TRUNC F8 BY R12;
    R12 = DM(SLOTS + ST_PEND);
    R12 = LSHIFT R12 BY -16;
    R12 = R12 OR LSHIFT R8 BY 16;
    DM(SLOTS + ST_PEND) = R12;
    R13 = DM(SLOTS + ST_W);
    R14 = RING0;
    R14 = R13 + R14;
    I4 = R14;
    DM(0, I4) = R12;
    BTST R11 BY 1;
    IF SZ JUMP r_ph;
    R13 = R13 + 1;
    R14 = RING_MASK;
    R13 = R13 AND R14;
    DM(SLOTS + ST_W) = R13;
r_ph:
    R11 = R11 + 1;
    R12 = 3;
    R11 = R11 AND R12;
    DM(SLOTS + ST_PH) = R11;

    // ---- LISTEN (stage -1): the live input, faded at both ends; at its end CAPTURE
    R10 = PASS R10;
    IF EQ JUMP o_sq;
    R10 = DM(SLOTS + ST_MI);
    R11 = DM(SLOTS + ST_MN);
    R12 = R11 - R10;
    R12 = MIN(R12, R10);
    R13 = -5;
    F12 = FLOAT R12 BY R13;
    F13 = 1.0;
    F12 = MIN(F12, F13);
    F5 = F7 * F12;
    R10 = R10 + 1;
    DM(SLOTS + ST_MI) = R10;
    COMP(R10, R11);
    IF LT JUMP o_sq;
    R10 = DM(SLOTS + ST_PLEN);          // the slice: the last plen words recorded
    CALL g_next;
    R11 = DM(SLOTS + ST_W);
    R11 = R11 - R10;
    R12 = RING_MASK;
    R11 = R11 AND R12;
    DM(SLOTS + ST_START) = R11;
    R11 = R10 + R10;
    R11 = R11 - 1;
    F11 = FLOAT R11;
    DM(SLOTS + ST_LM1) = F11;
    F12 = DM(SLOTS + ST_SPD);
    R13 = DM(SLOTS + ST_P2);
    COMP(R8, R13);
    IF LT F12 = F12 + F12;
    DM(SLOTS + ST_SP) = F12;
    R13 = DM(SLOTS + ST_RMASK);         // passes: the mode's, plus a random 0..RMASK
    R13 = R8 AND R13;
    R14 = DM(SLOTS + ST_REPS);
    R13 = R13 + R14;
    DM(SLOTS + ST_LEFT) = R13;
    F14 = 0.0;
    F12 = PASS F12;
    IF LE F14 = PASS F11;
    DM(SLOTS + ST_POS) = F14;
    R13 = 1;
    DM(SLOTS + ST_STAGE) = R13;

    // ---- the square treatment: e x (c + Func x (f - c)) x 0.7
o_sq:
    R10 = DM(SLOTS + ST_SQ);
    R10 = PASS R10;
    IF EQ JUMP o_tone;
    F8 = ABS F5;
    F9 = DM(SLOTS + ST_SQE);
    F10 = DM(K_SQR);
    F9 = F9 * F10;
    F10 = MAX(F9, F8);
    DM(SLOTS + ST_SQE) = F10;           // e
    F11 = DM(K_01);
    F11 = F10 * F11;                    // h = e / 10
    F12 = DM(SLOTS + ST_SQC);
    F13 = PASS F12;
    F14 = 1.0;
    COMP(F5, F11);
    IF GT F13 = PASS F14;
    F14 = -F11;
    COMP(F5, F14);
    F14 = -1.0;
    IF LT F13 = PASS F14;
    DM(SLOTS + ST_SQC) = F13;           // c
    COMP(F13, F12);
    F14 = DM(SLOTS + ST_SQF);
    IF GT F14 = -F14;
    DM(SLOTS + ST_SQF) = F14;           // f, toggled as c rises
    F14 = F14 - F13;
    F12 = DM(SLOTS + ST_SQM);
    F14 = F14 * F12;
    F14 = F13 + F14;
    F14 = F14 * F10;
    F12 = DM(K_07);
    F5 = F14 * F12;

    // ---- Tone, then out = Dry Level x + Mix Level wet
o_tone:
    F8 = DM(SLOTS + ST_LP);
    F9 = F5 - F8;
    F10 = DM(SLOTS + ST_TK);
    F9 = F10 * F9;
    F8 = F8 + F9;
    DM(SLOTS + ST_LP) = F8;
    F9 = DM(SLOTS + ST_DL);
    F9 = F9 * F7;
    F10 = DM(SLOTS + ST_ML);
    F10 = F10 * F8;
    F9 = F9 + F10;
    F10 = ABS F9;
    F11 = 8.0;
    COMP(F10, F11);
    IF GT R9 = R9 XOR R9;
    DM(I2, 1) = R9;
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
    I1 = DM(SAVE + 19);
    I2 = DM(SAVE + 20);
    MODE1 = DM(SAVE + 0);
    NOP;
    RTS (LR);

// ---- F14 = sample R15 (>= 0) of the slice: the word ST_START + R15 / 2, its low half if R15 is even, as
//      q / 32768. Uses R13, R14, I4.
g_smp:
    R14 = LSHIFT R15 BY -1;
    R13 = DM(SLOTS + ST_START);
    R14 = R14 + R13;
    R13 = RING_MASK;
    R14 = R14 AND R13;
    R13 = RING0;
    R14 = R14 + R13;
    I4 = R14;
    R14 = DM(0, I4);
    BTST R15 BY 0;
    IF NOT SZ JUMP g_hi;
    R14 = LSHIFT R14 BY 16;
g_hi:
    R14 = ASHIFT R14 BY -16;
    R13 = -15;
    F14 = FLOAT R14 BY R13;
    RTS;

// ---- R8 = next(): xorshift32 on ST_RND, then >> 8. Uses R8, R15.
g_next:
    R8 = DM(SLOTS + ST_RND);
    R15 = LSHIFT R8 BY 13;
    R8 = R8 XOR R15;
    R15 = LSHIFT R8 BY -17;
    R8 = R8 XOR R15;
    R15 = LSHIFT R8 BY 5;
    R8 = R8 XOR R15;
    DM(SLOTS + ST_RND) = R8;
    R8 = LSHIFT R8 BY -8;
    RTS;

// ---- F8 clamped to 0..1. Uses F9.
g_cl:
    F9 = 0.0;
    F8 = MAX(F8, F9);
    F9 = 1.0;
    F8 = MIN(F8, F9);
    RTS;
