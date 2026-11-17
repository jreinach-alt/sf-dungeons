"""paint.py — the PAINTERLY stage: Blender data frames -> hand-painted-looking pixels.

    python3 art/dungeons/style/paint.py art/dungeons/style/styles/a_storybook.toml

The spike pipeline's pixelate stage is an area average: honest, but the shading
falls out as noise and the outline is one flat colour. That is the "downsampled
3D" look the art direction rules out. This stage keeps the same DATA frames
(R sun, G material id, B ambient occlusion; no colour matching anywhere) and
replaces the pixel decisions with painter's rules:

  1 MATERIAL by weighted vote, as before (small features get heavier votes);
  2 SHADE smoothed within a material (normalised convolution), then quantised
    on the style's own ramp thresholds, so bands are coherent shapes;
  3 CLUSTERS: orphan pixels (a step that agrees with none of its neighbours)
    fold into the surrounding band, repeated; 1-px noise cannot survive;
  4 CONTACT: where one material passes over another (cloak over tunic) the
    lower material gets its darkest step along the seam: a painted shadow line;
  5 RIM: the lit silhouette edge (sun from the upper left) steps one up the ramp;
  6 SELOUT: the outline is the DARKEST step of the material it encloses (never
    black), and softens one step on the lit side;
  7 SHADOW: a small ground shadow with a dithered edge, not a solid disc;
  8 STAMPS: hand-authored pixel clusters (a hood's two glints, the lantern's
    bloom, the blade's edge light) placed at the projected 3D locators, so
    they follow the animation but are drawn, not rendered.

Nothing here is random. The same style file and frames give the same pixels.
Output: art/dungeons/style/out/<style>/<action>_<dir>.png (indexed strips,
index 0 transparent) and palettes.json (P1 / P2, 15 colours + transparent,
every colour exactly representable in BGR555).
"""
from __future__ import annotations

import json
import sys
import tomllib
import warnings
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "actors"))
import pixelate_actor as P  # noqa: E402  (the role table loader and the fit refusal)

SUN, SKY = P.SUN, P.SKY
OUT = HERE / "out"
WORK = REPO / "build" / "dgn_art_work"


# ---------------------------------------------------------------------------
# palettes: hex in the style file, exactly representable on the console
# ---------------------------------------------------------------------------
def snes(hexcol: str) -> tuple:
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) >> 3 for i in (0, 2, 4))
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def palettes(style: dict) -> dict:
    out = {}
    for k in ("p1", "p2"):
        cols = style["palette"][k]
        assert len(cols) == 15, f"{k}: 15 colours (indices 1-15), got {len(cols)}"
        out[k] = [(0, 0, 0)] + [snes(c) for c in cols]
    # the swap contract (docs/dungeons/11 §4): P1 and P2 differ in 1-7 only
    diff = [i for i in range(16) if out["p1"][i] != out["p2"][i]]
    assert diff == list(range(1, 8)), f"P1/P2 must differ in exactly entries 1-7, got {diff}"
    return out


# ---------------------------------------------------------------------------
# array helpers
# ---------------------------------------------------------------------------
def blocks(a: np.ndarray, ss: int) -> np.ndarray:
    h, w = a.shape[0] // ss, a.shape[1] // ss
    return a.reshape(h, ss, w, ss).transpose(0, 2, 1, 3).reshape(h, w, ss * ss)


def nb4(a: np.ndarray, fill=0) -> np.ndarray:
    p = np.pad(a, 1, mode="constant", constant_values=fill)
    return np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]], 0)   # up, down, left, right


def conv3(a: np.ndarray) -> np.ndarray:
    k = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], float)
    p = np.pad(a.astype(float), 1, mode="constant")
    out = np.zeros(a.shape, float)
    for dy in range(3):
        for dx in range(3):
            out += k[dy, dx] * p[dy:dy + a.shape[0], dx:dx + a.shape[1]]
    return out


# ---------------------------------------------------------------------------
# the painter
# ---------------------------------------------------------------------------
class Painter:
    def __init__(self, style: dict):
        self.style = style
        self.fam = P.load_family("hero")
        pt = style.get("paint", {})
        self.cover = pt.get("cover", 0.5)
        self.smooth = pt.get("smooth", 0.6)
        self.passes = pt.get("cluster_passes", 2)
        self.rim = pt.get("rim", 1)
        self.contact = pt.get("contact", True)
        self.lit_soft = pt.get("lit_soft", True)
        self.shadow_mode = pt.get("shadow", "dither")
        self.roles = {r["material"]: dict(r) for r in self.fam.roles}
        self.by_name = {r["name"]: r for r in self.fam.roles}
        for name, ov in style.get("ramp", {}).items():          # per-style thresholds / votes
            r = self.by_name[name]
            r.update({k: v for k, v in ov.items() if k in ("thresholds", "vote")})
        om = {"cloak": 1, "trim": 1, "skin": 10, "leather": 10, "glow": 14, "metal": 15, "detail": 15}
        om.update(pt.get("outline", {}))
        self.omap = {self.by_name[n]["material"]: v for n, v in om.items()}
        ol = {"cloak": 2, "trim": 2, "skin": 10, "leather": 10, "glow": 14, "metal": 15, "detail": 15}
        ol.update(pt.get("outline_lit", {}))
        self.omap_lit = {self.by_name[n]["material"]: v for n, v in ol.items()}
        # who passes OVER whom, for the contact shadow (higher = nearer the viewer)
        self.over = {self.by_name[n]["material"]: i for i, n in enumerate(
            pt.get("over", ["skin", "leather", "detail", "metal", "glow", "trim", "cloak"]))}

    # ---- steps 1-3 ----------------------------------------------------------
    def material_and_steps(self, raw: np.ndarray, ss: int):
        shade = blocks(SUN * raw[..., 0] / 255.0 + SKY * raw[..., 2] / 255.0, ss)
        ids = blocks(raw[..., 1], ss)
        mats = [r["material"] for r in self.fam.roles]
        counts = np.stack([(ids == m).sum(-1) for m in mats], -1)
        n = ss * ss
        cov = counts.sum(-1) / n
        win_i = (counts * np.array([self.by_name[r["name"]]["vote"] for r in self.fam.roles])).argmax(-1)
        win = np.array(mats)[win_i]
        model = cov >= self.cover
        win = self.clean_materials(np.where(model, win, 0), model)
        wmask = ids == win[..., None]
        lum = (shade * wmask).sum(-1) / np.maximum(wmask.sum(-1), 1)
        lum = np.where(wmask.sum(-1) > 0, lum, shade.mean(-1))     # a re-assigned pixel: the plain mean
        shadow = ~model & ((cov + (ids == P.MAT_SHADOW).sum(-1) / n) >= 0.5)
        step = np.zeros(win.shape, int)
        lum2 = lum.copy()
        for r in self.fam.roles:
            if r["kind"] != "ramp":
                continue
            m = (win == r["material"]) & model
            num, den = conv3(np.where(m, lum, 0.0)), conv3(m.astype(float))
            sm = np.where(m & (den > 0), num / np.maximum(den, 1e-9), lum)
            lum2 = np.where(m, (1 - self.smooth) * lum + self.smooth * sm, lum2)
            step[m] = np.digitize(lum2[m], self.by_name[r["name"]]["thresholds"])
        win = np.where(model, win, 0)
        step = self.clusters(win, step, model)
        return win, step, model, shadow

    def clean_materials(self, win, model):
        """A model pixel whose four neighbours share NONE of its material, but two or
        more share another, takes that material: stray pixels become the band around
        them. Lantern glow and steel are small by design and are left alone."""
        keep = {self.by_name["glow"]["material"], self.by_name["metal"]["material"]}
        for _ in range(2):
            nw = nb4(win, -1)
            out = win.copy()
            for m in {int(v) for v in np.unique(win[model])} - keep:
                same = (nw == m).sum(0)
                cand = model & (win == m) & (same == 0)
                if not cand.any():
                    continue
                # the most common neighbouring material
                best = np.zeros(win.shape, int)
                cnt = np.zeros(win.shape, int)
                for o2 in {int(v) for v in np.unique(win[model])} - {m}:
                    c = (nw == o2).sum(0)
                    better = c > cnt
                    best = np.where(better, o2, best)
                    cnt = np.where(better, c, cnt)
                sel = cand & (cnt >= 2)
                out[sel] = best[sel]
            win = out
        return win

    def clusters(self, win, step, model):
        """Fold orphan steps into the band around them (same material only)."""
        for _ in range(self.passes):
            ns = nb4(step, -9)
            nm = nb4(win, -1)
            out = step.copy()
            for r in self.fam.roles:
                if r["kind"] != "ramp":
                    continue
                m = (win == r["material"]) & model
                same = nm == r["material"]
                agree = ((ns == step) & same).sum(0)
                nsame = same.sum(0)
                orphan = m & (agree == 0) & (nsame >= 2)
                if orphan.any():
                    # the median step of the same-material neighbours
                    vals = np.where(same, ns, np.nan)
                    with np.errstate(all="ignore"), warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        med = np.nan_to_num(np.nanmedian(vals, axis=0), nan=0.0)
                    out[orphan] = np.rint(med[orphan]).astype(int)
            step = out
        # a 1-px line of one step between two pixels of the SAME other step is noise
        ns = nb4(step, -9)
        nm = nb4(win, -1)
        out = step.copy()
        for r in self.fam.roles:
            if r["kind"] != "ramp":
                continue
            m = (win == r["material"]) & model
            v = m & (nm[0] == r["material"]) & (nm[1] == r["material"]) & (ns[0] == ns[1]) & (ns[0] != step)
            h = m & (nm[2] == r["material"]) & (nm[3] == r["material"]) & (ns[2] == ns[3]) & (ns[2] != step)
            out[v] = ns[0][v]
            out[h & ~v] = ns[2][h & ~v]
        return out

    # ---- steps 4-6: index image ----------------------------------------------
    def compose(self, win, step, model, shadow):
        h, w = win.shape
        idx = np.zeros((h, w), np.uint8)
        for r in self.fam.roles:
            m = (win == r["material"]) & model
            if r["kind"] == "ramp":
                idx[m] = r["lo"] + np.clip(step[m], 0, r["hi"] - r["lo"])
            else:
                idx[m] = r["index"]
        if self.contact:
            nw = nb4(win, -1)
            hi_over = np.zeros((h, w), bool)
            for m_id, rank in self.over.items():
                lower = (win == m_id) & model
                lowr = np.zeros((h, w), bool)
                for other, orank in self.over.items():
                    if orank > rank:
                        lowr |= (nw == other).any(0)
                r = self.roles[m_id]
                if r["kind"] == "ramp":
                    sel = lower & lowr
                    idx[sel] = r["lo"]                         # the darkest step along the seam
        if self.rim:
            up, down, left, right = nb4(model, False)
            edge = ~up | ~left                                  # the lit (upper-left) silhouette
            for r in self.fam.roles:
                if r["kind"] != "ramp" or r["name"] in self.style.get("paint", {}).get("no_rim", ["skin"]):
                    continue
                m = (win == r["material"]) & model & edge & (idx > r["lo"])
                idx[m] = np.minimum(idx[m] + self.rim, r["hi"])
        # selout ring
        ring = ~model & nb4(model, False).any(0)
        order = [(0, False), (2, False), (3, True), (1, True)]    # take the up, left, right, down neighbour
        nbw = nb4(win, 0)
        nbi = nb4(idx, 0)
        chosen = np.zeros((h, w), np.uint8)
        done = np.zeros((h, w), bool)
        for k, litside in order:
            m = ring & ~done & (nbw[k] > 0)
            for mat in self.omap:
                mm = m & (nbw[k] == mat)
                if not mm.any():
                    continue
                r = self.roles[mat]
                o = self.omap[mat]
                if self.lit_soft and not litside:             # the ring pixel is up/left of the lit fill
                    bright = (nbi[k] - (r["lo"] if r["kind"] == "ramp" else 0)) >= 3
                    o = np.where(bright[mm], self.omap_lit[mat], self.omap[mat])
                chosen[mm] = o
            done |= m
        idx[ring & done] = chosen[ring & done]
        # shadow
        if self.shadow_mode:
            sh = shadow & ~ring
            if self.shadow_mode == "dither":
                nsh = nb4(sh | model, False)
                inner = nsh.all(0)
                yy, xx = np.mgrid[0:h, 0:w]
                chk = ((yy + xx) % 2) == 0
                idx[sh & (inner | chk)] = 15
            else:
                idx[sh] = 15
        return idx

    # ---- step 8: stamps ----------------------------------------------------------
    def stamp(self, idx, model, loc, direction, box_origin):
        """Hand-authored pixel clusters at the projected 3D locators."""
        st = self.style.get("stamp", {})
        h, w = idx.shape

        def put(pts, anchor):
            ax, ay = int(np.floor(anchor[0])), int(np.floor(anchor[1]))
            for dx, dy, ci in pts:
                x, y = ax + dx, ay + dy
                if 0 <= x < w and 0 <= y < h and (model[y, x] or idx[y, x] != 0):
                    idx[y, x] = ci
        if "head" in loc:
            key = "face_" + direction
            if key in st:
                put(st[key], loc["head"])
        if "lantern" in loc and "lantern" in st:
            put(st["lantern"], loc["lantern"])
        if "sword_tip" in loc and "sword_tip" in st:
            put(st["sword_tip"], loc["sword_tip"])
        if "sword_mid" in loc and "sword_mid" in st:
            put(st["sword_mid"], loc["sword_mid"])
        return idx

    def paint(self, raw, ss, margin, box, loc, direction, label):
        win, step, model, shadow = self.material_and_steps(raw, ss)
        idx = self.compose(win, step, model, shadow)
        idx = self.stamp(idx, model, loc, direction, (margin, margin))
        solid = model | shadow
        # the stamp coords are canvas coords; crop to the box, refusing spill (never crop)
        inner = P.fit(idx, solid, margin, box[0], box[1], label)
        return inner


# ---------------------------------------------------------------------------
def apply_overrides(sprite: np.ndarray, style: dict, key: str) -> np.ndarray:
    """THE HAND-CLEANUP LAYER. `[override.<action>_<dir>_<frame>]` lists [x, y, index]
    pixels, in BOX coordinates, applied last: what a pixel artist fixes by hand where
    the procedural stage does not get there (a boot's gap, a highlight edge). The table
    is data, committed beside the style, so a re-render keeps the cleanup and a diff
    shows exactly which pixels a person chose. Out-of-box pixels are an error."""
    ov = style.get("override", {}).get(key)
    if not ov:
        return sprite
    out = sprite.copy()
    h, w = out.shape
    for x, y, ci in ov["px"]:
        if not (0 <= x < w and 0 <= y < h and 0 <= ci <= 15):
            raise ValueError(f"override {key}: pixel ({x},{y})={ci} is outside the {w}x{h} box / 4bpp")
        out[y, x] = ci
    return out


def load_style(path: Path) -> dict:
    return tomllib.loads(Path(path).read_text())


def run(style_path: Path) -> int:
    style = load_style(style_path)
    name = style["name"]
    pal = palettes(style)
    src = WORK / f"style_{name}"
    log = json.loads((src / "locs.json").read_text())
    painter = Painter(style)
    cam = style["camera"]
    ss, m = cam["supersample"], cam["margin_px"]
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)
    strips: dict = {}
    for f in log["frames"]:
        raw = np.asarray(Image.open(src / f["file"]).convert("RGB"))
        bw, bh = f["box"]
        # the stamp locators are in BOX coords; the painter works on the canvas: add the margin
        loc = {k: [v[0] + m, v[1] + m] for k, v in f["loc"].items()}
        sprite = painter.paint(raw, ss, m, (bw, bh), loc, f["dir"], f"{name} {f['action']} {f['dir']} {f['i']}")
        sprite = apply_overrides(sprite, style, f"{f['action']}_{f['dir']}_{f['i']}")
        strips.setdefault((f["action"], f["dir"]), []).append(sprite)
    for (an, d), fr in strips.items():
        a = np.concatenate(fr, axis=1)
        im = Image.fromarray(a.astype(np.uint8), "P")
        im.putpalette([c for rgb in pal["p1"] for c in rgb])
        im.info["transparency"] = 0
        im.save(out / f"{an}_{d}.png", transparency=0)
    (out / "palettes.json").write_text(json.dumps(
        {"p1": [list(c) for c in pal["p1"]], "p2": [list(c) for c in pal["p2"]]}, indent=1) + "\n")
    print(f"paint[{name}]: {sum(len(v) for v in strips.values())} frames -> {out.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1])))
