; =============================================================================
; dgnt_bg.asm — the colossus's BG layers (docs/dungeons/21)
; =============================================================================
; Mode 1. BG1 and BG2 are the boss's two page-flipped buffers; BG3 is the room's floor. The tick fills a 4-byte DP
; shadow from the score (TM, BG VOFS) and the NMI hook commits it.

BG_REGS = $4300 + ES_D_BG_UP_CH * 16
FIXED_SRC = $08                   ; DMAP bit 3: the A-bus address does not step (a constant fill)

; --- dgnt_bg_arm: clear, floor, palettes, registers ---------------------------------------------------------------
; CONTRACT dgnt_bg_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      both boss tilemaps zeroed (power-on VRAM is random: rule 5), the floor's CHR + map in BG3's regions, the boss
;             palette (CGRAM 32..47) and floor palette (0..3), BGMODE 1, BG1SC/BG2SC/BG3SC, the CHR bases, BG3 scroll 0
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked (the scene_mgr enter contract). TM is dgnt_bg_commit's
;   tail:     rts
dgnt_bg_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_bg_arm"
    sep #$20
    .a8
    lda #$80
    sta a:$2115                     ; VMAIN: +1 word after the high byte
    lda #(ES_D_BG_UP_DMAP | FIXED_SRC)
    sta a:BG_REGS + 0               ; DMAP: mode 1, the source address fixed: a fill
    lda #ES_D_BG_UP_BBAD
    sta a:BG_REGS + 1
    lda #^dgnt_pool0_bin
    sta a:BG_REGS + 4               ; A1B: the pool's first block is the zero block
    rep #$20
    .a16
    lda #ES_V_BGA_MAP
    sta a:$2116
    lda #.loword(dgnt_pool0_bin)
    sta a:BG_REGS + 2
    lda #(ES_V_BGA_MAP_WORDS * 2)
    sta a:BG_REGS + 5
    sep #$20
    .a8
    lda #(1 << ES_D_BG_UP_CH)
    sta a:$420B                     ; BG1's tilemap: zeros
    rep #$20
    .a16
    lda #ES_V_BGB_MAP
    sta a:$2116
    lda #(ES_V_BGB_MAP_WORDS * 2)
    sta a:BG_REGS + 5
    sep #$20
    .a8
    lda #(1 << ES_D_BG_UP_CH)
    sta a:$420B                     ; BG2's tilemap: zeros
    lda #ES_D_BG_UP_DMAP
    sta a:BG_REGS + 0               ; back to a stepping transfer
    lda #^dgnt_floor_bin
    sta a:BG_REGS + 4
    rep #$20
    .a16
    lda #ES_V_FL_CHR
    sta a:$2116
    lda #.loword(dgnt_floor_bin)
    sta a:BG_REGS + 2
    lda #(ES_V_FL_CHR_WORDS * 2)
    sta a:BG_REGS + 5
    sep #$20
    .a8
    lda #(1 << ES_D_BG_UP_CH)
    sta a:$420B                     ; the floor's 2bpp tiles
    rep #$20
    .a16
    lda #ES_V_FL_MAP
    sta a:$2116
    lda #(.loword(dgnt_floor_bin) + ES_V_FL_CHR_WORDS * 2)
    sta a:BG_REGS + 2
    lda #(ES_V_FL_MAP_WORDS * 2)
    sta a:BG_REGS + 5
    sep #$20
    .a8
    lda #(1 << ES_D_BG_UP_CH)
    sta a:$420B                     ; the floor's map
    ; ---- palettes: the boss's 16 words at CGRAM 32, the floor's 4 at 0 ----------------------------------------
    lda #ES_C_BOSS_PAL
    sta a:$2121
    rep #$20
    .a16
    ldx #0
@bpal:
    .a16
    .i16
    lda f:dgnt_pal_bin, x
    sep #$20
    .a8
    sta a:$2122
    xba
    sta a:$2122
    rep #$20
    .a16
    inx
    inx
    cpx #(ES_C_BOSS_PAL_WORDS * 2)
    bcc @bpal
    sep #$20
    .a8
    lda #ES_C_FLOOR_PAL
    sta a:$2121
    rep #$20
    .a16
    ldx #(ES_C_BOSS_PAL_WORDS * 2)
@fpal:
    .a16
    .i16
    lda f:dgnt_pal_bin, x
    sep #$20
    .a8
    sta a:$2122
    xba
    sta a:$2122
    rep #$20
    .a16
    inx
    inx
    cpx #((ES_C_BOSS_PAL_WORDS + ES_C_FLOOR_PAL_WORDS) * 2)
    bcc @fpal
    ; ---- the registers ----------------------------------------------------------------------------------------------
    sep #$20
    .a8
    lda #1
    sta a:$2105                     ; BGMODE 1
    lda #ES_V_BGA_MAP_SC_BASE
    sta a:$2107                     ; BG1SC: the claimed base, size 32x64
    lda #ES_V_BGB_MAP_SC_BASE
    sta a:$2108                     ; BG2SC
    lda #ES_V_FL_MAP_SC_BASE
    sta a:$2109                     ; BG3SC
    lda #(ES_V_BGA_CHR_NBA | (ES_V_BGB_CHR_NBA << 4))
    sta a:$210B                     ; BG12NBA: BG1's CHR base low, BG2's high
    lda #ES_V_FL_CHR_NBA
    sta a:$210C                     ; BG34NBA: BG3's base low
    stz a:$210D
    stz a:$210D                     ; BG1HOFS (write-twice): 0
    stz a:$210F
    stz a:$210F                     ; BG2HOFS: 0
    stz a:$2111
    stz a:$2111                     ; BG3HOFS: 0
    stz a:$2112
    stz a:$2112                     ; BG3VOFS: 0
    rep #$20
    .a16
    rts

; --- dgnt_bg_commit: the shadow -> TM and both boss layers' vertical scroll -----------------------------------------------
; CONTRACT dgnt_bg_commit
;   entry:    A8 I16 DB=0
;   exit:     A8 I16
;   in:       the 4-byte shadow ES_BGSH: +0 TM, +2 BG VOFS
;   out:      TM written (which boss layer is shown), BG1VOFS and BG2VOFS written, each LOW byte first
;   clobbers: A, N, Z
;   assumes:  VBlank, from sm_nmi_hook, in that hook's A8/I16 convention
;   tail:     rts
dgnt_bg_commit:
    .a8
    .i16
    SF_ASSERT_WIDTH 8, 16, "dgnt_bg_commit"
    lda z:ES_BGSH + 0
    sta a:$212C                     ; TM: BG1 or BG2, plus BG3 and OBJ
    lda z:ES_BGSH + 2
    sta a:$210E
    lda z:ES_BGSH + 3
    sta a:$210E                     ; BG1VOFS
    lda z:ES_BGSH + 2
    sta a:$2110
    lda z:ES_BGSH + 3
    sta a:$2110                     ; BG2VOFS
    rts
