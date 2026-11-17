; =============================================================================
; dgnh_obj.asm — the model spike's wanderer as nine animated 16x16 OBJs
; =============================================================================
; CHR + both palettes from the dgnh_rom blobs; twenty OAM slots from this
; feature's claim: NINE ACTORS x TWO (a 16x32 figure is a top and a bottom
; 16x16 OBJ), plus two parked pads. Every entry is rebuilt each frame into the oam_sprites
; SHADOW (never hardware OAM, which the engine's VBlank GP-DMA owns) from the
; actor table below and the scene's two animation clocks.
;
; CPU-WRITTEN REGISTER, DECLARED: OBSEL $2101 (feature.toml obj_obsel). Size
; mode 0: small 8x8 / LARGE 16x16; every actor is large.

OBJ_REGS = $4300 + ES_D_OBJ_UP_CH * 16
OBJ_HI_BASE = ES_OAM_SHADOW + ES_OAM_SHADOW_SIZE - 32
OBJ0 = ES_OAM_SHADOW + ES_O_ACTORS * 4
OBJ_HI = OBJ_HI_BASE + (ES_O_ACTORS / 4)
OBJ_PARK_Y = 240                  ; Y = $F0: below the screen

; THE NAME-TABLE LAYOUT gen_dgn_hero_assets.py writes, asserted: 8 16x32
; frames per 4-tile-row band of the 16-tile-wide OBJ name table, so frame f's
; TOP half is name (f%8)*2 + (f/8)*64 = 2*(f&7) + 8*(f&~7), and its BOTTOM half
; is that + 32 (two tile rows down). Both are < 256, so the name-table bit is 0.
.assert DGNH_BAND * 2 = 16, error, "dgnh_obj: the converter's band must span the 16-wide name table"
BOT_NAME_DELTA = 2 * 16           ; two tile rows of the 16-wide name table
.assert ES_O_ACTORS .MOD 4 = 0, error, "dgnh_obj: the actors must start a hi-table byte"
.assert ES_O_ACTORS_SPRITES = 20, error, "dgnh_obj: five whole hi-table bytes"

; --- OAM attribute bytes: vhoopppN -------------------------------------------
ATTR_P1    = 3 << 4               ; priority 3, OBJ palette 0 (P1)
ATTR_P2    = (3 << 4) | (1 << 1)  ; priority 3, OBJ palette 1 (P2)
ATTR_HFLIP = 1 << 6               ; left = HFLIP of right (docs/dungeons/11 §2)
HI_LARGE4  = %10101010            ; four slots, all LARGE, all X9 clear
HI_LARGE2  = %00001010            ; slots 0 and 1 of the byte large, 2 and 3 small

; The anchor in a flipped frame: column 15 - x of the unflipped one.
DX_RIGHT = DGNH_ANCHOR_X
DX_LEFT  = (16 - 1) - DGNH_ANCHOR_X
OAM_DY   = DGNH_ANCHOR_Y + 1      ; an OBJ's first line is scanline Y+1, so
                                  ; the root row (anchor y) lands ON the foot y
HALF     = 16                     ; the bottom OBJ sits one 16x16 below the top

; --- the actor table ----------------------------------------------------------
; Per actor, 7 words: foot x, foot y, clock (0 idle, 1 walk), first frame,
; OAM attr, anchor dx, moving (1 = foot x comes from US_WX).
ACT_X     = 0
ACT_Y     = 2
ACT_CLOCK = 4
ACT_BASE  = 6
ACT_ATTR  = 8
ACT_DX    = 10
ACT_MOVE  = 12
ACT_SIZE  = 14
DGNH_ACTORS = 9
DGNH_WALKER_SLOT = 16             ; the last actor's TOP slot (2 per actor); hi byte 4, slot 0

COL1 = DGNH_COL0 + DGNH_COL_STEP
COL2 = DGNH_COL0 + DGNH_COL_STEP * 2
COL3 = DGNH_COL0 + DGNH_COL_STEP * 3
; The eight lineup actors never leave the screen, which is what lets hi bytes
; 0 and 1 be constants (all large, X9 clear). Asserted, not assumed.
.assert DGNH_COL0 >= DX_LEFT && DGNH_COL0 >= DX_RIGHT, error, "dgnh_obj: column 0 would cross x = 0"
.assert COL3 - DX_LEFT + 16 <= 256 && COL3 - DX_RIGHT + 16 <= 256, error, "dgnh_obj: column 3 would cross x = 256"

.pushseg
.segment "RODATA"
dgnh_actors:
    ; P1, walking: right, left, up, down
    .word DGNH_COL0, DGNH_ROW_WALK, 1, DGNH_F_WALK_RIGHT, ATTR_P1, DX_RIGHT, 0
    .word COL1,      DGNH_ROW_WALK, 1, DGNH_F_WALK_RIGHT, ATTR_P1 | ATTR_HFLIP, DX_LEFT, 0
    .word COL2,      DGNH_ROW_WALK, 1, DGNH_F_WALK_UP,    ATTR_P1, DX_RIGHT, 0
    .word COL3,      DGNH_ROW_WALK, 1, DGNH_F_WALK_DOWN,  ATTR_P1, DX_RIGHT, 0
    ; P2, idling: right, left, up, down
    .word DGNH_COL0, DGNH_ROW_IDLE, 0, DGNH_F_IDLE_RIGHT, ATTR_P2, DX_RIGHT, 0
    .word COL1,      DGNH_ROW_IDLE, 0, DGNH_F_IDLE_RIGHT, ATTR_P2 | ATTR_HFLIP, DX_LEFT, 0
    .word COL2,      DGNH_ROW_IDLE, 0, DGNH_F_IDLE_UP,    ATTR_P2, DX_RIGHT, 0
    .word COL3,      DGNH_ROW_IDLE, 0, DGNH_F_IDLE_DOWN,  ATTR_P2, DX_RIGHT, 0
    ; P1, the walker: right, at ground speed (foot x from US_WX)
    .word 0,         DGNH_ROW_PATH, 1, DGNH_F_WALK_RIGHT, ATTR_P1, DX_RIGHT, 1
dgnh_actors_end:
.popseg
.assert dgnh_actors_end - dgnh_actors = DGNH_ACTORS * ACT_SIZE, error, "dgnh_obj: actor table size"

; --- dgnh_obj_arm: CHR + palettes + OBSEL + hi table + parked pads -----------
; CONTRACT dgnh_obj_arm
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      OBJ CHR, OBJ palettes 0-1, OBSEL, the five hi-table bytes,
;             slots 18-19 parked
;   clobbers: A, X, N, Z, C
;   assumes:  forced blank AND the NMI masked (the scene_mgr enter
;             contract). Without these uploads OBJ VRAM and CGRAM 128.. are
;             random at power-on (rule 5) and every entry draws garbage
;   tail:     rts
dgnh_obj_arm:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnh_obj_arm"
    sep #$20
    .a8
    lda #$80
    sta a:$2115                     ; VMAIN: +1 word after the high byte
    rep #$20
    .a16
    lda #ES_V_OBJ_CHR
    sta a:$2116                     ; VMADD = the obj chr claim's base
    lda #.loword(dgnh_obj_chr_bin)
    sta a:OBJ_REGS + 2              ; A1T
    lda #ES_R_DGNH_OBJ_CHR_ROM_SIZE
    sta a:OBJ_REGS + 5              ; DAS, armed for this one transfer
    sep #$20
    .a8
    lda #^dgnh_obj_chr_bin
    sta a:OBJ_REGS + 4              ; A1B
    lda #ES_D_OBJ_UP_DMAP
    sta a:OBJ_REGS + 0
    lda #ES_D_OBJ_UP_BBAD
    sta a:OBJ_REGS + 1
    lda #(1 << ES_D_OBJ_UP_CH)
    sta a:$420B                     ; fire
    ; ---- OBJ palettes 0 + 1 (CGRAM 128..159) ------------------------------
    lda #ES_C_OBJ_PAL
    sta a:$2121
    rep #$20
    .a16
    ldx #0
@pal:
    .a16
    .i16
    lda f:dgnh_obj_pal_bin, x
    sep #$20
    .a8
    sta a:$2122                     ; low byte
    xba
    sta a:$2122                     ; high byte
    rep #$20
    .a16
    inx
    inx
    cpx #ES_R_DGNH_OBJ_PAL_ROM_SIZE
    bcc @pal
    ; ---- OBSEL: size mode 0 (8x8 / 16x16), base from the claim ------------
    sep #$20
    .a8
    lda #ES_V_OBJ_CHR_OBSEL_BASE
    sta a:$2101
    ; ---- hi table: slots 0-15 large (the lineup), 16-17 large (the walker),
    ; 18-19 small pads --------------------------------------------------------
    lda #HI_LARGE4
    sta a:OBJ_HI + 0
    sta a:OBJ_HI + 1
    sta a:OBJ_HI + 2
    sta a:OBJ_HI + 3
    lda #HI_LARGE2
    sta a:OBJ_HI + 4                ; dgnh_obj_place rebuilds the walker's X9s
    ; ---- slots 18-19: parked ------------------------------------------------
    lda #OBJ_PARK_Y
    sta a:OBJ0 + (DGNH_ACTORS * 2 + 0) * 4 + 1
    sta a:OBJ0 + (DGNH_ACTORS * 2 + 1) * 4 + 1
    rep #$20
    .a16
    rts

; --- dgnh_obj_place: the actor table + clocks -> the OAM shadow -------------
; CONTRACT dgnh_obj_place
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   in:       US_IDLE_I, US_WALK_I (the clocks), US_WX (the walker's foot x)
;   out:      slots 0-17 (x, y, name, attr: a top and a bottom OBJ per actor)
;             and hi byte 4's walker X9s
;   clobbers: A, X, Y, N, Z, C, US_TMP, US_TMP2
;   assumes:  once per frame from the scene's tick, after the clocks and
;             US_WX are committed
;   tail:     rts
dgnh_obj_place:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnh_obj_place"
    ldx #0                          ; actor table byte offset
    ldy #0                          ; OAM low-table byte offset (8 per actor)
@actor:
    .a16
    .i16
    ; ---- frame = first frame + this actor's clock --------------------------
    lda f:dgnh_actors + ACT_CLOCK, x
    beq @idle_clock
    lda z:US_WALK_I
    bra @have_i
@idle_clock:
    .a16
    .i16
    lda z:US_IDLE_I
@have_i:
    .a16
    .i16
    clc
    adc f:dgnh_actors + ACT_BASE, x
    sta z:US_TMP                    ; f
    ; ---- top name = 2*(f&7) + 8*(f&~7) -------------------------------------
    and #.loword(~(DGNH_BAND - 1))
    asl a
    asl a
    asl a
    sta z:US_TMP2                   ; 8*(f&~7)
    lda z:US_TMP
    and #(DGNH_BAND - 1)
    asl a
    clc
    adc z:US_TMP2                   ; A = the top half's name
    sep #$20
    .a8
    sta a:OBJ0 + 2, y               ; top name (bit 8 clear: names < 256)
    clc
    adc #BOT_NAME_DELTA
    sta a:OBJ0 + 4 * 1 + 2, y       ; bottom name
    lda f:dgnh_actors + ACT_ATTR, x
    sta a:OBJ0 + 3, y
    sta a:OBJ0 + 4 * 1 + 3, y
    rep #$20
    .a16
    ; ---- x = foot x - anchor dx (the walker's foot x is live) -------------
    lda f:dgnh_actors + ACT_MOVE, x
    beq @fixed_x
    lda z:US_WX
    bra @have_x
@fixed_x:
    .a16
    .i16
    lda f:dgnh_actors + ACT_X, x
@have_x:
    .a16
    .i16
    sec
    sbc f:dgnh_actors + ACT_DX, x
    sep #$20
    .a8
    sta a:OBJ0 + 0, y
    sta a:OBJ0 + 4 * 1 + 0, y
    rep #$20
    .a16
    ; ---- y: top = foot y - (anchor y + 1); bottom = top + 16 --------------
    lda f:dgnh_actors + ACT_Y, x
    sec
    sbc #OAM_DY
    sep #$20
    .a8
    sta a:OBJ0 + 1, y
    clc
    adc #HALF
    sta a:OBJ0 + 4 * 1 + 1, y
    rep #$20
    .a16
    ; ---- next ---------------------------------------------------------------
    txa
    clc
    adc #ACT_SIZE
    tax
    tya
    clc
    adc #8
    tay
    cpx #(DGNH_ACTORS * ACT_SIZE)
    bcc @actor
    ; ---- the walker's X9 (bit 8 of its OAM x) into hi byte 4, for BOTH halves:
    ; slot 16 -> bit 0, slot 17 -> bit 2 -------------------------------------
    lda z:US_WX
    sec
    sbc #DX_RIGHT
    xba
    and #1
    sta z:US_TMP
    asl a
    asl a
    ora z:US_TMP
    ora #HI_LARGE2
    sep #$20
    .a8
    sta a:OBJ_HI + (DGNH_WALKER_SLOT / 4)
    rep #$20
    .a16
    rts
.assert DGNH_WALKER_SLOT = (DGNH_ACTORS - 1) * 2, error, "dgnh_obj: the walker is the last actor"
.assert DGNH_WALKER_SLOT .MOD 4 = 0, error, "dgnh_obj: the walker's top half owns bit 0 of its hi byte"

; --- dgnh_obj_park: hide all twenty (scene exit) ----------------------------
; CONTRACT dgnh_obj_park
;   entry:    A16 I16 DB=0
;   exit:     A16 I16
;   out:      every slot parked, the hi bytes small + X9 clear
;   clobbers: A, X, N, Z, C
;   assumes:  the scene that armed the slots re-parks them. One scene and
;             no edges today, so nothing calls it; the contract is symmetric
;   tail:     rts
dgnh_obj_park:
    .a16
    .i16
    SF_ASSERT_WIDTH 16, 16, "dgnh_obj_park"
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
    stz a:OBJ_HI + 3
    stz a:OBJ_HI + 4
    rep #$20
    .a16
    rts
