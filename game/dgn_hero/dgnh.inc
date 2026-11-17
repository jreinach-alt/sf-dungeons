; =============================================================================
; dgnh.inc — the dgn_hero rail's geometry
; =============================================================================
; Pure equates. The frame indices, holds and anchor come from the generated
; dgnh_frames.inc (tools/gen_dgn_hero_assets.py), never retyped here.

; --- the lineup: foot points (screen px) -------------------------------------
DGNH_COL0 = 56
DGNH_COL_STEP = 48
DGNH_ROW_WALK = 84       ; P1, walk, four facings (foot y; a figure is 32 tall)
DGNH_ROW_IDLE = 132      ; P2, idle, four facings
DGNH_ROW_PATH = 188      ; the walker's path
DGNH_WALK_X0 = 40        ; the walker's first foot x

; --- the walker's ground speed: 1.5 px per 60 Hz frame -----------------------
; actions.toml: "a 32-frame cycle = 1.5 px/tick * 32 = 48 px stride pair".
DGNH_SPEED = (TS_ONE * 3) / 2
DGNH_WRAP_HI = 1 << 8    ; foot x at or past the right edge ...
DGNH_WRAP_LO = 16        ; ... re-enters at -16 (fully off the left)

; --- scene ids (game.toml manifest order) -----------------------------------
SCENE_SHOW = 0
