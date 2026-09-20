"""Render candidate model placements with the hand anchors marked.

Candidates:
  current : what the mod ships today (grip fraction baked at build time)
  edge    : both anchors exactly on the model's silhouette
  inset   : both anchors one fist-radius inside the silhouette, the way the vanilla
            plush sits relative to its own anchors

Run:
    python research/preview_placements.py
"""
import math
import os
import struct

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "preview")
RES = 1000

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


def raster(v, t, w, h, centre, scale, rot=0.0):
    depth = np.full((h, w), 1e30)
    pts = v.copy()
    if rot:
        c, s = math.cos(rot), math.sin(rot)
        pts = np.column_stack([pts[:, 0] * c + pts[:, 2] * s, pts[:, 1],
                               -pts[:, 0] * s + pts[:, 2] * c])
    p = (pts - centre) * scale
    px = p[:, 0] + w * 0.5
    py = h * 0.5 - p[:, 1]
    pz = p[:, 2]
    for tri in t:
        x0, y0, z0 = px[tri[0]], py[tri[0]], pz[tri[0]]
        x1, y1, z1 = px[tri[1]], py[tri[1]], pz[tri[1]]
        x2, y2, z2 = px[tri[2]], py[tri[2]], pz[tri[2]]
        minx = max(0, int(math.floor(min(x0, x1, x2))))
        maxx = min(w - 1, int(math.ceil(max(x0, x1, x2))))
        miny = max(0, int(math.floor(min(y0, y1, y2))))
        maxy = min(h - 1, int(math.ceil(max(y0, y1, y2))))
        if maxx < minx or maxy < miny:
            continue
        d00, d01 = x1 - x0, y1 - y0
        d10, d11 = x2 - x0, y2 - y0
        denom = d00 * d11 - d10 * d01
        if abs(denom) < 1e-9:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        u = (d11 * (gx - x0) - d01 * (gy - y0)) / denom
        vv = (d00 * (gy - y0) - d10 * (gx - x0)) / denom
        wc = 1.0 - u - vv
        inside = (u >= -1e-6) & (vv >= -1e-6) & (wc >= -1e-6)
        if not inside.any():
            continue
        z = wc * z0 + u * z1 + vv * z2
        yy, xx = np.nonzero(inside)
        yy += miny
        xx += minx
        closer = z[inside] < depth[yy, xx]
        depth[yy[closer], xx[closer]] = z[inside][closer]
    return depth < 1e29


def edges(v, height, band_frac=0.012):
    band = height * band_frac

    def left(y):
        b = v[np.abs(v[:, 1] - y) <= band]
        return b[:, 0].min() if len(b) else np.nan

    def right(y):
        b = v[np.abs(v[:, 1] - y) <= band]
        return b[:, 0].max() if len(b) else np.nan

    return left, right


def solve(v, height, inset_l, inset_r):
    lo, hi = v.min(axis=0), v.max(axis=0)
    left, right = edges(v, height)
    best = None
    for dy in np.arange(-0.20, 0.60, 0.002):
        yL = ANCHOR_L[1] - dy
        yR = ANCHOR_R[1] - dy
        if yL < lo[1] or yR > hi[1]:
            continue
        l = left(yL)
        r = right(yR)
        if np.isnan(l) or np.isnan(r):
            continue
        want = (ANCHOR_R[0] - inset_r) - (ANCHOR_L[0] + inset_l)
        err = abs((r - l) - want)
        if best is None or err < best[0]:
            best = (err, dy, l, r)
    err, dy, l, r = best
    dx = ANCHOR_L[0] - inset_l - l
    return dx, dy, err


def main():
    cases = {
        "miffy": [(0.22, 0.0, 0.0), (None, 0.0, 0.0), (None, 0.10, 0.10)],
        "zichaoxiong": [(0.26, 0.0, 0.0), (None, 0.0, 0.0), (None, 0.10, 0.10)],
    }
    names = ("current", "edge", "inset")

    for stem, specs in cases.items():
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

        for name, (frac, inset_l, inset_r) in zip(names, specs):
            if frac is not None:
                y_grip = lo[1] + frac * height
                band = v[np.abs(v[:, 1] - y_grip) < height * 0.02]
                mid_x = (band[:, 0].min() + band[:, 0].max()) * 0.5
                dx = ANCHOR_MID[0] - mid_x
                dy = ANCHOR_MID[1] - y_grip
                err = float("nan")
            else:
                dx, dy, err = solve(v, height, inset_l, inset_r)
            shift = np.array([dx, dy, 0.0])
            moved = v + shift

            centre = np.array([ANCHOR_MID[0], ANCHOR_MID[1], 0.0])
            scale = RES * 0.85 / 1.1
            mask = raster(moved, t, RES, RES, centre, scale)

            img = np.zeros((RES, RES, 3), dtype=np.uint8)
            img[mask] = (235, 235, 230)
            for tag, a in (("L", ANCHOR_L), ("R", ANCHOR_R)):
                cx = int(round((a[0] - centre[0]) * scale + RES * 0.5))
                cy = int(round(RES * 0.5 - (a[1] - centre[1]) * scale))
                col = (255, 60, 60) if tag == "L" else (60, 200, 255)
                for d in range(-16, 17):
                    for w in (-1, 0, 1):
                        for (xx, yy) in ((cx + d, cy + w), (cx + w, cy + d)):
                            if 0 <= xx < RES and 0 <= yy < RES:
                                img[yy, xx] = col
            path = os.path.join(OUT, f"place_{stem}_{name}.png")
            Image.fromarray(img[::-1]).save(path)
            print(f"{stem:12s} {name:8s} shift=({dx:+.4f},{dy:+.4f}) "
                  f"widthErr={err:.4f}  -> {os.path.basename(path)}")


if __name__ == "__main__":
    main()
