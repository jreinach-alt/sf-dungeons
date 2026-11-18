; =============================================================================
; dgnt_obj.asm — the colossus's players and SCORE PLAYER (docs/dungeons/21)
; =============================================================================
; Per tick the main thread copies one 20 B record (4 OAM entries, the hi byte, TM, BG VOFS); the NMI hook commits TM and
; VOFS and plays that tick's DMA COMMANDS. A command is 8 B: (destination offset u16, source offset u16, blob u8,
; kind u8, length u16). `kind` picks the VRAM region the destination is relative to; `blob` picks the ROM claim.

STREAM_REGS = $4300 + ES_H_DGNTS_CH * 16
OBJ0 = ES_OAM_SHADOW + ES_O_ACTORS * 4
OBJ_HI = ES_OAM_SHADOW + ES_OAM_SHADOW_SIZE - 32 + (ES_O_ACTORS / 4)
OBSEL_MODE3 = 3 << 5
CMD_BYTES = 8
OBJ_PARK_Y = 240
OBJ_PAL_OFF = (ES_C_BOSS_PAL_WORDS + ES_C_FLOOR_PAL_WORDS) * 2      ; the OBJ palettes follow the BG ones in the blob
REC_OAM = 16
.assert ES_O_ACTORS .MOD 4 = 0, error, "dgnt_obj: the actors must start a hi-table byte"
.assert ES_O_ACTORS_SPRITES = 4, error, "dgnt_obj: one whole hi-table byte"
.assert DGNT_REC = REC_OAM + 4, error, "dgnt_obj: the generator's record size"
.assert ES_R_DGNT_SCORE_ROM_SIZE >= DGNT_REC_END, error, "dgnt_obj: the score outgrew its claim"
.assert ES_R_DGNT_PTR_ROM_SIZE >= (DGNT_T + 2) * 2, error, "dgnt_obj: the pointer table outgrew its claim"
.assert ES_R_DGNT_PAL_ROM_SIZE = OBJ_PAL_OFF + ES_C_OBJ_PAL_WORDS * 2, error, "dgnt_obj: the palette blob's layout"
.assert DGNT_CHR_TILES <= 304, error, "dgnt_obj: a picture needs more slots than the BG CHR claims hold"

; kind -> the VRAM word base its destination is relative to; blob -> its ROM address and bank
.pushseg
.segment "RODATA"
dgnt_kind_tab:
    .word ES_V_BGA_CHR, ES_V_BGB_CHR, ES_V_BGA_MAP, ES_V_BGB_MAP, ES_V_OBJ_CHR
dgnt_blob_addr:
    .word ES_R_DGNT_POOL0_ROM_ADDR, ES_R_DGNT_POOL1_ROM_ADDR, ES_R_DGNT_POOL2_ROM_ADDR, ES_R_DGNT_POOL3_ROM_ADDR
    .word ES_R_DGNT_POOL4_ROM_ADDR, ES_R_DGNT_POOL5_ROM_ADDR, ES_R_DGNT_POOL6_ROM_ADDR, ES_R_DGNT_HERO_ROM_ADDR
dgnt_blob_bank:
    .byte ES_R_DGNT_POOL0_ROM_BANK, ES_R_DGNT_POOL1_ROM_BANK, ES_R_DGNT_POOL2_ROM_BANK, ES_R_DGNT_POOL3_ROM_BANK
    .byte ES_R_DGNT_POOL4_ROM_BANK, ES_R_DGNT_POOL5_ROM_BANK, ES_R_DGNT_POOL6_ROM_BANK, ES_R_DGNT_HERO_ROM_BANK
.popseg

; --- dgnt_obj_arm: the OBJ palettes and OBSEL ---------------------------------------------------------------------------
; CONTRACT dgnt_obj_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      OBJ palettes 0 and 1 (CGRAM 128..159), OBSEL
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked
;   tail:     rts
dgnt_obj_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_obj_arm"
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
    cpx #ES_R_DGNT_PAL_ROM_SIZE
    bcc @pal
    sep #$20
    .a8
    lda #(OBSEL_MODE3 | ES_V_OBJ_CHR_OBSEL_BASE)
    sta a:$2101
    rep #$20
    .a16
    rts

; --- dgnt_play: a run of DMA commands ---------------------------------------------------------------------------------------
; CONTRACT dgnt_play
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       X = the first command's byte offset, Y = one past the last (offsets into the command stream)
;   out:      each command's transfer done
;   clobbers: A, X, Y, N, Z, C, US_C_CUR, US_C_END, US_C_DST, US_C_SRC, US_C_LEN, US_C_IDX, the stream channel's $43xx
;   assumes:  VBlank or forced blank, VMAIN = $80, the stream channel's DMAP/BBAD set. DAS is single-shot
;   tail:     rts
dgnt_play:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_play"
    stx z:US_C_CUR
    sty z:US_C_END
@next:
    .a16
    .i16
    lda z:US_C_CUR
    cmp z:US_C_END
    bcs @done
    tax
    lda f:dgnt_cmds_bin + 0, x      ; destination offset
    sta z:US_C_DST
    lda f:dgnt_cmds_bin + 2, x      ; source offset within the blob
    sta z:US_C_SRC
    lda f:dgnt_cmds_bin + 6, x      ; length
    sta z:US_C_LEN
    lda f:dgnt_cmds_bin + 4, x      ; blob in the low byte, kind in the high
    sta z:US_C_IDX
    xba
    and #$00FF
    asl a
    tax                             ; X = kind * 2
    lda f:dgnt_kind_tab, x
    clc
    adc z:US_C_DST
    sta a:$2116                     ; VMADD = the region's base + the destination offset
    lda z:US_C_IDX
    and #$00FF
    asl a
    tax                             ; X = blob * 2
    lda f:dgnt_blob_addr, x
    clc
    adc z:US_C_SRC
    sta a:STREAM_REGS + 2           ; A1T
    lda z:US_C_LEN
    sta a:STREAM_REGS + 5           ; DAS, armed for this one transfer
    lda z:US_C_IDX
    and #$00FF
    tax                             ; X = blob
    sep #$20
    .a8
    lda f:dgnt_blob_bank, x
    sta a:STREAM_REGS + 4           ; A1B
    lda #(1 << ES_H_DGNTS_CH)
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

; --- dgnt_nmi_stream: the VBlank half ---------------------------------------------------------------------------------------------
; CONTRACT dgnt_nmi_stream
;   entry:    A8 I16 DB=0
;   exit:     A8 I16
;   in:       US_CT (the tick whose record is in the OAM shadow)
;   out:      that tick's DMA commands played; US_VEND = the V counter at the end, US_VMAX its running maximum,
;             US_S77 the sprite-limit flags seen so far
;   clobbers: A, X, Y, N, Z, C, dgnt_play's
;   assumes:  VBlank. It programs its own VMAIN and VMADD
;   tail:     rts
dgnt_nmi_stream:
    .a8
    .i16
    SF_ASSERT_WIDTH 8, 16, "dgnt_nmi_stream"
    lda #$80
    sta a:$2115
    lda #ES_H_DGNTS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNTS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    lda z:US_CT
.ifdef DGNT_LATE
    ; PLANTED FAULT (tests/test_dgn_colossus.py, `make dgn_colossus_late`): play the PREVIOUS tick's commands, one tick
    ; late. Never assembled into the real ROM: it exists so the displayed-picture detector is known to fire.
    bne @late_ok
    lda #DGNT_T
@late_ok:
    .a16
    dec a
.endif
    asl a
    tax
    lda f:dgnt_ptr_bin + 2, x       ; one past this tick's last command
    tay
    lda f:dgnt_ptr_bin, x           ; this tick's first command
    tax
    jsr dgnt_play
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

; --- dgnt_copy_record: the record at US_REC -> the OAM shadow and the BG shadow ------------------------------------------------------
; CONTRACT dgnt_copy_record
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_REC
;   out:      the four OAM entries and hi byte; ES_BGSH = TM and VOFS of that record
;   clobbers: A, X, Y, N, Z, C
;   assumes:  nothing about the NMI: the shadows are only committed by it
;   tail:     rts
dgnt_copy_record:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_copy_record"
    lda z:US_REC
    tax
    ldy #0
@oam:
    .a16
    .i16
    lda f:dgnt_score_bin, x
    sta a:OBJ0, y
    inx
    inx
    iny
    iny
    cpy #REC_OAM
    bcc @oam
    sep #$20
    .a8
    lda f:dgnt_score_bin, x          ; the hi byte
    sta a:OBJ_HI + 0
.ifdef DGNT_EARLY
    ; PLANTED FAULT (`make dgn_colossus_early`): the NEXT record's TM, so a swap shows the layer one tick before its
    ; tiles are loaded. Never assembled into the real ROM.
    lda f:dgnt_score_bin + 1 + DGNT_REC, x
.else
    lda f:dgnt_score_bin + 1, x      ; TM: which boss layer is shown
.endif
    sta z:ES_BGSH + 0
    rep #$20
    .a16
    lda f:dgnt_score_bin + 2, x      ; BG VOFS
    sta z:ES_BGSH + 2
    rts

; --- dgnt_obj_enter: the entry state and tick 0's shadows ----------------------------------------------------------------------------------
; CONTRACT dgnt_obj_enter
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      both boss layers holding the rest picture, the players' buffers filled; the shadows hold record 0
;   clobbers: A, X, Y, N, Z, C, dgnt_play's
;   assumes:  forced blank, after dgnt_bg_arm and dgnt_obj_arm. The entry-state commands are the stream's last
;   tail:     rts
dgnt_obj_enter:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_obj_enter"
    stz z:US_T
    stz z:US_REC
    stz z:US_CT
    stz z:US_VEND
    stz z:US_VMAX
    stz z:US_S77
    jsr dgnt_copy_record             ; an NMI can arrive before the first tick: the shadows must be real
    sep #$20
    .a8
    lda #$80
    sta a:$2115
    lda #ES_H_DGNTS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNTS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    lda f:dgnt_ptr_bin + DGNT_T * 2
    tax
    lda f:dgnt_ptr_bin + DGNT_T * 2 + 2
    tay
    jmp dgnt_play

; --- dgnt_obj_tick: this tick's record, then advance ------------------------------------------------------------------------------------------
; CONTRACT dgnt_obj_tick
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_T, US_REC
;   out:      the shadows = this tick's record; US_CT = this tick; US_T and US_REC advanced (wrapping)
;   clobbers: A, X, Y, N, Z, C
;   assumes:  once per frame from the scene's tick
;   tail:     rts
dgnt_obj_tick:                  ; TICK: ok — plays one record of a pre-baked score a frame; the unit IS the frame, by construction
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_obj_tick"
    lda z:US_T
    sta z:US_CT
    jsr dgnt_copy_record
    lda z:US_REC
    clc
    adc #DGNT_REC
    inc z:US_T
    cmp #DGNT_REC_END
    bcc @keep
    lda #0
    stz z:US_T
@keep:
    .a16
    .i16
    sta z:US_REC
    rts

; --- dgnt_obj_park: hide the four players' sprites (scene exit) -----------------------------------------------------------------------------------
; CONTRACT dgnt_obj_park
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      every slot parked, the hi byte small + X9 clear
;   clobbers: A, X, N, Z, C
;   assumes:  the scene that armed the slots re-parks them
;   tail:     rts
dgnt_obj_park:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnt_obj_park"
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
