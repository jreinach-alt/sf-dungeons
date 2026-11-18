; =============================================================================
; colossus scene — the tile-streamed giant boss (docs/dungeons/21)
; =============================================================================
; A score: dgnt_obj plays it. The boss is pictures on two page-flipped BG layers, the room is BG3, the players are OBJs.
.scope colossus
.include "engine_state_colossus.inc"   ; GENERATED — this scene's map
.include "dgnt_bg.asm"
.include "dgnt_obj.asm"

; --- enter: forced blank + NMI masked (scene_mgr contract) ----------------------------------------------
; In/out: A16/I16, DB=0.
enter:
    .a16
    .i16
    sep #$20
    .a8
    lda #$FF
    sta a:$4201                 ; REG-LINT: ok — WRIO is deliberately unowned (no claim class describes it, and this rail has no light-gun/pin user). Bit 7 set so a read of $2137 latches the H/V counters (the V-counter measurement in dgnt_nmi_stream)
    rep #$20
    .a16
    jsr dgnt_bg_arm
    jsr dgnt_obj_arm
    jmp dgnt_obj_enter

; --- exit: re-park ------------------------------------------------------------------------------------------
exit:
    .a16
    .i16
    jmp dgnt_obj_park

; --- tick: one frame (display active: the shadows only) ------------------------------------------------------
tick:
    .a16
    .i16
    jmp dgnt_obj_tick
.endscope
