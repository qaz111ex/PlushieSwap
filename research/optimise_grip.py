"""Find the model offset that puts both hands on the plush's surface.

The game holds an item by snapping the hand rigs to fixed item-local anchors; the mod
shifts the model to meet them. The shift has three free components (x, y, z) but only
x and y matter for "are the hands touching", so this sweeps them and reports the true
3D distance from each anchor to the surface.

Output: the best (dx, dy), expressed as the height fraction the build should bake as
its grip, plus the residual gap.
"""
import os
import struct
import sys

import numpy as np
from scipy.spatial import cKDTree

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])
ANCHOR_MID = (ANCHOR_L + ANCHOR_R) * 0.5


def read_subs(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        colour = np.array(struct.unpack_from("<4f", d, o)); o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((flags, v, t))
    return subs


def sample_surface(v, t, count=60000, seed=0):
    rng = np.random.default_rng(seed)
    tri = v[t]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = areas.sum()
    n = min(count, max(4000, len(t) * 6))
    picks = rng.choice(len(t), size=n, p=areas / total)
    u = rng.random(n)
    w = rng.random(n)
    flip = (u + w) > 1.0
    u[flip] = 1.0 - u[flip]
    w[flip] = 1.0 - w[flip]
    return a[picks] + (b[picks] - a[picks]) * u[:, None] + (c[picks] - a[picks]) * w[:, None]


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs = read_subs(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[0] & 1)]
        v = np.concatenate([s[1] for s in solid])
        t = []
        off = 0
        for s in solid:
            t.append(s[2] + off); off += len(s[1])
        t = np.concatenate(t)
        lo, hi = v.min(axis=0), v.max(axis=0)
        height = hi[1] - lo[1]

        samples = sample_surface(v, t)
        tree = cKDTree(samples)
        # outward normal per sample: from the nearest vertex normal
        vn = np.zeros_like(v)
        tri = v[t]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        for k in range(3):
            np.add.at(vn, t[:, k], fn)
        ln = np.linalg.norm(vn, axis=1, keepdims=True)
        ln[ln < 1e-12] = 1.0
        vn /= ln
        vtree = cKDTree(v)
        _, vidx = vtree.query(samples)
        snorm = vn[vidx]

        def gap(point):
            dist, idx = tree.query(point)
            outward = np.dot(point - samples[idx], snorm[idx])
            return float(dist) if outward >= 0 else -float(dist)

        best = None
        print(f"===== {stem} =====  (height {height:.4f})")
        for frac in np.arange(0.06, 0.62, 0.01):
            y_grip = lo[1] + frac * height
            band = v[np.abs(v[:, 1] - y_grip) < height * 0.02]
            if len(band) == 0:
                continue
            mid_x = (band[:, 0].min() + band[:, 0].max()) * 0.5
            base_shift = np.array([ANCHOR_MID[0] - mid_x, ANCHOR_MID[1] - y_grip, 0.0])
            for ddx in (-0.04, -0.02, 0.0, 0.02, 0.04):
                shift = base_shift + np.array([ddx, 0.0, 0.0])
                gl = gap(ANCHOR_L - shift)
                gr = gap(ANCHOR_R - shift)
                score = abs(gl) + abs(gr)
                if best is None or score < best[0]:
                    best = (score, frac, ddx, gl, gr, shift)
        print(f"  best score={best[0]:.4f}  frac={best[1]:.2f}  ddx={best[2]:+.2f}  "
              f"gapL={best[3]:+.4f}  gapR={best[4]:+.4f}")
        print(f"  shift = {np.round(best[5], 4)}")

        # Report the top few so a trade-off (grip height look) can be judged.
        rows = []
        for frac in np.arange(0.10, 0.56, 0.01):
            y_grip = lo[1] + frac * height
            band = v[np.abs(v[:, 1] - y_grip) < height * 0.02]
            if len(band) == 0:
                continue
            mid_x = (band[:, 0].min() + band[:, 0].max()) * 0.5
            for ddx in (-0.04, -0.02, 0.0, 0.02, 0.04):
                shift = np.array([ANCHOR_MID[0] - mid_x + ddx, ANCHOR_MID[1] - y_grip, 0.0])
                gl = gap(ANCHOR_L - shift)
                gr = gap(ANCHOR_R - shift)
                rows.append((abs(gl) + abs(gr), frac, ddx, gl, gr))
        rows.sort()
        print("  top 8:")
        for r in rows[:8]:
            print(f"    score={r[0]:.4f} frac={r[1]:.2f} ddx={r[2]:+.2f} "
                  f"gapL={r[3]:+.4f} gapR={r[4]:+.4f}")


if __name__ == "__main__":
    main()
