"""Render the shipped model at the hold offset baked into it, with hand anchors marked.

Reads the hold offset straight out of assets/<stem>.psmesh (so what is drawn is exactly
what the game will show) and draws the model in the front view with the two fixed hand
anchors as crosshairs. A crosshair on the silhouette is a grip.

Run:
    python research/preview_shipped_hold.py
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


def read(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        np.frombuffer(d[o:o + 16], "<f4"); o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((flags, v, t))
    bmin = np.frombuffer(d[o:o + 12], "<f4"); o += 12
    bmax = np.frombuffer(d[o:o + 12], "<f4"); o += 12
    hold = None
    (has,) = struct.unpack_from("<i", d, o); o += 4
    if has:
        o += 24 + 32
        hold = np.frombuffer(d[o:o + 12], "<f4").astype(np.float64); o += 12
    return subs, hold


def raster(v, t, w, h, centre, scale):
    depth = np.full((h, w), 1e30)
    p = (v - centre) * scale
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


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs, hold = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [(v, t) for flags, v, t in subs if not (flags & 1)]
        v = np.concatenate([s[0] for s in solid]) + (hold if hold is not None else 0.0)
        t = []
        off = 0
        for s in solid:
            t.append(s[1] + off); off += len(s[0])
        t = np.concatenate(t)

        centre = np.array([ANCHOR_MID[0], ANCHOR_MID[1], 0.0])
        scale = RES * 0.85 / 1.1
        mask = raster(v, t, RES, RES, centre, scale)

        img = np.zeros((RES, RES, 3), dtype=np.uint8)
        img[mask] = (235, 235, 230)
        for tag, a in (("L", ANCHOR_L), ("R", ANCHOR_R)):
            cx = int(round((a[0] - centre[0]) * scale + RES * 0.5))
            cy = int(round(RES * 0.5 - (a[1] - centre[1]) * scale))
            col = (255, 60, 60) if tag == "L" else (60, 200, 255)
            for d in range(-18, 19):
                for w in (-1, 0, 1):
                    for (xx, yy) in ((cx + d, cy + w), (cx + w, cy + d)):
                        if 0 <= xx < RES and 0 <= yy < RES:
                            img[yy, xx] = col
        path = os.path.join(OUT, f"shipped_hold_{stem}.png")
        Image.fromarray(img[::-1]).save(path)
        print(f"{stem:12s} hold={None if hold is None else np.round(hold,4)} -> {os.path.basename(path)}")


if __name__ == "__main__":
    main()
