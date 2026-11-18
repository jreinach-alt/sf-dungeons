; =============================================================================
; dgn_boss — SuperForge Dungeons' boss-battle spike (docs/dungeons/18). ROM skeleton.
; =============================================================================
; NOTHING HERE IS HAND-PLACED: every RAM/VRAM/CGRAM address, channel and
; register base comes from the allocator's emitted includes; hardware I/O
; ports are the only literals (no_literals-gated).
;
; OBJ ONLY, ONE SCENE, NO AUDIO, NO INPUT: the ROM boots into the arena and
; stays there. The art is the committed output of the creature and style pipelines,
; converted by tools/gen_dgn_boss_assets.py.
.p816
.smart

.define SF_HDR_TITLE "DGN BOSS SPIKE"
SF_HDR_TITLE_SET = 1
.include "engine_state_globals.inc" ; GENERATED — system + game-lifetime map
.include "dgnb_frames.inc"          ; GENERATED — anchors and the five timelines
.include "dgnb.inc"                 ; the rail's geometry
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
; build/dgnb/allocation_report.txt), each site asserted against the claim ----
.segment "BANK1"
dgnb_boss_down_bin:
    .incbin "dgnb_boss_down.bin"
.assert ^dgnb_boss_down_bin = ES_R_DGNB_BOSS_DOWN_ROM_BANK, error, "dgnb_boss_down bank drifted from allocator claim"
.assert .loword(dgnb_boss_down_bin) = ES_R_DGNB_BOSS_DOWN_ROM_ADDR, error, "dgnb_boss_down addr drifted from allocator claim"
dgnb_res_bin:
    .incbin "dgnb_res.bin"
.assert ^dgnb_res_bin = ES_R_DGNB_RES_ROM_BANK, error, "dgnb_res bank drifted from allocator claim"
.assert .loword(dgnb_res_bin) = ES_R_DGNB_RES_ROM_ADDR, error, "dgnb_res addr drifted from allocator claim"
dgnb_pal_bin:
    .incbin "dgnb_pal.bin"
.assert ^dgnb_pal_bin = ES_R_DGNB_PAL_ROM_BANK, error, "dgnb_pal bank drifted from allocator claim"
.assert .loword(dgnb_pal_bin) = ES_R_DGNB_PAL_ROM_ADDR, error, "dgnb_pal addr drifted from allocator claim"
.segment "BANK2"
dgnb_boss_right_bin:
    .incbin "dgnb_boss_right.bin"
.assert ^dgnb_boss_right_bin = ES_R_DGNB_BOSS_RIGHT_ROM_BANK, error, "dgnb_boss_right bank drifted from allocator claim"
.assert .loword(dgnb_boss_right_bin) = ES_R_DGNB_BOSS_RIGHT_ROM_ADDR, error, "dgnb_boss_right addr drifted from allocator claim"
.segment "BANK3"
dgnb_hero_bin:
    .incbin "dgnb_hero.bin"
.assert ^dgnb_hero_bin = ES_R_DGNB_HERO_ROM_BANK, error, "dgnb_hero bank drifted from allocator claim"
.assert .loword(dgnb_hero_bin) = ES_R_DGNB_HERO_ROM_ADDR, error, "dgnb_hero addr drifted from allocator claim"
.segment "CODE"

; --- scenes -------------------------------------------------------------------
.include "scenes/arena.asm"

; --- sm_nmi_hook: per-frame VBlank work ---------------------------------------
; In: A8/I16, DB=0 (from sm_nmi_core). Two writers: the OAM shadow's GP-DMA, then the
; boss and player CHR stream (each programs its own VMAIN/VMADD, so the order is free).
sm_nmi_hook:
    .a8
    .i16
    jsr oam_nmi_dma
    jsr arena::dgnb_nmi_stream
    rts

; --- scene dispatch tables (manifest order: arena=0) ------------------------
sm_enter_tab:   .word arena::enter
sm_tick_tab:    .word arena::tick
sm_exit_tab:    .word arena::exit

; --- MAIN: boot -------------------------------------------------------------
; init.inc leaves: native, A16/I16, DB=0, forced blank, NMI+HDMA off.
MAIN:
    .a16
    .i16
    jsr sm_init
    jsr input_init
    jsr fade_init
    jsr oam_park_all            ; whole shadow written before its first DMA
    ldx #(SCENE_ARENA * 2)
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
