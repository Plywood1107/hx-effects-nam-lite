// hostprobe_kernel.asm - the host probe ("Probe") for the HX Effects SHARC: a port of effects/hostprobe/hostprobe.c,
// checked bit for bit against it in ssim by hostprobe_kernel.py, which puts the .equ block, the sine table and the
// slots at "EQUS". Meant to run as an overlay on Drum Chapel's host (the mono Ratchet) in the probe image only.
//
// Conventions as the other kernels (effects/README.md): once per 16-sample block, I0 = the instance's DM block,
// I1 = 16 inputs, I2 = 16 outputs, I3 = the host's call-list entry; R0-R15, I1-I4 and MODE1 come back unchanged;
// L1-L4 left 0; no hardware loops; DM(3, I0) never touched; only P_SLOT (12) written in the instance block; state
// in one of NSLOTS claimed slots. The one other write: the memory test's two words in the instance's SDRAM block,
// only when DM(2, I3) words 6 and 7 describe a block of the size the graph asked for (hostprobe.h).
//
// Knob words: DM(6) Mode (int 0..2: Report, Pass, Load), DM(13) Level 0..1. (DM(5), the synced Time, is not read.)
// Read only, outside the instance: DM(IDLE_ADDR), the DSP's idle word, each call (its lowest this frame in ST_IDLEMIN).
// Registers in the transmitter loop: R10 the symbol's sample, R11 the symbol, R12 the sine phase, R13 its step,
// F14 Level, R15 the samples left (Mode is in the slot, ST_MODE); latch (CALL) uses R0-R9 and I4 only.

.equ PEYEN,    0x200000
.equ BDCST9,   0x400000

// EQUS

.section pm 0x0c4ef8

HOSTPROBE_ENTRY:
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
    DM(SAVE + 18) = I3;                 // the host's call-list entry, read again by latch
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
    R13 = -1;                           // the idle word's lowest: none yet (0xffffffff)
    DM(ST_IDLEMIN, I3) = R13;
c_have:
    DM(S_LAST, I3) = R9;

    // ---- knobs (clamped as fx_param_clamp does)
    R14 = DM(6, I0);                    // Mode, kept in the slot (the loop has no register left for it)
    R8 = 0;
    R14 = MAX(R14, R8);
    R8 = 2;
    R14 = MIN(R14, R8);
    DM(ST_MODE, I3) = R14;
    F14 = DM(13, I0);                   // Level
    F8 = 0.0;
    F14 = MAX(F14, F8);
    F8 = 1.0;
    F14 = MIN(F14, F8);
    R8 = DM(ST_CALLS, I3);
    R8 = R8 + 1;
    DM(ST_CALLS, I3) = R8;
    R8 = DM(IDLE_ADDR);                 // the DSP's idle word: keep this frame's lowest (unsigned)
    R7 = DM(ST_IDLEMIN, I3);
    COMPU(R8, R7);
    IF GE JUMP i_keep;
    DM(ST_IDLEMIN, I3) = R8;
i_keep:

    // ---- the meter: the 16 inputs, before any output is written
    F0 = DM(ST_PEAK, I3);
    F1 = 0.0;                           // the call's sum of squares
    F2 = 0.0;                           // and sum
    R15 = 16;
m_l:
    F7 = DM(I1, 1);
    F8 = ABS F7;
    F0 = MAX(F0, F8);
    F8 = F7 * F7;
    F1 = F1 + F8;
    F2 = F2 + F7;
    R15 = R15 - 1;
    IF NE JUMP m_l;
    I1 = DM(SAVE + 19);
    DM(ST_PEAK, I3) = F0;
    F8 = DM(ST_SQ, I3);
    F8 = F8 + F1;
    DM(ST_SQ, I3) = F8;
    F9 = DM(ST_SUM, I3);
    F9 = F9 + F2;
    DM(ST_SUM, I3) = F9;
    R7 = DM(ST_WCALLS, I3);
    R7 = R7 + 1;
    R6 = WIN_CALLS;
    COMP(R7, R6);
    IF LT JUMP m_open;
    DM(ST_LPEAK, I3) = F0;              // the window, latched
    DM(ST_LSQ, I3) = F8;
    DM(ST_LSUM, I3) = F9;
    R6 = DM(ST_WIN, I3);
    R6 = R6 + 1;
    DM(ST_WIN, I3) = R6;
    DM(ST_LWIN, I3) = R6;
    R7 = 0;
    DM(ST_PEAK, I3) = R7;
    DM(ST_SQ, I3) = R7;
    DM(ST_SUM, I3) = R7;
m_open:
    DM(ST_WCALLS, I3) = R7;

    // ---- the transmitter
    R10 = DM(ST_SPOS, I3);
    R11 = DM(ST_SIDX, I3);
    R12 = DM(ST_PH, I3);
    R13 = DM(ST_STEP, I3);
    R15 = 16;
t_l:
    R10 = PASS R10;
    IF NE JUMP t_sym;
    R11 = PASS R11;
    IF NE JUMP t_kind;
    CALL latch;
t_kind:                                 // this frame's geometry (latch set it by the Mode)
    R8 = DM(ST_FPIL, I3);
    COMP(R11, R8);
    IF GE JUMP t_bits;
    R13 = 6;
    JUMP t_sym;
t_bits:
    R8 = DM(ST_FPB, I3);
    COMP(R11, R8);
    IF GE JUMP t_gap;
    R8 = DM(ST_FPIL, I3);
    R8 = R11 - R8;                      // the bit
    R9 = LSHIFT R8 BY -5;               // its word
    R0 = ST_FR0;
    R9 = R9 + R0;
    R0 = I3;
    R9 = R9 + R0;
    I4 = R9;
    R9 = DM(0, I4);
    R0 = 31;
    R8 = R8 AND R0;
    R8 = R8 - R0;                       // -(31 - (bit & 31))
    R9 = LSHIFT R9 BY R8;
    R0 = 1;
    R9 = R9 AND R0;
    R13 = R9 + 1;
    R13 = LSHIFT R13 BY 1;              // 2 (a 0) or 4 (a 1)
    JUMP t_sym;
t_gap:
    R13 = 0;
t_sym:
    F6 = DM(I1, 1);                     // this sample's input (Pass; read after latch, which uses R0-R9)
    F7 = 0.0;
    R13 = PASS R13;
    IF EQ JUMP t_ph;
    R8 = T_SIN;
    R8 = R8 + R12;
    I4 = R8;
    F7 = DM(0, I4);
    F7 = F7 * F14;
t_ph:
    R12 = R12 + R13;
    R8 = NSIN;
    COMP(R12, R8);
    IF LT JUMP t_pos;
    R12 = R12 - R8;
t_pos:
    R10 = R10 + 1;
    R8 = DM(ST_FSYM, I3);
    COMP(R10, R8);
    IF LT JUMP t_out;
    R10 = 0;
    R11 = R11 + 1;
    R8 = DM(ST_FNSYM, I3);
    COMP(R11, R8);
    IF LT JUMP t_out;
    R11 = 0;
    R8 = DM(ST_FRAMES, I3);
    R8 = R8 + 1;
    DM(ST_FRAMES, I3) = R8;
t_out:
    R8 = DM(ST_MODE, I3);               // Pass (1) only
    R0 = 1;
    COMP(R8, R0);
    IF NE JUMP t_w;
    F7 = F6;
t_w:
    DM(I2, 1) = F7;
    R15 = R15 - 1;
    IF NE JUMP t_l;
    DM(ST_SPOS, I3) = R10;
    DM(ST_SIDX, I3) = R11;
    DM(ST_PH, I3) = R12;
    DM(ST_STEP, I3) = R13;
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

// ---- the frame's first sample: the memory test, then the frame (hostprobe.c latch()). Uses R0-R9 and I4.
latch:
    R0 = DM(SAVE + 18);                 // the host's call-list entry
    I4 = R0;
    R1 = DM(2, I4);                     // the instance struct
    I4 = R1;
    R2 = DM(6, I4);                     // its SDRAM block: start
    R3 = DM(7, I4);                     // end
    R4 = 0x200000;
    COMPU(R2, R4);
    IF LT JUMP l_frame;
    R4 = 0x1000000;
    COMPU(R3, R4);
    IF GT JUMP l_frame;
    R4 = R3 - R2;
    R5 = SDR_REQ;
    COMPU(R4, R5);
    IF LT JUMP l_frame;
    R5 = SDR_REQ + 0x400;
    COMPU(R4, R5);
    IF GT JUMP l_frame;
    R3 = R3 - 1;                        // the block's last word
    R5 = DM(ST_MSTAT, I3);
    R5 = PASS R5;
    IF EQ JUMP l_write;
    I4 = R2;
    R6 = DM(0, I4);
    R7 = PAT_A;
    COMP(R6, R7);
    IF NE JUMP l_bad;
    I4 = R3;
    R6 = DM(0, I4);
    R7 = PAT_B;
    COMP(R6, R7);
    IF EQ JUMP l_write;
l_bad:
    R6 = DM(ST_MBAD, I3);
    R6 = R6 + 1;
    DM(ST_MBAD, I3) = R6;
l_write:
    R5 = 1;
    DM(ST_MSTAT, I3) = R5;
    I4 = R2;
    R7 = PAT_A;
    DM(0, I4) = R7;
    I4 = R3;
    R7 = PAT_B;
    DM(0, I4) = R7;
l_frame:
    R5 = DM(ST_MODE, I3);
    R6 = 2;
    COMP(R5, R6);
    IF EQ JUMP l_load;
    R5 = SYM;                           // Report and Pass: the long frame (hostprobe.h)
    DM(ST_FSYM, I3) = R5;
    R5 = NPILOT;
    DM(ST_FPIL, I3) = R5;
    R5 = NPILOT + NBITS;
    DM(ST_FPB, I3) = R5;
    R5 = NSYM;
    DM(ST_FNSYM, I3) = R5;
    R9 = 0;                             // the sum of words 1..32
    R0 = SYNC;
    DM(ST_FR0, I3) = R0;
    R0 = MAGIC;
    DM(ST_FR1, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_FRAMES, I3);
    DM(ST_FR2, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_CALLS, I3);
    DM(ST_FR3, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_LPEAK, I3);
    DM(ST_FR4, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_LSQ, I3);
    DM(ST_FR5, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_LSUM, I3);
    DM(ST_FR6, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_LWIN, I3);
    DM(ST_FR7, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_MSTAT, I3);
    DM(ST_FR8, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_MBAD, I3);
    DM(ST_FR9, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(SAVE + 18);
    I4 = R0;
    R0 = DM(0, I4);
    DM(ST_FR10, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(1, I4);
    DM(ST_FR11, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(2, I4);
    DM(ST_FR12, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(3, I4);
    DM(ST_FR13, I3) = R0;
    R9 = R9 + R0;
    I4 = R1;                            // the instance struct, words 0..15
    R0 = DM(0, I4);
    DM(ST_FR14, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(1, I4);
    DM(ST_FR15, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(2, I4);
    DM(ST_FR16, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(3, I4);
    DM(ST_FR17, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(4, I4);
    DM(ST_FR18, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(5, I4);
    DM(ST_FR19, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(6, I4);
    DM(ST_FR20, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(7, I4);
    DM(ST_FR21, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(8, I4);
    DM(ST_FR22, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(9, I4);
    DM(ST_FR23, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(10, I4);
    DM(ST_FR24, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(11, I4);
    DM(ST_FR25, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(12, I4);
    DM(ST_FR26, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(13, I4);
    DM(ST_FR27, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(14, I4);
    DM(ST_FR28, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(15, I4);
    DM(ST_FR29, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_IDLEMIN, I3);            // the idle word's lowest since the last frame, then reset
    DM(ST_FR30, I3) = R0;
    R9 = R9 + R0;
    R1 = -1;
    DM(ST_IDLEMIN, I3) = R1;
    R0 = WIN_SAMPLES;
    DM(ST_FR31, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(IDLE_ADDR);                 // the idle word now
    DM(ST_FR32, I3) = R0;
    R9 = R9 + R0;
    DM(ST_FR33, I3) = R9;
    RTS;

l_load:                                 // Load: six words of long symbols (hostprobe.h, HOSTPROBE_L*)
    R5 = LSYM;
    DM(ST_FSYM, I3) = R5;
    R5 = LPILOT;
    DM(ST_FPIL, I3) = R5;
    R5 = LPILOT + LNBITS;
    DM(ST_FPB, I3) = R5;
    R5 = LNSYM;
    DM(ST_FNSYM, I3) = R5;
    R0 = SYNC;
    DM(ST_FR0, I3) = R0;
    R0 = MAGIC_L;
    DM(ST_FR1, I3) = R0;
    R9 = R0;
    R0 = DM(ST_FRAMES, I3);
    DM(ST_FR2, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(IDLE_ADDR);
    DM(ST_FR3, I3) = R0;
    R9 = R9 + R0;
    R0 = DM(ST_IDLEMIN, I3);
    DM(ST_FR4, I3) = R0;
    R9 = R9 + R0;
    R1 = -1;
    DM(ST_IDLEMIN, I3) = R1;
    DM(ST_FR5, I3) = R9;
    RTS;
