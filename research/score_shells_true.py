"""True ink coverage: rasterise the shell exactly as the game draws it.

The game draws the ink shell with front faces culled, so only the shell's
back-facing triangles are rasterised (with a depth test against the opaque body).
That is what makes an inverted hull draw only the band poking out around the
silhouette. Simulating anything else gives the wrong answer about stray ink.

Two numbers per variant, over several camera angles:

  missing   silhouette pixels with no ink just outside them -> the line is broken
  stray     ink pixels that lie well inside the body silhouette -> a line across
            the body (the classic inverted-hull artefact on concave shapes)
"""
import math
import os

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
BLENDER = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 1200
ANGLES = (0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330)
TAGS = ("current", "nomask_blend", "smoothwidth")


def read_obj(path):
    verts, groups, cur = [], {}, None
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


def prepare(verts, rot):
    pts = verts.copy()
    if rot:
        c, s = math.cos(rot), math.sin(rot)
        pts = np.column_stack([pts[:, 0] * c + pts[:, 2] * s,
                               pts[:, 1],
                               -pts[:, 0] * s + pts[:, 2] * c])
    return pts


def raster(pts, tris, w, h, centre, scale, cull_front=False):
    depth = np.full((h, w), 1e30)
    p = (pts - centre) * scale
    px = p[:, 0] + w * 0.5
    py = h * 0.5 - p[:, 1]
    pz = p[:, 2]
    for t in tris:
        i0, i1, i2 = t
        x0, y0, z0 = px[i0], py[i0], pz[i0]
        x1, y1, z1 = px[i1], py[i1], pz[i1]
        x2, y2, z2 = px[i2], py[i2], pz[i2]
        # signed area in screen space; camera looks down -Z with y up, so a
        # counter-clockwise (front-facing) triangle has positive area here
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
        v = (d00 * (gy - y0) - d10 * (gx - x0)) / denom
        wc = 1.0 - u - v
        inside = (u >= -1e-6) & (v >= -1e-6) & (wc >= -1e-6)
        if not inside.any():
            continue
        z = wc * z0 + u * z1 + v * z2
        yy, xx = np.nonzero(inside)
        yy += miny
        xx += minx
        closer = z[inside] < depth[yy, xx]
        depth[yy[closer], xx[closer]] = z[inside][closer]
    return depth


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


def erode(mask, r):
    return ~dilate(~mask.astype(bool), r)


def main():
    for stem in ("miffy", "zichaoxiong"):
        verts, groups = read_obj(os.path.join(BLENDER, f"var_{stem}_nomask_blend.obj"))
        body_tris = groups["body"]
        idx = np.unique(np.array([i for f in body_tris for i in f]))
        body_v = verts[idx]
        lo, hi = body_v.min(axis=0), body_v.max(axis=0)
        centre = (lo + hi) * 0.5
        scale = RES * 0.8 / max(hi - lo)

        for tag in TAGS:
            path = os.path.join(BLENDER, f"var_{stem}_{tag}.obj")
            if not os.path.isfile(path):
                continue
            v, g = read_obj(path)
            shell_tris = g.get("shell", [])
            tot_sil = tot_missing = tot_ink = tot_stray = 0
            for angle in ANGLES:
                pts = prepare(v, math.radians(angle))
                bdepth = raster(pts, g["body"], RES, RES, centre, scale)
                sdepth = raster(pts, shell_tris, RES, RES, centre, scale, cull_front=True)
                bmask = bdepth < 1e29
                ink = (sdepth < 1e29) & (sdepth < bdepth)
                sil = silhouette(bmask)
                missing = sil & ~dilate(ink, 5)
                # "stray" = ink at least 10 px inside the body silhouette, so the
                # legitimate band hugging the edge is excluded
                stray = ink & erode(bmask, 10)
                tot_sil += int(sil.sum())
                tot_missing += int(missing.sum())
                tot_ink += int(ink.sum())
                tot_stray += int(stray.sum())
                if angle == 0:
                    img = np.zeros((RES, RES, 3), dtype=np.uint8)
                    img[bmask] = (225, 225, 220)
                    img[ink] = (30, 30, 35)
                    img[stray] = (255, 40, 40)
                    img[missing] = (0, 150, 255)
                    Image.fromarray(img[::-1]).save(
                        os.path.join(OUT, f"true_{stem}_{tag}_000.png"))
            print(f"{stem:12s} {tag:14s} silhouette={tot_sil:7d} "
                  f"missing={tot_missing:7d} ({100.0*tot_missing/max(1,tot_sil):5.2f}%)  "
                  f"ink={tot_ink:7d} stray={tot_stray:6d} "
                  f"({100.0*tot_stray/max(1,tot_ink):5.2f}%)")


if __name__ == "__main__":
    main()
