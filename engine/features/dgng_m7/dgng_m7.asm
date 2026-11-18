; =============================================================================
; dgng_m7.asm — the giant boss's Mode 7 plane and its matrix commit (docs/dungeons/20)
; =============================================================================
; One DMA uploads the whole interleaved plane (even bytes to the tilemap, odd to the 8bpp CHR: mode 1 drives
; VMDATAL then VMDATAH). The matrix is a 16-byte DP shadow the tick fills from the score and the NMI hook commits.

M7_REGS = $4300 + ES_D_M7_UP_CH * 16

; --- dgng_m7_arm: the plane, its palette and the mode registers ----------------------------------------------------
; CONTRACT dgng_m7_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      the Mode 7 plane in VRAM, BG palette 0-15 (word 0 = the backdrop), BGMODE 7, TM = BG1 + OBJ, M7SEL 0
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked (the scene_mgr enter contract)
;   tail:     rts
dgng_m7_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_m7_arm"
    sep #$20
    .a8
    lda #$80
    sta a:$2115                     ; VMAIN: +1 word after the high byte
    lda #ES_D_M7_UP_DMAP
    sta a:M7_REGS + 0               ; DMAP: A->B, 2 registers (mode 1) = the interleave
    lda #ES_D_M7_UP_BBAD
    sta a:M7_REGS + 1               ; BBAD: VMDATAL, so B+1 = VMDATAH
    rep #$20
    .a16
    stz a:$2116                     ; VMADD = 0: the Mode 7 base is fixed
    lda #.loword(dgng_m7_bin)
    sta a:M7_REGS + 2               ; A1T
    lda #ES_R_DGNG_M7_ROM_SIZE
    sta a:M7_REGS + 5               ; DAS, armed for this one transfer
    sep #$20
    .a8
    lda #^dgng_m7_bin
    sta a:M7_REGS + 4               ; A1B
    lda #(1 << ES_D_M7_UP_CH)
    sta a:$420B                     ; fire
    lda #ES_C_M7_PAL
    sta a:$2121                     ; CGADD = the claim's base (0, by contract)
    rep #$20
    .a16
    ldx #0
@pal:
    .a16
    .i16
    lda f:dgng_pal_bin, x
    sep #$20
    .a8
    sta a:$2122
    xba
    sta a:$2122
    rep #$20
    .a16
    inx
    inx
    cpx #(ES_C_M7_PAL_WORDS * 2)
    bcc @pal
    sep #$20
    .a8
    lda #7
    sta a:$2105                     ; BGMODE 7
    lda #((1 << 0) | (1 << 4))
    sta a:$212C                     ; TM: BG1 (the plane) and OBJ
    stz a:$211A                     ; M7SEL: the plane wraps, no flip
    rep #$20
    .a16
    rts

; --- dgng_m7_commit: the shadow -> the eight Mode 7 ports ---------------------------------------------------------------
; CONTRACT dgng_m7_commit
;   entry:    A8 I16 DB=0
;   exit:     A8 I16
;   in:       the 16-byte shadow ES_M7SH
;   out:      M7A-M7D, M7X, M7Y, M7HOFS, M7VOFS written through, each LOW byte first (all eight are write-twice)
;   clobbers: A, N, Z
;   assumes:  VBlank, from sm_nmi_hook, in that hook's A8/I16 convention
;   tail:     rts
dgng_m7_commit:
    .a8
    .i16
    SF_ASSERT_WIDTH 8, 16, "dgng_m7_commit"
    lda z:ES_M7SH + 0
    sta a:$211B
    lda z:ES_M7SH + 1
    sta a:$211B                     ; M7A
.ifdef DGNG_PLANT
    ; PLANTED FAULT (tests/test_dgn_giant.py, `make dgn_giant_plant`): B and C swapped, so the matrix is the
    ; TRANSPOSE: the plane turns the wrong way. Never assembled into the real ROM.
    lda z:ES_M7SH + 4
    sta a:$211C
    lda z:ES_M7SH + 5
    sta a:$211C                     ; M7B <- C
    lda z:ES_M7SH + 2
    sta a:$211D
    lda z:ES_M7SH + 3
    sta a:$211D                     ; M7C <- B
.else
    lda z:ES_M7SH + 2
    sta a:$211C
    lda z:ES_M7SH + 3
    sta a:$211C                     ; M7B
    lda z:ES_M7SH + 4
    sta a:$211D
    lda z:ES_M7SH + 5
    sta a:$211D                     ; M7C
.endif
    lda z:ES_M7SH + 6
    sta a:$211E
    lda z:ES_M7SH + 7
    sta a:$211E                     ; M7D
    lda z:ES_M7SH + 8
    sta a:$211F
    lda z:ES_M7SH + 9
    sta a:$211F                     ; M7X, the pivot
    lda z:ES_M7SH + 10
    sta a:$2120
    lda z:ES_M7SH + 11
    sta a:$2120                     ; M7Y
    lda z:ES_M7SH + 12
    sta a:$210D
    lda z:ES_M7SH + 13
    sta a:$210D                     ; M7HOFS (the BG1HOFS port)
    lda z:ES_M7SH + 14
    sta a:$210E
    lda z:ES_M7SH + 15
    sta a:$210E                     ; M7VOFS
    rts
