; =============================================================================
; dgn_fight — SuperForge Dungeons' choreographed boss fight (docs/dungeons/19). ROM skeleton.
; =============================================================================
; NOTHING HERE IS HAND-PLACED: every RAM/VRAM/CGRAM address, channel and
; register base comes from the allocator's emitted includes; hardware I/O
; ports are the only literals (no_literals-gated).
;
; OBJ ONLY, ONE SCENE, NO AUDIO, NO INPUT: the ROM boots into the fight and
; stays there. The art is the committed output of the creature and style pipelines,
; converted by tools/gen_dgn_fight_assets.py.
.p816
.smart

.define SF_HDR_TITLE "DGN FIGHT SPIKE"
SF_HDR_TITLE_SET = 1
.include "engine_state_globals.inc" ; GENERATED — system + game-lifetime map
.include "dgnf_frames.inc"          ; GENERATED — the score's length and record size
SCENE_FIGHT = 0                     ; game.toml manifest order
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
; build/dgnf/allocation_report.txt), each site asserted against the claim ----
.segment "BANK1"
dgnf_score_bin:
    .incbin "dgnf_score.bin"
.assert ^dgnf_score_bin = ES_R_DGNF_SCORE_ROM_BANK, error, "dgnf_score bank drifted from allocator claim"
.assert .loword(dgnf_score_bin) = ES_R_DGNF_SCORE_ROM_ADDR, error, "dgnf_score addr drifted from allocator claim"
.segment "BANK2"
dgnf_boss0_bin:
    .incbin "dgnf_boss0.bin"
.assert ^dgnf_boss0_bin = ES_R_DGNF_BOSS0_ROM_BANK, error, "dgnf_boss0 bank drifted from allocator claim"
.assert .loword(dgnf_boss0_bin) = ES_R_DGNF_BOSS0_ROM_ADDR, error, "dgnf_boss0 addr drifted from allocator claim"
dgnf_ptr_bin:
    .incbin "dgnf_ptr.bin"
.assert ^dgnf_ptr_bin = ES_R_DGNF_PTR_ROM_BANK, error, "dgnf_ptr bank drifted from allocator claim"
.assert .loword(dgnf_ptr_bin) = ES_R_DGNF_PTR_ROM_ADDR, error, "dgnf_ptr addr drifted from allocator claim"
dgnf_pal_bin:
    .incbin "dgnf_pal.bin"
.assert ^dgnf_pal_bin = ES_R_DGNF_PAL_ROM_BANK, error, "dgnf_pal bank drifted from allocator claim"
.assert .loword(dgnf_pal_bin) = ES_R_DGNF_PAL_ROM_ADDR, error, "dgnf_pal addr drifted from allocator claim"
.segment "BANK3"
dgnf_boss1_bin:
    .incbin "dgnf_boss1.bin"
.assert ^dgnf_boss1_bin = ES_R_DGNF_BOSS1_ROM_BANK, error, "dgnf_boss1 bank drifted from allocator claim"
.assert .loword(dgnf_boss1_bin) = ES_R_DGNF_BOSS1_ROM_ADDR, error, "dgnf_boss1 addr drifted from allocator claim"
.segment "BANK4"
dgnf_boss2_bin:
    .incbin "dgnf_boss2.bin"
.assert ^dgnf_boss2_bin = ES_R_DGNF_BOSS2_ROM_BANK, error, "dgnf_boss2 bank drifted from allocator claim"
.assert .loword(dgnf_boss2_bin) = ES_R_DGNF_BOSS2_ROM_ADDR, error, "dgnf_boss2 addr drifted from allocator claim"
.segment "BANK5"
dgnf_cmds_bin:
    .incbin "dgnf_cmds.bin"
.assert ^dgnf_cmds_bin = ES_R_DGNF_CMDS_ROM_BANK, error, "dgnf_cmds bank drifted from allocator claim"
.assert .loword(dgnf_cmds_bin) = ES_R_DGNF_CMDS_ROM_ADDR, error, "dgnf_cmds addr drifted from allocator claim"
dgnf_hero_bin:
    .incbin "dgnf_hero.bin"
.assert ^dgnf_hero_bin = ES_R_DGNF_HERO_ROM_BANK, error, "dgnf_hero bank drifted from allocator claim"
.assert .loword(dgnf_hero_bin) = ES_R_DGNF_HERO_ROM_ADDR, error, "dgnf_hero addr drifted from allocator claim"
.segment "BANK6"
dgnf_res_bin:
    .incbin "dgnf_res.bin"
.assert ^dgnf_res_bin = ES_R_DGNF_RES_ROM_BANK, error, "dgnf_res bank drifted from allocator claim"
.assert .loword(dgnf_res_bin) = ES_R_DGNF_RES_ROM_ADDR, error, "dgnf_res addr drifted from allocator claim"
.segment "CODE"

; --- scenes -------------------------------------------------------------------
.include "scenes/fight.asm"

; --- sm_nmi_hook: per-frame VBlank work ---------------------------------------
; In: A8/I16, DB=0 (from sm_nmi_core). Two writers: the OAM shadow's GP-DMA, then the score's
; DMA rows for this tick (each programs its own VMAIN/VMADD, so the order is free).
sm_nmi_hook:
    .a8
    .i16
    jsr oam_nmi_dma
    jsr fight::dgnf_nmi_stream
    rts

; --- scene dispatch tables (manifest order: fight=0) ------------------------
sm_enter_tab:   .word fight::enter
sm_tick_tab:    .word fight::tick
sm_exit_tab:    .word fight::exit

; --- MAIN: boot -------------------------------------------------------------
; init.inc leaves: native, A16/I16, DB=0, forced blank, NMI+HDMA off.
MAIN:
    .a16
    .i16
    jsr sm_init
    jsr input_init
    jsr fade_init
    jsr oam_park_all            ; whole shadow written before its first DMA
    ldx #(SCENE_FIGHT * 2)
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
