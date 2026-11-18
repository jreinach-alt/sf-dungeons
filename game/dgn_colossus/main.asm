; =============================================================================
; dgn_colossus — SuperForge Dungeons' tile-streamed giant boss (docs/dungeons/21). ROM skeleton.
; =============================================================================
; NOTHING HERE IS HAND-PLACED: every RAM/VRAM/CGRAM address, channel and
; register base comes from the allocator's emitted includes; hardware I/O
; ports are the only literals (no_literals-gated).
;
; OBJ ONLY, ONE SCENE, NO AUDIO, NO INPUT: the ROM boots into the colossus and
; stays there. The art is the committed output of the creature and style pipelines,
; converted by tools/gen_dgn_tile_assets.py.
.p816
.smart

.define SF_HDR_TITLE "DGN COLOSSUS SPIKE"
SF_HDR_TITLE_SET = 1
.include "engine_state_globals.inc" ; GENERATED — system + game-lifetime map
.include "dgnt_frames.inc"          ; GENERATED — the score's length, record layout and CHR size
SCENE_COLOSSUS = 0                     ; game.toml manifest order
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
; build/dgnc/allocation_report.txt), each site asserted against the claim ----
.segment "BANK1"
dgnt_pool0_bin:
    .incbin "dgnt_pool0.bin"
.assert ^dgnt_pool0_bin = ES_R_DGNT_POOL0_ROM_BANK, error, "dgnt_pool0 bank drifted from allocator claim"
.assert .loword(dgnt_pool0_bin) = ES_R_DGNT_POOL0_ROM_ADDR, error, "dgnt_pool0 addr drifted from allocator claim"
dgnt_floor_bin:
    .incbin "dgnt_floor.bin"
.assert ^dgnt_floor_bin = ES_R_DGNT_FLOOR_ROM_BANK, error, "dgnt_floor bank drifted from allocator claim"
.assert .loword(dgnt_floor_bin) = ES_R_DGNT_FLOOR_ROM_ADDR, error, "dgnt_floor addr drifted from allocator claim"
dgnt_pal_bin:
    .incbin "dgnt_pal.bin"
.assert ^dgnt_pal_bin = ES_R_DGNT_PAL_ROM_BANK, error, "dgnt_pal bank drifted from allocator claim"
.assert .loword(dgnt_pal_bin) = ES_R_DGNT_PAL_ROM_ADDR, error, "dgnt_pal addr drifted from allocator claim"
.segment "BANK2"
dgnt_pool1_bin:
    .incbin "dgnt_pool1.bin"
.assert ^dgnt_pool1_bin = ES_R_DGNT_POOL1_ROM_BANK, error, "dgnt_pool1 bank drifted from allocator claim"
.assert .loword(dgnt_pool1_bin) = ES_R_DGNT_POOL1_ROM_ADDR, error, "dgnt_pool1 addr drifted from allocator claim"
dgnt_ptr_bin:
    .incbin "dgnt_ptr.bin"
.assert ^dgnt_ptr_bin = ES_R_DGNT_PTR_ROM_BANK, error, "dgnt_ptr bank drifted from allocator claim"
.assert .loword(dgnt_ptr_bin) = ES_R_DGNT_PTR_ROM_ADDR, error, "dgnt_ptr addr drifted from allocator claim"
.segment "BANK3"
dgnt_pool2_bin:
    .incbin "dgnt_pool2.bin"
.assert ^dgnt_pool2_bin = ES_R_DGNT_POOL2_ROM_BANK, error, "dgnt_pool2 bank drifted from allocator claim"
.assert .loword(dgnt_pool2_bin) = ES_R_DGNT_POOL2_ROM_ADDR, error, "dgnt_pool2 addr drifted from allocator claim"
.segment "BANK4"
dgnt_pool3_bin:
    .incbin "dgnt_pool3.bin"
.assert ^dgnt_pool3_bin = ES_R_DGNT_POOL3_ROM_BANK, error, "dgnt_pool3 bank drifted from allocator claim"
.assert .loword(dgnt_pool3_bin) = ES_R_DGNT_POOL3_ROM_ADDR, error, "dgnt_pool3 addr drifted from allocator claim"
.segment "BANK5"
dgnt_pool4_bin:
    .incbin "dgnt_pool4.bin"
.assert ^dgnt_pool4_bin = ES_R_DGNT_POOL4_ROM_BANK, error, "dgnt_pool4 bank drifted from allocator claim"
.assert .loword(dgnt_pool4_bin) = ES_R_DGNT_POOL4_ROM_ADDR, error, "dgnt_pool4 addr drifted from allocator claim"
.segment "BANK6"
dgnt_pool5_bin:
    .incbin "dgnt_pool5.bin"
.assert ^dgnt_pool5_bin = ES_R_DGNT_POOL5_ROM_BANK, error, "dgnt_pool5 bank drifted from allocator claim"
.assert .loword(dgnt_pool5_bin) = ES_R_DGNT_POOL5_ROM_ADDR, error, "dgnt_pool5 addr drifted from allocator claim"
.segment "BANK7"
dgnt_pool6_bin:
    .incbin "dgnt_pool6.bin"
.assert ^dgnt_pool6_bin = ES_R_DGNT_POOL6_ROM_BANK, error, "dgnt_pool6 bank drifted from allocator claim"
.assert .loword(dgnt_pool6_bin) = ES_R_DGNT_POOL6_ROM_ADDR, error, "dgnt_pool6 addr drifted from allocator claim"
.segment "BANK8"
dgnt_score_bin:
    .incbin "dgnt_score.bin"
.assert ^dgnt_score_bin = ES_R_DGNT_SCORE_ROM_BANK, error, "dgnt_score bank drifted from allocator claim"
.assert .loword(dgnt_score_bin) = ES_R_DGNT_SCORE_ROM_ADDR, error, "dgnt_score addr drifted from allocator claim"
dgnt_hero_bin:
    .incbin "dgnt_hero.bin"
.assert ^dgnt_hero_bin = ES_R_DGNT_HERO_ROM_BANK, error, "dgnt_hero bank drifted from allocator claim"
.assert .loword(dgnt_hero_bin) = ES_R_DGNT_HERO_ROM_ADDR, error, "dgnt_hero addr drifted from allocator claim"
.segment "BANK9"
dgnt_cmds_bin:
    .incbin "dgnt_cmds.bin"
.assert ^dgnt_cmds_bin = ES_R_DGNT_CMDS_ROM_BANK, error, "dgnt_cmds bank drifted from allocator claim"
.assert .loword(dgnt_cmds_bin) = ES_R_DGNT_CMDS_ROM_ADDR, error, "dgnt_cmds addr drifted from allocator claim"
.segment "CODE"

; --- scenes -------------------------------------------------------------------
.include "scenes/colossus.asm"

; --- sm_nmi_hook: per-frame VBlank work ---------------------------------------
; In: A8/I16, DB=0 (from sm_nmi_core). The OAM shadow's GP-DMA, the Mode 7 matrix commit (a handful of register
; writes), then the score's DMA rows for this tick (each programs its own VMAIN/VMADD, so the order is free).
sm_nmi_hook:
    .a8
    .i16
    jsr oam_nmi_dma
    jsr colossus::dgnt_bg_commit
    jsr colossus::dgnt_nmi_stream
    rts

; --- scene dispatch tables (manifest order: colossus=0) ------------------------
sm_enter_tab:   .word colossus::enter
sm_tick_tab:    .word colossus::tick
sm_exit_tab:    .word colossus::exit

; --- MAIN: boot -------------------------------------------------------------
; init.inc leaves: native, A16/I16, DB=0, forced blank, NMI+HDMA off.
MAIN:
    .a16
    .i16
    jsr sm_init
    jsr input_init
    jsr fade_init
    jsr oam_park_all            ; whole shadow written before its first DMA
    ldx #(SCENE_COLOSSUS * 2)
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
