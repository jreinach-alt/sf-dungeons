; =============================================================================
; dgn_giant — SuperForge Dungeons' giant Mode 7 boss (docs/dungeons/20). ROM skeleton.
; =============================================================================
; NOTHING HERE IS HAND-PLACED: every RAM/VRAM/CGRAM address, channel and
; register base comes from the allocator's emitted includes; hardware I/O
; ports are the only literals (no_literals-gated).
;
; OBJ ONLY, ONE SCENE, NO AUDIO, NO INPUT: the ROM boots into the giant boss and
; stays there. The art is the committed output of the creature and style pipelines,
; converted by tools/gen_dgn_giant_assets.py.
.p816
.smart

.define SF_HDR_TITLE "DGN GIANT SPIKE"
SF_HDR_TITLE_SET = 1
.include "engine_state_globals.inc" ; GENERATED — system + game-lifetime map
.include "dgng_frames.inc"          ; GENERATED — the score's length and record layout
SCENE_GIANT = 0                     ; game.toml manifest order
.include "header.inc"
.include "init.inc"                 ; RESET: native, A16/I16, forced blank
.include "sf_asm.inc"               ; placement assertions + SF_ASSERT_WIDTH

.segment "CODE"

NMI_STUB:
    rti
NMI:
    jmp sm_nmi_core

; --- engine feature runtimes ------------------------------------------------
.include "scene_mgr.asm"
.include "input.asm"
.include "fade.asm"
.include "oam_sprites.asm"

; --- global ROM blobs: ORDER = the allocator's packing (largest first; see
; build/dgng/allocation_report.txt), each site asserted against the claim ----
.segment "BANK1"
dgng_m7_bin:
    .incbin "dgng_m7.bin"
.assert ^dgng_m7_bin = ES_R_DGNG_M7_ROM_BANK, error, "dgng_m7 bank drifted from allocator claim"
.assert .loword(dgng_m7_bin) = ES_R_DGNG_M7_ROM_ADDR, error, "dgng_m7 addr drifted from allocator claim"
.segment "BANK2"
dgng_score_bin:
    .incbin "dgng_score.bin"
.assert ^dgng_score_bin = ES_R_DGNG_SCORE_ROM_BANK, error, "dgng_score bank drifted from allocator claim"
.assert .loword(dgng_score_bin) = ES_R_DGNG_SCORE_ROM_ADDR, error, "dgng_score addr drifted from allocator claim"
dgng_hero_bin:
    .incbin "dgng_hero.bin"
.assert ^dgng_hero_bin = ES_R_DGNG_HERO_ROM_BANK, error, "dgng_hero bank drifted from allocator claim"
.assert .loword(dgng_hero_bin) = ES_R_DGNG_HERO_ROM_ADDR, error, "dgng_hero addr drifted from allocator claim"
dgng_cmds_bin:
    .incbin "dgng_cmds.bin"
.assert ^dgng_cmds_bin = ES_R_DGNG_CMDS_ROM_BANK, error, "dgng_cmds bank drifted from allocator claim"
.assert .loword(dgng_cmds_bin) = ES_R_DGNG_CMDS_ROM_ADDR, error, "dgng_cmds addr drifted from allocator claim"
dgng_ptr_bin:
    .incbin "dgng_ptr.bin"
.assert ^dgng_ptr_bin = ES_R_DGNG_PTR_ROM_BANK, error, "dgng_ptr bank drifted from allocator claim"
.assert .loword(dgng_ptr_bin) = ES_R_DGNG_PTR_ROM_ADDR, error, "dgng_ptr addr drifted from allocator claim"
dgng_pal_bin:
    .incbin "dgng_pal.bin"
.assert ^dgng_pal_bin = ES_R_DGNG_PAL_ROM_BANK, error, "dgng_pal bank drifted from allocator claim"
.assert .loword(dgng_pal_bin) = ES_R_DGNG_PAL_ROM_ADDR, error, "dgng_pal addr drifted from allocator claim"
.segment "CODE"

; --- scenes -------------------------------------------------------------------
.include "scenes/giant.asm"

; --- sm_nmi_hook: per-frame VBlank work ---------------------------------------
; In: A8/I16, DB=0 (from sm_nmi_core). The OAM shadow's GP-DMA, the Mode 7 matrix commit (a handful of register
; writes), then the score's DMA rows for this tick (each programs its own VMAIN/VMADD, so the order is free).
sm_nmi_hook:
    .a8
    .i16
    jsr oam_nmi_dma
    jsr giant::dgng_m7_commit
    jsr giant::dgng_nmi_stream
    rts

; --- scene dispatch tables (manifest order: giant=0) ------------------------
sm_enter_tab:   .word giant::enter
sm_tick_tab:    .word giant::tick
sm_exit_tab:    .word giant::exit

; --- MAIN: boot -------------------------------------------------------------
; init.inc leaves: native, A16/I16, DB=0, forced blank, NMI+HDMA off.
MAIN:
    .a16
    .i16
    jsr sm_init
    jsr input_init
    jsr fade_init
    jsr oam_park_all            ; whole shadow written before its first DMA
    ldx #(SCENE_GIANT * 2)
    jsr (sm_enter_tab, x)
    sep #$20
    .a8
    lda #$81
    sta a:$4200                 ; NMITIMEN: NMI + auto-joypad
    jsr fade_start_in
    rep #$20
    .a16
@loop:
    .a16
    jsr input_read
    jsr sm_tick
    jsr fade_tick
    jsr sm_frame_sync
    bra @loop
