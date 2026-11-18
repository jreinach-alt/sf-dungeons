"""director.py — the sequence, the scheduler and the players for the tile-streamed giant boss (docs/dungeons/21).

THE SCHEDULER IS THE SOLVER. A scene is an ordered list of EVENTS (show this picture, lengthen the blade, hold,
shorten it). Every event that changes what is on screen needs tiles in VRAM first, and a tick has a fixed amount of
VBlank DMA (model.cap_mc). The director walks the events in order and gives each the EARLIEST tick at which its
loads can have completed, so the tick of every picture swap is not chosen: it is the answer to
    "when can the next picture's tiles have been delivered?"
and the angular speed that falls out (15 degrees over the ticks between swaps) is the limiter the owner asked for.

Two BG layers alternate (the next picture loads into the off-screen one; a swap is a TM write), so a picture's load
window is the one interval before it. A blade extension is an IN-PLACE patch of the shown layer: ATOMIC, because a
half-written blade on screen is a tear: it must fit in one tick's VBlank or it waits for a tick that can take it.

Pure Python. tests/test_dgn_tilestream_score.py checks the emitted binaries with an independent interpreter.
"""
from __future__ import annotations

import copy
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from dgn_tilestream import model as M  # noqa: E402
from dgn_fight import director as DF  # noqa: E402
from dgn_giant import director as GD  # noqa: E402  (the two players' OBJ layout and dodges' geometry helpers)

# DMA command kinds: which VRAM region a command's destination offset is relative to
K_CHR_A, K_CHR_B, K_MAP_A, K_MAP_B, K_OBJ = 0, 1, 2, 3, 4
POOL_CLAIMS = 7                       # boss tile/tilemap pool: seven 28,672 B ROM claims (a whole-bank window each)
POOL_BYTES = 28672
BLOB_HERO = POOL_CLAIMS               # the players' frame store is blob 7
ZERO_BYTES = 45 * 64                  # a zero block big enough to clear every tilemap row

Y_REST = -78
Y_PLATEAU = -60                       # shallow spin height (<= -56: the rim set covers it)
Y_MID = M.y_limit(20)                 # -24: the mid set's deepest
Y_CUT = M.y_limit(16)                 # +8: the cut's deepest lunge
SPIN_STEP = 2                         # in units of 15 degrees: 30, the readable limit (half the 72 degree point spacing)
EXT_GAP = 6                           # ticks between blade steps (a player needs ~12 to clear a corridor)
HOLD_TICKS = 6
REST_START = 12
REST_END = 10
TM_BG = {0: (1 << 0), 1: (1 << 1)}    # the boss layer shown (BG1 or BG2)
TM_FIXED = (1 << 2) | (1 << 4)        # BG3 (the floor) and OBJ (the players) are always on


# ---------------------------------------------------------------------------------------------------------------
# the ROM pool: every block of tile or tilemap data, packed so that no DMA run crosses a bank
# ---------------------------------------------------------------------------------------------------------------
class Pool:
    def __init__(self):
        self.blobs = [bytearray()]
        self.at = {}

    def add(self, name: str, data: bytes):
        if len(data) > POOL_BYTES:
            raise SystemExit(f"a block of {len(data)} B cannot fit one {POOL_BYTES} B claim: {name}")
        if len(self.blobs[-1]) + len(data) > POOL_BYTES:
            self.blobs.append(bytearray())
        self.at[name] = (len(self.blobs) - 1, len(self.blobs[-1]), len(data))
        self.blobs[-1] += data

    def finish(self):
        if len(self.blobs) > POOL_CLAIMS:
            raise SystemExit(f"the boss needs {len(self.blobs)} ROM claims of {POOL_BYTES} B, the budget is {POOL_CLAIMS}: "
                             "fewer pictures, a shallower depth or a coarser step")
        return [bytes(b).ljust(POOL_BYTES, b"\0") for b in self.blobs] + [bytes(POOL_BYTES)] * (POOL_CLAIMS - len(self.blobs))


def build_pool(lib, used=None):
    """Only the variants the sequence uses. A cut group stores each extension picture's VARYING tiles once; every blade
    patch is a slice of one of those blocks (the e0 patch is a slice of the base tiles)."""
    pool = Pool()
    pool.add("zero", bytes(ZERO_BYTES))
    for vid, v in lib.items():
        if used is not None and vid not in used:
            continue
        pool.add("tiles:" + vid, v.base_bytes())
        pool.add("map:" + vid, v.tilemap_bytes())
        if vid.startswith("c"):
            for pic in v.pics[1:]:
                pool.add(f"var:{vid}:{pic}", M.vary_block(v, pic))
    return pool


def patch_src(pool, v, b, lo):
    """(blob, offset) of the tiles of picture b starting at slot lo (1-based) inside the varying region."""
    if b == v.pics[0]:                                     # e0: the tail of the base tiles
        blob, off, _ = pool.at["tiles:" + v.vid]
        return blob, off + (lo - 1) * 32
    blob, off, _ = pool.at[f"var:{v.vid}:{b}"]
    return blob, off + (lo - v.static - 1) * 32


# ---------------------------------------------------------------------------------------------------------------
# the per-tick DMA capacity
# ---------------------------------------------------------------------------------------------------------------
class Timeline:
    """What each tick has left. `place` returns where a job's pieces went; pieces are whole tiles (32 B)."""

    def __init__(self, cap):
        self.cap = cap
        self.used = defaultdict(int)
        self.cmds = defaultdict(list)

    def free(self, t):
        return self.cap - self.used[t]

    def put(self, t, cmd):
        kind, dst, blob, src, n = cmd
        self.used[t] += M.cost_mc(n)
        self.cmds[t].append(cmd)

    def place_spread(self, runs, earliest):
        """Non-atomic: fill the free capacity from `earliest` on, run by run, in whole tiles. Returns the tick the
        last piece landed on."""
        t = earliest
        last = earliest
        for kind, dst, blob, src, n in runs:
            off = 0
            while off < n:
                room = int((self.free(t) - M.MC_PER_XFER) // M.MC_PER_BYTE)
                take = min(n - off, (room // 32) * 32)
                if take < 32 and n - off >= 32:
                    t += 1
                    continue
                take = min(take, n - off) if take >= 32 else n - off
                self.put(t, (kind, dst + (off // 32 * 16 if kind in (K_CHR_A, K_CHR_B) else off // 2), blob, src + off, take))
                last = t
                off += take
        return last

    def place_atomic(self, runs, earliest):
        """All of a job on ONE tick (a patch of a shown layer must not tear): the first tick that has room."""
        need = sum(M.cost_mc(n) for _, _, _, _, n in runs)
        assert need <= self.cap, f"an atomic patch of {need} mc can never fit a tick of {self.cap} mc"
        t = earliest
        while self.free(t) < need:
            t += 1
        for r in runs:
            self.put(t, r)
        return t


# ---------------------------------------------------------------------------------------------------------------
# the loads
# ---------------------------------------------------------------------------------------------------------------
def load_runs(v, layer, pool, dirty):
    """The runs that put variant `v` in `layer`: its tiles into slots 1.., then the tilemap rows. Rows an earlier, larger
    picture left behind (`dirty` = (first, last)) that this one does not cover are zeroed. Returns (runs, new dirty)."""
    runs = []
    pb, po, pn = pool.at["tiles:" + v.vid]
    runs.append((K_CHR_A + layer, 16, pb, po, pn))                      # slot 1 starts at word 16
    zb, zo, _ = pool.at["zero"]
    lo, hi = min(dirty[0], v.first_row), max(dirty[1], v.last_row)
    if v.first_row > lo:
        runs.append((K_MAP_A + layer, lo * 32, zb, zo, 64 * (v.first_row - lo)))
    mb, mo, mn = pool.at["map:" + v.vid]
    runs.append((K_MAP_A + layer, v.first_row * 32, mb, mo, mn))
    if hi > v.last_row:
        runs.append((K_MAP_A + layer, (v.last_row + 1) * 32, zb, zo, 64 * (hi - v.last_row)))
    return runs, (v.first_row, v.last_row)


# ---------------------------------------------------------------------------------------------------------------
# the sequence
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Ev:
    kind: str                 # 'swap' | 'ext' | 'hold'
    y: float                  # the eye's screen height at this event
    vid: str = ""             # swap: the variant shown
    pic: int = 0              # the picture on screen after the event (a spin index, or an extension frame)
    min_gap: int = 1          # ticks after the previous event
    frm: int = -1             # ext: the picture the blade goes from


def _smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def spin_leg(k_from, k_to, y_from, y_to, turns, final_shallow=False, y_hi=Y_PLATEAU):
    """Swap events for the pictures of one spin, rotating clockwise from spin index k_from (exclusive) to k_to
    (inclusive) with `turns` extra whole turns. Shallow pictures (15 degrees) while the eye is high, mid pictures
    (30 degrees, even indices only) when it has come forward."""
    total = (k_to - k_from) % 24 + 24 * turns
    assert total > 0
    evs, a = [], k_from
    while a < k_from + total:
        p = (a - k_from) / total
        if p < 0.3:
            y_next = y_from + (y_hi - y_from) * _smooth(p / 0.3)
        elif p < 0.7:
            y_next = y_hi
        else:
            y_next = y_hi + (y_to - y_hi) * _smooth((p - 0.7) / 0.3)
        # the picture must also be valid at the NEXT waypoint's height, so test the shallower limit on y_next
        shallow = y_next <= M.y_limit(24)
        nxt = a + SPIN_STEP
        if nxt % 2:
            nxt += 1                                     # both spin sets exist only at even indices (30 degree steps)
        if nxt >= k_from + total:
            nxt = k_from + total
            shallow = final_shallow
            y_next = y_to
        k = nxt % 24
        assert k % 2 == 0, f"spin picture at odd index {k}"
        evs.append(Ev("swap", y_next, ("s%d" if shallow else "m%d") % k, k))
        a = nxt
    return evs


def cut_events(k):
    """Swap to the cut variant, extend the blade in three steps while the eye lunges, hold, withdraw."""
    e1, e2, e3 = M.EXT[k]
    y = [Y_MID + (Y_CUT - Y_MID) * f for f in (0, 1 / 3, 2 / 3, 1)]
    return [Ev("swap", Y_MID, f"c{k}", k),
            Ev("ext", y[1], pic=e1, min_gap=EXT_GAP, frm=k), Ev("ext", y[2], pic=e2, min_gap=EXT_GAP, frm=e1),
            Ev("ext", y[3], pic=e3, min_gap=EXT_GAP, frm=e2), Ev("hold", y[3], pic=e3, min_gap=HOLD_TICKS),
            Ev("ext", y[2], pic=e2, min_gap=EXT_GAP, frm=e3), Ev("ext", y[1], pic=e1, min_gap=EXT_GAP, frm=e2),
            Ev("ext", y[0], pic=k, min_gap=EXT_GAP, frm=e1)]


def sequence(turns=(2, 1, 1, 1)):
    t1, t2, t3, t4 = turns
    evs = []
    evs += spin_leg(12, 20, Y_REST, Y_MID, t1)
    evs[0].min_gap = REST_START             # rest (blade up, k=12) -> m20, the picture before the 45 degree cut
    evs += cut_events(21)
    evs += spin_leg(21, 0, Y_MID, Y_MID, t2)                # -> m0 (the picture before the 90 degree cut at the same angle)
    evs += cut_events(0)
    evs += spin_leg(0, 2, Y_MID, Y_MID, t3)                 # -> m2, the picture before the 135 degree cut (k=3)
    evs += cut_events(3)
    evs += spin_leg(3, 12, Y_MID, Y_REST, t4, final_shallow=True)
    return evs


# ---------------------------------------------------------------------------------------------------------------
# the scheduler
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Placed:
    ev: Ev
    tick: int
    layer: int


def schedule(lib, pool, evs, cap, base=None):
    """Walk the events. Returns dict(events=[Placed], cmds={tick: [cmd]}, used={tick: mc}, T=ticks, init=[cmd])."""
    tl = Timeline(cap)
    if base:                                  # a load already committed (the players'), which the boss works round
        for t, mc in base.items():
            tl.used[t] += mc
    placed = []
    d12 = (lib["s12"].first_row, lib["s12"].last_row)
    layers = [{"vid": "s12", "dirty": d12}, {"vid": "s12", "dirty": d12}]
    shown = 0
    t_prev = 0                                # the previous event's tick
    t_last_swap = 0
    last_shown_pic = 12
    for ev in evs:
        if ev.kind == "swap":
            target = 1 - shown
            v = lib[ev.vid]
            runs, dirty = load_runs(v, target, pool, layers[target]["dirty"])
            done = tl.place_spread(runs, t_last_swap)
            t = max(done, t_prev + max(ev.min_gap, 1))
            layers[target] = {"vid": ev.vid, "dirty": dirty}
            placed.append(Placed(ev, t, target))
            shown, t_last_swap, t_prev = target, t, t
        elif ev.kind == "ext":
            v = lib[layers[shown]["vid"]]
            lo, hi, payload = M.ext_runs(v, ev.frm, ev.pic)
            blob, off = patch_src(pool, v, ev.pic, lo)
            runs = [(K_CHR_A + shown, lo * 16, blob, off, len(payload))]
            t = tl.place_atomic(runs, t_prev + max(ev.min_gap, 1))
            placed.append(Placed(ev, t, shown))
            t_prev = t
        else:                                  # hold
            t = t_prev + ev.min_gap
            placed.append(Placed(ev, t, shown))
            t_prev = t
    # the loop closes on two layers that BOTH hold the rest picture: mirror it into the one not shown
    target = 1 - shown
    runs, dirty = load_runs(lib["s12"], target, pool, layers[target]["dirty"])
    done = tl.place_spread(runs, t_last_swap)
    T = max(t_prev + REST_END, done + 3)
    # the entry state, loaded in forced blank: both layers = s12 (and slot 0, the blank tile)
    init = []
    for layer in (0, 1):
        zb, zo, _ = pool.at["zero"]
        init.append((K_CHR_A + layer, 0, zb, zo, 32))
        r, _ = load_runs(lib["s12"], layer, pool, d12)
        init += r
    return {"events": placed, "cmds": dict(tl.cmds), "used": dict(tl.used), "T": T, "init": init,
            "final_layer": shown, "mirror_done": done, "timeline": tl}


def boss_waypoints(sched):
    """[(tick, y)] the eye's height at every event, from the rest height at tick 0 to the rest height at the end."""
    pts = [(0, float(Y_REST))]
    for p in sched["events"]:
        pts.append((p.tick, p.ev.y))
    pts.append((sched["T"], float(Y_REST)))
    return pts


def eye_y(pts, t):
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return y0 + (y1 - y0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1.0)
    return pts[-1][1]


def per_tick(sched, lib):
    """What is on screen on each tick: (layer, variant id, picture id, eye y)."""
    pts = boss_waypoints(sched)
    T = sched["T"]
    evs = sorted(sched["events"], key=lambda p: p.tick)
    out, shown, vid, pic = [], 0, "s12", 12
    i = 0
    for t in range(T):
        while i < len(evs) and evs[i].tick <= t:
            p = evs[i]
            if p.ev.kind == "swap":
                shown, vid, pic = p.layer, p.ev.vid, p.ev.pic
            else:
                pic = p.ev.pic
            i += 1
        y = eye_y(pts, t)
        out.append({"layer": shown, "vid": vid, "pic": pic, "y": y, "vofs": M.EYE[1] - round(y)})
    return out


# ---------------------------------------------------------------------------------------------------------------
# the players: stand in a blade's corridor, dodge as it lengthens, come home
# ---------------------------------------------------------------------------------------------------------------
HEADING = {21: 45, 0: 90, 3: 135}
HOME = {"p1": (60, 178), "p2": (196, 178)}
DODGE_PX = 28
WALK = 1.45                           # px/tick for a walk; a dodge is a sprint
# (player, distance from the eye along the blade, sideways offset): outside the e2 reach (115), inside e3 (165)
STATIONS = {21: [("p2", 124, 0)], 0: [("p1", 152, 10), ("p2", 124, -12)], 3: [("p1", 124, 0)]}


def cuts(sched):
    """{k: {'swap': t, 'e1': t, 'e2': t, 'e3': t, 'hold': t, 'back2': t, 'back1': t, 'back0': t}} from the placed events."""
    out, cur = {}, None
    names = ["e1", "e2", "e3", "hold", "back2", "back1", "back0"]
    for p in sched["events"]:
        if p.ev.kind == "swap" and p.ev.vid.startswith("c"):
            cur = int(p.ev.vid[1:])
            out[cur] = {"swap": p.tick, "_i": 0}
        elif cur is not None and p.ev.kind in ("ext", "hold"):
            out[cur][names[out[cur]["_i"]]] = p.tick
            out[cur]["_i"] += 1
            if out[cur]["_i"] == len(names):
                cur = None
        elif p.ev.kind == "swap":
            cur = None
    for v in out.values():
        v.pop("_i", None)
    return out


def station_xy(k, d, off):
    a = math.radians(HEADING[k])
    ux, uy = math.cos(a), math.sin(a)
    return (128 + d * ux - off * uy, Y_CUT + d * uy + off * ux)


def dodge_xy(k, d, off, who):
    """Away from the corridor on the side the player is already standing on (so it never crosses the blade's line);
    a player ON the line goes down and away from the boss."""
    a_ = math.radians(HEADING[k])
    ux, uy = math.cos(a_), math.sin(a_)
    sx, sy = station_xy(k, d, off)
    n = (-uy, ux)
    ok = lambda c: 20 <= c[0] <= 236 and 40 <= c[1] <= 212
    sides = [1, -1] if off > 0 else [-1, 1] if off < 0 else None
    cand = [(sx + s * DODGE_PX * n[0], sy + s * DODGE_PX * n[1]) for s in (sides or [1, -1])]
    if sides is None:
        cand.sort(key=lambda c: -c[1])
    cand = [c for c in cand if ok(c)] or cand
    return tuple(round(v) for v in cand[0])


def player_waypoints(who, cut_t, T):
    w = [(0, *HOME[who])]
    for k in (21, 0, 3):
        for pw, d, off in STATIONS[k]:
            if pw != who:
                continue
            c = cut_t[k]
            st = tuple(round(v) for v in station_xy(k, d, off))
            w.append((c["swap"], *st))
            w.append((c["e3"] - 2, *dodge_xy(k, d, off, who)))
    w.append((T, *HOME[who]))
    return w


def _face(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) > abs(dy) * 0.8:
        return "right" if dx > 0 else "left"
    return "down"


def player_segments(wps, dodge_ticks):
    """Walk as late as a walk allows (idle first); a leg shorter than `dodge_ticks`+1 is a sprint."""
    segs, pos, t = [], wps[0][1:], 0
    for t1, x1, y1 in wps[1:]:
        dist = math.hypot(x1 - pos[0], y1 - pos[1])
        ticks = t1 - t
        if ticks <= 0:
            raise AssertionError(f"waypoints out of order at {t1}")
        if dist < 0.5:
            segs.append(DF.Seg("idle", ticks, None, "down"))
        else:
            sprint = dist / ticks > WALK
            walk_ticks = ticks if sprint else min(ticks, max(1, math.ceil(dist / WALK)))
            if walk_ticks < ticks:
                segs.append(DF.Seg("idle", ticks - walk_ticks, None, _face(pos, (x1, y1))))
            segs.append(DF.Seg("walk", walk_ticks, (x1, y1), _face(pos, (x1, y1)), 0.55 if dist / walk_ticks > 1.8 else 1.0))
        pos, t = (x1, y1), t1
    return segs


def player_states(sched):
    cut_t = cuts(sched)
    T = sched["T"]
    out = {}
    for who in ("p1", "p2"):
        wps = player_waypoints(who, cut_t, T)
        out[who] = DF.render_track(who, player_segments(wps, 12), HOME[who], "down")
        assert len(out[who]) == T
    return out


def blade_reach(cut_t, t):
    """(k, reach px) of the blade at tick t if a cut is in progress, else None."""
    for k, c in cut_t.items():
        if c["swap"] <= t < c["back0"]:
            lvl = 0
            for name, l in (("e1", 1), ("e2", 2), ("e3", 3), ("back2", 2), ("back1", 1)):
                if c[name] <= t:
                    lvl = l
            return k, M.BLADE_PX[lvl]
    return None


# ---------------------------------------------------------------------------------------------------------------
# the whole scene
# ---------------------------------------------------------------------------------------------------------------
# THE LAST SCANLINE THE NMI HOOK MAY END ON. VBlank is V = 225..261 and an overrun silently drops VRAM writes, so the
# limit is the cliff less a margin for the cost model's error (+-1 line against the console, tests/test_dgn_colossus.py).
# It cannot be lower than 258 here: the largest thing that must land in ONE tick is the blade's atomic in-place patch
# (the displayed layer cannot show half a blade), 33,506 mc with its players' reserve, which no V limit below 258 holds.
V_LIMIT = 258


def compile_scene(turns=(2, 1, 1, 1), v_limit=V_LIMIT, reserve_mc=3600, lib=None, pool=None):
    lib = lib or M.library()
    evs = sequence(turns)
    used = {e.vid for e in evs if e.kind == "swap"} | {"s12"}
    pool = pool or build_pool(lib, used)
    cap = M.cap_mc(v_limit)
    for _ in range(6):
        base = defaultdict(int)
        sched = schedule(lib, pool, evs, cap - reserve_mc)
        T = sched["T"]
        players = player_states(sched)
        plan = DF.compile_stream(players, mode="choreo", layout=GD.LAYOUT)
        pcost = [M.cost_mc(sum(c[4] for c in plan["cmds"].get(t, [])), len(plan["cmds"].get(t, []))) if plan["cmds"].get(t) else 0
                 for t in range(T)]
        if max(pcost) <= reserve_mc:
            break
        reserve_mc = max(pcost) + 200
    else:
        raise AssertionError("the players' reserve did not settle")
    # the unified per-tick command list: the boss's, then the players' (blob 7)
    cmds = defaultdict(list)
    for t, cs in sched["cmds"].items():
        cmds[t] += cs
    for t, cs in plan["cmds"].items():
        for actor, dst, bid, off, nbytes, *_ in cs:
            cmds[t].append((K_OBJ, dst, BLOB_HERO, off, nbytes))
    init = list(sched["init"])
    for actor, dst, bid, off, nbytes, *_ in plan["init_cmds"]:
        init.append((K_OBJ, dst, BLOB_HERO, off, nbytes))
    ticks = per_tick(sched, lib)
    return {"lib": lib, "pool": pool, "events": sched["events"], "sched": sched, "T": T, "ticks": ticks,
            "players": players, "player_plan": plan, "cmds": dict(cmds), "init": init, "reserve_mc": reserve_mc,
            "cap": cap, "cuts": cuts(sched)}
