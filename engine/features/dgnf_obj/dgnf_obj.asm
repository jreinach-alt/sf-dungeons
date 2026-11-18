; =============================================================================
; dgnf_obj.asm — the choreographed boss fight's OBJ layer: a SCORE PLAYER (docs/dungeons/19)
; =============================================================================
; The scene is data. Per tick the main thread copies one 51 B record of the score into the OAM shadow (12 entries
; and 3 hi-table bytes: every position, name, attribute and size the director worked out), and the NMI hook plays
; that tick's DMA rows. There is no game logic here, and that is the point: the director proved the per-tick
; load offline, so the ROM cannot be surprised by it.
;
; THE STREAM. Each streamed actor (the 64x64 boss, two players) has TWO VRAM buffers. A command is one tile row
; of one frame: (VRAM word offset, source offset in its blob, blob id). The blob table below gives each id's
; ROM address and row size; a row is one DMA.
;
; THE MEASUREMENT, as in dgnb_obj: the last thing the NMI hook does is latch the PPU's V counter (US_VEND, and
; its running maximum US_VMAX) and STAT77's sprite-limit flags (US_S77).

STREAM_REGS = $4300 + ES_H_DGNFS_CH * 16
UP_REGS = $4300 + ES_D_OBJ_UP_CH * 16
OBJ0 = ES_OAM_SHADOW + ES_O_ACTORS * 4
OBJ_HI = ES_OAM_SHADOW + ES_OAM_SHADOW_SIZE - 32 + (ES_O_ACTORS / 4)
VRAM_T1 = 256 * 16                ; words from the claim base to OBJ name table 1 (OBSEL gap 0: contiguous)
OBSEL_MODE3 = 3 << 5              ; small 16x16 / large 32x32
OBJ_PARK_Y = 240
REC_LOW = 12 * 4                  ; the record's OAM entries
REC_HI = 3                        ; and its hi-table bytes
CMD_BYTES = 6
.assert ES_O_ACTORS .MOD 4 = 0, error, "dgnf_obj: the actors must start a hi-table byte"
.assert ES_O_ACTORS_SPRITES = 12, error, "dgnf_obj: three whole hi-table bytes"
.assert DGNF_REC = REC_LOW + REC_HI, error, "dgnf_obj: the generator's record size"
.assert ES_V_OBJ_CHR_WORDS = 512 * 16, error, "dgnf_obj: both OBJ name tables"
.assert ES_R_DGNF_SCORE_ROM_SIZE >= DGNF_REC_END, error, "dgnf_obj: the score outgrew its claim"
.assert ES_R_DGNF_PTR_ROM_SIZE >= (DGNF_T + 2) * 2, error, "dgnf_obj: the pointer table outgrew its claim"

; The blob table: id -> ROM address, row size, bank (6 B). Ids 0-2 are the boss's three frame stores (256 B rows),
; id 3 is the players' (128 B rows). Derived from the allocator's symbols, never retyped.
.pushseg
.segment "RODATA"
dgnf_blob_tab:
    .word ES_R_DGNF_BOSS0_ROM_ADDR, 256
    .byte ES_R_DGNF_BOSS0_ROM_BANK, 0
    .word ES_R_DGNF_BOSS1_ROM_ADDR, 256
    .byte ES_R_DGNF_BOSS1_ROM_BANK, 0
    .word ES_R_DGNF_BOSS2_ROM_ADDR, 256
    .byte ES_R_DGNF_BOSS2_ROM_BANK, 0
    .word ES_R_DGNF_HERO_ROM_ADDR, 128
    .byte ES_R_DGNF_HERO_ROM_BANK, 0
.popseg

; --- dgnf_obj_arm: resident CHR + palettes + OBSEL ------------------------------------------------------------
; CONTRACT dgnf_obj_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      OBJ name table 1 (both enemies), OBJ palettes 0-3, OBSEL
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked (the scene_mgr enter contract). Name table 0 is the STREAMED half;
;             dgnf_play fills it from the score's entry-state rows
;   tail:     rts
dgnf_obj_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnf_obj_arm"
    sep #$20
    .a8
    lda #$80
    sta a:$2115                     ; VMAIN: +1 word after the high byte
    rep #$20
    .a16
    lda #(ES_V_OBJ_CHR + VRAM_T1)
    sta a:$2116                     ; VMADD = name table 1
    lda #.loword(dgnf_res_bin)
    sta a:UP_REGS + 2
    lda #ES_R_DGNF_RES_ROM_SIZE
    sta a:UP_REGS + 5
    sep #$20
    .a8
    lda #^dgnf_res_bin
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
    lda f:dgnf_pal_bin, x
    sep #$20
    .a8
    sta a:$2122
    xba
    sta a:$2122
    rep #$20
    .a16
    inx
    inx
    cpx #ES_R_DGNF_PAL_ROM_SIZE
    bcc @pal
    sep #$20
    .a8
    lda #(OBSEL_MODE3 | ES_V_OBJ_CHR_OBSEL_BASE)
    sta a:$2101
    rep #$20
    .a16
    rts

; --- dgnf_play: a run of DMA rows from the command stream ----------------------------------------------------
; CONTRACT dgnf_play
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       X = the first command's byte offset, Y = one past the last (offsets into the command stream)
;   out:      each row transferred to VRAM
;   clobbers: A, X, Y (read on entry only), N, Z, C, US_C_CUR, US_C_END, US_C_SRC, US_C_ID, the stream channel's $43xx
;   assumes:  VBlank or forced blank, VMAIN = $80, the stream channel's DMAP/BBAD set. DAS is single-shot, so
;             it is re-armed every row
;   tail:     rts
dgnf_play:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnf_play"
    stx z:US_C_CUR
    sty z:US_C_END
@next:
    .a16
    .i16
    lda z:US_C_CUR
    cmp z:US_C_END
    bcs @done
    tax
    lda f:dgnf_cmds_bin + 0, x      ; dst: VRAM word offset from the claim base
    clc
    adc #ES_V_OBJ_CHR
    sta a:$2116
    lda f:dgnf_cmds_bin + 2, x      ; src: byte offset within the blob
    sta z:US_C_SRC
    lda f:dgnf_cmds_bin + 4, x      ; blob id (the high byte is padding)
    and #$00FF
    asl a
    sta z:US_C_ID                   ; id * 2
    asl a                           ; id * 4
    clc
    adc z:US_C_ID                   ; id * 6: the blob table's stride
    tax                             ; (X is free: the command's fields are all read)
    lda f:dgnf_blob_tab + 0, x      ; the blob's ROM address
    clc
    adc z:US_C_SRC
    sta a:STREAM_REGS + 2           ; A1T
    lda f:dgnf_blob_tab + 2, x      ; the blob's row size
    sta a:STREAM_REGS + 5           ; DAS, armed for this one transfer
    sep #$20
    .a8
    lda f:dgnf_blob_tab + 4, x      ; the blob's bank
    sta a:STREAM_REGS + 4           ; A1B
    lda #(1 << ES_H_DGNFS_CH)
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

; --- dgnf_nmi_stream: the VBlank half ---------------------------------------------------------------------------
; CONTRACT dgnf_nmi_stream
;   entry:    A8 I16 DB=0
;   exit:     A8 I16
;   in:       US_CT (the tick whose record is in the OAM shadow)
;   out:      that tick's DMA rows transferred; US_VEND = the V counter at the end, US_VMAX its running
;             maximum, US_S77 the sprite-limit flags seen so far
;   clobbers: A, X, Y, N, Z, C, dgnf_play's
;   assumes:  VBlank. It programs its own VMAIN and VMADD, so its position in sm_nmi_hook is free
;   tail:     rts
dgnf_nmi_stream:
    .a8
    .i16
    SF_ASSERT_WIDTH 8, 16, "dgnf_nmi_stream"
    lda #$80
    sta a:$2115
    lda #ES_H_DGNFS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNFS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    lda z:US_CT
.ifdef DGNF_LATE
    ; PLANTED FAULT (tests/test_dgn_fight.py, `make dgn_fight_late`): play the PREVIOUS tick's rows, one tick
    ; late. Never assembled into the real ROM; it exists so the displayed-frame detector is known to fire.
    bne @late_ok
    lda #DGNF_T
@late_ok:
    .a16
    dec a
.endif
    asl a
    tax
    lda f:dgnf_ptr_bin + 2, x       ; one past this tick's last command
    tay
    lda f:dgnf_ptr_bin, x           ; this tick's first command
    tax
    jsr dgnf_play
    ; ---- the measurement: the sprite limits, then the V counter ----------------------------------------
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

; --- dgnf_obj_enter: the entry state, then tick 0 ---------------------------------------------------------------
; CONTRACT dgnf_obj_enter
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      both buffers of every streamed actor filled as the loop's steady state needs them; the cursor
;             at tick 0
;   clobbers: A, X, Y, N, Z, C, dgnf_play's
;   assumes:  forced blank, after dgnf_obj_arm. The entry-state rows are the stream's last (offset T)
;   tail:     rts
dgnf_obj_enter:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnf_obj_enter"
    stz z:US_T
    stz z:US_REC
    stz z:US_CT
    stz z:US_VEND
    stz z:US_VMAX
    stz z:US_S77
    sep #$20
    .a8
    lda #$80
    sta a:$2115
    lda #ES_H_DGNFS_DMAP
    sta a:STREAM_REGS + 0
    lda #ES_H_DGNFS_BBAD
    sta a:STREAM_REGS + 1
    rep #$20
    .a16
    lda f:dgnf_ptr_bin + DGNF_T * 2       ; the entry-state rows start where the last tick's end
    tax
    lda f:dgnf_ptr_bin + DGNF_T * 2 + 2   ; ... and end at the table's last word
    tay
    jmp dgnf_play

; --- dgnf_obj_tick: this tick's record -> the OAM shadow; advance ----------------------------------------------------
; CONTRACT dgnf_obj_tick
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_T, US_REC
;   out:      the OAM shadow's 12 entries and 3 hi bytes = this tick's record; US_CT = this tick; US_T and
;             US_REC advanced (wrapping at the loop's end)
;   clobbers: A, X, Y, N, Z, C
;   assumes:  once per frame from the scene's tick
;   tail:     rts
dgnf_obj_tick:                  ; TICK: ok — plays one record of a pre-baked score a frame; the score's unit IS the frame, by construction (docs/dungeons/19)
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnf_obj_tick"
    lda z:US_T
    sta z:US_CT
    lda z:US_REC
    tax                              ; X = the record's offset in the score
    ldy #0
@low:
    .a16
    .i16
    lda f:dgnf_score_bin, x
    sta a:OBJ0, y
    inx
    inx
    iny
    iny
    cpy #REC_LOW
    bcc @low
    sep #$20
    .a8
    lda f:dgnf_score_bin, x          ; the three hi-table bytes
    sta a:OBJ_HI + 0
    lda f:dgnf_score_bin + 1, x
    sta a:OBJ_HI + 1
    lda f:dgnf_score_bin + 2, x
    sta a:OBJ_HI + 2
    rep #$20
    .a16
    lda z:US_REC                     ; advance, wrapping at the loop's end
    clc
    adc #DGNF_REC
    inc z:US_T
    cmp #DGNF_REC_END
    bcc @keep
    lda #0
    stz z:US_T
@keep:
    .a16
    .i16
    sta z:US_REC
    rts

; --- dgnf_obj_park: hide all twelve (scene exit) ---------------------------------------------------------------------
; CONTRACT dgnf_obj_park
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      every slot parked, the hi bytes small + X9 clear
;   clobbers: A, X, N, Z, C
;   assumes:  the scene that armed the slots re-parks them
;   tail:     rts
dgnf_obj_park:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnf_obj_park"
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
