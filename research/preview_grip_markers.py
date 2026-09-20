"""Draw the plush exactly as the game holds it, with the two hand anchors marked.

The game snaps the hand rigs to fixed item-local positions (read from the vanilla
prefab) and the mod shifts the model to meet them. This reproduces that shift for a
chosen grip height and draws the result in the front view, with a crosshair at each
hand anchor. A crosshair that lands on the silhouette is a grip; one that lands in
empty space is "holding air".

Run:
    python research\preview_grip_markers.py
"""
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "preview")
sys.path.insert(0, os.path.join(ROOT, "tools"))

RES = 900
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
        subs.append((colour, flags, v, t))
    return subs


def raster(verts, tris, w, h, centre, scale):
    mask = np.zeros((h, w), dtype=bool)
    p = (verts - centre) * scale
    px = p[:, 0] + w * 0.5
    py = h * 0.5 - p[:, 1]
    for t in tris:
        x0, y0 = px[t[0]], py[t[0]]
        x1, y1 = px[t[1]], py[t[1]]
        x2, y2 = px[t[2]], py[t[2]]
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
        v = (d00 * (gy - y0) - d10 * (gx - x0)) / denom
        wc = 1.0 - u - v
        inside = (u >= -1e-6) & (v >= -1e-6) & (wc >= -1e-6)
        if not inside.any():
            continue
        yy, xx = np.nonzero(inside)
        mask[yy + miny, xx + minx] = True
    return mask


def main():
    import build_meshes as bm

    cases = [("miffy", 0.22), ("miffy", 0.44), ("miffy", 0.40),
             ("zichaoxiong", 0.26)]

    for stem, frac in cases:
        subs = read_subs(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[1] & 1)]
        v = np.concatenate([s[2] for s in solid])
        t = []
        off = 0
        for s in solid:
            t.append(s[3] + off); off += len(s[2])
        t = np.concatenate(t)

        lo, hi = v.min(axis=0), v.max(axis=0)
        grips = bm.compute_grip_points([(s[0], s[2], None, s[3], None, 0) for s in solid],
                                       (lo, hi), frac, 0.04)
        waist_mid = (grips["hand_left"] + grips["hand_right"]) * 0.5
        offset = ANCHOR_MID - waist_mid
        shifted = v + offset

        # centre the image on the ITEM, not the model, so the hand marks are meaningful
        centre = np.array([ANCHOR_MID[0], ANCHOR_MID[1], 0.0])
        scale = RES * 0.85 / 1.1
        mask = raster(shifted, t, RES, RES, centre, scale)

        img = np.zeros((RES, RES, 3), dtype=np.uint8)
        img[mask] = (235, 235, 230)

        for name, a in (("L", ANCHOR_L), ("R", ANCHOR_R)):
            px = int(round((a[0] - centre[0]) * scale + RES * 0.5))
            py = int(round(RES * 0.5 - (a[1] - centre[1]) * scale))
            col = (255, 60, 60) if name == "L" else (60, 200, 255)
            for d in range(-14, 15):
                for w in (-1, 0, 1):
                    x, y = px + d, py + w
                    if 0 <= x < RES and 0 <= y < RES:
                        img[y, x] = col
                    x, y = px + w, py + d
                    if 0 <= x < RES and 0 <= y < RES:
                        img[y, x] = col

        path = os.path.join(OUT, f"gripmark_{stem}_{int(frac*100):02d}.png")
        Image.fromarray(img[::-1]).save(path)
        print(f"{stem} frac={frac:.2f}  offset={np.round(offset,4)}  "
              f"grip L={np.round(grips['hand_left'],4)} R={np.round(grips['hand_right'],4)}  -> {path}")


if __name__ == "__main__":
    main()
