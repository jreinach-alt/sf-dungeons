"""dgn_giant — the giant Mode 7 boss's SCORE, checked without an emulator (docs/dungeons/20).

runtime: ~25 s, almost all of it the numpy reference renderer drawing a few hundred frames.

Two kinds of claim:

  * the CHOREOGRAPHY is what was asked for: a boss the whole width of the top of the screen with only part of it ever
    in view; it slides forward and spins as fast as it can be animated; it slices three times at 45, 90 and 135
    degrees; the two players dodge each slice; it retracts. These read the director's per-tick states and draw them
    through the reference Mode 7 renderer (the PPU's own arithmetic, including the 6 low bits it drops).

  * the SCHEDULE and the ART are safe: the players' prefetch is played by an independent interpreter, and the plane
    fits Mode 7's 256-tile budget.
"""
import json
import math
import sys
from pathlib import Path

SUPERFORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPERFORGE / "tools"))
sys.path.insert(0, str(SUPERFORGE / "vendor"))
# FIRST, before numpy: see tests/test_dgn_hero.py (the core is dlopen'd at import)
from machine import Machine  # noqa: E402,F401  (import order only)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from dgn_giant import director as G  # noqa: E402
from dgn_fight import director as DF  # noqa: E402
import gen_dgn_giant_assets as GEN  # noqa: E402

CROWN = SUPERFORGE / "art" / "dungeons" / "creatures" / "out" / "crownling_boss" / "idle_down.png"


@pytest.fixture(scope="module")
def img():
    return np.asarray(Image.open(CROWN))


@pytest.fixture(scope="module")
def plane(img):
    return G.plane_from_image(img)


@pytest.fixture(scope="module")
def boss():
    return G.boss_states()


@pytest.fixture(scope="module")
def players():
    return G.all_states()


@pytest.fixture(scope="module")
def frames(plane, boss):
    """The screen indices of every other tick, through the PPU's arithmetic."""
    return {t: G.render_m7(plane, G.matrix_words(*boss[t])) for t in range(0, G.LOOP, 2)}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("giant")
    assert GEN.main([str(d)]) == 0
    return {n: (d / n).read_bytes() for n in ("dgng_m7.bin", "dgng_score.bin", "dgng_cmds.bin", "dgng_ptr.bin",
                                               "dgng_pal.bin", "dgng_report.json")}


# =============================== the boss ===================================================================
def test_the_boss_fills_the_top_of_the_screen_but_only_part_is_ever_in_view(img, frames):
    """'So big he takes up the entire length of the top of the screen, and only a portion of the model is visible.'"""
    full = int((img > 0).sum() * G.SCALE ** 2)
    vis = {t: int((f > 0).sum()) / full for t, f in frames.items()}
    assert max(vis.values()) < 0.9, "the whole crown is on screen at once"
    assert min(vis.values()) < 0.12, "the crown is never mostly hidden"
    # the full width: the rim spans the screen's top edge at the widest moment
    widest = max(int(np.ptp(np.nonzero((f[:60] > 0).any(axis=0))[0])) + 1 for f in frames.values() if (f[:60] > 0).any())
    assert widest >= 240, f"the crown spans only {widest} of 256 px"


def test_the_eye_is_hidden_at_rest_and_only_comes_on_screen_to_cut(boss):
    assert boss[0][2] < -40 and boss[G.LOOP - 1][2] < -40
    on = [t for t in range(G.LOOP) if 0 <= boss[t][2] <= 224]
    assert on, "the eye never comes on screen"
    for a in G.SLICE_ANGLES:
        t0, t1 = G.cut_window(a)
        assert any(t0 <= t < t1 for t in on), f"the eye is off screen for the whole {a} degree cut"


def test_the_boss_slides_forward_on_every_cut_and_retracts(boss):
    for a in G.SLICE_ANGLES:
        t0, t1 = G.cut_window(a)
        y0 = boss[t0][2]
        y1 = max(boss[t][2] for t in range(t0, t1))
        assert y1 - y0 >= 80, f"the {a} degree cut only slides forward {y1 - y0} px"
        assert boss[t1 - 1][2] <= y0 + 4, f"the {a} degree cut does not withdraw"
    assert boss[0][1:] == boss[G.LOOP - 1][1:] or math.hypot(boss[0][1] - boss[-1][1], boss[0][2] - boss[-1][2]) <= 3


def test_the_boss_spins_as_fast_as_it_can_be_animated(boss):
    """Peak 45 deg/tick: eight ticks to a turn. Faster is not animation, it is aliasing (the crown's five points
    repeat every 72 degrees, so past that it appears to stand still or turn backwards)."""
    speed = [abs(boss[t][0] - boss[t - 1][0]) for t in range(1, G.LOOP)]
    assert max(speed) >= 40, max(speed)
    assert max(speed) <= 72, "past 72 deg/tick the five-fold crown aliases"
    for t0, t1 in ((20, 60), (94, 134), (168, 208)):                 # each spin leg turns the crown at least twice
        assert abs(boss[t1][0] - boss[t0][0]) >= 720, (t0, t1)


def test_it_slices_three_times_at_45_90_and_135_degrees(boss, plane):
    """The blade, drawn through the PPU's arithmetic, lies along the commanded heading on each cut."""
    for a in G.SLICE_ANGLES:
        t0, t1 = G.cut_window(a)
        t = t0 + G.LUNGE_T + 1
        f = G.render_m7(plane, G.matrix_words(*boss[t]))
        ys, xs = np.nonzero(f == 12)                                # the blade's own palette index
        assert len(xs) > 1500, f"the {a} degree blade is not on screen ({len(xs)} px)"
        ex, ey = boss[t][1], boss[t][2]
        pts = np.stack([xs - ex, ys - ey], 1).astype(float)
        vals, vecs = np.linalg.eigh(np.cov(pts.T))
        ang = math.degrees(math.atan2(vecs[1, 1], vecs[0, 1])) % 180
        assert abs(ang - a % 180) < 1.0, f"cut {a}: blade at {ang:.1f} degrees"
        # and the three headings are exactly the commanded ones, locked for the whole hold
        assert abs((boss[t][0] - boss[t0][0])) < 1e-6 and abs(((boss[t][0] + 90) % 360) - a) < 1e-6


def test_the_matrix_words_are_the_documented_8_8_rotation():
    A, B, C, D, x0, y0, hofs, vofs = G.matrix_words(0.0, 128, 60)
    assert (A, B, C, D) == (114, 0, 0, 114), "256 / 2.25 = 113.8 -> 114 at zero rotation"
    assert (x0, y0, hofs, vofs) == (512, 512, 512 - 128, 512 - 60)
    A, B, C, D = G.matrix_words(90.0, 0, 0)[:4]
    assert (A, B, C, D) == (0, 114, (-114) & 0xFFFF, 0), "a quarter turn swaps the axes and negates one"


def test_the_reference_renderer_turns_the_plane_clockwise_about_the_pivot():
    """An independent check of the convention: a marker below the pivot swings to the screen's LEFT at +90 degrees."""
    plane = np.zeros((1024, 1024), np.uint8)
    plane[512 + 40, 512] = 7                                       # 40 plane px below the pivot
    for phi, expect in ((0, (128, 100 + int(40 * G.SCALE))), (90, (128 - int(40 * G.SCALE), 100)),
                        (180, (128, 100 - int(40 * G.SCALE))), (270, (128 + int(40 * G.SCALE), 100))):
        f = G.render_m7(plane, G.matrix_words(phi, 128, 100))
        ys, xs = np.nonzero(f == 7)
        assert len(xs), phi
        assert abs(xs.mean() - expect[0]) <= 3 and abs(ys.mean() - expect[1]) <= 3, (phi, xs.mean(), ys.mean(), expect)


def test_the_ppu_drops_six_bits_of_every_product_and_the_reference_knows(plane):
    """Why the reference is not the naive formula: the hardware masks the low 6 bits of each offset x matrix product
    (a quarter pixel of noise). The two renderings differ, so a test against the naive one would be red on a correct ROM."""
    words = G.matrix_words(22.0, 120, 40)
    exact = G.render_m7(plane, words)
    A, B, C, Dm = (w - 0x10000 if w & 0x8000 else w for w in words[:4])
    ho, vo = words[6] - words[4], words[7] - words[5]
    sy, sx = np.mgrid[0:224, 0:256]
    naive = plane[((C * (sx + ho) + Dm * (sy + 1 + vo)) >> 8) + 512 & 1023, ((A * (sx + ho) + B * (sy + 1 + vo)) >> 8) + 512 & 1023]
    assert int((naive != exact).sum()) > 50


def test_the_loop_closes(boss):
    a, b = boss[0], G.boss_state(G.LOOP)
    assert (a[1], a[2]) == (b[1], b[2]) and abs((a[0] - b[0] + 180) % 360 - 180) < 1e-6


# =============================== the players =================================================================
def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def test_the_players_are_never_in_a_blade_that_is_cutting(players):
    n = 0
    for a in G.SLICE_ANGLES:
        t0, t1 = G.cut_window(a)
        for t in range(t0, t1):
            for who in ("p1", "p2"):
                s = players[who][t]
                assert not G.in_blade(s.x, s.y, t, margin=8), f"{who} is sliced at tick {t} ({a} degrees)"
                along, perp = G.dist_to_blade(s.x, s.y, t)
                if -10 <= along <= G.BLADE_LEN:
                    assert perp >= 28, f"{who} at {perp:.0f} px from the {a} degree blade, tick {t}"
                    n += 1
    assert n > 40, "the blade never reached a player: nothing was dodged"


def test_every_slice_has_a_player_who_dodges_it(players):
    """In the corridor when the cut begins (within 14 px of the blade's line) and clear by the time it lands."""
    for a in G.SLICE_ANGLES:
        t0, t1 = G.cut_window(a)
        dodgers = []
        for who in ("p1", "p2"):
            s0 = players[who][t0 - 14]
            along, perp = G.dist_to_blade(s0.x, s0.y, t0 + G.LUNGE_T)
            if perp < 14 and along > 100:
                s1 = players[who][t0 + 2]
                moved = _dist(s0, s1)
                _, perp1 = G.dist_to_blade(s1.x, s1.y, t0 + G.LUNGE_T)
                assert perp1 >= 28 and moved >= 20, (a, who, perp1, moved)
                dodgers.append(who)
        assert dodgers, f"nobody is in the way of the {a} degree slice"
    # the straight-down slice catches both, and they go opposite ways
    t0, _ = G.cut_window(90)
    d1 = players["p1"][t0 + 2].x - players["p1"][t0 - 14].x
    d2 = players["p2"][t0 + 2].x - players["p2"][t0 - 14].x
    assert d1 < -10 and d2 > 10, (d1, d2)


def test_the_players_move_at_a_walk_or_a_sprint_and_come_home(players):
    for who in ("p1", "p2"):
        sp = [_dist(players[who][t], players[who][t - 1]) for t in range(1, G.LOOP)]
        assert max(sp) <= 3.0, (who, max(sp))
        h = G.HOME[who]
        assert math.hypot(players[who][-1].x - h[0], players[who][-1].y - h[1]) <= 2, "the loop does not close"
        assert all(8 <= s.x <= 248 and 40 <= s.y <= 215 for s in players[who])


# =============================== the schedule and the art ==================================================
def _held(built):
    """Play the emitted stream on an abstract VRAM: {(actor, buffer): frame} after each tick."""
    cmds, ptr = built["dgng_cmds.bin"], built["dgng_ptr.bin"]
    off = lambda i: int.from_bytes(ptr[2 * i:2 * i + 2], "little")
    where = {}
    for actor, sl in G.SLOTS.items():
        for buf in (0, 1):
            for row in range(sl["rows"]):
                where[G.vmadd_of(actor, buf, row)] = (actor, buf, row)
    cell, held = {}, []
    for i in range(off(G.LOOP), off(G.LOOP + 1), 6):               # the entry state
        a, b, r = where[int.from_bytes(cmds[i:i + 2], "little")]
        o = int.from_bytes(cmds[i + 2:i + 4], "little")
        assert (o % 512) // 128 == r
        cell[(a, b, r)] = o // 512
    for t in range(G.LOOP):
        for i in range(off(t), off(t + 1), 6):
            a, b, r = where[int.from_bytes(cmds[i:i + 2], "little")]
            o = int.from_bytes(cmds[i + 2:i + 4], "little")
            assert (o % 512) // 128 == r
            cell[(a, b, r)] = o // 512
        held.append({(a, b): ({cell.get((a, b, r)) for r in range(4)}.pop() if len({cell.get((a, b, r)) for r in range(4)}) == 1 else None)
                     for a in G.SLOTS for b in (0, 1)})
    return held


def test_every_displayed_player_frame_is_in_its_buffer_on_every_tick(built, players):
    score = built["dgng_score.bin"]
    held = _held(built)
    names = {G.name_of(a, b): (a, b) for a in G.SLOTS for b in (0, 1)}
    for t in range(G.LOOP):
        rec = score[t * G.RECORD_BYTES:(t + 1) * G.RECORD_BYTES]
        for slot, who in ((0, "p1"), (2, "p2")):
            a, buf = names[rec[slot * 4 + 2]]
            assert a == who
            assert held[t][(who, buf)] == players[who][t].frame, f"tick {t}: {who} shows an unloaded buffer"


def test_the_plane_fits_mode_7s_256_tiles_and_the_blob_is_exactly_one_bank(built):
    rep = json.loads(built["dgng_report.json"])
    assert rep["unique_tiles"] <= 256, rep["unique_tiles"]
    assert len(built["dgng_m7.bin"]) == 32768
    blob = built["dgng_m7.bin"]
    # the interleave: even bytes are the 128x128 tilemap, odd bytes the CHR; tile 0 is blank, everything else is
    # inside the image's own cell range
    mp, chr_ = blob[0::2], blob[1::2]
    ox, oy = G.IMG_ORIGIN
    for r in range(128):
        for c in range(128):
            inside = oy // 8 <= r < oy // 8 + G.IMG_H // 8 and ox // 8 <= c < ox // 8 + G.IMG_W // 8
            if not inside:
                assert mp[r * 128 + c] == 0, (r, c)
    assert not any(chr_[:64]), "tile 0 must be blank: the rest of the plane is tile 0"


def test_the_plane_in_the_blob_decodes_back_to_the_crown(built, img):
    """Independent of the converter: rebuild the plane from the blob's map and tiles and compare with the strip."""
    blob = built["dgng_m7.bin"]
    mp, chr_ = np.frombuffer(blob[0::2], np.uint8), np.frombuffer(blob[1::2], np.uint8)
    plane = np.zeros((1024, 1024), np.uint8)
    for r in range(128):
        for c in range(128):
            t = int(mp[r * 128 + c])           # NOT a numpy uint8: t * 64 would wrap at 256
            plane[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = chr_[t * 64:t * 64 + 64].reshape(8, 8)
    assert (plane == G.plane_from_image(img)).all()


def test_the_stream_is_tiny_and_the_loop_closes_on_it(built):
    rep = json.loads(built["dgng_report.json"])
    assert rep["stream"]["peak_bytes"] <= 256 and rep["stream"]["peak_transfers"] <= 2
    assert len(built["dgng_score.bin"]) == GEN.SCORE_CLAIM
    assert G.LOOP * G.RECORD_BYTES <= GEN.SCORE_CLAIM
