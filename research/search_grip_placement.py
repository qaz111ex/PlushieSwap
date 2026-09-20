"""Search model placement (scale + dx + dy + dz) for a grip where both hands touch.

Uses a dense surface point cloud with a KD-tree so the search can cover a real grid,
then re-checks the winner with exact point-to-mesh distance.

Reports the gap at each hand: positive = air, negative = hand inside the surface.
"""
import os
import struct

import numpy as np
from scipy.spatial import cKDTree
import trimesh

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


def surface_points(v, t, count=120000, seed=1):
    rng = np.random.default_rng(seed)
    tri = v[t]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    p = areas / areas.sum()
    picks = rng.choice(len(t), size=count, p=p)
    u = rng.random(count)
    w = rng.random(count)
    flip = (u + w) > 1.0
    u[flip] = 1.0 - u[flip]
    w[flip] = 1.0 - w[flip]
    pts = a[picks] + (b[picks] - a[picks]) * u[:, None] + (c[picks] - a[picks]) * w[:, None]

    # outward normals for the sign test
    vn = np.zeros_like(v)
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(vn, t[:, k], fn)
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    ln[ln < 1e-12] = 1.0
    vn /= ln
    _, vidx = cKDTree(v).query(pts)
    return pts, vn[vidx]


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
        pts, nrm = surface_points(v, t)

        def gaps(scale, shift):
            p = (pts - centre) * scale + centre + shift
            tree = cKDTree(p)
            d, idx = tree.query(ANCHORS)
            dot = np.einsum("ij,ij->i", ANCHORS - p[idx], nrm[idx])
            signed = np.where(dot >= 0, d, -d)
            return signed

        best = None
        for scale in (0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20):
            for dx in np.arange(-0.10, 0.101, 0.02):
                for dy in np.arange(0.10, 0.401, 0.02):
                    for dz in np.arange(-0.06, 0.061, 0.02):
                        s = gaps(scale, np.array([dx, dy, dz]))
                        score = np.abs(s).sum()
                        if best is None or score < best[0]:
                            best = (score, scale, dx, dy, dz, s.copy())
        print(f"===== {stem} =====")
        print(f"  coarse best score={best[0]:.4f} scale={best[1]:.2f} "
              f"shift=({best[2]:+.3f},{best[3]:+.3f},{best[4]:+.3f}) "
              f"gaps=({best[5][0]:+.4f},{best[5][1]:+.4f})")

        s0, sc0, dx0, dy0, dz0 = best[:5]
        for scale in np.arange(sc0 - 0.04, sc0 + 0.041, 0.01):
            for dx in np.arange(dx0 - 0.02, dx0 + 0.021, 0.005):
                for dy in np.arange(dy0 - 0.02, dy0 + 0.021, 0.005):
                    for dz in np.arange(dz0 - 0.02, dz0 + 0.021, 0.005):
                        s = gaps(scale, np.array([dx, dy, dz]))
                        score = np.abs(s).sum()
                        if score < best[0]:
                            best = (score, scale, dx, dy, dz, s.copy())
        print(f"  refined     score={best[0]:.4f} scale={best[1]:.3f} "
              f"shift=({best[2]:+.4f},{best[3]:+.4f},{best[4]:+.4f}) "
              f"gaps=({best[5][0]:+.4f},{best[5][1]:+.4f})")

        # exact re-check
        m = trimesh.Trimesh(vertices=(v - centre) * best[1] + centre
                            + np.array(best[2:5]), faces=t, process=False)
        _, d, _ = trimesh.proximity.closest_point(m, ANCHORS)
        inside = m.contains(ANCHORS)
        signed = np.where(inside, -d, d)
        print(f"  exact       gaps=({signed[0]:+.4f},{signed[1]:+.4f}) inside={inside}")

        # what scale is needed if dy is the free rank-and-file grip height?
        print("  scale sweep at the best dy/dz (dx allowed to re-centre):")
        for scale in (1.00, 1.05, 1.10, 1.15, 1.20, 1.25):
            bb = None
            for dy in np.arange(0.10, 0.401, 0.005):
                for dz in np.arange(-0.10, 0.101, 0.005):
                    # dx is set so the model's mid-x matches the anchor mid-x
                    s = gaps(scale, np.array([0.0, dy, dz]))
                    # approximate dx by recentring on the widest band
                    score = np.abs(s).sum()
                    if bb is None or score < bb[0]:
                        bb = (score, dy, dz, s.copy())
            for dx in np.arange(-0.12, 0.121, 0.01):
                for dy in np.arange(0.10, 0.401, 0.01):
                    for dz in np.arange(-0.10, 0.101, 0.01):
                        s = gaps(scale, np.array([dx, dy, dz]))
                        score = np.abs(s).sum()
                        if score < bb[0]:
                            bb = (score, dy, dz, s.copy(), dx)
            print(f"    scale={scale:.2f} score={bb[0]:.4f} "
                  f"gaps=({bb[3][0]:+.4f},{bb[3][1]:+.4f})")


if __name__ == "__main__":
    main()
