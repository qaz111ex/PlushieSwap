"""Look at the eye region of each shell variant, zoomed, with the true draw rule.

The build masks the ink shell to stop the hull drawing a ring around each recessed
eye/mouth/blush. The masks also cut a fifth of the silhouette away, so before dropping
them this renders the face at high zoom for both variants and marks stray ink (ink
that lies well inside the body silhouette) in red.
"""
import math
import os

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
BLENDER = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 1600


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


def raster(pts, tris, w, h, centre, scale, cull_front=False):
    depth = np.full((h, w), 1e30)
    p = (pts - centre) * scale
    px = p[:, 0] + w * 0.5
    py = h * 0.5 - p[:, 1]
    pz = p[:, 2]
    for t in tris:
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
    return depth


def erode(mask, r):
    out = mask.astype(bool).copy()
    for _ in range(r):
        n = out.copy()
        n[1:, :] &= out[:-1, :]
        n[:-1, :] &= out[1:, :]
        n[:, 1:] &= out[:, :-1]
        n[:, :-1] &= out[:, 1:]
        out = n
    return out


def main():
    for stem in ("miffy", "zichaoxiong"):
        verts, groups = read_obj(os.path.join(BLENDER, f"var_{stem}_nomask_blend.obj"))
        idx = np.unique(np.array([i for f in groups["body"] for i in f]))
        body_v = verts[idx]
        lo, hi = body_v.min(axis=0), body_v.max(axis=0)
        centre = (lo + hi) * 0.5
        scale = RES * 0.8 / max(hi - lo)

        for tag in ("current", "nomask_blend", "faceonly"):
            path = os.path.join(BLENDER, f"var_{stem}_{tag}.obj")
            if not os.path.isfile(path):
                continue
            v, g = read_obj(path)
            bdepth = raster(v, g["body"], RES, RES, centre, scale)
            sdepth = raster(v, g["shell"], RES, RES, centre, scale, cull_front=True)
            bmask = bdepth < 1e29
            ink = (sdepth < 1e29) & (sdepth < bdepth)
            stray = ink & erode(bmask, 14)

            img = np.zeros((RES, RES, 3), dtype=np.uint8)
            img[bmask] = (232, 232, 226)
            img[ink] = (25, 25, 30)
            img[stray] = (255, 40, 40)

            # head: the face features sit at 55-75% of the model height
            y0 = int(RES * (1.0 - (0.78 * 0.8 + 0.1)))
            y1 = int(RES * (1.0 - (0.50 * 0.8 + 0.1)))
            crop = img[y0:y1, int(RES * 0.28):int(RES * 0.72)]
            Image.fromarray(crop[::-1]).save(
                os.path.join(OUT, f"eye_{stem}_{tag}.png"))
            print(f"{stem:12s} {tag:14s} stray={int(stray.sum()):6d}  "
                  f"-> eye_{stem}_{tag}.png")


if __name__ == "__main__":
    main()
