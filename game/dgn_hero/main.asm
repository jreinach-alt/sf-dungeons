; =============================================================================
; dgn_hero — SuperForge Dungeons' model spike, on the console. ROM skeleton.
; =============================================================================
; NOTHING HERE IS HAND-PLACED: every RAM/VRAM/CGRAM address, channel and
; register base comes from the allocator's emitted includes; hardware I/O
; ports are the only literals (no_literals-gated).
;
; OBJ ONLY, ONE SCENE, NO AUDIO, NO INPUT: the ROM boots into the lineup and
; stays there. The art is the committed output of the Blender spike
; (art/dungeons/actors/frames/), converted by tools/gen_dgn_hero_assets.py.
.p816
.smart

.define SF_HDR_TITLE "DGN HERO SPIKE"
SF_HDR_TITLE_SET = 1
.include "engine_state_globals.inc" ; GENERATED — system + game-lifetime map
.include "dgnh_frames.inc"          ; GENERATED — frame indices, holds, anchor
.include "dgnh.inc"                 ; the rail's geometry
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
.include "region.asm"               ; $213F bit 4 -> ES_RGN_PAL, once at boot
.include "tick_scale.asm"           ; TS_STEP: defined before the scene uses it

; --- global ROM blobs: ORDER = the allocator's packing (largest first; see
; build/dgnh/allocation_report.txt), each site asserted against the claim ----
.segment "BANK1"
dgnh_obj_chr_bin:
    .incbin "dgnh_obj_chr.bin"
.assert ^dgnh_obj_chr_bin = ES_R_DGNH_OBJ_CHR_ROM_BANK, error, "dgnh_obj_chr bank drifted from allocator claim"
.assert .loword(dgnh_obj_chr_bin) = ES_R_DGNH_OBJ_CHR_ROM_ADDR, error, "dgnh_obj_chr addr drifted from allocator claim"
dgnh_obj_pal_bin:
    .incbin "dgnh_obj_pal.bin"
.assert ^dgnh_obj_pal_bin = ES_R_DGNH_OBJ_PAL_ROM_BANK, error, "dgnh_obj_pal bank drifted from allocator claim"
.assert .loword(dgnh_obj_pal_bin) = ES_R_DGNH_OBJ_PAL_ROM_ADDR, error, "dgnh_obj_pal addr drifted from allocator claim"
.segment "CODE"

; --- scenes -------------------------------------------------------------------
.include "scenes/show.asm"

; --- sm_nmi_hook: per-frame VBlank work ---------------------------------------
; In: A8/I16, DB=0 (from sm_nmi_core). ONE writer: the OAM shadow's GP-DMA.
sm_nmi_hook:
    .a8
    .i16
    jsr oam_nmi_dma
    rts

; --- scene dispatch tables (manifest order: show=0) -------------------------
sm_enter_tab:   .word show::enter
sm_tick_tab:    .word show::tick
sm_exit_tab:    .word show::exit

; --- MAIN: boot -------------------------------------------------------------
; init.inc leaves: native, A16/I16, DB=0, forced blank, NMI+HDMA off.
MAIN:
    .a16
    .i16
    jsr sm_init
    jsr input_init
    jsr fade_init
    jsr region_init
    jsr oam_park_all            ; whole shadow written before its first DMA
    ldx #(SCENE_SHOW * 2)
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
