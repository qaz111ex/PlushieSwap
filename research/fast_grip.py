"""Find the model placement (scale, dx, dy, dz) that puts both hands on the plush.

The two hand anchors are fixed in item-local space (read from the vanilla prefab):
Hand_L at (-0.359, -0.177, -0.040), Hand_R at (+0.240, -0.104, -0.040). The mod may
place the model anywhere relative to them. This searches that placement for the one
where both hands are in contact with the surface.

The surface point cloud is built once; a candidate placement is tested by transforming
the two query points back into model space, so the search is a few thousand KD-tree
lookups instead of a few thousand tree builds.
"""
import os
import struct

import numpy as np
from scipy.spatial import cKDTree

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])
ANCHORS = np.array([ANCHOR_L, ANCHOR_R])


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


def build(v, t, count=150000, seed=3):
    rng = np.random.default_rng(seed)
    tri = v[t]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    picks = rng.choice(len(t), size=count, p=areas / areas.sum())
    u = rng.random(count)
    w = rng.random(count)
    flip = (u + w) > 1.0
    u[flip] = 1.0 - u[flip]
    w[flip] = 1.0 - w[flip]
    pts = a[picks] + (b[picks] - a[picks]) * u[:, None] + (c[picks] - a[picks]) * w[:, None]
    vn = np.zeros_like(v)
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(vn, t[:, k], fn)
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    ln[ln < 1e-12] = 1.0
    vn /= ln
    _, vidx = cKDTree(v).query(pts)
    return pts, vn[vidx], cKDTree(pts)


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
        centre = (v.min(axis=0) + v.max(axis=0)) * 0.5
        pts, nrm, tree = build(v, t)
        lo, hi = v.min(axis=0), v.max(axis=0)
        height = hi[1] - lo[1]
        print(f"===== {stem} =====  height {height:.4f}  X[{lo[0]:+.3f},{hi[0]:+.3f}]")

        def gaps(scale, shift):
            # world = (model - centre) * s + centre + shift
            # model = (world - centre - shift) / s + centre
            p = (ANCHORS - centre - shift) / scale + centre
            d, idx = tree.query(p)
            dot = np.einsum("ij,ij->i", p - pts[idx], nrm[idx])
            return np.where(dot >= 0, d, -d)

        def air(scale, shift):
            g = gaps(scale, shift)
            return np.maximum(g, 0.0).sum(), g

        best = None
        for scale in (1.00, 1.05, 1.10):
            for dx in np.arange(-0.10, 0.101, 0.01):
                for dy in np.arange(0.10, 0.461, 0.01):
                    for dz in np.arange(-0.24, 0.161, 0.02):
                        s, g = air(scale, np.array([dx, dy, dz]))
                        if best is None or s < best[0]:
                            best = (s, scale, dx, dy, dz, g)
        print(f"  coarse: air={best[0]:.4f} scale={best[1]:.2f} "
              f"shift=({best[2]:+.3f},{best[3]:+.3f},{best[4]:+.3f}) "
              f"gaps=({best[5][0]:+.4f},{best[5][1]:+.4f})")

        s0, sc0, dx0, dy0, dz0 = best[:5]
        for scale in np.arange(sc0 - 0.03, sc0 + 0.031, 0.01):
            for dx in np.arange(dx0 - 0.02, dx0 + 0.021, 0.005):
                for dy in np.arange(dy0 - 0.02, dy0 + 0.021, 0.005):
                    for dz in np.arange(dz0 - 0.03, dz0 + 0.031, 0.005):
                        s, g = air(scale, np.array([dx, dy, dz]))
                        if s < best[0]:
                            best = (s, scale, dx, dy, dz, g)
        print(f"  fine  : air={best[0]:.4f} scale={best[1]:.3f} "
              f"shift=({best[2]:+.4f},{best[3]:+.4f},{best[4]:+.4f}) "
              f"gaps=({best[5][0]:+.4f},{best[5][1]:+.4f})")

        # how sensitive is it? show the best air for each dy at scale 1
        print("  best air per dy (scale=1, dx/dz optimised):")
        for dy in np.arange(0.10, 0.461, 0.05):
            row = None
            for dx in np.arange(-0.10, 0.101, 0.01):
                for dz in np.arange(-0.24, 0.161, 0.02):
                    s, g = air(1.0, np.array([dx, dy, dz]))
                    if row is None or s < row[0]:
                        row = (s, dx, dz, g)
            yL = ANCHOR_L[1] - dy
            print(f"    dy={dy:+.2f} yLfrac={(yL-lo[1])/height:.2f} air={row[0]:.4f} "
                  f"dx={row[1]:+.2f} dz={row[2]:+.2f} gaps=({row[3][0]:+.4f},{row[3][1]:+.4f})")


if __name__ == "__main__":
    main()
