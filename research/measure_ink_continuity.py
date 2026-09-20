"""Measure ink continuity along the silhouette, for each outline variant.

Renders each variant's body and body+shell in the same front view, then walks the
body's silhouette and asks: is there a dark (ink) pixel within a small radius just
outside it? A gap in the outline is a run of silhouette pixels with no ink.

This is the numeric version of "the outline is broken" — it reports how much of the
silhouette is un-inked and where the longest un-inked run is.

Run:
    python research\measure_ink_continuity.py
"""
import math
import os

import numpy as np
from PIL import Image

ROOT = r"D:\zhuanban\Plushie Swap"
OUT = os.path.join(ROOT, "research", "preview")
RES = 1200
ANGLE = 0.0


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
                idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                groups[cur].append(idx)
    return np.array(verts), groups


def rasterise(verts, tris, w, h, centre, scale):
    """Orthographic front view (-Z), painter's algorithm with a z-buffer."""
    depth = np.full((h, w), 1e30)
    colour = np.zeros((h, w, 3), dtype=np.float32)
    pts = (verts - centre) * scale
    px = pts[:, 0] + w * 0.5
    py = h * 0.5 - pts[:, 1]
    pz = pts[:, 2]
    for t in tris:
        x0, y0, z0 = px[t[0]], py[t[0]], pz[t[0]]
        x1, y1, z1 = px[t[1]], py[t[1]], pz[t[1]]
        x2, y2, z2 = px[t[2]], py[t[2]], pz[t[2]]
        minx, maxx = int(max(0, math.floor(min(x0, x1, x2)))), int(min(w - 1, math.ceil(max(x0, x1, x2))))
        miny, maxy = int(max(0, math.floor(min(y0, y1, y2)))), int(min(h - 1, math.ceil(max(y0, y1, y2))))
        if maxx < minx or maxy < miny:
            continue
        d00 = x1 - x0
        d01 = y1 - y0
        d10 = x2 - x0
        d11 = y2 - y0
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
        colour[yy[closer], xx[closer]] = 0.0
    return depth < 1e29

def silhouette(mask):
    """Boundary pixels of a filled mask (4-neighbour)."""
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
        verts, groups = read_obj(os.path.join(ROOT, "research", "blender",
                                              f"var_{stem}_nomask_blend.obj"))
        body = groups["body"]
        body_set = set(i for f in body for i in f)
        body_v = verts[list(body_set)]
        lo, hi = body_v.min(axis=0), body_v.max(axis=0)
        centre = (lo + hi) * 0.5
        size = max(hi - lo)
        scale = RES * 0.8 / size

        for tag in ("current", "nomask_blend", "nomask_normal", "faceonly"):
            path = os.path.join(ROOT, "research", "blender", f"var_{stem}_{tag}.obj")
            if not os.path.isfile(path):
                continue
            v, g = read_obj(path)
            all_tris = [t for ts in g.values() for t in ts]
            shell_tris = g.get("shell", [])
            if not shell_tris:
                continue
            shell_set = set(i for f in shell_tris for i in f)
            # body only
            body_mask = np.zeros((RES, RES), dtype=bool)
            bv = v[list(set(i for f in g["body"] for i in f))]
            bdepth = rasterise(v, g["body"], RES, RES, centre, scale)
            # The shell is drawn with front faces culled, so only the part of it that
            # lies *outside* the body silhouette is visible. That visible band is the
            # ink. Anything painted outside the body counts.
            sdepth = rasterise(v, shell_tris, RES, RES, centre, scale)
            bmask = bdepth.astype(bool)
            smask = sdepth.astype(bool)
            sil = silhouette(bmask)
            ring = dilate(bmask, 6) & ~bmask
            covered = ring & smask
            missing = sil & ~dilate(smask, 4)
            print(f"{stem:12s} {tag:14s} silhouette px={sil.sum():6d}  "
                  f"no-ink px={missing.sum():6d} ({100.0*missing.sum()/max(1,sil.sum()):5.1f}%)  "
                  f"ring covered={100.0*covered.sum()/max(1,ring.sum()):5.1f}%")
            img = np.zeros((RES, RES, 3), dtype=np.uint8)
            img[bmask] = (230, 230, 225)
            img[smask & ~bmask] = (20, 20, 25)
            img[missing] = (255, 0, 0)
            Image.fromarray(img[::-1]).save(
                os.path.join(OUT, f"continuity_{stem}_{tag}.png"))


if __name__ == "__main__":
    main()
