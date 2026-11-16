; =============================================================================
; show scene — the wanderer lineup and the walker
; =============================================================================
; Two animation clocks (idle, walk) advance on actions.toml's holds; the walker
; moves at the walk's ground speed; dgnh_obj rebuilds the OAM shadow from both.
.scope show
.include "engine_state_show.inc"    ; GENERATED — this scene's map
.include "dgnh_obj.asm"

; --- enter: forced blank + NMI masked (scene_mgr contract) ------------------
; In/out: A16/I16, DB=0.
enter:
    .a16
    .i16
    ; ---- CGRAM word 0: the floor-coloured backdrop (preview tone) ---------
    sep #$20
    .a8
    lda #ES_C_BACKDROP_COLOR
    sta a:$2121
    lda #.lobyte(DGNH_BACKDROP_BGR)
    sta a:$2122
    lda #.hibyte(DGNH_BACKDROP_BGR)
    sta a:$2122
    ; ---- BGMODE + TM (backdrop's scene_writes): OBJ alone ------------------
    lda #1
    sta a:$2105                 ; BGMODE 1: inert (no BG enabled), but written
    lda #(1 << 4)
    sta a:$212C                 ; TM: OBJ only
    rep #$20
    .a16
    jsr dgnh_obj_arm
    ; ---- state: written before any read (power-on DP is random) ------------
    stz z:US_IDLE_I
    stz z:US_WALK_I
    lda f:dgnh_idle_hold
    and #.lobyte(-1)
    sta z:US_IDLE_CNT
    lda f:dgnh_walk_hold
    and #.lobyte(-1)
    sta z:US_WALK_CNT
    lda #DGNH_WALK_X0
    sta z:US_WX
    stz z:US_TS_ACC
    stz z:US_TS_STEP
    jsr dgnh_obj_place
    rts

; --- exit: re-park ------------------------------------------------------------
exit:
    .a16
    .i16
    jsr dgnh_obj_park
    rts

; --- tick: one frame (display active — shadow writes only) ------------------
; In/out: A16/I16, DB=0.
tick:
    .a16
    .i16
    ; ---- idle clock: count the hold down, then step the frame (wrapping) --
    dec z:US_IDLE_CNT
    bne @idle_held
    lda z:US_IDLE_I
    inc a
    cmp #DGNH_IDLE_N
    bcc @idle_set
    lda #0
@idle_set:
    .a16
    .i16
    sta z:US_IDLE_I
    tax
    lda f:dgnh_idle_hold, x
    and #.lobyte(-1)
    sta z:US_IDLE_CNT
@idle_held:
    .a16
    .i16
    ; ---- walk clock --------------------------------------------------------
    dec z:US_WALK_CNT
    bne @walk_held
    lda z:US_WALK_I
    inc a
    cmp #DGNH_WALK_N
    bcc @walk_set
    lda #0
@walk_set:
    .a16
    .i16
    sta z:US_WALK_I
    tax
    lda f:dgnh_walk_hold, x
    and #.lobyte(-1)
    sta z:US_WALK_CNT
@walk_held:
    .a16
    .i16
    ; ---- the walker: + ground speed, region-correct; wrap off the right
    ; edge (OAM x 256) to fully off the left (OAM x -16), keeping the
    ; sub-pixel phase --------------------------------------------------------
    TS_STEP z:US_TS_ACC, DGNH_SPEED
    sta z:US_TS_STEP
    lda z:US_WX
    clc
    adc z:US_TS_STEP
    bmi @no_wrap                ; still entering from the left
    cmp #(DGNH_WRAP_HI + DGNH_ANCHOR_X)
    bcc @no_wrap
    sec
    sbc #(DGNH_WRAP_HI + DGNH_WRAP_LO)
@no_wrap:
    .a16
    .i16
    sta z:US_WX
    jmp dgnh_obj_place
.endscope
