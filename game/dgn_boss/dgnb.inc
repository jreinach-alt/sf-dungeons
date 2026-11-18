; =============================================================================
; dgnb.inc — the boss-battle rail's geometry (docs/dungeons/18)
; =============================================================================
; Pure equates. Frame counts, holds and anchors come from the generated
; dgnb_frames.inc (tools/gen_dgn_boss_assets.py), never retyped here.

; --- foot points (screen px) ---------------------------------------------------
DGNB_BOSS_X = 128        ; the boss: a 64x64 frame, anchor (32, 46)
DGNB_BOSS_Y = 104
DGNB_P1_X = 72           ; the players, near the bottom, facing the boss
DGNB_P2_X = 184
DGNB_HERO_Y = 176
DGNB_EA_Y = 150          ; enemy A (32x32) ping-pongs between x 40 and 103
DGNB_EA_X0 = 40
DGNB_EB_Y = 134          ; enemy B (16x16) between 214 and 151
DGNB_EB_X0 = 214

; --- OBJ names in the 16-tile-wide OBJ name table --------------------------------
DGNB_NAME_BOSS = 0       ; tile (row 0, col 0): the boss's 8x8 tile frame
DGNB_NAME_P1 = 8         ; col 8, rows 0-3: a 4x4 slot
DGNB_NAME_P2 = 12        ; col 12
DGNB_NAME_EB = 64        ; in table 1 (N bit set): rows 4-5 of the resident blob

; --- OAM slots (feature.toml's pinned claim) -------------------------------------
DGNB_SL_P1 = 0           ; top; the bottom half is +1
DGNB_SL_P2 = 2
DGNB_SL_EA = 4
DGNB_SL_EB = 5
DGNB_SL_BOSS = 6         ; TL, TR, BL, BR

; --- OAM attribute bytes: vhoopppN ---------------------------------------------------
DGNB_PRI3 = 3 << 4
DGNB_ATTR_P1 = DGNB_PRI3 | (0 << 1)
DGNB_ATTR_P2 = DGNB_PRI3 | (1 << 1) | (1 << 6)    ; palette 1, and facing LEFT: HFLIP
DGNB_ATTR_BOSS = DGNB_PRI3 | (2 << 1)
DGNB_ATTR_E = DGNB_PRI3 | (3 << 1) | 1           ; palette 3, name table 1
DGNB_HFLIP = 1 << 6

; --- scene ids (game.toml manifest order) --------------------------------------------
SCENE_ARENA = 0
