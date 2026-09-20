"""Score the SHIPPED assets/<stem>.psmesh outline against the body it ships with.

This is the end-to-end check: it reads only the files the game loads, rasterises the
body and the ink shell exactly as the game draws them (shell with front faces culled,
depth-tested against the body), and reports how much of the visible silhouette has no
ink next to it.

Run:
    python research/score_shipped.py
"""
import math
import os
import struct

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "preview")
RES = 1200
ANGLES = (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330)
DARK = 0.45


def read(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        col = np.frombuffer(d[o:o + 16], "<f4").astype(np.float64); o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((col, flags, v, t))
    return subs


def raster(pts, tris, tri_bright, w, h, centre, scale, cull_front=False):
    depth = np.full((h, w), 1e30)
    bright = np.zeros((h, w), dtype=bool)
    p = (pts - centre) * scale
    px = p[:, 0] + w * 0.5
    py = h * 0.5 - p[:, 1]
    pz = p[:, 2]
    for fi, t in enumerate(tris):
        x0, y0, z0 = px[t[0]], py[t[0]], pz[t[0]]
        x1, y1, z1 = px[t[1]], py[t[1]], pz[t[1]]
        x2, y2, z2 = px[t[2]], py[t[2]], pz[t[2]]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        if cull_front and area > 0:
            continue
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
        if tri_bright is not None:
            bright[yy[closer], xx[closer]] = tri_bright[fi]
    return depth, bright


def silhouette(mask):
    m = mask.astype(bool)
    up = np.zeros_like(m); up[1:, :] = m[:-1, :]
    dn = np.zeros_like(m); dn[:-1, :] = m[1:, :]
    lf = np.zeros_like(m); lf[:, 1:] = m[:, :-1]
    rt = np.zeros_like(m); rt[:, :-1] = m[:, 1:]
    return m & ~(up & dn & lf & rt)


def dilate(mask, r):
    out = mask.astype(bool).copy()
    for _ in range(r):
        n = out.copy()
        n[1:, :] |= out[:-1, :]
        n[:-1, :] |= out[1:, :]
        n[:, 1:] |= out[:, :-1]
        n[:, :-1] |= out[:, 1:]
        out = n
    return out


def longest(mask):
    best = 0
    for arr in (mask, mask.T):
        for row in arr:
            run = 0
            for v in row:
                run = run + 1 if v else 0
                if run > best:
                    best = run
    return best


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        body = [(c, v, t) for c, f, v, t in subs if not (f & 1)]
        shell = [t for c, f, v, t in subs if f & 1]

        bv = np.concatenate([v for _, v, _ in body])
        bt = []
        tri_bright = []
        off = 0
        for col, v, t in body:
            bt.append(t + off)
            tri_bright.append(1.0 if float(np.asarray(col[:3]).mean()) > DARK else 0.0)
            off += len(v)
        bt = np.concatenate(bt)
        tri_bright = np.array(tri_bright)

        sv = np.concatenate([v for f, v, t in subs if f & 1])
        st = []
        off = 0
        for c, f, v, t in subs:
            if f & 1:
                st.append(t + off)
                off += len(v)
        st = np.concatenate(st)

        allv = np.concatenate([bv, sv])
        lo, hi = allv.min(axis=0), allv.max(axis=0)
        centre = (lo + hi) * 0.5
        scale = RES * 0.8 / max(hi - lo)

        tot_sil = tot_bright = tot_break = 0
        worst = 0
        for angle in ANGLES:
            c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            rot = lambda P: np.column_stack([P[:, 0] * c + P[:, 2] * s, P[:, 1],  # noqa: E731
                                             -P[:, 0] * s + P[:, 2] * c])
            bpts, spts = rot(bv), rot(sv)
            bdepth, bright = raster(bpts, bt, tri_bright, RES, RES, centre, scale)
            sdepth, _ = raster(spts, st, None, RES, RES, centre, scale, cull_front=True)
            bmask = bdepth < 1e29
            ink = (sdepth < 1e29) & (sdepth < bdepth)
            sil = silhouette(bmask)
            vis = sil & bright & ~dilate(ink, 5)
            tot_sil += int(sil.sum())
            tot_bright += int((sil & bright).sum())
            tot_break += int(vis.sum())
            worst = max(worst, longest(vis))

        print(f"{stem:12s} shell={len(st):6d} tris  silhouette={tot_sil:7d}  "
              f"bright={tot_bright:7d}  visible-break={tot_break:6d} "
              f"({100.0*tot_break/max(1,tot_bright):5.2f}% of bright silhouette)  "
              f"longest-run={worst:4d}px")


if __name__ == "__main__":
    main()
