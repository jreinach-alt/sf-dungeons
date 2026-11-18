; =============================================================================
; giant scene — the Mode 7 boss (docs/dungeons/20)
; =============================================================================
; A score: dgng_obj plays it. The boss is the plane's matrix, the players are streamed OBJs.
.scope giant
.include "engine_state_giant.inc"   ; GENERATED — this scene's map
.include "dgng_m7.asm"
.include "dgng_obj.asm"

; --- enter: forced blank + NMI masked (scene_mgr contract) -----------------------------------------------
; In/out: A16/I16, DB=0.
enter:
    .a16
    .i16
    sep #$20
    .a8
    lda #$FF
    sta a:$4201                 ; REG-LINT: ok — WRIO is deliberately unowned (no claim class describes it, and this rail has no light-gun/pin user). Bit 7 set so a read of $2137 latches the H/V counters (the V-counter measurement in dgng_nmi_stream)
    rep #$20
    .a16
    jsr dgng_m7_arm
    jsr dgng_obj_arm
    jmp dgng_obj_enter

; --- exit: re-park ----------------------------------------------------------------------------------------
exit:
    .a16
    .i16
    jmp dgng_obj_park

; --- tick: one frame (display active: the shadows only) ----------------------------------------------------
tick:
    .a16
    .i16
    jmp dgng_obj_tick
.endscope
