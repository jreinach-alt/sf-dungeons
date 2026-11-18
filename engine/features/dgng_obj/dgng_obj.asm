; =============================================================================
; dgng_obj.asm — the giant boss scene's OBJ layer and SCORE PLAYER (docs/dungeons/20)
; =============================================================================
; Per tick the main thread copies one 33 B record of the score: the four OAM entries (the two players, each a top
; and a bottom 16x16), the hi byte, and the 16-byte Mode 7 shadow for dgng_m7. The NMI hook plays that tick's DMA
; rows (the players' back-buffer prefetch) and measures the V counter and STAT77, as dgnf_obj does.

STREAM_REGS = $4300 + ES_H_DGNGS_CH * 16
OBJ0 = ES_OAM_SHADOW + ES_O_ACTORS * 4
OBJ_HI = ES_OAM_SHADOW + ES_OAM_SHADOW_SIZE - 32 + (ES_O_ACTORS / 4)
OBSEL_MODE3 = 3 << 5              ; small 16x16 / large 32x32
CMD_BYTES = 6
ROW_BYTES = 128                  ; one tile row of a 4x4-tile player slot
OBJ_PARK_Y = 240
OBJ_PAL_OFF = ES_C_M7_PAL_WORDS * 2     ; the OBJ palettes follow the BG palette in the pal blob
.assert ES_O_ACTORS .MOD 4 = 0, error, "dgng_obj: the actors must start a hi-table byte"
.assert ES_O_ACTORS_SPRITES = 4, error, "dgng_obj: one whole hi-table byte"
.assert DGNG_REC = DGNG_REC_OAM + DGNG_REC_HI + DGNG_REC_M7, error, "dgng_obj: the generator's record size"
.assert DGNG_REC_M7 = 16, error, "dgng_obj: the Mode 7 shadow is eight unrolled words"
.assert ES_R_DGNG_SCORE_ROM_SIZE >= DGNG_REC_END, error, "dgng_obj: the score outgrew its claim"
.assert ES_R_DGNG_PTR_ROM_SIZE >= (DGNG_T + 2) * 2, error, "dgng_obj: the pointer table outgrew its claim"
.assert ES_R_DGNG_PAL_ROM_SIZE = OBJ_PAL_OFF + ES_C_OBJ_PAL_WORDS * 2, error, "dgng_obj: the palette blob's layout"

; --- dgng_obj_arm: the OBJ palettes and OBSEL ----------------------------------------------------------------------
; CONTRACT dgng_obj_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      OBJ palettes 0 and 1 (CGRAM 128..159), OBSEL
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked
;   tail:     rts
dgng_obj_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_obj_arm"
    sep #$20
    .a8
    lda #ES_C_OBJ_PAL
    sta a:$2121
    rep #$20
    .a16
    ldx #OBJ_PAL_OFF
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
    cpx #ES_R_DGNG_PAL_ROM_SIZE
    bcc @pal
    sep #$20
    .a8
    lda #(OBSEL_MODE3 | ES_V_OBJ_CHR_OBSEL_BASE)
    sta a:$2101
    rep #$20
    .a16
    rts

; --- dgng_play: a run of DMA rows from the command stream -----------------------------------------------------------------
; CONTRACT dgng_play
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       X = the first command's byte offset, Y = one past the last (offsets into the command stream)
;   out:      each row (128 B of a player's slot) transferred to VRAM
;   clobbers: A, X, Y, N, Z, C, US_C_CUR, US_C_END, US_C_SRC, the stream channel's $43xx
;   assumes:  VBlank or forced blank, VMAIN = $80, the stream channel's DMAP/BBAD set. DAS is single-shot
;   tail:     rts
dgng_play:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_play"
    stx z:US_C_CUR
    sty z:US_C_END
@next:
    .a16
    .i16
    lda z:US_C_CUR
    cmp z:US_C_END
    bcs @done
    tax
    lda f:dgng_cmds_bin + 0, x      ; dst: VRAM word offset from the claim base
    clc
    adc #ES_V_OBJ_CHR
    sta a:$2116
    lda f:dgng_cmds_bin + 2, x      ; src: byte offset within the players' blob (the only blob: the id is unused)
    clc
    adc #.loword(dgng_hero_bin)
    sta a:STREAM_REGS + 2           ; A1T
    lda #ROW_BYTES
    sta a:STREAM_REGS + 5           ; DAS: one tile row of a 4x4-tile slot
    sep #$20
    .a8
    lda #^dgng_hero_bin
    sta a:STREAM_REGS + 4           ; A1B
    lda #(1 << ES_H_DGNGS_CH)
    sta a:$420B
    rep #$20
    .a16
    lda z:US_C_CUR
    clc
    adc #CMD_BYTES
    sta z:US_C_CUR
    bra @next
@done:
    .a16
    .i16
    rts

; --- dgng_nmi_stream: the VBlank half ---------------------------------------------------------------------------------------
; CONTRACT dgng_nmi_stream
;   entry:    A8 I16 DB=0
;   exit:     A8 I16
;   in:       US_CT (the tick whose record is in the OAM shadow)
;   out:      that tick's DMA rows transferred; US_VEND = the V counter at the end, US_VMAX its running maximum,
;             US_S77 the sprite-limit flags seen so far
;   clobbers: A, X, Y, N, Z, C, dgng_play's
;   assumes:  VBlank. It programs its own VMAIN and VMADD
;   tail:     rts
dgng_nmi_stream:
    .a8
    .i16
    SF_ASSERT_WIDTH 8, 16, "dgng_nmi_stream"
    lda #$80
    sta a:$2115
    lda #ES_H_DGNGS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNGS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    lda z:US_CT
    asl a
    tax
    lda f:dgng_ptr_bin + 2, x       ; one past this tick's last command
    tay
    lda f:dgng_ptr_bin, x           ; this tick's first command
    tax
    jsr dgng_play
    sep #$20
    .a8
    lda a:$213E                     ; STAT77: the sprite limits of the frame that just rendered
    and #$C0
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

; --- dgng_copy_record: the record at US_REC -> the OAM shadow and the Mode 7 shadow ------------------------------------------
; CONTRACT dgng_copy_record
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_REC
;   out:      the shadow's four entries and hi byte, and ES_M7SH, = that record
;   clobbers: A, X, Y, N, Z, C
;   assumes:  nothing about the NMI: the shadows are only committed by it
;   tail:     rts
dgng_copy_record:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_copy_record"
    lda z:US_REC
    tax                              ; X = the record's offset in the score
    ldy #0
@oam:
    .a16
    .i16
    lda f:dgng_score_bin, x
    sta a:OBJ0, y
    inx
    inx
    iny
    iny
    cpy #DGNG_REC_OAM
    bcc @oam
    sep #$20
    .a8
    lda f:dgng_score_bin, x          ; the hi byte
    sta a:OBJ_HI + 0
    rep #$20
    .a16
    inx                              ; X = the Mode 7 words: eight, unrolled (a direct-page store has no ,y form and the
                                     ; long-indexed load needs X)
    lda f:dgng_score_bin + 0, x
    sta z:ES_M7SH + 0
    lda f:dgng_score_bin + 2, x
    sta z:ES_M7SH + 2
    lda f:dgng_score_bin + 4, x
    sta z:ES_M7SH + 4
    lda f:dgng_score_bin + 6, x
    sta z:ES_M7SH + 6
    lda f:dgng_score_bin + 8, x
    sta z:ES_M7SH + 8
    lda f:dgng_score_bin + 10, x
    sta z:ES_M7SH + 10
    lda f:dgng_score_bin + 12, x
    sta z:ES_M7SH + 12
    lda f:dgng_score_bin + 14, x
    sta z:ES_M7SH + 14
    rts

; --- dgng_obj_enter: the entry state and tick 0's shadows -----------------------------------------------------------------------
; CONTRACT dgng_obj_enter
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      both buffers of each player filled as the loop's steady state needs; the shadows hold record 0
;   clobbers: A, X, Y, N, Z, C, dgng_play's
;   assumes:  forced blank, after dgng_obj_arm and dgng_m7_arm
;   tail:     rts
dgng_obj_enter:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_obj_enter"
    stz z:US_T
    stz z:US_REC
    stz z:US_CT
    stz z:US_VEND
    stz z:US_VMAX
    stz z:US_S77
    jsr dgng_copy_record             ; a NMI can arrive before the first tick: the Mode 7 shadow must be real
    sep #$20
    .a8
    lda #$80
    sta a:$2115
    lda #ES_H_DGNGS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNGS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    lda f:dgng_ptr_bin + DGNG_T * 2       ; the entry-state rows start where the last tick's end
    tax
    lda f:dgng_ptr_bin + DGNG_T * 2 + 2   ; ... and end at the table's last word
    tay
    jmp dgng_play

; --- dgng_obj_tick: this tick's record, then advance ---------------------------------------------------------------------------------
; CONTRACT dgng_obj_tick
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_T, US_REC
;   out:      the shadows = this tick's record; US_CT = this tick; US_T and US_REC advanced (wrapping)
;   clobbers: A, X, Y, N, Z, C
;   assumes:  once per frame from the scene's tick
;   tail:     rts
dgng_obj_tick:                  ; TICK: ok — plays one record of a pre-baked score a frame; the unit IS the frame, by construction
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_obj_tick"
    lda z:US_T
    sta z:US_CT
    jsr dgng_copy_record
    lda z:US_REC
    clc
    adc #DGNG_REC
    inc z:US_T
    cmp #DGNG_REC_END
    bcc @keep
    lda #0
    stz z:US_T
@keep:
    .a16
    .i16
    sta z:US_REC
    rts

; --- dgng_obj_park: hide the four players' sprites (scene exit) --------------------------------------------------------------------------
; CONTRACT dgng_obj_park
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      every slot parked, the hi byte small + X9 clear
;   clobbers: A, X, N, Z, C
;   assumes:  the scene that armed the slots re-parks them
;   tail:     rts
dgng_obj_park:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgng_obj_park"
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
    rep #$20
    .a16
    rts
