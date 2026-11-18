; =============================================================================
; fight scene — the choreographed boss fight (docs/dungeons/19)
; =============================================================================
; The scene is a score: dgnf_obj plays it. Nothing here decides anything.
.scope fight
.include "engine_state_fight.inc"   ; GENERATED — this scene's map
.include "dgnf_obj.asm"

; --- enter: forced blank + NMI masked (scene_mgr contract) -----------------------------------------
; In/out: A16/I16, DB=0.
enter:
    .a16
    .i16
    sep #$20
    .a8
    lda #ES_C_BACKDROP_COLOR
    sta a:$2121
    lda #.lobyte(DGNF_BACKDROP_BGR)
    sta a:$2122
    lda #.hibyte(DGNF_BACKDROP_BGR)
    sta a:$2122
    lda #1
    sta a:$2105                 ; BGMODE 1: inert (no BG enabled)
    lda #(1 << 4)
    sta a:$212C                 ; TM: OBJ only
    lda #$FF
    sta a:$4201                 ; REG-LINT: ok — WRIO is deliberately unowned (no claim class describes it, and this rail has no light-gun/pin user). Bit 7 set so a read of $2137 latches the H/V counters (the V-counter measurement in dgnf_nmi_stream)
    rep #$20
    .a16
    jsr dgnf_obj_arm
    jmp dgnf_obj_enter

; --- exit: re-park ------------------------------------------------------------------------------------
exit:
    .a16
    .i16
    jmp dgnf_obj_park

; --- tick: one frame (display active — the shadow only) ---------------------------------------------
tick:
    .a16
    .i16
    jmp dgnf_obj_tick
.endscope
