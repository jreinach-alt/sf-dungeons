; =============================================================================
; dgnb_obj.asm — the boss-battle spike's OBJ layer (docs/dungeons/18)
; =============================================================================
; A 64x64 boss (four 32x32 OBJs), two players that WALK, IDLE and ATTACK, and two small enemies.
;
; THE STREAM. The boss and each player have ONE VRAM slot, rewritten in VBlank when the frame the main
; thread WANTS (US_WANT_*) differs from the frame VRAM HAS (US_HAVE_*). OAM names never change, only the
; CHR behind them, so the OAM DMA and the CHR DMA land in the same VBlank and cannot disagree.
;   boss  8 tile rows x 256 B  (8 DMAs)   VRAM tile cols 0-7,  rows 0-7
;   P1    4 tile rows x 128 B  (4 DMAs)   cols 8-11, rows 0-3
;   P2    4 tile rows x 128 B  (4 DMAs)   cols 12-15, rows 0-3
; A player's slot image is a 32x32 whether it is drawn as two 16x16 OBJs (idle, walk) or one 32x32 (attack).
;
; THE MEASUREMENT. The last thing the NMI hook does is latch the PPU's V counter: US_VEND is the scanline
; the stream finished on, US_VMAX its maximum. VBlank is V = 225..261; a stream that is still running at
; V = 262 writes VRAM into the picture. docs/dungeons/18 reads these two words every frame.

STREAM_REGS = $4300 + ES_H_DGNBS_CH * 16
UP_REGS = $4300 + ES_D_OBJ_UP_CH * 16
OBJ0 = ES_OAM_SHADOW + ES_O_ACTORS * 4
OBJ_HI = ES_OAM_SHADOW + ES_OAM_SHADOW_SIZE - 32 + (ES_O_ACTORS / 4)
OBJ_PARK_Y = 240
VRAM_ROW = 16 * 16                ; words in one 16-tile row of the OBJ name table
VRAM_T1 = 256 * 16                ; words from the claim base to name table 1 (OBSEL gap 0: contiguous)
VRAM_P1 = ES_V_OBJ_CHR + DGNB_NAME_P1 * 16
VRAM_P2 = ES_V_OBJ_CHR + DGNB_NAME_P2 * 16
OBSEL_MODE3 = 3 << 5              ; small 16x16 / large 32x32
HI_BOSS_PAIR = %10101010          ; four large, X9 clear (the boss never leaves x 96..160)
HERO_OAM_Y = DGNB_HERO_Y - (DGNB_H_AY + 1)   ; an OBJ's first line is scanline Y+1
.assert ES_O_ACTORS .MOD 4 = 0, error, "dgnb_obj: the actors must start a hi-table byte"
.assert ES_O_ACTORS_SPRITES = 12, error, "dgnb_obj: three whole hi-table bytes"
.assert DGNB_BOSS_FRAMES_A_FACING * 2048 = ES_R_DGNB_BOSS_DOWN_ROM_SIZE, error, "dgnb_obj: a facing's frames fill its claim"
.assert DGNB_BOSS_FRAMES_A_FACING * 2048 = ES_R_DGNB_BOSS_RIGHT_ROM_SIZE, error, "dgnb_obj: a facing's frames fill its claim"
.assert ES_V_OBJ_CHR_WORDS = 512 * 16, error, "dgnb_obj: both OBJ name tables"
; x positions stay in 0..255 so every X9 bit is a constant 0 (asserted, not assumed)
.assert DGNB_BOSS_X - DGNB_BOSS_AX >= 0 && DGNB_BOSS_X + 32 <= 256, error, "dgnb_obj: the boss crosses x = 0 or 256"
.assert DGNB_P1_X - DGNB_H_ATK_AX >= 0 && DGNB_P2_X + 16 <= 256, error, "dgnb_obj: a player crosses an edge"
.assert DGNB_EA_X0 - DGNB_EA_AX >= 0 && DGNB_EB_X0 + 16 <= 256, error, "dgnb_obj: an enemy crosses an edge"

; --- HERO_PLACE: one player into its two OAM slots -----------------------------------------------
; Idle / walk (frame < ATK0): two stacked 16x16 OBJs. Attack: ONE 32x32 and the second slot parked.
; The attack's box is wider, and its anchor differs, so x changes with the frame type.
; In/out: A16 I16. Ors the slot's LARGE bit into US_TMP (hi byte 0).
; WIDTH-RISK: entry A16 I16, exit A16 I16 (each arm narrows to A8 for its byte stores and widens back before `done`)
.macro HERO_PLACE slot, footx, want, attr, sax, lax, name, largebit
    .local atk, done
    lda z:want
    cmp #DGNB_H_ATK0
    bcs atk
    sep #$20
    .a8
    lda #(footx - sax)
    sta a:OBJ0 + (slot) * 4 + 0
    sta a:OBJ0 + (slot + 1) * 4 + 0
    lda #HERO_OAM_Y
    sta a:OBJ0 + (slot) * 4 + 1
    lda #(HERO_OAM_Y + 16)
    sta a:OBJ0 + (slot + 1) * 4 + 1
    lda #name
    sta a:OBJ0 + (slot) * 4 + 2
    lda #(name + 32)
    sta a:OBJ0 + (slot + 1) * 4 + 2
    lda #attr
    sta a:OBJ0 + (slot) * 4 + 3
    sta a:OBJ0 + (slot + 1) * 4 + 3
    rep #$20
    .a16
    bra done
atk:
    .a16
    .i16
    sep #$20
    .a8
    lda #(footx - lax)
    sta a:OBJ0 + (slot) * 4 + 0
    lda #HERO_OAM_Y
    sta a:OBJ0 + (slot) * 4 + 1
    lda #name
    sta a:OBJ0 + (slot) * 4 + 2
    lda #attr
    sta a:OBJ0 + (slot) * 4 + 3
    lda #OBJ_PARK_Y
    sta a:OBJ0 + (slot + 1) * 4 + 1
    rep #$20
    .a16
    lda z:US_TMP
    ora #largebit
    sta z:US_TMP
done:
    .a16
    .i16
.endmacro

; --- dgnb_obj_arm: resident CHR + palettes + OBSEL ------------------------------------------------
; CONTRACT dgnb_obj_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      OBJ name table 1 (both enemies), OBJ palettes 0-3, OBSEL
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked (the scene_mgr enter contract). Name table 0 is the
;             STREAMED half and is filled by dgnb_nmi_stream, not here
;   tail:     rts
dgnb_obj_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnb_obj_arm"
    sep #$20
    .a8
    lda #$80
    sta a:$2115                     ; VMAIN: +1 word after the high byte
    rep #$20
    .a16
    lda #(ES_V_OBJ_CHR + VRAM_T1)
    sta a:$2116                     ; VMADD = name table 1
    lda #.loword(dgnb_res_bin)
    sta a:UP_REGS + 2
    lda #ES_R_DGNB_RES_ROM_SIZE
    sta a:UP_REGS + 5
    sep #$20
    .a8
    lda #^dgnb_res_bin
    sta a:UP_REGS + 4
    lda #ES_D_OBJ_UP_DMAP
    sta a:UP_REGS + 0
    lda #ES_D_OBJ_UP_BBAD
    sta a:UP_REGS + 1
    lda #(1 << ES_D_OBJ_UP_CH)
    sta a:$420B
    lda #ES_C_OBJ_PAL
    sta a:$2121
    rep #$20
    .a16
    ldx #0
@pal:
    .a16
    .i16
    lda f:dgnb_pal_bin, x
    sep #$20
    .a8
    sta a:$2122
    xba
    sta a:$2122
    rep #$20
    .a16
    inx
    inx
    cpx #ES_R_DGNB_PAL_ROM_SIZE
    bcc @pal
    sep #$20
    .a8
    lda #(OBSEL_MODE3 | ES_V_OBJ_CHR_OBSEL_BASE)
    sta a:$2101
    rep #$20
    .a16
    rts

; --- dgnb_obj_const: the entries that never change ------------------------------------------------
; CONTRACT dgnb_obj_const
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      the boss's four OAM entries, hi bytes 1 and 2, slots 10-11 parked
;   clobbers: A, N, Z, C
;   assumes:  once, from the scene's enter
;   tail:     rts
dgnb_obj_const:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnb_obj_const"
    sep #$20
    .a8
    ; the boss: TL, TR, BL, BR, each a 32x32 at its quadrant of the 64x64 frame
    BOSS_Q = DGNB_SL_BOSS
    BOSS_X0 = DGNB_BOSS_X - DGNB_BOSS_AX
    BOSS_Y0 = DGNB_BOSS_Y - (DGNB_BOSS_AY + 1)
    lda #BOSS_X0
    sta a:OBJ0 + (BOSS_Q + 0) * 4 + 0
    sta a:OBJ0 + (BOSS_Q + 2) * 4 + 0
    lda #(BOSS_X0 + 32)
    sta a:OBJ0 + (BOSS_Q + 1) * 4 + 0
    sta a:OBJ0 + (BOSS_Q + 3) * 4 + 0
    lda #BOSS_Y0
    sta a:OBJ0 + (BOSS_Q + 0) * 4 + 1
    sta a:OBJ0 + (BOSS_Q + 1) * 4 + 1
    lda #(BOSS_Y0 + 32)
    sta a:OBJ0 + (BOSS_Q + 2) * 4 + 1
    sta a:OBJ0 + (BOSS_Q + 3) * 4 + 1
    lda #(DGNB_NAME_BOSS)
    sta a:OBJ0 + (BOSS_Q + 0) * 4 + 2
    lda #(DGNB_NAME_BOSS + 4)
    sta a:OBJ0 + (BOSS_Q + 1) * 4 + 2
    lda #(DGNB_NAME_BOSS + 64)
    sta a:OBJ0 + (BOSS_Q + 2) * 4 + 2
    lda #(DGNB_NAME_BOSS + 68)
    sta a:OBJ0 + (BOSS_Q + 3) * 4 + 2
    lda #DGNB_ATTR_BOSS
    sta a:OBJ0 + (BOSS_Q + 0) * 4 + 3
    sta a:OBJ0 + (BOSS_Q + 1) * 4 + 3
    sta a:OBJ0 + (BOSS_Q + 2) * 4 + 3
    sta a:OBJ0 + (BOSS_Q + 3) * 4 + 3
    ; hi byte 1 = slots 4-7: EA large, EB small, boss TL + TR large; byte 2 = slots 8-11: boss BL + BR
    ; large, two pads small
    lda #%10100010
    sta a:OBJ_HI + 1
    lda #%00001010
    sta a:OBJ_HI + 2
    lda #OBJ_PARK_Y
    sta a:OBJ0 + 10 * 4 + 1
    sta a:OBJ0 + 11 * 4 + 1
    rep #$20
    .a16
    rts
.assert DGNB_SL_BOSS = 6, error, "dgnb_obj_const: hi bytes 1 and 2 assume the boss is slots 6-9"

; --- dgnb_obj_place: this frame's timelines -> the OAM shadow ----------------------------------------
; CONTRACT dgnb_obj_place
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_WANT_A / US_WANT_C (the players' frames), US_EA_I / US_EB_I (the enemies' timeline
;             indices), US_T (the frame counter)
;   out:      slots 0-5 and hi byte 0
;   clobbers: A, X, N, Z, C, US_TMP, US_TMP2
;   assumes:  once per frame from the scene's tick, after the timelines are stepped
;   tail:     rts
dgnb_obj_place:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnb_obj_place"
    stz z:US_TMP                    ; hi byte 0: the LARGE bits of the attacking players
    HERO_PLACE DGNB_SL_P1, DGNB_P1_X, US_WANT_A, DGNB_ATTR_P1, DGNB_H_AX, DGNB_H_ATK_AX, DGNB_NAME_P1, %00000010
    ; P2 faces left: HFLIP, so the foot anchor is 15 - x (small) / 31 - x (large) from the box's left
    HERO_PLACE DGNB_SL_P2, DGNB_P2_X, US_WANT_C, DGNB_ATTR_P2, (15 - DGNB_H_AX), (31 - DGNB_H_ATK_AX), DGNB_NAME_P2, %00100000
    lda z:US_TMP
    sep #$20
    .a8
    sta a:OBJ_HI + 0
    rep #$20
    .a16
    ; ---- the enemies ping-pong: phase = t & 127, pos = phase < 64 ? phase : 127 - phase ----------
    lda z:US_T
    and #127
    ldx #0                          ; X = 0 moving right (first half), 1 moving left
    cmp #64
    bcc @fw
    eor #127
    ldx #1
@fw:
    .a16
    .i16
    sta z:US_TMP                    ; pos 0..63
    stx z:US_TMP2
    ; ---- enemy A (32x32): foot x = X0 + pos, facing right, HFLIP while moving left ----------------
    lda z:US_EA_I
    asl a
    tax
    lda f:dgnb_ea_fr, x             ; frame 0..3
    asl a
    asl a                           ; name = frame * 4 (name table 1: the N bit is in the attribute)
    sep #$20
    .a8
    sta a:OBJ0 + DGNB_SL_EA * 4 + 2 ; name = frame * 4
    lda #(DGNB_EA_Y - (DGNB_EA_AY + 1))
    sta a:OBJ0 + DGNB_SL_EA * 4 + 1
    rep #$20
    .a16
    lda z:US_TMP
    clc
    adc #DGNB_EA_X0
    ldx z:US_TMP2
    bne @ea_left
    sec
    sbc #DGNB_EA_AX
    sep #$20
    .a8
    sta a:OBJ0 + DGNB_SL_EA * 4 + 0
    lda #DGNB_ATTR_E
    sta a:OBJ0 + DGNB_SL_EA * 4 + 3
    bra @ea_done
@ea_left:
    .a16
    .i16
    sec
    sbc #(31 - DGNB_EA_AX)
    sep #$20
    .a8
    sta a:OBJ0 + DGNB_SL_EA * 4 + 0
    lda #(DGNB_ATTR_E | DGNB_HFLIP)
    sta a:OBJ0 + DGNB_SL_EA * 4 + 3
@ea_done:
    .a8
    rep #$20
    .a16
    ; ---- enemy B (16x16): foot x = X0 - pos, facing right: HFLIP while moving LEFT (first half) ----
    lda z:US_EB_I
    asl a
    tax
    lda f:dgnb_eb_fr, x             ; frame 0..3
    asl a
    clc
    adc #DGNB_NAME_EB
    sep #$20
    .a8
    sta a:OBJ0 + DGNB_SL_EB * 4 + 2
    lda #(DGNB_EB_Y - (DGNB_EB_AY + 1))
    sta a:OBJ0 + DGNB_SL_EB * 4 + 1
    rep #$20
    .a16
    lda #DGNB_EB_X0
    sec
    sbc z:US_TMP
    ldx z:US_TMP2
    beq @eb_left
    sec
    sbc #DGNB_EB_AX
    sep #$20
    .a8
    sta a:OBJ0 + DGNB_SL_EB * 4 + 0
    lda #DGNB_ATTR_E
    sta a:OBJ0 + DGNB_SL_EB * 4 + 3
    bra @eb_done
@eb_left:
    .a16
    .i16
    sec
    sbc #(15 - DGNB_EB_AX)
    sep #$20
    .a8
    sta a:OBJ0 + DGNB_SL_EB * 4 + 0
    lda #(DGNB_ATTR_E | DGNB_HFLIP)
    sta a:OBJ0 + DGNB_SL_EB * 4 + 3
@eb_done:
    .a8
    rep #$20
    .a16
    rts

; --- dma_rows: a run of equal DMAs down the 16-wide OBJ name table ---------------------------------
; CONTRACT dgnb_dma_rows
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       X = rows, Y = bytes a row, US_X_S = the first VMADD, US_Y_S = the first source address,
;             the stream channel's A1B already set
;   out:      the rows in VRAM; US_X_S / US_Y_S advanced
;   clobbers: A, X, N, Z, C
;   assumes:  VBlank or forced blank, VMAIN = $80. DAS is single-shot, so it is re-armed every row
;   tail:     rts
dgnb_dma_rows:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnb_dma_rows"
@row:
    .a16
    .i16
    lda z:US_X_S
    sta a:$2116
    lda z:US_Y_S
    sta a:STREAM_REGS + 2
    sty a:STREAM_REGS + 5
    sep #$20
    .a8
    lda #(1 << ES_H_DGNBS_CH)
    sta a:$420B
    rep #$20
    .a16
    tya
    clc
    adc z:US_Y_S
    sta z:US_Y_S
    lda z:US_X_S
    clc
    adc #VRAM_ROW
    sta z:US_X_S
    dex
    bne @row
    rts

; --- dgnb_nmi_stream: the VBlank half -----------------------------------------------------------------
; CONTRACT dgnb_nmi_stream
;   entry:    A8 I16 DB=0
;   exit:     A8 I16
;   in:       US_WANT_B / _A / _C and US_HAVE_B / _A / _C
;   out:      every slot whose wanted frame differs from its held one is rewritten in VRAM and its HAVE
;             updated; US_VEND = the V counter at the end, US_VMAX its running maximum
;   clobbers: A, X, Y, N, Z, C, US_X_S, US_Y_S, the stream channel's $43xx
;   assumes:  VBlank (or forced blank at enter). It programs its own VMAIN and VMADD, so its position in
;             sm_nmi_hook is free
;   tail:     rts
dgnb_nmi_stream:
    .a8
    .i16
    SF_ASSERT_WIDTH 8, 16, "dgnb_nmi_stream"
    lda #$80
    sta a:$2115
    lda #ES_H_DGNBS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNBS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    ; ---- the boss ----------------------------------------------------------------------------------
    lda z:US_WANT_B
    cmp z:US_HAVE_B
    beq @boss_ok
    sta z:US_HAVE_B
    cmp #DGNB_BOSS_FRAMES_A_FACING
    bcs @boss_right
    xba
    asl a
    asl a
    asl a                           ; frame * 2048
    clc
    adc #.loword(dgnb_boss_down_bin)
    sta z:US_Y_S
    sep #$20
    .a8
    lda #^dgnb_boss_down_bin
    sta a:STREAM_REGS + 4
    rep #$20
    .a16
    bra @boss_go
@boss_right:
    .a16
    .i16
    sec
    sbc #DGNB_BOSS_FRAMES_A_FACING
    xba
    asl a
    asl a
    asl a
    clc
    adc #.loword(dgnb_boss_right_bin)
    sta z:US_Y_S
    sep #$20
    .a8
    lda #^dgnb_boss_right_bin
    sta a:STREAM_REGS + 4
    rep #$20
    .a16
@boss_go:
    .a16
    .i16
    lda #ES_V_OBJ_CHR
    sta z:US_X_S
    ldx #8
    ldy #256
    jsr dgnb_dma_rows
.ifdef DGNB_OVERLOAD
    ; PLANTED FAULT (tests/test_dgn_boss.py, `make dgn_boss_overload`): stream the boss a SECOND time.
    ; Never assembled into the real ROM; it exists so the tear and overrun detectors are known to fire.
    lda z:US_Y_S
    sec
    sbc #2048
    sta z:US_Y_S
    lda #ES_V_OBJ_CHR
    sta z:US_X_S
    ldx #8
    ldy #256
    jsr dgnb_dma_rows
.endif
@boss_ok:
    .a16
    .i16
    ; ---- player 1 ---------------------------------------------------------------------------------
    lda z:US_WANT_A
    cmp z:US_HAVE_A
    beq @a_ok
    sta z:US_HAVE_A
    ldx #VRAM_P1
    jsr dgnb_stream_hero
@a_ok:
    .a16
    .i16
    ; ---- player 2 ---------------------------------------------------------------------------------
    lda z:US_WANT_C
    cmp z:US_HAVE_C
    beq @c_ok
    sta z:US_HAVE_C
    ldx #VRAM_P2
    jsr dgnb_stream_hero
@c_ok:
    .a16
    .i16
    ; ---- the measurement: latch the V counter, keep it --------------------------------------------
    sep #$20
    .a8
    lda a:$213E                     ; STAT77: the sprite limits of the frame that just rendered
    and #$C0                        ; bit 7 range over (>32 sprites a line), bit 6 time over (>34 slivers)
    ora z:US_S77
    sta z:US_S77
    lda a:$213F                     ; STAT78: reset the H/V read flip-flops
    lda a:$2137                     ; SLHV: latch the counters
    lda a:$213D                     ; OPVCT low
    sta z:US_VEND
    lda a:$213D                     ; OPVCT high (bit 0)
    and #1
    sta z:US_VEND + 1
    rep #$20
    .a16
    lda z:US_VEND
    cmp z:US_VMAX
    bcc @vmax_ok
    sta z:US_VMAX
@vmax_ok:
    .a16
    .i16
    sep #$20
    .a8
    rts

; --- dgnb_stream_hero: one player's slot ------------------------------------------------------------
; CONTRACT dgnb_stream_hero
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       A = the player frame 0..8, X = the slot's first VMADD
;   out:      the slot's four tile rows in VRAM
;   clobbers: A, X, Y, N, Z, C, US_X_S, US_Y_S
;   assumes:  as dgnb_dma_rows
;   tail:     rts
dgnb_stream_hero:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnb_stream_hero"
    stx z:US_X_S
    xba
    asl a                           ; frame * 512
    clc
    adc #.loword(dgnb_hero_bin)
    sta z:US_Y_S
    sep #$20
    .a8
    lda #^dgnb_hero_bin
    sta a:STREAM_REGS + 4
    rep #$20
    .a16
    ldx #4
    ldy #128
    jmp dgnb_dma_rows

; --- dgnb_obj_park: hide all twelve (scene exit) -----------------------------------------------------
; CONTRACT dgnb_obj_park
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      every slot parked, the hi bytes small + X9 clear
;   clobbers: A, X, N, Z, C
;   assumes:  the scene that armed the slots re-parks them
;   tail:     rts
dgnb_obj_park:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnb_obj_park"
    ldx #0
    sep #$20
    .a8
@slot:
    .a8
    .i16
    lda #OBJ_PARK_Y
    sta a:OBJ0 + 1, x
    inx
    inx
    inx
    inx
    cpx #(ES_O_ACTORS_SPRITES * 4)
    bcc @slot
    stz a:OBJ_HI + 0
    stz a:OBJ_HI + 1
    stz a:OBJ_HI + 2
    rep #$20
    .a16
    rts
