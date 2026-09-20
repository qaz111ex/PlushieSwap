"""Score each ink-shell variant on both failure modes.

  * missing ink  : silhouette pixels with no ink just outside them -> a broken line
  * interior ink : ink pixels far from the silhouette -> a stray line across the body

The right shell has both near zero. Rendering the shell with front faces culled is
what the game does, so the shell is rasterised and only the part of it that lies
*outside* the body silhouette is counted as visible ink (that is exactly the visible
band of an inverted hull). Interior ink is then the visible ink that is nowhere near
the silhouette.

Run:
    python research\score_shells.py
"""
import math
import os

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
BLENDER = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 1400
ANGLES = (0, 30, 60, 90, 120, 150, 180)
TAGS = ("current", "nomask_blend", "nomask_normal", "faceonly")


def read_obj(path):
    verts = []
    groups = {}
    cur = None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                _, x, y, z = line.split()
                verts.append((float(x), float(y), float(z)))
            elif line.startswith("o "):
                cur = line[2:].strip()
                groups[cur] = []
            elif line.startswith("f "):
                groups[cur].append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    return np.array(verts), groups


def rasterise(verts, tris, w, h, centre, scale, rot):
    depth = np.full((h, w), 1e30)
    pts = verts.copy()
    if rot:
        c, s = math.cos(rot), math.sin(rot)
        pts = np.column_stack([pts[:, 0] * c + pts[:, 2] * s,
                               pts[:, 1],
                               -pts[:, 0] * s + pts[:, 2] * c])
    pts = (pts - centre) * scale
    px = pts[:, 0] + w * 0.5
    py = h * 0.5 - pts[:, 1]
    pz = pts[:, 2]
    for t in tris:
        x0, y0, z0 = px[t[0]], py[t[0]], pz[t[0]]
        x1, y1, z1 = px[t[1]], py[t[1]], pz[t[1]]
        x2, y2, z2 = px[t[2]], py[t[2]], pz[t[2]]
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
        z = wc * z0 + u * z1 + v * z2
        yy, xx = np.nonzero(inside)
        yy = yy + miny
        xx = xx + minx
        closer = z[inside] < depth[yy, xx]
        depth[yy[closer], xx[closer]] = z[inside][closer]
    return depth < 1e29


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


def main():
    for stem in ("miffy", "zichaoxiong"):
        verts, groups = read_obj(os.path.join(BLENDER, f"var_{stem}_nomask_blend.obj"))
        body_tris = groups["body"]
        idx = np.unique(np.array([i for f in body_tris for i in f]))
        body_v = verts[idx]
        lo, hi = body_v.min(axis=0), body_v.max(axis=0)
        centre = (lo + hi) * 0.5
        size = max(hi - lo)
        scale = RES * 0.8 / size

        for tag in TAGS:
            path = os.path.join(BLENDER, f"var_{stem}_{tag}.obj")
            if not os.path.isfile(path):
                continue
            v, g = read_obj(path)
            shell_tris = g.get("shell", [])
            if not shell_tris:
                continue
            tot_sil = tot_missing = tot_interior = tot_ink = 0
            for angle in ANGLES:
                rot = math.radians(angle)
                bmask = rasterise(v, g["body"], RES, RES, centre, scale, rot)
                smask = rasterise(v, shell_tris, RES, RES, centre, scale, rot)
                ink = smask & ~bmask
                sil = silhouette(bmask)
                near = dilate(sil, 8)
                missing = sil & ~dilate(smask, 5)
                interior = ink & ~near
                tot_sil += int(sil.sum())
                tot_missing += int(missing.sum())
                tot_interior += int(interior.sum())
                tot_ink += int(ink.sum())
                if angle == 0:
                    img = np.zeros((RES, RES, 3), dtype=np.uint8)
                    img[bmask] = (225, 225, 220)
                    img[ink] = (30, 30, 35)
                    img[interior] = (255, 40, 40)
                    img[missing] = (0, 140, 255)
                    Image.fromarray(img[::-1]).save(
                        os.path.join(OUT, f"score_{stem}_{tag}_000.png"))
            print(f"{stem:12s} {tag:14s} silhouette={tot_sil:7d} "
                  f"missing={tot_missing:7d} ({100.0*tot_missing/max(1,tot_sil):5.2f}%)  "
                  f"ink={tot_ink:7d} interior={tot_interior:7d} "
                  f"({100.0*tot_interior/max(1,tot_ink):5.2f}%)")


if __name__ == "__main__":
    main()
