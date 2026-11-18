; =============================================================================
; arena scene — the boss-battle spike (docs/dungeons/18)
; =============================================================================
; Five scripted timelines (boss, P1, P2, two enemies) advance on their holds; dgnb_obj turns the frames they
; want into OAM entries (here) and VRAM streams (in the NMI hook).
.scope arena
.include "engine_state_arena.inc"   ; GENERATED — this scene's map
.include "dgnb_obj.asm"

; TL_STEP: count a hold down; on zero, step the timeline (wrapping) and load the next hold.
; In/out: A16 I16.
.macro TL_STEP idx, cnt, n, hd
    .local held, set
    dec z:cnt
    bne held
    lda z:idx
    inc a
    cmp #n
    bcc set
    lda #0
set:
    .a16
    .i16
    sta z:idx
    tax
    lda f:hd, x
    and #$00FF
    sta z:cnt
held:
    .a16
    .i16
.endmacro

; --- dgnb_load_want: each timeline's current frame -> the frame the stream must hold ---------------
; In/out: A16 I16. Clobbers A, X.
load_want:
    .a16
    .i16
    lda z:US_B_I
    asl a
    tax
    lda f:dgnb_boss_fr, x
    sta z:US_WANT_B
    lda z:US_A_I
    asl a
    tax
    lda f:dgnb_p1_fr, x
    sta z:US_WANT_A
    lda z:US_C_I
    asl a
    tax
    lda f:dgnb_p2_fr, x
    sta z:US_WANT_C
    rts

; --- enter: forced blank + NMI masked (scene_mgr contract) -----------------------------------------
; In/out: A16/I16, DB=0.
enter:
    .a16
    .i16
    sep #$20
    .a8
    lda #ES_C_BACKDROP_COLOR
    sta a:$2121
    lda #.lobyte(DGNB_BACKDROP_BGR)
    sta a:$2122
    lda #.hibyte(DGNB_BACKDROP_BGR)
    sta a:$2122
    lda #1
    sta a:$2105                 ; BGMODE 1: inert (no BG enabled)
    lda #(1 << 4)
    sta a:$212C                 ; TM: OBJ only
    lda #$FF
    sta a:$4201                 ; REG-LINT: ok — WRIO is deliberately unowned: no claim class describes it, and this rail has no light-gun/pin user. Bit 7 set so a read of $2137 latches the H/V counters (the V-counter measurement in dgnb_nmi_stream)
    rep #$20
    .a16
    jsr dgnb_obj_arm
    ; ---- state: written before any read (power-on DP is random) ------------
    stz z:US_B_I
    stz z:US_A_I
    stz z:US_C_I
    stz z:US_EA_I
    stz z:US_EB_I
    stz z:US_T
    stz z:US_VEND
    stz z:US_VMAX
    stz z:US_S77
    lda f:dgnb_boss_hd
    and #$00FF
    sta z:US_B_CNT
    lda f:dgnb_p1_hd
    and #$00FF
    sta z:US_A_CNT
    lda f:dgnb_p2_hd
    and #$00FF
    sta z:US_C_CNT
    lda f:dgnb_ea_hd
    and #$00FF
    sta z:US_EA_CNT
    lda f:dgnb_eb_hd
    and #$00FF
    sta z:US_EB_CNT
    lda #$FFFF
    sta z:US_HAVE_B
    sta z:US_HAVE_A
    sta z:US_HAVE_C             ; nothing streamed yet: the first stream loads all three
    jsr load_want
    jsr dgnb_obj_const
    jsr dgnb_obj_place
    sep #$20
    .a8
    jsr dgnb_nmi_stream         ; forced blank: the first frames, through the same routine VBlank uses
    rep #$20
    .a16
    rts

; --- exit: re-park ------------------------------------------------------------------------------------
exit:
    .a16
    .i16
    jsr dgnb_obj_park
    rts

; --- tick: one frame (display active — shadow and want-words only) ---------------------------------
; In/out: A16/I16, DB=0.
tick:
    .a16
    .i16
    inc z:US_T
    TL_STEP US_B_I, US_B_CNT, DGNB_BOSS_N, dgnb_boss_hd
    TL_STEP US_A_I, US_A_CNT, DGNB_P1_N, dgnb_p1_hd
    TL_STEP US_C_I, US_C_CNT, DGNB_P2_N, dgnb_p2_hd
    TL_STEP US_EA_I, US_EA_CNT, DGNB_EA_N, dgnb_ea_hd
    TL_STEP US_EB_I, US_EB_CNT, DGNB_EB_N, dgnb_eb_hd
    jsr load_want
    jmp dgnb_obj_place
.endscope
