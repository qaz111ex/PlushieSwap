"""Distance from each hand anchor to the plush surface, as the grip height varies.

The game snaps the hand rigs to fixed item-local positions and the mod shifts the model
to meet them. The one free choice is how far up or down the model sits, which decides
where the hands land. This sweeps that choice and reports the true 3D distance from
each anchor to the nearest surface point, so the grip height can be picked from data:

  * distance > ~0.03 : the hand is visibly holding air
  * distance ~ 0     : the hand rests on the surface
  * distance < 0     : the hand is inside the body (a firm grip, but too deep is bad)

Run:
    python research\measure_grip_distance.py
"""
import os
import struct

import numpy as np
from scipy.spatial import cKDTree

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])
ANCHOR_MID = (ANCHOR_L + ANCHOR_R) * 0.5

# the player's hand mesh is about this big, so contact is "within half a hand"
HAND_RADIUS = 0.05


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


def sample_surface(v, t, count=40000, seed=0):
    """Uniform-ish points on the mesh surface, for a distance query."""
    rng = np.random.default_rng(seed)
    tri = v[t]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = areas.sum()
    if total <= 0:
        return v
    n = min(count, max(2000, len(t) * 4))
    picks = rng.choice(len(t), size=n, p=areas / total)
    u = rng.random(n)
    w = rng.random(n)
    flip = (u + w) > 1.0
    u[flip] = 1.0 - u[flip]
    w[flip] = 1.0 - w[flip]
    return a[picks] + (b[picks] - a[picks]) * u[:, None] + (c[picks] - a[picks]) * w[:, None]


def signed_gap(point, samples, normals, tree):
    """Distance to the surface, positive outside and negative inside.

    The sign comes from the nearest sample's outward normal, which is enough for a
    convex-ish body: a point outside is on the side the normal points to.
    """
    dist, idx = tree.query(point)
    outward = np.dot(point - samples[idx], normals[idx])
    return float(dist) if outward >= 0 else -float(dist)


def vertex_normals(v, t):
    n = np.zeros_like(v)
    tri = v[t]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(n, t[:, k], fn)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    length[length < 1e-12] = 1.0
    return n / length


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
        normals = vertex_normals(v, t)
        # normals for the samples: use the nearest vertex normal
        vtree = cKDTree(v)
        _, vidx = vtree.query(samples)
        snorm = normals[vidx]
        tree = cKDTree(samples)

        print(f"===== {stem} ===== height {height:.4f}")
        print("  frac   shiftY   gapL     gapR    |gap|   verdict")
        best = None
        for k in range(4, 81):
            frac = k / 100.0
            y_grip = lo[1] + frac * height
            band = v[np.abs(v[:, 1] - y_grip) < height * 0.02]
            if len(band) == 0:
                continue
            mid_x = (band[:, 0].min() + band[:, 0].max()) * 0.5
            shift = ANCHOR_MID - np.array([mid_x, y_grip, 0.0])
            hand_l = ANCHOR_L - shift
            hand_r = ANCHOR_R - shift
            gl = signed_gap(hand_l, samples, snorm, tree)
            gr = signed_gap(hand_r, samples, snorm, tree)
            score = abs(gl) + abs(gr)
            verdict = "AIR" if min(gl, gr) > HAND_RADIUS * 0.5 else (
                "inside" if max(gl, gr) < -HAND_RADIUS else "contact")
            print(f"  {frac:.2f}  {shift[1]:+.4f}  {gl:+.4f}  {gr:+.4f}  {score:.4f}  {verdict}")
            if best is None or score < best[0]:
                best = (score, frac, gl, gr)
        print(f"  best: frac={best[1]:.2f}  gaps=({best[2]:+.4f},{best[3]:+.4f})  "
              f"score={best[0]:.4f}")


if __name__ == "__main__":
    main()
