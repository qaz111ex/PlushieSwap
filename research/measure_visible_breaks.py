"""Measure outline breaks where they are actually visible.

The earlier metric counted a missing ink pixel as a break even when it sat on a dark
part of the plush (the eyes, the mouth, the blush). Those features are already dark,
so they read as a line by themselves and the hull is *supposed* to leave them alone.

This splits each variant's missing silhouette pixels by the body colour underneath:
only the ones on a bright surface are visible breaks. It also reports the longest
unbroken run of visible-break pixels, which is what "the line is broken" looks like.
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

# Body colours that are already dark enough to read as a drawn line on their own.
DARK = 0.45


def read_obj(path):
    verts, groups, cur = [], {}, None
    cols = []
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
    tid = np.full((h, w), -1, dtype=np.int64)
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
        tid[yy[closer], xx[closer]] = fi
    return depth, tid


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


def longest_run(mask):
    """Longest run of True along either axis, approximate (rows then columns)."""
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
        verts, groups = read_obj(os.path.join(BLENDER, f"var_{stem}_nomask_blend.obj"))
        idx = np.unique(np.array([i for f in groups["body"] for i in f]))
        body_v = verts[idx]
        lo, hi = body_v.min(axis=0), body_v.max(axis=0)
        centre = (lo + hi) * 0.5
        scale = RES * 0.8 / max(hi - lo)

        for tag in TAGS:
            path = os.path.join(BLENDER, f"var_{stem}_{tag}.obj")
            if not os.path.isfile(path):
                continue
            v, g = read_obj(path)
            # Which body triangles belong to a BRIGHT shell? The light shells are the
            # ones a missing line is visible against; a dark eye is its own line.
            bright_verts = np.load(os.path.join(BLENDER, f"var_{stem}_bright.npy"))
            tri_col = np.array([1.0 if bright_verts[t[0]] else 0.0 for t in g["body"]])
            tot_sil = tot_bright = tot_break = worst_run = 0
            for angle in ANGLES:
                c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                pts = np.column_stack([v[:, 0] * c + v[:, 2] * s, v[:, 1],
                                       -v[:, 0] * s + v[:, 2] * c])
                bdepth, btid = raster(pts, g["body"], RES, RES, centre, scale)
                sdepth, _ = raster(pts, g["shell"], RES, RES, centre, scale, cull_front=True)
                bmask = bdepth < 1e29
                ink = (sdepth < 1e29) & (sdepth < bdepth)
                sil = silhouette(bmask)

                # is the body surface under a silhouette pixel bright?
                bright = np.zeros_like(bmask)
                have = btid >= 0
                bright[have] = tri_col[btid[have]] > 0.5

                missing = sil & ~dilate(ink, 5)
                vis = missing & bright
                tot_sil += int(sil.sum())
                tot_bright += int((sil & bright).sum())
                tot_break += int(vis.sum())
                worst_run = max(worst_run, longest_run(vis))
                if angle == 0:
                    img = np.zeros((RES, RES, 3), dtype=np.uint8)
                    img[bmask] = (225, 225, 220)
                    img[ink] = (25, 25, 30)
                    img[vis] = (255, 40, 40)
                    img[missing & ~bright] = (255, 200, 0)
                    Image.fromarray(img[::-1]).save(
                        os.path.join(OUT, f"vis_{stem}_{tag}_000.png"))
            print(f"{stem:12s} {tag:14s} silhouette={tot_sil:7d} bright={tot_bright:7d} "
                  f"visible-break={tot_break:6d} "
                  f"({100.0*tot_break/max(1,tot_bright):5.2f}% of bright) "
                  f"longest-run={worst_run:4d}px")


if __name__ == "__main__":
    main()
