"""director.py — the choreographer and the VBlank scheduler for the boss fight (docs/dungeons/19).

The scene is a SCORE: every actor's position, facing and animation frame on every tick of a loop, compiled
offline. Because the whole sequence is known, the director can do what a runtime cannot:

  1. BACK-BUFFER PREFETCH. Each streamed actor (the 64x64 boss, the two players) owns TWO VRAM buffers. The
     frame it will show next is DMA'd into the buffer that is NOT on screen, a row at a time, spread over the
     ticks the previous frame is held. The swap is free: OAM names point at the other buffer. A frame already
     sitting in the idle buffer (an idle that toggles A/B/A/B) costs nothing at all.
  2. WATER-FILLING. Each row of each prefetch may land on any tick in its window; the director puts it on the
     least-loaded one, so the peak per-tick DMA is the smallest the windows allow, not whatever coincided.
  3. MOVEMENT IS FREE. Walking, scuttling and leaping change OAM x/y only. They cost no VBlank bytes.

`mode="naive"` compiles the SAME score the unchoreographed way (one buffer, every row on the tick the frame
changes), which is the control the measurement compares against.

Everything here is pure Python (no numpy, no Blender) so tests/test_dgn_fight_score.py runs in milliseconds.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRE = REPO / "art" / "dungeons" / "creatures" / "specs"

# ---------------------------------------------------------------------------------------------------------------
# The animation library: which frame ids an action owns, and how long each is held (game frames at 60 Hz).
# ---------------------------------------------------------------------------------------------------------------
BOSS_ACTIONS = (("idle", 4), ("scuttle", 4), ("prepare", 3), ("attack", 3), ("whirl", 5))
BOSS_FPF = sum(n for _, n in BOSS_ACTIONS)             # 19 frames a facing
HERO_ACTIONS = (("idle", 2), ("walk", 4), ("attack", 3))
HERO_FPF = sum(n for _, n in HERO_ACTIONS)             # 9
ENEMY_ACTIONS = (("hop", 4), ("prepare", 3), ("attack", 3))
ENEMY_FPF = sum(n for _, n in ENEMY_ACTIONS)           # 10
FACINGS = ("down", "right")                            # facing index 0, 1; LEFT is the right frames flipped
HERO_HOLDS = {"idle": [30, 30], "walk": [8, 8, 8, 8], "attack": [6, 6, 10]}   # attack readable at 60 Hz


def _spec_holds(name: str) -> dict:
    s = tomllib.loads((CRE / f"{name}.toml").read_text())
    return {a: list(v["hold"]) for a, v in s["action"].items()}


def _anims(actions, holds):
    out, first = {}, 0
    for name, n in actions:
        assert len(holds[name]) == n, (name, n, holds[name])
        out[name] = (first, list(holds[name]))
        first += n
    return out


BOSS_HOLDS = _spec_holds("bellwretch64")
BOSS_ANIM = _anims(BOSS_ACTIONS, BOSS_HOLDS)
HERO_ANIM = _anims(HERO_ACTIONS, HERO_HOLDS)
EA_ANIM = _anims(ENEMY_ACTIONS, _spec_holds("thornhopper"))
EB_ANIM = _anims(ENEMY_ACTIONS, _spec_holds("thornling"))
ANIMS = {"boss": BOSS_ANIM, "p1": HERO_ANIM, "p2": HERO_ANIM, "ea": EA_ANIM, "eb": EB_ANIM}
FPF = {"boss": BOSS_FPF, "p1": HERO_FPF, "p2": HERO_FPF, "ea": ENEMY_FPF, "eb": ENEMY_FPF}
LOOPING = {"idle", "scuttle", "walk", "hop"}           # the others play once and hold their last frame

# ---------------------------------------------------------------------------------------------------------------
# Geometry (foot points are screen px; the anchors are each art's measured root pixel in its frame box).
# ---------------------------------------------------------------------------------------------------------------
BOSS_AX, BOSS_AY = 32, 46                              # 64x64 box
HERO_AX, HERO_AY, HERO_ATK_AX = 10, 27, 16            # 16x32 box / 32x32 attack box
EA_AX, EA_AY = 17, 24                                  # thornhopper, 32x32
EB_AX, EB_AY = 8, 12                                   # thornling, 16x16
SCREEN_W, SCREEN_H = 256, 224
HERO_ATK0 = 6                                          # a player's first attack frame within a facing

# ---------------------------------------------------------------------------------------------------------------
# Choreography: segments -> per-tick state
# ---------------------------------------------------------------------------------------------------------------


@dataclass
class Seg:
    action: str
    ticks: int
    to: tuple | None = None        # foot point at the END of the segment (None = stay)
    face: str = "down"             # 'down' | 'right' | 'left'
    scale: float = 1.0             # holds are multiplied by this (a longer telegraph reads better)


@dataclass
class St:
    x: int
    y: int
    frame: int                     # absolute frame id: facing-major (facing index * FPF + action frame)
    flip: bool
    action: str
    face: str


def scaled(holds, scale):
    return [max(1, round(h * scale)) for h in holds]


def action_ticks(kind, action, scale=1.0, cycles=1):
    return sum(scaled(ANIMS[kind][action][1], scale)) * cycles


def render_track(kind: str, segs, start, face0: str) -> list[St]:
    """Per-tick states of one actor. Position is a straight line to each segment's `to`; the animation plays
    the action's holds (looping the looping actions, holding the last frame of the others)."""
    out, pos = [], start
    for s in segs:
        first, holds = ANIMS[kind][s.action]
        seq = []
        for k, h in enumerate(scaled(holds, s.scale)):
            seq += [k] * h
        end = s.to if s.to is not None else pos
        fi = FACINGS.index("down" if s.face == "down" else "right")
        for i in range(s.ticks):
            if s.action in LOOPING:
                k = seq[i % len(seq)]
            else:
                k = seq[min(i, len(seq) - 1)]
            u = (i + 1) / s.ticks
            x = round(pos[0] + (end[0] - pos[0]) * u)
            y = round(pos[1] + (end[1] - pos[1]) * u)
            out.append(St(x, y, fi * FPF[kind] + first + k, s.face == "left", s.action, s.face))
        pos = end
    return out


# ---- the boss: a pre-programmed sequence of moves and attacks, travelling about the arena ----------------------
C0 = (100, 112)


def boss_segs():
    pre = action_ticks("boss", "prepare", 1.6)
    atk = action_ticks("boss", "attack", 1.6)
    whirl = action_ticks("boss", "whirl", 1.15)
    return [
        ("idle", Seg("idle", 56, None, "down")),
        ("scuttle_r", Seg("scuttle", 64, (160, 112), "right")),
        ("prepare_r", Seg("prepare", pre, None, "right", 1.6)),
        ("attack_r", Seg("attack", atk, None, "right", 1.6)),
        ("scuttle_l", Seg("scuttle", 96, (96, 112), "left")),
        ("prepare_l", Seg("prepare", pre, None, "left", 1.6)),
        ("attack_l", Seg("attack", atk, None, "left", 1.6)),
        ("scuttle_d", Seg("scuttle", 72, (128, 126), "down")),
        ("prepare_d", Seg("prepare", pre, None, "down", 1.6)),
        ("whirl_d", Seg("whirl", whirl, None, "down", 1.15)),
        ("scuttle_b", Seg("scuttle", 72, C0, "down")),
    ]


def boss_bounds():
    """name -> (start tick, end tick) of each boss segment."""
    t, out = 0, {}
    for name, s in boss_segs():
        out[name] = (t, t + s.ticks)
        t += s.ticks
    return out


def total_ticks() -> int:
    return sum(s.ticks for _, s in boss_segs())


def boss_states():
    return render_track("boss", [s for _, s in boss_segs()], C0, "down")


# ---- player 1: follows the boss and attacks from several angles, backing away from every attack ----------------
SAFE_R = 86                    # px from the boss foot at which a player is clear of its attacks
DANGER_R = 70                  # inside this, during a boss attack, is a hit
ATK_R = {"left": 40, "right": 40, "top": 46}


def _polar(boss_xy, theta, r):
    return (boss_xy[0] + r * math.cos(math.radians(theta)), boss_xy[1] - r * math.sin(math.radians(theta)))


def p1_keys(B):
    """(tick, theta deg (0 right, 90 top, 180 left), radius, anim) tied to the boss's own segment boundaries. The
    interval ENDING at a key plays that key's anim. Backing away walks while facing the boss."""
    L = action_ticks("p1", "attack")
    end = lambda n: B[n][1]
    start = lambda n: B[n][0]
    T = total_ticks()
    return [
        (0, 135, SAFE_R, "idle"),
        (start("scuttle_r"), 180, SAFE_R, "walk"),                    # drift round to the boss's left during its idle
        (end("scuttle_r") - L, 180, ATK_R["left"], "walk"),           # chase the scuttling boss from behind
        (end("scuttle_r"), 180, ATK_R["left"], "attack"),             # strike (LEFT of the boss)
        (end("prepare_r"), 180, SAFE_R, "walk"),                      # the telegraph: back away
        (end("attack_r"), 150, SAFE_R, "walk"),                       # the slam lands out of reach; circle
        (end("scuttle_l") - L - 32, 90, SAFE_R, "walk"),              # over the top of the boss
        (end("scuttle_l") - L, 90, ATK_R["top"], "walk"),             # close in from above
        (end("scuttle_l"), 90, ATK_R["top"], "attack"),               # strike (ABOVE the boss)
        (end("prepare_l"), 60, SAFE_R, "walk"),                       # back away, circling right
        (end("attack_l"), 25, SAFE_R, "walk"),
        (end("scuttle_d") - L - 28, 0, SAFE_R, "walk"),
        (end("scuttle_d") - L, 0, ATK_R["right"], "walk"),            # close in from the right
        (end("scuttle_d"), 0, ATK_R["right"], "attack"),              # strike (RIGHT of the boss)
        (end("prepare_d"), 0, SAFE_R, "walk"),                        # clear before the whirl
        (T, 135, SAFE_R, "walk"),                                     # the run back round, over the top
    ]


def _hero_facing(theta):
    """A player faces the boss. From the left it faces right, from the right it faces left (flipped), from above
    it faces down. There is no `up` art, so a player is never placed below the boss."""
    if theta > 120:
        return "right"
    if theta < 60:
        return "left"
    return "down"


def p1_states(boss, B):
    T = total_ticks()
    keys = p1_keys(B)
    assert keys[0][0] == 0 and keys[-1][0] == T, "the keys must span the loop"
    out = []
    atk_len = action_ticks("p1", "attack")
    for (t0, th0, r0, _a0), (t1, th1, r1, a1) in zip(keys, keys[1:]):
        assert t1 > t0, (t0, t1)
        if a1 == "attack":
            assert t1 - t0 == atk_len, f"an attack interval is exactly one attack: {t1 - t0} != {atk_len}"
        first, holds = HERO_ANIM[a1]
        seq = [k for k, h in enumerate(holds) for _ in range(h)]
        for i in range(t1 - t0):
            t = t0 + i
            u = (i + 1) / (t1 - t0)
            th, r = th0 + (th1 - th0) * u, r0 + (r1 - r0) * u
            bx, by = boss[t].x, boss[t].y
            x, y = _polar((bx, by), th, r)
            x, y = min(max(x, 24), 232), min(max(y, 44), 206)       # keep the player on the screen
            face = _hero_facing(th)
            k = seq[i % len(seq)] if a1 in LOOPING else seq[min(i, len(seq) - 1)]
            fi = FACINGS.index("down" if face == "down" else "right")
            out.append(St(round(x), round(y), fi * HERO_FPF + first + k, face == "left", a1, face))
    assert len(out) == T, (len(out), T)
    return out


# ---- player 2 vs the two small enemies: a round is a phase per enemy -------------------------------------------
P2_HOME = (178, 188)
EA_HOME, EB_HOME = (96, 176), (80, 196)
PHASE = 128


def _fight_phase(kind_e, home, stage_y, who_attacks):
    """One phase of 96 ticks. Returns (enemy segs, p2 segs) for an enemy that hops up, opens its bloom, leaps at
    player 2 and is hit back, while player 2 guards, dodges the leap and counters."""
    a = 28
    p = action_ticks(kind_e, "prepare")
    q = action_ticks(kind_e, "attack")
    r = PHASE - a - p - q
    stage = (P2_HOME[0] - 46, stage_y)
    land = (stage[0] + 28, stage_y)
    cnt = action_ticks("p2", "attack")
    dodge = (P2_HOME[0] + 22, P2_HOME[1])
    assert r - cnt >= 8, f"phase too short: retreat {r}, counter {cnt}"
    enemy = [Seg("hop", a, stage, "right"), Seg("prepare", p, None, "right"), Seg("attack", q, land, "right"),
             Seg("hop", r, home, "left")]
    p2 = [Seg("idle", a + p, None, "left"), Seg("walk", q, dodge, "left"), Seg("attack", cnt, None, "left"),
          Seg("walk", r - cnt, P2_HOME, "left")]
    return enemy, p2


def fight_states(T):
    ea, eb, p2 = [], [], []
    ea_pos, eb_pos = EA_HOME, EB_HOME
    phases = T // PHASE
    for n in range(phases):
        if n % 2 == 0:                       # enemy A's turn; B bobs at home
            e, p = _fight_phase("ea", EA_HOME, EA_HOME[1], "ea")
            ea += render_track("ea", e, EA_HOME, "right")
            eb += render_track("eb", [Seg("hop", PHASE, None, "right")], EB_HOME, "right")
        else:
            e, p = _fight_phase("eb", EB_HOME, EB_HOME[1], "eb")
            eb += render_track("eb", e, EB_HOME, "right")
            ea += render_track("ea", [Seg("hop", PHASE, None, "right")], EA_HOME, "right")
        p2 += render_track("p2", p, P2_HOME, "left")
    rest = T - phases * PHASE                # a closing breather: everyone holds their home
    ea += render_track("ea", [Seg("hop", rest, None, "right")], EA_HOME, "right")
    eb += render_track("eb", [Seg("hop", rest, None, "right")], EB_HOME, "right")
    p2 += render_track("p2", [Seg("idle", rest, None, "left")], P2_HOME, "left")
    return ea, eb, p2


def all_states():
    boss = boss_states()
    T = len(boss)
    B = boss_bounds()
    p1 = p1_states(boss, B)
    ea, eb, p2 = fight_states(T)
    for k, v in (("p1", p1), ("ea", ea), ("eb", eb), ("p2", p2)):
        assert len(v) == T, (k, len(v), T)
    return {"boss": boss, "p1": p1, "p2": p2, "ea": ea, "eb": eb}


# ---------------------------------------------------------------------------------------------------------------
# The streamed actors, their VRAM buffers and the prefetch scheduler
# ---------------------------------------------------------------------------------------------------------------
# OBJ name table 0 is 16 tiles wide. Buffers are (tile column, tile row) of the slot's top-left tile.
SLOTS = {
    "boss": {"bufs": [(0, 0), (8, 0)], "rows": 8, "row_bytes": 256, "frame_bytes": 2048},
    "p1": {"bufs": [(0, 8), (4, 8)], "rows": 4, "row_bytes": 128, "frame_bytes": 512},
    "p2": {"bufs": [(8, 8), (12, 8)], "rows": 4, "row_bytes": 128, "frame_bytes": 512},
}
BOSS_FRAMES_PER_BLOB = 14
ARM_BYTES = 85                 # measured: a transfer costs about this many byte-times beyond its bytes (docs/18)


def name_of(actor: str, buf: int) -> int:
    col, row = SLOTS[actor]["bufs"][buf]
    return row * 16 + col


def vmadd_of(actor: str, buf: int, row: int) -> int:
    """VRAM word offset (from the OBJ claim base) of a slot's tile row `row`: 16 tiles x 16 words a row."""
    col, r0 = SLOTS[actor]["bufs"][buf]
    return ((r0 + row) * 16 + col) * 16


def src_of(actor: str, frame: int, row: int):
    """(blob id, byte offset in the blob) of one tile row of a frame in the ROM frame stores."""
    if actor == "boss":
        return frame // BOSS_FRAMES_PER_BLOB, (frame % BOSS_FRAMES_PER_BLOB) * 2048 + row * 256
    return 3, frame * 512 + row * 128          # the players share one blob (id 3), a facing-major 512 B slot image


class Layout:
    """Where each streamed actor's buffers live in VRAM and where its rows come from in ROM. The fight's own is
    FIGHT_LAYOUT (the module defaults); another rail passes its own (tools/dgn_giant: two players only)."""

    def __init__(self, slots, vmadd, src):
        self.slots, self.vmadd_of, self.src_of = slots, vmadd, src


FIGHT_LAYOUT = Layout(SLOTS, vmadd_of, src_of)


def displayed_frames(states, layout=None):
    actors = (layout.slots if layout else SLOTS)
    return {a: [s.frame for s in states[a]] for a in actors}


VIRT = 100000                  # a frame id + VIRT is the same picture shown from the other buffer (the parity swap)


def _add_parity_swap(seq):
    """Every change flips the displayed buffer, so an actor with an ODD number of changes in the loop would come
    round to the other buffer and the pattern would repeat every TWO loops. Add one deliberate swap in the middle
    of the longest hold: the same frame, shown from the other buffer (it costs one prefetch, spread over the hold)."""
    T = len(seq)
    if sum(1 for t in range(T) if seq[t] != seq[t - 1]) % 2 == 0:
        return seq
    starts = [t for t in range(T) if seq[t] != seq[t - 1]]
    best = max(range(len(starts)), key=lambda i: (starts[(i + 1) % len(starts)] - starts[i]) % T or T)
    a = starts[best]
    b = starts[(best + 1) % len(starts)]
    length = (b - a) % T or T
    out = list(seq)
    for i in range(length // 2, length):
        out[(a + i) % T] = seq[a] + VIRT
    return out


def plan_buffers(seq, naive=False):
    """Per tick: which of the actor's two buffers is displayed, and the prefetch jobs.

    Returns (bufsel per tick, jobs, init) where a job is (frame, buffer, release tick, deadline tick) in
    UNROLLED ticks of the final pass (a release may be negative: it belongs to the previous iteration), and
    `init` is the [content of buffer 0, buffer 1] the loop needs on entry (steady state)."""
    T = len(seq)
    if not naive:
        seq = _add_parity_swap(seq)
    if naive:                                   # one buffer; every change is loaded on the tick it happens
        jobs = [(seq[t], 0, t, t) for t in range(T) if seq[t] != seq[t - 1]]
        return [0] * T, jobs, [seq[0], None]
    content, disp = [seq[0], None], 0
    last_off = [-T, -T]                         # unrolled tick each buffer last stopped being displayed
    for _ in range(8):                          # iterate to the steady state: the wrap must not be a special case
        start = (list(content), disp, [v for v in last_off])
        jobs, bufsel = [], []
        content, disp, last_off = list(start[0]), start[1], list(start[2])
        for t in range(T):
            if content[disp] != seq[t]:         # a change: show the frame from the OTHER buffer
                free = 1 - disp
                if content[free] != seq[t]:
                    assert last_off[free] <= t
                    jobs.append((seq[t], free, last_off[free], t))
                    content[free] = seq[t]
                last_off[disp] = t
                disp = free
            bufsel.append(disp)
        # the next pass starts one period later: every release moves back by T
        nxt = (list(content), disp, [v - T for v in last_off])
        if (nxt[0], nxt[1]) == (start[0], start[1]) and nxt[2] == start[2]:
            break
        content, disp, last_off = nxt
    else:
        raise AssertionError("the buffer plan did not reach a steady state")
    for frame, buf, rel, d in jobs:
        assert d - rel < T, "a prefetch window wider than the loop: the buffer would be overwritten while it is shown"
    return bufsel, jobs, start[0]


def schedule_rows(all_jobs, T, naive_actors=frozenset(), layout=None):
    """Assign every row of every job to a tick in its window (mod T), least-loaded first. Actors in `naive_actors`
    are not planned: each of their rows lands on the tick the frame changes. Returns
    ({tick: [(actor, dst, id, off, bytes, frame, buf, row)]}, bytes per tick, load per tick)."""
    L = layout or FIGHT_LAYOUT
    rows = []                                   # (window length, deadline, actor, frame, buf, row, rel, d)
    for actor, jobs in all_jobs.items():
        sl = L.slots[actor]
        for frame, buf, rel, d in jobs:
            for row in range(sl["rows"]):
                rows.append((d - rel, d, actor, frame % VIRT, buf, row, rel, d))
    rows.sort()
    load = [0] * T
    out = {}
    assign = []
    for _, _, actor, frame, buf, row, rel, d in rows:
        sl = L.slots[actor]
        if actor in naive_actors:
            t = d % T
        else:
            best = min(range(rel, d + 1), key=lambda u: (load[u % T], u))
            t = best % T
        load[t] += sl["row_bytes"] + ARM_BYTES
        assign.append([actor, frame, buf, row, rel, d, t])
    if len(naive_actors) < len(all_jobs):        # local search: move a planned row to a lighter tick of its window
        for _ in range(8):
            moved = False
            for a in assign:
                actor, frame, buf, row, rel, d, t = a
                if actor in naive_actors:
                    continue
                cost = L.slots[actor]["row_bytes"] + ARM_BYTES
                best = min(range(rel, d + 1), key=lambda u: (load[u % T], u))
                if load[best % T] + cost < load[t]:          # the move strictly lowers the heavier of the two ticks
                    load[t] -= cost
                    load[best % T] += cost
                    a[6] = best % T
                    moved = True
            if not moved:
                break
    for actor, frame, buf, row, rel, d, t in assign:
        sl = L.slots[actor]
        bid, off = L.src_of(actor, frame, row)
        out.setdefault(t, []).append((actor, L.vmadd_of(actor, buf, row), bid, off, sl["row_bytes"], frame, buf, row))
    return out, [sum(c[4] for c in out.get(t, [])) for t in range(T)], load


MODES = {"choreo": frozenset(), "naive": frozenset({"boss", "p1", "p2"}),
         "hybrid": frozenset({"p1", "p2"})}     # hybrid: what a real game can do, the players follow human input


def compile_stream(states, naive=False, mode=None, layout=None):
    """The whole stream plan: per-tick buffer selection, per-tick DMA commands, the entry state.

    `mode`: 'choreo' plans every streamed actor; 'naive' plans none (one buffer, every row on the tick its frame
    changes); 'hybrid' plans the boss only, because the players' frames follow human input and cannot be known
    ahead. (`naive=True` is the old spelling of mode='naive'.)"""
    L = layout or FIGHT_LAYOUT
    mode = mode or ("naive" if naive else "choreo")
    unplanned = MODES[mode]
    T = len(states[next(iter(L.slots))])
    seqs = displayed_frames(states, L)
    bufsel, jobs, init = {}, {}, {}
    for a in L.slots:
        bufsel[a], jobs[a], init[a] = plan_buffers(seqs[a], a in unplanned)
    cmds, bytes_per_tick, load = schedule_rows(jobs, T, unplanned, L)
    # THE ENTRY STATE, by physical simulation at ROW level. A prefetch whose window straddles the loop's wrap has
    # its first rows in the previous iteration's tail, so the state the loop needs at tick 0 is NOT the planner's
    # frame-level start: it is whatever the rows leave behind after a full iteration, possibly a half-loaded
    # buffer. Play the stream until that repeats and load exactly it, in forced blank.
    cell = {}
    for a in L.slots:
        for buf, frame in enumerate(init[a]):
            if frame is not None:
                for row in range(L.slots[a]["rows"]):
                    cell[(a, buf, row)] = frame % VIRT
    prev = None
    for _ in range(4):
        for t in range(T):
            for actor, dst, bid, off, nbytes, frame, buf, row in cmds.get(t, []):
                cell[(actor, buf, row)] = frame
        if cell == prev:
            break
        prev = dict(cell)
    else:
        raise AssertionError("the stream's end-of-loop state did not repeat")
    init_cmds = []
    for (a, buf, row), frame in sorted(cell.items()):
        bid, off = L.src_of(a, frame, row)
        init_cmds.append((a, L.vmadd_of(a, buf, row), bid, off, L.slots[a]["row_bytes"], frame, buf, row))
    return {"bufsel": bufsel, "jobs": jobs, "cmds": cmds, "bytes": bytes_per_tick, "init_cmds": init_cmds,
            "init": init, "T": T}


# ---------------------------------------------------------------------------------------------------------------
# The OAM record of one tick: 12 entries (x, y, name, attr) and 3 hi-table bytes, 51 bytes
# ---------------------------------------------------------------------------------------------------------------
RECORD_BYTES = 12 * 4 + 3
PARK_Y = 240
PRI3 = 3 << 4
ATTR = {"p1": PRI3 | (0 << 1), "p2": PRI3 | (1 << 1), "boss": PRI3 | (2 << 1), "e": PRI3 | (3 << 1) | 1}
HFLIP = 1 << 6
HERO_NAME = {"p1": None, "p2": None}                    # from the buffer
EA_NAME = lambda f: (f // 4) * 64 + (f % 4) * 4         # name within table 1: frames 4 to a 4-row band
EB_NAME = lambda f: 12 * 16 + (f // 8) * 32 + (f % 8) * 2


def build_record(states, plan, t):
    """The 51 bytes the ROM copies into the OAM shadow on tick t."""
    ent = [[0, PARK_Y, 0, 0] for _ in range(12)]
    hi = [0, 0, 0]

    def set_hi(slot, large, x9=0):
        hi[slot // 4] |= ((2 if large else 0) | x9) << ((slot % 4) * 2)

    for slot0, who in ((0, "p1"), (2, "p2")):
        s = states[who][t]
        buf = plan["bufsel"][who][t]
        name = name_of(who, buf)
        fr = s.frame % HERO_FPF
        attr = ATTR[who] | (HFLIP if s.flip else 0)
        y = s.y - (HERO_AY + 1)
        if fr >= HERO_ATK0:                              # one 32x32; the second slot stays parked
            x = s.x - ((31 - HERO_ATK_AX) if s.flip else HERO_ATK_AX)
            ent[slot0] = [x, y, name, attr]
            set_hi(slot0, True)
        else:                                            # two stacked 16x16
            x = s.x - ((15 - HERO_AX) if s.flip else HERO_AX)
            ent[slot0] = [x, y, name, attr]
            ent[slot0 + 1] = [x, y + 16, name + 32, attr]
    s = states["ea"][t]
    f = s.frame % ENEMY_FPF
    x = s.x - ((31 - EA_AX) if s.flip else EA_AX)
    ent[4] = [x, s.y - (EA_AY + 1), EA_NAME(f), ATTR["e"] | (HFLIP if s.flip else 0)]
    set_hi(4, True)
    s = states["eb"][t]
    f = s.frame % ENEMY_FPF
    x = s.x - ((15 - EB_AX) if s.flip else EB_AX)
    ent[5] = [x, s.y - (EB_AY + 1), EB_NAME(f), ATTR["e"] | (HFLIP if s.flip else 0)]
    s = states["boss"][t]
    base = name_of("boss", plan["bufsel"]["boss"][t])
    quad = [base, base + 4, base + 64, base + 68]       # TL TR BL BR
    x0 = s.x - ((63 - BOSS_AX) if s.flip else BOSS_AX)
    y0 = s.y - (BOSS_AY + 1)
    cols = [(x0, 1), (x0 + 32, 0)] if s.flip else [(x0, 0), (x0 + 32, 1)]
    attr = ATTR["boss"] | (HFLIP if s.flip else 0)
    for row in range(2):
        for ci, (cx, qc) in enumerate(cols):
            slot = 6 + row * 2 + ci
            ent[slot] = [cx, y0 + 32 * row, quad[row * 2 + qc], attr]
            set_hi(slot, True)
    for e in ent:
        assert -0 <= e[0] <= 255 or e[1] == PARK_Y, f"an entry left the 0..255 band: {e}"
        assert 0 <= e[1] <= 255
    rec = bytearray()
    for e in ent:
        rec += bytes((e[0] & 255, e[1] & 255, e[2] & 255, e[3] & 255))
    rec += bytes(hi)
    assert len(rec) == RECORD_BYTES
    return bytes(rec)


def compile_all(naive=False):
    states = all_states()
    plan = compile_stream(states, naive)
    T = plan["T"]
    records = [build_record(states, plan, t) for t in range(T)]
    return states, plan, records


def command_bytes(plan):
    """The per-tick command stream the ROM plays: 6 B a command (dst u16, src offset u16, id u8, pad) and a
    u16 pointer table of T + 1 byte offsets. Rows are ordered boss, p1, p2 within a tick for determinism."""
    order = {"boss": 0, "p1": 1, "p2": 2}
    stream, ptrs = bytearray(), []
    for t in range(plan["T"]):
        ptrs.append(len(stream))
        for actor, dst, bid, off, nbytes, *_ in sorted(plan["cmds"].get(t, []), key=lambda c: (order[c[0]], c[1])):
            stream += dst.to_bytes(2, "little") + off.to_bytes(2, "little") + bytes((bid, 0))
    ptrs.append(len(stream))
    return bytes(stream), b"".join(p.to_bytes(2, "little") for p in ptrs)


def init_bytes(plan):
    out = bytearray()
    for actor, dst, bid, off, nbytes, *_ in plan["init_cmds"]:
        out += dst.to_bytes(2, "little") + off.to_bytes(2, "little") + bytes((bid, 0))
    return bytes(out)


def stats(plan):
    b = plan["bytes"]
    n = [len(plan["cmds"].get(t, [])) for t in range(plan["T"])]
    return {"peak_bytes": max(b), "peak_transfers": max(n), "total_bytes": sum(b),
            "mean_bytes": sum(b) / len(b), "ticks_with_dma": sum(1 for v in b if v),
            "hist": {str(k): sum(1 for v in b if v == k) for k in sorted(set(b))}}
